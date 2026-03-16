"""
In-memory metrics collector.
Resets on server restart — sufficient for local/dev observability.
Thread-safe via threading.Lock.
"""
from __future__ import annotations

from collections import defaultdict
from threading import Lock

from backend.lib.logger import get_logger

log = get_logger("lib.metrics")

_lock = Lock()

_counters: dict[str, int] = defaultdict(int)
_total_latency_ms: float = 0.0
_latency_samples: int = 0


def record_request(path: str, latency_ms: float, *, is_error: bool = False) -> None:
    """Record a single request. Call from middleware after each response."""
    global _total_latency_ms, _latency_samples
    with _lock:
        _counters["total_requests"] += 1
        _counters[f"path:{path}"] += 1
        if is_error:
            _counters["total_errors"] += 1
        _total_latency_ms += latency_ms
        _latency_samples += 1


def get_snapshot() -> dict:
    """Return a point-in-time snapshot of all collected metrics."""
    with _lock:
        avg_ms = _total_latency_ms / _latency_samples if _latency_samples else 0.0
        endpoint_counts = {
            k[len("path:"):]: v
            for k, v in _counters.items()
            if k.startswith("path:")
        }
        return {
            "total_requests": _counters["total_requests"],
            "total_errors": _counters["total_errors"],
            "avg_latency_ms": round(avg_ms, 2),
            "endpoints": endpoint_counts,
        }


def reset() -> None:
    """Reset all metrics. Intended for testing only."""
    global _total_latency_ms, _latency_samples
    with _lock:
        _counters.clear()
        _total_latency_ms = 0.0
        _latency_samples = 0
