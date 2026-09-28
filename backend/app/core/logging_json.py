"""Structured JSON logging with correlation IDs (Step 19).

Provides a JSON formatter that adds:
- timestamp (ISO8601)
- level
- logger name
- message
- correlation_id (from request headers or generated)
- user_id (when available)
- extra fields from log record
"""

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Optional

# Context variables for correlation ID and user ID
correlation_id_var: ContextVar[Optional[str]] = ContextVar(
    "correlation_id", default=None
)
user_id_var: ContextVar[Optional[str]] = ContextVar("user_id", default=None)


class JSONFormatter(logging.Formatter):
    """JSON log formatter with correlation ID and user ID support."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add correlation ID if available
        corr_id = correlation_id_var.get()
        if corr_id:
            log_obj["correlation_id"] = corr_id

        # Add user ID if available
        u_id = user_id_var.get()
        if u_id:
            log_obj["user_id"] = u_id

        # Add extra fields from record
        for key, value in record.__dict__.items():
            if key not in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "exc_info",
                "exc_text",
                "stack_info",
                "getMessage",
            }:
                log_obj[key] = value

        # Add exception info if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, default=str)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with JSON formatting configured."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def set_correlation_id(corr_id: Optional[str] = None) -> str:
    """Set correlation ID for current context. Returns the ID used."""
    if corr_id is None:
        corr_id = str(uuid.uuid4())[:8]
    correlation_id_var.set(corr_id)
    return corr_id


def clear_correlation_id() -> None:
    """Clear correlation ID from current context."""
    correlation_id_var.set(None)


def set_user_id(user_id: Optional[str]) -> None:
    """Set user ID for current context."""
    if user_id:
        user_id_var.set(str(user_id))


def clear_user_id() -> None:
    """Clear user ID from current context."""
    user_id_var.set(None)


class LogContext:
    """Context manager for setting correlation ID and user ID."""

    def __init__(
        self, correlation_id: Optional[str] = None, user_id: Optional[str] = None
    ):
        self.correlation_id = correlation_id
        self.user_id = user_id
        self._prev_corr_id: Optional[str] = None
        self._prev_user_id: Optional[str] = None

    def __enter__(self):
        self._prev_corr_id = correlation_id_var.get()
        self._prev_user_id = user_id_var.get()
        if self.correlation_id:
            correlation_id_var.set(self.correlation_id)
        if self.user_id:
            user_id_var.set(str(self.user_id))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._prev_corr_id:
            correlation_id_var.set(self._prev_corr_id)
        else:
            correlation_id_var.set(None)
        if self._prev_user_id:
            user_id_var.set(self._prev_user_id)
        else:
            user_id_var.set(None)


def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    **extra: Any,
) -> None:
    """Log a message with extra fields attached to the record."""
    logger.log(level, message, extra=extra)
