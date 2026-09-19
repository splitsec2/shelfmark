"""Audiobookshelf (ABS) library provider.

Fetches the user's ABS libraries over the REST API (title/author/isbn/asin per item).
ABS library metadata is messy (titles are often raw folder names, author frequently
empty), so each item is tokenized from title + author + folder path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import requests

from shelfmark.core.config import config as app_config
from shelfmark.core.library_providers import LibraryEntry, setting
from shelfmark.core.text_match import isbn_variants, tokens

if TYPE_CHECKING:
    from collections.abc import Mapping

_REQUEST_TIMEOUT = 15
_ITEMS_PAGE_LIMIT = 500


def _config(overrides: Mapping[str, Any] | None = None) -> tuple[bool, str, str, list[str]]:
    enabled = bool(setting(app_config, "LIBRARY_CHECK_ENABLED", False, overrides))
    url = str(setting(app_config, "AUDIOBOOKSHELF_URL", "", overrides) or "").strip().rstrip("/")
    token = str(setting(app_config, "AUDIOBOOKSHELF_TOKEN", "", overrides) or "").strip()
    lib_ids_raw = str(setting(app_config, "AUDIOBOOKSHELF_LIBRARY_IDS", "", overrides) or "")
    lib_ids = [s.strip() for s in lib_ids_raw.split(",") if s.strip()]
    return enabled, url, token, lib_ids


def _session(token: str) -> requests.Session:
    from shelfmark.download.network import get_ssl_verify

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}"})
    session.verify = get_ssl_verify()
    return session


def _item_to_entry(item: dict[str, Any]) -> LibraryEntry:
    media = item.get("media") or {}
    meta = media.get("metadata") or {}
    title = meta.get("title") or ""
    author = meta.get("authorName") or ""
    rel_path = item.get("relPath") or ""

    title_tok = set(tokens(title))
    context_tok = set(tokens(author))
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
    )


def _fetch_library_entries(url: str, token: str, lib_ids: list[str]) -> list[LibraryEntry]:
    session = _session(token)

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
