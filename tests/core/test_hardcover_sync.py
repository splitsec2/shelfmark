"""Tests for syncing Hardcover status shelves into pending requests."""

import sqlite3
from types import SimpleNamespace

import pytest

from shelfmark.core import hardcover_sync, library_index
from shelfmark.core.user_db import UserDB
from shelfmark.core.utils import transform_cover_url
from shelfmark.metadata_providers import BookMetadata


class _Config:
    def __init__(self, **values):
        self.values = values

    def get(self, key, default=None, user_id=None):
        return self.values.get(key, default)


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


def _insert_history(
    db_path,
    *,
    title,
    author,
    final_status="complete",
    content_type=None,
    request_id=None,
    terminal_at=None,
):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO download_history "
            "(task_id, source, title, author, final_status, content_type, request_id, "
            "terminal_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))",
            (
                f"task-{title}-{final_status}-{request_id}",
                "prowlarr",
                title,
                author,
                final_status,
                content_type,
                request_id,
                terminal_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _request(user_db, user_id, provider_id, content_type="audiobook", title="Some Book"):
    """A request for a Hardcover book, the shape the sync and the UI both create."""
    row = user_db.create_request(
        user_id=user_id,
        content_type=content_type,
        request_level="book",
        policy_mode="request_book",
        book_data={
            "title": title,
            "author": "Matt Dinniman",
            "provider": "hardcover",
            "provider_id": provider_id,
            "content_type": content_type,
        },
    )
    return int(row["id"])


_REAL_USER_TOKEN = hardcover_sync._user_token


@pytest.fixture(autouse=True)
def _users_have_their_own_token(monkeypatch):
    """A per-user pass needs the user's own token; tests that sync a user assume one.

    A test that exercises the real lookup puts ``_REAL_USER_TOKEN`` back.
    """
    monkeypatch.setattr(hardcover_sync, "_user_token", lambda _db, _user_id: "user-token")


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "users.db")


@pytest.fixture
def user_db(db_path):
    db = UserDB(db_path)
    db.initialize()
    return db


def _configure(monkeypatch, **values):
    monkeypatch.setattr(hardcover_sync, "app_config", _Config(**values))


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
        {"title": "B", "author": "X", "provider": "hardcover", "id": "22"},
        {"title": "C", "author": "X", "provider": "openlibrary", "id": "OL22W"},
        {"title": "D", "author": "X", "provider": "googlebooks", "provider_id": 33},
        {"title": "E", "author": "X", "provider": "manual"},
    ):
        user_db.create_request(
            user_id=user["id"],
            content_type="audiobook",
            request_level="book",
            policy_mode="request_book",
            book_data=book_data,
        )

    assert hardcover_sync._existing_request_keys(user_db, user["id"]) == {
        ("11", "audiobook"),
        ("22", "audiobook"),
    }


class TestSyncWishlist:
    @pytest.fixture(autouse=True)
    def _defaults(self, monkeypatch):
        _configure(monkeypatch, HARDCOVER_SYNC_STATUSES="1")
        monkeypatch.setattr(
            "shelfmark.core.library_index.is_in_library", lambda *_args, **_kwargs: False
        )

    def _use_provider(self, monkeypatch, provider):
        monkeypatch.setattr(hardcover_sync, "_build_provider", lambda *_args: provider)

    def test_a_failed_shelf_fetch_is_counted_as_an_error(self, user_db, monkeypatch):
        user = user_db.create_user(username="reader", role="user")

        class _Down(_Provider):
            def _fetch_current_user_books_by_status(self, status_id, page, limit):
                raise OSError("hardcover is down")

        self._use_provider(monkeypatch, _Down({}))

        summary = hardcover_sync.sync_wishlist(user_db, user_id=user["id"])

        assert summary["errors"] >= 1
        assert summary["added"] == 0

    def test_a_fetch_that_fails_on_a_later_page_keeps_the_books_already_read(
        self, user_db, monkeypatch
    ):
        user = user_db.create_user(username="reader", role="user")

        class _Flaky(_Provider):
            def _fetch_current_user_books_by_status(self, status_id, page, limit):
                if page == 2:
                    raise OSError("rate limited")
                return SimpleNamespace(books=[_book(1, "Dungeon Crawler Carl")], has_more=True)

        self._use_provider(monkeypatch, _Flaky({}))

        summary = hardcover_sync.sync_wishlist(user_db, user_id=user["id"])

        assert summary["added"] == 1
        assert summary["errors"] >= 1

    def test_adds_new_requests_across_pages(self, user_db, monkeypatch):
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

        summary = hardcover_sync.sync_wishlist(user_db, user_id=user["id"])

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

    def test_a_content_type_the_users_policy_blocks_is_not_requested(self, user_db, monkeypatch):
        user = user_db.create_user(username="reader", role="user")
        user_db.set_user_settings(user["id"], {"REQUEST_POLICY_DEFAULT_AUDIOBOOK": "blocked"})
        self._use_provider(monkeypatch, _Provider({1: [[_book(1, "Dungeon Crawler Carl")]]}))

        summary = hardcover_sync.sync_wishlist(user_db, user_id=user["id"])

        assert summary == {"added": 0, "skipped": 1, "in_library": 0, "errors": 0}
        assert user_db.list_requests() == []

    def test_an_admin_is_not_held_to_the_request_policy(self, user_db, monkeypatch):
        admin = user_db.create_user(username="ops", role="admin")
        user_db.set_user_settings(admin["id"], {"REQUEST_POLICY_DEFAULT_AUDIOBOOK": "blocked"})
        self._use_provider(monkeypatch, _Provider({1: [[_book(1, "Dungeon Crawler Carl")]]}))

        summary = hardcover_sync.sync_wishlist(user_db, user_id=admin["id"])

        assert summary["added"] == 1

    def test_preserves_request_after_another_users_delivery(self, user_db, db_path, monkeypatch):
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
        # The first user's delivery does not give the reader access to the book.
        other = user_db.create_user(username="other", role="user")
        _insert_history(
            db_path,
            title="Already Downloaded - Matt Dinniman [M4B]",
            author="Matt Dinniman",
            request_id=_request(user_db, other["id"], "11", title="Already Downloaded"),
        )
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

        summary = hardcover_sync.sync_wishlist(user_db, user_id=user["id"])

        assert summary == {"added": 2, "skipped": 2, "in_library": 1, "errors": 0}
        titles = sorted(
            row["book_data"]["title"] for row in user_db.list_requests(user_id=user["id"])
        )
        assert titles == ["Already Downloaded", "Already Requested", "Brand New"]

    def test_a_library_that_cannot_be_read_stops_the_sync_before_anything_is_requested(
        self, user_db, monkeypatch
    ):
        user = user_db.create_user(username="reader", role="user")
        provider = _Provider({1: [[_book(1, "Dungeon Crawler Carl")]]})
        self._use_provider(monkeypatch, provider)
        _configure(monkeypatch, HARDCOVER_SYNC_STATUSES="1")

        def _down(*_args, **_kwargs):
            raise library_index.LibraryUnavailableError("Audiobookshelf is unavailable")

        monkeypatch.setattr("shelfmark.core.library_index.require_ready", _down)

        summary = hardcover_sync.sync_wishlist(user_db, user_id=user["id"])

        # Skipping is the safe side: syncing now would request books the library already holds.
        assert summary == {"added": 0, "skipped": 0, "in_library": 0, "errors": 1}
        assert provider.calls == []  # Hardcover was not even asked
        assert user_db.list_requests() == []

    def test_a_blocked_formats_library_being_down_does_not_stop_the_permitted_one(
        self, user_db, monkeypatch
    ):
        """A blocked format's unavailable library does not stop the permitted format's requests."""
        user = user_db.create_user(username="reader", role="user")
        user_db.set_user_settings(user["id"], {"REQUEST_POLICY_DEFAULT_AUDIOBOOK": "blocked"})
        _configure(monkeypatch, HARDCOVER_SYNC_STATUSES="1", HARDCOVER_SYNC_CONTENT_TYPE="both")
        self._use_provider(monkeypatch, _Provider({1: [[_book(1, "Dungeon Crawler Carl")]]}))
        checked: list[str] = []

        def _ready(content_type, *, shared_only):
            """Record each readiness check; the audiobook library is down."""
            assert shared_only is True
            checked.append(content_type)
            if content_type == "audiobook":
                raise library_index.LibraryUnavailableError("Audiobookshelf is unavailable")

        monkeypatch.setattr("shelfmark.core.library_index.require_ready", _ready)

        summary = hardcover_sync.sync_wishlist(user_db, user_id=user["id"])

        assert checked == ["ebook"]
        assert summary == {"added": 1, "skipped": 1, "in_library": 0, "errors": 0}
        assert [row["content_type"] for row in user_db.list_requests()] == ["ebook"]

    def test_a_user_whose_own_token_is_gone_is_skipped_not_given_the_shared_one(
        self, user_db, monkeypatch
    ):
        """A user whose own token is gone is skipped, never synced on the shared token."""
        user = user_db.create_user(username="reader", role="user")
        monkeypatch.setattr(hardcover_sync, "_user_token", lambda _db, _user_id: "")
        built: list[object] = []
        monkeypatch.setattr(
            hardcover_sync, "_build_provider", lambda *args: built.append(args) or _Provider({})
        )

        summary = hardcover_sync.sync_wishlist(user_db, user_id=user["id"])

        assert summary == {"added": 0, "skipped": 0, "in_library": 0, "errors": 0}
        assert built == []
        assert user_db.list_requests() == []

    def test_a_per_user_provider_uses_only_the_users_own_token(self, monkeypatch):
        monkeypatch.setattr(hardcover_sync, "_user_token", lambda _db, _user_id: "")
        monkeypatch.setattr(hardcover_sync, "_configured_token", lambda *_a: "app-token")

        assert hardcover_sync._build_provider("") is None

    def test_unavailable_provider_counts_as_error(self, user_db, monkeypatch):
        self._use_provider(monkeypatch, None)

        summary = hardcover_sync.sync_wishlist(user_db)

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

    def test_sync_without_admin_counts_an_error_and_creates_nothing(self, user_db):
        user_db.create_user(username="reader", role="user")

        summary = hardcover_sync.sync_wishlist(user_db)

        assert summary == {"added": 0, "skipped": 0, "in_library": 0, "errors": 1}
        assert user_db.list_requests() == []

    def test_sync_defaults_to_the_lowest_id_admin(self, user_db, monkeypatch):
        user_db.create_user(username="reader", role="user")
        admin = user_db.create_user(username="ops", role="admin")
        provider = _Provider({1: [[_book(1, "Dungeon Crawler Carl")]]})
        monkeypatch.setattr(hardcover_sync, "_build_provider", lambda *_args: provider)

        summary = hardcover_sync.sync_wishlist(user_db)

        assert summary["added"] == 1
        assert user_db.list_requests()[0]["user_id"] == admin["id"]


class TestPerUserTokens:
    def test_provider_api_key_remains_the_last_resort(self, monkeypatch):
        """With no sync token anywhere, the metadata provider's API key is used."""

        def _get(key, default=None, user_id=None):
            """Config.get stand-in that only knows the provider API key."""
            return "provider-key" if key == "HARDCOVER_API_KEY" else ""

        monkeypatch.setattr(hardcover_sync.app_config, "get", _get)

        assert hardcover_sync._configured_token() == "provider-key"

    def test_only_users_who_connected_a_token_are_listed(self, user_db, monkeypatch):
        """Only users with a token of their own are listed for a per-user sync."""
        monkeypatch.setattr(hardcover_sync, "_user_token", _REAL_USER_TOKEN)
        reader = user_db.create_user(username="reader", role="user")
        admin = user_db.create_user(username="ops", role="admin")
        user_db.create_user(username="nobody", role="user")
        connected = {reader["id"], admin["id"]}
        for user_id in connected:
            user_db.set_user_settings(user_id, {"HARDCOVER_SYNC_TOKEN": "token"})

        assert hardcover_sync.users_with_hardcover_token(user_db) == sorted(connected)

    def test_a_users_sync_is_owned_by_them_and_deduped_against_their_own_requests(
        self, user_db, monkeypatch
    ):
        user_db.create_user(username="ops", role="admin")
        reader = user_db.create_user(username="reader", role="user")
        provider = _Provider({1: [[_book(1, "Dungeon Crawler Carl")]]})
        monkeypatch.setattr(hardcover_sync, "_build_provider", lambda *_args: provider)

        first = hardcover_sync.sync_wishlist(user_db, user_id=reader["id"])
        assert first["added"] == 1
        assert user_db.list_requests()[0]["user_id"] == reader["id"]

        second = hardcover_sync.sync_wishlist(user_db, user_id=reader["id"])
        assert second["added"] == 0
        assert second["skipped"] == 1

    def test_another_users_request_does_not_swallow_this_users_book(self, user_db, monkeypatch):
        user_db.create_user(username="ops", role="admin")
        first_reader = user_db.create_user(username="ann", role="user")
        second_reader = user_db.create_user(username="ben", role="user")
        provider = _Provider({1: [[_book(1, "Dungeon Crawler Carl")]]})
        monkeypatch.setattr(hardcover_sync, "_build_provider", lambda *_args: provider)

        hardcover_sync.sync_wishlist(user_db, user_id=first_reader["id"])
        summary = hardcover_sync.sync_wishlist(user_db, user_id=second_reader["id"])

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


class TestSyncBothFormats:
    def test_both_creates_an_ebook_and_an_audiobook_request_per_book(self, user_db, monkeypatch):
        """Both formats gives an ebook and an audiobook request per book, each checked alone."""
        admin = user_db.create_user(username="ops", role="admin")
        _configure(monkeypatch, HARDCOVER_SYNC_STATUSES="1", HARDCOVER_SYNC_CONTENT_TYPE="both")
        provider = _Provider({1: [[_book(1, "Dungeon Crawler Carl")]]})
        monkeypatch.setattr(hardcover_sync, "_build_provider", lambda *_args: provider)
        checked: list[str] = []
        monkeypatch.setattr("shelfmark.core.library_index.any_provider_enabled", lambda: True)
        monkeypatch.setattr(
            "shelfmark.core.library_index.is_in_library",
            lambda _book, content_type=None, **_kwargs: (
                checked.append(content_type) or content_type == "ebook"
            ),
        )

        summary = hardcover_sync.sync_wishlist(user_db, user_id=admin["id"])

        assert summary == {"added": 1, "skipped": 0, "in_library": 1, "errors": 0}
        assert checked == ["ebook", "audiobook"]
        rows = user_db.list_requests()
        assert [row["content_type"] for row in rows] == ["audiobook"]
        assert rows[0]["book_data"]["content_type"] == "audiobook"

    def test_second_run_skips_both_existing_requests(self, user_db, monkeypatch):
        admin = user_db.create_user(username="ops", role="admin")
        _configure(monkeypatch, HARDCOVER_SYNC_STATUSES="1", HARDCOVER_SYNC_CONTENT_TYPE="both")
        provider = _Provider({1: [[_book(1, "Dungeon Crawler Carl")]]})
        monkeypatch.setattr(hardcover_sync, "_build_provider", lambda *_args: provider)

        first = hardcover_sync.sync_wishlist(user_db, user_id=admin["id"])
        second = hardcover_sync.sync_wishlist(user_db, user_id=admin["id"])

        assert first["added"] == 2
        assert second == {"added": 0, "skipped": 2, "in_library": 0, "errors": 0}
        assert sorted(row["content_type"] for row in user_db.list_requests()) == [
            "audiobook",
            "ebook",
        ]


def test_personal_sync_and_manual_batch_share_an_atomic_quota(user_db, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from shelfmark.core import requests_service

    reader = user_db.create_user(username="reader", role="user")
    user_id = reader["id"]
    user_db.set_user_settings(user_id, {"MAX_PENDING_REQUESTS_PER_USER": 1})
    second_connection = UserDB(user_db.db_path)
    _configure(monkeypatch, HARDCOVER_SYNC_CONTENT_TYPE="both")
    provider = _Provider({1: [[_book(7, "Shelf Book")]]})
    monkeypatch.setattr(hardcover_sync, "_build_provider", lambda _token: provider)
    simultaneous = Barrier(2)
    find_duplicate = requests_service._find_duplicate_pending_request

    def look_up_duplicate(db, **kwargs):
        if kwargs["content_type"] == "ebook":
            simultaneous.wait(timeout=5)
        return find_duplicate(db, **kwargs)

    def manual_create():
        try:
            return requests_service.create_requests(
                second_connection,
                requests=[
                    {
                        "user_id": user_id,
                        "content_type": "ebook",
                        "request_level": "book",
                        "policy_mode": "request_book",
                        "book_data": {
                            "title": "Manual Book",
                            "author": "Someone",
                            "provider": "hardcover",
                            "provider_id": "42",
                        },
                        "max_pending_per_user": 1,
                    }
                ],
            )
        except requests_service.RequestServiceError as exc:
            assert exc.code == "max_pending_reached"
            return []

    with monkeypatch.context() as patch:
        patch.setattr(requests_service, "_find_duplicate_pending_request", look_up_duplicate)
        with ThreadPoolExecutor(max_workers=2) as pool:
            sync = pool.submit(hardcover_sync.sync_wishlist, user_db, user_id=user_id)
            manual = pool.submit(manual_create)
            assert sync.result()["added"] + len(manual.result()) == 1
    assert user_db.count_user_pending_requests(user_id) == 1

    first = user_db.list_requests(user_id=user_id)[0]
    user_db.update_request(first["id"], status="cancelled")
    assert hardcover_sync.sync_wishlist(user_db, user_id=user_id)["added"] == 1
    assert user_db.count_user_pending_requests(user_id) == 1
