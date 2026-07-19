from __future__ import annotations

from threading import RLock
from typing import Any


class SharedDataManager:
    """<h1>DO NOT USE THIS CLASS DIRECTLY! USE <code>shared_data</code> VARIABLE INSTEAD TO AVOID OVERWRITING OR DATA ACCESS TROUBLES!</h1>
    <hr>

    Thread-safe storage for shared project-wide data."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._lock = RLock()

    def set(self, key: str, value: Any) -> Any:
        with self._lock:
            self._data[key] = value
            return value

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def require(self, key: str) -> Any:
        with self._lock:
            if key not in self._data:
                raise KeyError(f"Shared data '{key}' is not initialized")
            return self._data[key]

    def has(self, key: str) -> bool:
        with self._lock:
            return key in self._data

    def remove(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.pop(key, default)

    def update(self, **values: Any) -> None:
        with self._lock:
            self._data.update(values)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def all(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)


shared_data = SharedDataManager()
