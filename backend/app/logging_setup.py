"""Structured JSON logging with a request id on every line.

An audit trail that cannot be correlated with the request that produced it is
half an audit trail, so the request id is generated at the edge, attached to the
log context, returned in the response header, and written onto audit_events.
"""
from __future__ import annotations

import logging
import sys

import structlog

from .config import settings


def configure_logging() -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout,
                        level=logging.DEBUG if settings.DEBUG else logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            (structlog.dev.ConsoleRenderer() if settings.ENVIRONMENT == "development"
             else structlog.processors.JSONRenderer()),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if settings.DEBUG else logging.INFO),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "tulya"):
    return structlog.get_logger(name)
