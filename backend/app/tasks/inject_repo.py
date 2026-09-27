"""Celery task: ingest one cloned repository.

Steps 4 + 5 + 7 in one pass:
  1. Walk the clone, apply Step-4 filters, tally languages (histogram).
  2. Parse each survived file with tree-sitter (Step 5) and persist:
     files, symbols, imports, edges (file→file imports, symbol→file).
  3. Chunk each file (Step 7) from those exact symbol spans, embed the
     chunks on CPU, and persist code_embeddings rows.
  4. Update the analysis_jobs row so the polling endpoint shows progress.

The structural pass is committed *before* the embedding pass: the embedding
model is a ~1.5GB download, and losing a completed structural index because
that download failed would be a bad trade. An embedding failure downgrades
to a warning on the job instead (see `_embed_chunks`).
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Tuple

from app.analysis.parsers import parse_source
from app.analysis.resolve import resolve_import
from app.config import settings
from app.db.session import db_session
from app.embeddings.chunker import Chunk, chunk_file, contextualize
from app.ingestion.filters import iter_source_files
from app.ingestion.language_detect import detect_language
from app.models.code_embedding import EMBEDDING_DIM, CodeEmbedding
from app.models.edge import CodeEdge
from app.models.file import SourceFile
from app.models.import_stmt import ImportStatement
from app.models.job import JOB_COMPLETED, JOB_FAILED, JOB_RUNNING, AnalysisJob
from app.models.repository import ProjectRepository
from app.models.symbol import Symbol
from app.worker import celery_app

# Chunks embedded and INSERTed per round trip. Bounds peak memory (each row
# carries a 768-float vector) and gives the worker incremental progress.
EMBED_BATCH_ROWS = 200

log = logging.getLogger(__name__)


def _clone_dir(repo: ProjectRepository) -> Path:
    """Mirror of the attach path layout: CLONE_ROOT_DIR/<project>/<owner>__<name>."""
    return (
        Path(settings.CLONE_ROOT_DIR)
        / str(repo.project_id)
        / f"{repo.github_owner}__{repo.github_name}"
    )


def _replace_repo_analysis(db, repo_id) -> None:
    """Drop prior files/symbols/imports/edges/embeddings (fresh re-index)."""
    for model in (CodeEdge, ImportStatement, Symbol, CodeEmbedding, SourceFile):
        db.query(model).filter(model.repo_id == repo_id).delete(
            synchronize_session=False
        )


def _embed_chunks(
    db,
    *,
    repo_id,
    chunks: List[Chunk],
    file_ids_by_path: Dict[str, uuid.UUID],
) -> Tuple[int, Optional[str]]:
    """Embed chunks and insert them in batches.

    Returns `(rows_inserted, warning)`. Deliberately never raises: the
    structural index is already committed at this point, so a model that
    cannot load/downloaded-out-of-band must not fail the whole job.
    """
    if not chunks:
        return 0, None

    try:
        from app.embeddings.jina import embed_passages

        inserted = 0
        for start in range(0, len(chunks), EMBED_BATCH_ROWS):
            batch = chunks[start : start + EMBED_BATCH_ROWS]
            vectors = embed_passages([contextualize(chunk) for chunk in batch])

            if len(vectors) != len(batch):
                raise RuntimeError(
                    f"model returned {len(vectors)} vectors for {len(batch)} chunks"
                )
            wrong_dim = next((len(v) for v in vectors if len(v) != EMBEDDING_DIM), None)
            if wrong_dim is not None:
                raise RuntimeError(
                    f"model produced {wrong_dim}-d vectors but the column is "
                    f"vector({EMBEDDING_DIM}); change EMBEDDING_DIM in "
                    f"app/models/code_embedding.py and re-run the migration"
                )

            rows = [
                CodeEmbedding(
                    id=uuid.uuid4(),
                    repo_id=repo_id,
                    file_id=file_ids_by_path.get(chunk.file_path),
                    file_path=chunk.file_path,
                    language=chunk.language,
                    symbol_kind=chunk.symbol_kind,
                    symbol_name=chunk.symbol_name,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    content=chunk.content,
                    embedding=vector,
                )
                for chunk, vector in zip(batch, vectors)
            ]
            db.add_all(rows)
            db.flush()
            inserted += len(rows)
            log.info("embedded %d/%d chunks", inserted, len(chunks))
        return inserted, None
    except Exception as exc:  # noqa: BLE001 — never fail the job over this
        db.rollback()
        message = f"warning: embeddings skipped ({type(exc).__name__}: {exc})"
        log.warning("embedding pass failed, structure kept: %s", message)
        return 0, message[:2000]


@celery_app.task(bind=True, name="ingestion.ingest_repo")
def ingest_repo(self, job_id: str) -> dict:
    """Walk, filter, parse, chunk, embed, and persist; finalize the job."""
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
            # path -> file id (not the ORM row): the embedding phase runs after
            # a commit, and touching an expired SourceFile would re-query.
            file_ids_by_path: Dict[str, uuid.UUID] = {}
            pending_import_edges: list[tuple[str, uuid.UUID]] = []
            file_rows: list[SourceFile] = []
            symbol_rows: list[Symbol] = []
            import_rows: list[ImportStatement] = []
            edge_rows: list[CodeEdge] = []
            chunks: List[Chunk] = []

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
                file_ids_by_path[rel_posix.as_posix()] = file_row.id

                # Step 7: chunk straight off the spans tree-sitter just gave
                # us, so every chunk's line metadata is the parser's, not a
                # re-derivation that could drift.
                chunks.extend(
                    chunk_file(
                        file_path=rel_posix.as_posix(),
                        language=lang,
                        text=source.decode("utf-8", errors="replace"),
                        symbols=parsed.symbols,
                    )
                )

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
                target_id = file_ids_by_path.get(resolved_path)
                if target_id is not None:
                    edge_rows.append(
                        CodeEdge(
                            id=uuid.uuid4(),
                            repo_id=job.repo_id,
                            source_kind="file",
                            source_id=source_file_id,
                            edge_type="imports",
                            target_id=target_id,
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
            # Commit the structure before embedding: the embedding pass is slow
            # and depends on a ~1.5GB model, so a failure there must not cost
            # us the structural index. The job stays `running` until it ends.
            # Commit inside the try so a commit-time failure still lands on the
            # job row below. db_session()'s outer commit then becomes a no-op.
            db.commit()

            # Step 7: embed the chunks collected during the walk.
            chunks_indexed = 0
            embed_warning: Optional[str] = None
            if not settings.EMBEDDING_ENABLED:
                embed_warning = "warning: embeddings disabled (EMBEDDING_ENABLED=false)"
                log.info("embedding pass skipped: EMBEDDING_ENABLED=false")
            else:
                chunks_indexed, embed_warning = _embed_chunks(
                    db,
                    repo_id=job.repo_id,
                    chunks=chunks,
                    file_ids_by_path=file_ids_by_path,
                )

            job.chunks_indexed = chunks_indexed
            job.status = JOB_COMPLETED
            job.finished_at = datetime.now(timezone.utc)
            if embed_warning:
                # Visible via GET /jobs/{id} without failing the run: the
                # structure is indexed, only the vectors are missing.
                job.error = embed_warning
            db.commit()
            return {
                "ok": True,
                "files_scanned": files_scanned,
                "files_indexed": files_indexed,
                "symbols_indexed": symbols_indexed,
                "chunks_indexed": chunks_indexed,
                "languages": languages,
                "warning": embed_warning,
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
