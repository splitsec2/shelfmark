"""Tests for the Library Check section of the Hardcover Sync settings tab."""

from __future__ import annotations

from typing import Any

import pytest

from shelfmark.config import hardcover_sync_settings
from shelfmark.core import settings_registry
from shelfmark.core.settings_registry import (
    ActionButton,
    CheckboxField,
    HeadingField,
    PasswordField,
    TextField,
)


def _field_map() -> dict[str, Any]:
    return {field.key: field for field in hardcover_sync_settings.hardcover_sync_settings()}


def test_library_check_section_covers_both_providers() -> None:
    fields = _field_map()

    heading = fields["library_check_heading"]
    assert isinstance(heading, HeadingField)
    assert heading.title == "Library Check"
    assert "Audiobookshelf" in heading.description
    assert "Calibre" in heading.description


def test_audiobookshelf_fields_are_unchanged() -> None:
    fields = _field_map()

    assert isinstance(fields["LIBRARY_CHECK_ENABLED"], CheckboxField)
    assert fields["LIBRARY_CHECK_ENABLED"].default is False
    assert isinstance(fields["AUDIOBOOKSHELF_URL"], TextField)
    assert isinstance(fields["AUDIOBOOKSHELF_TOKEN"], PasswordField)
    assert isinstance(fields["AUDIOBOOKSHELF_LIBRARY_IDS"], TextField)
    assert isinstance(fields["test_library_connection"], ActionButton)


def test_calibre_fields_and_defaults() -> None:
    fields = _field_map()

    enabled = fields["LIBRARY_CHECK_CALIBRE_ENABLED"]
    assert isinstance(enabled, CheckboxField)
    assert enabled.default is False

    path = fields["CALIBRE_LIBRARY_DB_PATH"]
    assert isinstance(path, TextField)
    assert path.default == "/calibre-library/metadata.db"
    assert ":ro" in path.description

    assert isinstance(fields["test_calibre_library"], ActionButton)


def test_calibre_fields_follow_the_audiobookshelf_ones() -> None:
    keys = [field.key for field in hardcover_sync_settings.hardcover_sync_settings()]

    assert keys.index("library_check_heading") < keys.index("LIBRARY_CHECK_ENABLED")
    assert keys.index("test_library_connection") < keys.index("LIBRARY_CHECK_CALIBRE_ENABLED")
    assert keys.index("test_calibre_library") < keys.index("cross_format_heading")
    assert keys.index("apply_cross_format_tags") < keys.index("sync_now")


def test_cross_format_fields_and_defaults() -> None:
    fields = _field_map()

    heading = fields["cross_format_heading"]
    assert isinstance(heading, HeadingField)
    assert "calibredb" in heading.description

    enabled = fields["CROSS_FORMAT_ABS_TAGGING_ENABLED"]
    assert isinstance(enabled, CheckboxField)
    assert enabled.default is False

    tag = fields["CROSS_FORMAT_ABS_TAG"]
    assert isinstance(tag, TextField)
    assert tag.default == "ebook-in-library"

    assert isinstance(fields["preview_cross_format_tags"], ActionButton)
    assert isinstance(fields["apply_cross_format_tags"], ActionButton)


def test_preview_button_dry_runs_with_the_form_values(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[bool, dict[str, Any] | None]] = []

    def fake_sync(*, dry_run: bool, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        seen.append((dry_run, overrides))
        return {"summary": True}

    monkeypatch.setattr("shelfmark.core.cross_format.sync_audiobookshelf_tags", fake_sync)
    monkeypatch.setattr("shelfmark.core.cross_format.describe_summary", lambda s: "2 pair(s).")

    result = settings_registry.execute_action(
        "hardcover_sync", "preview_cross_format_tags", {"CROSS_FORMAT_ABS_TAG": "x"}
    )

    assert result == {"success": True, "message": "Dry run: 2 pair(s)."}
    assert seen == [(True, {"CROSS_FORMAT_ABS_TAG": "x"})]


def test_apply_button_writes_with_saved_settings_only(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, Any]] = []

    def fake_sync(**kwargs: Any) -> dict[str, Any]:
        seen.append(kwargs)
        return {"forbidden": False}

    monkeypatch.setattr("shelfmark.core.cross_format.sync_audiobookshelf_tags", fake_sync)
    monkeypatch.setattr("shelfmark.core.cross_format.describe_summary", lambda s: "done")

    result = settings_registry.execute_action(
        "hardcover_sync", "apply_cross_format_tags", {"CROSS_FORMAT_ABS_TAG": "x"}
    )

    assert result == {"success": True, "message": "done"}
    assert seen == [{"dry_run": False}]


def test_buttons_report_a_refusal_as_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from shelfmark.core.cross_format import CrossFormatDisabledError

    def fake_sync(**_kwargs: Any) -> dict[str, Any]:
        raise CrossFormatDisabledError("tagging is off")

    monkeypatch.setattr("shelfmark.core.cross_format.sync_audiobookshelf_tags", fake_sync)

    result = settings_registry.execute_action("hardcover_sync", "apply_cross_format_tags")

    assert result == {"success": False, "message": "tagging is off"}


@pytest.mark.parametrize(
    ("action", "provider"),
    [("test_library_connection", "audiobookshelf"), ("test_calibre_library", "calibre")],
)
def test_action_buttons_delegate_to_the_library_index(
    monkeypatch: pytest.MonkeyPatch, action: str, provider: str
) -> None:
    calls: list[str] = []

    def fake_test_connection(name: str, current_values: dict[str, Any] | None) -> dict[str, Any]:
        calls.append(name)
        assert current_values == {}
        return {"success": True, "message": name}

    monkeypatch.setattr("shelfmark.core.library_index.test_connection", fake_test_connection)

    result = settings_registry.execute_action("hardcover_sync", action)

    assert result == {"success": True, "message": provider}
    assert calls == [provider]
