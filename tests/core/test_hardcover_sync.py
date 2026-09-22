"""Tests for syncing Hardcover status shelves into pending requests."""

import sqlite3
from types import SimpleNamespace

import pytest

from shelfmark.core import hardcover_sync
from shelfmark.core.user_db import UserDB
from shelfmark.core.utils import transform_cover_url
from shelfmark.metadata_providers import BookMetadata
from tests.core.fakes import FakeConfig

pytestmark = pytest.mark.usefixtures("fake_app_config")


class _Provider:
    """Stub exposing the private paging method ``sync_wishlist`` relies on."""

    def __init__(self, pages_by_status):
        self.pages_by_status = pages_by_status
        self.calls = []

    def _fetch_current_user_books_by_status(self, status_id, page, limit):
        self.calls.append((status_id, page, limit))
        pages = self.pages_by_status.get(status_id, [])
        books = pages[page - 1] if page <= len(pages) else []
        return SimpleNamespace(books=books, has_more=page < len(pages))


def _book(provider_id, title, author="Matt Dinniman", **overrides):
    fields = {
        "provider": "hardcover",
        "provider_id": provider_id,
        "title": title,
        "authors": [author],
    }
    fields.update(overrides)
    return BookMetadata(**fields)


def _insert_history(db_path, *, title, author):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO download_history (task_id, source, title, author, final_status) "
            "VALUES (?, ?, ?, ?, ?)",
            (f"task-{title}", "prowlarr", title, author, "complete"),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "users.db")


@pytest.fixture
def user_db(db_path):
    db = UserDB(db_path)
    db.initialize()
    return db


def _configure(monkeypatch, **values):
    monkeypatch.setattr(hardcover_sync, "app_config", FakeConfig(**values))


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"HARDCOVER_SYNC_TOKEN": "  sync-token  ", "HARDCOVER_API_KEY": "api"}, "sync-token"),
        ({"HARDCOVER_SYNC_TOKEN": "", "HARDCOVER_API_KEY": "api-key"}, "api-key"),
        ({}, ""),
    ],
)
def test_configured_token_falls_back_to_provider_api_key(monkeypatch, values, expected):
    _configure(monkeypatch, **values)

    assert hardcover_sync._configured_token() == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("3", [3]),
        (" 2 ", [2]),
        (["1", "3"], [1, 3]),
        ((1, "x", None), [1]),
        ("garbage", [1]),
        ([], [1]),
        (42, [1]),
    ],
)
def test_configured_statuses_parsing(monkeypatch, raw, expected):
    _configure(monkeypatch, HARDCOVER_SYNC_STATUSES=raw)

    assert hardcover_sync._configured_statuses() == expected


def test_configured_statuses_default(monkeypatch):
    _configure(monkeypatch)

    assert hardcover_sync._configured_statuses() == [1]


def test_book_to_book_data_includes_optional_fields_only_when_present():
    full = _book(
        7,
        "Dungeon Crawler Carl",
        cover_url="https://img.example/c.jpg",
        publish_year=2020,
        subtitle="Book One",
        search_author="Dinniman",
    )
    sparse = BookMetadata(provider="hardcover", provider_id="8", title="Untitled")

    assert hardcover_sync._book_to_book_data(full, "audiobook") == {
        "title": "Dungeon Crawler Carl",
        "author": "Dinniman",
        "provider": "hardcover",
        "provider_id": "7",
        "content_type": "audiobook",
        "preview": transform_cover_url("https://img.example/c.jpg", "hardcover_7"),
        "year": 2020,
        "subtitle": "Book One",
    }
    assert hardcover_sync._book_to_book_data(sparse, "ebook") == {
        "title": "Untitled",
        "author": "Unknown",
        "provider": "hardcover",
        "provider_id": "8",
        "content_type": "ebook",
    }


def test_existing_request_keys_pair_provider_id_with_content_type(user_db):
    user = user_db.create_user(username="reader", role="user")
    for book_data in (
        {"title": "A", "author": "X", "provider": "hardcover", "provider_id": 11},
        {"title": "B", "author": "X", "provider": "openlibrary", "id": "OL22W"},
        {"title": "C", "author": "X", "provider": "manual"},
    ):
        user_db.create_request(
            user_id=user["id"],
            content_type="audiobook",
            request_level="book",
            policy_mode="request_book",
            book_data=book_data,
        )

    assert hardcover_sync._existing_request_keys(user_db) == {
        ("11", "audiobook"),
        ("OL22W", "audiobook"),
    }


def test_already_downloaded_matches_history_case_insensitively(user_db, db_path):
    _insert_history(db_path, title="Dungeon Crawler Carl", author="Matt Dinniman")

    assert hardcover_sync._already_downloaded(
        db_path, "dungeon crawler CARL", "MATT dinniman", "audiobook"
    )
    assert not hardcover_sync._already_downloaded(
        db_path, "Dungeon Crawler Carl", "Someone", "audiobook"
    )
    assert not hardcover_sync._already_downloaded(
        None, "Dungeon Crawler Carl", "Matt Dinniman", "audiobook"
    )


def test_already_downloaded_fails_open_without_history_table(tmp_path):
    missing = str(tmp_path / "empty.db")

    assert hardcover_sync._already_downloaded(missing, "Anything", "Anyone", "ebook") is False


class TestSyncWishlist:
    @pytest.fixture(autouse=True)
    def _defaults(self, monkeypatch):
        _configure(monkeypatch, HARDCOVER_SYNC_STATUSES="1")
        monkeypatch.setattr(
            "shelfmark.core.library_index.is_in_library", lambda *_args, **_kwargs: False
        )

    def _use_provider(self, monkeypatch, provider):
        monkeypatch.setattr(hardcover_sync, "_build_provider", lambda *_args: provider)

    def test_adds_new_requests_across_pages(self, user_db, db_path, monkeypatch):
        user = user_db.create_user(username="reader", role="user")
        provider = _Provider(
            {
                1: [
                    [_book(1, "Dungeon Crawler Carl", cover_url="https://img.example/1.jpg")],
                    [_book(2, "Carl's Doomsday Scenario", publish_year=2021)],
                ]
            }
        )
        self._use_provider(monkeypatch, provider)

        summary = hardcover_sync.sync_wishlist(user_db, db_path=db_path, user_id=user["id"])

        assert summary == {"added": 2, "skipped": 0, "in_library": 0, "errors": 0}
        assert provider.calls == [(1, 1, 25), (1, 2, 25)]
        rows = {row["book_data"]["provider_id"]: row for row in user_db.list_requests()}
        assert set(rows) == {"1", "2"}
        assert rows["1"]["status"] == "pending"
        assert rows["1"]["content_type"] == "audiobook"
        assert rows["1"]["book_data"]["preview"] == transform_cover_url(
            "https://img.example/1.jpg", "hardcover_1"
        )
        assert rows["2"]["book_data"]["year"] == 2021
        assert "preview" not in rows["2"]["book_data"]

    def test_skips_known_downloaded_owned_and_duplicate_books(self, user_db, db_path, monkeypatch):
        user = user_db.create_user(username="reader", role="user")
        user_db.create_request(
            user_id=user["id"],
            content_type="audiobook",
            request_level="book",
            policy_mode="request_book",
            book_data={
                "title": "Already Requested",
                "author": "Matt Dinniman",
                "provider": "hardcover",
                "provider_id": "10",
            },
        )
        _insert_history(db_path, title="Already Downloaded", author="Matt Dinniman")
        _configure(monkeypatch, HARDCOVER_SYNC_STATUSES="1", LIBRARY_CHECK_ENABLED=True)
        monkeypatch.setattr("shelfmark.core.library_index.any_provider_enabled", lambda: True)
        monkeypatch.setattr(
            "shelfmark.core.library_index.is_in_library",
            lambda book, *_args, **_kwargs: book.title == "Already Owned",
        )
        provider = _Provider(
            {
                1: [
                    [
                        _book(10, "Already Requested"),
                        _book(11, "Already Downloaded"),
                        _book(12, "Already Owned"),
                        _book(13, "Brand New"),
                        _book(14, "Brand New"),
                    ]
                ]
            }
        )
        self._use_provider(monkeypatch, provider)

        summary = hardcover_sync.sync_wishlist(user_db, db_path=db_path, user_id=user["id"])

        assert summary == {"added": 1, "skipped": 3, "in_library": 1, "errors": 0}
        titles = sorted(row["book_data"]["title"] for row in user_db.list_requests())
        assert titles == ["Already Requested", "Brand New"]

    def test_unavailable_provider_counts_as_error(self, user_db, db_path, monkeypatch):
        self._use_provider(monkeypatch, None)

        summary = hardcover_sync.sync_wishlist(user_db, db_path=db_path)

        assert summary == {"added": 0, "skipped": 0, "in_library": 0, "errors": 1}
        assert user_db.list_requests() == []


class TestResolveRequestOwner:
    def test_returns_lowest_id_admin(self, user_db):
        user_db.create_user(username="reader", role="user")
        first_admin = user_db.create_user(username="ops", role="admin")
        user_db.create_user(username="second", role="admin")

        assert hardcover_sync.resolve_request_owner(user_db) == first_admin["id"]

    def test_returns_none_without_admins(self, user_db):
        user_db.create_user(username="reader", role="user")

        assert hardcover_sync.resolve_request_owner(user_db) is None

    def test_sync_without_admin_counts_an_error_and_creates_nothing(self, user_db, db_path):
        user_db.create_user(username="reader", role="user")

        summary = hardcover_sync.sync_wishlist(user_db, db_path=db_path)

        assert summary == {"added": 0, "skipped": 0, "in_library": 0, "errors": 1}
        assert user_db.list_requests() == []

    def test_sync_defaults_to_the_lowest_id_admin(self, user_db, db_path, monkeypatch):
        user_db.create_user(username="reader", role="user")
        admin = user_db.create_user(username="ops", role="admin")
        provider = _Provider({1: [[_book(1, "Dungeon Crawler Carl")]]})
        monkeypatch.setattr(hardcover_sync, "_build_provider", lambda *_args: provider)

        summary = hardcover_sync.sync_wishlist(user_db, db_path=db_path)

        assert summary["added"] == 1
        assert user_db.list_requests()[0]["user_id"] == admin["id"]


class TestPerUserTokens:
    def test_a_users_own_token_is_used_for_their_sync(self, monkeypatch):
        seen: list[int | None] = []

        def _get(key, default=None, user_id=None):
            seen.append(user_id)
            if key == "HARDCOVER_SYNC_TOKEN" and user_id == 5:
                return "user-token"
            if key == "HARDCOVER_SYNC_TOKEN":
                return "app-token"
            return default

        monkeypatch.setattr(hardcover_sync.app_config, "get", _get)

        assert hardcover_sync._configured_token(5) == "user-token"
        assert 5 in seen

    def test_the_app_level_token_is_the_fallback(self, monkeypatch):
        def _get(key, default=None, user_id=None):
            if key == "HARDCOVER_SYNC_TOKEN" and user_id is None:
                return "app-token"
            if key == "HARDCOVER_SYNC_TOKEN":
                return ""
            if key == "HARDCOVER_API_KEY":
                return ""
            return default

        monkeypatch.setattr(hardcover_sync.app_config, "get", _get)

        assert hardcover_sync._configured_token() == "app-token"
        # A user who connected nothing of their own still syncs on the shared token.
        assert hardcover_sync._configured_token(5) == ""

    def test_provider_api_key_remains_the_last_resort(self, monkeypatch):
        def _get(key, default=None, user_id=None):
            return "provider-key" if key == "HARDCOVER_API_KEY" else ""

        monkeypatch.setattr(hardcover_sync.app_config, "get", _get)

        assert hardcover_sync._configured_token() == "provider-key"

    def test_only_users_who_connected_a_token_are_listed(self, user_db, monkeypatch):
        reader = user_db.create_user(username="reader", role="user")
        admin = user_db.create_user(username="ops", role="admin")
        user_db.create_user(username="nobody", role="user")
        connected = {reader["id"], admin["id"]}
        monkeypatch.setattr(
            hardcover_sync.app_config,
            "get_user_override",
            lambda _key, *, user_id: "token" if user_id in connected else None,
        )

        assert hardcover_sync.users_with_hardcover_token(user_db) == sorted(connected)

    def test_a_users_sync_is_owned_by_them_and_deduped_against_their_own_requests(
        self, user_db, db_path, monkeypatch
    ):
        user_db.create_user(username="ops", role="admin")
        reader = user_db.create_user(username="reader", role="user")
        provider = _Provider({1: [[_book(1, "Dungeon Crawler Carl")]]})
        monkeypatch.setattr(hardcover_sync, "_build_provider", lambda *_args: provider)

        first = hardcover_sync.sync_wishlist(user_db, db_path=db_path, user_id=reader["id"])
        assert first["added"] == 1
        assert user_db.list_requests()[0]["user_id"] == reader["id"]

        second = hardcover_sync.sync_wishlist(user_db, db_path=db_path, user_id=reader["id"])
        assert second["added"] == 0
        assert second["skipped"] == 1

    def test_another_users_request_does_not_swallow_this_users_book(
        self, user_db, db_path, monkeypatch
    ):
        user_db.create_user(username="ops", role="admin")
        first_reader = user_db.create_user(username="ann", role="user")
        second_reader = user_db.create_user(username="ben", role="user")
        provider = _Provider({1: [[_book(1, "Dungeon Crawler Carl")]]})
        monkeypatch.setattr(hardcover_sync, "_build_provider", lambda *_args: provider)

        hardcover_sync.sync_wishlist(user_db, db_path=db_path, user_id=first_reader["id"])
        summary = hardcover_sync.sync_wishlist(
            user_db, db_path=db_path, user_id=second_reader["id"]
        )

        assert summary["added"] == 1
        owners = {row["user_id"] for row in user_db.list_requests()}
        assert owners == {first_reader["id"], second_reader["id"]}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ebook", ["ebook"]),
        ("audiobook", ["audiobook"]),
        ("both", ["ebook", "audiobook"]),
        ("BOTH ", ["ebook", "audiobook"]),
        ("garbage", ["audiobook"]),
        (None, ["audiobook"]),
    ],
)
def test_configured_content_types(monkeypatch, raw, expected):
    _configure(monkeypatch, HARDCOVER_SYNC_CONTENT_TYPE=raw)

    assert hardcover_sync._configured_content_types() == expected


def test_already_downloaded_is_per_content_type(user_db, db_path):
    _insert_history(db_path, title="Dungeon Crawler Carl", author="Matt Dinniman")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE download_history SET content_type = 'ebook'")
        conn.commit()
    finally:
        conn.close()

    assert hardcover_sync._already_downloaded(
        db_path, "Dungeon Crawler Carl", "Matt Dinniman", "ebook"
    )
    assert not hardcover_sync._already_downloaded(
        db_path, "Dungeon Crawler Carl", "Matt Dinniman", "audiobook"
    )


class TestSyncBothFormats:
    def test_both_creates_an_ebook_and_an_audiobook_request_per_book(
        self, user_db, db_path, monkeypatch
    ):
        admin = user_db.create_user(username="ops", role="admin")
        _configure(monkeypatch, HARDCOVER_SYNC_STATUSES="1", HARDCOVER_SYNC_CONTENT_TYPE="both")
        provider = _Provider({1: [[_book(1, "Dungeon Crawler Carl")]]})
        monkeypatch.setattr(hardcover_sync, "_build_provider", lambda *_args: provider)
        checked: list[str] = []
        monkeypatch.setattr("shelfmark.core.library_index.any_provider_enabled", lambda: True)
        monkeypatch.setattr(
            "shelfmark.core.library_index.is_in_library",
            lambda _book, content_type=None: (
                checked.append(content_type) or content_type == "ebook"
            ),
        )

        summary = hardcover_sync.sync_wishlist(user_db, db_path=db_path, user_id=admin["id"])

        assert summary == {"added": 1, "skipped": 0, "in_library": 1, "errors": 0}
        assert checked == ["ebook", "audiobook"]
        rows = user_db.list_requests()
        assert [row["content_type"] for row in rows] == ["audiobook"]
        assert rows[0]["book_data"]["content_type"] == "audiobook"

    def test_second_run_skips_both_existing_requests(self, user_db, db_path, monkeypatch):
        admin = user_db.create_user(username="ops", role="admin")
        _configure(monkeypatch, HARDCOVER_SYNC_STATUSES="1", HARDCOVER_SYNC_CONTENT_TYPE="both")
        provider = _Provider({1: [[_book(1, "Dungeon Crawler Carl")]]})
        monkeypatch.setattr(hardcover_sync, "_build_provider", lambda *_args: provider)

        first = hardcover_sync.sync_wishlist(user_db, db_path=db_path, user_id=admin["id"])
        second = hardcover_sync.sync_wishlist(user_db, db_path=db_path, user_id=admin["id"])

        assert first["added"] == 2
        assert second == {"added": 0, "skipped": 2, "in_library": 0, "errors": 0}
        assert sorted(row["content_type"] for row in user_db.list_requests()) == [
            "audiobook",
            "ebook",
        ]
