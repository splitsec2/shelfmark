"""Tests for user override precedence and effective user-preference payloads."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from shelfmark.core.config import config


def _download_field(key: str):
    import shelfmark.config.settings  # noqa: F401
    from shelfmark.core import settings_registry

    return settings_registry.get_settings_field_map()[key][0]


def test_get_prefers_env_over_user_override(monkeypatch):
    field = _download_field("DESTINATION")

    monkeypatch.setattr(config, "_ensure_loaded", lambda: None)
    monkeypatch.setattr(config, "_cache", {"DESTINATION": "/env/books"})
    monkeypatch.setattr(config, "_field_map", {"DESTINATION": (field, "downloads")})
    monkeypatch.setattr(config, "_get_user_override", lambda user_id, key: "/user/books")
    monkeypatch.setattr(
        "shelfmark.core.config._get_registry",
        lambda: SimpleNamespace(is_value_from_env=lambda field: True),
    )

    assert config.get("DESTINATION", "/default", user_id=10) == "/env/books"


def test_get_uses_user_override_when_not_from_env(monkeypatch):
    field = _download_field("DESTINATION")

    monkeypatch.setattr(config, "_ensure_loaded", lambda: None)
    monkeypatch.setattr(config, "_cache", {"DESTINATION": "/global/books"})
    monkeypatch.setattr(config, "_field_map", {"DESTINATION": (field, "downloads")})
    monkeypatch.setattr(config, "_get_user_override", lambda user_id, key: "/user/books")
    monkeypatch.setattr(
        "shelfmark.core.config._get_registry",
        lambda: SimpleNamespace(is_value_from_env=lambda field: False),
    )

    assert config.get("DESTINATION", "/default", user_id=10) == "/user/books"


def test_get_ignores_user_override_for_non_overridable_field(monkeypatch):
    field = _download_field("FILE_ORGANIZATION")

    monkeypatch.setattr(config, "_ensure_loaded", lambda: None)
    monkeypatch.setattr(config, "_cache", {"FILE_ORGANIZATION": "rename"})
    monkeypatch.setattr(
        config,
        "_field_map",
        {"FILE_ORGANIZATION": (field, "downloads")},
    )
    monkeypatch.setattr(config, "_get_user_override", lambda user_id, key: "organize")
    monkeypatch.setattr(
        "shelfmark.core.config._get_registry",
        lambda: SimpleNamespace(is_value_from_env=lambda field: False),
    )

    assert config.get("FILE_ORGANIZATION", "rename", user_id=10) == "rename"


def test_get_keeps_empty_string_override(monkeypatch):
    field = _download_field("DESTINATION_AUDIOBOOK")

    monkeypatch.setattr(config, "_ensure_loaded", lambda: None)
    monkeypatch.setattr(config, "_cache", {"DESTINATION_AUDIOBOOK": "/global/audiobooks"})
    monkeypatch.setattr(
        config,
        "_field_map",
        {"DESTINATION_AUDIOBOOK": (field, "downloads")},
    )
    monkeypatch.setattr(config, "_get_user_override", lambda user_id, key: "")
    monkeypatch.setattr(
        "shelfmark.core.config._get_registry",
        lambda: SimpleNamespace(is_value_from_env=lambda field: False),
    )

    assert config.get("DESTINATION_AUDIOBOOK", "/default", user_id=10) == ""


def test_build_user_preferences_payload_reports_effective_sources(monkeypatch):
    import shelfmark.config.settings  # noqa: F401
    from shelfmark.core import settings_registry
    from shelfmark.core.user_settings_overrides import build_user_preferences_payload

    user_db = SimpleNamespace(
        get_user_settings=lambda user_id: {
            "DESTINATION": "/user/books",
        }
    )

    def fake_get(key, default=None, user_id=None):
        values = {
            "DESTINATION": "/global/books",
            "BOOKS_OUTPUT_MODE": "folder",
            "EMAIL_RECIPIENT": "global@example.com",
        }
        return values.get(key, default)

    with (
        patch(
            "shelfmark.core.user_settings_overrides.get_settings_registry",
            return_value=settings_registry,
        ),
        patch(
            "shelfmark.core.user_settings_overrides.load_config_file",
            return_value={
                "DESTINATION": "/global/books",
                "BOOKS_OUTPUT_MODE": "folder",
                "EMAIL_RECIPIENT": "global@example.com",
            },
        ),
        patch.object(config, "get", side_effect=fake_get),
        patch.object(
            settings_registry,
            "is_value_from_env",
            side_effect=lambda field: field.key == "BOOKS_OUTPUT_MODE",
        ),
    ):
        payload = build_user_preferences_payload(user_db, 7, "downloads")

    assert payload["tab"] == "downloads"
    assert payload["userOverrides"] == {"DESTINATION": "/user/books"}
    assert payload["globalValues"]["DESTINATION"] == "/global/books"
    assert payload["effective"]["DESTINATION"] == {
        "value": "/user/books",
        "source": "user_override",
    }
    assert payload["effective"]["BOOKS_OUTPUT_MODE"] == {
        "value": "folder",
        "source": "env_var",
    }
    assert payload["effective"]["EMAIL_RECIPIENT"] == {
        "value": "global@example.com",
        "source": "global_config",
    }

    fields_by_key = {field["key"]: field for field in payload["fields"]}
    assert fields_by_key["DESTINATION"]["fromEnv"] is False
    assert fields_by_key["BOOKS_OUTPUT_MODE"]["fromEnv"] is True


def test_build_user_preferences_payload_carries_the_language_default():
    """BOOK_LANGUAGE rides along with the other search preferences on its tab."""
    import shelfmark.config.settings  # noqa: F401
    from shelfmark.core.user_settings_overrides import build_user_preferences_payload

    user_db = SimpleNamespace(get_user_settings=lambda user_id: {"BOOK_LANGUAGE": ["de", "en"]})

    payload = build_user_preferences_payload(user_db, 7, "search_mode")

    assert payload["tab"] == "search_mode"
    assert {"SEARCH_MODE", "BOOK_LANGUAGE"}.issubset(payload["keys"])
    assert payload["userOverrides"] == {"BOOK_LANGUAGE": ["de", "en"]}
    assert payload["effective"]["BOOK_LANGUAGE"] == {
        "value": ["de", "en"],
        "source": "user_override",
    }

    fields_by_key = {field["key"]: field for field in payload["fields"]}
    assert fields_by_key["BOOK_LANGUAGE"]["type"] == "MultiSelectField"
    assert fields_by_key["BOOK_LANGUAGE"]["options"]


def test_build_user_preferences_payload_masks_password_fields(monkeypatch):
    """A PasswordField value never leaves as itself; every copy becomes the placeholder."""
    import shelfmark.config.settings  # noqa: F401
    from shelfmark.core.user_settings_overrides import (
        SECRET_PLACEHOLDER,
        build_user_preferences_payload,
    )

    monkeypatch.delenv("HARDCOVER_SYNC_TOKEN", raising=False)
    user_db = SimpleNamespace(
        get_user_settings=lambda user_id: {"HARDCOVER_SYNC_TOKEN": "user-token-value"}
    )

    def fake_get(key, default=None, user_id=None):
        if key == "HARDCOVER_SYNC_TOKEN":
            return "user-token-value" if user_id is not None else "global-token-value"
        return default

    with (
        patch(
            "shelfmark.core.user_settings_overrides.load_config_file",
            return_value={"HARDCOVER_SYNC_TOKEN": "global-token-value"},
        ),
        patch.object(config, "get", side_effect=fake_get),
    ):
        payload = build_user_preferences_payload(user_db, 7, "hardcover_sync")

    assert payload["userOverrides"] == {"HARDCOVER_SYNC_TOKEN": SECRET_PLACEHOLDER}
    assert payload["globalValues"]["HARDCOVER_SYNC_TOKEN"] == SECRET_PLACEHOLDER
    assert payload["effective"]["HARDCOVER_SYNC_TOKEN"] == {
        "value": SECRET_PLACEHOLDER,
        "source": "user_override",
    }
    assert "user-token-value" not in repr(payload)
    assert "global-token-value" not in repr(payload)


def test_build_user_preferences_payload_leaves_an_unset_secret_empty(monkeypatch):
    """No stored secret means no placeholder either, so a client can tell the two apart."""
    import shelfmark.config.settings  # noqa: F401
    from shelfmark.core.user_settings_overrides import (
        SECRET_PLACEHOLDER,
        build_user_preferences_payload,
    )

    monkeypatch.delenv("HARDCOVER_SYNC_TOKEN", raising=False)
    user_db = SimpleNamespace(get_user_settings=lambda user_id: {})

    with (
        patch("shelfmark.core.user_settings_overrides.load_config_file", return_value={}),
        patch.object(config, "get", side_effect=lambda key, default=None, user_id=None: default),
    ):
        payload = build_user_preferences_payload(user_db, 7, "hardcover_sync")

    assert payload["userOverrides"] == {}
    assert not payload["globalValues"]["HARDCOVER_SYNC_TOKEN"]
    assert payload["effective"]["HARDCOVER_SYNC_TOKEN"]["value"] != SECRET_PLACEHOLDER


def test_mask_secret_settings_masks_only_password_fields():
    import shelfmark.config.settings  # noqa: F401
    from shelfmark.core.settings_registry import PasswordField, TextField
    from shelfmark.core.user_settings_overrides import (
        SECRET_PLACEHOLDER,
        is_masked_secret,
        mask_secret_settings,
    )

    masked = mask_secret_settings(
        {"HARDCOVER_SYNC_TOKEN": "user-token-value", "DESTINATION": "/books", "NOT_A_SETTING": 1}
    )

    assert masked == {
        "HARDCOVER_SYNC_TOKEN": SECRET_PLACEHOLDER,
        "DESTINATION": "/books",
        "NOT_A_SETTING": 1,
    }
    assert mask_secret_settings({"HARDCOVER_SYNC_TOKEN": ""}) == {"HARDCOVER_SYNC_TOKEN": ""}

    secret = PasswordField(key="k", label="k")
    plain = TextField(key="k", label="k")
    assert is_masked_secret(secret, SECRET_PLACEHOLDER) is True
    assert is_masked_secret(secret, "user-token-value") is False
    assert is_masked_secret(plain, SECRET_PLACEHOLDER) is False
