# Library Check

Configure in **Settings → Hardcover Sync → Library Check**.

The library check stops the Hardcover sync and automatic downloads from fetching books you already own. Before a synced book becomes a request, and again before auto-download picks a release, Shelfmark looks the book up in the libraries you have connected and skips it when it is already there.

Two libraries are supported. Enable one or both.

## Audiobookshelf

Checks audiobook requests against your Audiobookshelf libraries over its API.

| Setting | Description | Default |
|---------|-------------|---------|
| Skip books already in Audiobookshelf | Enable the Audiobookshelf check | Off |
| Audiobookshelf URL | Base URL reachable from the Shelfmark container, e.g. `http://10.0.0.91:13378` | _none_ |
| Audiobookshelf API Token | Token from **Settings → Users → your user → API Token** in Audiobookshelf | _none_ |
| Library IDs | Comma-separated library IDs to check. Blank checks every book library | _all book libraries_ |

**Test library connection** fetches the libraries and reports how many items were indexed.

Environment variables: `LIBRARY_CHECK_ENABLED`, `AUDIOBOOKSHELF_URL`, `AUDIOBOOKSHELF_TOKEN`, `AUDIOBOOKSHELF_LIBRARY_IDS`.

## Calibre

Checks ebook requests against a Calibre library's `metadata.db` — the same file plain Calibre, Calibre-Web and Calibre-Web Automated maintain. Shelfmark only ever reads it.

| Setting | Description | Default |
|---------|-------------|---------|
| Skip books already in a Calibre library | Enable the Calibre check | Off |
| Calibre metadata.db path | Path to `metadata.db` as seen from inside the Shelfmark container | `/calibre-library/metadata.db` |

**Test Calibre library** reads the database and reports how many books were indexed.

Environment variables: `LIBRARY_CHECK_CALIBRE_ENABLED`, `CALIBRE_LIBRARY_DB_PATH`.

### Mounting the library

Mount the Calibre library **folder** into the Shelfmark container read-only and point the path setting at the `metadata.db` inside it:

```yaml
volumes:
  - /path/to/calibre-library:/calibre-library:ro
```

Mount the whole folder, not just the file. Calibre may keep the database in SQLite's WAL mode, in which case recent writes live in `metadata.db-wal` beside the main file until Calibre checkpoints them. With the folder mounted those side files are visible and Shelfmark's reads are current. If only the file is mounted, or the side files are absent on a read-only mount, SQLite cannot open the database in place; Shelfmark then reads a snapshot of the main file, which can lag behind until the next checkpoint, and logs a line saying so.

## How Matching Works

A book counts as owned when any of these match a library entry:

1. **Provider id** — the library records the book's id from the metadata provider the request came from. Calibre identifiers `hardcover-id`, `google` and `openlibrary`/`olid` map to the Hardcover, Google Books and Open Library providers.
2. **ISBN** — ISBN-10 and ISBN-13 are both recognised, and an ISBN-10 on either side is also compared in its ISBN-13 form, so a library that stores only one form still matches. Calibre indexes the `isbn`, `isbn-10` and `isbn-13` identifiers; Audiobookshelf its ISBN field.
3. **Title and author** — at least 85% of the significant words in the title appear in the entry (title, authors, series and, for Audiobookshelf, folder path), and the author's surname appears too. A book with no author metadata matches on title alone.

Sequels and other near-miss titles fail the title rule; the same title by a different author fails the surname rule.

## Which Library Is Checked

Requests carry a content type. Audiobook requests are checked against Audiobookshelf and ebook requests against Calibre. A library that is disabled, or that does not hold the requested content type, is not consulted — with only Calibre enabled, audiobook requests are never skipped by the check.

## If a Library Is Unreachable

The check fails open. When Audiobookshelf is down, the Calibre path is wrong or the database cannot be read, Shelfmark logs a warning and carries on as if the book were not owned — it never blocks a sync or a download. If an earlier index exists it keeps answering from that until the library is reachable again.

Libraries are re-indexed every 10 minutes, or sooner when the Calibre database file changes.
