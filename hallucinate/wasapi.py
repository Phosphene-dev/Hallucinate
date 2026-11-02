"""Bit-perfect playback's part on Windows: the output taken in exclusive mode (WASAPI), at the song's own format.

Windows' shared mixer runs every output at one rate (the one in Sound settings) and converts whatever plays at
another; it has no supported way for an app to switch it per song. Exclusive mode is the documented way around it:
for as long as Hallucinate holds the output, its samples go to the driver as they are, at the song's own rate,
and nothing else plays there. So it's held only while there's something to play: paused for a few seconds, it's
given back for other apps, and taken again on play.

`ExclusiveSink` stands in for the QAudioSink the equalizer's tap otherwise uses (the same calls: start, write
through what start returns, bytesFree, suspend, resume, reset, stop, setVolume), so eq.EqTap needs no second
path. Everything that talks to Windows runs on the sink's own thread (COM in its free-threaded mode), through
ctypes: nothing is added to the Windows bundle. If the output can't be had (another app holds it, exclusive mode is
switched off for it, it doesn't take the format), opening fails with a plain reason and the tap plays through the
shared mixer as before."""
import ctypes
import logging
import sys
import threading
import time

import numpy as np

logger = logging.getLogger(__name__)

HRESULT = ctypes.c_long
PERIOD_HNS = 400000  # 40 ms of sound per wake-up (in 100 ns units): steady from Python, unnoticeable when seeking
RELEASE_AFTER_PAUSE_S = 5.0
OPEN_TIMEOUT_S = 5.0

SHAREMODE_EXCLUSIVE = 1
STREAMFLAGS_EVENTCALLBACK = 0x00040000
CLSCTX_ALL = 0x17
COINIT_MULTITHREADED = 0x0
E_RENDER, ROLE_MULTIMEDIA = 0, 1
BUFFERFLAGS_SILENT = 0x2
WAVE_FORMAT_EXTENSIBLE = 0xFFFE

ERRORS = {
    0x8889000A: "another app is using this output by itself",
    0x8889000E: "this output doesn't allow exclusive mode (Sound settings → the device's Properties → Advanced)",
    0x88890008: "this output doesn't take the song's format",
    0x88890004: "the output went away",
    0x80070490: "there's no sound output",
    0x88890019: "the output wants another buffer size",
}
NOT_ALIGNED = 0x88890019
UNSUPPORTED = 0x88890008


class WasapiError(OSError):
    def __init__(self, hr, what):
        self.code = hr & 0xFFFFFFFF
        super().__init__(f"{ERRORS.get(self.code, what)} (0x{self.code:08X})")


class GUID(ctypes.Structure):
    _fields_ = [("data1", ctypes.c_uint32), ("data2", ctypes.c_uint16), ("data3", ctypes.c_uint16),
                ("data4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, text):
        h = text.replace("-", "")
        return cls(int(h[0:8], 16), int(h[8:12], 16), int(h[12:16], 16),
                   (ctypes.c_ubyte * 8)(*bytes.fromhex(h[16:32])))


CLSID_ENUMERATOR = "BCDE0395-E52F-467C-8E3D-C4579291692E"
IID_ENUMERATOR = "A95664D2-9614-4F35-A746-DE8DB63617E6"
IID_AUDIO_CLIENT = "1CB9AD4C-DBFA-4C32-B178-C2F568A703B2"
IID_RENDER_CLIENT = "F294ACFC-3146-4483-A7BF-ADDCA7C260E2"
SUBTYPE_PCM = "00000001-0000-0010-8000-00AA00389B71"
SUBTYPE_FLOAT = "00000003-0000-0010-8000-00AA00389B71"


class WAVEFORMATEXTENSIBLE(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("tag", ctypes.c_uint16), ("channels", ctypes.c_uint16), ("rate", ctypes.c_uint32),
                ("bytes_per_second", ctypes.c_uint32), ("block_align", ctypes.c_uint16),
                ("bits", ctypes.c_uint16), ("extra_size", ctypes.c_uint16), ("valid_bits", ctypes.c_uint16),
                ("channel_mask", ctypes.c_uint32), ("subformat", GUID)]


MASKS = {1: 0x4, 2: 0x3, 4: 0x33, 6: 0x3F, 8: 0x63F}


def wave_format(rate, channels, container, valid, is_float=False):
    fmt = WAVEFORMATEXTENSIBLE()
    fmt.tag, fmt.channels, fmt.rate = WAVE_FORMAT_EXTENSIBLE, channels, rate
    fmt.block_align = channels * container // 8
    fmt.bytes_per_second = rate * fmt.block_align
    fmt.bits, fmt.extra_size, fmt.valid_bits = container, 22, valid
    fmt.channel_mask = MASKS.get(channels, 0)
    fmt.subformat = GUID.parse(SUBTYPE_FLOAT if is_float else SUBTYPE_PCM)
    return fmt


# What each kind of decoded sample is tried as, best first: (container bits, valid bits, float). 24-bit songs
# come decoded as 32-bit integers (the low byte zero), so 32/32, 24-in-32 and packed 24 all keep every bit.
CANDIDATES = {
    "int16": [(16, 16, False), (32, 24, False), (24, 24, False), (32, 32, False)],
    "int32": [(32, 32, False), (32, 24, False), (24, 24, False), (16, 16, False)],
    "float": [(32, 32, True), (32, 32, False), (32, 24, False), (24, 24, False), (16, 16, False)],
    "uint8": [(16, 16, False), (32, 24, False), (24, 24, False)],
}


def convert(data, kind, target, volume=1.0):
    """Decoded bytes of `kind` ("int16", "int32", "float", "uint8") as the device's (container, valid, float)
    format. Where they're the same (the usual case) the bytes go through as they are."""
    container, valid, is_float = target
    same = {("int16", (16, 16, False)), ("int32", (32, 32, False)), ("int32", (32, 24, False)),
            ("float", (32, 32, True))}
    if volume == 1.0 and (kind, target) in same:
        return bytes(data)
    if kind == "int16":
        x = np.frombuffer(data, "<i2").astype(np.int64) << 16
    elif kind == "int32":
        x = np.frombuffer(data, "<i4").astype(np.int64)
    elif kind == "uint8":
        x = (np.frombuffer(data, "u1").astype(np.int64) - 128) << 24
    else:
        x = np.clip(np.round(np.frombuffer(data, "<f4").astype(np.float64) * 2147483647.0),
                    -2147483648, 2147483647).astype(np.int64)
    if volume != 1.0:  # (only the sleep timer's fade at its very end)
        x = (x * float(volume)).astype(np.int64)
    if is_float:
        return (x / 2147483648.0).astype("<f4").tobytes()
    if container == 16:
        return (x >> 16).astype("<i2").tobytes()
    if container == 32:
        return x.astype("<i4").tobytes()
    b = (x >> 8).astype("<i4").view(np.uint8).reshape(-1, 4)[:, :3]  # packed 24-bit, little-endian
    return b.tobytes()


def sample_kind(sample_format):
    from PySide6.QtMultimedia import QAudioFormat

    return {QAudioFormat.SampleFormat.Int16: "int16", QAudioFormat.SampleFormat.Int32: "int32",
            QAudioFormat.SampleFormat.Float: "float", QAudioFormat.SampleFormat.UInt8: "uint8"}.get(sample_format, "")


def device_id(qaudio_device):
    """The Windows endpoint id behind a Qt audio device ("" for the default output)."""
    if qaudio_device is None or qaudio_device.isNull():
        return ""
    try:
        return bytes(qaudio_device.id()).decode("utf-8", "ignore")
    except (TypeError, ValueError):
        return ""


class _Com:
    """The handful of COM calls needed, through each interface's table of functions."""

    def __init__(self):
        self.ole32 = ctypes.windll.ole32
        self.kernel32 = ctypes.windll.kernel32
        self.ole32.CoInitializeEx.restype = HRESULT
        self.ole32.CoCreateInstance.restype = HRESULT
        self.kernel32.CreateEventW.restype = ctypes.c_void_p
        self.kernel32.WaitForSingleObject.restype = ctypes.c_uint32
        self.kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self.kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

    @staticmethod
    def method(obj, index, *argtypes, restype=HRESULT):
        table = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
        fn = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(table[index])
        return lambda *args: fn(obj, *args)

    def call(self, obj, index, argtypes, *args, what="talk to the output"):
        hr = self.method(obj, index, *argtypes)(*args)
        if hr < 0:
            raise WasapiError(hr, f"couldn't {what}")
        return hr

    def release(self, obj):
        if obj:
            self.method(obj, 2, restype=ctypes.c_ulong)()


class Busy(Exception):
    """The output is still playing out a song at another format: try again in a moment (nothing is lost)."""


class Writer:
    """One tap's way into the held output: what QAudioSink offers the tap (start, write through what start
    returns, bytesFree, suspend, resume, reset, stop, setVolume, error), in its own queue. The output plays the
    writers in turn (see Sequencer), so one song's tail and the next song's start meet without a gap."""

    def __init__(self, sequencer, capacity, sink):
        self._seq, self.capacity, self._sink = sequencer, capacity, sink
        self.buf = bytearray()
        self.running = False
        self.closed = False

    @property
    def error(self):
        return self._sink.error

    @property
    def format(self):
        return self._sink.format

    def setBufferSize(self, _size):  # noqa: N802 - QAudioSink's names
        pass

    def setVolume(self, v):  # noqa: N802
        self._sink.volume = float(v)

    def start(self):
        return self

    def write(self, data):
        with self._seq.lock:
            if self.closed:
                return len(data)  # (its turn is over: what comes late is let go)
            n = max(0, min(len(data), self.capacity - len(self.buf)))
            self.buf += bytes(data[:n])
        return n

    def bytesFree(self):  # noqa: N802
        with self._seq.lock:
            return max(0, self.capacity - len(self.buf)) if not self.closed else self.capacity

    def suspend(self):
        self._seq.set_running(self, False)
        self._sink.wake()

    def resume(self):
        self._seq.set_running(self, True)
        self._sink.wake()

    def reset(self):
        with self._seq.lock:
            self.buf.clear()

    def stop(self):
        self._seq.remove(self)
        self._sink.wake()

    def deleteLater(self):  # noqa: N802
        self.stop()


class Sequencer:
    """The writers of one held output, oldest first: the oldest one plays; it gives way to the next once it has
    nothing left and the next has sound waiting (the end of a song, gapless), or once it's paused while the next
    plays. Nothing here talks to Windows: it's the order the sound goes out in."""

    def __init__(self):
        self.lock = threading.Lock()
        self.writers = []
        self.paused_at = time.monotonic()

    def add(self, capacity, sink):
        w = Writer(self, capacity, sink)
        with self.lock:
            self.writers.append(w)
        return w

    def remove(self, w):
        with self.lock:
            w.closed = True
            w.buf.clear()
            if w in self.writers:
                self.writers.remove(w)
            if not any(x.running for x in self.writers):
                self.paused_at = time.monotonic()

    def set_running(self, w, running):
        with self.lock:
            w.running = running
            if not any(x.running for x in self.writers):
                self.paused_at = time.monotonic()

    def running(self):
        with self.lock:
            return any(w.running for w in self.writers)

    def busy(self):
        """Whether something is still playing (a running writer with sound left)."""
        with self.lock:
            return any(w.running and w.buf for w in self.writers)

    def take(self, n):
        """Up to n bytes to play next, in turn."""
        out = bytearray()
        with self.lock:
            while len(out) < n and self.writers:
                w = self.writers[0]
                if w.running:
                    chunk = w.buf[:n - len(out)]
                    del w.buf[:len(chunk)]
                    out += chunk
                    if len(out) >= n:
                        break
                later = any(x.running and x.buf for x in self.writers[1:])
                if later and (not w.buf or not w.running):
                    w.closed = True  # its turn is over: the next one goes straight on
                    w.buf.clear()
                    self.writers.pop(0)
                    continue
                break  # (it has nothing yet: silence until it does)
        return bytes(out)


_REGISTRY_LOCK = threading.Lock()
_HELD = None  # the ExclusiveSink holding the output, shared by the taps (one song after another)


def open_writer(endpoint, rate, channels, kind, buffer_ms=250):
    """A writer into the output held in exclusive mode at this format: the one already held if it's the same
    format (the next song goes straight on), otherwise the output opened afresh once whatever plays has played
    out (Busy until then). RuntimeError when it can't be had at all."""
    global _HELD
    with _REGISTRY_LOCK:
        held = _HELD
        if held is not None and held.alive and held.matches(endpoint, rate, channels, kind):
            return held.add_writer(buffer_ms)
        if held is not None and held.alive and held.sequencer.busy():
            raise Busy()
        if held is not None:
            held.stop()
            _HELD = None
        held = ExclusiveSink(endpoint, rate, channels, kind)
        _HELD = held
        return held.add_writer(buffer_ms)


def release():
    """Lets the output go (bit-perfect switched off, or quitting)."""
    global _HELD
    with _REGISTRY_LOCK:
        if _HELD is not None:
            _HELD.stop()
            _HELD = None


class ExclusiveSink:
    """The output held in exclusive mode at one format; see the module's description. Taps write to it through
    their own Writer (open_writer). `kind` is the decoded samples' kind (see CANDIDATES); `endpoint` a Windows
    endpoint id ("" for the default output)."""

    def __init__(self, endpoint, rate, channels, kind):
        if sys.platform != "win32":
            raise RuntimeError("exclusive mode is only on Windows")
        if kind not in CANDIDATES:
            raise RuntimeError("an unknown sample format")
        self.endpoint, self.rate, self.channels, self.kind = endpoint, int(rate), int(channels), kind
        self.bytes_per_frame = channels * {"int16": 2, "int32": 4, "float": 4, "uint8": 1}[kind]
        self.sequencer = Sequencer()
        self.volume = 1.0
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._opened = threading.Event()
        self.error = ""  # set when the output was lost while playing (the taps give up on it then)
        self.format = None  # the (container, valid, float) the device took
        self._open_error = None
        self._thread = threading.Thread(target=self._run, name="wasapi-exclusive", daemon=True)
        self._thread.start()
        if not self._opened.wait(OPEN_TIMEOUT_S):
            self._stop.set()
            raise RuntimeError("the output didn't answer")
        if self._open_error is not None:
            raise RuntimeError(str(self._open_error))

    @property
    def alive(self):
        return self._thread.is_alive() and not self._stop.is_set() and not self.error

    def matches(self, endpoint, rate, channels, kind):
        return (endpoint, int(rate), int(channels), kind) == (self.endpoint, self.rate, self.channels, self.kind)

    def add_writer(self, buffer_ms=250):
        capacity = max(1, self.rate * buffer_ms // 1000) * self.bytes_per_frame
        return self.sequencer.add(capacity, self)

    def wake(self):
        self._wake.set()

    def stop(self):
        """Lets the output go, and waits (briefly) until it has: the next format may open it straight away."""
        self._stop.set()
        self._wake.set()
        if self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(1.0)

    # --- the output's own thread --------------------------------------------------------------------------
    def _run(self):
        com = None
        try:
            com = _Com()
            com.ole32.CoInitializeEx(None, COINIT_MULTITHREADED)
            self._event = com.kernel32.CreateEventW(None, False, False, None)
            self._loop(com)
        except Exception as e:  # noqa: BLE001 - whatever Windows says, it's said plainly and the tap moves on
            logger.info("Exclusive output: %s", e)
            if not self._opened.is_set():
                self._open_error = e
                self._opened.set()
            else:
                self.error = str(e)
        finally:
            if com is not None:
                if getattr(self, "_event", None):
                    com.kernel32.CloseHandle(self._event)
                com.ole32.CoUninitialize()

    def _loop(self, com):
        held = self._take(com)  # (client, render client, buffer frames) or None
        self.format = held[3]
        self._opened.set()
        try:
            while not self._stop.is_set():
                if held is None:  # given back while paused: taken again on play
                    self._wake.wait(0.5)
                    self._wake.clear()
                    if self.sequencer.running() and not self._stop.is_set():
                        held = self._take(com)
                    continue
                client, render, frames, target = held
                if not self.sequencer.running():
                    com.call(client, 11, ())  # Stop
                    self._wake.wait(0.2)
                    self._wake.clear()
                    if (not self.sequencer.running()
                            and time.monotonic() - self.sequencer.paused_at > RELEASE_AFTER_PAUSE_S):
                        self._give_back(com, held)  # (paused a while: other apps may play)
                        held = None
                        continue
                    if self.sequencer.running():
                        com.call(client, 10, ())  # Start
                    continue
                if com.kernel32.WaitForSingleObject(self._event, 500) != 0:
                    continue  # (no wake-up: the device stalled for a moment, or it was stopped)
                self._fill(com, render, frames, target)
        finally:
            if held is not None:
                self._give_back(com, held)

    def _take(self, com):
        """Opens the output in exclusive mode at the first format it takes; (client, render, frames, format)."""
        enumerator = ctypes.c_void_p()
        hr = com.ole32.CoCreateInstance(ctypes.byref(GUID.parse(CLSID_ENUMERATOR)), None, CLSCTX_ALL,
                                        ctypes.byref(GUID.parse(IID_ENUMERATOR)), ctypes.byref(enumerator))
        if hr < 0:
            raise WasapiError(hr, "couldn't list the outputs")
        device = ctypes.c_void_p()
        try:
            found = False
            if self.endpoint:
                hr = com.method(enumerator, 5, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p))(
                    self.endpoint, ctypes.byref(device))
                found = hr >= 0 and bool(device)
            if not found:
                com.call(enumerator, 4, (ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)),
                         E_RENDER, ROLE_MULTIMEDIA, ctypes.byref(device), what="find the output")
        finally:
            com.release(enumerator)
        try:
            return self._initialize(com, device)
        finally:
            com.release(device)

    def _activate(self, com, device):
        client = ctypes.c_void_p()
        com.call(device, 3, (ctypes.POINTER(GUID), ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)),
                 ctypes.byref(GUID.parse(IID_AUDIO_CLIENT)), CLSCTX_ALL, None, ctypes.byref(client),
                 what="open the output")
        return client

    def _initialize(self, com, device):
        client = self._activate(com, device)
        chosen, last = None, None
        for target in CANDIDATES[self.kind]:
            fmt = wave_format(self.rate, self.channels, *target)
            hr = com.method(client, 7, ctypes.c_int, ctypes.POINTER(WAVEFORMATEXTENSIBLE), ctypes.c_void_p)(
                SHAREMODE_EXCLUSIVE, ctypes.byref(fmt), None)
            if hr == 0:
                chosen = (target, fmt)
                break
            last = hr
        if chosen is None:
            com.release(client)
            raise WasapiError(last if last is not None else UNSUPPORTED, "the output doesn't take the song's format")
        target, fmt = chosen
        init = com.method(client, 3, ctypes.c_int, ctypes.c_uint32, ctypes.c_longlong, ctypes.c_longlong,
                          ctypes.POINTER(WAVEFORMATEXTENSIBLE), ctypes.c_void_p)
        period = PERIOD_HNS
        hr = init(SHAREMODE_EXCLUSIVE, STREAMFLAGS_EVENTCALLBACK, period, period, ctypes.byref(fmt), None)
        if (hr & 0xFFFFFFFF) == NOT_ALIGNED:  # the device wants a period that's a whole number of its blocks
            frames = ctypes.c_uint32()
            com.call(client, 4, (ctypes.POINTER(ctypes.c_uint32),), ctypes.byref(frames))
            com.release(client)
            period = int(10_000_000 * frames.value / self.rate + 0.5)
            client = self._activate(com, device)
            hr = init(SHAREMODE_EXCLUSIVE, STREAMFLAGS_EVENTCALLBACK, period, period, ctypes.byref(fmt), None)
        if hr < 0:
            com.release(client)
            raise WasapiError(hr, "couldn't open the output by itself")
        try:
            com.call(client, 13, (ctypes.c_void_p,), self._event)  # SetEventHandle
            frames = ctypes.c_uint32()
            com.call(client, 4, (ctypes.POINTER(ctypes.c_uint32),), ctypes.byref(frames))  # GetBufferSize
            render = ctypes.c_void_p()
            com.call(client, 14, (ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)),
                     ctypes.byref(GUID.parse(IID_RENDER_CLIENT)), ctypes.byref(render))  # GetService
        except Exception:
            com.release(client)
            raise
        held = (client, render, frames.value, target)
        self._silence(com, render, frames.value)  # (a whole buffer to start with: the device asks for the next)
        if self.sequencer.running():
            com.call(client, 10, ())
        return held

    def _silence(self, com, render, frames):
        buf = ctypes.c_void_p()
        com.call(render, 3, (ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)), frames, ctypes.byref(buf))
        com.call(render, 4, (ctypes.c_uint32, ctypes.c_uint32), frames, BUFFERFLAGS_SILENT)

    def _fill(self, com, render, frames, target):
        container = target[0]
        out_frame = self.channels * container // 8
        chunk = self.sequencer.take(frames * self.bytes_per_frame)
        data = convert(chunk, self.kind, target, self.volume) if chunk else b""
        buf = ctypes.c_void_p()
        com.call(render, 3, (ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)), frames, ctypes.byref(buf))
        size = frames * out_frame
        if len(data) < size:
            data += b"\0" * (size - len(data))  # (nothing more yet: silence rather than old sound)
        ctypes.memmove(buf, data, size)
        com.call(render, 4, (ctypes.c_uint32, ctypes.c_uint32), frames, 0)

    def _give_back(self, com, held):
        client, render = held[0], held[1]
        try:
            com.method(client, 11)()  # Stop (an output that went away answers with an error: let go all the same)
        except OSError:
            pass
        finally:
            com.release(render)
            com.release(client)
