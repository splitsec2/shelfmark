# Shelfmark base image: PR #1616 (Chainguard/Wolfi) vs stripped Debian

Run on 2026-11-01. The first pass ran on a machine without Docker, and the real builds ran on GitHub Actions on my fork the same day.

- **main:** `0a7e114`. The published `latest` is v1.6.0 (`9bd6c51`, amd64 `sha256:4dfada99...`); `git diff 9bd6c51 origin/main -- Dockerfile entrypoint.sh pyproject.toml uv.lock` is empty, so `latest` matches main for this comparison.
- **PR:** `a7b1b84`, branched from `7583f99`, so it predates #1609, #1610, #1614 and #1615. GitHub reports it as CONFLICTING.
- **Scanner:** Trivy 0.76.1, vulnerability DB of 2026-11-01 7:02 am.

> **"Real builds" holds the only current recommendation: D1, on Debian Chromium.** It reports real Docker builds on both architectures and supersedes the numbers and any recommendation in the sections after it. Those are kept as the record of how we got there.

## Real builds (GitHub Actions)

Every result here is `[verified]` from a real `docker build` on a GitHub-hosted runner, amd64 and arm64, with logs and JSON downloaded and read, unless tagged otherwise. Both architectures agreed on every case except where noted.

- **Run 1:** 41335522683. main, ffmpeg patch, #1616 as written. 6 jobs.
- **Run 2:** 41339436116. main, ffmpeg patch, D1, D2, rebased Wolfi. 10 jobs, all from main at `0a7e114`.
- **Harness:** temporary branch `test/base-image-matrix` on `splitsec2/shelfmark`, orphan, so none of Shelfmark's workflows ran. Actions pinned by SHA, scanners pinned by version or digest, no secrets, images never pushed, only logs and JSON uploaded. No job needed an infrastructure re-run.

### The variants

| Variant | What it is |
|---|---|
| main | Upstream at `0a7e114`, control |
| ffmpeg patch | main + `ffmpeg-optional.patch` |
| **D1** | Patch + supervisor in `uv.lock` + direct `libtk`/`libtcl`. Chromium stays .73: **`trixie-security` and snapshot.debian.org top out at 156.0.8078.73 on both architectures, rechecked 1:30 pm, so the bump to at least .79 isn't available.** |
| D2 | D1 with Chrome for Testing .80 instead of Debian Chromium. Evaluated and declined, see the recommendation below. |
| **Rebased Wolfi** | #1616 rebased on main, `wg-quick` from upstream pinned by hash, Chrome for Testing .80. Keeps ffmpeg. |

### Results

| | main | Patch | D1 | D2 | Rebased Wolfi | #1616 as written |
|---|---|---|---|---|---|---|
| Trivy, full: all | 1158 | 752 | 655 | **534** | **0** | 9 |
| Critical / High | 1 / 297 | 1 / 148 | 1 / 122 | 1 / 73 | 0 / 0 | 1 / 3 |
| **Findings with a fix** | 0 | 0 | 0 | 0 | 0 | 9 |
| Trivy, lite: all | 442 | 442 | 359 | 359 | 0 | 0 |
| **OSV, same source: distinct IDs** | 453 | not run | 339 | 275 | **18 CVEs** (65 entries) | not run |
| Grype, full: all | 1135 | 738 | 641 | 520 | 10 | not run |
| **Browser** | .73 | .73 | .73 | .80 | .80 | **.47** |
| **NVD CVEs for that browser version** | 21 | 21 | 21 | **0** | **0** | **72** |
| Scanners see the browser? | yes | yes | yes | **no** | **no** | no |
| Gzipped image, amd64 | 454 MB | 376 MB | 362 MB | **359 MB** | 446 MB | 455 MB |
| Gzipped lite, amd64 | 93 MB | 93 MB | 80 MB | 80 MB | **74 MB** | 74 MB |
| **Manual pins nothing tracks** | 3 | 3 | **3** | 4 | **10** | 8 |
| Smoke as uid 1000 | pass | pass | pass | pass | pass | pass |
| Tor (`IsTor: true`) | pass | pass | pass | pass | pass | pass |
| WireGuard tunnel + egress | pass | pass | pass | pass | pass | **fail** |
| Kill switch, tunnel down | pass | pass | pass | pass | pass | not applicable |
| RAR samples read of 51 | 35 | 35 | 35 | 35 | **40** | 40 |
| `import tkinter, pyautogui, mouseinfo` under Xvfb | pass | pass | pass | pass | pass | not run |
| `tkinter.Tk()` window | pass | pass | pass | pass | **fail** | not run |
| Debug recording (mp4) | pass | pass | pass | pass | pass | pass |
| Cloudflare demo page | not solved | not solved | not solved | not solved | not solved | timed out |

"Findings with a fix" comes from Trivy's `FixedVersion` in the same JSON, not a separate `--ignore-unfixed` run. For D2, the real build's 534 replaces the 558 from my rootfs replay; the Debian package sets differ.

### What Wolfi's "0" hides (`[verified]`, except where tagged)

Installed: 224 apk packages. Queried by `pkg:apk/wolfi/<name>@<version>` and also by the `Wolfi` and `Chainguard` ecosystems, which gave the same 65 entries. **All 65 have no `fixed` event. They collapse to 18 distinct CVEs.**

| Source | Result |
|---|---|
| Trivy | 0 |
| OSV batch | 18 CVEs |
| Grype | 10, **all also in OSV**; none are Wolfi-feed matches, all are `cpe-match` against NVD. `--only-notfixed` returned the same 10. 8 OSV CVEs (glibc 5, expat 2, python 1) don't appear in grype. |

Latest status from `advisories.cgr.dev`:

| Chainguard status | CVEs | Which |
|---|---|---|
| `pending_upstream_fix` | 9 | ffmpeg-9.0 (5), alsa-lib (3), expat (1) |
| `detection` (newly detected) | 2 | python-3.14, expat |
| `fix_not_planned` | 1 | python-3.14, CVE-2025-15367 |
| `fixed` | 5 | glibc-2.44 (4), python-3.14 (1) |
| `false_positive_determination` | 1 | glibc-2.44 |

- So about **12 are open by Chainguard's own status.** The 5 `fixed` ones still have no `fixed` event in OSV, and I didn't verify the fix against the installed version. `[unverified]`
- I saw no status literally named "under investigation"; `detection` is the closest.
- The same OSV query on Debian returned 453 (main), 339 (D1) and 275 (D2) IDs. **So the gap is real and large: about 18 vs 275.** This corrects my earlier statement that it couldn't be measured. Feed coverage still differs between distros, so read it as an order of magnitude, not an exact ratio. `[unverified]`
- Removing ffmpeg from Wolfi would take out the 5 ffmpeg CVEs, based on package names. `[unverified]`, not built.

### Software outside the package manager

| Check | Chrome for Testing | Source-built Tor |
|---|---|---|
| Trivy lists it? | no | no |
| Syft SBOM lists it? | no | no |
| Version vs latest | 156.0.8078.80 = stable | 0.4.9.15 = latest on dist.torproject.org |
| NVD by CPE, rate-limited and noisy | .80: **0**. .73: **21** (2 Critical, 16 High), the same 21 as Trivy's Debian list. .47: **72** (16 Critical, 50 High). | 1, but it's CVE-2017-16541, a Tor *Browser* issue: a false match |
| `ldd` "not found" | 0 | 0 |
| Libraries owned by apk | 72 checked across both, 71 owned | |

- The one unowned result is `libffi`: `apk info -W` fails because the package installs to `/usr/lib64` and the lookup used `/usr/lib`. `apk info -L libffi` lists it, so it is apk-owned.
- NVD's 0 for .80 reflects today's data and will lag new disclosures. **Nothing would flag it when that changes**, which is why D2 and Wolfi need a freshness check.

### ffmpeg patch gaps

| Case | Result, patch and D1/D2 | Evidence |
|---|---|---|
| Debug off, startup added | **None** | `/api/health` 3-4 s, main 3 s |
| Debug only in config, startup added | **About 10-11 s** | 13-15 s, main 3-4 s; real mp4 after |
| Debug env, startup added | About 10-11 s | 19-21 s, main 9-10 s |
| Fresh named volume, Debug only in config | pass | Recording made, uid 1000 writes OK |
| Existing uid-1000 volume, Debug only in config | pass | Same, `root_owned_on_host=0` |
| `find /config /var/log/shelfmark -user root` | **0 files** | Same as main |
| `find /app -user root` | 245, same as main | Image's own files; list identical to main |
| `--user 1000`, Debug on | pass | Logs both messages, bypass works, no mp4 |
| apt blocked (closed proxy) | pass | `Could not install ffmpeg` logged, bypass works, no mp4, about 7 s added |
| `--network none`, Debug on | pass | Running, health 200 inside after 60 s; no hang |

The root-phase import of `shelfmark.config.env` leaves nothing root-owned. **No gap found.**

### D1 and D2 runtime checks

Both pass everything above. Debian's Python 3.13 packages are gone (0, against 17 on the patch alone), which removes that package family's findings. Supervisor from `uv.lock` runs Tor. `import tkinter, pyautogui, mouseinfo` and a real `Tk()` window work, so **direct libtk is safe to use; `python3-tk` isn't needed.**

### Wolfi: new finding on Tk

The import passes, but `tkinter.Tk()` fails: "Cannot find a usable init.tcl". Wolfi's `tcl` package installs it at `/usr/library/init.tcl`, and Tcl looks in `/usr/lib/tcl9.1`. That's a packaging fault. Shelfmark's source doesn't call `tkinter` or `pyautogui` directly, and `mouseinfo` and `pymsgbox` only open windows when their GUI functions are called, so nothing in these tests hit it. Whether SeleniumBase can reach it on any challenge path isn't proven either way. `[unverified]`

### Sandbox

**No case works by default.** On all variants and architectures, default Docker gives "No usable sandbox!" and Chrome doesn't start.

| Docker setting (uid 1000, no `--no-sandbox`) | Starts? | Renderer | Bypass code on example.com |
|---|---|---|---|
| Default | no | | |
| Narrow seccomp profile: adds only `clone`, `unshare`, `setns`, **no capabilities** | yes | Own PID and network namespace, plus an extra seccomp filter (2 vs browser's 1) | pass |
| `seccomp=unconfined` (run 1) | yes | Same isolation | pass |
| `--cap-add SYS_ADMIN` (run 1) | yes | Same isolation | pass |

With `--no-sandbox`, renderers share the browser's namespaces and have the same filter count (1 and 1). So the flag does remove real isolation. The narrow profile is the only clean option, and each user would have to add it. It could be offered as optional hardening. With it, the demo page result was the same: not solved.

### Cloudflare demo page

A real challenge was served on `scrapingcourse.com/cloudflare-challenge`. **No variant solved it, including main, with or without the sandbox.** All 10 jobs: 18 attempts, "same challenge detected 4 times", about 6 minutes, then the budget ran out. Identical behaviour gives no sign that Chrome for Testing is worse, but no solve means it doesn't show it's as good, either. This is from Azure IPs, and #1614 saw the same non-solve from a different network.

### Pins and browser-bump burden

Read from each variant's Dockerfile and `pyproject.toml` on 2026-11-01. No variant changes `.github/dependabot.yml`, and no workflow tracks any pin; CI's Docker job only builds lite on amd64. `[verified]` for the pin lists. "Tracked" comes from reading the Dependabot config; the Wolfi `latest@sha256` line and the new supervisor entry have not been seen working. `[unverified]`

| Pin | main | D1 | D2 | Rebased Wolfi | Tracked by |
|---|---|---|---|---|---|
| Frontend base digest | `node:24-alpine` | same | same | `wolfi-base` | Dependabot `docker` |
| uv tag and digest | yes | yes | yes | yes | Dependabot `docker` |
| Python image tag and digest | yes | yes | yes, 2 `FROM` lines | none | Dependabot `docker`, patch only |
| `wolfi-base:latest` digest | | | | 4 `FROM` lines | Dependabot `docker` `[unverified]` |
| supervisor | apt, unpinned | `pyproject.toml` and `uv.lock` | same | **version and hash, by hand** | D1/D2: Dependabot `uv` `[unverified]`. Wolfi: nothing |
| `CHROMIUM_VERSION` | **manual** | **manual** | | | nothing |
| `CHROMIUM_SNAPSHOT` | **manual** | **manual** | | | nothing |
| `CHROME_VERSION` | | | **manual** | **manual** | nothing |
| `CHROME_SHA256_AMD64` | | | **manual** | **manual** | nothing |
| `CHROME_SHA256_ARM64` | | | **manual** | **manual** | nothing |
| `TOR_VERSION` | | | | **manual** | nothing |
| `TOR_SHA256` | | | | **manual** | nothing |
| `WG_QUICK_VERSION` | | | | **manual** | nothing |
| `WG_QUICK_SHA256` | | | | **manual** | nothing |
| `python-xlib==0.33` | **manual** | **manual** | **manual** | **manual** | nothing |
| **Manual values, total** | **3** | **3** | **4** | **10** | |

- Wolfi's supervisor line is 2 of the 10 (version and hash).
- **Floating, so not counted as pins:** apt packages on Debian variants; every apk package on Wolfi, including `python-3.14` and `nodejs-24`, whose minor or major is fixed only by the package name.
- **Wolfi coupling:** `wireguard-tools` floats with apk while `wg-quick` is pinned to a release, so the two can drift apart with nothing noticing.

**Bumping the browser once**

| Step | main, D1 | D2, rebased Wolfi |
|---|---|---|
| 1. Find the version | Wait for Debian to publish it. Today that blocks: Debian has .73, the fix is in .79. | `last-known-good-versions.json`. Today: .80. |
| 2. Get what you need to pin | Find a `snapshot.debian.org` timestamp that has it for amd64 and arm64 | Download both zips, about 170 MB each, and hash them. Google publishes no checksums, so the hash records what was downloaded and doesn't prove it's authentic. |
| 3. Edit | 2 ARGs and the comment (3 lines, as in #1614) | 3 ARGs and the comment |
| 4. Check libraries | apt resolves them | Compare with the new `deb.deps`; a new library means a hand edit |
| 5. Test | Build and smoke, plus a bypass check. Debian's Chromium 150 once broke the CDP bypasser (#1105). | Same |
| Notified by | Nothing tracks it today | Nothing tracks it, and Trivy can't see the browser either |


### Recommendation: D1, on Debian Chromium

1. **Open the ffmpeg PR.** Every gap tested clean on both architectures. It takes out 406 findings, 149 High and 78 MB.
2. **Move supervisor into `uv.lock` and use `libtk`/`libtcl` directly.** That drops Debian's Python 3.13 family. Result: 655 findings and the same 3 manual pins as today. Tor, WireGuard and `Tk()` all pass.
3. **Stay on Debian's Chromium and add a scheduled check** that flags when Debian publishes a newer chromium, because nothing does today and the pin goes stale silently. The check isn't built or tested. `[unverified]`
4. **#1616 can't merge unchanged.** With its blockers fixed Wolfi works, except `Tk()`, and it ships fewer known-unfixed CVEs (18 vs 339). It also costs 10 hand-kept pins against 3, `apk` packages that float with no snapshot to roll back to, and a browser no scanner can see. That needs a named owner.

**Chrome for Testing was evaluated and declined, so D2 is out.** It built and passed everything, and .80 has 0 NVD CVEs today. The reasons:

- It hides the browser from every scanner, and the browser is the riskiest component.
- It adds two hashes per bump, on top of the version.
- It changes the browser under bypass code that has already proven sensitive to Chromium versions (#1105, #1614).

The cost of this decision is that the image stays on .73 until Debian publishes a newer build. The 21 CVEs on .73 are all fixed in .79, and Chrome runs with `--no-sandbox` on every variant, so that exposure stays open until then.

### Conclusion (superseded by the recommendation above)

Kept as the record of the earlier call. It preferred Chrome for Testing, which has since been declined.

1. **Open the ffmpeg PR.** Every gap tested clean, on both architectures. It's worth doing on any base: -406 findings, -149 High, -78 MB. On Wolfi it would need `apk` in place of `apt-get`.
2. **The browser is the real risk, and it's the one thing the base image scan doesn't settle.** 21 CVEs on .73, all fixed at .79, with `--no-sandbox` always on. Debian doesn't have the fix today; Chrome for Testing does. #1616 as written would make this much worse (72), so it can't merge unchanged.
3. **My call on the base: rebased Wolfi, if the maintainer accepts a pin-check workflow; otherwise D2.**
   - Wolfi wins on what it ships: 18 known-unfixed CVEs against 275, and everything tested works, including Tor and WireGuard once `wg-quick` is supplied. It also reads more RAR files.
   - It costs 10 hand-kept pins against 4, floating `apk` packages with no snapshot to roll back to, and the Tk packaging fault. It's also the largest of the three candidates.
   - D2 is the smaller step: 359 MB, 4 pins, and the same browser. It carries far more unfixed findings, nearly all with no fix available.
   - **D1 adds no upkeep but leaves the browser where it is**, so it's a good interim, not an end state.
4. **Either D2 or Wolfi needs a small scheduled check** that compares the Chrome and Tor pins with upstream, because no scanner will flag them. Worth adding before or with the move. Not built or tested. `[unverified]`

### What I didn't run, and why

- **A solved Cloudflare challenge.** None succeeded on any variant; that's a result, not a gap in running it. Real book-source sites weren't tested, on purpose.
- **Dependabot on `wolfi-base:latest@sha256` and the new `uv.lock` entry.** It only acts on its own schedule on the default branch.
- **`--ignore-unfixed` as a separate flag.** Counted from `FixedVersion` in the same JSON.
- **A real VPN provider or real-world Tor load.** The WireGuard peer was the runner itself, and the kill switch was checked with one `curl` over IPv4.
- **OSV for the ffmpeg patch or #1616 as written.** They add nothing to the comparison. **Grype for #1616 as written:** run 1 predates it.
- **`seccomp=unconfined` and `SYS_ADMIN` on D1, D2 and rebased Wolfi.** Run 2 kept only the default and narrow-profile cases, which decide the question.
- **Non-free `unrar` in real builds.** Out of scope for these runs; those numbers come from the earlier rootfs test.
- **Wolfi without ffmpeg.** Not built.
- **Rebuild reproducibility on Wolfi.** Both runs used one day's `apk` index.
- One Tor check on D1 arm64 returned blank from `check.torproject.org`, while the same job's `tor.routed` case passed. Treated as a flaky network call and not re-run.

## Earlier pass, without Docker (superseded by "Real builds")

This pass ran on a machine without Docker. **No image was built for either branch.**

I replaced the builds with something that needs no Docker:

- **Debian:** extracted the published image's layers into a local directory and removed packages with `dpkg`.
- **PR:** extracted the pinned `wolfi-base` and replayed the PR's Dockerfile steps by hand: real `apk`, `uv`, the pinned Chrome and Tor, checksums checked.
- **Execution:** everything ran under `unshare -Ur` in private mount and PID namespaces.

In this report, `[verified]` means I saw the command and output, and `[replay]` also means the result came from a rootfs replay, not a built image.

**How far to trust the replay:** `trivy rootfs` on the extracted published image gave the same result as `trivy image` (1159 findings, zero differences in package or CVE sets), and its smoke test passed. `[verified]`

## TL;DR (superseded by "Real builds")

**Earlier recommendation, kept as a record: don't merge #1616 as it stands. Remove ffmpeg from the default image now, on any base, and take #1616 afterwards if its blockers are fixed. The scan totals alone don't justify the switch.**

| Measure | Published `latest` (Debian) | Debian, ffmpeg removed `[replay]` | PR #1616 as written `[replay]` | PR #1616 rebased on #1615 (modelled) |
|---|---|---|---|---|
| Total findings, full | **1159** | **753** | **9** | **0** |
| Critical / High | 1 / 297 | 1 / 148 | 1 / 3 | 0 / 0 |
| Findings with a fix available | **1** | 1 | 9 | 0 |
| Findings, lite | 442 | not applicable (no ffmpeg in lite) | **0** | 0 |
| OS packages | 413 | 320 | 224 | 224 |
| Size, tar then gzip of rootfs | 448 MB (published layers: 463 MB) | 375 MB | 464 MB | not measured |
| Smoke test: `internal_bypasser.get()` on example.com | pass | pass, **fails if DEBUG is on** | pass | not run |
| Chromium version | 156.0.8078.73 | same | **156.0.8078.47** | needs a bump |
| Is the browser visible to the scanner? | yes | yes | **no** | no |
| WireGuard egress | `wg-quick` present | present | **`wg-quick` missing** | still missing |

Four findings decide this:

1. **0 vs 1159 is not like for like.** Trivy documents Wolfi as behaving like Alpine, and Alpine has no unfixed-vulnerability detection. 1158 of Debian's 1159 findings have no fix available, and that category can't appear on a Wolfi scan. Counting only findings with a fix, main has 1 and the rebased PR has 0. Wolfi's packages are newer (libxml2 2.15.0 vs Debian's 2.9.14 base), which is a real gain, but this scan cannot measure its size.
2. **The PR's low count hides the browser, which is the riskiest component.** Trivy lists neither Chrome for Testing nor the source-built Tor. Every one of the 21 Chromium CVEs on main is described as fixed in Chrome 156.0.8078.79, so the PR's .47 build is also older than the fix, and its scan reports none of them. Chrome runs with `--no-sandbox` against third-party sites.
3. **The PR breaks WireGuard.** Wolfi's `wireguard-tools` ships only `wg`, and `wireguard.sh` calls `wg-quick`. `USING_WIREGUARD=true` would fail with exit 127.
4. **Removing ffmpeg is the best value on Debian but needs a code change.** It drops 93 packages, 406 findings (149 High) and 73 MB. Without a guard, turning Debug on breaks every bypass, because `Popen` raises `FileNotFoundError`.

### Blockers before #1616 can merge

1. Provide `wg-quick`, then test a real tunnel.
2. Rebase. That picks up #1615, which removes the only 9 findings, and the newer uv.
3. Bump Chrome to at least .79. Chrome for Testing stable is at .80 today, ahead of Debian's .73.
4. Add a freshness check for Chrome and Tor, because no scanner or Dependabot rule will flag them.
5. Fix `dependabot.yml`. The PR's Dockerfile cites "the python notes" there, but the PR doesn't touch the file, and its `python` and `node` rules no longer match any image.
6. Test Tor and WireGuard in a real container, and test a Cloudflare challenge. Chrome for Testing has not been shown to solve one.

## 1. ffmpeg

### Where it is used `[verified]`

| Item | Detail |
|---|---|
| Install | `Dockerfile:162`, in the full image's `RUN`. Not in lite. |
| Trigger | `shelfmark/bypass/internal_bypasser.py:1427`: `app_config.get("DEBUG", False)` and no recorder running, each time a browser is created |
| Stop | `_stop_ffmpeg_recording()` on browser close and orphan cleanup (`:1443`, `:383`) |
| Output | `RECORDING_DIR` = `LOG_DIR/recording`: `/var/log/shelfmark/recording/screen_recording_<ts>.mp4`, with `<same>.ffmpeg.log` beside it |
| Tests | `tests/bypass/test_ffmpeg_recording_diagnostics.py` asserts `-f x11grab` and the error log |

The exact command (`:1511`):

```
ffmpeg -y -f x11grab -i <display> -c:v libx264 -preset ultrafast -maxrate 700k -bufsize 1400k -crf 36 \
  -pix_fmt yuv420p -tune animation -x264-params bframes=0:deblock=-1,-1 -r 15 -an <out.mp4> -nostats -loglevel error
```

- **Other callers:** none. `grep -rIl ffmpeg` over `*.py` in the published image's venv, including SeleniumBase, returned nothing. `[verified]`
- **Does recording work today?** Yes, with DEBUG on, on both bases: a 108,828-byte mp4 on Debian and a 128,927-byte mp4 on the PR's ffmpeg 9.0.2. `[replay]`

### Trap: DEBUG has two sources `[verified]`

`shelfmark/config/env.py:36` reads the `DEBUG` env var and falls back to `/config/plugins/advanced.json`, and the UI has a "Debug Mode" checkbox (`settings.py:2020`). `entrypoint.sh:502` checks only the env var. An entrypoint-only install would therefore miss anyone who enabled Debug in the UI.

I hit this by accident: a `DEBUG=true` run persisted to `advanced.json`, and the next run, with no env var, failed:

```
RuntimeError: FileNotFoundError: [Errno 2] No such file or directory: 'ffmpeg'
```

The non-debug smoke run passed once I deleted that file. `[replay]`

### Sketch: install on demand plus a guard (not applied)

```bash
# entrypoint.sh, in the DEBUG block, like strace at :534. Root mode only.
if ! command -v ffmpeg >/dev/null && [ "$(id -u)" = 0 ]; then
    apt-get update && apt-get install -y --no-install-recommends ffmpeg || echo "ffmpeg unavailable; no recording"
fi
```

```python
# internal_bypasser.py, top of _start_ffmpeg_recording. Required, not optional.
if shutil.which("ffmpeg") is None:
    logger.warning("ffmpeg not installed; no recording for this bypass")
    return
```

The guard is the part that matters. It is what stops a missing diagnostic tool from failing a bypass. Known gaps, by reading the code and not tested:

- Non-root mode can't install anything.
- A UI-only Debug setting skips the entrypoint install, so that path produces no recording.
- The install runs after `tor.sh` and `wireguard.sh`, so it goes through whichever egress is active.
- The install adds time to startup, and needs network access.

### Can CDP replace it?

Sketch only, none of it run.

| Option | Availability | Trade-off |
|---|---|---|
| Periodic `Page.captureScreenshot` | SeleniumBase's `tab.py:1248` already calls `cdp.page.capture_screenshot` `[verified]` | Simplest, no new packages. An async task writes a JPEG to `RECORDING_DIR` every 1 or 2 seconds and the debug bundle picks them up. |
| `Page.startScreencast` | `start_screencast` exists in Selenium's bundled devtools `page.py`; I did not find it in SeleniumBase's CDP driver. `[verified]` | Delivers frames only when the page changes, needs a frame ack loop, and would need adding to the driver. More work for little gain over screenshots. |

**What it would lose, by design (`[unverified]`, not tested):**

- x11grab records the whole X display. CDP sees a single page target, so browser UI, a crashed tab or a blank display won't show. Those are often what a bypass failure looks like.
- The mp4 has real timing; screenshots are sparse.
- Whether extra CDP traffic changes how a challenge page treats the session is untested.

I would start with the guard and install-on-demand, because it keeps the same artifact maintainers already read in bug reports. CDP screenshots are a good fallback for when ffmpeg isn't available.

### What `apt-get install -s --no-install-recommends ffmpeg` adds `[verified]`

Run on `python:3.14.9-slim@sha256:35caba83...` (Debian 13.7, trixie), with the Dockerfile's snapshot source added: **205 packages**. Comparing the full Dockerfile install with and without ffmpeg splits them into two groups.

The check on this method: simulated packages plus base packages equal the published image's real package list exactly, 413 on both sides with no differences.

**93 needed only by ffmpeg:**

`ffmpeg` `libaom3` `libass9` `libavc1394-0` `libavcodec61` `libavdevice61` `libavfilter10` `libavformat61` `libavutil59` `libblas3` `libbluray2` `libbs2b0` `libcaca0` `libcdio-cdda2t64` `libcdio-paranoia2t64` `libcdio19t64` `libchromaprint1` `libcjson1` `libcodec2-1.2` `libdc1394-25` `libdecor-0-0` `libdvdnav4` `libdvdread8t64` `libfftw3-double3` `libflite1` `libgfortran5` `libgme0` `libgomp1` `libgsm1` `libhwy1t64` `libiec61883-0` `libjack-jackd2-0` `libjxl0.11` `liblapack3` `liblilv-0-0` `libmbedcrypto16` `libmysofa1` `libnorm1t64` `libnuma1` `libopenal-data` `libopenal1` `libopenmpt0t64` `libpgm-5.3-0t64` `libplacebo349` `libpocketsphinx3` `libpostproc58` `librabbitmq4` `librav1e0.7` `libraw1394-11` `librist4` `librsvg2-2` `librubberband2` `libsamplerate0` `libsdl2-2.0-0` `libserd-0-0` `libshine3` `libslang2` `libsnappy1v5` `libsodium23` `libsord-0-0` `libsoxr0` `libspeex1` `libsphinxbase3t64` `libsratom-0-0` `libsrt1.5-gnutls` `libssh-4` `libsvtav1enc2` `libswresample5` `libswscale8` `libtheoradec1` `libtheoraenc1` `libtwolame0` `libudfread0` `libunibreak6` `libusb-1.0-0` `libva-drm2` `libva-x11-2` `libva2` `libvdpau1` `libvidstab1.1` `libvorbisfile3` `libvpl2` `libvpx9` `libwebpmux3` `libx264-164` `libx265-215` `libxvidcore4` `libzimg2` `libzix-0-0` `libzmq5` `libzvbi-common` `libzvbi0t64` `ocl-icd-libopencl1`

**112 also needed by another component (Xvfb, Chromium or python3-tk), which stay either way:**

`fontconfig` `fontconfig-config` `fonts-dejavu-core` `fonts-dejavu-mono` `libasound2-data` `libasound2t64` `libasyncns0` `libatomic1` `libbrotli1` `libcairo-gobject2` `libcairo2` `libcom-err2` `libdatrie1` `libdav1d7` `libdbus-1-3` `libdeflate0` `libdrm-amdgpu1` `libdrm-common` `libdrm-intel1` `libdrm2` `libedit2` `libelf1t64` `libexpat1` `libflac14` `libfontconfig1` `libfreetype6` `libfribidi0` `libgbm1` `libgdk-pixbuf-2.0-0` `libgdk-pixbuf2.0-common` `libgl1` `libgl1-mesa-dri` `libglib2.0-0t64` `libglvnd0` `libglx-mesa0` `libglx0` `libgnutls30t64` `libgraphite2-3` `libgssapi-krb5-2` `libharfbuzz0b` `libidn2-0` `libjbig0` `libjpeg62-turbo` `libk5crypto3` `libkeyutils1` `libkrb5-3` `libkrb5support0` `liblcms2-2` `liblerc4` `libllvm19` `libmp3lame0` `libmpg123-0t64` `libogg0` `libopenjp2-7` `libopus0` `libp11-kit0` `libpango-1.0-0` `libpangocairo-1.0-0` `libpangoft2-1.0-0` `libpciaccess0` `libpixman-1-0` `libpng16-16t64` `libpulse0` `libsensors-config` `libsensors5` `libsharpyuv0` `libsndfile1` `libtasn1-6` `libthai-data` `libthai0` `libtiff6` `libunistring5` `libvorbis0a` `libvorbisenc2` `libvulkan1` `libwayland-client0` `libwayland-cursor0` `libwayland-egl1` `libwayland-server0` `libwebp7` `libx11-6` `libx11-data` `libx11-xcb1` `libxau6` `libxcb-dri3-0` `libxcb-glx0` `libxcb-present0` `libxcb-randr0` `libxcb-render0` `libxcb-shape0` `libxcb-shm0` `libxcb-sync1` `libxcb-xfixes0` `libxcb1` `libxcursor1` `libxdmcp6` `libxext6` `libxfixes3` `libxi6` `libxkbcommon0` `libxml2` `libxrandr2` `libxrender1` `libxshmfence1` `libxss1` `libxv1` `libxxf86vm1` `libz3-4` `mesa-libgallium` `shared-mime-info` `x11-common` `xkb-data`

## 2. Baseline scan of the published images `[verified]`

Command: `trivy image --image-src remote --platform linux/amd64 --scanners vuln --list-all-pkgs --format json`. Trivy warned about third-party SBOMs on both scans, and did not name them.

| | full (`latest`, v1.6.0) | lite (`latest`, v1.6.0) |
|---|---|---|
| Total findings (package + CVE pairs) | 1159 | 442 |
| Unique IDs | 443 | 184 |
| Critical | 1 (libxml2, CVE-2026-6653, no fix) | 0 |
| High | 297 | 71 |
| Medium | 467 | 167 |
| Low | 347 | 193 |
| Unknown | 47 | 11 |
| Fix available | **1** (libnss3, DSA-6599-1, severity unknown) | **0** |
| No fix: `affected` / `fix_deferred` / `will_not_fix` | 784 / 337 / 37 | 427 / 3 / 12 |
| Python package findings | 0 (119 packages) | 0 (56 packages) |

The counts multiply: one ffmpeg CVE shows up once per library, so 40 CVEs become 360 findings across nine packages.

**Layers:**

| Label | Full image DiffID | Lite image DiffID | Layer | Findings, full |
|---|---|---|---|---|
| A | `a70f6272827f` | same | Debian base | 175 |
| B | `4222d7f3ddcd` | same | python image build | 2 |
| C | `1085b03daba9` | `80f03328f0da` | Shelfmark's base `apt-get` RUN | 265 |
| D | `69475169fb82` | not present | Chromium, ffmpeg and Xvfb RUN | 717 |

**Top 20 packages, full:**

| Package | Findings | High | Layer | | Package | Findings | High | Layer |
|---|---|---|---|---|---|---|---|---|
| ffmpeg | 40 | 16 | D | | curl | 39 | 2 | C |
| libavcodec61 | 40 | 16 | D | | libcurl4t64 | 39 | 2 | C |
| libavdevice61 | 40 | 16 | D | | libcups2t64 | 27 | 2 | D |
| libavfilter10 | 40 | 16 | D | | libc-bin | 22 | 0 | A |
| libavformat61 | 40 | 16 | D | | libc-l10n | 22 | 0 | C |
| libavutil59 | 40 | 16 | D | | libc6 | 22 | 0 | A |
| libpostproc58 | 40 | 16 | D | | libmbedcrypto16 | 22 | 0 | D |
| libswresample5 | 40 | 16 | D | | locales | 22 | 0 | C |
| libswscale8 | 40 | 16 | D | | chromium | 21 | 20 | D |
| | | | | | chromium-common | 21 | 20 | D |
| | | | | | libpython3.13-minimal | 19 | 5 | C |

**Top 20 packages, lite:**

| Package | Findings | High | Layer | | Package | Findings | High | Layer |
|---|---|---|---|---|---|---|---|---|
| curl | 39 | 2 | C | | libsqlite3-0 | 15 | 2 | A |
| libcurl4t64 | 39 | 2 | C | | libelf1t64 | 7 | 0 | C |
| libc-bin | 22 | 0 | A | | libgnutls30t64 | 7 | 0 | C |
| libc-l10n | 22 | 0 | C | | libsystemd0 | 7 | 1 | A |
| libc6 | 22 | 0 | A | | libudev1 | 7 | 1 | A |
| locales | 22 | 0 | C | | bsdutils | 6 | 4 | A |
| libpython3.13-minimal | 19 | 5 | C | | libblkid1 | 6 | 4 | A |
| libpython3.13-stdlib | 19 | 5 | C | | libgssapi-krb5-2 | 6 | 0 | C |
| python3.13 | 19 | 5 | C | | libk5crypto3 | 6 | 0 | C |
| python3.13-minimal | 19 | 5 | C | | libkrb5-3 | 6 | 0 | C |

**With Chromium, Tor and ffmpeg excluded:**

| Exclusion method | Full | High | Lite |
|---|---|---|---|
| None | 1159 | 297 | 442 |
| Only packages named chromium, chromium-common, tor, ffmpeg | 1074 | 241 | 439 |
| Those plus `libav*`, `libsw*`, `libpostproc*` | 730 | 113 | 439 |
| **Every package only those three need (193 packages)** | **549** | **97** | **439** |

The last row is the meaningful one. Findings per component, counting only packages exclusive to it: ffmpeg 406 (93 packages), Chromium 133 (47 packages), Tor 3 (3 packages), all three Low and dating as far back as 2007. Tor contributes almost nothing, so it isn't a reason to change anything.

## 3. Strip experiment

**Docker build skipped.** `dpkg --purge` of the 93 ffmpeg-only packages on the extracted published image. `[replay]`

**Result, ffmpeg removed:**

| | Before | After | Change |
|---|---|---|---|
| Total | 1159 | **753** | -406 (35%) |
| High | 297 | **148** | -149 (50%) |
| Critical | 1 | 1 | none |
| Medium / Low / Unknown | 467 / 347 / 47 | 279 / 306 / 19 | |
| Packages | 413 | 320 | -93 |
| Uncompressed | 1198 MB | 1047 MB | -151 MB |
| Tar then gzip | 448 MB | 375 MB | -73 MB |

- The rescan matches the prediction exactly (same set of package and CVE pairs).
- `apt-get check` is clean, and Chromium has no missing libraries (`ldd` shows 0 `not found`).
- **Smoke test, DEBUG off: pass.** Returned `Example Domain` in 11.6 s.
- **Smoke test, DEBUG on: fail** with `FileNotFoundError`, as in section 1. That is what the guard fixes.

**Other packages: all four failed a "nothing imports them" test, so I did not remove them.** `[verified]`

| Package | What uses it | Findings it would remove |
|---|---|---|
| python3-tk | `pyautogui` imports `mouseinfo`, which imports `tkinter` at module level and calls `sys.exit` if that fails. SeleniumBase's `cdp_util.py:148` imports `pyautogui`. The image's Python 3.14 `_tkinter` links `libtk8.6` and `libtcl8.6`, which arrive through this package. | 20 (5 High) |
| zip | `genDebug.sh:206` builds the debug bundle with `zip -r` | 0 |
| iputils-ping | `wireguard.sh:710` and `:865` (the second has a curl fallback), `genDebug.sh:58` | 1 (Low) |
| unrar-free | `rarfile`, used by `shelfmark/download/archive.py`. RAR extraction needs it. | 8 (Low, from libarchive13t64) |

Two details on python3-tk:

- With the `tkinter` module moved aside, the example.com smoke test still passed. `cdp_util.py` logs "X11 display failed" and falls back before reaching the `pyautogui` import, because the image has no `xauth`. That shows only that this one path doesn't import it. Whether any challenge path does is untested, so I would not remove it on this evidence. `[replay]`
- Removing it alone would not remove Debian's Python 3.13 family, because `supervisor` needs it too. Swapping both does: see the follow-up section.

**The floor for Debian stripping:** lite alone is 442 findings on the same base, and the full image's non-browser remainder is 549. No realistic stripping gets near zero on this measure, because almost all of what remains is `affected` with no Debian fix.

## 4. Chainguard (PR #1616)

**Docker build skipped.** Dockerfile steps replayed by hand. `[replay]`

### Comparison with identical Trivy settings

| | main (published) | PR #1616 replay |
|---|---|---|
| Total, full | 1159 | **9** |
| Fix available | 1 | **9** |
| Severity | 1 C, 297 H | 1 C, 3 H, 2 M, 3 L |
| Top packages | ffmpeg family, curl, libcups2t64 | Cargo `zip` 8.6.0 (5), `rustls` 0.23.45 (4) |
| Total, lite | 442 | **0** |
| Size, uncompressed | 1198 MB | 1190 MB |
| Size, tar then gzip | 448 MB (published 463 MB) | 464 MB |
| Lite size | published 94 MB | tar then gzip 85 MB |

- **The 9 findings are all from one file:** `selenium/webdriver/common/selenium-manager.cdx.json`. #1615 already removes it on main. The OS packages on the PR show **0 findings across 224 packages**, so the rebased count is modelled at 0.
- **Size is a wash on the full image.** Wolfi's OS layers are smaller, but Chrome for Testing unpacks to 403 MB, and this PR build still carries selenium-manager. Size isn't an argument for or against.

### Specific questions

| Question | Answer | Tag |
|---|---|---|
| Does Trivy list Chrome for Testing? | **No.** No package name containing "chrom" in `scan/pr-full.json`. | `[replay]` |
| Does Trivy list the source-built Tor? | **No.** No `tor` package, though `/usr/bin/tor` is present. | `[replay]` |
| Anonymous pull of `cgr.dev/chainguard/wolfi-base`? | **Yes**, tested at registry level, with an anonymous token, manifest and all 11 layers, without `docker pull`. Pinned digest `sha256:88a20e2d...` is still `latest`, created 2026-10-28. | `[verified]` |
| `apk search tor` in wolfi-base? | **Not found.** `apk search -x tor` is empty, and the index has no `tor` on either `apk.cgr.dev/chainguard` or `packages.wolfi.dev/os`. | `[verified]`, chroot, not a container |
| `apk search chromium`? | **`chromium-149.0.7827.53-r0`**, last built 2026-06-05, 27 versions in the index. This supports the PR's claim that it stopped updating; 149 is seven majors behind. | `[verified]`, chroot |
| `.asc` for the pinned Tor tarball? | **Not under that name:** `tor-0.4.9.15.tar.gz.asc` is 404. Tor signs the checksum file instead: `tor-0.4.9.15.tar.gz.sha256sum.asc` exists with two signatures. One verifies as a good signature from David Goulet, `B74417ED...8D36`. I could not check the second (`514102...9179`) because I had no public key for it. The hash in the file equals the PR's `TOR_SHA256`. | `[verified]` |
| Smoke test on the PR? | **Pass:** Chrome for Testing 156.0.8078.47, Python 3.14.10, `Example Domain` in 12.2 s. Also passes with DEBUG on, with a real recording. | `[replay]` |

The PR could verify that signature in its build. It checks only a hash it stores itself, taken from the same site as the download.

### Problems in the PR

| # | Finding | Evidence | Severity |
|---|---|---|---|
| 1 | **`wg-quick` is missing.** `apk info -L wireguard-tools` lists only `usr/bin/wg` as a binary, and no package provides `cmd:wg-quick`. `wireguard.sh:221`, `:821` and `:824` call it. Debian's package provides `/usr/bin/wg-quick`. Running it gives `command not found`, exit 127. | `[replay]` | **Blocker** |
| 2 | **Browser older than main and invisible to scanners.** PR has .47, main .73, Chrome for Testing stable .80. All 21 Chromium CVEs on main (20 High) are described on Debian's tracker as fixed in `156.0.8078.79`. | `[verified]` | **Blocker** until bumped |
| 3 | **Conflicts with main and predates #1615**, plus uv 0.13.5 vs main's 0.13.6. | `[verified]` | Must fix |
| 4 | **No CI has built it.** The only checks on the PR are the two Jules review jobs. CI's `docker-build-check` covers only `shelfmark-lite` on amd64 in any case, so nothing in PR CI builds the full image. | `[verified]` | Must check |
| 5 | **`apk add` floats.** Only `wolfi-base` is pinned, so rebuilding the same commit can produce different packages. Example: Tor today links `libssl.so.4` from `openssl-4.0`, while the PR's stated requirement is `so:libssl.so.3`. It works because other packages (`libevent`, `python-3.14-base`, `libcurl-openssl4`) pull in OpenSSL 4. | `[replay]` | Know the trade-off |
| 6 | `mount` is missing, used only by `entrypoint.sh:514` in the debug block, which runs with `set +e`. | `[replay]` | Cosmetic |
| 7 | `archive.py:288` still says "install unrar package" when the tool is now `7z`. | `[verified]` | Cosmetic |

**Checked and fine:**

- Tor works in the `base` stage. I suspected the OpenSSL mismatch would break the `tor --version` at Dockerfile line 154, and it doesn't. `[replay]`
- The arm64 Chrome hash matches the PR's `CHROME_SHA256_ARM64` when I download the zip. Google publishes `linux-arm64` for this version. `[verified]`
- The amd64 hash matches too. `[replay]`
- Chrome finds all its libraries, and the Xlib fix step passes. `[replay]`

### RAR: a point in the PR's favour `[replay]`

Using the 51 samples in the rarfile 4.5 sdist, `RarFile` open, `testrar()` and read:

| | unrar-free (main) | 7z (PR) |
|---|---|---|
| All samples OK, including password-protected ones that fail on both | 35 of 51 | 40 of 51 |
| RAR5, no password | 18 of 20 | 18 of 20 |
| RAR3, no password | 8 of 12 | 9 of 12 |
| Regressions | | none |

- 7z reads five samples unrar-free can't: `rar15-comment-lock`, `rar15-comment`, `rar2-unix-owner`, `rar3-solid`, `unicode`.
- The PR's Dockerfile comment says 7z "also reads RAR5, unlike unrar-free". These samples don't support that: both read the same number of RAR5 files.
- The real gain is in older formats. **This is not a simple swap on Debian:** see the follow-up section.

## 5. Maintenance surface `[verified]`

| Pin | main | PR #1616 | Kept current by |
|---|---|---|---|
| Node frontend base | `node:24-alpine@sha256` | `wolfi-base` plus unpinned `nodejs-24` | main: Dependabot. PR: floats within the 24 line. |
| uv | tag and digest | tag and digest (older) | Dependabot `docker` |
| Python | `python:3.14.9-slim@sha256` | unpinned `python-3.14` apk (3.14.10 today) | main: Dependabot, patch only. PR: floats; a minor bump is manual. |
| Runtime base | the Python image above | `wolfi-base:latest@sha256`, in 4 `FROM` lines | Dependabot `docker`; handling of `latest@digest` not tested |
| Chromium | `CHROMIUM_VERSION`, `CHROMIUM_SNAPSHOT` | `CHROME_VERSION`, `CHROME_SHA256_AMD64`, `CHROME_SHA256_ARM64` | **Manual on both** |
| Tor | apt, floats within trixie | `TOR_VERSION`, `TOR_SHA256` | main: rebuild. **PR: manual.** |
| supervisor | apt 4.2.5 | `supervisor==4.3.0` and hash in a `printf` | main: rebuild. **PR: manual.** |
| python-xlib | `==0.33` | `==0.33` | **Manual on both** |
| OS packages | apt, float | apk, float | Rebuild only |
| Python and npm deps, Actions | `uv.lock`, `package-lock.json`, workflow SHAs | same | Dependabot |

**Manual values to bump:** main has 3 (2 Chromium, 1 xlib). The PR has 8 (3 Chrome, 2 Tor, 2 supervisor, 1 xlib).

**How often this bites:** Chromium pin bumps on main were #1105 (Jul 6), #1477 (Oct 20), #1601 (Oct 27) and #1614 (Oct 30), so three in the last 11 days. The PR needs two downloads and two hashes per bump, since Google publishes no checksums. Upstream, though, Chrome for Testing is ahead of Debian today.

**Dependabot:** the PR doesn't edit `.github/dependabot.yml` (its diff is `Dockerfile` and `entrypoint.sh` only). The `node` and `python` rules there would match nothing after this change.

**Scanners in CI:** CodeQL only (`python`, `javascript-typescript`), and it scans source. **No container scanner exists in any workflow**, so nothing tracks these numbers today.

## 6. Runtime posture of the full image `[verified]`

Read from code and image config, not observed in a running container with real ids.

| Item | Finding |
|---|---|
| Container start | Image config has no `User`, so it starts as **root** by default |
| App and Chromium user | `entrypoint.sh` drops via `gosu` to `PUID`:`PGID`, **default 1000:1000** (`:164-190`, final `exec_as_target_user`). Chromium is launched by the app, so it runs as that user. `PUID=0` keeps root. Starting directly as non-root is supported. |
| `--no-sandbox` in production | **Yes, always.** `internal_bypasser.py:1388` passes `sandbox=False`, which SeleniumBase turns into `--no-sandbox` (`cdp_driver/config.py:352`), and it also adds `--disable-setuid-sandbox`. This is not limited to debug. |
| Other Chrome flags | `--ignore-certificate-errors`, `--ignore-ssl-errors`, `--allow-running-insecure-content`, `--enable-unsafe-swiftshader` (`:794-802`), `--test-type` from SeleniumBase |
| Tor | Must start as root; `entrypoint.sh:91-98` refuses otherwise. `tor.sh` runs before the privilege drop, and sets iptables NAT rules. Tor itself runs as `debian-tor`. Needs `NET_ADMIN`, `NET_RAW` (`compose/docker-compose.tor.yml`, `readme.md:192`). |
| WireGuard | Must start as root (`entrypoint.sh:100-105`). Needs `NET_ADMIN`, `NET_RAW`, plus sysctl `net.ipv4.conf.all.src_valid_mark=1`, and IPv6 disabled unless `ip6tables` works (`compose/docker-compose.wireguard.yml`). |
| Default deployment | Needs no added capabilities for either; only those two modes do. `SYS_PTRACE` appears only in the dev compose. |

**Why this matters for the decision:** Debian's tracker describes the first CVE I sampled as code execution "inside the sandbox" and the next as "outside the sandbox". With `--no-sandbox` that boundary isn't there, and the browser loads third-party pages by design. Browser currency is therefore worth more here than most of the 1159 findings, and it is the one thing the PR's scan can't see. This applies to both bases: main at .73 is also behind the fix.

## Follow-up: what the PR swapped, and what works on Debian

Added the same day, before the real builds, and superseded by "Real builds" where they differ. Tested on a rootfs of the published image; all `[replay]`.

### Every tool the PR swaps `[verified]`

| Component | main (Debian) | PR (Wolfi) | On Debian? |
|---|---|---|---|
| OS, libc | Debian 13.7, glibc 2.41 | Wolfi, glibc 2.44 | that is the swap itself |
| Package manager | apt | apk; floats, no snapshot | n/a |
| Shell utilities | GNU coreutils | BusyBox, plus GNU grep, `procps`, `shadow` | n/a |
| Python | python.org build in `/usr/local`, 3.14.9 | Wolfi `python-3.14`, 3.14.10 | n/a |
| Chromium | Debian 156.0.8078.73 | Chrome for Testing .47 | **works**, tested with .80 |
| Tor | Debian 0.4.9.15 | source build 0.4.9.15 | no reason to: same version, 3 Low findings |
| supervisor | Debian 4.2.5 | PyPI 4.3.0 in a venv | **works** |
| Tk | `python3-tk` (pulls Debian Python 3.13) | `python-3.14-tk`, Tk 9.1 | **works** with `libtk8.6` and `libtcl8.6` directly |
| RAR | `unrar-free` | `7zip` 26.05 with RAR | **needs `non-free`**, see below |
| ffmpeg | 7.1.5 | 9.0.2 | removed instead |
| WireGuard | `wireguard-tools` with `wg-quick` | no `wg-quick` | stays |
| Frontend build | `node:24-alpine` | Wolfi `nodejs-24` | no gain |
| Locale | `locales` plus `locale-gen` | `glibc-locale-en` | no gain |

### RAR options

Same 51 samples, same test. RAR5 and RAR3 columns exclude password-protected samples.

| Tool | Source | OK of 51 | RAR5 | RAR3 | Regressions vs unrar-free | Does Trivy see it? |
|---|---|---|---|---|---|---|
| `unrar-free` (today) | Debian `main` | 35 | 18/20 | 8/12 | n/a | yes; 8 Low/Medium via libarchive |
| `7zip` alone | Debian `main` | 26 | 10/20 | 8/12 | **9 samples** | yes |
| `bsdtar` (libarchive-tools) | Debian `main` | 26 | 10/20 | 8/12 | **9 samples** | yes |
| **`unrar`** | Debian **`non-free`** | **40** | 18/20 | 9/12 | none | **yes; 1 finding, severity unknown** |
| `7zip` + `7zip-rar` | Debian **`non-free`** | 40 | 18/20 | 9/12 | none | yes; 8+ findings, 2 High |
| Upstream `7zz` | 7-zip.org binary (tested 23.01) | 40 | not separated | not separated | none | **no**, `Results []` |

- Debian's `7zip` has its RAR codec split out into `7zip-rar`, which is why it fails RAR5 samples.
- **Wolfi's 7zip can't be reused to get the scan.** Trivy sees it only through Wolfi's package database, so outside Wolfi it is the same invisible binary as upstream.
- **A hand-written CycloneDX file** next to `7zz` produced no results in a quick test (both `pkg:generic` and `pkg:deb` PURLs). I stopped there: making it match would mean claiming an upstream binary is a Debian package, which is a cosmetic result.
- **Best option if RAR matters:** Debian's `unrar`. No code change, since `rarfile` already prefers `unrar`. It removes `unrar-free` and libarchive, and Trivy still scans it. The catch is that it needs the `non-free` component, and its copyright file says "This software is non-free" and "License: freeware". That is calibrain's call. It also doesn't belong in the ffmpeg PR.

### How far Debian gets, cumulatively

| Step | Total | High | Critical | Packages | Tar + gzip | Smoke |
|---|---|---|---|---|---|---|
| Published | 1159 | 297 | 1 | 413 | 448 MB | pass |
| Remove ffmpeg | 753 | 148 | 1 | 320 | 375 MB | pass |
| PyPI supervisor, direct libtk | 656 | 122 | 1 | 299 | not measured | pass |
| `unrar` from non-free | 649 | 122 | 1 | 298 | not measured | RAR test only |
| Chrome for Testing .80, with its `deb.deps` | 629 | 84 | 1 | 278 | 390 MB | pass |
| Drop GTK and the second libcurl | **558** | **79** | 1 | 238 | **378 MB** | pass |

- Findings with a fix available in the final row: 0. The critical is libxml2 CVE-2026-6653, no fix.
- The Chrome step removes the 21 Chromium findings for real, since .80 is past the .79 fix. It also makes the browser invisible to Trivy, as on the PR, so a freshness check is needed there too.
- Counts for the last four rows are corrected by removing a `uv` binary I had left in the test rootfs's `/tmp`, which added 4 `rustls` findings. The final two rows were rescanned without it; the two rows above were reduced by those 4. A recheck of the published image on the same DB still gave 1159.
- The namespace left `dbus-user-session` and `dconf` unconfigured during the CfT install. Those were removed in the last step, and `dpkg --audit` is clean there. A real build should confirm it.

### The ffmpeg decision and PR draft

**Call: remove ffmpeg, keep x11grab recording through install-on-demand plus a guard. Don't move to CDP.** CDP would be more code and record less, since x11grab sees the whole display. Recordings from it are what the debug history in #1276 and #1364 relies on.

Draft patch at this stage: 4 files, +46/-2. It later became the ffmpeg PR, which also adds a docs line.

| Test | Result |
|---|---|
| Unit tests: `tests/bypass/test_ffmpeg_recording_diagnostics.py`, 1 new | 6 pass |
| All of `tests/bypass` | 149 pass |
| `ruff check`, `ruff format --check`, `shellcheck -S warning entrypoint.sh` | clean |
| `basedpyright` on `internal_bypasser.py` | 3 errors, identical with and without the patch |
| Debug on, no ffmpeg: smoke | pass, logs `ffmpeg is not installed; no recording for this bypass.` |
| Real `entrypoint.sh`, `PUID=0`, Debug off | `/api/health` 200 after about 6 s, ffmpeg not installed |
| Real `entrypoint.sh`, `PUID=0`, Debug **only in config file** | installs ffmpeg, 200 after about 18 s |
| Smoke after that install | pass, 98,343-byte mp4 |

The entrypoint asks the app for the effective Debug value, which closes the UI gap: the setting is `requires_restart`, so a restart reaches this check. In non-root mode it can't install, so it logs that and the guard takes over.

Not tested at this stage: non-root mode, and a failed `apt-get`. Both pass in "Real builds". Note that the test rootfs needed `APT::Sandbox::User "root"` because of the namespace, which a real container doesn't.

## Commands run

These ran in a scratch directory, with small helper scripts that aren't in this repo.

```bash
# Setup
which docker trivy gh; trivy --version; unshare -Ur id
git clone https://github.com/calibrain/shelfmark.git repo
git -C repo fetch origin pull/1616/head:pr1616

# Scans (published)
trivy image --image-src remote --platform linux/amd64 --scanners vuln --list-all-pkgs --format json \
  --output scan/full.json --timeout 40m ghcr.io/calibrain/shelfmark:latest
trivy image --image-src remote --platform linux/amd64 --scanners vuln --list-all-pkgs --format json \
  --output scan/lite.json --timeout 40m ghcr.io/calibrain/shelfmark-lite:latest

# Scans (rootfs; control, stripped, PR, PR lite)
trivy rootfs --skip-db-update --scanners vuln --list-all-pkgs --format json --output <out>.json \
  --timeout 30m --skip-dirs proc --skip-dirs sys --skip-dirs dev <rootfs>

# Rootfs extraction, whiteouts applied, no owners or devices
python3 extract.py ghcr.io calibrain/shelfmark latest d/full
python3 extract.py docker.io library/python sha256:35caba83af2fe6da9a5d922f9b0156f21d1246a48278c58a08bd253303ba42e8 d/pybase
python3 extract.py cgr.dev chainguard/wolfi-base sha256:88a20e2d017bd20cdc0cb3910de603e7bea9512a6c351a8dd3c9df212ab03d73 w/base

# Namespace wrapper (nsrun.sh <rootfs> <cmd...>)
unshare -Ur --mount --pid --fork --propagation private --kill-child \
  bash -c 'mount --rbind /proc $R/proc; mount --rbind /dev $R/dev; mount --rbind /sys $R/sys; chroot $R env -i ...'

# ffmpeg closure (in d/pybase, for each package set)
apt-get install -s --no-install-recommends -o Acquire::Check-Valid-Until=false <packages>

# Strip
dpkg --purge $(cat apt/ffmpeg-exclusive.txt)

# Smoke test (cd /app; DOCKERMODE=true PYTHONPATH=/app PATH=/app/.venv/bin:$PATH)
python -c "from shelfmark.bypass import internal_bypasser as ib; html = ib.get('https://example.com'); ..."

# Wolfi
apk update; apk search -x tor; apk search -v 'chromium*'; apk info -L wireguard-tools; apk search -x cmd:wg-quick
curl -fsSL https://apk.cgr.dev/chainguard/x86_64/APKINDEX.tar.gz | tar -xzO APKINDEX   # also packages.wolfi.dev/os

# Tor signature
curl -o /dev/null -w '%{http_code}' https://dist.torproject.org/tor-0.4.9.15.tar.gz.asc
gpg --verify tor-0.4.9.15.tar.gz.sha256sum.asc tor-0.4.9.15.tar.gz.sha256sum

# Chrome
curl -s https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions.json
curl -fsSL https://storage.googleapis.com/chrome-for-testing-public/156.0.8078.47/linux-arm64/chrome-linux-arm64.zip | sha256sum
curl https://security-tracker.debian.org/tracker/<CVE>   # for each of the 21 Chromium CVEs

# Repo and API
grep -rnIiE 'ffmpeg|x11grab|screen.?record|screencast' . --exclude-dir=node_modules --exclude=uv.lock --exclude=package-lock.json
gh pr checks 1616 -R calibrain/shelfmark
```

The PR replay ran the package lists from `pr1616:Dockerfile` lines 87, 110-140 and 216-229, then the Tor build (lines 48-57), the Chrome download (71-82), supervisor (159-168), `uv sync`, the Xlib fix and pip removal (234-259), all as written.

### Runs I discarded

- **First ffmpeg purge:** `apt-get purge` failed its privilege drop in the namespace and removed nothing. Its scan and smoke results were just the baseline again.
- **First post-purge "non-debug" smoke:** invalid because my earlier DEBUG run had persisted the setting.
- **Replay fidelity:** the namespace has a single uid, so ownership changes were skipped or failed, including 3 apk "updating directory permissions" errors. The frontend `dist` wasn't built for the replay.

## What I could not verify (at the time)

Written before the real builds. Items 1 to 3, 5, 6 and 8 are now answered in "Real builds". Item 4 remains open: no variant solved the challenge.

1. **Any real `docker build`, of either branch.** The PR's Dockerfile has not been built here, and its real layer sizes and compressed image size are unknown.
2. **`entrypoint.sh` end to end on the PR**, including the `gosu` drop and BusyBox `timeout`. The namespace can't switch uid; the smoke test calls Python directly.
3. **Tor and WireGuard at runtime on either base.** No tunnel, iptables rules or capabilities were exercised. `wg-quick` being absent is verified; whether an upstream copy works on Wolfi is not.
4. **Bypassing a real challenge.** example.com serves none, so the smoke test proves only that the browser starts and loads a page. Whether Chrome for Testing is treated differently from Debian's Chromium on Cloudflare is unknown, and the bypass is the point of the full image.
5. **Chromium as the unprivileged user**, because the smoke tests ran as namespace root.
6. **How much real exposure Wolfi removes.** Trivy can't report unfixed CVEs on Wolfi, so I have no like-for-like number. A scanner with the same data source wouldn't settle it either. `[unverified]`
7. **CVEs fixed between Chrome .47 and .73.** Debian's chromium doc directory has no changelog in the image. The PR's real Chrome exposure is at least the 21 listed, and possibly more.
8. **arm64 at all**, beyond the download hash. All scans, builds and smoke tests were amd64.
9. **Dependabot's handling of `wolfi-base:latest@sha256`.** Also Chainguard's free-tier terms, rate limits, and how long old digests and packages stay available.
10. **Which third-party SBOM Trivy warned about** on the published scans. It didn't affect the control comparison, but the log doesn't name it.
11. **Screencast and screenshot alternatives to ffmpeg.** Sketches only.
