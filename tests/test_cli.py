from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from reaper_ticker.cli import apply_runtime_overrides, build_parser, main
from reaper_ticker.config import load_config


class CliTests(unittest.TestCase):
    def test_help_mentions_theme_presets_and_commands(self) -> None:
        help_text = build_parser().format_help()
        self.assertIn("--config", help_text)
        self.assertIn("--dump-default-config", help_text)
        self.assertIn("matrix", help_text)
        self.assertIn("newspaper", help_text)
        self.assertIn("config", help_text)
        self.assertIn("doctor", help_text)

    def test_parser_collects_repeatable_run_overrides(self) -> None:
        args = build_parser().parse_args(
            [
                "--include-keyword",
                "python",
                "--include-keyword",
                "rss",
                "--feed",
                "https://example.com/feed.xml",
            ]
        )
        self.assertEqual(args.include_keyword, ["python", "rss"])
        self.assertEqual(args.feed, ["https://example.com/feed.xml"])

    def test_apply_runtime_overrides_updates_effective_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_config(Path(tmpdir))
            config = load_config(path)
            args = build_parser().parse_args(
                [
                    "--theme",
                    "matrix",
                    "--refresh-interval",
                    "120",
                    "--include-keyword",
                    "python",
                    "--disable-open-links",
                    "--feed",
                    "https://example.com/extra.xml",
                ]
            )
            overridden = apply_runtime_overrides(config, args)
        self.assertEqual(overridden.theme.preset, "matrix")
        self.assertEqual(overridden.display.refresh_interval_seconds, 120)
        self.assertIn("python", overridden.filters.include_keywords)
        self.assertFalse(overridden.behavior.open_links)
        self.assertEqual(len(overridden.feeds), 2)

    def test_config_show_resolved_prints_expanded_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_config(Path(tmpdir), theme={"preset": "matrix"})
            output = self._run_main(["config", "show", "--resolved", "--config", str(path)])
        payload = json.loads(output)
        self.assertEqual(payload["theme"]["preset"], "matrix")
        self.assertEqual(payload["theme"]["palette"]["accent"], "green")

    def test_theme_show_prints_palette_and_chrome(self) -> None:
        output = self._run_main(["theme", "show", "amber"])
        payload = json.loads(output)
        self.assertEqual(payload["preset"], "amber")
        self.assertIn("chrome", payload)
        self.assertIn("selected_prefix", payload["chrome"])

    def test_feed_list_prints_configured_feeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_config(Path(tmpdir))
            output = self._run_main(["--config", str(path), "feed", "list"])
        self.assertIn("[enabled]", output)
        self.assertIn("Example", output)

    def test_config_init_stdout_prints_starter_config(self) -> None:
        output = self._run_main(["config", "init", "--stdout"])
        payload = json.loads(output)
        self.assertIn("feeds", payload)
        self.assertIn("theme", payload)

    def test_doctor_runs_without_entering_tui(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_config(Path(tmpdir))
            with patch("reaper_ticker.cli.webbrowser.get") as browser_get, patch(
                "reaper_ticker.cli.detect_color_support",
                return_value="256 colors",
            ):
                browser_get.return_value.name = "test-browser"
                output = self._run_main(["--config", str(path), "doctor"])
        self.assertIn("Doctor Report", output)
        self.assertIn("Config: OK", output)
        self.assertIn("Browser: OK", output)

    def test_default_invocation_launches_tui(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_config(Path(tmpdir))
            with patch("reaper_ticker.cli.TickerApp") as app_cls:
                app_cls.return_value.run.return_value = 7
                result = main(["--config", str(path)])
        self.assertEqual(result, 7)
        app_cls.return_value.run.assert_called_once()

    def test_default_invocation_uses_local_config_without_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_config(root, theme={"preset": "default"})
            previous_cwd = Path.cwd()
            os.chdir(root)
            try:
                with patch("reaper_ticker.cli.TickerApp") as app_cls:
                    app_cls.return_value.run.return_value = 5
                    result = main(["--theme", "matrix"])
            finally:
                os.chdir(previous_cwd)
        self.assertEqual(result, 5)
        passed_config = app_cls.call_args.args[0]
        self.assertEqual(passed_config.theme.preset, "matrix")

    def _run_main(self, argv: list[str]) -> str:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = main(argv)
        self.assertEqual(result, 0)
        return stdout.getvalue()

    def _write_config(self, directory: Path, theme: dict[str, object] | None = None) -> Path:
        path = directory / "config.json"
        payload = {
            "feeds": [
                {
                    "name": "Example",
                    "url": "https://example.com/feed.xml",
                    "enabled": True,
                    "tags": ["news"],
                }
            ],
            "theme": theme or {},
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path


if __name__ == "__main__":
    unittest.main()
