"""Pydantic schemas for Step-5 structural analysis read endpoints."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SourceFileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    repo_id: UUID
    path: str
    language: str
    line_count: int
    parse_error: Optional[str] = None
    created_at: datetime


class SymbolRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    file_id: UUID
    kind: str  # function | class | method | route
    name: str
    start_line: int
    end_line: int
    file_path: Optional[str] = None  # populated by the API via join


class SourceFileWithSymbols(SourceFileRead):
    symbols: list[SymbolRead] = []


class ImportEdgeRead(BaseModel):
    source_path: str
    target_path: str
    edge_type: str
