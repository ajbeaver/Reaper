from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reaper_ticker.models import (
    AppConfig,
    BehaviorConfig,
    DisplayConfig,
    FeedDefinition,
    FiltersConfig,
    ThemeConfig,
    ThemePalette,
)

APP_NAME = "reaper-ticker"


DEFAULT_CONFIG_DATA: dict[str, Any] = {
    "feeds": [
        {
            "name": "HN Frontpage",
            "url": "https://hnrss.org/frontpage",
            "enabled": True,
            "tags": ["tech"],
        },
        {
            "name": "BBC World",
            "url": "http://feeds.bbci.co.uk/news/world/rss.xml",
            "enabled": True,
            "tags": ["world"],
        },
        {
            "name": "NPR News",
            "url": "https://feeds.npr.org/1001/rss.xml",
            "enabled": True,
            "tags": ["us", "world"],
        },
        {
            "name": "Ars Technica",
            "url": "https://feeds.arstechnica.com/arstechnica/index",
            "enabled": True,
            "tags": ["tech"],
        },
        {
            "name": "Engadget",
            "url": "https://www.engadget.com/rss.xml",
            "enabled": True,
            "tags": ["tech"],
        },
        {
            "name": "HN Newest",
            "url": "https://hnrss.org/newest",
            "enabled": True,
            "tags": ["tech"],
        },
    ],
    "filters": {
        "include_keywords": [],
        "exclude_keywords": [],
        "include_sources": [],
        "exclude_sources": [],
    },
    "display": {
        "scroll_speed_lines_per_second": 2.5,
        "refresh_interval_seconds": 300,
        "max_items": 200,
        "density": "comfortable",
        "ordering": "newest_first",
    },
    "behavior": {
        "open_links": True,
        "dedupe_window": 1000,
        "preview_length": 280,
        "request_timeout_seconds": 10.0,
    },
    "theme": {
        "enable_color": True,
        "splash_enabled": True,
        "preset": "default",
        "header_title": "REAPER TICKER",
        "header_tagline": "LIVE RSS WIREFEED",
        "palette": {},
    },
}

COLOR_CHOICES = (
    "default",
    "black",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "white",
)

THEME_PRESETS: dict[str, dict[str, str]] = {
    "default": {
        "header_fg": "black",
        "header_bg": "cyan",
        "accent": "cyan",
        "meta": "blue",
        "selected": "yellow",
        "status_fg": "black",
        "status_bg": "white",
        "error": "red",
        "splash": "cyan",
    },
    "amber": {
        "header_fg": "black",
        "header_bg": "yellow",
        "accent": "yellow",
        "meta": "magenta",
        "selected": "red",
        "status_fg": "black",
        "status_bg": "yellow",
        "error": "red",
        "splash": "yellow",
    },
    "matrix": {
        "header_fg": "black",
        "header_bg": "green",
        "accent": "green",
        "meta": "white",
        "selected": "yellow",
        "status_fg": "black",
        "status_bg": "green",
        "error": "red",
        "splash": "green",
    },
    "ice": {
        "header_fg": "white",
        "header_bg": "blue",
        "accent": "cyan",
        "meta": "white",
        "selected": "yellow",
        "status_fg": "white",
        "status_bg": "blue",
        "error": "red",
        "splash": "cyan",
    },
    "newspaper": {
        "header_fg": "black",
        "header_bg": "white",
        "accent": "black",
        "meta": "blue",
        "selected": "magenta",
        "status_fg": "black",
        "status_bg": "white",
        "error": "red",
        "splash": "black",
    },
}

THEME_DESCRIPTIONS: dict[str, str] = {
    "default": "Clean cyan wirefeed with neutral chrome.",
    "amber": "Warm bulletin-board look with loud separators.",
    "matrix": "Green-on-black signal room with coded chrome.",
    "ice": "Cold blue desk with crisp dividers.",
    "newspaper": "High-contrast print layout with editorial markers.",
}


class ConfigError(ValueError):
    """Raised when the config file is invalid."""


def dump_default_config() -> str:
    return json.dumps(DEFAULT_CONFIG_DATA, indent=2) + "\n"


def dump_resolved_config(config: AppConfig) -> str:
    return json.dumps(serialize_config(config), indent=2) + "\n"


def serialize_config(config: AppConfig) -> dict[str, Any]:
    return {
        "feeds": [
            {
                "name": feed.name,
                "url": feed.url,
                "enabled": feed.enabled,
                "tags": list(feed.tags),
            }
            for feed in config.feeds
        ],
        "filters": {
            "include_keywords": list(config.filters.include_keywords),
            "exclude_keywords": list(config.filters.exclude_keywords),
            "include_sources": list(config.filters.include_sources),
            "exclude_sources": list(config.filters.exclude_sources),
        },
        "display": {
            "scroll_speed_lines_per_second": config.display.scroll_speed_lines_per_second,
            "refresh_interval_seconds": config.display.refresh_interval_seconds,
            "max_items": config.display.max_items,
            "density": config.display.density,
            "ordering": config.display.ordering,
        },
        "behavior": {
            "open_links": config.behavior.open_links,
            "dedupe_window": config.behavior.dedupe_window,
            "preview_length": config.behavior.preview_length,
            "request_timeout_seconds": config.behavior.request_timeout_seconds,
        },
        "theme": {
            "enable_color": config.theme.enable_color,
            "splash_enabled": config.theme.splash_enabled,
            "preset": config.theme.preset,
            "header_title": config.theme.header_title,
            "header_tagline": config.theme.header_tagline,
            "palette": {
                "header_fg": config.theme.palette.header_fg,
                "header_bg": config.theme.palette.header_bg,
                "accent": config.theme.palette.accent,
                "meta": config.theme.palette.meta,
                "selected": config.theme.palette.selected,
                "status_fg": config.theme.palette.status_fg,
                "status_bg": config.theme.palette.status_bg,
                "error": config.theme.palette.error,
                "splash": config.theme.palette.splash,
            },
        },
    }


def default_config_path() -> Path:
    return Path.home() / ".reaper" / "config.json"


def config_search_paths(cwd: Path | None = None) -> tuple[Path, ...]:
    base_cwd = cwd if cwd is not None else Path.cwd()
    return (
        default_config_path(),
        base_cwd / "config.json",
    )


def discover_config_path(cwd: Path | None = None) -> Path | None:
    for candidate in config_search_paths(cwd):
        if candidate.exists():
            return candidate
    return None


def load_config(path: Path | None = None) -> AppConfig:
    if path is not None:
        config_path = path
    else:
        config_path = discover_config_path()
        if config_path is None:
            searched = ", ".join(str(candidate) for candidate in config_search_paths())
            raise ConfigError(
                "Config file not found. "
                f"Searched: {searched}. "
                "Use --dump-default-config to generate a starter config."
            )
    if not config_path.exists():
        raise ConfigError(
            f"Config file not found at {config_path}. "
            "Use --dump-default-config to generate a starter config."
        )
    try:
        raw_data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Failed to parse JSON config: {exc}") from exc
    return parse_config(raw_data)


def parse_config(data: dict[str, Any]) -> AppConfig:
    feeds_data = data.get("feeds")
    if not isinstance(feeds_data, list) or not feeds_data:
        raise ConfigError("'feeds' must be a non-empty array.")

    feeds: list[FeedDefinition] = []
    for index, item in enumerate(feeds_data):
        if not isinstance(item, dict):
            raise ConfigError(f"'feeds[{index}]' must be an object.")
        name = _require_str(item, "name", context=f"feeds[{index}]")
        url = _require_str(item, "url", context=f"feeds[{index}]")
        enabled = _optional_bool(item.get("enabled"), default=True, context=f"feeds[{index}].enabled")
        tags = _optional_str_list(item.get("tags"), context=f"feeds[{index}].tags")
        feeds.append(FeedDefinition(name=name, url=url, enabled=enabled, tags=tuple(tags)))

    filters_section = _require_dict(data.get("filters", {}), "filters")
    display_section = _require_dict(data.get("display", {}), "display")
    behavior_section = _require_dict(data.get("behavior", {}), "behavior")
    theme_section = _require_dict(data.get("theme", {}), "theme")

    filters = FiltersConfig(
        include_keywords=tuple(_optional_str_list(filters_section.get("include_keywords"), "filters.include_keywords")),
        exclude_keywords=tuple(_optional_str_list(filters_section.get("exclude_keywords"), "filters.exclude_keywords")),
        include_sources=tuple(_optional_str_list(filters_section.get("include_sources"), "filters.include_sources")),
        exclude_sources=tuple(_optional_str_list(filters_section.get("exclude_sources"), "filters.exclude_sources")),
    )

    density = _optional_choice(
        display_section.get("density"),
        ("compact", "comfortable"),
        default="comfortable",
        context="display.density",
    )
    ordering = _optional_choice(
        display_section.get("ordering"),
        ("newest_first", "oldest_first"),
        default="newest_first",
        context="display.ordering",
    )
    display = DisplayConfig(
        scroll_speed_lines_per_second=_optional_float(
            display_section.get("scroll_speed_lines_per_second"),
            default=2.5,
            minimum=0.0,
            context="display.scroll_speed_lines_per_second",
        ),
        refresh_interval_seconds=_optional_int(
            display_section.get("refresh_interval_seconds"),
            default=300,
            minimum=30,
            context="display.refresh_interval_seconds",
        ),
        max_items=_optional_int(
            display_section.get("max_items"),
            default=200,
            minimum=10,
            context="display.max_items",
        ),
        density=density,  # type: ignore[arg-type]
        ordering=ordering,  # type: ignore[arg-type]
    )

    behavior = BehaviorConfig(
        open_links=_optional_bool(behavior_section.get("open_links"), default=True, context="behavior.open_links"),
        dedupe_window=_optional_int(
            behavior_section.get("dedupe_window"),
            default=max(display.max_items * 4, 1000),
            minimum=display.max_items,
            context="behavior.dedupe_window",
        ),
        preview_length=_optional_int(
            behavior_section.get("preview_length"),
            default=280,
            minimum=40,
            context="behavior.preview_length",
        ),
        request_timeout_seconds=_optional_float(
            behavior_section.get("request_timeout_seconds"),
            default=10.0,
            minimum=1.0,
            context="behavior.request_timeout_seconds",
        ),
    )

    palette_section = _require_dict(theme_section.get("palette", {}), "theme.palette")
    preset = _optional_choice(
        theme_section.get("preset"),
        tuple(THEME_PRESETS.keys()),
        default="default",
        context="theme.preset",
    )
    preset_palette = THEME_PRESETS[preset]
    theme = ThemeConfig(
        enable_color=_optional_bool(theme_section.get("enable_color"), default=True, context="theme.enable_color"),
        splash_enabled=_optional_bool(
            theme_section.get("splash_enabled"),
            default=True,
            context="theme.splash_enabled",
        ),
        preset=preset,
        header_title=_optional_str(
            theme_section.get("header_title"),
            default="REAPER TICKER",
            context="theme.header_title",
        ),
        header_tagline=_optional_str(
            theme_section.get("header_tagline"),
            default="LIVE RSS WIREFEED",
            context="theme.header_tagline",
        ),
        palette=ThemePalette(
            header_fg=_optional_choice(
                palette_section.get("header_fg"),
                COLOR_CHOICES,
                default=preset_palette["header_fg"],
                context="theme.palette.header_fg",
            ),
            header_bg=_optional_choice(
                palette_section.get("header_bg"),
                COLOR_CHOICES,
                default=preset_palette["header_bg"],
                context="theme.palette.header_bg",
            ),
            accent=_optional_choice(
                palette_section.get("accent"),
                COLOR_CHOICES,
                default=preset_palette["accent"],
                context="theme.palette.accent",
            ),
            meta=_optional_choice(
                palette_section.get("meta"),
                COLOR_CHOICES,
                default=preset_palette["meta"],
                context="theme.palette.meta",
            ),
            selected=_optional_choice(
                palette_section.get("selected"),
                COLOR_CHOICES,
                default=preset_palette["selected"],
                context="theme.palette.selected",
            ),
            status_fg=_optional_choice(
                palette_section.get("status_fg"),
                COLOR_CHOICES,
                default=preset_palette["status_fg"],
                context="theme.palette.status_fg",
            ),
            status_bg=_optional_choice(
                palette_section.get("status_bg"),
                COLOR_CHOICES,
                default=preset_palette["status_bg"],
                context="theme.palette.status_bg",
            ),
            error=_optional_choice(
                palette_section.get("error"),
                COLOR_CHOICES,
                default=preset_palette["error"],
                context="theme.palette.error",
            ),
            splash=_optional_choice(
                palette_section.get("splash"),
                COLOR_CHOICES,
                default=preset_palette["splash"],
                context="theme.palette.splash",
            ),
        ),
    )

    return AppConfig(feeds=tuple(feeds), filters=filters, display=display, behavior=behavior, theme=theme)


def _require_dict(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"'{context}' must be an object.")
    return value


def _require_str(container: dict[str, Any], key: str, context: str) -> str:
    value = container.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"'{context}.{key}' must be a non-empty string.")
    return value.strip()


def _optional_str_list(value: Any, context: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ConfigError(f"'{context}' must be an array of strings.")
    return [item.strip() for item in value if item.strip()]


def _optional_bool(value: Any, default: bool, context: str) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ConfigError(f"'{context}' must be a boolean.")
    return value


def _optional_str(value: Any, default: str, context: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"'{context}' must be a non-empty string.")
    return value.strip()


def _optional_int(value: Any, default: int, minimum: int, context: str) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(f"'{context}' must be an integer.")
    if value < minimum:
        raise ConfigError(f"'{context}' must be >= {minimum}.")
    return value


def _optional_float(value: Any, default: float, minimum: float, context: str) -> float:
    if value is None:
        return default
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ConfigError(f"'{context}' must be a number.")
    if float(value) < minimum:
        raise ConfigError(f"'{context}' must be >= {minimum}.")
    return float(value)


def _optional_choice(
    value: Any,
    choices: tuple[str, ...],
    default: str,
    context: str,
) -> str:
    if value is None:
        return default
    if not isinstance(value, str) or value not in choices:
        choice_list = ", ".join(choices)
        raise ConfigError(f"'{context}' must be one of: {choice_list}.")
    return value
