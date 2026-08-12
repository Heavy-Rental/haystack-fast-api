"""Process-local idempotency store for Call 1 ingest (S2a / resilience C1).

Maps a scoped key (``user_id`` + ``Idempotency-Key``) to a successful lean
``IngestFromProjectSpecResponse``. Failed 4xx/5xx responses are never stored.

**Limit:** single-process memory only — not shared across replicas. Documented
in OpenSpec contract and Postman ops notes. Optional TTL bounds memory growth.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from app.schemas.indexing import IngestFromProjectSpecResponse


def scope_idempotency_key(user_id: str, idempotency_key: str) -> str:
    """Stable store key: ``user_id`` + client ``Idempotency-Key``."""
    return f"{(user_id or '').strip()}:{(idempotency_key or '').strip()}"


def normalize_idempotency_key(raw: str | None) -> str | None:
    """Return stripped key or None when missing/blank."""
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


class InMemoryIdempotencyStore:
    """Thread-safe in-memory map of successful ingest responses.

    Concurrent POSTs with the same scoped key use **single-flight**: waiters
    block until the first producer finishes, then receive the cached 200 body
    (or re-raise if the first attempt failed without caching).
    """

    def __init__(self, *, ttl_seconds: float | None = 86400.0) -> None:
        self._ttl_seconds = ttl_seconds
        self._lock = threading.RLock()
        self._entries: dict[
            str, tuple[float | None, IngestFromProjectSpecResponse]
        ] = {}
        self._inflight: dict[str, threading.Event] = {}
        self._inflight_errors: dict[str, BaseException] = {}

    def get(self, key: str) -> IngestFromProjectSpecResponse | None:
        with self._lock:
            return self._get_unlocked(key)

    def _get_unlocked(self, key: str) -> IngestFromProjectSpecResponse | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, response = entry
        if expires_at is not None and time.monotonic() >= expires_at:
            del self._entries[key]
            return None
        return response.model_copy(deep=True)

    def put(self, key: str, response: IngestFromProjectSpecResponse) -> None:
        expires_at: float | None = None
        if self._ttl_seconds is not None and self._ttl_seconds > 0:
            expires_at = time.monotonic() + float(self._ttl_seconds)
        with self._lock:
            self._entries[key] = (expires_at, response.model_copy(deep=True))

    def run_once(
        self,
        key: str,
        producer: Callable[[], IngestFromProjectSpecResponse],
    ) -> IngestFromProjectSpecResponse:
        """Return cached success, join in-flight peer, or run ``producer`` once.

        Only successful producer results are cached. Exceptions propagate and
        are not treated as successful idempotent outcomes.
        """
        while True:
            with self._lock:
                cached = self._get_unlocked(key)
                if cached is not None:
                    return cached
                if key in self._inflight:
                    event = self._inflight[key]
                    is_waiter = True
                else:
                    event = threading.Event()
                    self._inflight[key] = event
                    is_waiter = False

            if is_waiter:
                event.wait(timeout=300.0)
                with self._lock:
                    cached = self._get_unlocked(key)
                    if cached is not None:
                        return cached
                    err = self._inflight_errors.pop(key, None)
                if err is not None:
                    raise err
                # Producer failed without a cache entry — try again as owner.
                continue

            try:
                result = producer()
                self.put(key, result)
                return result
            except BaseException as exc:
                with self._lock:
                    self._inflight_errors[key] = exc
                raise
            finally:
                with self._lock:
                    self._inflight.pop(key, None)
                event.set()

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._inflight.clear()
            self._inflight_errors.clear()

    def __len__(self) -> int:
        with self._lock:
            # Drop expired while counting
            keys = list(self._entries.keys())
            alive = 0
            for key in keys:
                if self._get_unlocked(key) is not None:
                    alive += 1
            return alive


_store: InMemoryIdempotencyStore | None = None
_store_lock = threading.RLock()


def get_ingest_idempotency_store() -> InMemoryIdempotencyStore:
    """Return the process-local singleton store (lazy, settings-backed TTL)."""
    global _store
    with _store_lock:
        if _store is None:
            from app.config import get_settings

            settings = get_settings()
            _store = InMemoryIdempotencyStore(
                ttl_seconds=settings.idempotency_ttl_seconds
            )
        return _store


def reset_ingest_idempotency_store() -> InMemoryIdempotencyStore:
    """Replace the singleton (tests)."""
    global _store
    with _store_lock:
        from app.config import get_settings

        settings = get_settings()
        _store = InMemoryIdempotencyStore(
            ttl_seconds=settings.idempotency_ttl_seconds
        )
        return _store
