# Base image follow-ups

Follow-ups from the [base image report](https://github.com/splitsec2/shelfmark/blob/8509a385ddb6ef0bc5d5c03bc27b985daa219297/docs/research/2026-11-01-base-image-report.md), filed on calibrain/shelfmark on 2026-11-01 as written below. Numbers are from the real builds in that report, amd64 and arm64.

## a. Issue: move supervisor to `uv.lock` and use libtk/libtcl directly

**Filed:** [#1633](https://github.com/calibrain/shelfmark/issues/1633)
**Type:** issue
**Labels:** enhancement, docker, dependencies
**Assignee:** splitsec2

**Title:** Move supervisor into uv.lock and use libtk/libtcl directly

**Body:**

Debian's `supervisor` and `python3-tk` both pull in Debian's Python 3.13, which the image doesn't run. Swapping them removes that package family and puts supervisor where Dependabot can see it. This builds on #1631, so the numbers below compare against that branch.

The change:

- Remove `supervisor` from the apt install. Add `supervisor==4.3.0` to `pyproject.toml`, and symlink `supervisord` and `supervisorctl` to the Debian paths `tor.sh` expects, plus `mkdir -p /etc/supervisor`.
- Replace `python3-tk` with `libtk8.6 libtcl8.6`. Those are the libraries the image's own `_tkinter` links against.

| | #1631 | With this change | Change |
|---|---|---|---|
| Trivy, full: all | 752 | 655 | -97 |
| Trivy, full: High | 148 | 122 | -26 |
| Trivy, full: Critical | 1 | 1 | none |
| Trivy, lite: all | 442 | 359 | -83 |
| Grype, full: all | 738 | 641 | -97 |
| Debian Python 3.13 packages | 17 | 0 | -17 |
| Gzipped full, amd64 | 376 MB | 362 MB | -14 MB |
| Gzipped lite, amd64 | 93 MB | 80 MB | -13 MB |
| Manual pins | 3 | 3 | none |

For reference, OSV on the same build gives 339 distinct IDs against 453 on main, counting the ffmpeg removal as well.

Tested on both arches as uid 1000: Tor through supervisor, a real WireGuard tunnel and kill switch, `import tkinter, pyautogui, mouseinfo`, a real `tkinter.Tk()` window, Debug recording. Not tested: whether Dependabot picks up the new `uv.lock` entry, because it only acts on its own schedule on the default branch.

## b. Issue: optional seccomp hardening profile for the browser

**Filed:** [#1634](https://github.com/calibrain/shelfmark/issues/1634)
**Type:** issue
**Labels:** enhancement, documentation, docker
**Assignee:** splitsec2

**Title:** Optional seccomp profile so the browser can run with its sandbox on

**Body:**

Chrome runs with `--no-sandbox` on every image because `internal_bypasser.py` passes `sandbox=False`. On default Docker it has no other option: without the flag Chrome exits with "No usable sandbox!". With the flag, renderers share the browser's namespaces.

A narrow seccomp profile fixes this with no added capabilities. It's Docker's default profile with `clone`, `unshare` and `setns` allowed.

| Docker setting, uid 1000, no `--no-sandbox` | Chrome starts? | Renderer | Bypass code on example.com |
|---|---|---|---|
| Default | no | | |
| Narrow profile, no capabilities | yes | Own PID and network namespace, 2 seccomp filters against the browser's 1 | pass |

The Cloudflare demo page behaved the same with the sandbox on: not solved, the same as without it.

This needs a small code change as well as docs. My tests flipped `sandbox=False` with `sed` in the image, so a real version needs a setting that defaults to off. It has to stay off when the app runs as root (`PUID=0`), because Chrome refuses to sandbox as root.

Proposed:

- A setting to turn the sandbox on, default off, documented as needing the profile.
- The profile checked in under `compose/`.
- A doc page covering what it does and what it trades away, plus a compose example:

```yaml
services:
  shelfmark:
    # Plus the new setting, once it has a name
    security_opt:
      - seccomp=./shelfmark-browser-seccomp.json
```

Things the doc page has to say:

- The profile applies to the whole container, so the app can make these calls too. That's more kernel surface in exchange for renderer isolation.
- With the setting on and no profile, Chrome won't start. It would be better to detect that and log a clear message.
- The checked-in copy will drift from Docker's default profile.

Not tested: Podman, Kubernetes, or hosts that restrict unprivileged user namespaces.

## c. Issue: scheduled check for a newer Debian chromium

**Filed:** [#1635](https://github.com/calibrain/shelfmark/issues/1635)
**Type:** issue
**Labels:** enhancement, github_actions, docker, dependencies
**Assignee:** splitsec2

**Title:** Scheduled check that opens an issue when Debian publishes a newer chromium

**Body:**

`CHROMIUM_VERSION` and `CHROMIUM_SNAPSHOT` are set by hand and nothing notices when they go stale. Dependabot doesn't track them. The last few bumps (#1477, #1601, #1614) happened because someone went and looked.

Proposed, as a workflow on a daily or weekly schedule:

1. Read the `chromium` version from `trixie-security`'s `Packages.xz` for amd64 and arm64, and compare it with `CHROMIUM_VERSION` in the `Dockerfile`.
2. If it's newer on both, look on snapshot.debian.org for the first timestamp that has it for both arches, since that's the value the bump needs.
3. Open an issue with the version and the snapshot, unless one is already open for that version.

It should only open an issue and not a bump PR. #1105 shows a new Debian Chromium can break the CDP bypasser, so a person has to test each bump. Actions pinned by SHA, with `issues: write` as the only permission.

Not built or tested yet. Renovate's `deb` datasource is a candidate implementation, pending a test against security.debian.org.

What each bump still has to check is the click path. .73 clears DDoS-Guard on Anna's Archive from a residential network, but those challenges all cleared on the auto-wait step, so `_bypass_method_cdp_click` (and `_bypass_method_cdp_gui_click`, which runs before it) wasn't exercised. So the open Chromium regression question is that path, and no longer solving in general.

## d. Discussion: support policy for native Tor and WireGuard vs gluetun-style sidecars

**Filed:** [discussion #1636](https://github.com/calibrain/shelfmark/discussions/1636)
**Type:** discussion, not an issue
**Category:** Ideas
**Labels:** none

**Title:** Should native Tor and WireGuard stay in the image, or should we point people at a sidecar?

**Body:**

This came up while comparing base images on #1616. Native Tor and WireGuard add more to the image than their share of the features suggests, so I'd like to ask if we want to keep supporting them this way.

What they cost today:

- The image carries `tor`, `wireguard-tools`, `iptables` and `supervisor`.
- Both modes have to start as root and need `NET_ADMIN` and `NET_RAW`. WireGuard also needs the `src_valid_mark` sysctl, and IPv6 disabled unless `ip6tables` works. So non-root mode can't use either of them.
- `tor.sh` and `wireguard.sh` are real code to maintain, along with their tests.
- On Wolfi, 6 of the 10 hand-kept pins (Tor, `wg-quick`, supervisor) exist only for these two modes. On Debian they're cheap: Tor is 3 Low findings.

What a sidecar would change: a container like gluetun holds the tunnel and Shelfmark joins its network with `network_mode: service:gluetun`. The kill switch and provider support become that project's job, and the Shelfmark container could run without those capabilities.

What it wouldn't solve, as far as I can tell:

- It's more setup for people who just want one container. Unraid and NAS users may feel that the most, which is an assumption on my part.
- Tor has no equivalent as widely used as gluetun is for VPNs. I haven't looked at what's available.
- Existing users would need a migration path, and any deprecation would need a long notice.

I haven't tested a sidecar with Shelfmark, I haven't measured how much of the image comes off without these modes, and I have no idea how many people use them. Knowing that last one matters most, so it would be good to hear from anyone running either mode.

Options I can see: keep both as they are, keep them and document a sidecar as the alternative, or deprecate them over a few releases. Ultimately a call for @calibrain.
