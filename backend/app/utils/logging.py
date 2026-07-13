import logging
import json
from datetime import datetime, timezone

# Configure root logger once
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. Import this everywhere instead of using logging directly."""
    return logging.getLogger(name)


def log_pipeline_decision(logger: logging.Logger, stage: str, decision: str, reason: str = "", **extra):
    """Structured log line for every orchestrator routing decision."""
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "decision": decision,
        "reason": reason,
        **extra,
    }
    logger.info(json.dumps(payload))
