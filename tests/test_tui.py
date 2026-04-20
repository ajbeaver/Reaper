from __future__ import annotations

import unittest

from reaper_ticker.models import AppConfig, DisplayConfig, FeedDefinition
from reaper_ticker.tui import (
    RenderState,
    StyledLine,
    adjust_scroll_for_selection,
    build_divider,
    build_header_rule,
    build_header_title,
    compute_page_step,
    count_visible_entries,
    get_newest_index,
    get_theme_chrome,
    load_splash_art,
    truncate_line,
)


class SplashTests(unittest.TestCase):
    def test_load_splash_art_returns_lines(self) -> None:
        lines = load_splash_art()
        self.assertGreater(len(lines), 5)
        self.assertTrue(any(line.strip() for line in lines))

    def test_build_header_rule_matches_requested_width(self) -> None:
        rule = build_header_rule(17)
        self.assertEqual(len(rule), 17)

    def test_truncate_line_adds_ellipsis(self) -> None:
        self.assertEqual(truncate_line("abcdefgh", 5), "ab...")

    def test_preset_chrome_is_distinct(self) -> None:
        self.assertNotEqual(build_header_rule(12, "matrix"), build_header_rule(12, "ice"))
        self.assertNotEqual(build_divider(12, "amber"), build_divider(12, "newspaper"))
        self.assertIn("REAPER", build_header_title("REAPER", "default"))
        self.assertEqual(get_theme_chrome("matrix").selected_prefix, "[]")

    def test_adjust_scroll_for_selection_moves_downward(self) -> None:
        render_state = RenderState(
            lines=[
                StyledLine("a0", "title", 0),
                StyledLine("a1", "meta", 0),
                StyledLine("b0", "title", 1),
                StyledLine("b1", "meta", 1),
                StyledLine("c0", "title", 2),
                StyledLine("c1", "meta", 2),
            ],
            content_height=3,
        )
        self.assertEqual(adjust_scroll_for_selection(render_state, 2, 0.0), 3.0)

    def test_adjust_scroll_for_selection_moves_upward(self) -> None:
        render_state = RenderState(
            lines=[
                StyledLine("a0", "title", 0),
                StyledLine("a1", "meta", 0),
                StyledLine("b0", "title", 1),
                StyledLine("b1", "meta", 1),
                StyledLine("c0", "title", 2),
                StyledLine("c1", "meta", 2),
            ],
            content_height=3,
        )
        self.assertEqual(adjust_scroll_for_selection(render_state, 0, 4.0), 0.0)

    def test_count_visible_entries_counts_distinct_items(self) -> None:
        render_state = RenderState(
            lines=[
                StyledLine("a0", "title", 0),
                StyledLine("a1", "meta", 0),
                StyledLine("b0", "title", 1),
                StyledLine("b1", "meta", 1),
                StyledLine("c0", "title", 2),
            ],
            content_height=3,
        )
        self.assertEqual(count_visible_entries(render_state, 0.0), 2)

    def test_compute_page_step_uses_visible_entries(self) -> None:
        render_state = RenderState(
            lines=[
                StyledLine("a0", "title", 0),
                StyledLine("a1", "meta", 0),
                StyledLine("b0", "title", 1),
                StyledLine("b1", "meta", 1),
                StyledLine("c0", "title", 2),
                StyledLine("c1", "meta", 2),
            ],
            content_height=4,
        )
        self.assertEqual(compute_page_step(render_state, 0.0, 1.0), 1)
        self.assertEqual(compute_page_step(render_state, 0.0, 0.5), 1)

    def test_get_newest_index_respects_ordering(self) -> None:
        newest_first = AppConfig(
            feeds=(FeedDefinition(name="Example", url="https://example.com/feed.xml"),),
            display=DisplayConfig(ordering="newest_first"),
        )
        oldest_first = AppConfig(
            feeds=(FeedDefinition(name="Example", url="https://example.com/feed.xml"),),
            display=DisplayConfig(ordering="oldest_first"),
        )
        self.assertEqual(get_newest_index(newest_first, 5), 0)
        self.assertEqual(get_newest_index(oldest_first, 5), 4)


if __name__ == "__main__":
    unittest.main()
