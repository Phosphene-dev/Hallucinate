"""Crash records, so a tester can send us what happened instead of "it closed".

Two kinds of failure are kept in <data>/crash/:
- native.log: a hard crash (segfault, abort, a fatal Qt error), written by faulthandler as the process dies,
  with the Python stack of every thread;
- python.log: an exception that reached the top of the program, or of a thread, with its traceback;
- freeze.log: the window stopped responding for a while (see `watch_freezes()`), with what every thread was
  doing at the time, and whether it came back.

`install()` starts recording for this run. `take_previous()`, called before it, returns what the previous run
left behind and clears it, so the window can offer to copy it once. Paths under the home folder are
replaced with "~" because the text usually ends up in a public issue."""
import faulthandler
import logging
import sys
import threading
import time
import traceback
from pathlib import Path

from . import __version__

MAX_BYTES = 64_000  # a runaway loop of errors shouldn't fill the disk
_state = {"dir": None, "native": None, "beat": 0.0, "watch": None}
FREEZE_AFTER = 20.0  # seconds without the window's heartbeat


def _redact(text):
    from .diagnostics import _redact as redact

    return redact(text)


def take_previous(folder):
    """(report, crashed) from what the previous run left in `folder`: ("", False) when there's nothing.

    `crashed` is True for a hard crash, False when the app kept running after an error. A native log holding
    only its start line means the run ended without exiting cleanly but without a crash either (it was
    killed, or the computer lost power), so it isn't reported. Reading the records clears them."""
    folder = Path(folder)
    parts, crashed = [], False
    for name, title in (("native.log", "Crash"), ("python.log", "Unhandled error"), ("freeze.log", "Stopped responding")):
        path = folder / name
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        try:
            path.unlink()
        except OSError:
            pass
        if name == "native.log":
            if len(text.splitlines()) < 2:
                continue
            crashed = True
        if text:
            parts.append(f"{title}:\n{text[-MAX_BYTES:]}")
    return _redact("\n\n".join(parts)), crashed


def _append(name, text):
    folder = _state["dir"]
    if folder is None:
        return
    path = folder / name
    try:
        if path.exists() and path.stat().st_size > MAX_BYTES:
            return
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass


def _record(kind, exc_type, exc, tb, where=""):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    body = "".join(traceback.format_exception(exc_type, exc, tb))
    _append("python.log", f"--- {stamp}, Hallucinate {__version__}{where} ---\n{body}\n")
    logging.getLogger("hallucinate").error("%s: %s", kind, "".join(traceback.format_exception_only(exc_type, exc)).strip())


def install(folder):
    """Record this run's crashes in `folder`. Call once, after taking the previous run's report."""
    folder = Path(folder)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        native = open(folder / "native.log", "w", encoding="utf-8")  # noqa: SIM115 - must outlive this call
    except OSError:
        return False
    _state["dir"], _state["native"] = folder, native
    native.write(f"Hallucinate {__version__}, started {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    native.flush()
    faulthandler.enable(file=native, all_threads=True)

    previous_hook = sys.excepthook

    def excepthook(exc_type, exc, tb):
        if not issubclass(exc_type, KeyboardInterrupt):
            _record("Unhandled error", exc_type, exc, tb)
        previous_hook(exc_type, exc, tb)

    sys.excepthook = excepthook

    def thread_hook(args):
        if args.exc_type is not SystemExit:
            name = getattr(args.thread, "name", "?")
            _record("Unhandled error in a thread", args.exc_type, args.exc_value, args.exc_traceback,
                    f", thread {name}")

    threading.excepthook = thread_hook
    return True


def watch_freezes(threshold=FREEZE_AFTER, clock=time.monotonic, interval=1.0, context=None):
    """Notice when the window stops responding: a timer on the GUI thread beats every half second and a small
    thread checks the beat. Once it's been silent for `threshold` seconds, the stacks of every thread go in
    freeze.log (what was busy), and when it beats again, how long it was gone. A computer that slept isn't a
    freeze: the watcher itself stops then, so a gap in its own checks resets the count. `context()`, called with
    each beat on the GUI thread, says what the app was doing (the window's state, what's playing), and the last
    one goes in the record. Returns the timer."""
    from PySide6.QtCore import QTimer

    if _state["dir"] is None:
        return None
    _state["beat"] = clock()

    _state["context"] = ""

    def beat():
        _state["beat"] = clock()
        if context is not None:
            try:
                _state["context"] = str(context())
            except Exception:  # noqa: BLE001 - a record of the state must never break the app
                pass

    timer = QTimer()
    timer.setInterval(500)
    timer.timeout.connect(beat)
    timer.start()
    stop = threading.Event()

    def watch():
        frozen_since = None
        last_check = clock()
        while not stop.wait(interval):
            now = clock()
            if now - last_check > max(5.0, interval * 5):  # the whole process was paused (sleep, a debugger)
                _state["beat"] = now
            last_check = now
            silent = now - _state["beat"]
            if frozen_since is None and silent >= threshold:
                frozen_since = _state["beat"]
                _write_freeze(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')}, Hallucinate {__version__}: the window "
                              f"stopped responding {silent:.0f} s ago.\n"
                              + (f"Just before: {_state.get('context')}\n" if _state.get("context") else "")
                              + "What each thread was doing:\n", stacks=True)
            elif frozen_since is not None and silent < threshold:
                _write_freeze(f"It came back after {_state['beat'] - frozen_since:.0f} s.\n\n")
                frozen_since = None

    thread = threading.Thread(target=watch, name="freeze-watch", daemon=True)
    thread.start()
    _state["watch"] = (timer, stop, thread)
    return timer


def _write_freeze(text, stacks=False):
    folder = _state["dir"]
    if folder is None:
        return
    try:
        path = folder / "freeze.log"
        if path.exists() and path.stat().st_size > MAX_BYTES:
            return
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)
            if stacks:
                f.flush()
                faulthandler.dump_traceback(file=f, all_threads=True)
                f.write("\n")
    except OSError:
        pass


def record_fatal(message):
    """A fatal Qt message: Qt aborts right after it, and faulthandler then adds the stacks."""
    native = _state["native"]
    if native is not None:
        try:
            native.write(f"Qt fatal: {_redact(str(message))}\n")
            native.flush()
        except (OSError, ValueError):
            pass


def finish():
    """A clean exit: the native log holds only its header, so drop it."""
    native, folder = _state["native"], _state["dir"]
    if _state["watch"] is not None:
        timer, stop, _thread = _state["watch"]
        stop.set()
        timer.stop()
        _state["watch"] = None
    if native is None:
        return
    try:
        faulthandler.disable()
        native.close()
        (folder / "native.log").unlink()
    except OSError:
        pass
    _state["native"] = None
