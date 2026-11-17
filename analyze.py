import csv
import glob
import os
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
    ("frame_age_ms", "camera->servo"),
]


def load(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print(f"{path} has no rows")
        raise SystemExit
    return rows


def column(rows, name):
    return np.array([float(r[name]) for r in rows if r.get(name, "") not in ("", None)])


def summarize(path):
    rows = load(path)
    first = float(rows[0]["timestamp"])
    last = float(rows[-1]["timestamp"]) + float(rows[-1]["total_ms"]) / 1000
    duration = last - first
    total = column(rows, "total_ms")

    stats = {}
    for col, label in STAGES:
        v = column(rows, col)
        if len(v):
            stats[label] = (len(v), np.percentile(v, 50), np.percentile(v, 95), np.percentile(v, 99), v.max())
        else:
            stats[label] = None

    skipped = column(rows, "skipped_frames")
    return {
        "path": path,
        "cycles": len(rows),
        "duration": duration,
        "fps": len(rows) / duration,
        "over_pct": (total > OVER_MS).mean() * 100,
        "over_n": int((total > OVER_MS).sum()),
        "errors": sum(1 for r in rows if r.get("error")),
        "not_visible": sum(1 for r in rows if r.get("arm_visible") == "0"),
        "skipped": int(skipped.sum()) if len(skipped) else None,
        "stats": stats,
    }


def fmt(value):
    return f"{value:.1f}" if value is not None else "-"


def print_single(s):
    print(f"Log:      {s['path']}")
    print(f"Cycles:   {s['cycles']}")
    print(f"Duration: {s['duration']:.1f} s")
    print(f"FPS:      {s['fps']:.1f}")
    print()
    print(f"{'Stage':<15}{'n':>7}{'p50 ms':>10}{'p95 ms':>10}{'p99 ms':>10}{'max ms':>10}")
    print("-" * 62)
    for _, label in STAGES:
        st = s["stats"][label]
        if st is None:
            print(f"{label:<15}{0:>7}{'-':>10}{'-':>10}{'-':>10}{'-':>10}")
        else:
            n, p50, p95, p99, mx = st
            print(f"{label:<15}{n:>7}{p50:>10.1f}{p95:>10.1f}{p99:>10.1f}{mx:>10.1f}")
    print()
    print(f"Cycles over {OVER_MS} ms: {s['over_pct']:.1f}% ({s['over_n']} of {s['cycles']})")
    print(f"Service errors:     {s['errors']}")
    print(f"Arm not visible:    {s['not_visible']} cycles")
    if s["skipped"] is not None:
        print(f"Skipped frames:     {s['skipped']}")


def print_compare(a, b):
    print(f"A: {a['path']}")
    print(f"B: {b['path']}")
    print()
    print(f"{'Stage':<15}{'A p50':>9}{'B p50':>9}{'change':>9}"
          f"{'A p95':>9}{'B p95':>9}{'change':>9}"
          f"{'A p99':>9}{'B p99':>9}{'change':>9}")
    print("-" * 96)
    for _, label in STAGES:
        sa, sb = a["stats"][label], b["stats"][label]
        a50 = sa[1] if sa else None
        b50 = sb[1] if sb else None
        a95 = sa[2] if sa else None
        b95 = sb[2] if sb else None
        a99 = sa[3] if sa else None
        b99 = sb[3] if sb else None
        d50 = fmt(b50 - a50) if (sa and sb) else "-"
        d95 = fmt(b95 - a95) if (sa and sb) else "-"
        d99 = fmt(b99 - a99) if (sa and sb) else "-"
        print(f"{label:<15}{fmt(a50):>9}{fmt(b50):>9}{d50:>9}{fmt(a95):>9}{fmt(b95):>9}{d95:>9}{fmt(a99):>9}{fmt(b99):>9}{d99:>9}")
    print()
    print(f"FPS:                 A {a['fps']:.1f}   B {b['fps']:.1f}")
    print(f"Cycles over {OVER_MS} ms:  A {a['over_pct']:.1f}%   B {b['over_pct']:.1f}%")


# 0 files: newest log | 1 file: summarize it | 2 files: compare A vs B
args = sys.argv[1:]
if len(args) == 0:
    files = glob.glob("logs/run_*.csv")
    if not files:
        print("No logs found in logs/")
        raise SystemExit
    print_single(summarize(max(files, key=os.path.getmtime)))
elif len(args) == 1:
    print_single(summarize(args[0]))
else:
    print_compare(summarize(args[0]), summarize(args[1]))
