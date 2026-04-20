from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


OrderingMode = Literal["newest_first", "oldest_first"]
DensityMode = Literal["compact", "comfortable"]
ColorName = Literal["default", "black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]


@dataclass(slots=True)
class FeedDefinition:
    name: str
    url: str
    enabled: bool = True
    tags: tuple[str, ...] = ()


@dataclass(slots=True)
class FiltersConfig:
    include_keywords: tuple[str, ...] = ()
    exclude_keywords: tuple[str, ...] = ()
    include_sources: tuple[str, ...] = ()
    exclude_sources: tuple[str, ...] = ()


@dataclass(slots=True)
class DisplayConfig:
    scroll_speed_lines_per_second: float = 2.5
    refresh_interval_seconds: int = 300
    max_items: int = 200
    density: DensityMode = "comfortable"
    ordering: OrderingMode = "newest_first"


@dataclass(slots=True)
class BehaviorConfig:
    open_links: bool = True
    dedupe_window: int = 1000
    preview_length: int = 280
    request_timeout_seconds: float = 10.0


@dataclass(slots=True)
class ThemePalette:
    header_fg: ColorName = "black"
    header_bg: ColorName = "cyan"
    accent: ColorName = "cyan"
    meta: ColorName = "blue"
    selected: ColorName = "yellow"
    status_fg: ColorName = "black"
    status_bg: ColorName = "white"
    error: ColorName = "red"
    splash: ColorName = "cyan"


@dataclass(slots=True)
class ThemeConfig:
    enable_color: bool = True
    splash_enabled: bool = True
    preset: str = "default"
    header_title: str = "REAPER TICKER"
    header_tagline: str = "LIVE RSS WIREFEED"
    palette: ThemePalette = field(default_factory=ThemePalette)


@dataclass(slots=True)
class AppConfig:
    feeds: tuple[FeedDefinition, ...]
    filters: FiltersConfig = field(default_factory=FiltersConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)
    theme: ThemeConfig = field(default_factory=ThemeConfig)


@dataclass(slots=True)
class NewsEntry:
    entry_id: str
    title: str
    source: str
    published_at: datetime | None
    preview: str
    link: str
    feed_url: str

    def __post_init__(self) -> None:
        if self.published_at is None:
            return
        if self.published_at.tzinfo is None:
            self.published_at = self.published_at.replace(tzinfo=timezone.utc)
        else:
            self.published_at = self.published_at.astimezone(timezone.utc)
