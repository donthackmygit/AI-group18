from __future__ import annotations

from contextlib import contextmanager
from queue import Empty, Full, LifoQueue
from threading import BoundedSemaphore, Lock
from typing import Any, Iterator

from backend.app.core.config import Settings


DEFAULT_POOL_MAX_SIZE = 5


class _DatabasePool:
    def __init__(self, kwargs: dict[str, str | int], max_size: int) -> None:
        self._kwargs = dict(kwargs)
        self._idle: LifoQueue[Any] = LifoQueue(maxsize=max_size)
        self._semaphore = BoundedSemaphore(max_size)

    def acquire(self) -> Any:
        self._semaphore.acquire()
        try:
            while True:
                try:
                    conn = self._idle.get_nowait()
                except Empty:
                    return self._connect()

                if _is_connection_usable(conn):
                    return conn

                _close_quietly(conn)
        except Exception:
            self._semaphore.release()
            raise

    def release(self, conn: Any) -> None:
        try:
            if not _is_connection_usable(conn):
                _close_quietly(conn)
                return

            try:
                conn.rollback()
            except Exception:
                _close_quietly(conn)
                return

            try:
                self._idle.put_nowait(conn)
            except Full:
                _close_quietly(conn)
        finally:
            self._semaphore.release()

    def close(self) -> None:
        while True:
            try:
                conn = self._idle.get_nowait()
            except Empty:
                return
            _close_quietly(conn)

    def _connect(self) -> Any:
        import psycopg

        return psycopg.connect(**self._kwargs)


_pools: dict[tuple[tuple[str, str], ...], _DatabasePool] = {}
_pools_lock = Lock()


@contextmanager
def get_database_connection(settings: Settings) -> Iterator[Any]:
    pool = _get_pool(settings)
    conn = pool.acquire()
    try:
        yield conn
    finally:
        pool.release(conn)


def close_database_pools() -> None:
    with _pools_lock:
        pools = list(_pools.values())
        _pools.clear()

    for pool in pools:
        pool.close()


def _get_pool(settings: Settings) -> _DatabasePool:
    kwargs = settings.database_kwargs()
    key = tuple(sorted((str(name), str(value)) for name, value in kwargs.items()))

    with _pools_lock:
        pool = _pools.get(key)
        if pool is None:
            pool = _DatabasePool(kwargs, DEFAULT_POOL_MAX_SIZE)
            _pools[key] = pool
        return pool


def _is_connection_usable(conn: Any) -> bool:
    return not bool(getattr(conn, "closed", True))


def _close_quietly(conn: Any) -> None:
    try:
        conn.close()
    except Exception:
        pass
