from __future__ import annotations

import hashlib
import html
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable

from reaper_ticker.models import FeedDefinition, NewsEntry

TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?])")


@dataclass(slots=True)
class FeedFetchResult:
    entries: list[NewsEntry]
    errors: list[str]


@dataclass(slots=True)
class FeedRequestState:
    etag: str | None = None
    last_modified: str | None = None


class FeedFetcher:
    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = timeout_seconds
        self._state_by_url: dict[str, FeedRequestState] = {}

    def fetch_all(self, feeds: Iterable[FeedDefinition]) -> FeedFetchResult:
        entries: list[NewsEntry] = []
        errors: list[str] = []
        for feed in feeds:
            if not feed.enabled:
                continue
            try:
                entries.extend(self.fetch_feed(feed))
            except FeedError as exc:
                errors.append(f"{feed.name}: {exc}")
        return FeedFetchResult(entries=entries, errors=errors)

    def fetch_feed(self, feed: FeedDefinition) -> list[NewsEntry]:
        state = self._state_by_url.setdefault(feed.url, FeedRequestState())
        request = urllib.request.Request(
            feed.url,
            headers={
                "User-Agent": "reaper-ticker/0.1",
                **({"If-None-Match": state.etag} if state.etag else {}),
                **({"If-Modified-Since": state.last_modified} if state.last_modified else {}),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                if response.status == 304:
                    return []
                payload = response.read()
                if not payload:
                    return []
                state.etag = response.headers.get("ETag") or state.etag
                state.last_modified = response.headers.get("Last-Modified") or state.last_modified
        except urllib.error.HTTPError as exc:
            if exc.code == 304:
                return []
            raise FeedError(f"HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise FeedError(f"network error: {exc.reason}") from exc
        except OSError as exc:
            raise FeedError(f"io error: {exc}") from exc
        return parse_feed(payload, feed)


class FeedError(RuntimeError):
    """Raised when a feed request or parse step fails."""


def parse_feed(payload: bytes, feed: FeedDefinition) -> list[NewsEntry]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise FeedError(f"parse error: {exc}") from exc

    tag = _local_name(root.tag)
    if tag == "feed":
        return _parse_atom(root, feed)
    if tag in {"rss", "rdf"}:
        return _parse_rss(root, feed)
    raise FeedError(f"unsupported feed type: {tag}")


def _parse_rss(root: ET.Element, feed: FeedDefinition) -> list[NewsEntry]:
    channel = root.find("./channel")
    item_parent = channel if channel is not None else root
    entries: list[NewsEntry] = []
    for item in item_parent.findall(".//item"):
        title = _text_of(item, "title") or "(untitled)"
        link = _text_of(item, "link") or ""
        preview = _preview_text(_text_of(item, "description") or _text_of(item, "encoded") or "")
        published = _parse_datetime(
            _text_of(item, "pubDate")
            or _text_of(item, "published")
            or _text_of(item, "updated")
        )
        guid = _text_of(item, "guid")
        entry_id = _build_entry_id(feed.url, guid, link, title, published)
        entries.append(
            NewsEntry(
                entry_id=entry_id,
                title=title.strip(),
                source=feed.name,
                published_at=published,
                preview=preview,
                link=link.strip(),
                feed_url=feed.url,
            )
        )
    return entries


def _parse_atom(root: ET.Element, feed: FeedDefinition) -> list[NewsEntry]:
    entries: list[NewsEntry] = []
    for item in root.findall("./{*}entry"):
        title = _text_of(item, "title") or "(untitled)"
        preview = _preview_text(_text_of(item, "summary") or _text_of(item, "content") or "")
        published = _parse_datetime(
            _text_of(item, "published")
            or _text_of(item, "updated")
        )
        entry_id = _text_of(item, "id")
        link = ""
        for link_node in item.findall("./{*}link"):
            rel = link_node.attrib.get("rel", "alternate")
            if rel == "alternate":
                link = link_node.attrib.get("href", "").strip()
                if link:
                    break
        stable_id = _build_entry_id(feed.url, entry_id, link, title, published)
        entries.append(
            NewsEntry(
                entry_id=stable_id,
                title=title.strip(),
                source=feed.name,
                published_at=published,
                preview=preview,
                link=link,
                feed_url=feed.url,
            )
        )
    return entries


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _text_of(node: ET.Element, target_name: str) -> str | None:
    for child in node:
        if _local_name(child.tag) == target_name:
            return "".join(child.itertext()).strip()
    return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        parsed = None
    if parsed is None:
        normalized = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _preview_text(value: str) -> str:
    if not value:
        return ""
    stripped = TAG_RE.sub(" ", html.unescape(value))
    normalized = WHITESPACE_RE.sub(" ", stripped).strip()
    return SPACE_BEFORE_PUNCT_RE.sub(r"\1", normalized)


def _build_entry_id(
    feed_url: str,
    guid: str | None,
    link: str,
    title: str,
    published_at: datetime | None,
) -> str:
    if guid:
        return guid.strip()
    if link:
        return link.strip()
    payload = "|".join(
        [
            feed_url.strip(),
            title.strip(),
            published_at.isoformat() if published_at is not None else "",
        ]
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()
