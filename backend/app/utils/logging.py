"""
Structured logging setup (Phase 6 / NFR6). This module used to define
get_logger()/log_pipeline_decision() but nothing in the app ever imported
it — logging.basicConfig() never ran, so every app.* logger fell through to
Python's WARNING-only "lastResort" handler and every INFO-level pipeline log
was silently dropped in production. configure_logging() is now called once
from main.py at import time and is the only thing that actually attaches a
handler.
"""
import json
import logging
import sys
from datetime import datetime, timezone

# Standard LogRecord attributes — anything else found on a record (passed in
# via `extra=`) is a genuinely custom field and gets surfaced in the JSON
# output as its own key, so Cloud Logging can filter/query on it directly
# (jsonPayload.stage, jsonPayload.cost_usd, etc).
_STANDARD_RECORD_FIELDS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName", "message",
}


class JsonFormatter(logging.Formatter):
    """One JSON object per line — readable as-is in journald, and directly
    queryable once shipped to Cloud Logging (jsonPayload.<field>)."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_FIELDS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


_configured = False


def configure_logging():
    """
    Idempotent — safe to call from main.py's module scope even if something
    (a test harness, an eval script) imports app.main more than once in the
    same process.
    """
    global _configured
    if _configured:
        return
    _configured = True

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # Cloud Logging shipping — best-effort. Uses the VM's attached service
    # account via Application Default Credentials (the official-library
    # equivalent of the metadata-server token fetch deploy/fetch_secrets.sh
    # does by hand for Secret Manager). In local dev / CI / pytest, ADC
    # isn't present, so this silently no-ops rather than crashing app
    # startup over an observability nice-to-have — a missing Cloud Logging
    # handler must never be why the app fails to boot.
    try:
        import google.cloud.logging as gcp_logging
        cloud_handler = gcp_logging.Client().get_default_handler()
        # CloudLoggingHandler formats the record through whatever formatter
        # it's given, and — if the result starts with "{" — parses it back
        # into a dict and ships THAT as the structured jsonPayload (see
        # google.cloud.logging_v2.handlers.handlers._format_and_parse_message).
        # Without this, every extra= field (stage, cost_usd, ...) would only
        # ever land as flattened text, not as queryable jsonPayload.<field>.
        cloud_handler.setFormatter(JsonFormatter())
        root.addHandler(cloud_handler)
    except Exception as e:
        logging.getLogger(__name__).warning(f"Cloud Logging handler not attached (no ADC / not on GCP?): {e}")


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. Prefer this over logging.getLogger directly —
    kept as a thin wrapper so call sites don't need to know it's stdlib."""
    return logging.getLogger(name)


def log_stage(logger: logging.Logger, complaint_id, stage: str, decision: str,
              reason: str = "", level: str = "info", **extra):
    """
    Structured per-pipeline-stage log line (NFR6) — same human-readable
    "[id] Stage: X | Decision: Y | Reason: Z" message the orchestrator
    already used, now with real queryable fields attached via `extra=`
    instead of only being buried inside the message string.
    """
    msg = f"[{complaint_id}] Stage: {stage} | Decision: {decision}"
    if reason:
        msg += f" | Reason: {reason}"
    getattr(logger, level)(
        msg,
        extra={
            "event": "pipeline_stage", "complaint_id": str(complaint_id),
            "stage": stage, "decision": decision, "reason": reason, **extra,
        },
    )
