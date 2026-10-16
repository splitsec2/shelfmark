"""What the activity list says about a download that failed, and what happens next."""

from __future__ import annotations

import pytest

from shelfmark.core.status_messages import explain, explain_buckets


def _explain(message, *, linked=True, minutes=20):
    return explain(message, request_linked=linked, retry_minutes=minutes)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "Peer transfer failed: Errored",
            "The Soulseek peer dropped the transfer (Errored). "
            "Another copy will be tried in about 20 minutes.",
        ),
        (
            "Failed to add to slskd: 500 Server Error: Internal Server Error for url: http://x",
            "The Soulseek peer did not answer slskd's queue request (tried twice). "
            "Another copy will be tried in about 20 minutes.",
        ),
        (
            "Download stalled (no activity for 300s)",
            "Nothing was downloading, so it was stopped. "
            "Another copy will be tried in about 20 minutes.",
        ),
        (
            "No seeders: 0 found, 1 needed, for 5 min (12% downloaded)",
            "No seeders: 0 found, 1 needed, for 5 min (12% downloaded); the torrent was removed. "
            "Another copy will be tried in about 20 minutes.",
        ),
        (
            "All download sources failed",
            "None of the download sources could provide this book. "
            "Another copy will be tried in about 20 minutes.",
        ),
    ],
)
def test_a_failure_says_what_happened_and_what_comes_next(raw, expected):
    assert _explain(raw) == expected


def test_interrupted_says_a_restart_did_it():
    assert _explain("Interrupted") == "Interrupted by a restart. Use Retry to run it again."


def test_a_superseded_row_says_the_book_was_delivered():
    assert (
        _explain("Superseded by a completed download")
        == "This book was already delivered by another download."
    )


def test_without_the_quick_retry_a_request_is_pointed_at_retry_or_reopen():
    assert _explain("Peer transfer failed: TimedOut", minutes=0).endswith(
        "Use Retry to try again, or reopen the request to try another copy."
    )


def test_a_manual_download_is_never_promised_an_automatic_retry():
    text = _explain("Peer transfer failed: Errored", linked=False)

    assert "will be tried" not in text
    assert text.endswith("Use Retry to try again, or pick another copy.")


def test_an_unknown_message_and_an_empty_one_are_left_as_they_are():
    assert _explain("Something new broke") == "Something new broke"
    assert _explain(None) is None
    assert _explain("  ") == "  "


def test_the_buckets_are_rewritten_without_touching_the_original_payload():
    original = {"id": "t", "request_id": 5, "status_message": "Peer transfer failed: Errored"}
    status = {"error": {"t": original}, "cancelled": {}, "complete": {"c": {"status_message": "x"}}}

    explain_buckets(status)

    assert status["error"]["t"]["status_message"].startswith("The Soulseek peer dropped")
    assert original["status_message"] == "Peer transfer failed: Errored"
    assert status["complete"]["c"]["status_message"] == "x"
