import csv
import glob
import sys

import numpy as np

OVER_MS = 100

STAGES = [
    ("capture_ms", "capture"),
    ("encode_ms", "encode"),
    ("network_ms", "network"),
    ("inference_ms", "inference"),
    ("servo_ms", "servo write"),
    ("display_ms", "display"),
    ("total_ms", "END-TO-END"),
]

# Use the file given on the command line, or the newest log
if len(sys.argv) > 1:
    path = sys.argv[1]
else:
    files = sorted(glob.glob("logs/run_*.csv"))
    if not files:
        print("No logs found in logs/")
        raise SystemExit
    path = files[-1]

with open(path, newline="") as f:
    rows = list(csv.DictReader(f))

if not rows:
    print(f"{path} has no rows")
    raise SystemExit


def values(column):
    return np.array([float(r[column]) for r in rows if r[column] != ""])


first = float(rows[0]["timestamp"])
last = float(rows[-1]["timestamp"]) + float(rows[-1]["total_ms"]) / 1000
duration = last - first
fps = len(rows) / duration

print(f"Log:      {path}")
print(f"Cycles:   {len(rows)}")
print(f"Duration: {duration:.1f} s")
print(f"FPS:      {fps:.1f}")
print()
print(f"{'Stage':<14}{'n':>7}{'p50 ms':>10}{'p95 ms':>10}{'max ms':>10}")
print("-" * 51)

for column, label in STAGES:
    v = values(column)
    if len(v) == 0:
        print(f"{label:<14}{0:>7}{'-':>10}{'-':>10}{'-':>10}")
        continue
    print(
        f"{label:<14}{len(v):>7}"
        f"{np.percentile(v, 50):>10.1f}"
        f"{np.percentile(v, 95):>10.1f}"
        f"{v.max():>10.1f}"
    )

total = values("total_ms")
over = total > OVER_MS
print()
print(f"Cycles over {OVER_MS} ms: {over.mean() * 100:.1f}% ({over.sum()} of {len(total)})")

errors = sum(1 for r in rows if r["error"])
not_visible = sum(1 for r in rows if r["arm_visible"] == "0")
print(f"Service errors:     {errors}")
print(f"Arm not visible:    {not_visible} cycles")
