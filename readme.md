> [!IMPORTANT]
> **This is a fork of [calibrain/shelfmark](https://github.com/calibrain/shelfmark).**
> Everything below this block is upstream's own README, unchanged. If you are not me, you
> almost certainly want [the upstream image](https://github.com/calibrain/shelfmark).
> This fork exists to run one household's book pipeline, and its images are amd64-only.

## What this fork adds

Upstream's scope leans away from library integration, automation and collection
management ([Contributing](#contributing)), so this fork carries that layer for a setup where
Shelfmark feeds a Calibre-Web-Automated library and an Audiobookshelf server. It has shrunk as
upstream took things: the Hardcover sync, the Audiobookshelf check and the automatic downloads
are all upstream now, and this page lists only what is still different.

The Origin column says who wrote a change and where it stands upstream: **open** (the PR is
linked), **not sent yet** (an upstream candidate) or **fork only** (outside upstream's scope, so
it is never sent). Changes carried from someone else's work credit them.

### Hardcover

| Change | Origin |
|---|---|
| Per-user Hardcover accounts: each user connects their own account and their shelf syncs to requests they own | This fork. Open upstream: [#1592](https://github.com/calibrain/shelfmark/pull/1592) |
| Lists and shelves on the search page follow the signed-in user: a user who connected their own Hardcover token gets their own lists, "add to list" and read-status actions, and a user with no account of their own gets none. Upstream shares the instance's account with everyone | This fork. Not sent yet (an upstream candidate, after [#1592](https://github.com/calibrain/shelfmark/pull/1592)) |
| Series gaps (admin): every series in your libraries against the volumes Hardcover lists, marked owned, requested or missing, with one column for ebooks and one for audiobooks. A series with ebooks and no audiobooks can still have its audiobooks requested, and Hardcover's duplicate or mis-credited listings of a series are passed over for the real one | This fork. Not sent yet (an upstream candidate) |
| The sync scheduler reports its health: `/api/stats` carries the age of the last cycle, its errors and a healthy flag, and `/api/health` says whether it is running. One cycle is bounded, so a stuck call is given up on and the next cycle can run | This fork. Not sent yet (an upstream candidate) |
| A user's own Hardcover token (and any other per-user secret) is masked in settings payloads and shown to its owner only on request | This fork. Fork only |

### Library check

| Change | Origin |
|---|---|
| Per-format "in your library" badges, one for the ebook and one for the audiobook, where upstream shows a single badge | This fork. Not sent yet (an upstream candidate) |
| A series label in front of the title ("Alex Cross 02: Kiss the Girls", "HHG 5: Mostly Harmless") does not hide an owned book, in both the Calibre and the Audiobookshelf check | This fork. Not sent yet (an upstream candidate, both halves) |
| Search results with a pending request say so ("Ebook requested", "Audiobook requested"), including requests the Hardcover sync made | Idea and helper from [DrNgo/shelfmark-fork@1b393c6](https://github.com/DrNgo/shelfmark-fork/commit/1b393c6) by [@DrNgo](https://github.com/DrNgo). Not sent upstream; it would need a restyle without our per-format pills |
| Cross-format markers: finds the books you have in both Calibre and Audiobookshelf, and can tag those audiobooks (`ebook-in-library`) so a listener sees the ebook is there too. Tagging is off by default and has a dry-run preview | This fork. Not sent yet (an upstream candidate) |

### Sources and downloads

| Change | Origin |
|---|---|
| A Soulseek uploader's anti-leech bot that blocks downloads until a word is typed in a private message gets that word as a reply, at most once per user every 12 hours, logged on each reply (`SLSKD_CHAT_AUTOPROVE`, on by default) | Adapted from [Nezreka/SoulSync@445473b](https://github.com/Nezreka/SoulSync/commit/445473b) by [@Nezreka](https://github.com/Nezreka). Open upstream as a draft, [#1591](https://github.com/calibrain/shelfmark/pull/1591), with the setting off by default there |
| AudiobookBay pages that wrap each post in base64 are decoded, and a page that parses to nothing is logged instead of looking like an empty result | Ported from [DrNgo/shelfmark-fork@7fb5f27](https://github.com/DrNgo/shelfmark-fork/commit/7fb5f27) by [@DrNgo](https://github.com/DrNgo). Not sent upstream yet; I'm asking him first whether he wants to send it himself |
| Dead torrents nothing is watching are removed with their partial data: stalled or stuck fetching metadata, idle for `STALE_TORRENT_HOURS` (6 by default, 3 to 72, 0 turns it off, qBittorrent only), and owned by no running download. Only torrents this instance added are ever touched: it keeps a ledger of the hash of every torrent it adds, so a torrent added before the ledger, or one something else put in the same category, is never removed | This fork. Not sent yet (an upstream candidate) |
| Soulseek leftovers (checked at the start of each sync cycle, before the sync and the auto-download pass): a download folder holding every file whose import an interruption cut off is imported without downloading again, partial folders are removed after `SLSKD_CLEAN_LEFTOVERS_DAYS`, and unfinished slskd transfers no running download owns are picked up again when their request still waits for them, or cancelled | This fork. Not sent yet (an upstream candidate) |

### Requests and the activity list (admin)

| Change | Origin |
|---|---|
| An admin can also reopen a request whose download failed or was cancelled. The release that failed is remembered on the request so the next search skips it, and the same happens when a failed download reopens its request by itself | This fork. Fork only |
| A Rejected view next to History lists every rejected request, including ones cleared from the list, with Reopen on each. Cards can be hidden from it, with a "Show hidden" toggle so nothing gets lost | This fork. Fork only |
| A rejected card says who declined it and when. Admin actions taken by scripts carry an `[auto]` note, so they can be told apart from a person's | This fork. Fork only |
| The format is a coloured pill on every card: Audiobook or Ebook on a request, the file format (EPUB, M4B, MP3) on a download, violet for audio and orange for ebooks. The requester is named once instead of twice | This fork. Fork only |
| Clear Completed also clears finished requests that never had a download, and shows on the Requests tab | This fork. Not sent upstream; a maintainer ask comes first (#1438, which it builds on, has merged) |
| A download that picks up work already under way (a torrent the client had, files already on disk, slskd transfers it rejoins) shows a Reattached pill | This fork. Fork only for the pill; the flag on the task is an upstream candidate, not sent yet |
| Finished cards say how long a download took and how long ago it ended, as text at the end of the existing line ("took 4m · 2h ago", "5m ago" on a failure, "delivered 3h ago" on a request) | This fork. Fork only |
| The Requests view says what is automatic and what is for a person: a decision the automation made reads "Declined automatically" or "Automatic: ..." instead of naming the admin account it acted through, "Needs Review" is "No Match Yet" with a line saying the search repeats on every sync and what the admin can do, and a request reopened after a failed download sits under "Retrying Automatically". Failure reasons use plain words | This fork. Fork only |
| Failed and cancelled cards say in plain words what happened and what comes next (another copy in about N minutes, or Retry), instead of the log line | This fork. Not sent yet (an upstream candidate now that the quick retry it describes has merged in [#1535](https://github.com/calibrain/shelfmark/pull/1535)) |

### Build

| Change | Origin |
|---|---|
| Fork-only CI: amd64-only images and no legacy alias job. This one isn't meant for upstream | This fork. Fork only |
| Mesa and LLVM are dropped from the image (about 180 MB). Chromium draws WebGL with its own SwiftShader, so they were never used | Ported from [DrNgo/shelfmark-fork@075caff](https://github.com/DrNgo/shelfmark-fork/commit/075caff) by [@DrNgo](https://github.com/DrNgo), the ffmpeg part left out because upstream still uses it. Not sent upstream yet; I'm asking him first whether he wants to send it himself |

Docs for the added features live on the branches that carry them:
[Hardcover sync](https://github.com/splitsec2/shelfmark/blob/build/fork-images/docs/hardcover-sync.md) ·
[Library check](https://github.com/splitsec2/shelfmark/blob/build/fork-images/docs/library-check.md).

## Upstream first

Anything here that is *not* library integration or automation belongs upstream, and goes there
instead of living in this fork. 99 pull requests from this fork have merged into
calibrain/shelfmark and none have been closed unmerged. [The full list](https://github.com/calibrain/shelfmark/pulls?q=is%3Apr+is%3Amerged+author%3Asplitsec2)
is on GitHub, and these are the clusters:

- **Hardcover sync and the Audiobookshelf check**, in five parts: [#1516](https://github.com/calibrain/shelfmark/pull/1516), [#1519](https://github.com/calibrain/shelfmark/pull/1519), [#1533](https://github.com/calibrain/shelfmark/pull/1533), [#1534](https://github.com/calibrain/shelfmark/pull/1534), [#1535](https://github.com/calibrain/shelfmark/pull/1535). They replaced
  [#1047](https://github.com/calibrain/shelfmark/pull/1047) by [@InfiniteAvenger](https://github.com/InfiniteAvenger),
  which this fork carried for a month, and the refactor [@InfiniteAvenger](https://github.com/InfiniteAvenger) wrote
  for it went in as [#1355](https://github.com/calibrain/shelfmark/pull/1355) (squash-merged under my account). Follow-ups: [#1569](https://github.com/calibrain/shelfmark/pull/1569), [#1589](https://github.com/calibrain/shelfmark/pull/1589), where
  [@joeRob2468](https://github.com/joeRob2468) traced the missing series.
- **Downloads and clients**: [#1409](https://github.com/calibrain/shelfmark/pull/1409), [#1420](https://github.com/calibrain/shelfmark/pull/1420), [#1421](https://github.com/calibrain/shelfmark/pull/1421), [#1426](https://github.com/calibrain/shelfmark/pull/1426), [#1429](https://github.com/calibrain/shelfmark/pull/1429), [#1431](https://github.com/calibrain/shelfmark/pull/1431), [#1459](https://github.com/calibrain/shelfmark/pull/1459), [#1493](https://github.com/calibrain/shelfmark/pull/1493), [#1494](https://github.com/calibrain/shelfmark/pull/1494), [#1495](https://github.com/calibrain/shelfmark/pull/1495), [#1538](https://github.com/calibrain/shelfmark/pull/1538), [#1572](https://github.com/calibrain/shelfmark/pull/1572), [#1573](https://github.com/calibrain/shelfmark/pull/1573), [#1577](https://github.com/calibrain/shelfmark/pull/1577), [#1570](https://github.com/calibrain/shelfmark/pull/1570)
  (stall windows, retries, qBittorrent 5 states, torrents that never start), the Soulseek source
  [#1428](https://github.com/calibrain/shelfmark/pull/1428) and its retry [#1590](https://github.com/calibrain/shelfmark/pull/1590), and [#1378](https://github.com/calibrain/shelfmark/pull/1378), which streams a finished book instead of
  buffering it in RAM ([@DrNgo](https://github.com/DrNgo) found that one).
- **Requests and the activity list**: [#1438](https://github.com/calibrain/shelfmark/pull/1438), [#1491](https://github.com/calibrain/shelfmark/pull/1491), [#1496](https://github.com/calibrain/shelfmark/pull/1496), [#1506](https://github.com/calibrain/shelfmark/pull/1506), [#1507](https://github.com/calibrain/shelfmark/pull/1507), [#1508](https://github.com/calibrain/shelfmark/pull/1508), [#1513](https://github.com/calibrain/shelfmark/pull/1513), [#1541](https://github.com/calibrain/shelfmark/pull/1541), [#1597](https://github.com/calibrain/shelfmark/pull/1597), [#1598](https://github.com/calibrain/shelfmark/pull/1598).
- **Search, metadata and library check**: [#1371](https://github.com/calibrain/shelfmark/pull/1371), [#1377](https://github.com/calibrain/shelfmark/pull/1377), [#1380](https://github.com/calibrain/shelfmark/pull/1380), [#1434](https://github.com/calibrain/shelfmark/pull/1434), [#1537](https://github.com/calibrain/shelfmark/pull/1537), [#1587](https://github.com/calibrain/shelfmark/pull/1587), the Calibre half of the library check
  after [discussion #1372](https://github.com/calibrain/shelfmark/discussions/1372).
- **Auth, errors and logs**: [#1356](https://github.com/calibrain/shelfmark/pull/1356), [#1358](https://github.com/calibrain/shelfmark/pull/1358), [#1359](https://github.com/calibrain/shelfmark/pull/1359), [#1360](https://github.com/calibrain/shelfmark/pull/1360) and [#1558](https://github.com/calibrain/shelfmark/pull/1558), [#1559](https://github.com/calibrain/shelfmark/pull/1559), [#1562](https://github.com/calibrain/shelfmark/pull/1562), [#1571](https://github.com/calibrain/shelfmark/pull/1571), [#1578](https://github.com/calibrain/shelfmark/pull/1578), [#1593](https://github.com/calibrain/shelfmark/pull/1593), [#1603](https://github.com/calibrain/shelfmark/pull/1603), which keep
  credentials, paths and exception text out of logs and responses. The fail-open auth fix that
  [DrNgo/shelfmark-fork](https://github.com/DrNgo/shelfmark-fork) made first went in as [#1397](https://github.com/calibrain/shelfmark/pull/1397), so this fork no longer carries its own copy.
- **Speed**: [#1539](https://github.com/calibrain/shelfmark/pull/1539), [#1544](https://github.com/calibrain/shelfmark/pull/1544), [#1545](https://github.com/calibrain/shelfmark/pull/1545), [#1546](https://github.com/calibrain/shelfmark/pull/1546).
- **Image and build**: [#1379](https://github.com/calibrain/shelfmark/pull/1379), [#1404](https://github.com/calibrain/shelfmark/pull/1404), [#1435](https://github.com/calibrain/shelfmark/pull/1435), the Chromium pin [#1614](https://github.com/calibrain/shelfmark/pull/1614), and [#1615](https://github.com/calibrain/shelfmark/pull/1615), which drops the
  unused selenium-manager binaries after [@wrycu](https://github.com/wrycu) raised the image contents in [#1606](https://github.com/calibrain/shelfmark/pull/1606).
- **Docs, tests and tidying**: [#1564](https://github.com/calibrain/shelfmark/pull/1564), [#1565](https://github.com/calibrain/shelfmark/pull/1565), [#1566](https://github.com/calibrain/shelfmark/pull/1566), [#1567](https://github.com/calibrain/shelfmark/pull/1567), [#1563](https://github.com/calibrain/shelfmark/pull/1563), [#1576](https://github.com/calibrain/shelfmark/pull/1576), [#1594](https://github.com/calibrain/shelfmark/pull/1594), [#1595](https://github.com/calibrain/shelfmark/pull/1595) (routes out of `main.py`) and
  [#1580](https://github.com/calibrain/shelfmark/pull/1580), [#1381](https://github.com/calibrain/shelfmark/pull/1381).

Open:

- [#1579](https://github.com/calibrain/shelfmark/pull/1579) let a book be requested alongside downloads
- [#1591](https://github.com/calibrain/shelfmark/pull/1591) answer anti-leech chat challenges from Soulseek uploaders, off by default
- [#1592](https://github.com/calibrain/shelfmark/pull/1592) sync each user's own Hardcover account (plan item 9 of the
  [original split](https://github.com/calibrain/shelfmark/pull/1047#issuecomment-6302071588))

What stays here is what upstream has not been asked for yet: the changes marked not sent yet or
fork only above. The badges, the cross-format markers, the series gap report and the scheduler
cycle guard are next, in small pieces.

## How it is maintained

The fork-only features are separate branches on top of upstream `main`, one per feature so each
can go upstream on its own, **rebased** and never merged, so every fork-only commit stays a
reviewable patch on top of current upstream. A weekly job trial-rebases them, runs upstream's
test suite and reports when upstream has moved. Images publish to
`ghcr.io/splitsec2/shelfmark:sha-<7>` from `build/fork-images`.

Licence and copyright are upstream's, unchanged.

---

# 📚 Shelfmark: Book Search & Request Tool

<img src="src/frontend/public/logo.png" alt="Shelfmark" width="200">

> [!NOTE]
> Shelfmark is feature stable and maintained on a best-effort basis. Bug fixes, security updates, and small quality-of-life improvements are still shipped, and pull requests are reviewed — including new features. There is no roadmap for new features for now.

Shelfmark is a self-hosted web interface for searching and requesting books and audiobooks across multiple sources. Bring your own sources, metadata providers, and download clients to build a single hub for your digital library. Supports multiple users with a built-in request system, so you can share your instance with others and let them browse and request books on their own.

Works great alongside the following library tools, with support for automatic imports:
- [Calibre](https://calibre-ebook.com/)
- [Calibre-Web](https://github.com/janeczku/calibre-web)
- [Calibre-Web-Automated](https://github.com/crocodilestick/Calibre-Web-Automated)
- [Grimmory](https://github.com/grimmory-tools/grimmory)
- [Audiobookshelf](https://github.com/advplyr/audiobookshelf)

## ✨ Features

- **One-Stop Interface** - A clean, modern UI to search, browse, and download from multiple configured sources in one place
- **Multiple Sources** - Configurable web (including OceanofPDF), torrent, usenet, IRC, Soulseek (slskd), and Webshare.cz source support, with indexers through Prowlarr or Jackett
- **Audiobook Support** - Full audiobook search and download with dedicated processing
- **Flexible Search** - Search metadata providers (Hardcover, Open Library, Google Books, DNB, Databáze knih, Moly.hu) for rich book and audiobook discovery, or query configured sources directly
- **Multi-User & Requests** - Share your instance with others, let users browse and request books, and manage approvals with configurable notifications
- **Authentication** - Built-in login, OIDC single sign-on, proxy auth, and Calibre-Web database support
- **Library Check** - Optionally mark search results you already own in a Calibre or Audiobookshelf library, so you don't download a second copy. See [Library Check](docs/library-check.md)
- **Hardcover Sync** - Optionally pull a Hardcover shelf in as requests and download the books without an admin picking a release. Off by default. See [Hardcover Sync](docs/hardcover-sync.md)
- **Real-Time Progress** - Unified download queue with live status updates across all sources
- **Network Flexibility** - Configurable proxy support, DNS settings, and optional Cloudflare handling for protected sources

## 🖼️ Screenshots

**Home screen**
![Home screen](README_images/homescreen.png 'Home screen')

**Search results**
![Search results](README_images/search-results.png 'Search results')

**Multi-source downloads**
![Multi-source downloads](README_images/multi-source.png 'Multi-source downloads')

**Download queue**
![Download queue](README_images/downloads.png 'Download queue')

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- At least 2 GB of RAM available to the container when using the standard image — see [Memory Requirements](#memory-requirements)

### Installation

1. Download the [docker-compose file](compose/docker-compose.yml):
   ```bash
   curl -O https://raw.githubusercontent.com/calibrain/shelfmark/main/compose/docker-compose.yml
   ```

2. Start the service:
   ```bash
   docker compose up -d
   ```

3. Open `http://localhost:8084`

Open the web interface, then configure the sources and settings you want to use.

### Volume Setup

```yaml
volumes:
  - /your/config/path:/config # Config, database, and artwork cache directory
  - /your/download/path:/books # Downloaded books
  - /client/path:/client/path # Optional: For Torrent/Usenet downloads, match your client directory exactly.
```

> **Tip**: Point the download volume to your CWA or Grimmory ingest folder for automatic import.

> **Note**: CIFS shares require `nobrl` mount option to avoid database lock errors.

### Non-root container mode

- Start the container as `1000:1000` with Docker `user: "1000:1000"` or `docker run --user 1000:1000`.
- For Kubernetes, set `runAsUser: 1000`, `runAsGroup: 1000`, and `runAsNonRoot: true` together.
- `PUID`/`PGID` keep the default root startup flow.
- Mounted paths must already be writable by `1000:1000`.
- `USING_TOR=true` requires root startup.

## ⚙️ Configuration

### Search Modes

**Direct**
- Queries configured sources directly

**Universal** (recommended)
- Search via metadata providers (Hardcover, Open Library, Google Books, DNB, Databáze knih, Moly.hu) for richer results
- Aggregates releases from multiple configured sources
- Full audiobook support

### Hardcover API Key

Hardcover powers metadata search in Universal mode. Create a token at
[hardcover.app/account/api](https://hardcover.app/account/api) — current keys start with `hc_pat_`
and are far shorter than the JWTs Hardcover issued before August 2026.

Tick these seven scopes on the token screen:

| Scope | Used for |
|-------|----------|
| `read:catalog` | Metadata search, plus book, edition, author and series lookups |
| `read:library` | Your reading status and shelf counts |
| `read:lists` | Your lists and the books on them |
| `read:me:content` | Test Connection and the "Connected as" label |
| `read:users` | Usernames shown alongside lists |
| `write:library` | Setting a book's reading status from Shelfmark |
| `write:lists` | Adding and removing books from lists, including auto-remove on download |

The two `write:` scopes matter only if you set reading status from Shelfmark or leave
**Auto-Remove from List on Download** enabled (it is on by default) — without them those actions
fail silently. Everything else Hardcover offers (journal, goals, reviews, prompts, notifications,
account) can stay unticked. The `all` scope works too, but it grants full account access including
deletion, so prefer the list above.

### Environment Variables

Environment variables work for initial setup and Docker deployments. They serve as defaults that can be overridden in the web interface.

| Variable | Description | Default |
|----------|-------------|---------|
| `FLASK_PORT` | Web interface port | `8084` |
| `INGEST_DIR` | Book download directory | `/books` |
| `TZ` | Container timezone | `UTC` |
| `PUID` / `PGID` | Runtime user/group for the default root-startup flow (also supports legacy `UID`/`GID`) | `1000` / `1000` |
| `SEARCH_MODE` | `direct` or `universal` | `universal` |
| `USING_TOR` | Enable Tor routing (requires root startup) | `false` |
| `USING_WIREGUARD` | Enable WireGuard VPN egress with kill-switch (requires root startup) | `false` |
| `WIREGUARD_CONFIG` | Path to the mounted wg-quick config | `/config/wg0.conf` |
| `WIREGUARD_INTERFACE` | WireGuard interface name | `wg0` |
| `LAN_NETWORK` | Comma-separated CIDRs kept off the tunnel so the WebUI / internal clients stay reachable | `127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16` |
| `WIREGUARD_ENFORCE_DNS` | Pin the resolver (via `WIREGUARD_DNS`, else the config's `DNS =`) so DNS can't silently fall back to an off-tunnel path. Designed for a trusted LAN resolver kept reachable via `LAN_NETWORK` (query leaves over the LAN; download still egresses via the tunnel) — it does **not** force queries through the tunnel. Docker's embedded resolver (`127.0.0.11`) is preserved when present so container-name resolution keeps working; pin its upstream via the container's `dns:` list. Fails closed if no resolver is available or `/etc/resolv.conf` is not writable. | `true` |
| `WIREGUARD_DNS` | Explicit resolver(s) to pin (comma/space separated). Use when the VPN's pushed DNS filters domains you need; point at a resolver reachable via the tunnel or an allowed LAN resolver. | _(unset; uses config `DNS =`)_ |
| `WIREGUARD_DISABLE_IPV6` | Strip IPv6 from the tunnel config (many container kernels lack the ip6tables `raw` table wg-quick needs) and remove IPv6 as a leak surface. | `true` |
| `WIREGUARD_ALLOW_IPV6_LEAK` | Escape hatch: continue even when an IPv6 kill-switch can't be installed AND IPv6 can't be disabled. Only set if the container has no IPv6 connectivity. | `false` |
| `WIREGUARD_ALLOW_WEBUI_OFFTUNNEL` | Opt-in off-tunnel WebUI reachability. Default (`false`) keeps the kill-switch strictly fail-closed: the only off-tunnel egress is loopback, the tunnel device and the LAN allowlist. Set `true` only if a **non-LAN** client (e.g. a public reverse proxy on another segment) must reach the WebUI; it permits app-server **replies** (`--sport FLASK_PORT`, conntrack REPLY) off-tunnel — server replies only, never client-initiated egress. LAN clients never need it (covered by `LAN_NETWORK`). | `false` |
| `WIREGUARD_STALE_AFTER` | Seconds since the last handshake before the healthcheck bounces the tunnel. | `180` |

See the full [Environment Variables Reference](docs/environment-variables.md) for all available options.

Some of the additional options available in Settings:
- **Prowlarr / Jackett** - Configure indexers to download books and audiobooks through your torrent and usenet clients
- **Download clients** - qBittorrent, Transmission, Deluge, rTorrent, NZBGet, SABnzbd, a blackhole folder, or a debrid service (AllDebrid, Real-Debrid, TorBox, Debrid-Link)
- **Additional audiobook sources** - Configure additional sources for audiobook discovery
- **Webshare.cz** - Search Webshare.cz by file name and download ebooks and audiobooks with your Webshare account (a VIP account is recommended for full speed)
- **Direct Download mirrors** - Supply your own Anna's Archive mirror URLs; Auto mode tries them in the order listed. The `annas-archive.is` domain does not currently work as a source — use `annas-archive.gl` instead (checked August 2026; mirror availability changes)
- **IRC** - Add details for IRC book sources and download directly from the UI. Most networks serve audiobooks from the same channel as ebooks (on `irc.irchighway.net` that's `#ebooks`, while `#bookz` is effectively inactive), so leave the separate audiobook channel blank unless your network actually indexes one. IRC audiobooks usually arrive as ZIP/RAR archives — keep those enabled under Supported Audiobook Formats or the releases are filtered out of results
- **Soulseek (slskd)** - Search the Soulseek network and download through a [slskd](https://github.com/slskd/slskd) instance. Point Shelfmark at slskd's URL with an API key (`web.authentication.api_keys` in `slskd.yml`, role `readwrite`), and mount slskd's downloads folder into the Shelfmark container. If the folder sits at a different path inside Shelfmark, set **Downloads Path** in the slskd settings or add a Remote Path Mapping for client `slskd`. Ebook results are single files; audiobook results group a peer's folder of audio files into one release
- **Library Link** - Add links to your book library (Calibre-Web or Grimmory) and your audiobook library (Audiobookshelf, Plex) in the UI header
- **File processing** - Customiseable download paths, file renaming and directory creation with template-based renaming
- **Network Settings** - Custom proxy support (SOCKS5 + HTTP/S) and configurable DNS
- **Format & Language** - Filter downloads by preferred formats, languages and sorting order
- **Metadata Providers** - Configure API keys for Hardcover, Google Books and the other metadata providers

## 🐳 Docker Variants

### Standard
```bash
docker compose up -d
```

The full-featured image with all network capabilities included.

#### Memory Requirements

The standard image ships a real Chromium browser, which it launches to solve Cloudflare challenges for Direct Download. Chromium needs room to run:

- **2 GB of RAM available to the container** is a safe minimum; 1 GB or less is where problems usually start
- Only relevant if you use Direct Download. Prowlarr, IRC and audiobook sources don't start the browser

When the container is starved of memory, Chromium fails to start and every Direct Download fails with unrelated-looking errors — repeated `403 detected; switching to bypasser` followed by `No download URL found`, and downloads that never complete. If you're seeing that, check the container's memory limit and the host's free memory before suspecting your ISP or DNS.

If you can't spare the memory, use the [Lite](#lite) image with an external resolver (e.g. FlareSolverr) running elsewhere.

#### Tor Routing
Optional Tor support for network privacy:
```bash
curl -O https://raw.githubusercontent.com/calibrain/shelfmark/main/compose/docker-compose.tor.yml
docker compose -f docker-compose.tor.yml up -d
```

**Notes:**
- Requires root startup
- Requires `NET_ADMIN` and `NET_RAW` capabilities
- Timezone is auto-detected from Tor exit node
- Custom DNS/proxy settings are ignored when Tor is active

#### WireGuard VPN Routing
Optional WireGuard support to route all external egress through a VPN tunnel with a fail-closed kill-switch:
```bash
curl -O https://raw.githubusercontent.com/calibrain/shelfmark/main/compose/docker-compose.wireguard.yml
# place your wg-quick config where the compose mounts /config, as wg0.conf
docker compose -f docker-compose.wireguard.yml up -d
```

**Notes:**
- Requires root startup
- Requires `NET_ADMIN` and `NET_RAW` capabilities
- Mount a standard wg-quick config at `WIREGUARD_CONFIG` (default `/config/wg0.conf`)
- All non-LAN egress is forced through the tunnel; if the tunnel drops, external traffic **fails closed** while LAN ranges (WebUI, Prowlarr, qBittorrent) stay reachable
- IPv4 and IPv6 both fail closed. On kernels without a usable `ip6tables`, disable IPv6 for the container (`sysctls: net.ipv6.conf.all.disable_ipv6=1`, as in the compose example) or the container refuses to start rather than risk an IPv6 leak
- A supervised healthcheck bounces the tunnel if the handshake goes stale, and refreshes the endpoint allow rules so a roaming/rotated peer endpoint can reconnect
- Mutually exclusive with `USING_TOR`
- **DNS trust:** `WIREGUARD_DNS` must be a resolver you trust on a trusted network segment. When it is a LAN resolver (kept reachable off-tunnel by `LAN_NETWORK`), the query to that resolver leaves as plaintext UDP/53 on the LAN — the resolver is responsible for encrypting upstream. Two resolver paths exist: (1) when Docker's embedded resolver (`127.0.0.11`) is present it is **preserved** so container names (Prowlarr, qBittorrent) resolve — you MUST pin its upstream to a trusted resolver via the container's compose `dns:` list, since `WIREGUARD_DNS` cannot repoint the embedded resolver from inside the container; (2) otherwise `WIREGUARD_DNS`/the config `DNS =` line is written to `/etc/resolv.conf`. Setting `WIREGUARD_ENFORCE_DNS=false` is a **foot-gun**: with no embedded resolver present the container then uses its inherited resolver, which forwards to the Docker daemon's upstream **off-tunnel**, leaking your DNS. Leave enforcement on unless you have pinned the resolver another way.

### Lite
A lighter image without the built-in browser automation. Ideal for:

- **External services** - Already running FlareSolverr or similar for other applications
- **Alternative sources** - Using Prowlarr, IRC, or other configured sources
- **Audiobooks** - Using Shelfmark primarily for audiobooks
- **Constrained hosts** - No bundled browser, so it runs comfortably below the standard image's [memory requirements](#memory-requirements)

```bash
curl -O https://raw.githubusercontent.com/calibrain/shelfmark/main/compose/docker-compose.lite.yml
docker compose -f docker-compose.lite.yml up -d
```

If you need browser-based access with the Lite image, configure an external resolver in Settings.

## 🔐 Authentication

Authentication is optional but recommended for shared or exposed instances. Multiple authentication methods are available in Settings:

**1. Single Username/Password**

**2. Proxy (Forward) Authentication**

Proxy auth trusts headers set by your reverse proxy (e.g. `X-Auth-User`). Ensure Shelfmark is not directly exposed, and configure your proxy to strip/overwrite these headers for all inbound requests.

**3. OIDC (OpenID Connect)**

Integrate with your identity provider (Authelia, Authentik, Keycloak, etc.) for single sign-on. Supports PKCE flow, auto-discovery, group-based admin mapping, and auto-provisioning of new users.

**4. Calibre-Web Database**

If you're running Calibre-Web, you can reuse its user database by mounting it:

```yaml
volumes:
  - /path/to/calibre-web/app.db:/auth/app.db:ro
```

### Multi-User Support

With any authentication method enabled, Shelfmark supports multi-user management with admin/user roles. Users can have per-user settings for download destinations, email recipients, and notification preferences. Non-admin users only see their own downloads and can submit book requests for admin review. Admins can configure request policies per source to control whether users can download directly, must submit a request, or are blocked entirely.

See [API Access](docs/api-access.md) to call the API with a static key from scripts and integrations.

## Project Scope

Shelfmark is a manual search and download tool, the entry point to your book library, not a library manager. It finds books, downloads them, and sends them to a configured destination. That's the core scope.

Shelfmark intentionally does not:

- **Manage your library** - it never edits, tags or reorganises what you already own. The optional [Library Check](docs/library-check.md) only reads your Calibre or Audiobookshelf library to mark results you already have
- **Integrate with library software beyond delivery** - what happens after delivery is up to your library tool
- **Monitor authors, series, or new releases** - there is no watching for new books. The optional [Hardcover Sync](docs/hardcover-sync.md) is the one background job: it turns a Hardcover shelf you choose into requests, and it is off by default
- **Queue future downloads** - if a book isn't available now, Shelfmark won't watch for it. Hardcover Sync retries a request on a schedule, which is the closest it gets

These are non-goals, not missing features.

## Contributing

Shelfmark's core feature set is complete.

Pull requests are welcome and all of them get reviewed, new features included. If you want a feature, the fastest path is to send a PR for it rather than to file a request.

Feature requests that fall outside the project scope (library integration, automation, collection management) will be closed, and PRs implementing them won't be merged. If you're unsure whether something fits, open a discussion first.

## Health Monitoring

The application exposes a health endpoint at `/api/health` (no authentication required). Add a health check to your compose:

```yaml
healthcheck:
  test: ["CMD", "curl", "-sf", "http://localhost:8084/api/health"]
  interval: 30s
  timeout: 30s
  retries: 3
```

The endpoint answers 503 when the download coordinator, the part that picks queued downloads up, is not running. Without it every download stays queued, so a container that reports unhealthy for this reason needs a restart.

## Logging

Logs are available via:
- `docker logs <container-name>`
- `/var/log/shelfmark/` inside the container (when `ENABLE_LOGGING=true`)

Log level is configurable under Settings → Advanced or via the `LOG_LEVEL` environment
variable (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`; case-insensitive, defaults to
`INFO`). The environment variable wins over the setting, and `DEBUG=true` forces `DEBUG`
regardless of either. Changes take effect on restart.

## Development

```bash
# Quality checks
make checks              # Run ALL static analysis (frontend + Python)
make python-checks       # Run Ruff, BasedPyright, and Vulture
make install-python-dev  # Sync Python runtime + dev tools with uv

# Frontend development
make install     # Install dependencies
make dev         # Start Vite dev server (localhost:5173)
make build       # Production build
make frontend-typecheck  # TypeScript checks

# Backend (Docker)
make up          # Start backend via docker-compose.dev.yml
make down        # Stop services
make refresh     # Rebuild and restart
make restart     # Restart container
```

The frontend dev server proxies to the backend on port 8084.

## License

MIT License - see [LICENSE](LICENSE) for details.

## ⚠️ Disclaimer

Shelfmark is a search interface that displays results from external metadata providers and sources. It does not host, store, or distribute any content. The developers are not responsible for how the tool is used or what is accessed through it.

Users are solely responsible for:
- Ensuring they have the legal right to download any material they access
- Complying with copyright laws and intellectual property rights in their jurisdiction
- Understanding and accepting the terms of any sources they configure

Use of this tool is entirely at your own risk.

## Support

For issues or questions, please [file an issue](https://github.com/calibrain/shelfmark/issues) on GitHub.
