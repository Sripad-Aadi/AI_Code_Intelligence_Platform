"""Chat request/response schemas (Step 9).

The field names mirror ``frontend/src/api/types.ts`` exactly — the Chat page
already existed and speaks this contract, so the backend conforms to it
rather than the other way round.
"""

from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """One turn of history, as the page keeps it in state."""

    role: Literal["user", "assistant"]
    content: str = Field(default="", max_length=8000)


class ChatRequest(BaseModel):
    repo_id: UUID
    query: str = Field(..., min_length=1, max_length=2000)
    chat_history: List[ChatMessage] = Field(default_factory=list)


class EvidenceChunk(BaseModel):
    """A retrieved chunk the answer may cite.

    Exactly the metadata the page renders under the answer (path, symbol,
    inclusive 1-based line range, verbatim content), so a reader can jump to
    the code that justifies the reply.
    """

    file_path: str
    symbol_name: Optional[str] = None
    symbol_kind: Optional[str] = None
    start_line: int
    end_line: int
    content: str


class ChatResponse(BaseModel):
    answer: str
    evidence: List[EvidenceChunk] = Field(default_factory=list)
