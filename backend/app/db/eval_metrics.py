"""
Persistent metrics store for the evaluation harness — the backing DB for the
observability dashboard (trends over time), separate from the operational
civic.db so metric history survives whenever the dev complaint DB is reset.

Deliberately plain sqlite3 (not SQLModel): this table is append-only telemetry
with no relations, and keeping it off SQLModel's shared metadata avoids the
metrics table leaking into civic.db (or vice-versa). Every eval script logs a
row per headline metric per run via log_metric(); the /eval/trends endpoint and
the EvalConsole sparklines read them back via fetch_trends().
"""
import os
import sqlite3
import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# backend/eval_metrics.db  (app/db/eval_metrics.py -> app -> backend)
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(_BACKEND_DIR, "eval_metrics.db")


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_metric (
            id          TEXT PRIMARY KEY,
            run_id      TEXT,
            created_at  TEXT,   -- ISO-8601 UTC; lexicographic order == chronological
            layer       TEXT,   -- which eval produced it, e.g. 'summary_grounding'
            model       TEXT,   -- LLM_MODEL at run time (compare models over time)
            metric      TEXT,   -- e.g. 'hallucination_rate'
            value       REAL,   -- the number (0..1 or 0..100 depending on metric)
            n           INTEGER,-- sample size behind the value
            extra_json  TEXT    -- optional drill-down detail
        )
        """
    )
    return conn


def new_run_id() -> str:
    """One id groups every metric logged during a single script invocation."""
    return str(uuid.uuid4())


def log_metric(layer: str, metric: str, value: float, n: int,
               model: str = "", run_id: Optional[str] = None,
               extra: Optional[dict] = None) -> None:
    """Append one metric row. Best-effort: never let telemetry crash an eval run."""
    try:
        conn = _connect()
        conn.execute(
            "INSERT INTO eval_metric (id, run_id, created_at, layer, model, metric, value, n, extra_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                run_id or new_run_id(),
                datetime.now(timezone.utc).isoformat(),
                layer, model, metric,
                float(value) if value is not None else None,
                int(n) if n is not None else None,
                json.dumps(extra) if extra else None,
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:  # noqa: BLE001 — telemetry must never break the actual eval
        logger.warning(f"log_metric failed ({layer}/{metric}): {e}")


def fetch_trends(limit: int = 20) -> dict:
    """
    Returns {metric: [{created_at, model, value, n}, ...]} with up to `limit`
    most-recent points per metric, ordered oldest -> newest (chart-ready).
    Empty dict if the store doesn't exist yet.
    """
    if not os.path.exists(DB_PATH):
        return {}
    try:
        conn = _connect()
        rows = conn.execute(
            "SELECT metric, created_at, model, value, n FROM eval_metric ORDER BY created_at ASC"
        ).fetchall()
        conn.close()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"fetch_trends failed: {e}")
        return {}

    series: dict = {}
    for metric, created_at, model, value, n in rows:
        series.setdefault(metric, []).append(
            {"created_at": created_at, "model": model, "value": value, "n": n}
        )
    # Keep only the last `limit` points per metric.
    return {m: pts[-limit:] for m, pts in series.items()}
