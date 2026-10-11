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

Sequels and other near-miss titles fail the title rule; the same title by a different author fails the surname rule. A series label in front of a library title ("Alex Cross 02: Kiss the Girls", "HHG 5: Mostly Harmless") is read as the series, not as part of the title, when the entry is in a series, so renaming a shelf to show reading order doesn't make its books look unowned. A shelf title whose bracketed words name another edition ("Full Cast Edition", "Dramatized Adaptation") is not the book either: owning the adaptation is not owning the recording asked for. Printing words ("Illustrated Edition", "Unabridged") change nothing, and in a Calibre title a numbered parenthetical ("(Alex Cross Series #11)") is read as the series, not as an edition.

## Badges in Search Results

When a library check is enabled, search results (card, list and compact views) and the details dialog show an **Ebook** / **Audiobook** badge on books the check already finds in the matching library. Only formats with an enabled library are reported, and the badges use the same cached index as the sync, so they add no network calls per search once the index is warm.

## Which Library Is Checked

Requests carry a content type. Audiobook requests are checked against Audiobookshelf and ebook requests against Calibre. With **Request as: Ebooks and audiobooks**, every shelf book yields one request of each type, so the same title can be skipped as an ebook (already in Calibre) yet requested as an audiobook, or vice versa. A library that is disabled, or that does not hold the requested content type, is not consulted — with only Calibre enabled, audiobook requests are never skipped by the check.

## If a Library Is Unreachable

When Audiobookshelf is down, the Calibre path is wrong or the database cannot be read, Shelfmark logs a warning. If an earlier index exists it keeps answering from that until the library is reachable again. Without one, the unattended paths hold rather than guess: shelf sync skips that run and automatic download leaves the request pending, so nothing is requested or downloaded blind. Search-result badges just show nothing.

Libraries are re-indexed every 10 minutes, or sooner when the Calibre database file changes.

## Cross-Format Markers

With both library checks on, Shelfmark can mark the works you hold in both formats, so a reader in Audiobookshelf sees that the ebook is in Calibre, and a reader in Calibre-Web sees that the audiobook is in Audiobookshelf.

A Calibre book and an Audiobookshelf item are a **pair** when either one, asked for by its own title, author and identifiers (ISBN, ASIN), is found in the other library by the matching rules above. The same exceptions apply: a series label or numbered parenthetical in front of a title is the series, not another work; a different edition ("Full Cast Edition", "Dramatized Adaptation") is a different recording and not a pair; an omnibus contains the work but is not its copy; a sequel whose title extends the other ("Dune", "Dune Messiah") is a different book. Two editions on one side both pair with the one copy on the other.

### Audiobookshelf tags

Shelfmark writes one tag (`ebook-in-library` by default) to every paired audiobook and removes it from any audiobook that has lost its pair. No other tag is touched: the item's current tag list is read back from Audiobookshelf just before each write, so a tag you added a minute ago is kept, and running the sync twice changes nothing the second time.

| Setting | Description | Default |
|---------|-------------|---------|
| Tag audiobooks whose ebook is in Calibre | Write the tag at the end of every sync cycle | Off |
| Audiobookshelf tag | The tag to write | `ebook-in-library` |

**Preview Audiobookshelf tags** is a dry run: it counts the pairs and lists what would be added and removed, without writing. It works with the toggle off and uses the form's unsaved values. **Apply Audiobookshelf tags now** writes the changes with the saved settings and needs the toggle on.

With the toggle on, the tags are also refreshed at the end of every [Hardcover sync](hardcover-sync.md) cycle. The cycle's log reports the counts, and a failure in this pass is logged and counted but never stops the cycle.

The token's user needs Audiobookshelf's **Can update** permission. Without it Audiobookshelf answers 403 (`PATCH /api/items/<id>/media`); Shelfmark stops at the first refusal, logs it, and says so in the settings button's message and the endpoint's answer. Each write sends the item's whole tag list, as the Audiobookshelf API requires, which is why the fresh read comes first.

Environment variables: `CROSS_FORMAT_ABS_TAGGING_ENABLED`, `CROSS_FORMAT_ABS_TAG`.

### Endpoints

Both are admin endpoints, so an [API key](api-access.md) can call them from a script.

`GET /api/admin/library/cross-format` returns the pairs, flat and indexed from both sides:

```json
{
  "ebooks_indexed": 412,
  "audiobooks_indexed": 97,
  "pair_count": 1,
  "pairs": [
    {"ebook": {"id": "118", "title": "Dune", "author": "Frank Herbert"},
     "audiobook": {"id": "li_8gch9ve09orgn4fdz8", "title": "Dune", "author": "Frank Herbert"}}
  ],
  "by_calibre_id": {"118": [{"id": "li_8gch9ve09orgn4fdz8", "title": "Dune", "author": "Frank Herbert"}]},
  "by_audiobookshelf_id": {"li_8gch9ve09orgn4fdz8": [{"id": "118", "title": "Dune", "author": "Frank Herbert"}]}
}
```

`POST /api/admin/library/cross-format/audiobookshelf-tags` with body `{"dry_run": true}` (the default when the body is empty) reports; `{"dry_run": false}` writes. The answer lists the `added` and `removed` items with `already_current`, `errors` and `forbidden` counts, plus a one-line `message`. Status codes: 400 when either library check is off, 409 when writing with the toggle off, 503 when a library cannot be read, 502 when Audiobookshelf refused the write.

Both hold rather than guess when a library cannot be read: an empty index would look like "no pairs" and remove every tag.

### Marking the Calibre side

Shelfmark only reads `metadata.db`, so the Calibre side is marked outside Shelfmark by a script that reads `by_calibre_id` from the endpoint and runs `calibredb` wherever Calibre's tools and the library are (a Calibre-Web container that ships them, or a host with calibre installed). A yes/no custom column is the natural marker. Create it once:

```bash
calibredb add_custom_column --library-path /calibre-library audiobook "Audiobook in library" bool
```

Then set it on each Calibre id the endpoint lists and clear it on books that are no longer listed:

```bash
calibredb set_custom --library-path /calibre-library audiobook 118 true
calibredb set_custom --library-path /calibre-library audiobook 118 ""
```

`calibredb list --library-path /calibre-library --fields id,#audiobook` shows what is set, so the script can change only what differs. Do not run `calibredb` against a library that the calibre desktop application has open; Calibre-Web and Calibre-Web Automated read the database and may need their library refresh to show the column.
