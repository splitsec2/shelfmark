"""The folders /api/localdownload may send files from, and the check against them (#1661)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from shelfmark.core.utils import get_download_roots, is_within_download_roots


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """Point every setting at nothing, TMP_DIR at a scratch folder, and return the dict to fill."""
    values: dict[str, str] = {}
    monkeypatch.setattr("shelfmark.config.env.TMP_DIR", tmp_path / "tmp")
    with patch(
        "shelfmark.core.config.config.get",
        side_effect=lambda key, default=None, **_kwargs: values.get(key, default),
    ):
        yield values


def test_each_kind_of_folder_is_a_root(tmp_path, settings):
    settings.update(
        {
            "DESTINATION": str(tmp_path / "books"),
            "DESTINATION_AUDIOBOOK": str(tmp_path / "audiobooks"),
            "INGEST_DIR": str(tmp_path / "ingest"),
            "AA_CONTENT_TYPE_DIR_COMIC": str(tmp_path / "comics"),
            "INGEST_DIR_MAGAZINE": str(tmp_path / "magazines"),
        }
    )

    assert set(get_download_roots()) == {
        (tmp_path / name).resolve()
        for name in ("books", "audiobooks", "ingest", "comics", "magazines", "tmp")
    }


def test_a_user_placeholder_cuts_the_destination_to_the_folder_above_it(tmp_path, settings):
    settings["DESTINATION"] = str(tmp_path / "books" / "shelf-{User}" / "inbox")

    assert (tmp_path / "books").resolve() in get_download_roots()
    assert not any("{" in str(root) for root in get_download_roots())


def test_relative_and_empty_settings_are_left_out(tmp_path, settings):
    settings.update(
        {"DESTINATION": "relative/books", "INGEST_DIR": "  ", "DESTINATION_AUDIOBOOK": ""}
    )

    assert get_download_roots() == [(tmp_path / "tmp").resolve()]


@pytest.fixture
def books(tmp_path, settings):
    root = tmp_path / "books"
    root.mkdir()
    settings["DESTINATION"] = str(root)
    return root


def test_a_file_in_a_download_folder_is_allowed(books):
    book = books / "Some Author" / "Some Author - A Book (2020).epub"
    book.parent.mkdir()
    book.write_bytes(b"x")

    assert is_within_download_roots(str(book))


def test_a_title_with_dots_in_it_is_allowed(books):
    # Shelfmark keeps "..." in its file names, so a substring check would refuse this book.
    book = books / "Some Author - Wait... What_ (2020).epub"
    book.write_bytes(b"x")

    assert is_within_download_roots(str(book))


def test_dot_dot_out_of_the_folder_is_refused(tmp_path, books):
    outside = tmp_path / "secret.txt"
    outside.write_text("x")

    assert not is_within_download_roots(str(books / ".." / "secret.txt"))


def test_a_symlink_out_of_the_folder_is_refused(tmp_path, books):
    outside = tmp_path / "secret.txt"
    outside.write_text("x")
    (books / "link.epub").symlink_to(outside)

    assert not is_within_download_roots(str(books / "link.epub"))


def test_a_folder_that_only_shares_a_prefix_is_refused(tmp_path, books):
    neighbour = tmp_path / "books-old" / "a.epub"
    neighbour.parent.mkdir()
    neighbour.write_bytes(b"x")

    assert not is_within_download_roots(str(neighbour))


def test_a_file_outside_every_folder_is_refused(tmp_path, books):
    elsewhere = tmp_path / "elsewhere.epub"
    elsewhere.write_bytes(b"x")

    assert not is_within_download_roots(str(elsewhere))


def test_a_missing_file_is_refused(books):
    assert not is_within_download_roots(str(books / "gone.epub"))


def test_the_old_destination_is_refused_after_a_change(tmp_path, settings):
    old = tmp_path / "old-books"
    old.mkdir()
    book = old / "a.epub"
    book.write_bytes(b"x")
    settings["DESTINATION"] = str(tmp_path / "new-books")

    assert not is_within_download_roots(Path(book))
