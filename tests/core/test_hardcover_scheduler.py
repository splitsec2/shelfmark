"""Tests for the Hardcover sync scheduler's interval parsing and run gating."""

import threading

import pytest

from shelfmark.core import hardcover_scheduler as scheduler
from tests.core.fakes import FakeConfig

pytestmark = pytest.mark.usefixtures("fake_app_config")


@pytest.fixture(autouse=True)
def _isolated_scheduler(monkeypatch):
    monkeypatch.setattr(scheduler, "_ctx", {})
    monkeypatch.setattr(scheduler, "_run_lock", threading.Lock())
    monkeypatch.setattr(scheduler, "app_config", FakeConfig())
    monkeypatch.setattr(scheduler, "_state", scheduler._new_state())
    monkeypatch.setattr(scheduler, "_thread", None)


def _configure(monkeypatch, **values):
    monkeypatch.setattr(scheduler, "app_config", FakeConfig(**values))


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

    def __init__(self, users=None):
        self._users = users or []

    def list_users(self):
        return list(self._users)


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
            (user_db, {"queue_release": queue_release, "db_path": "/data/users.db"})
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
        assert calls["sync"] == [(user_db, {"db_path": "/data/users.db"})]

    def test_scheduled_run_syncs_when_enabled(self, monkeypatch, calls):
        _configure(monkeypatch, HARDCOVER_SYNC_ENABLED=True)
        user_db = _FakeUserDB()
        scheduler.configure(user_db, object(), None)

        result = scheduler.run_once()

        assert result["sync"]["added"] == 1
        assert calls["sync"] == [(user_db, {"db_path": None})]

    def test_every_connected_account_syncs_before_the_app_level_token(self, monkeypatch, calls):
        _configure(monkeypatch, HARDCOVER_SYNC_ENABLED=True)
        user_db = _FakeUserDB([{"id": 7}, {"id": 3}, {"id": 9}])
        monkeypatch.setattr(
            "shelfmark.core.hardcover_sync._user_token",
            lambda user_id: "token" if user_id in {3, 7} else "",
        )
        scheduler.configure(user_db, object(), "/data/users.db")

        result = scheduler.run_once()

        # Lowest id first, then the app-level pass with no user id.
        assert [kwargs.get("user_id") for _db, kwargs in calls["sync"]] == [3, 7, None]
        assert result["sync"]["added"] == 3
        assert result["sync"]["accounts"] == 3

    def test_one_failing_account_does_not_stop_the_sweep(self, monkeypatch, calls):
        _configure(monkeypatch, HARDCOVER_SYNC_ENABLED=True)
        user_db = _FakeUserDB([{"id": 1}, {"id": 2}])
        monkeypatch.setattr("shelfmark.core.hardcover_sync._user_token", lambda _user_id: "token")

        def _sync(user_db_arg, **kwargs):
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
        assert seen == [{"force": force}]


class TestStatus:
    """What /api/stats and /api/health report about the background cycle."""

    NOW = 1_000_000.0

    @pytest.fixture
    def clock(self, monkeypatch):
        now = [self.NOW]
        monkeypatch.setattr(scheduler, "_now", lambda: now[0])
        monkeypatch.setattr(scheduler, "_state", scheduler._new_state())
        return now

    @pytest.fixture
    def alive(self, monkeypatch):
        class _Thread:
            def is_alive(self):
                return True

        monkeypatch.setattr(scheduler, "_thread", _Thread())

    @pytest.fixture
    def stubs(self, monkeypatch):
        results = {"sync": {"added": 2, "errors": 0}, "auto": {"queued": 1, "error": 0}}

        monkeypatch.setattr(
            "shelfmark.core.hardcover_sync.sync_wishlist", lambda *_a, **_k: results["sync"]
        )

        def _auto(*_a, **_k):
            if isinstance(results["auto"], Exception):
                raise results["auto"]
            return results["auto"]

        monkeypatch.setattr("shelfmark.core.auto_download.auto_download_pending", _auto)
        scheduler.configure(_FakeUserDB(), object(), None)
        _configure(monkeypatch, HARDCOVER_SYNC_ENABLED=True)
        return results

    def test_disabled_scheduler_is_healthy_and_says_so(self, clock):
        status = scheduler.status()

        assert status["enabled"] is False
        assert status["healthy"] is True
        assert status["last_cycle_at"] is None

    def test_a_clean_cycle_is_recorded(self, clock, alive, stubs):
        scheduler.run_once()
        clock[0] += 120

        status = scheduler.status()

        assert status["last_cycle_errors"] == 0
        assert status["seconds_since_last_cycle"] == 120
        assert status["consecutive_failed_cycles"] == 0
        assert status["healthy"] is True
        assert status["last_cycle_at"].startswith("1970-01-12")

    def test_errors_inside_a_cycle_are_counted_and_unhealthy(self, clock, alive, stubs):
        stubs["sync"] = {"added": 0, "errors": 2}
        stubs["auto"] = {"queued": 0, "error": 3}

        scheduler.run_once()
        status = scheduler.status()

        assert status["last_cycle_errors"] == 5
        assert status["consecutive_failed_cycles"] == 1
        assert status["healthy"] is False
        assert "5 error" in status["problems"][0]

    def test_a_clean_cycle_resets_the_failure_streak(self, clock, alive, stubs):
        stubs["auto"] = {"queued": 0, "error": 1}
        scheduler.run_once()
        scheduler.run_once()
        assert scheduler.status()["consecutive_failed_cycles"] == 2

        stubs["auto"] = {"queued": 0, "error": 0}
        scheduler.run_once()

        assert scheduler.status()["consecutive_failed_cycles"] == 0

    def test_a_cycle_that_raises_is_a_failed_cycle_and_still_propagates(self, clock, alive, stubs):
        stubs["auto"] = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            scheduler.run_once()
        status = scheduler.status()

        assert status["consecutive_failed_cycles"] == 1
        assert status["last_cycle_errors"] == 1
        assert status["healthy"] is False

    def test_busy_and_unconfigured_runs_are_not_cycles(self, clock, alive):
        assert scheduler.run_once() == {"status": "unconfigured"}

        assert scheduler.status()["last_cycle_at"] is None

    def test_overdue_after_two_intervals(self, clock, alive, stubs):
        scheduler.run_once()
        clock[0] += 2 * 6 * 3600 + 1

        status = scheduler.status()

        assert status["healthy"] is False
        assert "no cycle" in status["problems"][0]

    def test_not_yet_overdue_just_inside_two_intervals(self, clock, alive, stubs):
        scheduler.run_once()
        clock[0] += 2 * 6 * 3600 - 1

        assert scheduler.status()["healthy"] is True

    def test_a_dead_thread_is_unhealthy_when_enabled(self, clock, stubs):
        status = scheduler.status()

        assert status["thread_alive"] is False
        assert status["healthy"] is False
        assert any("thread" in problem for problem in status["problems"])

    def test_no_cycle_yet_is_given_a_grace_period_after_startup(self, clock, alive, stubs):
        assert scheduler.status()["healthy"] is True

        clock[0] += 2 * 6 * 3600 + scheduler._WARMUP_SECONDS + 1

        status = scheduler.status()
        assert status["healthy"] is False
        assert "no cycle" in status["problems"][0]
