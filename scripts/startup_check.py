"""Time Hallucinate's start-up and measure its memory on a big synthetic library.

    python scripts/startup_check.py [--tracks 250000] [--plays 300000] [--runs 3] [--dir /tmp/hallucinate-scale]

Builds the library once with bench_library.build (reused when it exists), then starts the real app on a copy
of it several times with HALLUCINATE_STARTUP_TRACE set, and reports when each start-up step was reached
(seconds after launch: imports done, application created, library opened, services up, window loaded, first
frame drawn, library ready) and the memory in use. Runs offscreen unless QT_QPA_PLATFORM says otherwise.
scale_check.py measures how the running app copes with such a library; this measures getting there."""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
STEPS = ["imports", "application", "library-opened", "services", "window-loaded", "first-frame", "library-ready"]


def rss_mb(pid):
    try:
        with open(f"/proc/{pid}/statm") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 1e6
    except (OSError, ValueError):
        return 0.0


def one_run(tmp, settle_ms):
    """Start the app on the data in `tmp`, let it run settle_ms, and quit (cleanly, as a user would)."""
    data = tmp / "data"
    env = dict(os.environ, HALLUCINATE_STARTUP_TRACE="1", HALLUCINATE_DATA=str(data), HOME=str(tmp),
               XDG_CONFIG_HOME=str(tmp / "config"), XDG_CACHE_HOME=str(tmp / "cache"),
               HALLUCINATE_DISABLE_LEGACY_MIGRATION="1", HALLUCINATE_CONTROL_SOCKET=f"startup-{os.getpid()}")
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    start = time.time()
    proc = subprocess.Popen([sys.executable, "-m", "hallucinate", "--quit-after", str(settle_ms)],
                            cwd=ROOT, env=env, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
    peak = {"rss": 0.0, "end": 0.0}

    def sample():
        while proc.poll() is None:
            value = rss_mb(proc.pid)
            peak["rss"] = max(peak["rss"], value)
            peak["end"] = value or peak["end"]
            time.sleep(0.05)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    marks = {}
    for line in proc.stderr:
        if line.startswith("startup-trace "):
            _, step, stamp = line.split()
            marks.setdefault(step, float(stamp) - start)
    proc.wait(timeout=300)
    sampler.join(1)
    return marks, peak


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tracks", type=int, default=250_000)
    ap.add_argument("--plays", type=int, default=300_000)
    ap.add_argument("--runs", type=int, default=4)
    ap.add_argument("--settle", type=int, default=6000, help="ms the app runs before quitting")
    ap.add_argument("--dir", default="/tmp/hallucinate-scale")
    args = ap.parse_args()
    work = Path(args.dir) / f"n{args.tracks}"
    work.mkdir(parents=True, exist_ok=True)
    db = work / "library.db"
    if not db.exists():
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import bench_library
        from PySide6.QtGui import QGuiApplication

        app = QGuiApplication(sys.argv[:1])  # noqa: F841 - covers are drawn with QImage
        print(f"Building {args.tracks} songs and {args.plays} plays…", flush=True)
        bench_library.build(db, args.tracks, args.plays, work / "covers")
    print(f"{args.tracks} songs; seconds after launch: first start (as after a crash, so the database gets its"
          f" integrity check), then the best of {args.runs - 1} restarts")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "data").mkdir()
        shutil.copy2(db, tmp / "data" / "library.db")
        results = [one_run(tmp, args.settle) for _ in range(args.runs)]
    for step in STEPS:
        times = [marks.get(step) for marks, _ in results]
        if all(t is not None for t in times):
            later = f"{min(times[1:]):6.2f}" if len(times) > 1 else "     -"
            print(f"  {step:15s} {times[0]:6.2f}  {later}")
        else:
            print(f"  {step:15s}    not reached")
    print(f"  memory: peak {max(p['rss'] for _, p in results):.0f} MB, "
          f"after {args.settle / 1000:g} s {min(p['end'] for _, p in results):.0f} MB")


if __name__ == "__main__":
    main()
