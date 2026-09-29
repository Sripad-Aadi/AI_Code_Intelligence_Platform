"""Step 9 chat tests: the API contract, the grounding rules, and the guard.

None of these hit Groq or the database — they pin the parts that are easy to
regress silently (the request shape the page sends, the prompt rules that
make the answer trustworthy, and the path traversal guard), so the live
end-to-end check only has to prove the provider call works.
"""

from pathlib import Path

from app.agents.chat_chain import (
    DEFAULT_MODEL,
    FALLBACK_PROMPT,
    MAX_HISTORY_TURNS,
    SYSTEM_PROMPT,
    ChatError,
    _history_messages,
    _is_force_stop,
    _model_name,
    _sanitize_answer,
    _translate_provider_error,
)
from app.agents.tools import _clip, safe_clone_path
from app.core.cost_tracking import calculate_cost
from app.schemas.chat import ChatMessage, ChatRequest, ChatResponse, EvidenceChunk

# Exactly what Chat.tsx posts.
FRONTEND_REQUEST = {
    "repo_id": "1b6c8e15-e0ea-47b1-b3a8-c5d21c5e6e9f",
    "query": "How does authentication work?",
    "chat_history": [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ],
}


def test_chat_request_matches_the_contract_the_page_sends():
    request = ChatRequest(**FRONTEND_REQUEST)
    assert str(request.repo_id) == FRONTEND_REQUEST["repo_id"]
    assert request.query.startswith("How does")
    assert [m.role for m in request.chat_history] == ["user", "assistant"]
    # History is optional: the first turn of a conversation has none.
    assert (
        ChatRequest(repo_id=FRONTEND_REQUEST["repo_id"], query="q").chat_history == []
    )


def test_chat_response_carries_answer_and_cited_evidence():
    evidence = EvidenceChunk(
        file_path="backend/app/core/security.py",
        symbol_name="decode_supabase_token",
        symbol_kind="function",
        start_line=115,
        end_line=141,
        content="def decode_supabase_token(...): ...",
    )
    response = ChatResponse(
        answer="It verifies a JWT. [security.py:115-141]", evidence=[evidence]
    )
    assert response.answer
    assert response.evidence[0].file_path.endswith("security.py")
    assert (response.evidence[0].start_line, response.evidence[0].end_line) == (
        115,
        141,
    )
    # Evidence is optional: an honest "no evidence" answer still returns.
    assert ChatResponse(answer="not found here").evidence == []


def test_system_prompt_forces_grounding_and_citations():
    """The differentiator per the plan: answer from tools, cite or stay silent."""
    assert "Answer ONLY from tool results" in SYSTEM_PROMPT
    assert "`path:start-end`" in SYSTEM_PROMPT
    # The loop guard: without an explicit stop rule the model burns all
    # MAX_ITERATIONS re-searching paraphrases and never answers.
    assert "Stop rule" in SYSTEM_PROMPT and "NEXT" in SYSTEM_PROMPT
    # It must actively prefer admitting ignorance over inventing an answer.
    assert "plausible guess is a failure" in SYSTEM_PROMPT
    assert "general programming" in SYSTEM_PROMPT
    # And it must scope the model to this repository.
    assert "exactly one repository" in SYSTEM_PROMPT


def test_system_prompt_names_every_tool_the_agent_has():
    for tool in ("search_code", "get_file", "get_symbol", "get_dependencies"):
        assert tool in SYSTEM_PROMPT, f"prompt does not mention {tool}"


def test_default_model_is_a_priced_free_tier_groq_model():
    """The plan's Llama 3.3 70B left Groq's lineup — chat 404'd on it.

    The default must therefore be a model this key actually serves (free
    tier) *and* one the cost tracker has a price for, or observability would
    silently report $0 spend forever.
    """
    assert DEFAULT_MODEL == "openai/gpt-oss-20b"
    assert _model_name().strip()  # whatever LLM_MODEL the env sets, no blanks
    assert calculate_cost(DEFAULT_MODEL, 1_000_000, 1_000_000) == 0.375


def test_chat_error_carries_an_http_status():
    err = ChatError("no key", status_code=503)
    assert err.status_code == 503
    assert "no key" in str(err)
    assert ChatError("boom").status_code == 502  # default


def _groq_error(status: int, message: str):
    """Build a real SDK error without touching the network."""
    import groq
    import httpx

    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status, request=request)
    cls = {
        400: groq.BadRequestError,
        401: groq.AuthenticationError,
        404: groq.NotFoundError,
        429: groq.RateLimitError,
    }[status]
    return cls(f"Error code: {status} - {message}", response=response, body=None)


def test_provider_errors_map_to_actionable_statuses():
    assert (
        _translate_provider_error(_groq_error(404, "model_not_found")).status_code
        == 503
    )
    assert "LLM_MODEL" in str(
        _translate_provider_error(_groq_error(404, "model_not_found"))
    )
    assert _translate_provider_error(_groq_error(401, "invalid key")).status_code == 503
    assert (
        _translate_provider_error(_groq_error(429, "rate limited")).status_code == 429
    )
    # The 400 that hid the first production failure must keep the body now.
    fallback = _translate_provider_error(_groq_error(400, "tool_use_failed"))
    assert fallback.status_code == 502
    assert "tool_use_failed" in str(fallback)


def test_fallback_prompt_keeps_the_grounding_contract():
    """The deterministic fallback must promise the same guarantees."""
    assert "ONLY from the evidence" in FALLBACK_PROMPT
    assert "`path:start-end`" in FALLBACK_PROMPT
    assert "plausible guess is a failure" in FALLBACK_PROMPT


def test_force_stop_message_is_detected_not_answered():
    assert _is_force_stop("Agent stopped due to max iterations.")
    assert _is_force_stop("Agent stopped due to time limit.")
    assert not _is_force_stop("I could not find that here.")
    assert not _is_force_stop("")


def test_sanitizer_cuts_harmony_tool_call_leakage():
    """The exact fragment a live turn returned: half a tool call as text."""
    leaked = (
        "The React pages are in `src/pages`: `src/pages/home.jsx`. "
        "These files were listed by the repository's file listing "
        "(`src` directory)?assistant to=get_file<|channel|>commentary "
        '<|constrain|>json<|message|>{"path":"src","query":""}'
    )
    clean = _sanitize_answer(leaked)
    assert "assistant to=" not in clean
    assert "<|" not in clean
    assert clean.endswith("(`src` directory)?")
    assert "`src/pages/home.jsx`" in clean
    # Clean answers pass through untouched.
    plain = "It verifies a JWT. `security.py:115-141`"
    assert _sanitize_answer(plain) == plain


def test_history_is_converted_to_messages_and_truncated():
    history = [
        ChatMessage(role="user" if i % 2 == 0 else "assistant", content=f"turn {i}")
        for i in range(MAX_HISTORY_TURNS * 4)
    ]
    converted = _history_messages(history)
    assert len(converted) == MAX_HISTORY_TURNS * 2
    assert converted[-1].content == history[-1].content
    # Blank turns are dropped rather than sent to the model as empty turns.
    assert [
        m.content for m in _history_messages([ChatMessage(role="user", content="  ")])
    ] == []


def test_safe_clone_path_keeps_reads_inside_the_clone(tmp_path: Path):
    root = tmp_path / "repo"
    (root / "app").mkdir(parents=True)
    (root / "app" / "main.py").write_text("print('hi')", encoding="utf-8")

    inside = safe_clone_path(root, "app/main.py")
    assert inside is not None and inside.read_text(encoding="utf-8").startswith("print")


def test_safe_clone_path_rejects_every_escape(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    for attempt in (
        "../outside.txt",
        "app/../../outside.txt",
        "/etc/passwd",
        "",
        str(outside),
        "..",
    ):
        assert safe_clone_path(root, attempt) is None, f"escaped: {attempt!r}"


def test_safe_clone_path_refuses_the_root_itself(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    # Reading the directory as a file is never useful and must not resolve.
    assert safe_clone_path(root, ".") is None


def test_clip_reports_how_much_was_dropped():
    long_text = "x" * 20_000
    clipped = _clip(long_text, limit=100)
    assert clipped.startswith("x" * 100)
    assert "19900 more characters" in clipped
    assert _clip("") == ""
    assert _clip(None) == ""
    # Short input is returned verbatim — no gratuitous marker.
    assert _clip("short") == "short"
