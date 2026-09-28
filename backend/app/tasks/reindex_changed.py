"""Step 16 — Incremental re-indexing task.

Re-parses and re-embeds only the files changed in a push event.
Deletes stale vectors by file_path before inserting new ones.
Updates dependency relationships for changed files.
"""

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Dict, List, Tuple

from app.analysis.parsers import parse_source
from app.analysis.resolve import resolve_import
from app.config import settings
from app.db.session import db_session
from app.embeddings.chunker import Chunk, chunk_file, contextualize
from app.embeddings.jina import embed_passages
from app.ingestion.language_detect import detect_language
from app.models.code_embedding import CodeEmbedding
from app.models.edge import CodeEdge
from app.models.file import SourceFile
from app.models.import_stmt import ImportStatement
from app.models.job import JOB_COMPLETED, JOB_FAILED, JOB_RUNNING, AnalysisJob
from app.models.repository import ProjectRepository
from app.models.symbol import Symbol
from app.worker import celery_app

log = logging.getLogger(__name__)

EMBED_BATCH_ROWS = 200


def _clone_dir(repo: ProjectRepository) -> Path:
    """Mirror of the attach path layout: CLONE_ROOT_DIR/<project>/<owner>__<name>."""
    return (
        Path(settings.CLONE_ROOT_DIR)
        / str(repo.project_id)
        / f"{repo.github_owner}__{repo.github_name}"
    )


def _delete_stale_analysis(db, repo_id: uuid.UUID, file_paths: List[str]) -> int:
    """
    Delete all analysis data for the given file paths.
    Returns count of deleted embedding rows.
    """
    # Get file IDs for these paths
    file_rows = (
        db.query(SourceFile)
        .filter(
            SourceFile.repo_id == repo_id,
            SourceFile.path.in_(file_paths),
        )
        .all()
    )

    file_ids = [f.id for f in file_rows]
    if not file_ids:
        return 0

    # Delete embeddings
    emb_deleted = (
        db.query(CodeEmbedding)
        .filter(CodeEmbedding.file_id.in_(file_ids))
        .delete(synchronize_session=False)
    )

    # Delete symbols
    db.query(Symbol).filter(Symbol.file_id.in_(file_ids)).delete(
        synchronize_session=False
    )

    # Delete imports
    db.query(ImportStatement).filter(ImportStatement.file_id.in_(file_ids)).delete(
        synchronize_session=False
    )

    # Delete edges (both file->file imports and symbol->file belongs_to)
    db.query(CodeEdge).filter(
        (CodeEdge.source_kind == "file") & (CodeEdge.source_id.in_(file_ids))
    ).delete(synchronize_session=False)
    db.query(CodeEdge).filter(
        (CodeEdge.source_kind == "symbol") & (CodeEdge.target_id.in_(file_ids))
    ).delete(synchronize_session=False)

    # Delete source files
    db.query(SourceFile).filter(SourceFile.id.in_(file_ids)).delete(
        synchronize_session=False
    )

    log.info(
        "Deleted stale analysis for %d files (%d embeddings)",
        len(file_ids),
        emb_deleted,
    )
    return emb_deleted


def _process_changed_files(
    db,
    repo_id: uuid.UUID,
    clone_dir: Path,
    changed_files: List[str],
    job_id: str,
) -> Tuple[int, int, int, int, Dict[str, int]]:
    """
    Process changed files: parse, chunk, embed, persist.

    Returns: (files_indexed, symbols_indexed, chunks_indexed,
    embeddings_count, languages_histogram).
    """
    languages: Dict[str, int] = {}
    files_indexed = 0
    symbols_indexed = 0
    chunks_indexed = 0
    all_chunks: List[Chunk] = []
    file_ids_by_path: Dict[str, uuid.UUID] = {}
    pending_import_edges: List[Tuple[str, uuid.UUID]] = []

    file_rows: List[SourceFile] = []
    symbol_rows: List[Symbol] = []
    import_rows: List[ImportStatement] = []
    edge_rows: List[CodeEdge] = []

    for rel_path in changed_files:
        file_path = clone_dir / rel_path
        if not file_path.is_file():
            log.debug("Changed file not found on disk (may be deleted): %s", rel_path)
            continue

        files_indexed += 1
        rel = PurePosixPath(rel_path)
        lang = detect_language(rel)
        languages[lang] = languages.get(lang, 0) + 1

        try:
            source = file_path.read_bytes()
        except OSError:
            continue
        line_count = len(source.splitlines())

        parsed = parse_source(rel, source)
        file_row = SourceFile(
            id=uuid.uuid4(),
            repo_id=repo_id,
            path=rel.as_posix(),
            language=lang,
            line_count=line_count,
            parse_error=parsed.error,
        )
        file_rows.append(file_row)
        file_ids_by_path[rel.as_posix()] = file_row.id

        # Chunk from symbols
        all_chunks.extend(
            chunk_file(
                file_path=rel.as_posix(),
                language=lang,
                text=source.decode("utf-8", errors="replace"),
                symbols=parsed.symbols,
            )
        )

        for sym in parsed.symbols:
            sym_row = Symbol(
                id=uuid.uuid4(),
                repo_id=repo_id,
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
                    repo_id=repo_id,
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
                    file_rel=rel,
                    module=imp.module,
                )
            import_rows.append(
                ImportStatement(
                    id=uuid.uuid4(),
                    repo_id=repo_id,
                    file_id=file_row.id,
                    module=imp.module,
                    is_relative=imp.is_relative,
                    resolved_path=resolved,
                )
            )
            if resolved:
                pending_import_edges.append((resolved, file_row.id))

    # Persist in dependency order with explicit flushes
    db.add_all(file_rows)
    db.flush()
    db.add_all(symbol_rows + import_rows)
    db.flush()
    db.add_all(edge_rows)

    # Second pass: link imports to files that were actually indexed
    for resolved_path, source_file_id in pending_import_edges:
        target_id = file_ids_by_path.get(resolved_path)
        if target_id is not None:
            edge_rows.append(
                CodeEdge(
                    id=uuid.uuid4(),
                    repo_id=repo_id,
                    source_kind="file",
                    source_id=source_file_id,
                    edge_type="imports",
                    target_id=target_id,
                )
            )
    if edge_rows:
        db.add_all(edge_rows)
        db.flush()

    # Embed chunks
    if all_chunks and settings.EMBEDDING_ENABLED:
        for start in range(0, len(all_chunks), EMBED_BATCH_ROWS):
            batch = all_chunks[start : start + EMBED_BATCH_ROWS]
            vectors = embed_passages([contextualize(c) for c in batch])

            if len(vectors) != len(batch):
                raise RuntimeError(
                    f"model returned {len(vectors)} vectors for {len(batch)} chunks"
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
            chunks_indexed += len(rows)

    return files_indexed, symbols_indexed, chunks_indexed, len(all_chunks), languages


@celery_app.task(
    bind=True, name="ingestion.reindex_changed", max_retries=3, default_retry_delay=60
)
def reindex_changed_files_task(
    self,
    repo_id: str,
    branch: str,
    head_sha: str,
    base_sha: str,
    changed_files: List[str],
    github_delivery_id: str,
) -> dict:
    """
    Incremental re-indexing for changed files from a push event.

    Args:
        repo_id: ProjectRepository UUID
        branch: Branch name that was pushed
        head_sha: New commit SHA
        base_sha: Previous commit SHA (before push)
        changed_files: List of file paths that changed (added/modified/removed)
        github_delivery_id: GitHub webhook delivery ID
    """
    repo_uuid = uuid.UUID(repo_id)

    with db_session() as db:
        repo = db.get(ProjectRepository, repo_uuid)
        if not repo:
            return {"ok": False, "error": f"Repository {repo_id} not found"}

        clone_dir = _clone_dir(repo)
        if not clone_dir.is_dir():
            return {"ok": False, "error": f"Clone not found at {clone_dir}"}

        # Create a job record for tracking
        job = AnalysisJob(
            id=uuid.uuid4(),
            repo_id=repo_uuid,
            status=JOB_RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.commit()

        try:
            # Separate deleted files from added/modified
            existing_files = []
            deleted_files = []
            for f in changed_files:
                file_path = clone_dir / f
                if file_path.is_file():
                    existing_files.append(f)
                else:
                    deleted_files.append(f)

            log.info(
                "Incremental reindex for %s: %d changed (%d existing, %d deleted)",
                repo.github_full_name,
                len(changed_files),
                len(existing_files),
                len(deleted_files),
            )

            # Delete stale analysis for ALL changed files (deleted + modified)
            _delete_stale_analysis(db, repo_uuid, changed_files)

            # Process existing (added/modified) files
            files_idx = 0
            symbols_idx = 0
            chunks_idx = 0
            languages = {}

            if existing_files:
                files_idx, symbols_idx, chunks_idx, _, languages = (
                    _process_changed_files(
                        db, repo_uuid, clone_dir, existing_files, str(job.id)
                    )
                )

            # Update job
            job.files_scanned = len(changed_files)
            job.files_indexed = files_idx
            job.symbols_indexed = symbols_idx
            job.chunks_indexed = chunks_idx
            job.languages = languages or None
            job.status = JOB_COMPLETED
            job.finished_at = datetime.now(timezone.utc)

            # Update repo's last_indexed_at
            repo.last_indexed_at = datetime.now(timezone.utc)

            db.commit()

            log.info(
                "Incremental reindex completed for %s: %d files, %d symbols, %d chunks",
                repo.github_full_name,
                files_idx,
                symbols_idx,
                chunks_idx,
            )

            return {
                "ok": True,
                "repo_id": repo_id,
                "branch": branch,
                "head_sha": head_sha,
                "files_changed": len(changed_files),
                "files_processed": files_idx,
                "symbols_indexed": symbols_idx,
                "chunks_indexed": chunks_idx,
                "languages": languages,
                "github_delivery_id": github_delivery_id,
            }

        except Exception as exc:  # noqa: BLE001
            db.rollback()
            job.status = JOB_FAILED
            job.error = str(exc)[:2000]
            job.finished_at = datetime.now(timezone.utc)
            try:
                db.commit()
            except Exception:
                db.rollback()

            if self.request.retries < self.max_retries:
                log.warning(
                    "Retrying incremental reindex (attempt %d/%d)",
                    self.request.retries + 1,
                    self.max_retries,
                )
                raise self.retry(exc=exc)

            log.exception("Incremental reindex failed for %s", repo.github_full_name)
            return {"ok": False, "error": str(exc)}
