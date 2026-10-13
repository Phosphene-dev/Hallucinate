"""Crash records, so a tester can send us what happened instead of "it closed".

Two kinds of failure are kept in <data>/crash/:
- native.log: a hard crash (segfault, abort, a fatal Qt error), written by faulthandler as the process dies,
  with the Python stack of every thread;
- python.log: an exception that reached the top of the program, or of a thread, with its traceback.

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
_state = {"dir": None, "native": None}


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
    for name, title in (("native.log", "Crash"), ("python.log", "Unhandled error")):
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
    if native is None:
        return
    try:
        faulthandler.disable()
        native.close()
        (folder / "native.log").unlink()
    except OSError:
        pass
    _state["native"] = None
