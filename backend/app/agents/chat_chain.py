"""Repository-aware AI chat (Step 9).

A LangChain tool-calling agent backed by Groq (``openai/gpt-oss-20b`` by
default — it is on Groq's free tier, cheap in tokens and fast enough that a
chat turn feels instant; ``openai/gpt-oss-120b`` is the one-line swap for
more reasoning — and changing models or providers is a config edit through
``LLM_MODEL``/``LLM_PROVIDER``, as the plan asks). It is deliberately *not*
a chain over the whole repository: the model answers from whatever the four
Step-9 tools return, one hop at a time, which keeps a question about a
100k-line repo inside a sane context.

The plan is explicit that the grounding instruction and evidence surfacing
are the actual product differentiator, so this module does two things the
naive version would skip:

* :data:`SYSTEM_PROMPT` forbids answering from anything but tool output,
  demands a ``path:start-end`` citation for every claim, and requires an
  honest "no evidence for that" instead of a plausible guess.
* Every chunk the retrieval tool returned is returned to the *client* as
  well as the answer, so the UI can render the source next to the reply and
  a reader can verify the citation themselves.

Token usage from every LLM call in the run is summed and handed to the Step
19 cost tracker, so ``GET /observability/costs/summary`` reflects real spend
instead of staying at zero forever.
"""

import logging
import re
import time
from typing import Any, List, Sequence, Tuple
from uuid import UUID

import groq
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_groq import ChatGroq
from sqlalchemy.orm import Session

from app.agents.tools import _to_evidence, build_tools
from app.config import settings
from app.core.cost_tracking import LLMUsage, calculate_cost, get_cost_tracker
from app.retrieval.search import search_code
from app.schemas.chat import ChatMessage, EvidenceChunk

log = logging.getLogger(__name__)

DEFAULT_MODEL = "openai/gpt-oss-20b"

# Bound the spend: the agent gets a handful of turns, and only the last few
# turns of history are replayed so a long conversation cannot grow forever.
# 6 iterations cover the longest useful chain the tools support
# (search → file → symbol → deps → answer) plus one misstep. Anything beyond
# that is the model looping, and the deterministic evidence fallback below
# answers from what retrieval already found instead of burning more calls.
MAX_ITERATIONS = 6
MAX_EXECUTION_SECONDS = 60
MAX_HISTORY_TURNS = 6
LLM_TIMEOUT_SECONDS = 30

SYSTEM_PROMPT = """\
You are a code assistant with read-only access to exactly one repository.

You have four tools: search_code (semantic search over indexed code),
get_file (read a file by repo-relative path), get_symbol (find a function,
class, method or route) and get_dependencies (a file's imports, one hop).
Use them before you answer. You have no other knowledge of this repository.

Rules — they are not negotiable:
1. Answer ONLY from tool results. Never answer from general programming
   knowledge, and never describe code you have not read in this session.
2. Cite every factual claim as `path:start-end`, for example
   `backend/app/core/security.py:115-141`. If you cannot cite it, do not
   say it.
3. Stop rule: after any tool result that contains the answer, your NEXT
   action must be the final answer — no more tool calls. Re-searching
   paraphrases when the results in hand already answer the question burns
   your step budget and you will be stopped before answering.
4. If the tools turn up nothing useful, say plainly that the repository
   contains no evidence for the question. A short honest "I could not find
   that here" is the correct answer — a plausible guess is a failure.
5. Quote code sparingly and only where the quote is the answer.
6. For "how does X work" questions, walk the real call path you found, in
   order, naming each file and its line range.
7. Stay inside this repository. If asked about something else, say you only
   have access to this codebase.
"""


class ChatError(RuntimeError):
    """A chat failure the API layer should turn into an HTTP status."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def _model_name() -> str:
    return (settings.LLM_MODEL or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _build_llm() -> ChatGroq:
    """Build the Groq client.

    Timeout and retries are bounded on purpose (plan Step 17: every external
    call needs one) — a hung provider must fail the request, not the worker.
    """
    return ChatGroq(
        model=_model_name(),
        groq_api_key=settings.GROQ_API_KEY,
        temperature=0,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=1,
        # The endpoint returns the finished answer, never a token stream, so
        # streaming buys nothing here — and it cost us real data: Groq puts
        # usage on the final chunk only, which the agent does not carry into
        # the messages it returns, so Step 19's tracker read 0 calls/0 tokens
        # after two perfectly good chat turns. `invoke` carries usage on the
        # message itself.
        disable_streaming=True,
    )


def _history_messages(
    history: Sequence[ChatMessage],
) -> List[Any]:
    """Turn client history into LangChain messages, most recent last."""
    messages: List[Any] = []
    for msg in list(history)[-MAX_HISTORY_TURNS * 2 :]:
        text = (msg.content or "").strip()
        if not text:
            continue
        if msg.role == "user":
            messages.append(HumanMessage(content=text))
        else:
            messages.append(AIMessage(content=text))
    return messages


def _record_usage(result: dict, repo_id: UUID) -> None:
    """Sum token usage across every model call in the run (Step 19)."""
    input_tokens = 0
    output_tokens = 0
    for message in result.get("messages", []):
        meta = getattr(message, "usage_metadata", None)
        if not meta:
            # Belt and braces: some paths report usage only under
            # response_metadata.token_usage (Groq's streaming form), so take
            # whichever signal is present rather than silently recording 0.
            raw = (getattr(message, "response_metadata", None) or {}).get("token_usage")
            if raw:
                meta = {
                    "input_tokens": raw.get("prompt_tokens"),
                    "output_tokens": raw.get("completion_tokens"),
                }
        if not meta:
            continue
        input_tokens += int(meta.get("input_tokens") or 0)
        output_tokens += int(meta.get("output_tokens") or 0)

    if not (input_tokens or output_tokens):
        return

    model = _model_name()
    try:
        get_cost_tracker().record(
            LLMUsage(
                model=model,
                provider=settings.LLM_PROVIDER,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=0,
                estimated_cost_usd=calculate_cost(model, input_tokens, output_tokens),
                repo_id=repo_id,
            )
        )
    except Exception:  # never fail an answer over bookkeeping
        log.exception("could not record LLM usage")


def _translate_provider_error(exc: groq.APIStatusError) -> ChatError:
    """Turn a Groq API failure into an actionable HTTP status.

    Measured the hard way: pointing the default at a model this key does not
    serve makes Groq answer 404 ``model_not_found``, and the naive version
    turned that into an opaque 502. A wrong model id or a bad key are
    *configuration* faults — the caller needs 503 plus the name of the knob
    to turn, not "chat failed".
    """
    status = getattr(exc, "status_code", None)
    # Groq's message is an `Error code: N - {'error': {...}}` string with no
    # secret in it. Keep a bounded copy: the first 400 was completely opaque
    # because this function used to discard the body.
    body = " ".join(str(exc).split())[:400]
    if status == 404:
        return ChatError(
            f"Model {_model_name()!r} is not available to this Groq key. "
            "Set LLM_MODEL to one of the ids the key can serve.",
            status_code=503,
        )
    if status == 401:
        return ChatError(
            "Groq rejected GROQ_API_KEY (401) — check it in backend/.env.",
            status_code=503,
        )
    if status == 429:
        return ChatError(
            "Groq rate-limited this key (429); try again in a moment.",
            status_code=429,
        )
    return ChatError(
        f"Groq call failed ({status or type(exc).__name__}): {body}",
        status_code=502,
    )


def _sanitize_answer(answer: str) -> str:
    """Remove model control-token leakage from the final answer.

    gpt-oss sometimes half-decides to call a tool *while writing the final
    answer* and emits the Harmony prologue as text instead of a tool call::

        ... the `src` directory)?assistant to=get_file<|channel|>commentary
        <|constrain|>json<|message|>{"path":"src","query":""}

    Everything from ``assistant to=`` on is framework exhaust, never prose —
    cut the answer there — and drop any stray ``<|...|>`` control tokens
    wherever they appear (they can never be legitimate answer text).
    """
    cut = answer.find("assistant to=")
    if cut != -1:
        answer = answer[:cut]
    answer = re.sub(r"<\|[a-z_]+\|>", "", answer)
    return answer.strip()


FALLBACK_PROMPT = """\
You answer questions about one repository from the evidence quoted below —
retrieved code chunks, nothing else.

Rules:
1. Answer ONLY from the evidence. Never use general programming knowledge.
2. Cite every factual claim as `path:start-end`, using the headers given
   with each chunk. If you cannot cite it, do not say it.
3. If the evidence does not contain the answer, say plainly that the
   repository excerpt has no evidence for the question. A short honest
   "I could not find that here" is correct; a plausible guess is a failure.
4. Keep code quotes short.
"""


def _answer_from_evidence(
    llm: ChatGroq, query: str, evidence: List[EvidenceChunk], repo_id: UUID
) -> str:
    """Answer directly from retrieved chunks, with no tools.

    Deterministic safety net for the two ways the tool loop dies on the
    small Groq models: malformed tool-call JSON (400 `tool_use_failed`, same
    input usually fails twice) and re-search looping to force-stop. The
    retrieval that feeds it is plain Python, so this path cannot 400 or
    loop — and the grounding contract is identical (cite or admit).
    """
    context = "\n\n---\n\n".join(
        f"{chunk.file_path}:{chunk.start_line}-{chunk.end_line}\n"
        f"{_clip_text(chunk.content)}"
        for chunk in evidence
    )
    message = llm.invoke(
        [
            SystemMessage(content=FALLBACK_PROMPT),
            HumanMessage(
                content=f"Evidence:\n{context}\n\nQuestion: {query}\n\n"
                "Answer with citations, or say there is no evidence."
            ),
        ]
    )
    content = message.content if isinstance(message.content, str) else ""
    meta = getattr(message, "usage_metadata", None) or {}
    try:
        get_cost_tracker().record(
            LLMUsage(
                model=_model_name(),
                provider=settings.LLM_PROVIDER,
                input_tokens=int(meta.get("input_tokens") or 0),
                output_tokens=int(meta.get("output_tokens") or 0),
                latency_ms=0,
                estimated_cost_usd=calculate_cost(
                    _model_name(),
                    int(meta.get("input_tokens") or 0),
                    int(meta.get("output_tokens") or 0),
                ),
                repo_id=repo_id,
            )
        )
    except Exception:  # never fail an answer over bookkeeping
        log.exception("could not record LLM usage")
    return _sanitize_answer(content.strip())


def _clip_text(text: str, limit: int = 1500) -> str:
    return text if len(text) <= limit else text[:limit] + "\n… [truncated]"


def _is_force_stop(output: str) -> bool:
    """Detect LangChain's early-stopping message.

    With ``early_stopping_method="force"`` an exhausted agent does not raise —
    it returns ``"Agent stopped due to ..."`` as the answer. That framework
    text must never reach the user as if it were a reply.
    """
    return output.startswith("Agent stopped due to")


def run_chat(
    db: Session,
    repo_id: UUID,
    query: str,
    history: Sequence[ChatMessage] = (),
) -> Tuple[str, List[EvidenceChunk]]:
    """Run one grounded turn and return ``(answer, evidence)``.

    Raises :class:`ChatError` with an HTTP status for expected failures
    (missing key, provider refusal) and lets unexpected ones propagate to the
    router, which logs them and answers 502.
    """
    if settings.LLM_PROVIDER.lower() != "groq":
        raise ChatError(
            f"LLM_PROVIDER={settings.LLM_PROVIDER!r} is not implemented; "
            "only 'groq' is available.",
            status_code=503,
        )
    if not settings.GROQ_API_KEY:
        raise ChatError(
            "GROQ_API_KEY is not configured, so chat cannot reach the model.",
            status_code=503,
        )

    tools, evidence = build_tools(db, repo_id)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )
    llm = _build_llm()
    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        max_iterations=MAX_ITERATIONS,
        max_execution_time=MAX_EXECUTION_SECONDS,
        early_stopping_method="force",
        handle_parsing_errors=True,
    )

    payload = {"input": query, "chat_history": _history_messages(history)}

    started = time.perf_counter()
    result = None
    try:
        result = executor.invoke(payload)
    except groq.APIStatusError as exc:
        # gpt-oss-20b occasionally emits malformed tool-call JSON
        # (`{"query":"tsx",""}` — truncated arguments), which Groq rejects
        # with 400 `tool_use_failed`. The generation is stochastic, so one
        # retry sometimes lands a well-formed call; anything else is
        # translated for the caller, and a second 400 falls through to the
        # evidence fallback below instead of failing the turn.
        if getattr(exc, "status_code", None) == 400:
            log.warning("chat tool call rejected, retrying once (repo=%s)", repo_id)
            try:
                result = executor.invoke(payload)
            except groq.APIStatusError as retry_exc:
                if getattr(retry_exc, "status_code", None) != 400:
                    raise _translate_provider_error(retry_exc) from retry_exc
                log.warning("chat retry rejected too; using evidence fallback")
        else:
            raise _translate_provider_error(exc) from exc
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    answer = ""
    if result is not None:
        output = result.get("output", "")
        answer = output.strip() if isinstance(output, str) else str(output).strip()
        answer = _sanitize_answer(answer)

    if result is None or not answer or _is_force_stop(answer):
        # The tool loop died (double-400 or re-search looping). Answer
        # deterministically instead: retrieve directly and complete once.
        if not evidence:
            for hit in search_code(db, query=query, repo_id=repo_id, k=6):
                if len(evidence) >= 8:
                    break
                evidence.append(_to_evidence(hit))
        if not evidence:
            raise ChatError(
                "The model could not use its tools and nothing relevant "
                "was retrieved — try rephrasing the question.",
            )
        log.info(
            "chat fallback: repo=%s evidence=%d (agent failed)",
            repo_id,
            len(evidence),
        )
        answer = _answer_from_evidence(llm, query, evidence, repo_id)
        if not answer:
            raise ChatError("The model returned an empty answer.")
        return answer, evidence

    _record_usage(result, repo_id)

    _record_usage(result, repo_id)
    log.info(
        "chat turn: repo=%s tools=%d evidence=%d ms=%d chars=%d",
        repo_id,
        len(tools),
        len(evidence),
        elapsed_ms,
        len(answer),
    )
    return answer, evidence
