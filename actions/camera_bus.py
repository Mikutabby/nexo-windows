"""Shared camera frame buffer — prevents double VideoCapture conflicts."""
import time
import threading

_frame: dict = {"bytes": None, "mime": "image/jpeg", "ts": 0.0}
_lock = threading.Lock()

def put_frame(jpeg_bytes: bytes) -> None:
    with _lock:
        _frame["bytes"] = jpeg_bytes
        _frame["mime"] = "image/jpeg"
        _frame["ts"] = time.time()

def get_frame(max_age: float = 2.0):
    """Returns (bytes, mime) if frame is fresh, else (None, None)."""
    with _lock:
        fb = _frame["bytes"]
        ts = _frame["ts"]
    if fb and (time.time() - ts) < max_age:
        return fb, "image/jpeg"
    return None, None

def clear_frame():
    with _lock:
        _frame["bytes"] = None
        _frame["ts"] = 0.0
