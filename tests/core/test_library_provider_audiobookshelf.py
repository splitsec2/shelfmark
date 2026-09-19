"""Tests for the Audiobookshelf library provider."""

from __future__ import annotations

from typing import Any

import pytest

from shelfmark.core.library_providers import audiobookshelf


def _item(title: str, author: str, rel_path: str = "", **meta: Any) -> dict[str, Any]:
    return {
        "relPath": rel_path,
        "media": {"metadata": {"title": title, "authorName": author, **meta}},
    }


def test_item_to_entry_tokenizes_title_author_and_path() -> None:
    item = _item(
        "Dungeon Crawler Carl",
        "Matt Dinniman",
        "Matt Dinniman/Dungeon Crawler Carl (2020)",
        isbn="978-0-593-82024-7",
        asin=" b08bkgyqxw ",
    )

    entry = audiobookshelf._item_to_entry(item)

    assert {"dungeon", "crawler", "carl", "matt", "dinniman", "2020"} <= entry.tokens
    assert entry.isbns == {"9780593820247"}
    assert entry.asins == {"B08BKGYQXW"}
    assert entry.external_ids == frozenset()


def test_item_to_entry_indexes_both_forms_of_an_isbn10() -> None:
    entry = audiobookshelf._item_to_entry(_item("Carl", "Dinniman", isbn="059382024X"))

    assert entry.isbns == {"059382024X", "9780593820247"}


def test_item_to_entry_tolerates_missing_metadata() -> None:
    entry = audiobookshelf._item_to_entry({})

    assert (entry.tokens, entry.isbns, entry.asins) == (frozenset(), frozenset(), frozenset())


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class _Session:
    def __init__(self, libraries: list[dict[str, Any]], pages: dict[int, dict[str, Any]]) -> None:
        self.libraries = libraries
        self.pages = pages
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, url: str, params: dict[str, Any] | None = None, timeout: int = 0) -> _Response:
        self.calls.append((url, dict(params or {})))
        if url.endswith("/api/libraries"):
            return _Response({"libraries": self.libraries})
        return _Response(self.pages[int(self.calls[-1][1]["page"])])


def _install(monkeypatch: pytest.MonkeyPatch, session: _Session) -> None:
    monkeypatch.setattr(audiobookshelf, "_session", lambda token: session)
    monkeypatch.setattr(audiobookshelf, "_ITEMS_PAGE_LIMIT", 2)


def test_fetch_pages_through_book_libraries(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _Session(
        libraries=[{"id": "books", "mediaType": "book"}, {"id": "pods", "mediaType": "podcast"}],
        pages={
            0: {"results": [_item("One", "A"), _item("Two", "B")], "total": 3},
            1: {"results": [_item("Three", "C")], "total": 3},
        },
    )
    _install(monkeypatch, session)

    entries = audiobookshelf._fetch_library_entries("http://abs", "token", [])

    assert [sorted(entry.tokens) for entry in entries] == [
        ["a", "one"],
        ["b", "two"],
        ["c", "three"],
    ]
    item_calls = [(url, params) for url, params in session.calls if url.endswith("/items")]
    assert [url for url, _ in item_calls] == ["http://abs/api/libraries/books/items"] * 2
    assert [params["page"] for _, params in item_calls] == [0, 1]
    assert all(params["limit"] == 2 for _, params in item_calls)


def test_fetch_honours_the_library_id_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _Session(
        libraries=[{"id": "books", "mediaType": "book"}, {"id": "kids", "mediaType": "book"}],
        pages={0: {"results": [_item("One", "A")], "total": 1}},
    )
    _install(monkeypatch, session)

    entries = audiobookshelf._fetch_library_entries("http://abs", "token", ["kids"])

    assert len(entries) == 1
    assert [url for url, _ in session.calls if url.endswith("/items")] == [
        "http://abs/api/libraries/kids/items"
    ]


def test_fetch_stops_on_an_empty_page(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _Session(
        libraries=[{"id": "books", "mediaType": "book"}],
        pages={0: {"results": [], "total": 50}},
    )
    _install(monkeypatch, session)

    assert audiobookshelf._fetch_library_entries("http://abs", "token", []) == []
    assert len([url for url, _ in session.calls if url.endswith("/items")]) == 1


@pytest.mark.parametrize(
    ("values", "enabled"),
    [
        (
            {
                "LIBRARY_CHECK_ENABLED": True,
                "AUDIOBOOKSHELF_URL": "http://abs/",
                "AUDIOBOOKSHELF_TOKEN": "t",
            },
            True,
        ),
        ({"LIBRARY_CHECK_ENABLED": True, "AUDIOBOOKSHELF_URL": "http://abs/"}, False),
        (
            {
                "LIBRARY_CHECK_ENABLED": False,
                "AUDIOBOOKSHELF_URL": "http://abs/",
                "AUDIOBOOKSHELF_TOKEN": "t",
            },
            False,
        ),
    ],
    ids=["configured", "missing-token", "disabled"],
)
def test_provider_is_enabled_only_when_configured(
    monkeypatch: pytest.MonkeyPatch, values: dict[str, Any], enabled: bool
) -> None:
    monkeypatch.setattr(
        audiobookshelf.app_config,
        "get",
        lambda key, default=None, user_id=None: values.get(key, default),
    )
    provider = audiobookshelf.AudiobookshelfLibrary()

    assert provider.is_enabled() is enabled
    assert provider.describe() == "Audiobookshelf at http://abs"
    assert provider.fingerprint() is None


def test_fetch_entries_requires_url_and_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        audiobookshelf.app_config, "get", lambda key, default=None, user_id=None: default
    )
    provider = audiobookshelf.AudiobookshelfLibrary()

    assert provider.describe() == "Audiobookshelf"
    with pytest.raises(ValueError, match="URL and token"):
        provider.fetch_entries()
