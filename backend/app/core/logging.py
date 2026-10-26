"""Logging con redacción de secretos: ninguna clave o token debe acabar en un log."""

import logging
import re

_PATTERNS = [
    re.compile(r"(Authorization:\s*)(ApiKey|Bearer)\s+\S+", re.IGNORECASE),
    re.compile(
        r"((?:api[_-]?key|access[_-]?token|token|secret|password)[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]+",
        re.IGNORECASE,
    ),
]


def redact(text: str) -> str:
    for pattern in _PATTERNS:
        text = pattern.sub(lambda m: f"{m.group(1)}***", text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg))
        if record.args:
            record.args = tuple(redact(str(a)) for a in record.args)
        return True


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # httpx registra URLs; nunca cabeceras, pero bajamos su nivel por ruido.
    logging.getLogger("httpx").setLevel(logging.WARNING)
