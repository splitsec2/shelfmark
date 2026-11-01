"""Start Chrome directly and report what isolation its processes actually got."""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

flags = sys.argv[1:]
udd = tempfile.mkdtemp(prefix="sbx")
err = tempfile.TemporaryFile()
cmd = ["chromium", "--headless=new", "--disable-gpu", f"--user-data-dir={udd}", "--remote-debugging-port=0", *flags, "https://example.com"]
proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=err)
time.sleep(10)
rows = []
for path in glob.glob("/proc/[0-9]*"):
    try:
        line = open(f"{path}/cmdline", "rb").read().replace(b"\0", b" ").decode(errors="replace")
        if udd not in line:
            continue
        kind = (re.findall(r"--type=([a-z-]+)", line) or ["browser"])[0]
        status = open(f"{path}/status").read()
        rows.append({
            "type": kind,
            "uid": re.search(r"^Uid:\s+(\d+)", status, re.M).group(1),
            "seccomp": re.search(r"^Seccomp:\s+(\d+)", status, re.M).group(1),
            "filters": (re.findall(r"^Seccomp_filters:\s+(\d+)", status, re.M) or ["?"])[0],
            "pidns": os.readlink(f"{path}/ns/pid"),
            "netns": os.readlink(f"{path}/ns/net"),
        })
    except (OSError, AttributeError):
        continue
alive = proc.poll() is None
exit_code = proc.poll()
if alive:
    proc.kill()
    proc.wait()
err.seek(0)
stderr = err.read().decode(errors="replace")
shutil.rmtree(udd, ignore_errors=True)
browser = [r for r in rows if r["type"] == "browser"]
rend = [r for r in rows if r["type"] == "renderer"]
print(json.dumps({
    "flags": flags,
    "alive": alive,
    "exit": exit_code,
    "renderers": len(rend),
    "renderer_pidns_isolated": bool(browser and rend and all(r["pidns"] != browser[0]["pidns"] for r in rend)),
    "renderer_netns_isolated": bool(browser and rend and all(r["netns"] != browser[0]["netns"] for r in rend)),
    "browser_filters": browser[0]["filters"] if browser else None,
    "renderer_filters": rend[0]["filters"] if rend else None,
    "uid": browser[0]["uid"] if browser else None,
    "fatal": [l[:220] for l in stderr.splitlines() if re.search(r"FATAL|No usable sandbox|sandbox", l, re.I)][:4],
}))
