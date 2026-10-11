"""Tests for self-service account edit context and update endpoints."""

import os
import tempfile
from typing import Any
from unittest.mock import patch

import pytest
from flask import Flask

from shelfmark.core.self_user_routes import register_self_user_routes
from shelfmark.core.user_db import UserDB


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "shelfmark.db")


@pytest.fixture
def user_db(db_path):
    db = UserDB(db_path)
    db.initialize()
    return db


@pytest.fixture
def app(user_db):
    test_app = Flask(__name__)
    test_app.config["SECRET_KEY"] = "test-secret"
    test_app.config["TESTING"] = True

    register_self_user_routes(test_app, user_db)
    return test_app


def _authed_client_for_user(app: Flask, user: dict) -> Any:
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user["username"]
        sess["db_user_id"] = user["id"]
        sess["is_admin"] = False
    return client


def _visible_sections_config_get(
    visible_sections: object,
):
    def _get(key: str, default: object = None, user_id: int | None = None) -> object:
        del user_id
        if key == "VISIBLE_SELF_SETTINGS_SECTIONS":
            return visible_sections
        return default

    return _get


def test_users_me_edit_context_respects_visible_sections(app, user_db, monkeypatch):
    user = user_db.create_user(username="alice")
    user_db.set_user_settings(user["id"], {"DESTINATION": "/books/alice"})
    client = _authed_client_for_user(app, user)
    monkeypatch.delenv("INGEST_DIR", raising=False)

    with patch("shelfmark.core.self_user_routes.load_active_auth_mode", return_value="builtin"):
        with patch(
            "shelfmark.core.self_user_routes.app_config.get",
            side_effect=_visible_sections_config_get(["delivery"]),
        ):
            resp = client.get("/api/users/me/edit-context")

    assert resp.status_code == 200
    assert resp.json["visibleUserSettingsSections"] == ["delivery"]
    assert resp.json["deliveryPreferences"]["tab"] == "downloads"
    assert resp.json["deliveryPreferences"]["effective"]["DESTINATION"]["value"] == "/books/alice"
    assert resp.json["deliveryPreferences"]["effective"]["DESTINATION"]["source"] == "user_override"
    assert "DESTINATION" in resp.json["userOverridableKeys"]
    assert resp.json["notificationPreferences"] is None


def test_users_me_edit_context_includes_search_preferences_when_visible(app, user_db):
    user = user_db.create_user(username="alice")
    user_db.set_user_settings(
        user["id"],
        {
            "SEARCH_MODE": "universal",
            "METADATA_PROVIDER": "openlibrary",
            "BOOK_LANGUAGE": ["de", "en"],
        },
    )
    client = _authed_client_for_user(app, user)

    with patch("shelfmark.core.self_user_routes.load_active_auth_mode", return_value="builtin"):
        with patch(
            "shelfmark.core.self_user_routes.app_config.get",
            side_effect=_visible_sections_config_get(["delivery", "search"]),
        ):
            resp = client.get("/api/users/me/edit-context")

    assert resp.status_code == 200
    assert resp.json["visibleUserSettingsSections"] == ["delivery", "search"]
    assert resp.json["deliveryPreferences"]["tab"] == "downloads"
    assert resp.json["searchPreferences"]["tab"] == "search_mode"
    assert resp.json["searchPreferences"]["effective"]["SEARCH_MODE"]["value"] == "universal"
    assert resp.json["searchPreferences"]["effective"]["SEARCH_MODE"]["source"] == "user_override"
    assert resp.json["searchPreferences"]["effective"]["BOOK_LANGUAGE"]["value"] == ["de", "en"]
    assert resp.json["searchPreferences"]["effective"]["BOOK_LANGUAGE"]["source"] == (
        "user_override"
    )
    assert "SEARCH_MODE" in resp.json["userOverridableKeys"]
    assert "METADATA_PROVIDER" in resp.json["userOverridableKeys"]
    assert "BOOK_LANGUAGE" in resp.json["userOverridableKeys"]
    assert resp.json["notificationPreferences"] is None
    assert resp.json["userOverridableKeys"] == sorted(resp.json["userOverridableKeys"])


def test_users_me_edit_context_falls_back_to_default_sections_for_invalid_config(app, user_db):
    user = user_db.create_user(username="alice")
    client = _authed_client_for_user(app, user)

    with patch("shelfmark.core.self_user_routes.load_active_auth_mode", return_value="builtin"):
        with patch(
            "shelfmark.core.self_user_routes.app_config.get",
            side_effect=_visible_sections_config_get("bogus"),
        ):
            resp = client.get("/api/users/me/edit-context")

    assert resp.status_code == 200
    assert resp.json["visibleUserSettingsSections"] == [
        "delivery",
        "search",
        "notifications",
        "hardcover",
    ]
    assert resp.json["deliveryPreferences"] is not None
    assert resp.json["searchPreferences"] is not None
    assert resp.json["notificationPreferences"] is not None


def test_users_me_update_rejects_hidden_section_settings(app, user_db):
    user = user_db.create_user(username="alice")
    client = _authed_client_for_user(app, user)

    with patch("shelfmark.core.self_user_routes.load_active_auth_mode", return_value="builtin"):
        with patch(
            "shelfmark.core.self_user_routes.app_config.get",
            side_effect=_visible_sections_config_get(["delivery"]),
        ):
            resp = client.put(
                "/api/users/me",
                json={
                    "settings": {
                        "USER_NOTIFICATION_ROUTES": [
                            {"event": "all", "url": "ntfys://ntfy.sh/alice"}
                        ],
                    }
                },
            )

    assert resp.status_code == 400
    assert resp.json["error"] == "Some settings are admin-only"
    assert "Setting not user-overridable: USER_NOTIFICATION_ROUTES" in resp.json["details"]


def test_users_me_update_accepts_visible_section_settings(app, user_db):
    user = user_db.create_user(username="alice")
    client = _authed_client_for_user(app, user)

    with patch("shelfmark.core.self_user_routes.load_active_auth_mode", return_value="builtin"):
        with patch(
            "shelfmark.core.self_user_routes.app_config.get",
            side_effect=_visible_sections_config_get(["delivery"]),
        ):
            resp = client.put(
                "/api/users/me",
                json={"settings": {"DESTINATION": "/books/alice"}},
            )

    assert resp.status_code == 200
    assert user_db.get_user_settings(user["id"]).get("DESTINATION") == "/books/alice"
    assert resp.json["settings"]["DESTINATION"] == "/books/alice"


def test_users_me_update_accepts_book_language_when_search_section_visible(app, user_db):
    user = user_db.create_user(username="alice")
    client = _authed_client_for_user(app, user)

    with patch("shelfmark.core.self_user_routes.load_active_auth_mode", return_value="builtin"):
        with patch(
            "shelfmark.core.self_user_routes.app_config.get",
            side_effect=_visible_sections_config_get(["search"]),
        ):
            resp = client.put(
                "/api/users/me",
                json={"settings": {"BOOK_LANGUAGE": ["German", "en"]}},
            )

    assert resp.status_code == 200
    assert user_db.get_user_settings(user["id"])["BOOK_LANGUAGE"] == ["de", "en"]


def test_users_me_update_rejects_book_language_when_search_section_hidden(app, user_db):
    user = user_db.create_user(username="alice")
    client = _authed_client_for_user(app, user)

    with patch("shelfmark.core.self_user_routes.load_active_auth_mode", return_value="builtin"):
        with patch(
            "shelfmark.core.self_user_routes.app_config.get",
            side_effect=_visible_sections_config_get(["delivery"]),
        ):
            resp = client.put(
                "/api/users/me",
                json={"settings": {"BOOK_LANGUAGE": ["de"]}},
            )

    assert resp.status_code == 400
    assert resp.json["error"] == "Some settings are admin-only"
    assert user_db.get_user_settings(user["id"]) == {}


def test_users_me_update_rejects_non_object_settings_payload(app, user_db):
    user = user_db.create_user(username="alice")
    client = _authed_client_for_user(app, user)

    with patch("shelfmark.core.self_user_routes.load_active_auth_mode", return_value="builtin"):
        with patch(
            "shelfmark.core.self_user_routes.app_config.get",
            side_effect=_visible_sections_config_get(["delivery"]),
        ):
            resp = client.put("/api/users/me", json={"settings": ["DESTINATION"]})

    assert resp.status_code == 400
    assert resp.json["error"] == "Settings must be an object"


def test_users_me_update_rejects_oidc_email_change(app, user_db):
    user = user_db.create_user(
        username="oidc-user",
        oidc_subject="oidc-sub-123",
        auth_source="oidc",
    )
    client = _authed_client_for_user(app, user)

    with patch("shelfmark.core.self_user_routes.load_active_auth_mode", return_value="builtin"):
        resp = client.put("/api/users/me", json={"email": "new@example.com"})

    assert resp.status_code == 400
    assert resp.json["error"] == "Cannot change email for OIDC users"
    assert user_db.get_user(user_id=user["id"])["email"] is None


def test_users_me_update_keeps_password_and_profile_when_settings_rejected(app, user_db):
    user = user_db.create_user(
        username="alice",
        display_name="Alice Old",
        password_hash="old_hash",
    )
    client = _authed_client_for_user(app, user)

    with patch("shelfmark.core.self_user_routes.load_active_auth_mode", return_value="builtin"):
        with patch(
            "shelfmark.core.self_user_routes.app_config.get",
            side_effect=_visible_sections_config_get(["delivery"]),
        ):
            resp = client.put(
                "/api/users/me",
                json={
                    "password": "newpass99",
                    "display_name": "Alice New",
                    "settings": {
                        "USER_NOTIFICATION_ROUTES": [
                            {"event": "all", "url": "ntfys://ntfy.sh/alice"}
                        ],
                    },
                },
            )

    assert resp.status_code == 400
    assert resp.json["error"] == "Some settings are admin-only"

    stored = user_db.get_user(user_id=user["id"])
    assert stored["password_hash"] == "old_hash"
    assert stored["display_name"] == "Alice Old"


def test_users_me_update_applies_password_profile_and_settings_together(app, user_db):
    user = user_db.create_user(
        username="alice",
        display_name="Alice Old",
        password_hash="old_hash",
    )
    client = _authed_client_for_user(app, user)

    with patch("shelfmark.core.self_user_routes.load_active_auth_mode", return_value="builtin"):
        with patch(
            "shelfmark.core.self_user_routes.app_config.get",
            side_effect=_visible_sections_config_get(["delivery"]),
        ):
            resp = client.put(
                "/api/users/me",
                json={
                    "password": "newpass99",
                    "display_name": "Alice New",
                    "settings": {"DESTINATION": "/books/alice"},
                },
            )

    assert resp.status_code == 200

    stored = user_db.get_user(user_id=user["id"])
    assert stored["password_hash"] != "old_hash"
    assert stored["display_name"] == "Alice New"
    assert user_db.get_user_settings(user["id"])["DESTINATION"] == "/books/alice"


def _hardcover_config_get(global_token: str = "global-token-value"):
    def _get(key: str, default: object = None, user_id: int | None = None) -> object:
        del user_id
        if key == "VISIBLE_SELF_SETTINGS_SECTIONS":
            return ["delivery", "hardcover"]
        if key == "HARDCOVER_SYNC_TOKEN":
            return global_token
        return default

    return _get


def test_users_me_edit_context_masks_secret_settings(app, user_db, monkeypatch):
    from shelfmark.core.user_settings_overrides import SECRET_PLACEHOLDER

    monkeypatch.delenv("HARDCOVER_SYNC_TOKEN", raising=False)
    user = user_db.create_user(username="alice")
    user_db.set_user_settings(user["id"], {"HARDCOVER_SYNC_TOKEN": "alice-token-value"})
    client = _authed_client_for_user(app, user)

    with patch("shelfmark.core.self_user_routes.load_active_auth_mode", return_value="builtin"):
        with patch(
            "shelfmark.core.self_user_routes.app_config.get",
            side_effect=_hardcover_config_get(),
        ):
            resp = client.get("/api/users/me/edit-context")

    assert resp.status_code == 200
    assert resp.json["user"]["settings"]["HARDCOVER_SYNC_TOKEN"] == SECRET_PLACEHOLDER
    hardcover = resp.json["hardcoverPreferences"]
    assert hardcover["userOverrides"]["HARDCOVER_SYNC_TOKEN"] == SECRET_PLACEHOLDER
    assert hardcover["globalValues"]["HARDCOVER_SYNC_TOKEN"] == SECRET_PLACEHOLDER
    assert hardcover["effective"]["HARDCOVER_SYNC_TOKEN"] == {
        "value": SECRET_PLACEHOLDER,
        "source": "user_override",
    }
    body = resp.get_data(as_text=True)
    assert "alice-token-value" not in body
    assert "global-token-value" not in body


def test_users_me_update_keeps_the_stored_secret_when_the_placeholder_comes_back(app, user_db):
    from shelfmark.core.user_settings_overrides import SECRET_PLACEHOLDER

    user = user_db.create_user(username="alice")
    user_db.set_user_settings(user["id"], {"HARDCOVER_SYNC_TOKEN": "alice-token-value"})
    client = _authed_client_for_user(app, user)

    with patch("shelfmark.core.self_user_routes.load_active_auth_mode", return_value="builtin"):
        with patch(
            "shelfmark.core.self_user_routes.app_config.get",
            side_effect=_hardcover_config_get(),
        ):
            resp = client.put(
                "/api/users/me",
                json={
                    "settings": {
                        "HARDCOVER_SYNC_TOKEN": SECRET_PLACEHOLDER,
                        "DESTINATION": "/books/alice",
                    }
                },
            )

    assert resp.status_code == 200
    stored = user_db.get_user_settings(user["id"])
    assert stored["HARDCOVER_SYNC_TOKEN"] == "alice-token-value"
    assert stored["DESTINATION"] == "/books/alice"
    assert resp.json["settings"]["HARDCOVER_SYNC_TOKEN"] == SECRET_PLACEHOLDER
    assert "alice-token-value" not in resp.get_data(as_text=True)


def test_users_me_update_stores_a_new_secret_and_clears_it_on_null(app, user_db):
    user = user_db.create_user(username="alice")
    client = _authed_client_for_user(app, user)

    with patch("shelfmark.core.self_user_routes.load_active_auth_mode", return_value="builtin"):
        with patch(
            "shelfmark.core.self_user_routes.app_config.get",
            side_effect=_hardcover_config_get(),
        ):
            saved = client.put(
                "/api/users/me", json={"settings": {"HARDCOVER_SYNC_TOKEN": "new-token-value"}}
            )
            assert saved.status_code == 200
            assert user_db.get_user_settings(user["id"])["HARDCOVER_SYNC_TOKEN"] == (
                "new-token-value"
            )
            assert "new-token-value" not in saved.get_data(as_text=True)

            cleared = client.put("/api/users/me", json={"settings": {"HARDCOVER_SYNC_TOKEN": None}})

    assert cleared.status_code == 200
    assert "HARDCOVER_SYNC_TOKEN" not in user_db.get_user_settings(user["id"])


def test_users_me_secret_returns_only_the_callers_own_override(app, user_db):
    alice = user_db.create_user(username="alice")
    user_db.set_user_settings(alice["id"], {"HARDCOVER_SYNC_TOKEN": "alice-token-value"})
    bob = user_db.create_user(username="bob")

    with patch("shelfmark.core.self_user_routes.load_active_auth_mode", return_value="builtin"):
        with patch(
            "shelfmark.core.self_user_routes.app_config.get",
            side_effect=_hardcover_config_get(),
        ):
            alice_resp = _authed_client_for_user(app, alice).get(
                "/api/users/me/secrets/HARDCOVER_SYNC_TOKEN"
            )
            bob_resp = _authed_client_for_user(app, bob).get(
                "/api/users/me/secrets/HARDCOVER_SYNC_TOKEN"
            )

    assert alice_resp.status_code == 200
    assert alice_resp.json == {"key": "HARDCOVER_SYNC_TOKEN", "value": "alice-token-value"}
    assert bob_resp.status_code == 200
    assert bob_resp.json == {"key": "HARDCOVER_SYNC_TOKEN", "value": ""}


def test_users_me_secret_rejects_anything_but_a_visible_password_field(app, user_db):
    user = user_db.create_user(username="alice")
    user_db.set_user_settings(
        user["id"], {"HARDCOVER_SYNC_TOKEN": "alice-token-value", "DESTINATION": "/books/alice"}
    )
    client = _authed_client_for_user(app, user)

    with patch("shelfmark.core.self_user_routes.load_active_auth_mode", return_value="builtin"):
        with patch(
            "shelfmark.core.self_user_routes.app_config.get",
            side_effect=_hardcover_config_get(),
        ):
            plain_field = client.get("/api/users/me/secrets/DESTINATION")
            unknown = client.get("/api/users/me/secrets/NO_SUCH_SETTING")
        with patch(
            "shelfmark.core.self_user_routes.app_config.get",
            side_effect=_visible_sections_config_get(["delivery"]),
        ):
            hidden_section = client.get("/api/users/me/secrets/HARDCOVER_SYNC_TOKEN")
        anonymous = app.test_client().get("/api/users/me/secrets/HARDCOVER_SYNC_TOKEN")

    assert plain_field.status_code == 404
    assert unknown.status_code == 404
    assert hidden_section.status_code == 404
    assert anonymous.status_code == 401
    for resp in (plain_field, unknown, hidden_section, anonymous):
        assert "alice-token-value" not in resp.get_data(as_text=True)
        assert "/books/alice" not in resp.get_data(as_text=True)
