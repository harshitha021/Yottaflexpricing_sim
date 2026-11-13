#!/usr/bin/env python
"""Regenerate twice with the same seed and compare row counts + SHA-256 of every output file.
Usage: python reproduce.py <out_report.json> [generator args...]   e.g. --skus 5000 --days 180 --promos 2000 --seed 20261022
"""
import hashlib, json, os, shutil, subprocess, sys, tempfile
here = os.path.dirname(os.path.abspath(__file__))
report, args = sys.argv[1], sys.argv[2:]
runs = []
tmp = tempfile.mkdtemp(prefix="repro_")
for i in (1, 2):
    out = os.path.join(tmp, f"run{i}")
    subprocess.run([sys.executable, os.path.join(here, "generate.py"), *args, "--out", out], check=True, stdout=subprocess.DEVNULL)
    files = {}
    for root, _, fs in os.walk(out):
        for fn in sorted(fs):
            p = os.path.join(root, fn)
            files[os.path.relpath(p, out).replace("\\", "/")] = (hashlib.sha256(open(p, "rb").read()).hexdigest(), sum(1 for _ in open(p, "rb")) - 1 if fn.endswith(".csv") else None)
    runs.append(files)
cmp = {k: dict(run1_sha256=runs[0][k][0], run2_sha256=runs[1][k][0], rows_run1=runs[0][k][1], rows_run2=runs[1][k][1],
               identical=runs[0][k] == runs[1].get(k)) for k in runs[0]}
rep = dict(args=args, files_compared=len(cmp), all_identical=all(v["identical"] for v in cmp.values()) and runs[0].keys() == runs[1].keys(), files=cmp)
json.dump(rep, open(report, "w"), indent=1)
shutil.rmtree(tmp, ignore_errors=True)
print("files:", len(cmp), "all identical:", rep["all_identical"])
