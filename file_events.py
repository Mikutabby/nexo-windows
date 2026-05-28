"""file_events.py — Thread-safe event bus for NEXO file creation events."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

@dataclass
class FileEvent:
    path:      str   # absolute file path on disk
    name:      str   # display filename
    content:   str   # text content (empty for binary files)
    file_type: str   # "code" | "document" | "image" | "pdf" | "other"
    mime:      str   # "text/html", "image/png", etc.

_lock: threading.Lock = threading.Lock()
_handlers: list[Callable[[FileEvent], None]] = []


def subscribe(handler: Callable[[FileEvent], None]) -> None:
    with _lock:
        if handler not in _handlers:
            _handlers.append(handler)


def unsubscribe(handler: Callable[[FileEvent], None]) -> None:
    with _lock:
        if handler in _handlers:
            _handlers.remove(handler)


def emit(
    path:      str,
    name:      str  = "",
    content:   str  = "",
    file_type: str  = "other",
    mime:      str  = "",
) -> None:
    if not name:
        name = Path(path).name
    evt = FileEvent(path=path, name=name, content=content, file_type=file_type, mime=mime)
    with _lock:
        handlers = list(_handlers)
    for h in handlers:
        try:
            h(evt)
        except Exception:
            pass


# ── Convenience helpers ────────────────────────────────────────────────────────

def emit_document(path: str, content: str = "") -> None:
    p = Path(path)
    ext = p.suffix.lower()
    if ext in (".docx", ".doc"):
        ft, mime = "document", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif ext in (".xlsx", ".xls"):
        ft, mime = "document", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif ext == ".pdf":
        ft, mime = "pdf", "application/pdf"
    else:
        ft, mime = "document", "application/octet-stream"
    emit(str(p), p.name, content, ft, mime)


def emit_image(path: str) -> None:
    p = Path(path)
    ext = p.suffix.lower().lstrip(".")
    mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}
    emit(str(p), p.name, "", "image", mime_map.get(ext, "image/png"))


def emit_code(path: str, content: str = "") -> None:
    p = Path(path)
    ext = p.suffix.lower()
    mime_map = {
        ".html": "text/html", ".css": "text/css", ".js": "text/javascript",
        ".ts": "text/typescript", ".py": "text/python", ".json": "application/json",
        ".md": "text/markdown", ".txt": "text/plain", ".xml": "text/xml",
        ".sql": "text/sql", ".sh": "text/x-sh", ".bat": "text/bat",
    }
    mime = mime_map.get(ext, "text/plain")
    emit(str(p), p.name, content, "code", mime)
