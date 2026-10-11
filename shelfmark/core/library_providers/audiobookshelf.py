"""Audiobookshelf (ABS) library provider.

Fetches the user's ABS libraries over the REST API (title/author/isbn/asin per item).
ABS library metadata is messy (titles are often raw folder names, author frequently
empty), so each item is tokenized from title + author + folder path.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import requests

from shelfmark.core.config import config as app_config
from shelfmark.core.library_providers import LibraryEntry, setting
from shelfmark.core.text_match import isbn_variants, tokens
from shelfmark.core.utils import normalize_http_url

if TYPE_CHECKING:
    from collections.abc import Mapping

_REQUEST_TIMEOUT = 15
_ITEMS_PAGE_LIMIT = 500


def _config(overrides: Mapping[str, Any] | None = None) -> tuple[bool, str, str, list[str]]:
    enabled = bool(setting(app_config, "LIBRARY_CHECK_ENABLED", False, overrides))
    url = normalize_http_url(str(setting(app_config, "AUDIOBOOKSHELF_URL", "", overrides) or ""))
    token = str(setting(app_config, "AUDIOBOOKSHELF_TOKEN", "", overrides) or "").strip()
    lib_ids_raw = str(setting(app_config, "AUDIOBOOKSHELF_LIBRARY_IDS", "", overrides) or "")
    lib_ids = [s.strip() for s in lib_ids_raw.split(",") if s.strip()]
    return enabled, url, token, lib_ids


def _session(url: str, token: str) -> requests.Session:
    from shelfmark.download.network import get_ssl_verify

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}"})
    # The URL lets CERTIFICATE_VALIDATION=disabled_local skip verification for a LAN
    # server, which is where Audiobookshelf usually lives.
    session.verify = get_ssl_verify(url)
    return session


# "Alex Cross 02: ", "DCC 1: ", "Reacher 19.5: " - a short label, a number and a colon.
_SERIES_PREFIX = re.compile(r"^(?P<label>[^\d:]{1,40}?)\s+(?P<number>\d+(?:\.\d+)?)\s*:\s*(?=\S)")
# The minified item metadata carries the series as one string, "Name #sequence" per
# series joined with ", " (Audiobookshelf's Book.seriesName). The sequence is free text.
_SERIES_WITH_SEQUENCE = re.compile(r"^(?P<name>.+?)\s+#(?P<sequence>\S+)$")


def _parse_series_name(value: object) -> tuple[str | None, float | None]:
    """The first series in a ``seriesName`` string, and its position when numeric."""
    text = str(value or "").strip()
    if not text:
        return None, None
    first = text.split(", ", 1)[0].strip()
    match = _SERIES_WITH_SEQUENCE.match(first)
    if not match:
        return first or None, None
    name = match["name"].strip()
    try:
        position: float | None = float(match["sequence"])
    except ValueError:
        position = None
    return name or None, position


def _item_to_entry(item: dict[str, Any]) -> LibraryEntry:
    media = item.get("media") or {}
    meta = media.get("metadata") or {}
    title = meta.get("title") or ""
    author = meta.get("authorName") or ""
    rel_path = item.get("relPath") or ""
    shown_title = title
    item_tags = frozenset(
        str(tag) for tag in (media.get("tags") or []) if isinstance(tag, str) and tag
    )

    context_tok = set(tokens(author))
    series_name, series_index = _parse_series_name(meta.get("seriesName"))
    # A book in a series is often titled "Alex Cross 02: Kiss the Girls" so players that
    # ignore the series number still show the order. Those leading words name the series,
    # not another work, so they go with the author as context.
    prefix = _SERIES_PREFIX.match(title) if series_name else None
    if prefix:
        context_tok |= set(tokens(f"{prefix['label']} {prefix['number']}"))
        title = title[prefix.end() :]
        if series_index is None:
            # No sequence in the series field; the label's number is the next best thing.
            series_index = float(prefix["number"])
    title_tok = set(tokens(title))
    tok = title_tok | context_tok | set(tokens(rel_path))

    asin = str(meta.get("asin") or "").strip().upper()
    asins = {asin} if asin else set()

    return LibraryEntry(
        frozenset(tok),
        isbn_variants(meta.get("isbn")),
        frozenset(asins),
        frozenset(),
        frozenset(title_tok),
        frozenset(context_tok),
        item_id=str(item.get("id") or ""),
        title=shown_title,
        author=str(author).strip() or None,
        tags=item_tags,
        series_name=series_name,
        series_index=series_index,
    )


def _fetch_library_entries(url: str, token: str, lib_ids: list[str]) -> list[LibraryEntry]:
    session = _session(url, token)

    resp = session.get(f"{url}/api/libraries", timeout=_REQUEST_TIMEOUT)
    resp.raise_for_status()
    libraries = resp.json().get("libraries", [])

    selected: list[str] = []
    for lib in libraries:
        lib_id = lib.get("id")
        if not lib_id:
            continue
        if lib_ids:
            if lib_id in lib_ids:
                selected.append(lib_id)
        elif lib.get("mediaType") == "book":
            selected.append(lib_id)

    entries: list[LibraryEntry] = []
    for lib_id in selected:
        page = 0
        while True:
            resp = session.get(
                f"{url}/api/libraries/{lib_id}/items",
                params={"limit": _ITEMS_PAGE_LIMIT, "page": page},
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", []) or []
            entries.extend(_item_to_entry(item) for item in results)
            total = int(data.get("total", 0) or 0)
            page += 1
            if not results or page * _ITEMS_PAGE_LIMIT >= total:
                break

    return entries


class AudiobookshelfForbiddenError(PermissionError):
    """Audiobookshelf answered 403: the token's user may not update library items."""


def _item_tags(payload: dict[str, Any]) -> list[str]:
    media = payload.get("media") or {}
    return [tag for tag in (media.get("tags") or []) if isinstance(tag, str) and tag]


class AudiobookshelfTagClient:
    """Read and replace one item's tag list over the REST API.

    ``PATCH /api/items/<id>/media`` takes a Book payload whose ``tags`` is the whole
    list, so a write always starts from a fresh ``GET /api/items/<id>`` rather than
    the cached index: a tag someone added in Audiobookshelf a minute ago survives.
    Audiobookshelf refuses the PATCH with 403 when the token's user lacks the update
    permission; that surfaces as :class:`AudiobookshelfForbiddenError`.
    """

    def __init__(self, overrides: Mapping[str, Any] | None = None) -> None:
        _enabled, url, token, _lib_ids = _config(overrides)
        if not url or not token:
            raise ValueError("Set the Audiobookshelf URL and token first.")
        self._url = url
        self._session = _session(url, token)

    def tags(self, item_id: str) -> list[str]:
        resp = self._session.get(f"{self._url}/api/items/{item_id}", timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        return _item_tags(resp.json())

    def set_tags(self, item_id: str, tags: list[str]) -> None:
        resp = self._session.patch(
            f"{self._url}/api/items/{item_id}/media",
            json={"tags": list(tags)},
            timeout=_REQUEST_TIMEOUT,
        )
        if resp.status_code == 403:
            raise AudiobookshelfForbiddenError(
                "Audiobookshelf refused the update (403): the API token's user needs the "
                "'Can update' permission to change tags."
            )
        resp.raise_for_status()


class AudiobookshelfLibrary:
    """Audiobook ownership via the Audiobookshelf REST API."""

    name = "audiobookshelf"
    display_name = "Audiobookshelf"
    content_types = frozenset({"audiobook"})

    def __init__(self, overrides: Mapping[str, Any] | None = None) -> None:
        self._overrides = overrides

    def is_enabled(self) -> bool:
        enabled, url, token, _lib_ids = _config(self._overrides)
        return enabled and bool(url) and bool(token)

    def describe(self) -> str:
        _enabled, url, _token, _lib_ids = _config(self._overrides)
        return f"Audiobookshelf at {url}" if url else "Audiobookshelf"

    def fingerprint(self) -> None:
        return None

    def fetch_entries(self) -> list[LibraryEntry]:
        _enabled, url, token, lib_ids = _config(self._overrides)
        if not url or not token:
            raise ValueError("Set the Audiobookshelf URL and token first.")
        return _fetch_library_entries(url, token, lib_ids)
