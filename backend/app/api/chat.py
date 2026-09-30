"""Repository-aware AI chat endpoint (Step 9).

``POST /chat`` — the one expensive, stateful endpoint in the API, so it gets
all three protections the plan asks for: ownership (``_get_owned_repo``),
rate limiting (20/min per user via ``chat_rate_limit``) and a bounded model
call inside the agent.

Failures are deliberately distinguishable: 503 when chat cannot work at all
(no API key, embeddings off), 409 when the repository simply has not been
indexed yet (an actionable problem — press Analyze), and 502 when the
provider or retrieval misbehaves. Collapsing those into one "chat failed"
would leave the user guessing which of three very different things to fix.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.agents.chat_chain import ChatError, run_chat
from app.config import settings
from app.core.rate_limit import chat_rate_limit
from app.core.security import CurrentUser, get_owned_repo
from app.db.session import get_db
from app.models.code_embedding import CodeEmbedding
from app.schemas.chat import ChatRequest, ChatResponse

log = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


def _require_ready(db: Session, repo_id) -> None:
    """Translate 'chat cannot work here' into the right HTTP status."""
    if settings.LLM_PROVIDER.lower() != "groq":
        raise HTTPException(
            status_code=503,
            detail=(
                f"Chat is unavailable: LLM_PROVIDER={settings.LLM_PROVIDER!r} "
                "is not implemented (only 'groq')."
            ),
        )
    if not settings.GROQ_API_KEY:
        raise HTTPException(
            status_code=503,
            detail=("Chat is unavailable: GROQ_API_KEY is not set in backend/.env."),
        )
    if not settings.EMBEDDING_ENABLED:
        raise HTTPException(
            status_code=503,
            detail=(
                "Chat is unavailable: EMBEDDING_ENABLED=false, so there are "
                "no chunks to retrieve."
            ),
        )

    indexed = (
        db.query(func.count(CodeEmbedding.id))
        .filter(CodeEmbedding.repo_id == repo_id)
        .scalar()
        or 0
    )
    if indexed == 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "This repository has no indexed chunks yet — run Analyze on "
                "the project first."
            ),
        )


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(chat_rate_limit),
) -> ChatResponse:
    """Answer a question about one repository the caller owns.

    The reply cites `path:start-end` for its claims and carries the chunks it
    was grounded on, so the frontend can render sources next to the answer.
    """
    repo = get_owned_repo(payload.repo_id, current_user, db)
    _require_ready(db, repo.id)

    try:
        answer, evidence = run_chat(
            db,
            repo_id=repo.id,
            query=payload.query,
            history=payload.chat_history,
            user_id=str(current_user.id),
        )
    except ChatError as exc:
        log.warning("chat rejected (repo=%s): %s", repo.id, exc)
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("chat failed (repo=%s)", repo.id)
        raise HTTPException(status_code=502, detail=f"Chat failed: {exc}") from exc

    return ChatResponse(answer=answer, evidence=evidence)
