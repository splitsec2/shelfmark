"""Tests for the Audiobookshelf library provider."""

from __future__ import annotations

from typing import Any

import pytest

from shelfmark.core import library_index
from shelfmark.core.library_providers import audiobookshelf
from shelfmark.metadata_providers import BookMetadata
from tests.core.fakes import FakeConfig

pytestmark = pytest.mark.usefixtures("fake_app_config")


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


def _searching(title: str, author: str = "James Patterson") -> BookMetadata:
    return BookMetadata(
        provider="hardcover",
        provider_id="1",
        title=title,
        authors=[author],
        search_title=title,
        search_author=author,
    )


@pytest.mark.parametrize(
    ("shelf_title", "series", "author", "searching"),
    [
        ("Alex Cross 02: Kiss the Girls", "Alex Cross #2", "James Patterson", "Kiss the Girls"),
        ("Alex Cross 12: Cross", "Alex Cross #12", "James Patterson", "Cross"),
        ("Alex Cross 13: Double Cross", "Alex Cross #13", "James Patterson", "Double Cross"),
        (
            "DCC 2: Carl's Doomsday Scenario",
            "Dungeon Crawler Carl #2",
            "Matt Dinniman",
            "Carl's Doomsday Scenario",
        ),
        ("Reacher 19: Personal", "Jack Reacher #19", "Lee Child", "Personal"),
        ("Reacher 01: Killing Floor", "Jack Reacher #1", "Lee Child", "Killing Floor"),
    ],
)
def test_a_series_number_in_the_shelf_title_does_not_hide_the_book(
    shelf_title: str, series: str, author: str, searching: str
) -> None:
    entry = audiobookshelf._item_to_entry(_item(shelf_title, author, seriesName=series))

    assert library_index.match_entries(_searching(searching, author), [entry]) == "owned"


def test_a_search_title_that_carries_the_series_words_still_matches() -> None:
    """Metadata sources often title the same book "Kiss the Girls: Alex Cross"."""
    entry = audiobookshelf._item_to_entry(
        _item("Alex Cross 02: Kiss the Girls", "James Patterson", seriesName="Alex Cross #2")
    )

    assert library_index.match_entries(_searching("Kiss the Girls: Alex Cross"), [entry]) == "owned"


def test_a_numbered_shelf_title_still_does_not_match_a_different_book() -> None:
    entry = audiobookshelf._item_to_entry(
        _item("Alex Cross 02: Kiss the Girls", "James Patterson", seriesName="Alex Cross #2")
    )

    assert library_index.match_entries(_searching("Along Came a Spider"), [entry]) is None
    # A shorter search title is still a different book, as with "Dune" and "Dune Messiah".
    assert library_index.match_entries(_searching("Cross"), [entry]) is None


def test_a_number_before_a_colon_is_only_a_series_label_when_abs_reports_a_series() -> None:
    entry = audiobookshelf._item_to_entry(_item("Apollo 13: The Movie", "Someone"))

    assert library_index.match_entries(_searching("The Movie", "Someone"), [entry]) is None


def test_a_plain_shelf_title_is_unchanged_by_the_series_handling() -> None:
    entry = audiobookshelf._item_to_entry(
        _item("Kiss the Girls", "James Patterson", seriesName="Alex Cross #2")
    )

    assert library_index.match_entries(_searching("Kiss the Girls"), [entry]) == "owned"


@pytest.mark.parametrize(
    "shelf_title",
    [
        "Dungeon Crawler Carl (Full Cast Edition)",
        "Dungeon Crawler Carl (Audio Immersion Tunnel)",
        "Dungeon Crawler Carl (GraphicAudio)",
        "Dungeon Crawler Carl [Dramatized Adaptation]",
        "Dungeon Crawler Carl (Part 1 of 3) (Dramatized Adaptation)",
    ],
)
def test_an_alternate_edition_on_the_shelf_is_not_the_book(shelf_title: str) -> None:
    # A full-cast or dramatized recording shares the title and author of the
    # single-narrator original, but owning one is not owning the other. The bracketed
    # words stay in the title set, where the matcher reads them as naming another
    # edition.
    entry = audiobookshelf._item_to_entry(_item(shelf_title, "Matt Dinniman"))

    assert (
        library_index.match_entries(_searching("Dungeon Crawler Carl", "Matt Dinniman"), [entry])
        is None
    )


@pytest.mark.parametrize(
    ("shelf_title", "searching"),
    [
        ("Dungeon Crawler Carl (Unabridged)", "Dungeon Crawler Carl"),
        ("Dungeon Crawler Carl (Abridged)", "Dungeon Crawler Carl"),
        ("Dungeon Crawler Carl (Illustrated Edition)", "Dungeon Crawler Carl"),
        ("Dungeon Crawler Carl (Full Cast Edition)", "Dungeon Crawler Carl (Full Cast Edition)"),
    ],
)
def test_a_printing_word_or_the_same_edition_marker_is_still_the_book(
    shelf_title: str, searching: str
) -> None:
    # "(Unabridged)" is shelf noise, not an edition; and the edition asked for by its
    # own name is the one on the shelf.
    entry = audiobookshelf._item_to_entry(_item(shelf_title, "Matt Dinniman"))

    assert library_index.match_entries(_searching(searching, "Matt Dinniman"), [entry]) == "owned"


def test_a_marker_on_the_searched_title_alone_is_not_on_the_shelf() -> None:
    entry = audiobookshelf._item_to_entry(_item("Dungeon Crawler Carl", "Matt Dinniman"))

    assert (
        library_index.match_entries(
            _searching("Dungeon Crawler Carl (GraphicAudio)", "Matt Dinniman"), [entry]
        )
        is None
    )


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
    monkeypatch.setattr(audiobookshelf, "_session", lambda url, token: session)
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
    fake_app_config: FakeConfig, values: dict[str, Any], enabled: bool
) -> None:
    fake_app_config.values.update(values)
    provider = audiobookshelf.AudiobookshelfLibrary()

    assert provider.is_enabled() is enabled
    assert provider.describe() == "Audiobookshelf at http://abs"
    assert provider.fingerprint() is None


def test_fetch_entries_requires_url_and_token() -> None:
    provider = audiobookshelf.AudiobookshelfLibrary()

    assert provider.describe() == "Audiobookshelf"
    with pytest.raises(ValueError, match="URL and token"):
        provider.fetch_entries()


@pytest.mark.parametrize(
    ("mode", "url", "verify"),
    [
        ("disabled_local", "https://10.0.0.91:13378", False),
        ("disabled_local", "https://abs.example.com", True),
        ("enabled", "https://10.0.0.91:13378", True),
    ],
)
def test_session_honours_certificate_validation_for_the_server_url(
    fake_app_config: FakeConfig, mode: str, url: str, verify: bool
) -> None:
    fake_app_config.values["CERTIFICATE_VALIDATION"] = mode

    assert audiobookshelf._session(url, "t").verify is verify


def test_configured_url_is_normalized(fake_app_config: FakeConfig) -> None:
    fake_app_config.values.update(
        LIBRARY_CHECK_ENABLED=True,
        AUDIOBOOKSHELF_URL=' "abs.lan:13378/" ',
        AUDIOBOOKSHELF_TOKEN="t",
    )

    assert (
        audiobookshelf.AudiobookshelfLibrary().describe()
        == "Audiobookshelf at http://abs.lan:13378"
    )
