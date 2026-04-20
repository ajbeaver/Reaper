from __future__ import annotations

import curses
import textwrap
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources

from reaper_ticker.config import AppConfig
from reaper_ticker.feeds import FeedFetcher
from reaper_ticker.models import NewsEntry
from reaper_ticker.state import FeedStore

SPLASH_DURATION_SECONDS = 1.2
HEADER_HEIGHT = 3

COLOR_NAME_TO_CURSES = {
    "default": -1,
    "black": curses.COLOR_BLACK,
    "red": curses.COLOR_RED,
    "green": curses.COLOR_GREEN,
    "yellow": curses.COLOR_YELLOW,
    "blue": curses.COLOR_BLUE,
    "magenta": curses.COLOR_MAGENTA,
    "cyan": curses.COLOR_CYAN,
    "white": curses.COLOR_WHITE,
}


@dataclass(slots=True)
class StyledLine:
    text: str
    style: str
    entry_index: int | None = None


@dataclass(frozen=True, slots=True)
class ThemeChrome:
    title_left: str
    title_right: str
    rule_pattern: str
    selected_prefix: str
    unselected_prefix: str
    divider_pattern: str
    splash_frames: tuple[str, ...]
    splash_footer: str


@dataclass(slots=True)
class RenderState:
    lines: list[StyledLine]
    content_height: int


class TickerApp:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.store = FeedStore(config)
        self.fetcher = FeedFetcher(timeout_seconds=config.behavior.request_timeout_seconds)
        self.paused = False
        self.selected_index = 0
        self.manual_selection = False
        self.scroll_offset = 0.0
        self.last_tick = time.monotonic()
        self.last_refresh_wallclock: datetime | None = None
        self.last_error = ""
        self.status_message = "Starting..."
        self.styles: dict[str, int] = self._base_styles()
        self.last_render_state = RenderState(lines=[], content_height=1)
        self.last_cols = 80
        self.show_help_overlay = False
        self.is_refreshing = False

    def run(self) -> int:
        return curses.wrapper(self._main)

    def _main(self, stdscr: curses.window) -> int:
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        self.styles = self._init_styles()
        stdscr.nodelay(True)
        stdscr.timeout(100)
        if self._show_splash(stdscr) == "quit":
            return 0
        self._refresh_feeds()
        next_refresh = time.monotonic() + self.config.display.refresh_interval_seconds

        while True:
            now = time.monotonic()
            if now >= next_refresh:
                self._refresh_feeds()
                next_refresh = now + self.config.display.refresh_interval_seconds

            rows, cols = stdscr.getmaxyx()
            self.last_cols = cols
            self._advance_scroll(now, rows - 1, cols)
            render_state = self._render(stdscr, next_refresh)
            active_index = self._resolve_active_index(render_state)
            if active_index is not None and not self.manual_selection:
                self.selected_index = max(0, min(active_index, len(self.store.entries) - 1))

            key = stdscr.getch()
            if key != -1:
                outcome = self._handle_key(key)
                if outcome == "quit":
                    return 0
                if outcome == "refresh":
                    self._refresh_feeds()
                    next_refresh = time.monotonic() + self.config.display.refresh_interval_seconds

    def _show_splash(self, stdscr: curses.window) -> str | None:
        if not self.config.theme.splash_enabled:
            return None
        art_lines = load_splash_art()
        if not art_lines:
            return None
        chrome = get_theme_chrome(self.config.theme.preset)
        frames = chrome.splash_frames
        started_at = time.monotonic()
        frame_index = 0

        while time.monotonic() - started_at < SPLASH_DURATION_SECONDS:
            stdscr.erase()
            rows, cols = stdscr.getmaxyx()
            title_y = max(1, (rows - len(art_lines)) // 2 - 3)
            self._draw_centered(stdscr, title_y, cols, self.config.theme.header_title, self.styles["splash_title"])
            self._draw_centered(
                stdscr,
                title_y + 1,
                cols,
                self.config.theme.header_tagline,
                self.styles["splash_loading"],
            )
            self._draw_centered_block(stdscr, title_y + 3, cols, art_lines, self.styles["splash_art"])
            footer_y = min(rows - 2, title_y + len(art_lines) + 3)
            self._draw_centered(stdscr, footer_y, cols, frames[frame_index % len(frames)], self.styles["splash_loading"])
            self._draw_centered(
                stdscr,
                min(rows - 1, footer_y + 1),
                cols,
                chrome.splash_footer,
                self.styles["meta"],
            )
            stdscr.refresh()

            key = stdscr.getch()
            if key in {ord("q"), ord("Q")}:
                return "quit"

            time.sleep(0.1)
            frame_index += 1
        return None

    def _draw_centered(self, stdscr: curses.window, row: int, cols: int, text: str, attr: int = 0) -> None:
        if row < 0:
            return
        col = max(0, (cols - len(text)) // 2)
        try:
            stdscr.addnstr(row, col, text, max(0, cols - col), attr)
        except curses.error:
            pass

    def _draw_centered_block(
        self,
        stdscr: curses.window,
        start_row: int,
        cols: int,
        lines: list[str],
        attr: int = 0,
    ) -> None:
        for offset, line in enumerate(lines):
            row = start_row + offset
            if row < 0:
                continue
            col = max(0, (cols - len(line)) // 2)
            try:
                stdscr.addnstr(row, col, line, max(0, cols - col), attr)
            except curses.error:
                pass

    def _advance_scroll(self, now: float, usable_height: int, cols: int) -> None:
        delta = max(0.0, now - self.last_tick)
        self.last_tick = now
        if self.paused or usable_height <= 0:
            return
        render_state = self._build_render_lines(max(usable_height, 1), cols)
        if len(render_state.lines) <= usable_height:
            self.scroll_offset = 0.0
            return
        self.scroll_offset += self.config.display.scroll_speed_lines_per_second * delta
        max_offset = max(0, len(render_state.lines) - usable_height)
        if self.scroll_offset > max_offset:
            self.scroll_offset = 0.0

    def _refresh_feeds(self) -> None:
        self.is_refreshing = True
        self.status_message = "refreshing feeds"
        try:
            result = self.fetcher.fetch_all(self.config.feeds)
            added = self.store.ingest(result.entries)
            self.last_refresh_wallclock = datetime.now(timezone.utc)
            if result.errors:
                self.last_error = result.errors[-1]
            else:
                self.last_error = ""
            self.status_message = f"refresh complete, {added} new item(s)"
        finally:
            self.is_refreshing = False

    def _handle_key(self, key: int) -> str | None:
        if self.show_help_overlay:
            if key in {ord("?"), ord("q"), ord("Q"), 27}:
                self.show_help_overlay = False
            return None
        if key == ord("?"):
            self.show_help_overlay = True
            return None
        if key in {ord("q"), ord("Q")}:
            return "quit"
        if key in {ord("p"), ord("P"), ord(" ")}:
            self.paused = not self.paused
            if not self.paused:
                self.manual_selection = False
                self.status_message = "resumed live scroll"
            else:
                self.status_message = "paused auto-scroll"
            return None
        if key in {curses.KEY_UP, ord("k"), ord("K")}:
            self._move_selection(-1)
            return None
        if key in {curses.KEY_DOWN, ord("j"), ord("J")}:
            self._move_selection(1)
            return None
        if key == curses.KEY_PPAGE:
            self._page_selection(-1, fraction=1.0)
            return None
        if key == curses.KEY_NPAGE:
            self._page_selection(1, fraction=1.0)
            return None
        if key in {ord("u"), ord("U")}:
            self._page_selection(-1, fraction=0.5)
            return None
        if key in {ord("d"), ord("D")}:
            self._page_selection(1, fraction=0.5)
            return None
        if key == ord("g"):
            self._jump_to_index(0)
            return None
        if key == ord("G"):
            self._jump_to_index(max(0, len(self.store.entries) - 1))
            return None
        if key in {ord("n"), ord("N")}:
            self._return_to_live()
            return None
        if key in {ord("r"), ord("R")}:
            return "refresh"
        if key in {ord("o"), ord("O"), curses.KEY_ENTER, 10, 13} and self.config.behavior.open_links:
            self._open_selected_link()
            return None
        return None

    def _open_selected_link(self) -> None:
        if not self.store.entries:
            self.status_message = "no items to open"
            return
        entry = self.store.entries[self.selected_index]
        if not entry.link:
            self.status_message = "selected item has no link"
            return
        opened = webbrowser.open(entry.link, new=2, autoraise=False)
        self.status_message = "opened link" if opened else "failed to open link"

    def _render(self, stdscr: curses.window, next_refresh: float) -> RenderState:
        stdscr.erase()
        rows, cols = stdscr.getmaxyx()
        self._render_header(stdscr, cols)
        content_height = max(1, rows - HEADER_HEIGHT - 1)
        render_state = self._build_render_lines(content_height, cols)
        start_line = min(int(self.scroll_offset), max(0, len(render_state.lines) - content_height))
        visible_lines = render_state.lines[start_line : start_line + content_height]

        for row, styled_line in enumerate(visible_lines, start=HEADER_HEIGHT):
            try:
                stdscr.addnstr(
                    row,
                    0,
                    styled_line.text.ljust(cols),
                    cols,
                    self.styles.get(styled_line.style, 0),
                )
            except curses.error:
                pass

        if self.show_help_overlay:
            self._render_help_overlay(stdscr, rows, cols)

        status = self._status_line(next_refresh, cols)
        try:
            status_style = self.styles["error_status"] if self.last_error else self.styles["status"]
            stdscr.addnstr(rows - 1, 0, status.ljust(cols), cols, status_style)
        except curses.error:
            pass
        stdscr.refresh()
        render_state.content_height = content_height
        self.last_render_state = render_state
        return render_state

    def _render_header(self, stdscr: curses.window, cols: int) -> None:
        chrome = get_theme_chrome(self.config.theme.preset)
        header_title = build_header_title(self.config.theme.header_title, self.config.theme.preset)
        tagline = self.config.theme.header_tagline
        info = f"feeds={len([feed for feed in self.config.feeds if feed.enabled])}  order={self.config.display.ordering}  density={self.config.display.density}"
        controls = "q quit  ? help  r refresh  PgUp/PgDn jump  n live"

        try:
            stdscr.addnstr(0, 0, (" " * cols), cols, self.styles["header_fill"])
            self._draw_centered(stdscr, 0, cols, header_title[:cols], self.styles["header_title"])
            stdscr.addnstr(1, 0, truncate_line(f" {tagline}  |  {info}", cols).ljust(cols), cols, self.styles["header_tagline"])
            rule = build_header_rule(cols, self.config.theme.preset)
            stdscr.addnstr(2, 0, rule, cols, self.styles["header_rule"])
            if cols > len(controls) + 2:
                stdscr.addnstr(2, max(0, cols - len(controls) - 1), controls, len(controls), self.styles["header_tagline"])
        except curses.error:
            pass

    def _build_render_lines(self, content_height: int, cols: int) -> RenderState:
        lines: list[StyledLine] = []
        width = max(20, cols - 2)
        density = self.config.display.density
        preview_chars = self.config.behavior.preview_length if density == "comfortable" else min(
            self.config.behavior.preview_length,
            140,
        )
        spacer_lines = 1 if density == "comfortable" else 0

        if not self.store.entries:
            placeholder = "No feed items yet. Waiting for refresh..."
            return RenderState(
                lines=[StyledLine(text=placeholder[:width], style="empty", entry_index=0)],
                content_height=content_height,
            )

        chrome = get_theme_chrome(self.config.theme.preset)
        for index, entry in enumerate(self.store.entries):
            is_selected = index == self.selected_index
            title_prefix = chrome.selected_prefix if is_selected else chrome.unselected_prefix
            title = f"{title_prefix} {entry.title}".strip()
            meta = f"   {entry.source} | {format_timestamp(entry.published_at)}"
            preview = entry.preview[:preview_chars]

            for line in textwrap.wrap(title, width=width) or ["(untitled)"]:
                style = "selected_title" if is_selected else "title"
                lines.append(StyledLine(text=line, style=style, entry_index=index))
            for line in textwrap.wrap(meta, width=width):
                lines.append(StyledLine(text=line, style="meta", entry_index=index))
            if preview:
                wrapped_preview = textwrap.wrap(preview, width=width)
                preview_limit = 3 if density == "comfortable" else 2
                for line in wrapped_preview[:preview_limit]:
                    lines.append(StyledLine(text=line, style="preview", entry_index=index))
            divider = build_divider(width, self.config.theme.preset)
            lines.append(StyledLine(text=divider, style="divider", entry_index=index))
            for _ in range(spacer_lines):
                lines.append(StyledLine(text="", style="preview", entry_index=index))

        return RenderState(lines=lines, content_height=content_height)

    def _resolve_active_index(self, render_state: RenderState) -> int | None:
        if not self.store.entries:
            return None
        line_index = min(int(self.scroll_offset), max(0, len(render_state.lines) - 1))
        return render_state.lines[line_index].entry_index

    def _status_line(self, next_refresh: float, cols: int) -> str:
        remaining = max(0, int(next_refresh - time.monotonic()))
        state = "browse" if self.manual_selection else ("paused" if self.paused else "live")
        last_refresh = format_timestamp(self.last_refresh_wallclock) if self.last_refresh_wallclock else "never"
        parts = [
            f"{state}",
            f"items={len(self.store.entries)}",
            ("refresh=running" if self.is_refreshing else f"refresh_in={remaining}s"),
            f"last={last_refresh}",
            self.status_message,
        ]
        if self.manual_selection and self.store.entries:
            parts.insert(1, f"item={self.selected_index + 1}/{len(self.store.entries)}")
        if self.last_error:
            parts.append(f"error={self.last_error}")
        status = " | ".join(parts)
        return status[:cols]

    def _sync_scroll_to_selection(self) -> None:
        if not self.last_render_state.lines:
            self.last_render_state = self._build_render_lines(self.last_render_state.content_height, self.last_cols)
        self.scroll_offset = adjust_scroll_for_selection(
            self.last_render_state,
            self.selected_index,
            self.scroll_offset,
        )

    def _move_selection(self, delta: int) -> None:
        if not self.store.entries:
            return
        self.paused = True
        self.manual_selection = True
        self.selected_index = clamp_index(self.selected_index + delta, len(self.store.entries))
        self._sync_scroll_to_selection()
        self.status_message = f"browsing item {self.selected_index + 1}"

    def _page_selection(self, direction: int, fraction: float) -> None:
        if not self.store.entries:
            return
        self.paused = True
        self.manual_selection = True
        step = compute_page_step(self.last_render_state, self.scroll_offset, fraction)
        self.selected_index = clamp_index(self.selected_index + (direction * step), len(self.store.entries))
        self._sync_scroll_to_selection()
        self.status_message = f"jumped to item {self.selected_index + 1}"

    def _jump_to_index(self, index: int) -> None:
        if not self.store.entries:
            return
        self.paused = True
        self.manual_selection = True
        self.selected_index = clamp_index(index, len(self.store.entries))
        self._sync_scroll_to_selection()
        self.status_message = f"jumped to item {self.selected_index + 1}"

    def _return_to_live(self) -> None:
        newest_index = get_newest_index(self.config, len(self.store.entries))
        self.selected_index = newest_index
        self.paused = False
        self.manual_selection = False
        self.show_help_overlay = False
        if newest_index == 0:
            self.scroll_offset = 0.0
        else:
            self._sync_scroll_to_selection()
        self.status_message = "returned to live feed"

    def _render_help_overlay(self, stdscr: curses.window, rows: int, cols: int) -> None:
        lines = [
            "Controls",
            "q quit   ? close help   p pause/resume   r refresh now",
            "Up/Down or j/k move item   Enter or o open link",
            "PgUp/PgDn jump one page   u/d jump half page",
            "g top   G bottom   n newest/live",
        ]
        box_width = min(cols - 4, max(len(line) for line in lines) + 4)
        box_height = min(rows - HEADER_HEIGHT - 2, len(lines) + 2)
        if box_width <= 4 or box_height <= 2:
            return
        start_row = HEADER_HEIGHT + max(0, ((rows - HEADER_HEIGHT - 1) - box_height) // 2)
        start_col = max(0, (cols - box_width) // 2)
        body_style = self.styles.get("header_fill", curses.A_REVERSE)
        title_style = self.styles.get("status", curses.A_REVERSE)

        for row in range(box_height):
            try:
                stdscr.addnstr(start_row + row, start_col, " " * box_width, box_width, body_style)
            except curses.error:
                pass

        title = truncate_line(f" {lines[0]} ", box_width - 2)
        try:
            stdscr.addnstr(start_row, start_col + 1, title.ljust(box_width - 2), box_width - 2, title_style)
        except curses.error:
            pass
        for index, line in enumerate(lines[1:], start=1):
            if index >= box_height - 1:
                break
            try:
                stdscr.addnstr(
                    start_row + index,
                    start_col + 2,
                    truncate_line(line, box_width - 4).ljust(box_width - 4),
                    box_width - 4,
                    body_style,
                )
            except curses.error:
                pass

    def _init_styles(self) -> dict[str, int]:
        styles = self._base_styles()
        if not self.config.theme.enable_color:
            return styles
        if not curses.has_colors():
            return styles

        try:
            curses.start_color()
            curses.use_default_colors()
        except curses.error:
            return styles

        palette = self.config.theme.palette
        pairs = [
            ("header_fill", palette.header_fg, palette.header_bg),
            ("header_title", palette.header_fg, palette.header_bg),
            ("header_tagline", palette.header_fg, palette.header_bg),
            ("header_rule", palette.accent, "default"),
            ("title", palette.accent, "default"),
            ("selected_title", palette.selected, "default"),
            ("meta", palette.meta, "default"),
            ("preview", "default", "default"),
            ("divider", palette.accent, "default"),
            ("status", palette.status_fg, palette.status_bg),
            ("error_status", palette.status_fg, palette.error),
            ("splash_title", palette.splash, "default"),
            ("splash_art", palette.splash, "default"),
            ("splash_loading", palette.accent, "default"),
            ("empty", palette.meta, "default"),
        ]
        next_pair = 1
        for style_name, fg_name, bg_name in pairs:
            try:
                curses.init_pair(
                    next_pair,
                    COLOR_NAME_TO_CURSES[fg_name],
                    COLOR_NAME_TO_CURSES[bg_name],
                )
            except curses.error:
                next_pair += 1
                continue
            base_attr = curses.color_pair(next_pair)
            if style_name in {"header_title", "title", "selected_title", "splash_title"}:
                base_attr |= curses.A_BOLD
            if style_name in {"meta", "header_tagline", "empty"}:
                base_attr |= curses.A_DIM
            styles[style_name] = base_attr
            next_pair += 1
        return styles

    def _base_styles(self) -> dict[str, int]:
        return {
            "header_fill": curses.A_REVERSE,
            "header_title": curses.A_BOLD | curses.A_REVERSE,
            "header_tagline": curses.A_REVERSE,
            "header_rule": curses.A_BOLD,
            "title": curses.A_BOLD,
            "selected_title": curses.A_BOLD | curses.A_REVERSE,
            "meta": curses.A_DIM,
            "preview": 0,
            "divider": curses.A_DIM,
            "status": curses.A_REVERSE,
            "error_status": curses.A_BOLD | curses.A_REVERSE,
            "splash_title": curses.A_BOLD,
            "splash_art": 0,
            "splash_loading": curses.A_DIM,
            "empty": curses.A_DIM,
        }


def format_timestamp(value: datetime | None) -> str:
    if value is None:
        return "unknown"
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


def load_splash_art() -> list[str]:
    try:
        art = resources.files("reaper_ticker").joinpath("ascii.txt").read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError):
        return []
    return [line.rstrip("\n") for line in art.splitlines() if line.strip()]


def get_theme_chrome(preset: str) -> ThemeChrome:
    presets = {
        "default": ThemeChrome(
            title_left="[ ",
            title_right=" ]",
            rule_pattern="=+= ",
            selected_prefix=">>",
            unselected_prefix="  ",
            divider_pattern="-",
            splash_frames=("Loading feeds   ", "Loading feeds.  ", "Loading feeds.. ", "Loading feeds..."),
            splash_footer="Press q to quit",
        ),
        "amber": ThemeChrome(
            title_left="< ",
            title_right=" >",
            rule_pattern=":~: ",
            selected_prefix="=>",
            unselected_prefix=" .",
            divider_pattern="=",
            splash_frames=("Warming wires   ", "Warming wires.  ", "Warming wires.. ", "Warming wires..."),
            splash_footer="Press q to cut the line",
        ),
        "matrix": ThemeChrome(
            title_left="[[ ",
            title_right=" ]]",
            rule_pattern="10|",
            selected_prefix="[]",
            unselected_prefix="::",
            divider_pattern=".",
            splash_frames=("Syncing signal   ", "Syncing signal.  ", "Syncing signal.. ", "Syncing signal..."),
            splash_footer="Press q to drop the signal",
        ),
        "ice": ThemeChrome(
            title_left="{ ",
            title_right=" }",
            rule_pattern="*-* ",
            selected_prefix="*>",
            unselected_prefix=" -",
            divider_pattern="~",
            splash_frames=("Cooling feed   ", "Cooling feed.  ", "Cooling feed.. ", "Cooling feed..."),
            splash_footer="Press q to break the ice",
        ),
        "newspaper": ThemeChrome(
            title_left=":: ",
            title_right=" ::",
            rule_pattern="=-",
            selected_prefix="##",
            unselected_prefix="--",
            divider_pattern="_",
            splash_frames=("Rolling edition   ", "Rolling edition.  ", "Rolling edition.. ", "Rolling edition..."),
            splash_footer="Press q to stop the press",
        ),
    }
    return presets.get(preset, presets["default"])


def build_header_rule(cols: int, preset: str = "default") -> str:
    if cols <= 0:
        return ""
    pattern = get_theme_chrome(preset).rule_pattern
    repeated = (pattern * ((cols // len(pattern)) + 1))[:cols]
    return repeated


def truncate_line(text: str, cols: int) -> str:
    if cols <= 0:
        return ""
    if len(text) <= cols:
        return text
    if cols <= 3:
        return text[:cols]
    return text[: cols - 3] + "..."


def build_header_title(text: str, preset: str) -> str:
    chrome = get_theme_chrome(preset)
    return f"{chrome.title_left}{text}{chrome.title_right}"


def build_divider(width: int, preset: str) -> str:
    if width <= 0:
        return ""
    pattern = get_theme_chrome(preset).divider_pattern
    return (pattern * ((width // len(pattern)) + 1))[:width]


def clamp_index(index: int, total_items: int) -> int:
    if total_items <= 0:
        return 0
    return max(0, min(total_items - 1, index))


def count_visible_entries(render_state: RenderState, current_offset: float) -> int:
    if not render_state.lines or render_state.content_height <= 0:
        return 0
    start = max(0, int(current_offset))
    end = start + render_state.content_height
    seen: set[int] = set()
    for line in render_state.lines[start:end]:
        if line.entry_index is not None:
            seen.add(line.entry_index)
    return len(seen)


def compute_page_step(render_state: RenderState, current_offset: float, fraction: float) -> int:
    visible_entries = count_visible_entries(render_state, current_offset)
    if visible_entries <= 1:
        return 1
    if fraction >= 1.0:
        return max(1, visible_entries - 1)
    return max(1, int(visible_entries * fraction))


def get_newest_index(config: AppConfig, total_items: int) -> int:
    if total_items <= 0:
        return 0
    if config.display.ordering == "newest_first":
        return 0
    return total_items - 1


def adjust_scroll_for_selection(render_state: RenderState, selected_index: int, current_offset: float) -> float:
    if not render_state.lines or render_state.content_height <= 0:
        return 0.0

    start_line: int | None = None
    end_line: int | None = None
    for line_number, styled_line in enumerate(render_state.lines):
        if styled_line.entry_index != selected_index:
            continue
        if start_line is None:
            start_line = line_number
        end_line = line_number

    if start_line is None or end_line is None:
        return float(max(0, int(current_offset)))

    current_start = max(0, int(current_offset))
    current_end = current_start + render_state.content_height - 1

    if start_line < current_start:
        return float(start_line)
    if end_line > current_end:
        return float(max(0, end_line - render_state.content_height + 1))
    return float(current_start)
