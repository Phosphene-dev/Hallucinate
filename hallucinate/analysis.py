"""Decoding songs for their waveform and loudness in a helper process, so a file FFmpeg chokes on can't
freeze or crash the window.

QAudioDecoder has to be driven from a thread with a Qt event loop, and in the app that meant the window's
thread. A damaged or unusual file can leave FFmpeg stuck, and then stopping the decoder never returns: the
window stopped responding while ReplayGain was measuring. Here the decoding runs in a second copy of the
program (`hallucinate --analysis-worker`), one song at a time. It reports progress as it goes; if it stops
making progress for STALL_S, or dies, it's ended and the next song gets a fresh one. It quits by itself after
IDLE_MS with nothing to do.

The protocol is one JSON object per line. Asked: {"id", "path", "kind": "waveform" | "loudness" | "spectrogram" |
"render", "envelope": bool, "options": {…}} ("render" writes the song as heard here to a WAV file for a cast
device: see core/cast/render.py and render_options). Answered: {"id", "beat": buffers decoded so far} while working, then {"id", "result"}
(None when the file couldn't be decoded; {"silent": true} for loudness of a silent song)."""
import base64
import json
import os
import sys
import threading
import time

import numpy as np
from PySide6.QtCore import QObject, QProcess, QTimer, Signal, Slot

STALL_S = 45.0  # no progress for this long: the helper is stuck, so it's ended (a busy disk can be slow)
IDLE_MS = 60_000  # the helper quits after this long with nothing to do
BEAT_MS = 1000


def _pack(array, dtype=np.float32):
    return base64.b64encode(np.ascontiguousarray(array, dtype=dtype).tobytes()).decode("ascii")


def _unpack(text, dtype=np.float32):
    return np.frombuffer(base64.b64decode(text), dtype=dtype)


def command():
    """How to start the helper: this same program with --analysis-worker."""
    if getattr(sys, "frozen", False):  # the Windows and macOS builds: the app itself is the executable
        return sys.executable, ["--analysis-worker"]
    python = sys.executable
    if not os.path.basename(python).lower().startswith("python"):
        # The AppImage gives its own file as the interpreter (starting it runs the app): use the Python inside
        # it, or else the AppImage itself, which hands --analysis-worker on to the app.
        inside = os.path.join(sys.prefix, "bin", f"python{sys.version_info[0]}.{sys.version_info[1]}")
        if not os.path.isfile(inside):
            return python, ["--analysis-worker"]
        python = inside
    # -P (3.11+): not the current folder first, where a folder named hallucinate would be imported instead
    safe = ["-P"] if sys.version_info >= (3, 11) else []
    return python, ["-s", *safe, "-c", "import sys; from hallucinate.analysis import serve; sys.exit(serve())"]


def _helper_path(pythonpath=""):
    """Where the helper finds its modules: this copy of the app, then what's already on PYTHONPATH, then this
    process's own module path. Nix puts PySide6 and numpy on the path from inside its launcher script, not
    through PYTHONPATH, so a plain `python -c` wouldn't find them. The user's own site-packages stay out,
    as the helper's -s keeps them out."""
    import site
    from pathlib import Path

    user = site.getusersitepackages() if site.ENABLE_USER_SITE is not None else ""
    paths = [str(Path(__file__).resolve().parent.parent)] + [p for p in pythonpath.split(os.pathsep) if p]
    paths += [p for p in sys.path if p and p != user and os.path.isdir(p)]
    return list(dict.fromkeys(paths))


# --- the helper process ------------------------------------------------------------------------------------
def _pipes():
    """The helper's stdin and stdout as binary files. A windowed Windows build has no sys.stdin/stdout even
    when started with pipes, so they're opened from the process's standard handles there."""
    if sys.stdin is not None and sys.stdout is not None:
        return sys.stdin.buffer, sys.stdout.buffer
    if os.name == "nt":
        import ctypes
        import msvcrt

        kernel32 = ctypes.windll.kernel32
        kernel32.GetStdHandle.restype = ctypes.c_void_p
        fd_in = msvcrt.open_osfhandle(kernel32.GetStdHandle(-10), os.O_RDONLY | os.O_BINARY)
        fd_out = msvcrt.open_osfhandle(kernel32.GetStdHandle(-11), os.O_BINARY)
        return os.fdopen(fd_in, "rb", 0), os.fdopen(fd_out, "wb", 0)
    return os.fdopen(0, "rb", 0), os.fdopen(1, "wb", 0)


def serve():
    """The helper's main loop: decode what's asked on stdin, answer on stdout. Ends when stdin closes."""
    from PySide6.QtCore import QCoreApplication, QUrl
    from PySide6.QtMultimedia import QAudioDecoder

    from . import loudness
    from .replaygain import channel_samples
    from .spectrogram import Accumulator
    from .waveform import blocks_from_samples, mono_samples, peaks_from_blocks

    app = QCoreApplication(sys.argv[:1])
    stdin, out = _pipes()
    lock = threading.Lock()

    def say(obj):
        with lock:
            out.write(json.dumps(obj).encode("utf-8") + b"\n")
            out.flush()

    class Jobs(QObject):
        arrived = Signal(object)

    jobs = Jobs()
    queue = []
    state = {"job": None, "decoder": None, "buffers": 0}

    def reader():
        for line in stdin:
            try:
                jobs.arrived.emit(json.loads(line))
            except ValueError:
                continue
        jobs.arrived.emit(None)  # the app closed its end: quit

    def arrived(job):
        if job is None:
            app.quit()
            return
        queue.append(job)
        start_next()

    def start_next():
        if state["job"] is not None or not queue:
            return
        job = state["job"] = queue.pop(0)
        state["buffers"] = 0
        state.update(ms=[], peak=[], rate=0, meter=loudness.Meter() if job.get("kind") == "loudness" else None,
                     spectrum=Accumulator() if job.get("kind") == "spectrogram" else None, render=None)
        decoder = state["decoder"] = QAudioDecoder()
        if job.get("kind") == "render":
            try:
                state["render"], fmt = _start_render(job)
            except (OSError, ValueError, TypeError, KeyError) as e:
                say({"id": job["id"], "result": None, "why": str(e)})
                state["job"] = state["decoder"] = None
                decoder.deleteLater()
                QTimer.singleShot(0, start_next)
                return
            if fmt is not None:
                decoder.setAudioFormat(fmt)
        decoder.bufferReady.connect(on_buffer)
        decoder.finished.connect(on_finished)
        decoder.error.connect(lambda _e: QTimer.singleShot(0, lambda: finish(None)))
        decoder.setSource(QUrl.fromLocalFile(job["path"]))
        decoder.start()

    def on_buffer():
        decoder = state["decoder"]
        if decoder is None:
            return
        buf = decoder.read()
        if not buf.isValid():
            return
        state["buffers"] += 1
        rate = buf.format().sampleRate()
        if state["render"] is not None:
            samples = channel_samples(buf)
            if samples is not None and samples.size and not state["render"].add(samples, rate):
                state["render_done"] = True
                decoder.blockSignals(True)  # past the song's end (a CUE song): no need to decode the rest
                QTimer.singleShot(0, on_finished)
            return
        if state["meter"] is not None:
            samples = channel_samples(buf)
            if samples is not None and samples.size:
                state["meter"].add(samples, rate)
            return
        if state["spectrum"] is not None:
            samples = channel_samples(buf)
            if samples is not None and samples.size:
                state["spectrum"].add(samples, rate)
            return
        if not state["rate"]:
            state["rate"] = rate
        samples = mono_samples(buf)
        if samples is not None and samples.size:
            ms, peak = blocks_from_samples(samples)
            state["ms"].append(ms)
            state["peak"].append(peak)

    def on_finished():
        job = state["job"]
        if job is None:
            return
        if state["render"] is not None:
            result = state["render"].finish()
            if not result["frames"]:
                result = None
        elif state["spectrum"] is not None:
            got = state["spectrum"].result()
            cols = got["columns"]
            result = {"columns": _pack(cols, np.uint8), "count": int(cols.shape[0]), "rows": int(cols.shape[1]),
                      "rate": got["rate"], "channels": got["channels"]}
        elif state["meter"] is not None:
            got = loudness.track_result(state["meter"])
            result = {"silent": True} if got is None else {
                "loudness": got["loudness"], "gain": got["gain"], "peak": got["peak"],
                "blocks": _pack(got["blocks"], np.float64)}
        else:
            ms = np.concatenate(state["ms"]) if state["ms"] else np.zeros(0, np.float32)
            peak = np.concatenate(state["peak"]) if state["peak"] else np.zeros(0, np.float32)
            result = {"peaks": peaks_from_blocks(ms, peak) if ms.size else []}
            if job.get("envelope") and ms.size and state["rate"]:
                result["envelope"] = {"ms": _pack(ms), "peak": _pack(peak), "rate": state["rate"]}
        QTimer.singleShot(0, lambda: finish(result))

    def finish(result):
        job, decoder = state["job"], state["decoder"]
        if job is None:
            return
        state["job"] = state["decoder"] = None
        if state.get("render") is not None and not state["render"].done:
            state["render"].abandon()  # the file couldn't be decoded: what was written is no use
        if decoder is not None:
            decoder.blockSignals(True)
            decoder.deleteLater()  # (if this is where FFmpeg is stuck, the app ends this process)
        say({"id": job["id"], "result": result})
        start_next()

    def beat():
        if state["job"] is not None:
            say({"id": state["job"]["id"], "beat": state["buffers"]})

    jobs.arrived.connect(arrived)
    timer = QTimer()
    timer.timeout.connect(beat)
    timer.start(BEAT_MS)
    threading.Thread(target=reader, name="analysis-input", daemon=True).start()
    return app.exec()


def render_options(gain=1.0, start=0.0, end=0.0, rate=0, channels=2, eq_on=False, gains=None, curve=None,
                   crossfeed=""):
    """The options of a "render" job (what this computer's sound is set to, for one song)."""
    return {"gain": float(gain), "start": float(start), "end": float(end), "rate": int(rate or 0),
            "channels": int(channels or 2), "eq": {"on": bool(eq_on), "gains": list(gains or [0.0] * 10),
                                                   "curve": curve, "crossfeed": crossfeed or ""}}


def _start_render(job):
    """(Renderer, the QAudioFormat to ask the decoder for or None) for a render job."""
    from PySide6.QtMultimedia import QAudioFormat

    from . import eq
    from .core.cast.render import Renderer

    opts = job.get("options") or {}
    out = job["out"]
    processor, delay = None, 0
    e = opts.get("eq") or {}
    if eq.available() and (e.get("on") or e.get("crossfeed") in eq.CROSSFEED):
        processor = eq.EqProcessor()
        processor.eq_on = bool(e.get("on"))
        processor.set_gains([float(g) for g in (e.get("gains") or [0.0] * 10)][:10])
        processor.set_curve(e.get("curve") or None)
        processor.set_crossfeed(e.get("crossfeed") or "")
        delay = 0 if processor.eq_flat else eq.TAPS // 2
    renderer = Renderer(out, processor=processor, delay=delay, gain=float(opts.get("gain", 1.0)),
                        start=float(opts.get("start", 0.0)), end=float(opts.get("end", 0.0)))
    fmt = None
    rate = int(opts.get("rate") or 0)
    if rate:
        fmt = QAudioFormat()
        fmt.setSampleRate(rate)
        fmt.setChannelCount(max(1, min(2, int(opts.get("channels") or 2))))
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)
    return renderer, fmt


# --- the app's side ------------------------------------------------------------------------------------------
class Analyser(QObject):
    """submit(path, kind, then, envelope=False) decodes `path` in the helper and calls then(result) on this
    thread: the result's dict, or None when the file couldn't be decoded (or the helper got stuck on it).
    Songs are done one at a time, in the order asked (`first=True` puts one at the front)."""

    def __init__(self, parent=None, program=None):
        super().__init__(parent)
        self._program = program or command()
        self._proc = None
        self._buffer = b""
        self._queue = []  # [(id, path, kind, envelope, then, extra)]
        self._current = None
        self._next_id = 0
        self._progress = (0, 0.0)  # (buffers decoded, when that last went up)
        self._clock = time.monotonic
        self._watch = QTimer(self)
        self._watch.setInterval(BEAT_MS)
        self._watch.timeout.connect(self._check)
        self._idle = QTimer(self)
        self._idle.setSingleShot(True)
        self._idle.setInterval(IDLE_MS)
        self._idle.timeout.connect(self._stop_process)

    @property
    def busy(self):
        return self._current is not None or bool(self._queue)

    def submit(self, path, kind, then, envelope=False, first=False, extra=None):
        """`extra`: more fields for the job (a render's "out" and "options")."""
        self._next_id += 1
        job = (self._next_id, str(path), kind, bool(envelope), then, dict(extra or {}))
        self._queue.insert(0, job) if first else self._queue.append(job)
        self._idle.stop()
        self._send_next()
        return job[0]

    def cancel(self):
        """Forget everything asked; a song being decoded is abandoned (its helper ended)."""
        self._queue.clear()
        if self._current is not None:
            self._current = None
            self._stop_process()

    def shutdown(self):
        self._queue.clear()
        self._current = None
        self._idle.stop()
        proc = self._proc
        self._stop_process()
        if proc is not None:
            proc.waitForFinished(1000)  # killed: gone at once, unless stuck in the kernel (then not waited for)

    # --- the helper ------------------------------------------------------------------------------------
    def _ensure_process(self):
        if self._proc is not None:
            return True
        proc = QProcess(self)
        if not getattr(sys, "frozen", False):  # find this copy of the app, wherever it was started from
            from PySide6.QtCore import QProcessEnvironment

            env = QProcessEnvironment.systemEnvironment()
            env.insert("PYTHONPATH", os.pathsep.join(_helper_path(env.value("PYTHONPATH") if env.contains("PYTHONPATH") else "")))
            proc.setProcessEnvironment(env)
        proc.setStandardErrorFile(QProcess.nullDevice())  # FFmpeg's chatter about damaged files
        # Slots of this object, not lambdas: Qt cuts them off when it's deleted (a process going away with it
        # would otherwise call into it half-destroyed).
        proc.readyReadStandardOutput.connect(self._read)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_error)
        program, args = self._program
        proc.start(program, list(args))
        self._proc, self._buffer = proc, b""
        return True

    def _stop_process(self):
        proc, self._proc = self._proc, None
        self._watch.stop()
        if proc is not None:
            proc.blockSignals(True)
            if proc.state() != QProcess.ProcessState.NotRunning:
                proc.kill()  # doesn't wait; the object goes once the process has had time to go too
            QTimer.singleShot(2000, proc, proc.deleteLater)  # (dropped if it's deleted with this object first)

    def _send_next(self):
        if self._current is not None or not self._queue:
            return
        self._current = self._queue.pop(0)
        job_id, path, kind, envelope, _then, extra = self._current
        self._ensure_process()
        self._progress = (0, self._clock())
        self._proc.write(json.dumps(dict(extra, id=job_id, path=path, kind=kind, envelope=envelope)).encode("utf-8")
                         + b"\n")
        self._watch.start()

    @Slot()
    def _read(self):
        if self._proc is None:
            return
        self._buffer += bytes(self._proc.readAllStandardOutput())
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if self._current is None or msg.get("id") != self._current[0]:
                continue
            if "beat" in msg:
                if msg["beat"] > self._progress[0]:
                    self._progress = (msg["beat"], self._clock())
                continue
            self._done(_decode_result(self._current[2], msg.get("result")))

    def _check(self):
        if self._current is not None and self._clock() - self._progress[1] > STALL_S:
            self._stop_process()  # stuck on this file: end it, and the next song gets a new helper
            self._done(None)

    @Slot(int, QProcess.ExitStatus)
    def _on_finished(self, _code, _status):
        self._ended(self.sender())

    @Slot(QProcess.ProcessError)
    def _on_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self._ended(self.sender())

    def _ended(self, proc):
        if proc is not self._proc:
            return
        self._proc = None
        self._watch.stop()
        proc.deleteLater()
        if self._current is not None:  # it died on this file (or couldn't start)
            self._done(None)

    def _done(self, result):
        job, self._current = self._current, None
        self._watch.stop()
        if not self._queue:
            self._idle.start()
        try:
            if job is not None:
                job[4](result)
        finally:
            self._send_next()


def _decode_result(kind, result):
    if not isinstance(result, dict):
        return None
    try:
        if kind == "spectrogram":
            cols = _unpack(result["columns"], np.uint8).reshape(int(result["count"]), int(result["rows"]))
            return {**result, "columns": cols}
        if kind == "loudness":
            if result.get("silent"):
                return {"silent": True}
            return {**result, "blocks": _unpack(result["blocks"], np.float64)}
        env = result.get("envelope")
        if env:
            result["envelope"] = (_unpack(env["ms"]), _unpack(env["peak"]), int(env["rate"]))
        return result
    except (KeyError, TypeError, ValueError):
        return None
