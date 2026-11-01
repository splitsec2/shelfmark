"""Read every rarfile sample with whichever tool rarfile picks in this image."""
import glob
import json
import sys

import rarfile

tool = rarfile.tool_setup(force=True).get_cmdline("open_cmd", None)[0]
ok, fail = [], []
for path in sorted(glob.glob(sys.argv[1] + "/*.rar")):
    name = path.rsplit("/", 1)[-1]
    try:
        with rarfile.RarFile(path) as rf:
            names = rf.namelist()
            rf.testrar()
            if not rf.getinfo(names[0]).is_dir():
                rf.read(names[0])
        ok.append(name)
    except Exception:  # noqa: BLE001
        fail.append(name)
print(json.dumps({"tool": tool, "ok": len(ok), "fail": len(fail), "failed": fail}))
