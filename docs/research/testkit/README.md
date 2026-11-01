Test harness for the Shelfmark base image comparison (calibrain/shelfmark#1616). It builds on the runner and pushes no images. It ran from a temporary orphan branch on my fork, which has since been kept here so the runs can be repeated.

## Running it again

The workflow doesn't run from this folder. To run it, put it on an orphan branch laid out like this and push:

```
.github/workflows/base-image-matrix.yml
testkit/          (everything else in this folder)
```

The branch has to be named `test/base-image-matrix`, or change the `on: push` line in the workflow. It needs no secrets, and it uploads only logs, JSON and TSV as artifacts. `run.sh` is one script for every case. Results land in `results/results.tsv`.

## What's in here

- `run.sh`: every case, for one variant and architecture.
- `base-image-matrix.yml`: the workflow, as last run. The matrix is set to `[ffmpeg-optional]`. Runs 1 and 2 also used `main`, `d1`, `d2` and `wolfi`, and #1616 as written.
- `ffmpeg-optional.patch`: #1631 with the background install.
- `d1.patch`, `d2.patch`, `wolfi.patch`: as they ran in run 2. D1 and D2 carry the first ffmpeg patch, which installed before startup, so regenerate them before relying on that part. Wolfi keeps ffmpeg in the image.
- `smoke.py`, `sbx.py`, `rar.py`: helpers `run.sh` copies into the container.

## A known wrong check

`blackhole_mirror.result` reports FAIL in run 4, on both architectures, because it expects the 120 s timeout message. With a proxy that never answers, apt gave up on its own first and logged `Could not install ffmpeg (exit 100)`. The app was healthy, the bypass passed and apt and dpkg were left clean, so the behaviour is fine and the check was too narrow. I left the script as it ran. The timeout itself fires in `blackhole_dns`.
