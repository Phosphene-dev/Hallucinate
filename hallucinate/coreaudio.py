"""Bit-perfect playback's part on macOS: the output device runs at each song's own rate.

Core Audio mixes everything at the device's "nominal" sample rate and converts whatever plays at another rate.
Its mixer is 32-bit float, so at full volume and the song's own rate the samples reach the device as they are;
the rate is the part to take care of. Any app may set a device's rate (Audio MIDI Setup does just that): while
bit-perfect playback is on, Hallucinate sets it to each song's rate where the device has that rate, and puts back
the rate it found when bit-perfect playback is switched off or Hallucinate quits.

Plain ctypes on the Core Audio framework (AudioObjectGetPropertyData / AudioObjectSetPropertyData), so nothing
is added to the macOS bundle. Elsewhere `available()` is False and nothing is called."""
import ctypes
import logging
import struct
import sys

logger = logging.getLogger(__name__)

FRAMEWORK = "/System/Library/Frameworks/CoreAudio.framework/CoreAudio"


def _code(text):
    return struct.unpack(">I", text.encode("ascii"))[0]


SYSTEM_OBJECT = 1
DEFAULT_OUTPUT = _code("dOut")
NOMINAL_RATE = _code("nsrt")
AVAILABLE_RATES = _code("nsr#")
DEVICE_UID = _code("uid ")
SCOPE_GLOBAL = _code("glob")
ELEMENT_MAIN = 0


class _Address(ctypes.Structure):
    _fields_ = [("selector", ctypes.c_uint32), ("scope", ctypes.c_uint32), ("element", ctypes.c_uint32)]


class _Range(ctypes.Structure):
    _fields_ = [("minimum", ctypes.c_double), ("maximum", ctypes.c_double)]


_lib = None


def _framework():
    global _lib
    if _lib is None:
        lib = ctypes.CDLL(FRAMEWORK)
        for name in ("AudioObjectGetPropertyData", "AudioObjectSetPropertyData"):
            getattr(lib, name).restype = ctypes.c_int32
        lib.AudioObjectGetPropertyDataSize.restype = ctypes.c_int32
        _lib = lib
    return _lib


def _check(status, what):
    if status:
        raise OSError(f"Core Audio couldn't {what} (error {status})")


def _get(obj, selector, value):
    addr = _Address(selector, SCOPE_GLOBAL, ELEMENT_MAIN)
    size = ctypes.c_uint32(ctypes.sizeof(value))
    _check(_framework().AudioObjectGetPropertyData(ctypes.c_uint32(obj), ctypes.byref(addr), 0, None,
                                                   ctypes.byref(size), ctypes.byref(value)), "read the output")
    return value.value if hasattr(value, "value") else value


def default_device():
    """The default output device's id (0: none)."""
    return int(_get(SYSTEM_OBJECT, DEFAULT_OUTPUT, ctypes.c_uint32(0)))


def nominal_rate(device):
    return float(_get(device, NOMINAL_RATE, ctypes.c_double(0.0)))


def available_rates(device):
    """The rates the device can run at, as (minimum, maximum) ranges (most are single rates)."""
    lib = _framework()
    addr = _Address(AVAILABLE_RATES, SCOPE_GLOBAL, ELEMENT_MAIN)
    size = ctypes.c_uint32(0)
    _check(lib.AudioObjectGetPropertyDataSize(ctypes.c_uint32(device), ctypes.byref(addr), 0, None,
                                              ctypes.byref(size)), "list the output's rates")
    count = size.value // ctypes.sizeof(_Range)
    if not count:
        return []
    ranges = (_Range * count)()
    _check(lib.AudioObjectGetPropertyData(ctypes.c_uint32(device), ctypes.byref(addr), 0, None,
                                          ctypes.byref(size), ranges), "list the output's rates")
    return [(r.minimum, r.maximum) for r in ranges]


def set_nominal_rate(device, rate):
    addr = _Address(NOMINAL_RATE, SCOPE_GLOBAL, ELEMENT_MAIN)
    value = ctypes.c_double(float(rate))
    _check(_framework().AudioObjectSetPropertyData(ctypes.c_uint32(device), ctypes.byref(addr), 0, None,
                                                   ctypes.sizeof(value), ctypes.byref(value)),
           f"switch the output to {rate} Hz")


def available():
    if sys.platform != "darwin":
        return False
    try:
        return default_device() != 0
    except OSError:
        return False


def supports(ranges, rate):
    return any(lo - 0.5 <= rate <= hi + 0.5 for lo, hi in ranges)


class DeviceRate:
    """Switches the default output to a rate and back. `ops` stands in for this module's Core Audio calls in
    tests: an object with default_device(), nominal_rate(d), available_rates(d), set_nominal_rate(d, rate)."""

    def __init__(self, ops=None):
        self._ops = ops or sys.modules[__name__]
        self._found = None  # (device, the rate it ran at before Hallucinate changed it)

    def available(self):
        try:
            return self._ops.default_device() != 0
        except OSError:
            return False

    def __call__(self, rate):
        """Asks for `rate` (0: put back the rate the device had). A rate the device hasn't got is left alone
        (Core Audio converts it, and the signal path says so)."""
        ops = self._ops
        if not rate:
            if self._found is not None:
                device, before = self._found
                self._found = None
                ops.set_nominal_rate(device, before)
            return
        device = ops.default_device()
        if not device:
            raise OSError("no sound output")
        if self._found is not None and self._found[0] != device:
            self._found = None  # (another output now: leave the old one as it is)
        if not supports(ops.available_rates(device), rate):
            raise OSError(f"the output can't run at {rate} Hz")
        current = ops.nominal_rate(device)
        if self._found is None:
            self._found = (device, current)
        if abs(current - rate) > 0.5:
            ops.set_nominal_rate(device, rate)
