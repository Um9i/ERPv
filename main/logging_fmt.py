"""Structured JSON log formatter for production use."""

import json
import logging
import traceback
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line.

    Merges ``record.extra`` fields (if present) into the output so that
    structured ``logger.info("event", extra={...})`` calls produce
    searchable key/value pairs in centralised log aggregators.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1] is not None:
            log_entry["exception"] = traceback.format_exception(*record.exc_info)
        # merge any extra keys the caller passed
        for key in ("extra",):
            val = getattr(record, key, None)
            if isinstance(val, dict):
                log_entry.update(val)
        return json.dumps(log_entry, default=str)
