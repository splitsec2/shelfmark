"""Same check as calibrain/shelfmark#1615: internal_bypasser.get() against a URL."""
import os
import re
import sys
import time

url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
want = sys.argv[2] if len(sys.argv) > 2 else "Example Domain"
started = time.time()
from shelfmark.bypass import internal_bypasser as ib  # noqa: E402

try:
    html = ib.get(url)
except BaseException as exc:  # noqa: BLE001
    print(f"RESULT exception {type(exc).__name__}: {str(exc)[:300]}", flush=True)
    sys.exit(2)
title = re.findall(r"<title>(.*?)</title>", html or "", re.I | re.S)[:1]
print(f"RESULT uid={os.getuid()} len={len(html or '')} title={title} elapsed={time.time() - started:.1f}", flush=True)
sys.exit(0 if html and want in html else 1)
