"""Writing a file so it's either the old one or the whole new one, never half of either."""
import os
import tempfile


def _read_umask():
    mask = os.umask(0)  # the only way to read it; done once, at import, before any worker threads exist
    os.umask(mask)
    return mask


_DEFAULT_MODE = 0o666 & ~_read_umask()


def write_atomic(target, write, private=False):
    """Write a file so that it's either the old one or the complete new one, never half of either: into a
    temporary file next to it, flushed to disk, then renamed over it. `write(f)` writes to the open file.
    The file keeps the permissions it had (or gets the usual ones for a new file); `private` makes it
    readable by you alone (backups hold your listening history)."""
    target = os.fspath(target)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=os.path.dirname(os.path.abspath(target)))
    try:
        with os.fdopen(fd, "wb") as f:
            write(f)
            f.flush()
            os.fsync(f.fileno())
        if not private:
            try:
                mode = os.stat(target).st_mode & 0o7777
            except OSError:
                mode = _DEFAULT_MODE
            os.chmod(tmp, mode)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_text(target, text, encoding="utf-8"):
    write_atomic(target, lambda f: f.write(text.encode(encoding)))
