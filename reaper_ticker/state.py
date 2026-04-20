from __future__ import annotations

from collections import deque

from reaper_ticker.models import AppConfig, NewsEntry


class FeedStore:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._entries: list[NewsEntry] = []
        self._seen_ids: set[str] = set()
        self._seen_order: deque[str] = deque()

    @property
    def entries(self) -> list[NewsEntry]:
        return list(self._entries)

    def ingest(self, incoming: list[NewsEntry]) -> int:
        added_count = 0
        for entry in incoming:
            if entry.entry_id in self._seen_ids:
                continue
            if not self._matches_filters(entry):
                continue
            self._entries.append(entry)
            self._remember(entry.entry_id)
            added_count += 1

        if added_count:
            self._entries.sort(key=self._sort_key)
            self._entries = self._entries[: self._config.display.max_items]
        return added_count

    def _sort_key(self, item: NewsEntry) -> tuple[bool, float]:
        if item.published_at is None:
            return (True, 0.0)
        timestamp = item.published_at.timestamp()
        if self._config.display.ordering == "newest_first":
            return (False, -timestamp)
        return (False, timestamp)

    def _remember(self, entry_id: str) -> None:
        self._seen_ids.add(entry_id)
        self._seen_order.append(entry_id)
        while len(self._seen_order) > self._config.behavior.dedupe_window:
            expired = self._seen_order.popleft()
            self._seen_ids.discard(expired)

    def _matches_filters(self, entry: NewsEntry) -> bool:
        haystack = f"{entry.title} {entry.preview}".casefold()
        source = entry.source.casefold()

        include_sources = [value.casefold() for value in self._config.filters.include_sources]
        if include_sources and source not in include_sources:
            return False

        exclude_sources = [value.casefold() for value in self._config.filters.exclude_sources]
        if source in exclude_sources:
            return False

        include_keywords = [value.casefold() for value in self._config.filters.include_keywords]
        if include_keywords and not any(keyword in haystack for keyword in include_keywords):
            return False

        exclude_keywords = [value.casefold() for value in self._config.filters.exclude_keywords]
        if any(keyword in haystack for keyword in exclude_keywords):
            return False

        return True
