from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reaper_ticker.config import ConfigError, default_config_path, discover_config_path, dump_default_config, load_config, parse_config


class ConfigTests(unittest.TestCase):
    def test_parse_config_uses_defaults(self) -> None:
        config = parse_config(
            {
                "feeds": [
                    {
                        "name": "Example",
                        "url": "https://example.com/feed.xml",
                    }
                ]
            }
        )
        self.assertEqual(config.display.ordering, "newest_first")
        self.assertEqual(config.display.max_items, 200)
        self.assertTrue(config.behavior.open_links)
        self.assertEqual(config.theme.preset, "default")
        self.assertEqual(config.theme.header_title, "REAPER TICKER")
        self.assertEqual(config.theme.palette.header_bg, "cyan")

    def test_parse_config_rejects_invalid_display(self) -> None:
        with self.assertRaises(ConfigError):
            parse_config(
                {
                    "feeds": [{"name": "Example", "url": "https://example.com/feed.xml"}],
                    "display": {"density": "dense"},
                }
            )

    def test_load_config_reads_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "feeds": [
                            {
                                "name": "Example",
                                "url": "https://example.com/feed.xml",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            config = load_config(path)
        self.assertEqual(config.feeds[0].name, "Example")

    def test_default_config_path_uses_dot_reaper(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("reaper_ticker.config.Path.home", return_value=Path(tmpdir)):
                self.assertEqual(default_config_path(), Path(tmpdir) / ".reaper" / "config.json")

    def test_discover_config_path_prefers_home_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            local_config = root / "config.json"
            local_config.write_text(json.dumps({"feeds": [{"name": "Local", "url": "https://example.com/local.xml"}]}), encoding="utf-8")
            home_config = root / ".reaper" / "config.json"
            home_config.parent.mkdir(parents=True, exist_ok=True)
            home_config.write_text(json.dumps({"feeds": [{"name": "Home", "url": "https://example.com/home.xml"}]}), encoding="utf-8")
            with patch("reaper_ticker.config.Path.home", return_value=root):
                discovered = discover_config_path(root)
        self.assertEqual(discovered, home_config)

    def test_load_config_uses_home_default_when_local_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            home_config = root / ".reaper" / "config.json"
            home_config.parent.mkdir(parents=True, exist_ok=True)
            home_config.write_text(
                json.dumps({"feeds": [{"name": "Home", "url": "https://example.com/home.xml"}]}),
                encoding="utf-8",
            )
            previous_cwd = Path.cwd()
            os.chdir(root)
            try:
                with patch("reaper_ticker.config.Path.home", return_value=root):
                    config = load_config()
            finally:
                os.chdir(previous_cwd)
        self.assertEqual(config.feeds[0].name, "Home")

    def test_parse_config_accepts_theme_overrides(self) -> None:
        config = parse_config(
            {
                "feeds": [{"name": "Example", "url": "https://example.com/feed.xml"}],
                "theme": {
                    "preset": "matrix",
                    "header_title": "MY TICKER",
                    "header_tagline": "custom wire",
                    "palette": {
                        "header_bg": "blue",
                        "selected": "magenta",
                    },
                },
            }
        )
        self.assertEqual(config.theme.preset, "matrix")
        self.assertEqual(config.theme.header_title, "MY TICKER")
        self.assertEqual(config.theme.header_tagline, "custom wire")
        self.assertEqual(config.theme.palette.header_bg, "blue")
        self.assertEqual(config.theme.palette.selected, "magenta")
        self.assertEqual(config.theme.palette.accent, "green")

    def test_parse_config_rejects_invalid_theme_color(self) -> None:
        with self.assertRaises(ConfigError):
            parse_config(
                {
                    "feeds": [{"name": "Example", "url": "https://example.com/feed.xml"}],
                    "theme": {"palette": {"accent": "orange"}},
                }
            )

    def test_parse_config_rejects_invalid_theme_preset(self) -> None:
        with self.assertRaises(ConfigError):
            parse_config(
                {
                    "feeds": [{"name": "Example", "url": "https://example.com/feed.xml"}],
                    "theme": {"preset": "sunset"},
                }
            )

    def test_dump_default_config_is_valid_json(self) -> None:
        data = json.loads(dump_default_config())
        self.assertIn("feeds", data)


if __name__ == "__main__":
    unittest.main()
