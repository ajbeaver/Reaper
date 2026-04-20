from __future__ import annotations

import unittest
from datetime import datetime, timezone

from reaper_ticker.models import AppConfig, BehaviorConfig, DisplayConfig, FeedDefinition, FiltersConfig, NewsEntry
from reaper_ticker.state import FeedStore


def make_entry(entry_id: str, title: str, source: str, hour: int) -> NewsEntry:
    return NewsEntry(
        entry_id=entry_id,
        title=title,
        source=source,
        published_at=datetime(2026, 4, 20, hour, 0, tzinfo=timezone.utc),
        preview=f"{title} preview",
        link=f"https://example.com/{entry_id}",
        feed_url="https://example.com/feed.xml",
    )


class FeedStoreTests(unittest.TestCase):
    def test_ingest_dedupes_and_orders_newest_first(self) -> None:
        config = AppConfig(
            feeds=(FeedDefinition(name="Example", url="https://example.com/feed.xml"),),
            display=DisplayConfig(max_items=5, ordering="newest_first"),
            behavior=BehaviorConfig(dedupe_window=10),
        )
        store = FeedStore(config)
        added = store.ingest(
            [
                make_entry("1", "Older", "Source", 10),
                make_entry("1", "Duplicate", "Source", 10),
                make_entry("2", "Newer", "Source", 11),
            ]
        )
        self.assertEqual(added, 2)
        self.assertEqual([entry.entry_id for entry in store.entries], ["2", "1"])

    def test_ingest_applies_filters(self) -> None:
        config = AppConfig(
            feeds=(FeedDefinition(name="Example", url="https://example.com/feed.xml"),),
            filters=FiltersConfig(include_keywords=("python",), exclude_sources=("blocked",)),
            behavior=BehaviorConfig(dedupe_window=10),
        )
        store = FeedStore(config)
        added = store.ingest(
            [
                make_entry("1", "Python story", "Allowed", 10),
                make_entry("2", "Rust story", "Allowed", 11),
                make_entry("3", "Python blocked", "Blocked", 12),
            ]
        )
        self.assertEqual(added, 1)
        self.assertEqual(store.entries[0].entry_id, "1")

    def test_ingest_caps_retained_items(self) -> None:
        config = AppConfig(
            feeds=(FeedDefinition(name="Example", url="https://example.com/feed.xml"),),
            display=DisplayConfig(max_items=2),
            behavior=BehaviorConfig(dedupe_window=10),
        )
        store = FeedStore(config)
        store.ingest(
            [
                make_entry("1", "One", "Source", 9),
                make_entry("2", "Two", "Source", 10),
                make_entry("3", "Three", "Source", 11),
            ]
        )
        self.assertEqual([entry.entry_id for entry in store.entries], ["3", "2"])

    def test_ingest_globally_orders_entries_across_feeds(self) -> None:
        config = AppConfig(
            feeds=(
                FeedDefinition(name="First", url="https://example.com/first.xml"),
                FeedDefinition(name="Second", url="https://example.com/second.xml"),
            ),
            display=DisplayConfig(max_items=5, ordering="newest_first"),
            behavior=BehaviorConfig(dedupe_window=10),
        )
        store = FeedStore(config)
        store.ingest(
            [
                make_entry("1", "Older from first", "First", 10),
                make_entry("2", "Newest from first", "First", 12),
                make_entry("3", "Middle from second", "Second", 11),
            ]
        )
        self.assertEqual([entry.entry_id for entry in store.entries], ["2", "3", "1"])

    def test_ingest_keeps_unknown_dates_after_known_dates(self) -> None:
        config = AppConfig(
            feeds=(FeedDefinition(name="Example", url="https://example.com/feed.xml"),),
            display=DisplayConfig(max_items=5, ordering="newest_first"),
            behavior=BehaviorConfig(dedupe_window=10),
        )
        store = FeedStore(config)
        store.ingest(
            [
                make_entry("1", "Known", "Source", 11),
                NewsEntry(
                    entry_id="2",
                    title="Unknown",
                    source="Source",
                    published_at=None,
                    preview="Unknown preview",
                    link="https://example.com/2",
                    feed_url="https://example.com/feed.xml",
                ),
            ]
        )
        self.assertEqual([entry.entry_id for entry in store.entries], ["1", "2"])


if __name__ == "__main__":
    unittest.main()
