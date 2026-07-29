import sys
from datetime import datetime, timezone


def _format(level: str, message: str) -> str:
    ts = datetime.now(timezone.utc).isoformat()
    return f"[{ts}] {level}: {message}"


def info(message: str) -> None:
    print(_format("INFO", message), file=sys.stderr)


def warn(message: str) -> None:
    print(_format("WARN", message), file=sys.stderr)


def error(message: str) -> None:
    print(_format("ERROR", message), file=sys.stderr)


def debug(message: str) -> None:
    if __debug__:
        print(_format("DEBUG", message), file=sys.stderr)