from __future__ import annotations

import unittest

from reaper_ticker.feeds import FeedError, parse_feed
from reaper_ticker.models import FeedDefinition

RSS_SAMPLE = b"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Sample RSS</title>
    <item>
      <title>First story</title>
      <link>https://example.com/1</link>
      <guid>story-1</guid>
      <pubDate>Mon, 20 Apr 2026 12:00:00 GMT</pubDate>
      <description><![CDATA[<p>Hello <b>world</b>.</p>]]></description>
    </item>
  </channel>
</rss>
"""

ATOM_SAMPLE = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example Feed</title>
  <entry>
    <title>Atom entry</title>
    <id>tag:example.com,2026:/posts/1</id>
    <updated>2026-04-20T13:00:00Z</updated>
    <summary>Summary text</summary>
    <link href="https://example.com/atom-1" rel="alternate" />
  </entry>
</feed>
"""


class FeedParsingTests(unittest.TestCase):
    def test_parse_rss_feed(self) -> None:
        entries = parse_feed(
            RSS_SAMPLE,
            FeedDefinition(name="Sample", url="https://example.com/rss.xml"),
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].entry_id, "story-1")
        self.assertEqual(entries[0].preview, "Hello world.")

    def test_parse_atom_feed(self) -> None:
        entries = parse_feed(
            ATOM_SAMPLE,
            FeedDefinition(name="Sample", url="https://example.com/atom.xml"),
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].title, "Atom entry")
        self.assertEqual(entries[0].link, "https://example.com/atom-1")

    def test_parse_feed_rejects_invalid_xml(self) -> None:
        with self.assertRaises(FeedError):
            parse_feed(b"<not-xml", FeedDefinition(name="Bad", url="https://example.com"))


if __name__ == "__main__":
    unittest.main()

