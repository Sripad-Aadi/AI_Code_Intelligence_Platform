"""Structural analysis read API — repo explorer data (Step 5).

These endpoints surface the files / symbols / import edges that the ingest
task wrote, so the Step-6 frontend can render a repo explorer and the Step-7
chunking layer can pull symbol spans.
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.ingestion import _get_owned_repo
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.edge import CodeEdge
from app.models.file import SourceFile
from app.models.repository import ProjectRepository
from app.models.symbol import Symbol
from app.schemas.analysis import (
    ImportEdgeRead,
    SourceFileRead,
    SourceFileWithSymbols,
    SymbolRead,
)

router = APIRouter(tags=["analysis"])


def _get_owned_file(
    file_id: UUID, current_user: CurrentUser, db: Session
) -> SourceFile:
    file_row = db.get(SourceFile, file_id)
    if file_row is None:
        raise HTTPException(status_code=404, detail="File not found")
    repo = db.get(ProjectRepository, file_row.repo_id)
    from app.models.project import Project

    project = db.get(Project, repo.project_id) if repo else None
    if repo is None or project is None or project.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to access this file"
        )
    return file_row


@router.get("/repos/{repo_id}/files", response_model=List[SourceFileRead])
def list_repo_files(
    repo_id: UUID,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    path: Optional[str] = Query(default=None, description="Prefix filter"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[SourceFile]:
    """List indexed files for a repo (path prefix filter + paging)."""
    _get_owned_repo(repo_id, current_user, db)
    query = db.query(SourceFile).filter(SourceFile.repo_id == repo_id)
    if path:
        query = query.filter(SourceFile.path.like(f"{path}%"))
    return query.order_by(SourceFile.path.asc()).offset(offset).limit(limit).all()


@router.get("/files/{file_id}", response_model=SourceFileWithSymbols)
def get_file_with_symbols(
    file_id: UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """One file plus its extracted symbols (functions/classes/...)."""
    file_row = _get_owned_file(file_id, current_user, db)
    symbols = (
        db.query(Symbol)
        .filter(Symbol.file_id == file_id)
        .order_by(Symbol.start_line.asc())
        .all()
    )
    return {
        **SourceFileRead.model_validate(file_row).model_dump(),
        "symbols": [
            SymbolRead(
                id=s.id,
                file_id=s.file_id,
                kind=s.kind,
                name=s.name,
                start_line=s.start_line,
                end_line=s.end_line,
            )
            for s in symbols
        ],
    }


@router.get("/repos/{repo_id}/symbols", response_model=List[SymbolRead])
def list_repo_symbols(
    repo_id: UUID,
    kind: Optional[str] = Query(
        default=None, description="function|class|method|route"
    ),
    name: Optional[str] = Query(default=None, description="Name substring"),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[dict]:
    """Repo-wide symbols, optionally filtered by kind / name."""
    _get_owned_repo(repo_id, current_user, db)
    query = db.query(Symbol, SourceFile.path).join(
        SourceFile, SourceFile.id == Symbol.file_id
    )
    query = query.filter(Symbol.repo_id == repo_id)
    if kind:
        query = query.filter(Symbol.kind == kind)
    if name:
        query = query.filter(Symbol.name.ilike(f"%{name}%"))
    rows = query.order_by(Symbol.start_line.asc()).offset(offset).limit(limit).all()
    return [
        {
            "id": s.id,
            "file_id": s.file_id,
            "kind": s.kind,
            "name": s.name,
            "start_line": s.start_line,
            "end_line": s.end_line,
            "file_path": path,
        }
        for s, path in rows
    ]


@router.get("/repos/{repo_id}/edges", response_model=List[ImportEdgeRead])
def list_repo_edges(
    repo_id: UUID,
    edge_type: str = Query(default="imports", description="imports|belongs_to"),
    limit: int = Query(default=200, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[dict]:
    """Import (file→file) or belongs_to (symbol→file) edges for a repo."""
    _get_owned_repo(repo_id, current_user, db)
    target = SourceFile.__table__.alias("target")
    base = db.query(CodeEdge.edge_type, target.c.path).join(
        target, target.c.id == CodeEdge.target_id
    )
    if edge_type == "belongs_to":
        # Source is a symbol; resolve its path through the symbols->files join.
        source_files = SourceFile.__table__.alias("source_files")
        base = (
            base.add_columns(source_files.c.path)
            .join(Symbol, Symbol.id == CodeEdge.source_id)
            .join(source_files, source_files.c.id == Symbol.file_id)
        )
    else:
        source = SourceFile.__table__.alias("source")
        base = base.add_columns(source.c.path).join(
            source, source.c.id == CodeEdge.source_id
        )

    rows = (
        base.filter(
            CodeEdge.repo_id == repo_id,
            CodeEdge.edge_type == edge_type,
        )
        .limit(limit)
        .all()
    )
    return [{"source_path": s, "target_path": t, "edge_type": et} for et, t, s in rows]
