"""Sync a Hardcover reading shelf (e.g. "Want to Read") into Shelfmark requests.

This replaces the standalone ``scripts/sync_hardcover_wishlist.py`` with an in-app
service that reuses the registered Hardcover metadata provider (so synced requests
carry full metadata incl. covers) and the request-service validation/dedup path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from shelfmark.core import library_index
from shelfmark.core.config import config as app_config
from shelfmark.core.logger import setup_logger
from shelfmark.core.request_helpers import (
    load_users_request_policy_settings,
    normalize_optional_text,
)
from shelfmark.core.request_policy import (
    merge_request_policy_settings,
    normalize_content_type,
    pending_request_limit,
)
from shelfmark.core.user_settings_overrides import PERSONAL_HARDCOVER_TOKEN_KEY
from shelfmark.core.utils import transform_cover_url

if TYPE_CHECKING:
    from shelfmark.core.user_db import UserDB
    from shelfmark.metadata_providers import BookMetadata

logger = setup_logger(__name__)

# Hardcover status_id -> shelf. Default sync target is "Want to Read" (1).
DEFAULT_SYNC_STATUSES = ("1",)
PERSONAL_SYNC_ORIGIN = "hardcover_personal_sync"
_PAGE_LIMIT = 25  # Hardcover API page size.
_MAX_PAGES = 40  # Safety bound (~1000 books) so a bad response can't loop forever.


def _configured_token() -> str:
    """Read the deployment's sync credential, falling back to the metadata API key."""
    token = app_config.get("HARDCOVER_SYNC_TOKEN", "") or app_config.get("HARDCOVER_API_KEY", "")
    return str(token or "").strip()


def has_app_level_token() -> bool:
    """Whether the instance has a credential for its own sync pass."""
    return bool(_configured_token())


def _user_token(user_db: UserDB, user_id: int) -> str:
    """Read the personal credential directly from the user's settings."""
    return (
        normalize_optional_text(
            user_db.get_user_settings(user_id).get(PERSONAL_HARDCOVER_TOKEN_KEY)
        )
        or ""
    )


def users_with_hardcover_token(user_db: UserDB) -> list[int]:
    """Ids of users who connected their own Hardcover token, lowest id first."""
    return sorted(
        int(user["id"])
        for user in user_db.list_users()
        if user.get("id") is not None and _user_token(user_db, int(user["id"]))
    )


def _configured_statuses() -> list[int]:
    raw = app_config.get("HARDCOVER_SYNC_STATUSES", list(DEFAULT_SYNC_STATUSES))
    values: list[object]
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, (list, tuple)):
        values = list(raw)
    else:
        values = []
    statuses: list[int] = []
    for value in values:
        try:
            statuses.append(int(str(value).strip()))
        except ValueError:
            continue
    return statuses or [int(s) for s in DEFAULT_SYNC_STATUSES]


_CONTENT_TYPES = {"ebook": ["ebook"], "audiobook": ["audiobook"], "both": ["ebook", "audiobook"]}
DEFAULT_SYNC_CONTENT_TYPE = "audiobook"


def _configured_content_types() -> list[str]:
    """Content types to request for every shelf book ("both" → an ebook and an audiobook)."""
    raw = str(app_config.get("HARDCOVER_SYNC_CONTENT_TYPE", DEFAULT_SYNC_CONTENT_TYPE) or "")
    return list(_CONTENT_TYPES.get(raw.strip().lower(), _CONTENT_TYPES[DEFAULT_SYNC_CONTENT_TYPE]))


def _build_provider(token: str) -> Any | None:
    """Build a provider scoped to the credential selected for this pass."""
    from shelfmark.metadata_providers import get_provider

    if not token:
        logger.warning("hardcover-sync: no Hardcover token configured")
        return None
    provider = get_provider("hardcover", api_key=token, for_sync=True)
    if not provider.is_available():
        logger.warning("hardcover-sync: Hardcover provider unavailable")
        return None
    return provider


def _blocked_content_types(user_db: UserDB, user_id: int) -> set[str]:
    """Content types this user's request policy blocks, so their sync does not queue them.

    An admin is not held to the policy. Requests created here skip the request routes, and
    auto-download later approves them, so a blocked type has to be left out at this point.
    """
    from shelfmark.core.request_policy import PolicyMode, resolve_policy_mode

    user = user_db.get_user(user_id=user_id)
    if user is None or user.get("role") == "admin":
        return set()
    global_settings = load_users_request_policy_settings()
    user_settings = user_db.get_user_settings(user_id)
    return {
        content_type
        for content_type in ("ebook", "audiobook")
        if resolve_policy_mode(
            source=None,
            content_type=content_type,
            global_settings=global_settings,
            user_settings=user_settings,
        )
        == PolicyMode.BLOCKED
    }


def resolve_request_owner(user_db: UserDB) -> int | None:
    """Return the lowest-id admin, who owns synced requests and approves auto-downloads."""
    admin = user_db.get_first_admin()
    return int(admin["id"]) if admin else None


def _primary_author(book: BookMetadata) -> str:
    if book.search_author:
        return book.search_author
    if book.authors:
        return book.authors[0]
    return "Unknown"


def _book_to_book_data(
    book: BookMetadata, content_type: str, *, personal: bool = False
) -> dict[str, Any]:
    book_data: dict[str, Any] = {
        "title": book.title,
        "author": _primary_author(book),
        "provider": "hardcover",
        "provider_id": str(book.provider_id),
        "content_type": content_type,
    }
    if personal:
        book_data["sync_origin"] = PERSONAL_SYNC_ORIGIN
    # Proxy the cover the same way search results are, so the row is ready for the UI.
    if book.cover_url:
        book_data["preview"] = transform_cover_url(book.cover_url, f"hardcover_{book.provider_id}")
    if book.publish_year:
        book_data["year"] = book.publish_year
    if book.subtitle:
        book_data["subtitle"] = book.subtitle
    return book_data


def _existing_request_keys(user_db: UserDB, user_id: int) -> set[tuple[str, str]]:
    """``(hardcover id, content_type)`` pairs already requested, in any status.

    An owner's existing request counts in every status and only for its own format.
    """
    keys: set[tuple[str, str]] = set()
    for row in user_db.list_requests(user_id=user_id):
        book_data = row.get("book_data") or {}
        if isinstance(book_data, dict) and book_data.get("provider") == "hardcover":
            pid = book_data.get("provider_id") or book_data.get("id")
            if pid is not None:
                # Normalized the way requests_service's duplicate check does, so a row
                # with no content type counts as the ebook request it is treated as.
                content_type = normalize_content_type(
                    row.get("content_type") or book_data.get("content_type")
                )
                keys.add((str(pid), content_type))
    return keys


def _fetch_status_books(provider: Any, status_id: int) -> tuple[list[BookMetadata], bool]:
    """Page through a Hardcover status shelf: the books read, and whether a fetch failed."""
    books: list[BookMetadata] = []
    failed = False
    for page in range(1, _MAX_PAGES + 1):
        try:
            result = provider._fetch_current_user_books_by_status(status_id, page, _PAGE_LIMIT)
        except Exception as exc:  # noqa: BLE001 - network/provider errors shouldn't abort the sync
            logger.warning(
                "hardcover-sync: fetch failed (status=%s page=%s): %s", status_id, page, exc
            )
            failed = True
            break
        page_books = list(result.books or [])
        books.extend(page_books)
        if not result.has_more or not page_books:
            break
    return books, failed


def sync_wishlist(
    user_db: UserDB,
    *,
    user_id: int | None = None,
) -> dict[str, int]:
    """Sync configured Hardcover shelves into pending requests.

    One request is created per shelf book and configured content type ("both" means an
    ebook and an audiobook request each), so each format is checked against its own
    library. Returns ``{"added", "skipped", "in_library", "errors"}``. Requires a
    configured token; enable-gating is the caller's responsibility (see hardcover_scheduler).

    Pass ``user_id`` to sync that user's own Hardcover account: their token is used and
    the requests are theirs. Omit it for the app-level token, whose requests are owned
    by :func:`resolve_request_owner`.
    """
    summary = {"added": 0, "skipped": 0, "in_library": 0, "errors": 0}

    per_user = user_id is not None
    if user_id is None:
        user_id = resolve_request_owner(user_db)
    if user_id is None:
        logger.warning("hardcover-sync: no admin user exists to own synced requests")
        summary["errors"] += 1
        return summary

    token = _user_token(user_db, user_id) if per_user else _configured_token()
    if per_user and not token:
        # Their token went between the account list being read and this pass.
        logger.info("hardcover-sync: user %s no longer has a token of their own; skipped", user_id)
        return summary

    provider = _build_provider(token)
    if provider is None:
        summary["errors"] += 1
        return summary

    content_types = _configured_content_types()
    blocked_types = _blocked_content_types(user_db, user_id) if per_user else set()

    try:
        for content_type in content_types:
            if content_type not in blocked_types:
                library_index.require_ready(content_type, shared_only=per_user)
    except library_index.LibraryUnavailableError as exc:
        # Requesting now would queue books the library may already hold.
        logger.warning("hardcover-sync: %s; skipping this sync", exc)
        summary["errors"] += 1
        return summary
    known_requests = _existing_request_keys(user_db, user_id)
    max_pending = None
    if per_user:
        max_pending = pending_request_limit(
            merge_request_policy_settings(
                load_users_request_policy_settings(), user_db.get_user_settings(user_id)
            )
        )

    from shelfmark.core.requests_service import RequestServiceError, create_request

    for status_id in _configured_statuses():
        shelf, fetch_failed = _fetch_status_books(provider, status_id)
        if fetch_failed:
            summary["errors"] += 1
        for book in shelf:
            provider_id = str(book.provider_id)
            author = _primary_author(book)

            for content_type in content_types:
                if content_type in blocked_types:
                    summary["skipped"] += 1
                    continue
                if (provider_id, content_type) in known_requests:
                    summary["skipped"] += 1
                    continue
                if library_index.is_in_library(
                    book, content_type, strict=True, shared_only=per_user
                ):
                    summary["in_library"] += 1
                    logger.info(
                        "hardcover-sync: '%s' (%s) already in library; skipping",
                        book.title,
                        content_type,
                    )
                    continue

                try:
                    create_request(
                        user_db,
                        user_id=user_id,
                        source_hint=None,
                        content_type=content_type,
                        request_level="book",
                        policy_mode="request_book",
                        book_data=_book_to_book_data(book, content_type, personal=per_user),
                        max_pending_per_user=max_pending,
                        note=None,
                    )
                except RequestServiceError as exc:
                    # Duplicate / max-pending / validation: treat as skip, not failure.
                    if exc.code in {"duplicate_pending_request", "max_pending_reached"}:
                        summary["skipped"] += 1
                    else:
                        logger.warning(
                            "hardcover-sync: could not add '%s' (%s): %s",
                            book.title,
                            content_type,
                            exc,
                        )
                        summary["errors"] += 1
                    continue
                except Exception:
                    logger.exception(
                        "hardcover-sync: unexpected error adding '%s' (%s)",
                        book.title,
                        content_type,
                    )
                    summary["errors"] += 1
                    continue

                known_requests.add((provider_id, content_type))
                summary["added"] += 1
                logger.info(
                    "hardcover-sync: added %s request for '%s' by %s",
                    content_type,
                    book.title,
                    author,
                )

    logger.info("hardcover-sync complete: %s", summary)
    return summary
