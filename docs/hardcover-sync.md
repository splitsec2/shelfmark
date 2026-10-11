# Hardcover Sync

Configure in **Settings → Hardcover Sync**.

Hardcover Sync pulls books from your [Hardcover](https://hardcover.app) reading shelves into Shelfmark as requests, optionally downloads them without an admin picking a release, and can skip books you already own in Audiobookshelf or a Calibre library. Every part is opt-in and off by default; the tab does nothing until you enable it.

## Capabilities

### Shelf sync

On a schedule, Shelfmark reads the selected Hardcover shelf (by default **Want to Read**) through the Hardcover metadata provider and creates a **pending** request for each book that is not already known. Requests carry Hardcover's metadata, including the cover, and are owned by the lowest-id admin account.

A book is skipped when:

- a request with the same Hardcover book id already exists, in any status
- a request for the same Hardcover book and format, by any user, has a download in the history that finished or is still running (an unfinished download older than a day no longer counts as running)
- the library check (below) says you already own it
- a pending request with the same title, author, and content type already exists

### Automatic downloads

When enabled, each pending request that came from Hardcover is searched across your release sources in the priority order configured for its content type (audiobook requests use the audiobook list, ebook requests the ebook list). The first source that yields a **strict match** wins, and the best candidate from that source is queued through the normal request fulfilment path, so it appears in the activity view and download history exactly like a request an admin approved.

A release is a strict match only when all of the following hold:

- at least 85% of the significant words in the book's title appear in the release title. Numbers from 1 to 20 count as the same word however they are written, so *Part II*, *Part Two* and *Part 2* agree, while *Part One* never stands in for *Part Two*;
- the author's surname appears in the release title, indexer name or author field (a book with no author metadata matches on title alone). Some AudiobookBay listings carry no author in their title (*The Mummy or Ramses the Damned*). When a source turns up no strict match, the detail pages of up to three such releases that pass every other rule are read, and the author they credit (a narrator does not count) is checked like any other. A page that credits nobody, or someone else, leaves the release rejected;
- the release title doesn't name a different book that contains the requested one. A "Dune" request won't take *Dune Messiah* or *Children of Dune*, and a bare number after the title (*Mistborn 2*, *Mistborn Two*, *Dune Chronicles Book II*) names a sequel. A title with a number of its own (*Ready Player One*) takes no other number after it, 1 included. Only the parts of the release name that hold the title are judged, so narrators, uploader tags and the book's own series, author and subtitle words don't count against it; a part that is just the series name (*Alex Cross 25*) does not vouch for a one-word title, so a "Cross" request won't take *Alex Cross: Cross Justice*. Two slash-separated names that both hold the title (*Dune / Dune Messiah*) are two books;
- the release is not a derivative of the work: *summary*, *analysis*, *study guide*, *workbook*, *abridged*, *dramatized*, *adaptation* or *graphic novel* anywhere in the name disqualifies it, unless the requested title itself carries the word. *Unabridged* is a full recording and is fine;
- the release is not a multi-book pack: ranges like `1-24` or `Books 1 to 17`, or words like *complete*, *collection*, *box set*, *omnibus*, *trilogy*, *megapack*, *+ short stories*, unless the requested title itself carries them. "Complete and Unabridged" describes one recording and doesn't count. The library check uses the same word list;
- the format fits the request — an audiobook request needs an audiobook signal (`m4b`/`mp3`, a release from an audiobook-only source, or "audiobook"/"unabridged" in the title) and is never an ebook-only file; an ebook request needs one of your **Supported Book Formats** (or an `.epub`-style marker in the title) and no audiobook signal;
- for torrents that report a seeder count, it meets **Minimum seeders** — sources that report none (AudiobookBay) are not judged on seeders.

AudiobookBay requires every word of a query, and its posts for one volume of a multi-part book often spell the part differently from the request ("Part Two" for "Part II"), so a query carrying the part finds only the packs that list it. When no row a query returns carries the requested title, the source tries the next query, ending with the title minus its trailing *, Part N* or *Volume N*. The strict match above still decides which part was found.

When no source yields a strict match for the request's own search title, up to three simpler titles are tried in turn, each across the sources in priority order and all within the request's search budget: the title without a subtitle after `:` or ` - `, the title without an alternate title (*The Hobbit, or There and Back Again* becomes *The Hobbit*), and the title with its numbers written as digits (*Part II* becomes *Part 2*). The first one that yields a strict match wins, and the log names it. A simpler title is matched by exactly the rules above, so a release has to name the shorter title, the right author, and no sequel, edition, derivative or pack. The subtitle is only dropped when the book's metadata says it is one (a series name is known, or the book's subtitle is what follows the separator), and never when what is left is only the series or author name: *Star Wars: Thrawn* is not searched as *Star Wars*.

Among matching releases from the winning source, format ranks first (`m4b` over `mp3` for audiobooks; `epub` over `azw3` over `mobi` for ebooks), then the copy other people chose — more downloads (direct-download sources report them), then more seeders — then larger size. If no source produces a confident match the request stays **pending** for manual review; nothing is guessed.

A request whose book turns out to be in your library already is closed, not left pending: it is marked fulfilled with the admin note `[auto] Already in the library.`, so it stops being looked up every pass. Before this it sat in Needs Review indefinitely. **Clear Completed** clears these too.

Hardcover allows a short burst of lookups and then answers 429. Each pass paces its book lookups and backs off when told to, following `Retry-After`. A lookup that still fails counts as an error for that request, not as "book not found", and the request is tried again next pass.

A download that fails, or is interrupted (a restart while it was queued, say), does not stay that way forever. Once the request has sat there for **Retry failed downloads after (days)** (7 by default), it goes back to pending and the next pass searches again. Each pass reopens at most five, oldest first, so a backlog is spread out instead of hitting your sources at once. An interrupted download may pick the same release again, since a torrent already in your client is joined instead of added twice. A download that itself failed, or that Shelfmark's stall timer cancelled, has its release remembered and skipped next time, and the request is given up on after three failed retries. Requests you or an admin cancelled are never retried, and neither are rejected ones: both are decisions. Set the value to 0 to turn retries off.

### Library check

When enabled, both shelf sync and automatic downloads look the book up in the libraries you have connected — Audiobookshelf for audiobook requests, a Calibre library (Calibre-Web / Calibre-Web Automated) for ebook requests — by provider id, ISBN, or fuzzy title plus author surname, and skip it if it is already there. Each library is indexed at most every 10 minutes. Settings, mounting and the matching rules are described in [Library Check](library-check.md).

If a library is unreachable or returns an error, Shelfmark reuses the last successful fetch if it has one. Without one, it does not guess: shelf sync skips that run (requesting now could queue books the library already holds) and automatic download leaves the request pending for the next pass. Search-result badges are the exception and simply show nothing.

### Series gaps

Admins can open **Series gaps** from the activity sidebar header (the stacked-books button). For every series the connected libraries hold, Shelfmark looks the series up on Hardcover and lists the volumes Hardcover knows, with one column per connected format: ebooks from the Calibre library, audiobooks from Audiobookshelf. Each volume is marked per format:

- **owned**: the library matcher finds the book (the same rules as the library check), or the library holds that series at the same position under another title. An omnibus that holds the volume shows as a collection and counts as owned.
- **requested**: a request for the book exists in any status, from any user, whether it came from Hardcover or another provider. A rejected or cancelled request still counts, so a decision is not undone by the report.
- **missing**: neither of the above.

A format column only applies to a series the library collects in that format. With an audiobook of volume 1 and no ebooks of the series at all, the ebook column stays blank rather than listing every volume as missing. Tick the missing volumes you want and press **Request selected**: each becomes a pending book-level request owned by the lowest-id admin, exactly as shelf sync creates them, so automatic downloads pick them up and the usual duplicate checks apply. The request carries a note naming the series and position.

Hardcover is asked once per series (one series search and one series fetch) and the answer is kept for a day; a series Hardcover does not know is asked about again after an hour. **Refresh** forgets the cached answers and asks again. Each load spends at most 20 seconds on Hardcover; series it did not reach come back as pending and the page keeps asking until none are left. Hardcover's pacing and 429 back-off apply here as everywhere else.

The series name has to match. The library's series name, packaging words such as "Series" aside, is looked up on Hardcover, and a Hardcover series credited to another author, or whose volumes name another author, is not taken; the report says so under the series. Unreleased volumes and compilations are left out. The report needs the app-level Hardcover token and at least one connected library; if a library cannot be read, the report says so instead of guessing. Series index numbers come from Calibre's series index and from Audiobookshelf's series sequence, falling back to the number in a "Label NN:" title.

## Per-user accounts

Every user can connect their own Hardcover account instead of sharing one. The token
field is user overridable, so it appears under **Settings, Hardcover Account** for each
user, and it is also settable per user by an admin from the user editor. Admins choose
whether that section is shown at all with **Visible self settings sections** on the Users
tab.

When a user connects a token, each scheduled run syncs their shelf on their own token and
the requests it creates are owned by them, deduplicated against their own requests rather
than the whole instance. Accounts are synced one at a time, so a token that has expired or
an API error on one account does not stop the others.

The app-level token still runs as its own pass afterwards, owned by the lowest-id admin,
which is what a single-account install keeps doing with no change.

## Settings

| Key | Label | Default | Notes |
|-----|-------|---------|-------|
| `HARDCOVER_SYNC_ENABLED` | Enable scheduled sync | Off | Runs shelf sync on the interval below |
| `HARDCOVER_SYNC_TOKEN` | Hardcover API Token | — | Leave blank to reuse the Hardcover metadata provider's token. Each user can connect their own account instead, see [Per-user accounts](#per-user-accounts) |
| `HARDCOVER_SYNC_STATUSES` | Shelves to sync | Want to Read | Hardcover reading status to pull from |
| `HARDCOVER_SYNC_CONTENT_TYPE` | Request as | Audiobooks | `Audiobooks`, `Ebooks`, or `Ebooks and audiobooks` — the last creates one request of each per shelf book, each checked against its own library |
| `HARDCOVER_SYNC_INTERVAL` | Sync interval | 6 | Combined with the unit below |
| `HARDCOVER_SYNC_INTERVAL_UNIT` | Interval unit | Hours | Minutes or hours. The effective interval never drops below 60 seconds |
| `AUTO_DOWNLOAD_ENABLED` | Enable automatic downloads | Off | Auto-approve and queue strict matches for Hardcover requests |
| `AUTO_DOWNLOAD_SOURCE_PRIORITY` | Audiobook source priority | All usable sources | Drag to order; used for audiobook requests. Sources you disable here, or that are not configured, are skipped |
| `AUTO_DOWNLOAD_EBOOK_SOURCE_PRIORITY` | Ebook source priority | All usable sources | Same, for ebook requests |
| `AUTO_DOWNLOAD_MIN_SEEDERS` | Minimum seeders (torrents) | 1 | Torrent releases below this are ignored |
| `LIBRARY_CHECK_ENABLED` | Skip books already in Audiobookshelf | Off | Applies to both sync and automatic downloads |
| `AUDIOBOOKSHELF_URL` | Audiobookshelf URL | — | Must be reachable from the Shelfmark container, e.g. `http://10.0.0.91:13378` |
| `AUDIOBOOKSHELF_TOKEN` | Audiobookshelf API Token | — | From Audiobookshelf **Settings → Users → your user → API Token** |
| `AUDIOBOOKSHELF_LIBRARY_IDS` | Library IDs | — | Comma-separated. Blank checks every book library |
| `LIBRARY_CHECK_CALIBRE_ENABLED` | Skip books already in a Calibre library (Calibre-Web / CWA) | Off | Ebook requests only |
| `CALIBRE_LIBRARY_DB_PATH` | Calibre metadata.db path | `/calibre-library/metadata.db` | Mount the library folder read-only |

Two action buttons sit at the bottom of the tab:

- **Test library connection** verifies the Audiobookshelf URL and token and reports how many items were indexed.
- **Test Calibre library** reads `metadata.db` and reports how many books were indexed.
- **Sync now** runs a sync and automatic-download pass immediately using the saved settings. Sync runs even when scheduled sync is off; automatic downloads still require their own toggle.

## Request Flow

1. Shelf sync creates a **pending** request per new Hardcover book, with cover, year, and subtitle where Hardcover has them.
2. If automatic downloads are enabled, the request is searched source by source and the first strict match is queued through the normal fulfil path. The request becomes **fulfilled** and its delivery state is tracked like any other.
3. If no source yields a confident match, the request stays **pending** in the admin queue for manual review, exactly as if a user had requested the book.

Only requests whose provider is Hardcover are considered for automatic downloads, and requests that have already been dispatched are left alone.

## Scheduler

The scheduler starts with the app and waits **60 seconds** before its first cycle. Each cycle runs a shelf sync (when scheduled sync is enabled) followed by an automatic-download pass (when that is enabled), then sleeps for the configured interval. Intervals shorter than 60 seconds are raised to 60 seconds so a typo cannot hammer the Hardcover API. When neither toggle is on the scheduler idles.

Only one run happens at a time. If a scheduled cycle is in progress, **Sync now** reports that a sync is already running.

Each request's release search during a cycle runs under the same time limit as a search from the UI (`RELEASE_SEARCH_TIMEOUT`). A cycle that is still running after an hour is treated as stuck: the scheduler stops waiting for it, logs an error, counts the cycle as failed in `/api/health`, and lets the next cycle or **Sync now** run. The stuck cycle itself stops at its next request. Whatever it did not get to waits for the next cycle.

## Troubleshooting

**Sync adds nothing and the log says "no Hardcover token configured"** — set **Hardcover API Token** on this tab, or configure the token on the Hardcover metadata provider. A sync without a usable token counts as an error and creates no requests.

**Requests appear but nothing downloads** — check **Enable automatic downloads** is on, that the source-priority list for the request's content type contains at least one configured source, and look for `no strict match` lines in the log. Lowering **Minimum seeders** helps on quiet trackers; loosening the title or author match is deliberately not an option.

**Books you own keep being added** — enable the library check and use **Test library connection**. Because the check fails open, a wrong URL or token only produces a log warning rather than blocking the sync; the test button is where a bad connection is reported plainly.

**Too many requests at once** — the first sync of a large shelf creates one request per book, and the per-user pending limit from **Users & Requests** does not apply to synced requests. Start with a shelf you are happy to see in the queue in full.
