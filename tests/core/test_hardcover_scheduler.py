"""Tests for the Hardcover sync scheduler's interval parsing and run gating."""

import threading

import pytest

from shelfmark.core import hardcover_scheduler as scheduler


class _Config:
    def __init__(self, **values):
        self.values = values

    def get(self, key, default=None, user_id=None):
        return self.values.get(key, default)


@pytest.fixture(autouse=True)
def _isolated_scheduler(monkeypatch):
    monkeypatch.setattr(scheduler, "_ctx", {})
    monkeypatch.setattr(scheduler, "_run_lock", threading.Lock())
    monkeypatch.setattr(scheduler, "app_config", _Config())


def _configure(monkeypatch, **values):
    monkeypatch.setattr(scheduler, "app_config", _Config(**values))


@pytest.mark.parametrize(
    ("interval", "unit", "expected"),
    [
        (30, "minutes", 1800),
        (2, "hours", 7200),
        ("1.5", "hours", 5400),
        (0.5, "minutes", 60),
        (6, "fortnights", 6 * 3600),
        ("garbage", "hours", 6 * 3600),
        ([], "hours", 6 * 3600),
    ],
)
def test_interval_seconds(monkeypatch, interval, unit, expected):
    _configure(monkeypatch, HARDCOVER_SYNC_INTERVAL=interval, HARDCOVER_SYNC_INTERVAL_UNIT=unit)

    assert scheduler._interval_seconds() == expected


def test_interval_seconds_defaults_to_six_hours(monkeypatch):
    _configure(monkeypatch)

    assert scheduler._interval_seconds() == 6 * 3600


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({}, False),
        ({"HARDCOVER_SYNC_ENABLED": True}, True),
        ({"AUTO_DOWNLOAD_ENABLED": True}, True),
        ({"HARDCOVER_SYNC_ENABLED": False, "AUTO_DOWNLOAD_ENABLED": False}, False),
    ],
)
def test_enabled(monkeypatch, values, expected):
    _configure(monkeypatch, **values)

    assert scheduler._enabled() is expected


def test_run_once_before_configure_is_unconfigured():
    assert scheduler.run_once() == {"status": "unconfigured"}
    assert scheduler.run_once(force=True) == {"status": "unconfigured"}


def test_run_once_reports_busy_while_another_run_holds_the_lock():
    with scheduler._run_lock:
        assert scheduler.run_once(force=True) == {"status": "busy"}

    assert scheduler.run_once() == {"status": "unconfigured"}


class _FakeUserDB:
    """Only what the sweep needs: the user list it enumerates tokens over."""

    def __init__(self, users=None, pending=None):
        """Hold the users the sweep lists and the requests it reads as pending."""
        self._users = users or []
        self._pending = pending or []

    def list_users(self):
        return list(self._users)

    def list_requests(self, *, status):
        assert status == "pending"
        return list(self._pending)


class TestRunOnce:
    @pytest.fixture
    def calls(self, monkeypatch):
        recorded = {"sync": [], "auto": []}

        def _sync(user_db, **kwargs):
            recorded["sync"].append((user_db, kwargs))
            return {"added": 1}

        def _auto(user_db, **kwargs):
            recorded["auto"].append((user_db, kwargs))
            return {"queued": 1}

        monkeypatch.setattr("shelfmark.core.hardcover_sync.sync_wishlist", _sync)
        monkeypatch.setattr("shelfmark.core.auto_download.auto_download_pending", _auto)
        return recorded

    def test_scheduled_run_skips_sync_when_disabled(self, calls):
        user_db, queue_release = _FakeUserDB(), object()
        scheduler.configure(user_db, queue_release, "/data/users.db")

        result = scheduler.run_once()

        assert result == {"status": "ok", "sync": None, "auto_download": {"queued": 1}}
        assert calls["sync"] == []
        assert calls["auto"] == [
            (
                user_db,
                {
                    "queue_release": queue_release,
                    "db_path": "/data/users.db",
                    "ignore_backoff": False,
                },
            )
        ]

    def test_forced_run_syncs_regardless_of_toggle(self, calls):
        user_db = _FakeUserDB()
        scheduler.configure(user_db, object(), "/data/users.db")

        result = scheduler.run_once(force=True)

        assert result["status"] == "ok"
        assert result["sync"] == {
            "added": 1,
            "skipped": 0,
            "in_library": 0,
            "errors": 0,
            "accounts": 1,
        }
        assert result["auto_download"] == {"queued": 1}
        assert calls["sync"] == [(user_db, {})]
        # Sync now searches every request, whatever the no-match backoff says.
        assert calls["auto"][0][1]["ignore_backoff"] is True

    def test_scheduled_run_syncs_when_enabled(self, monkeypatch, calls):
        _configure(monkeypatch, HARDCOVER_SYNC_ENABLED=True)
        user_db = _FakeUserDB()
        scheduler.configure(user_db, object(), None)

        result = scheduler.run_once()

        assert result["sync"]["added"] == 1
        assert calls["sync"] == [(user_db, {})]

    def test_every_connected_account_syncs_before_the_app_level_token(self, monkeypatch, calls):
        """Connected accounts sync lowest id first, then the app-level token."""
        _configure(monkeypatch, HARDCOVER_SYNC_ENABLED=True)
        user_db = _FakeUserDB([{"id": 7}, {"id": 3}, {"id": 9}])
        monkeypatch.setattr(
            "shelfmark.core.hardcover_sync._user_token",
            lambda _db, user_id: "token" if user_id in {3, 7} else "",
        )
        monkeypatch.setattr("shelfmark.core.hardcover_sync.has_app_level_token", lambda: True)
        scheduler.configure(user_db, object(), "/data/users.db")

        result = scheduler.run_once()

        # Lowest id first, then the app-level pass with no user id.
        assert [kwargs.get("user_id") for _db, kwargs in calls["sync"]] == [3, 7, None]
        assert result["sync"]["added"] == 3
        assert result["sync"]["accounts"] == 3

    def test_admin_scope_syncs_only_admin_accounts_and_their_requests(self, monkeypatch, calls):
        user_db = _FakeUserDB(
            [{"id": 1, "role": "admin"}, {"id": 3, "role": "user"}, {"id": 7, "role": "user"}],
            pending=[{"id": 10, "user_id": 1}, {"id": 11, "user_id": 3}, {"id": 12, "user_id": 7}],
        )
        monkeypatch.setattr(
            "shelfmark.core.hardcover_sync._user_token", lambda _db, _user_id: "token"
        )
        monkeypatch.setattr("shelfmark.core.hardcover_sync.has_app_level_token", lambda: True)
        scheduler.configure(user_db, object(), "/data/users.db")

        result = scheduler.run_once(force=True, scope="admin")

        # The admin's own account, then the app-level pass; users 3 and 7 are not synced.
        assert [kwargs.get("user_id") for _db, kwargs in calls["sync"]] == [1, None]
        assert result["sync"]["accounts"] == 2
        assert calls["auto"][0][1]["only_request_ids"] == frozenset({10})

    def test_admin_scope_with_only_user_tokens_and_no_app_token_is_not_an_error(
        self, monkeypatch, calls
    ):
        """Sync (admin) with only users' tokens and no app token counts no error."""
        user_db = _FakeUserDB([{"id": 1, "role": "admin"}, {"id": 3, "role": "user"}])
        monkeypatch.setattr(
            "shelfmark.core.hardcover_sync._user_token",
            lambda _db, user_id: "token" if user_id == 3 else "",
        )
        monkeypatch.setattr("shelfmark.core.hardcover_sync.has_app_level_token", lambda: False)
        scheduler.configure(user_db, object(), "/data/users.db")

        result = scheduler.run_once(force=True, scope="admin")

        assert calls["sync"] == []
        assert result["sync"]["errors"] == 0
        assert result["sync"]["accounts"] == 0

    def test_all_scope_does_not_limit_auto_download(self, monkeypatch, calls):
        user_db = _FakeUserDB([{"id": 1, "role": "admin"}, {"id": 3, "role": "user"}])
        monkeypatch.setattr(
            "shelfmark.core.hardcover_sync._user_token", lambda _db, _user_id: "token"
        )
        monkeypatch.setattr("shelfmark.core.hardcover_sync.has_app_level_token", lambda: True)
        scheduler.configure(user_db, object(), "/data/users.db")

        scheduler.run_once(force=True, scope="all")

        assert [kwargs.get("user_id") for _db, kwargs in calls["sync"]] == [1, 3, None]
        assert "only_request_ids" not in calls["auto"][0][1]

    def test_app_level_pass_is_skipped_when_only_accounts_are_connected(self, monkeypatch, calls):
        _configure(monkeypatch, HARDCOVER_SYNC_ENABLED=True)
        user_db = _FakeUserDB([{"id": 7}, {"id": 3}])
        monkeypatch.setattr(
            "shelfmark.core.hardcover_sync._user_token", lambda _db, _user_id: "token"
        )
        monkeypatch.setattr("shelfmark.core.hardcover_sync.has_app_level_token", lambda: False)
        scheduler.configure(user_db, object(), None)

        result = scheduler.run_once()

        assert [kwargs.get("user_id") for _db, kwargs in calls["sync"]] == [3, 7]
        assert result["sync"]["accounts"] == 2
        assert result["sync"]["errors"] == 0

    def test_app_level_pass_still_runs_when_nobody_connected_an_account(self, monkeypatch, calls):
        _configure(monkeypatch, HARDCOVER_SYNC_ENABLED=True)
        user_db = _FakeUserDB([{"id": 1}])
        monkeypatch.setattr("shelfmark.core.hardcover_sync._user_token", lambda _db, _user_id: "")
        monkeypatch.setattr("shelfmark.core.hardcover_sync.has_app_level_token", lambda: False)
        scheduler.configure(user_db, object(), None)

        result = scheduler.run_once()

        assert [kwargs.get("user_id") for _db, kwargs in calls["sync"]] == [None]
        assert result["sync"]["accounts"] == 1

    def test_one_failing_account_does_not_stop_the_sweep(self, monkeypatch, calls):
        """An account whose sync raises is counted as an error and the rest still sync."""
        _configure(monkeypatch, HARDCOVER_SYNC_ENABLED=True)
        user_db = _FakeUserDB([{"id": 1}, {"id": 2}])
        monkeypatch.setattr(
            "shelfmark.core.hardcover_sync._user_token", lambda _db, _user_id: "token"
        )
        monkeypatch.setattr("shelfmark.core.hardcover_sync.has_app_level_token", lambda: True)

        def _sync(user_db_arg, **kwargs):
            """Fail user 1's sync and record every other call."""
            if kwargs.get("user_id") == 1:
                raise RuntimeError("bad token")
            calls["sync"].append((user_db_arg, kwargs))
            return {"added": 1}

        monkeypatch.setattr("shelfmark.core.hardcover_sync.sync_wishlist", _sync)
        scheduler.configure(user_db, object(), None)

        result = scheduler.run_once()

        assert [kwargs.get("user_id") for _db, kwargs in calls["sync"]] == [2, None]
        assert result["sync"]["added"] == 2
        assert result["sync"]["errors"] == 1

    def test_lock_is_released_after_a_run(self, calls):
        scheduler.configure(_FakeUserDB(), object(), None)

        scheduler.run_once()

        assert scheduler._run_lock.locked() is False


class TestTriggerAsync:
    def test_returns_false_while_a_run_is_active(self, monkeypatch):
        def _unexpected(**_kwargs):
            raise AssertionError("run_once must not be scheduled")

        monkeypatch.setattr(scheduler, "run_once", _unexpected)

        with scheduler._run_lock:
            assert scheduler.trigger_async() is False

    @pytest.mark.parametrize("force", [True, False])
    def test_runs_once_in_the_background_with_force_flag(self, monkeypatch, force):
        finished = threading.Event()
        seen = []

        def _run_once(**kwargs):
            seen.append(kwargs)
            finished.set()
            return {"status": "ok"}

        monkeypatch.setattr(scheduler, "run_once", _run_once)

        assert scheduler.trigger_async(force=force) is True
        assert finished.wait(timeout=5)
        assert seen == [{"force": force, "scope": "all"}]


class _Clock:
    """A clock the scheduler's sleeps move, so a wait that is hours long runs instantly."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def monotonic(self) -> float:
        return self.now


def _run_wait(monkeypatch, *, interval, quick, retries):
    clock = _Clock()
    monkeypatch.setattr(scheduler.time, "sleep", clock.sleep)
    monkeypatch.setattr(scheduler.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(scheduler, "_interval_seconds", lambda: interval)
    monkeypatch.setattr(scheduler, "_quick_retry_interval_seconds", lambda: quick)
    monkeypatch.setattr(scheduler, "run_quick_retry", lambda: retries.append(clock.now))
    scheduler._wait_for_next_cycle()
    return clock


def test_the_wait_between_cycles_is_one_sleep_when_the_quick_retry_is_off(monkeypatch):
    retries: list[float] = []

    clock = _run_wait(monkeypatch, interval=3600.0, quick=0.0, retries=retries)

    assert clock.sleeps == [3600.0]
    assert retries == []


def test_failed_downloads_are_looked_at_between_cycles_when_it_is_on(monkeypatch):
    retries: list[float] = []

    clock = _run_wait(monkeypatch, interval=3600.0, quick=900.0, retries=retries)

    assert clock.now == 3600.0
    assert retries == [900.0, 1800.0, 2700.0]  # not again at the cycle itself


def test_a_failing_quick_retry_does_not_stop_the_wait(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(scheduler.time, "sleep", clock.sleep)
    monkeypatch.setattr(scheduler.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(scheduler, "_interval_seconds", lambda: 3600.0)
    monkeypatch.setattr(scheduler, "_quick_retry_interval_seconds", lambda: 1800.0)

    def boom():
        raise RuntimeError("search down")

    monkeypatch.setattr(scheduler, "run_quick_retry", boom)

    scheduler._wait_for_next_cycle()

    assert clock.now == 3600.0


def test_the_quick_retry_interval(monkeypatch):
    monkeypatch.setattr(scheduler, "app_config", _Config(AUTO_DOWNLOAD_FAILURE_RETRY_MINUTES=20))
    assert scheduler._quick_retry_interval_seconds() == 1200.0
    monkeypatch.setattr(scheduler, "app_config", _Config())
    assert scheduler._quick_retry_interval_seconds() == 0.0


def test_the_quick_retry_skips_while_a_cycle_holds_the_lock():
    scheduler._run_lock.acquire()
    try:
        assert scheduler.run_quick_retry() is None
    finally:
        scheduler._run_lock.release()


def test_an_unreadable_interval_does_not_end_the_scheduler_thread(monkeypatch):
    sleeps: list[float] = []

    def _sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) >= 3:
            raise KeyboardInterrupt  # stands in for the end of the test: the loop never returns

    def _wait():
        raise RuntimeError("bad interval")

    monkeypatch.setattr(scheduler.time, "sleep", _sleep)
    monkeypatch.setattr(scheduler, "_enabled", lambda: False)
    monkeypatch.setattr(scheduler, "_wait_for_next_cycle", _wait)

    with pytest.raises(KeyboardInterrupt):
        scheduler._scheduler_loop()

    # Warm-up, then the fallback wait twice: the loop went round again after the failure.
    assert sleeps == [
        scheduler._WARMUP_SECONDS,
        scheduler._FALLBACK_WAIT_SECONDS,
        scheduler._FALLBACK_WAIT_SECONDS,
    ]


def test_a_sweep_isolates_real_provider_accounts_with_an_environment_token(tmp_path, monkeypatch):
    import json

    from requests import Response

    from shelfmark.config.hardcover_sync_settings import hardcover_sync_settings
    from shelfmark.core import cache, hardcover_sync
    from shelfmark.core.settings_registry import load_config_file, save_config_file
    from shelfmark.core.user_db import UserDB
    from shelfmark.metadata_providers import hardcover

    monkeypatch.setenv("HARDCOVER_SYNC_TOKEN", "instance-token")
    monkeypatch.setattr(cache, "_metadata_cache", cache.CacheService())
    # Resolve the deployment token from the real settings registry, including its env rule.
    from shelfmark.core.settings_registry import get_setting_value

    field = next(
        field for field in hardcover_sync_settings() if field.key == "HARDCOVER_SYNC_TOKEN"
    )
    instance_token = get_setting_value(field, "hardcover_sync")
    assert instance_token == "instance-token"
    sync_config = _Config(HARDCOVER_SYNC_TOKEN=instance_token)
    monkeypatch.setattr(hardcover_sync, "app_config", sync_config)
    _configure(monkeypatch, HARDCOVER_SYNC_ENABLED=True)
    monkeypatch.setattr(
        "shelfmark.core.auto_download.auto_download_pending", lambda *_args, **_kwargs: {}
    )
    original_config = load_config_file("hardcover")
    saved_identity = {**original_config, "_connected_user_id": "999", "_connected_username": "old"}
    save_config_file("hardcover", saved_identity)

    db = UserDB(str(tmp_path / "users.db"))
    db.initialize()
    admin = db.create_user(username="root", role="admin")
    expired = db.create_user(username="expired")
    alice = db.create_user(username="alice")
    bob = db.create_user(username="bob")
    db.set_user_settings(expired["id"], {"HARDCOVER_SYNC_TOKEN": "expired-token"})
    db.set_user_settings(alice["id"], {"HARDCOVER_SYNC_TOKEN": "alice-token"})
    db.set_user_settings(bob["id"], {"HARDCOVER_SYNC_TOKEN": "bob-token"})
    scheduler.configure(db, lambda *_args, **_kwargs: (True, None), db.db_path)

    accounts = {
        "instance-token": (99, "instance", 100),
        "expired-token": (90, "expired", 101),
        "alice-token": (91, "alice", 102),
        "bob-token": (92, "bob", 103),
        "rotated-token": (91, "alice", 104),
    }
    identities = []
    shelf_fetches = []

    def post(provider, payload):
        token = provider.session.headers["Authorization"].removeprefix("Bearer ")
        account_id, username, book_id = accounts[token]
        result = Response()
        result.url = hardcover.HARDCOVER_API_URL
        result.status_code = 200
        if "GetCurrentUserBooksByStatus" not in payload["query"]:
            identities.append(token)
            data = {"me": [{"id": account_id, "username": username}]}
        else:
            shelf_fetches.append(token)
            if token == "expired-token":
                result.status_code = 401
                return result
            data = {"me": {"status_books": [{"book": {"id": book_id, "title": f"Book {book_id}"}}]}}
        result._content = json.dumps({"data": data}).encode()
        return result

    monkeypatch.setattr(hardcover.HardcoverProvider, "_post_with_backoff", post)
    try:
        assert scheduler.run_once()["sync"] == {
            "accounts": 4,
            "added": 3,
            "skipped": 0,
            "in_library": 0,
            "errors": 1,
        }
        assert [
            row["book_data"]["provider_id"] for row in db.list_requests(user_id=alice["id"])
        ] == ["102"]
        assert [row["book_data"]["provider_id"] for row in db.list_requests(user_id=bob["id"])] == [
            "103"
        ]
        assert [
            row["book_data"]["provider_id"] for row in db.list_requests(user_id=admin["id"])
        ] == ["100"]
        assert db.list_requests(user_id=expired["id"]) == []

        db.set_user_settings(alice["id"], {"HARDCOVER_SYNC_TOKEN": "rotated-token"})
        assert scheduler.run_once(force=True, scope="all")["sync"]["added"] == 1
        assert identities == [
            "expired-token",
            "alice-token",
            "bob-token",
            "instance-token",
            "expired-token",
            "rotated-token",
            "bob-token",
            "instance-token",
        ]
        assert shelf_fetches == [
            "expired-token",
            "alice-token",
            "bob-token",
            "instance-token",
            "expired-token",
            "rotated-token",
        ]
        assert load_config_file("hardcover") == saved_identity
        rotated = hardcover.HardcoverProvider(api_key="rotated-token", for_sync=True)
        result = rotated._fetch_current_user_books_by_status(1, 1, 25)
        assert result.source_url and "/@alice/" in result.source_url
        assert [book.provider_id for book in result.books] == ["104"]
    finally:
        save_config_file("hardcover", original_config)
