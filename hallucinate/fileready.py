"""Checking on a song file without letting a slow disk hang the window.

A file on a disk that's spinning up, or on a network share that has gone away, can take seconds (or forever)
to open. `soon` runs such a check on a thread of its own and waits only briefly for it: the player then
carries on in the background if the disk is slow (see Player._check_file)."""
import threading


def soon(fn, late, timeout):
    """fn() on a thread of its own. (True, its value) if it answers within `timeout` seconds; otherwise
    (False, None), and late(value) is called from that thread once it does."""
    box = {}
    done = threading.Event()
    lock = threading.Lock()

    def run():
        try:
            value = fn()
        except Exception:  # noqa: BLE001 - a check that broke counts as "no"
            value = False
        with lock:
            box["value"] = value
            done.set()
            gave_up = box.get("gave_up", False)
        if gave_up:
            late(value)

    threading.Thread(target=run, name="file-check", daemon=True).start()
    done.wait(timeout)
    with lock:
        if done.is_set():
            return True, box["value"]
        box["gave_up"] = True
        return False, None
