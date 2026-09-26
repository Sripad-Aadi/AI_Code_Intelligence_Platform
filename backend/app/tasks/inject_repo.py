"""Celery task: ingest one cloned repository.

Steps 4 + 5 in one pass:
  1. Walk the clone, apply Step-4 filters, tally languages (histogram).
  2. Parse each survived file with tree-sitter (Step 5) and persist:
     files, symbols, imports, edges (file→file imports, symbol→file).
  3. Update the analysis_jobs row so the polling endpoint shows progress.
"""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from app.analysis.parsers import parse_source
from app.analysis.resolve import resolve_import
from app.config import settings
from app.db.session import db_session
from app.ingestion.filters import iter_source_files
from app.ingestion.language_detect import detect_language
from app.models.edge import CodeEdge
from app.models.file import SourceFile
from app.models.import_stmt import ImportStatement
from app.models.job import JOB_COMPLETED, JOB_FAILED, JOB_RUNNING, AnalysisJob
from app.models.repository import ProjectRepository
from app.models.symbol import Symbol
from app.worker import celery_app


def _clone_dir(repo: ProjectRepository) -> Path:
    """Mirror of the attach path layout: CLONE_ROOT_DIR/<project>/<owner>__<name>."""
    return (
        Path(settings.CLONE_ROOT_DIR)
        / str(repo.project_id)
        / f"{repo.github_owner}__{repo.github_name}"
    )


def _replace_repo_analysis(db, repo_id) -> None:
    """Drop prior files/symbols/imports/edges for a repo (fresh re-index)."""
    for model in (CodeEdge, ImportStatement, Symbol, SourceFile):
        db.query(model).filter(model.repo_id == repo_id).delete(
            synchronize_session=False
        )


@celery_app.task(bind=True, name="ingestion.ingest_repo")
def ingest_repo(self, job_id: str) -> dict:
    """Walk, filter, parse, and persist a repo's structure; finalize the job."""
    now = datetime.now(timezone.utc)
    with db_session() as db:
        job = db.get(AnalysisJob, job_id)
        if job is None:
            return {"ok": False, "error": f"job {job_id} not found"}

        job.status = JOB_RUNNING
        job.started_at = now
        try:
            repo = db.get(ProjectRepository, job.repo_id)
            if repo is None:
                raise ValueError(f"repository row for job {job_id} not found")

            clone_dir = _clone_dir(repo)
            if not clone_dir.is_dir():
                raise FileNotFoundError(
                    f"clone not found at {clone_dir} — attach the repository first"
                )

            _replace_repo_analysis(db, job.repo_id)

            # Raw count of every file entry in the tree (includes ignored files).
            files_scanned = sum(len(files) for _, _, files in os.walk(clone_dir))

            languages: dict[str, int] = {}
            files_indexed = 0
            symbols_indexed = 0
            files_by_path: dict[str, SourceFile] = {}
            pending_import_edges: list[tuple[str, uuid.UUID]] = []
            file_rows: list[SourceFile] = []
            symbol_rows: list[Symbol] = []
            import_rows: list[ImportStatement] = []
            edge_rows: list[CodeEdge] = []

            for file_path in iter_source_files(clone_dir):
                files_indexed += 1
                rel = file_path.relative_to(clone_dir)
                rel_posix = PurePosixPath(rel.as_posix())
                lang = detect_language(rel_posix)
                languages[lang] = languages.get(lang, 0) + 1

                try:
                    source = file_path.read_bytes()
                except OSError:
                    continue
                line_count = len(source.splitlines())

                parsed = parse_source(rel_posix, source)
                file_row = SourceFile(
                    id=uuid.uuid4(),
                    repo_id=job.repo_id,
                    path=rel_posix.as_posix(),
                    language=lang,
                    line_count=line_count,
                    parse_error=parsed.error,
                )
                file_rows.append(file_row)
                files_by_path[rel_posix.as_posix()] = file_row

                for sym in parsed.symbols:
                    sym_row = Symbol(
                        id=uuid.uuid4(),
                        repo_id=job.repo_id,
                        file_id=file_row.id,
                        kind=sym.kind,
                        name=sym.name,
                        start_line=sym.start_line,
                        end_line=sym.end_line,
                    )
                    symbol_rows.append(sym_row)
                    edge_rows.append(
                        CodeEdge(
                            id=uuid.uuid4(),
                            repo_id=job.repo_id,
                            source_kind="symbol",
                            source_id=sym_row.id,
                            edge_type="belongs_to",
                            target_id=file_row.id,
                        )
                    )
                    symbols_indexed += 1

                for imp in parsed.imports:
                    resolved = None
                    if parsed.grammar:
                        resolved = resolve_import(
                            grammar=parsed.grammar,
                            repo_root=clone_dir,
                            file_rel=rel_posix,
                            module=imp.module,
                        )
                    import_rows.append(
                        ImportStatement(
                            id=uuid.uuid4(),
                            repo_id=job.repo_id,
                            file_id=file_row.id,
                            module=imp.module,
                            is_relative=imp.is_relative,
                            resolved_path=resolved,
                        )
                    )
                    if resolved:
                        pending_import_edges.append((resolved, file_row.id))

            # Second pass: link imports to files that were actually indexed.
            for resolved_path, source_file_id in pending_import_edges:
                target = files_by_path.get(resolved_path)
                if target is not None:
                    edge_rows.append(
                        CodeEdge(
                            id=uuid.uuid4(),
                            repo_id=job.repo_id,
                            source_kind="file",
                            source_id=source_file_id,
                            edge_type="imports",
                            target_id=target.id,
                        )
                    )

            # Persist in dependency order with explicit flushes. The ORM's
            # unit-of-work sorts INSERTs by declared relationship()s, and this
            # project's models use no relationships — without the phased flush,
            # the edges INSERT can run before files/symbols exist and trip the
            # FK constraints (observed: edges inserted first).
            db.add_all(file_rows)
            db.flush()
            db.add_all(symbol_rows + import_rows)
            db.flush()
            db.add_all(edge_rows)

            job.files_scanned = files_scanned
            job.files_indexed = files_indexed
            job.symbols_indexed = symbols_indexed
            job.languages = languages or None
            job.status = JOB_COMPLETED
            job.finished_at = datetime.now(timezone.utc)
            # Commit inside the try so a commit-time failure still lands on the
            # job row below. db_session()'s outer commit then becomes a no-op.
            db.commit()
            return {
                "ok": True,
                "files_scanned": files_scanned,
                "files_indexed": files_indexed,
                "symbols_indexed": symbols_indexed,
                "languages": languages,
            }
        except Exception as exc:  # noqa: BLE001 — persist any failure on the job
            db.rollback()
            job.status = JOB_FAILED
            job.error = str(exc)[:2000]
            job.finished_at = datetime.now(timezone.utc)
            try:
                db.commit()
            except Exception:  # noqa: BLE001 — surface the original failure
                db.rollback()
            return {"ok": False, "error": str(exc)}
