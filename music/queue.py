"""Очередь воспроизведения."""

from __future__ import annotations

import random
from collections import deque
from collections.abc import Iterable, Iterator

from music.track import Track


class QueueFull(Exception):
    """Очередь достигла максимального размера."""


class Queue:
    """Двусторонняя очередь треков с ограничением по размеру."""

    def __init__(self, max_size: int = 500) -> None:
        self._items: deque[Track] = deque()
        self.max_size = max_size

    def __len__(self) -> int:
        return len(self._items)

    def __bool__(self) -> bool:
        return bool(self._items)

    def __iter__(self) -> Iterator[Track]:
        return iter(self._items)

    @property
    def is_full(self) -> bool:
        return len(self._items) >= self.max_size

    def items(self) -> list[Track]:
        return list(self._items)

    def peek(self) -> Track | None:
        return self._items[0] if self._items else None

    def pop(self) -> Track | None:
        return self._items.popleft() if self._items else None

    def add_first(self, track: Track) -> None:
        self._items.appendleft(track)

    def add(self, track: Track) -> None:
        if self.is_full:
            raise QueueFull
        self._items.append(track)

    def add_many(self, tracks: Iterable[Track]) -> int:
        """Добавляет треки, возвращает количество добавленных."""

        added = 0
        for track in tracks:
            if self.is_full:
                break
            self._items.append(track)
            added += 1
        return added

    def remove(self, index: int) -> Track:
        """Удаляет трек по индексу с нуля."""

        if index < 0 or index >= len(self._items):
            raise IndexError(index)
        track = self._items[index]
        del self._items[index]
        return track

    def clear(self) -> None:
        self._items.clear()

    def shuffle(self) -> None:
        shuffled = list(self._items)
        random.shuffle(shuffled)
        self._items = deque(shuffled)

    @property
    def total_duration(self) -> int:
        return sum(track.duration for track in self._items)

    def page(self, page: int, per_page: int) -> tuple[list[Track], int, int]:
        """Возвращает треки страницы, номер страницы и общее число страниц."""

        per_page = max(1, per_page)
        pages = max(1, -(-len(self._items) // per_page))
        page = min(max(1, page), pages)
        start = (page - 1) * per_page
        return list(self._items)[start : start + per_page], page, pages
