from __future__ import annotations

import argparse
import curses
import json
import os
import sys
import webbrowser
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse

from reaper_ticker.config import (
    ConfigError,
    THEME_DESCRIPTIONS,
    THEME_PRESETS,
    config_search_paths,
    discover_config_path,
    default_config_path,
    dump_default_config,
    dump_resolved_config,
    load_config,
)
from reaper_ticker.models import AppConfig, FeedDefinition, FiltersConfig, ThemeConfig, ThemePalette
from reaper_ticker.tui import TickerApp, get_theme_chrome


class HelpFormatter(argparse.RawDescriptionHelpFormatter, argparse.ArgumentDefaultsHelpFormatter):
    """Combined formatter for examples plus visible defaults."""


def build_parser() -> argparse.ArgumentParser:
    theme_list = ", ".join(THEME_PRESETS.keys())
    search_help = format_config_search_help()
    config_parent = argparse.ArgumentParser(add_help=False)
    config_parent.add_argument(
        "--config",
        type=Path,
        default=argparse.SUPPRESS,
        help=f"Path to JSON config file. If omitted, {search_help}",
    )
    parser = argparse.ArgumentParser(
        prog="reaper-ticker",
        description="Terminal RSS/Atom live ticker with a branded curses UI.",
        formatter_class=HelpFormatter,
        epilog=(
            "Examples:\n"
            "  reaper-ticker --dump-default-config > config.json\n"
            "  reaper-ticker --validate-config --config config.json\n"
            "  reaper-ticker --theme matrix --refresh-interval 120 --config config.json\n"
            "  reaper-ticker config show --resolved --config config.json\n"
            "  reaper-ticker theme show amber\n\n"
            f"Theme presets: {theme_list}\n"
            "Precedence: built-in defaults < config file < top-level run flags.\n"
            "Controls in the UI: q quit, ? help, p pause, r refresh, Enter/o open, arrows or j/k move, PgUp/PgDn jump, n live."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=f"Path to JSON config file. If omitted, {search_help}",
    )
    parser.add_argument(
        "--validate-config",
        action="store_true",
        help="Validate the effective config and exit without starting the TUI.",
    )
    parser.add_argument(
        "--dump-default-config",
        action="store_true",
        help="Print a starter JSON config with feeds, display settings, and theme fields.",
    )
    parser.add_argument(
        "--theme",
        choices=tuple(THEME_PRESETS.keys()),
        help="Override the theme preset for this run.",
    )
    parser.add_argument("--header-title", help="Override the branded header title for this run.")
    parser.add_argument("--header-tagline", help="Override the branded header tagline for this run.")
    parser.add_argument("--no-color", action="store_true", help="Disable color output for this run.")
    parser.add_argument("--no-splash", action="store_true", help="Skip the startup splash screen for this run.")
    parser.add_argument(
        "--refresh-interval",
        type=int,
        metavar="SECONDS",
        help="Override the feed refresh interval in seconds.",
    )
    parser.add_argument(
        "--scroll-speed",
        type=float,
        metavar="LINES_PER_SECOND",
        help="Override the auto-scroll speed.",
    )
    parser.add_argument("--max-items", type=int, metavar="N", help="Override the retained item limit.")
    parser.add_argument(
        "--density",
        choices=("compact", "comfortable"),
        help="Override the feed layout density.",
    )
    parser.add_argument(
        "--ordering",
        choices=("newest_first", "oldest_first"),
        help="Override item ordering.",
    )
    parser.add_argument(
        "--include-keyword",
        action="append",
        default=[],
        metavar="TEXT",
        help="Append an include keyword filter for this run. Repeatable.",
    )
    parser.add_argument(
        "--exclude-keyword",
        action="append",
        default=[],
        metavar="TEXT",
        help="Append an exclude keyword filter for this run. Repeatable.",
    )
    parser.add_argument(
        "--include-source",
        action="append",
        default=[],
        metavar="NAME",
        help="Append an include source filter for this run. Repeatable.",
    )
    parser.add_argument(
        "--exclude-source",
        action="append",
        default=[],
        metavar="NAME",
        help="Append an exclude source filter for this run. Repeatable.",
    )
    parser.add_argument(
        "--disable-open-links",
        action="store_true",
        help="Disable opening article links from the TUI for this run.",
    )
    parser.add_argument(
        "--feed",
        action="append",
        default=[],
        metavar="URL",
        help="Append an ad hoc feed URL for this run. Repeatable.",
    )
    parser.add_argument(
        "--feed-file",
        action="append",
        default=[],
        metavar="PATH",
        help="Append feed URLs from a plain text file, one URL per line. Repeatable.",
    )

    subparsers = parser.add_subparsers(dest="command")

    config_parser = subparsers.add_parser("config", help="Manage config files.", formatter_class=HelpFormatter)
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    config_subparsers.add_parser(
        "path",
        help="Print the resolved config path.",
        parents=[config_parent],
        formatter_class=HelpFormatter,
    )
    config_init_parser = config_subparsers.add_parser(
        "init",
        help="Write or print a starter config.",
        parents=[config_parent],
        formatter_class=HelpFormatter,
    )
    config_init_parser.add_argument("--force", action="store_true", help="Overwrite an existing config file.")
    config_init_parser.add_argument("--stdout", action="store_true", help="Print the starter config instead of writing it.")
    config_show_parser = config_subparsers.add_parser(
        "show",
        help="Print the raw or resolved config.",
        parents=[config_parent],
        formatter_class=HelpFormatter,
    )
    config_show_parser.add_argument(
        "--resolved",
        action="store_true",
        help="Print the fully resolved config with defaults and expanded theme palette.",
    )

    theme_parser = subparsers.add_parser("theme", help="Inspect built-in themes.", formatter_class=HelpFormatter)
    theme_subparsers = theme_parser.add_subparsers(dest="theme_command", required=True)
    theme_subparsers.add_parser("list", help="List available theme presets.", formatter_class=HelpFormatter)
    theme_show_parser = theme_subparsers.add_parser(
        "show",
        help="Show details for a theme preset.",
        formatter_class=HelpFormatter,
    )
    theme_show_parser.add_argument("preset", choices=tuple(THEME_PRESETS.keys()), help="Preset name.")

    feed_parser = subparsers.add_parser("feed", help="Inspect configured feeds.", formatter_class=HelpFormatter)
    feed_subparsers = feed_parser.add_subparsers(dest="feed_command", required=True)
    feed_subparsers.add_parser(
        "list",
        help="List feeds from the loaded config.",
        parents=[config_parent],
        formatter_class=HelpFormatter,
    )

    subparsers.add_parser(
        "doctor",
        help="Check config and terminal compatibility.",
        parents=[config_parent],
        formatter_class=HelpFormatter,
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.dump_default_config:
        sys.stdout.write(dump_default_config())
        return 0

    if args.command is not None:
        return dispatch_command(args, parser)

    config = load_effective_config(args, parser)
    if args.validate_config:
        sys.stdout.write("Config OK\n")
        return 0

    app = TickerApp(config)
    return app.run()


def dispatch_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.command == "config":
        return handle_config_command(args, parser)
    if args.command == "theme":
        return handle_theme_command(args)
    if args.command == "feed":
        return handle_feed_command(args, parser)
    if args.command == "doctor":
        return handle_doctor_command(args, parser)
    parser.exit(status=2, message=f"error: unknown command {args.command}\n")
    return 2


def handle_config_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    target = resolved_or_default_config_path(getattr(args, "config", None))
    if args.config_command == "path":
        sys.stdout.write(f"{target}\n")
        return 0
    if args.config_command == "init":
        target = explicit_or_default_config_path(getattr(args, "config", None))
        content = dump_default_config()
        if args.stdout:
            sys.stdout.write(content)
            return 0
        if target.exists() and not args.force:
            parser.exit(status=2, message=f"error: config file already exists at {target}. Use --force to overwrite.\n")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        sys.stdout.write(f"Wrote starter config to {target}\n")
        return 0
    if args.config_command == "show":
        if args.resolved:
            config = load_config_or_exit(target, parser)
            sys.stdout.write(dump_resolved_config(config))
            return 0
        if not target.exists():
            parser.exit(status=2, message=f"error: config file not found at {target}\n")
        raw_text = target.read_text(encoding="utf-8")
        sys.stdout.write(raw_text)
        if not raw_text.endswith("\n"):
            sys.stdout.write("\n")
        return 0
    parser.exit(status=2, message="error: unsupported config command\n")
    return 2


def handle_theme_command(args: argparse.Namespace) -> int:
    if args.theme_command == "list":
        for preset, description in THEME_DESCRIPTIONS.items():
            sys.stdout.write(f"{preset:10} {description}\n")
        return 0
    if args.theme_command == "show":
        preset = args.preset
        chrome = get_theme_chrome(preset)
        palette = THEME_PRESETS[preset]
        payload = {
            "preset": preset,
            "description": THEME_DESCRIPTIONS[preset],
            "palette": palette,
            "chrome": {
                "title_left": chrome.title_left,
                "title_right": chrome.title_right,
                "rule_pattern": chrome.rule_pattern,
                "selected_prefix": chrome.selected_prefix,
                "unselected_prefix": chrome.unselected_prefix,
                "divider_pattern": chrome.divider_pattern,
                "splash_footer": chrome.splash_footer,
            },
        }
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return 0
    return 2


def handle_feed_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    config = load_config_or_exit(getattr(args, "config", None), parser)
    if args.feed_command == "list":
        for index, feed in enumerate(config.feeds, start=1):
            state = "enabled" if feed.enabled else "disabled"
            sys.stdout.write(f"{index:02d}. [{state}] {feed.name} <{feed.url}>\n")
        return 0
    return 2


def handle_doctor_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    config_path = resolved_or_default_config_path(getattr(args, "config", None))
    issues = 0
    warnings = 0

    sys.stdout.write("Doctor Report\n")
    sys.stdout.write(f"Config path: {config_path}\n")
    try:
        load_config(config_path)
    except ConfigError as exc:
        issues += 1
        sys.stdout.write(f"Config: ERROR ({exc})\n")
    else:
        sys.stdout.write("Config: OK\n")

    term = os.environ.get("TERM")
    if term:
        sys.stdout.write(f"TERM: {term}\n")
    else:
        warnings += 1
        sys.stdout.write("TERM: missing\n")

    stdout_tty = sys.stdout.isatty()
    sys.stdout.write(f"stdout isatty: {'yes' if stdout_tty else 'no'}\n")
    if not stdout_tty:
        warnings += 1

    color_result = detect_color_support()
    sys.stdout.write(f"Color support: {color_result}\n")
    if color_result.startswith("unavailable"):
        warnings += 1

    try:
        browser = webbrowser.get()
    except webbrowser.Error as exc:
        warnings += 1
        sys.stdout.write(f"Browser: unavailable ({exc})\n")
    else:
        sys.stdout.write(f"Browser: OK ({browser.name})\n")

    if issues:
        sys.stdout.write(f"Summary: {issues} error(s), {warnings} warning(s)\n")
        return 1
    sys.stdout.write(f"Summary: 0 error(s), {warnings} warning(s)\n")
    return 0


def detect_color_support() -> str:
    try:
        curses.setupterm()
        colors = curses.tigetnum("colors")
    except Exception as exc:  # pragma: no cover - platform-specific
        return f"unavailable ({exc})"
    if colors is None or colors < 0:
        return "unavailable (terminal reports no color support)"
    return f"{colors} colors"


def explicit_or_default_config_path(path: Path | None) -> Path:
    return path if path is not None else default_config_path()


def resolved_or_default_config_path(path: Path | None) -> Path:
    if path is not None:
        return path
    discovered = discover_config_path()
    return discovered if discovered is not None else default_config_path()


def load_config_or_exit(path: Path | None, parser: argparse.ArgumentParser) -> AppConfig:
    try:
        return load_config(path)
    except ConfigError as exc:
        parser.exit(status=2, message=f"error: {exc}\n")
    raise AssertionError("unreachable")


def load_effective_config(args: argparse.Namespace, parser: argparse.ArgumentParser) -> AppConfig:
    config = load_config_or_exit(args.config, parser)
    try:
        return apply_runtime_overrides(config, args)
    except ConfigError as exc:
        parser.exit(status=2, message=f"error: {exc}\n")
    raise AssertionError("unreachable")


def apply_runtime_overrides(config: AppConfig, args: argparse.Namespace) -> AppConfig:
    display = replace(config.display)
    behavior = replace(config.behavior)
    filters = replace(config.filters)
    theme = replace(config.theme, palette=replace(config.theme.palette))
    feeds = list(config.feeds)

    if getattr(args, "theme", None):
        theme = replace(
            theme,
            preset=args.theme,
            palette=ThemePalette(**THEME_PRESETS[args.theme]),
        )
    if getattr(args, "header_title", None):
        theme = replace(theme, header_title=args.header_title)
    if getattr(args, "header_tagline", None):
        theme = replace(theme, header_tagline=args.header_tagline)
    if getattr(args, "no_color", False):
        theme = replace(theme, enable_color=False)
    if getattr(args, "no_splash", False):
        theme = replace(theme, splash_enabled=False)

    if getattr(args, "refresh_interval", None) is not None:
        if args.refresh_interval < 30:
            raise ConfigError("'--refresh-interval' must be >= 30.")
        display = replace(display, refresh_interval_seconds=args.refresh_interval)
    if getattr(args, "scroll_speed", None) is not None:
        if args.scroll_speed < 0:
            raise ConfigError("'--scroll-speed' must be >= 0.")
        display = replace(display, scroll_speed_lines_per_second=args.scroll_speed)
    if getattr(args, "max_items", None) is not None:
        if args.max_items < 10:
            raise ConfigError("'--max-items' must be >= 10.")
        display = replace(display, max_items=args.max_items)
    if getattr(args, "density", None):
        display = replace(display, density=args.density)
    if getattr(args, "ordering", None):
        display = replace(display, ordering=args.ordering)

    if getattr(args, "disable_open_links", False):
        behavior = replace(behavior, open_links=False)

    include_keywords = list(filters.include_keywords) + list(getattr(args, "include_keyword", []))
    exclude_keywords = list(filters.exclude_keywords) + list(getattr(args, "exclude_keyword", []))
    include_sources = list(filters.include_sources) + list(getattr(args, "include_source", []))
    exclude_sources = list(filters.exclude_sources) + list(getattr(args, "exclude_source", []))
    filters = replace(
        filters,
        include_keywords=tuple(include_keywords),
        exclude_keywords=tuple(exclude_keywords),
        include_sources=tuple(include_sources),
        exclude_sources=tuple(exclude_sources),
    )

    for url in getattr(args, "feed", []):
        feeds.append(make_adhoc_feed(url, len(feeds) + 1))
    for file_path in getattr(args, "feed_file", []):
        feeds.extend(load_feed_file(Path(file_path), len(feeds) + 1))

    if behavior.dedupe_window < display.max_items:
        behavior = replace(behavior, dedupe_window=display.max_items)

    return AppConfig(
        feeds=tuple(feeds),
        filters=filters,
        display=display,
        behavior=behavior,
        theme=theme,
    )


def make_adhoc_feed(url: str, index: int) -> FeedDefinition:
    parsed = urlparse(url)
    name = parsed.netloc or f"ad-hoc-{index}"
    return FeedDefinition(name=name, url=url.strip())


def load_feed_file(path: Path, start_index: int) -> list[FeedDefinition]:
    if not path.exists():
        raise ConfigError(f"feed file not found at {path}")
    feeds: list[FeedDefinition] = []
    current_index = start_index
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        feeds.append(make_adhoc_feed(line, current_index))
        current_index += 1
    return feeds


def format_config_search_help() -> str:
    candidates = config_search_paths()
    return f"search {candidates[0]} first, then {candidates[1]}"
