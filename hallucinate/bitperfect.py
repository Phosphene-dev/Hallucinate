"""Bit-perfect playback's part outside Hallucinate: asking the system to run the output at each song's own rate.

On Linux with PipeWire, the output runs at one rate for everything (often 48 kHz), and anything at another rate
is resampled on the way. PipeWire lets an app ask for the rate it needs, `clock.force-rate` in its "settings"
metadata (what `pw-metadata -n settings 0 clock.force-rate 96000` does): while bit-perfect playback is on,
Hallucinate asks for each song's rate as it starts, and puts it back (0: PipeWire's own choice) when bit-perfect
playback is switched off and when Hallucinate quits. While it's asked for, other sounds on the computer play at
that rate too (PipeWire converts them, as it would anyway).

It's done with PipeWire's own `pw-metadata` tool, on a thread (it answers in milliseconds, but a stuck sound
server must never hold the window). On macOS the output device's own rate is switched instead (coreaudio.py);
on Windows the output is taken in exclusive mode at the song's format (wasapi.py), so nothing is asked here.
Without any of these (another Linux sound system, the Flatpak) nothing is asked and the signal path says the
output may resample."""
import logging
import os
import shutil
import subprocess
import sys
import threading

logger = logging.getLogger(__name__)

TOOL = "pw-metadata"
RATES = (44100, 48000, 88200, 96000, 176400, 192000, 352800, 384000)


def tool():
    """The pw-metadata command, or "" where rates can't be asked for (no PipeWire, not Linux)."""
    if not sys.platform.startswith("linux"):
        return ""
    from .audiobackend import pipewire_running

    if not pipewire_running():
        return ""
    return shutil.which(TOOL) or ""


def system():
    """What switches the output's rate here: "pipewire", "coreaudio", "wasapi" (exclusive mode, see wasapi.py)
    or "" (nothing: the system may resample)."""
    if sys.platform == "darwin":
        from . import coreaudio

        return "coreaudio" if coreaudio.available() else ""
    if sys.platform.startswith("win"):
        return "wasapi"
    return "pipewire" if tool() else ""


class RateRequest:
    """Asks the system for the rate a song needs (and gives it back): PipeWire on Linux, the output device itself
    on macOS. Remembers what it asked, so asking for the same rate again does nothing, and only ever puts back a
    rate it set itself."""

    def __init__(self, run=None, which=tool):
        if run is None and sys.platform == "darwin":
            from .coreaudio import DeviceRate

            device = DeviceRate()
            run, which = device, (lambda: "coreaudio" if device.available() else "")
        self._run = run or self._call
        self._which = which
        self._lock = threading.Lock()
        self.rate = 0  # what's asked for now (0: nothing)
        self.error = ""

    @property
    def available(self):
        return bool(self._which())

    def _call(self, rate):
        cmd = self._which()
        if not cmd:
            raise OSError("pw-metadata isn't here")
        subprocess.run([cmd, "-n", "settings", "0", "clock.force-rate", str(int(rate))], check=True,
                       timeout=3, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env=dict(os.environ, LC_ALL="C"))

    def ask(self, rate, wait=False):
        """Asks for `rate` (0 gives the choice back to PipeWire). Rates outside the usual ones are not asked for."""
        rate = int(rate or 0)
        if rate and rate not in RATES:
            rate = 0
        with self._lock:
            if rate == self.rate:
                return
            self.rate = rate

        def run():
            try:
                self._run(rate)
                self.error = ""
            except (OSError, subprocess.SubprocessError) as e:
                self.error = str(e) or type(e).__name__
                logger.info("Couldn't ask PipeWire for %s Hz: %s", rate, self.error)
        if wait:
            run()
        else:
            threading.Thread(target=run, name="pipewire-rate", daemon=True).start()

    def release(self):
        """Gives the rate back (on switching off, or quitting: waits briefly, so it's done before the app goes)."""
        if self.rate:
            self.ask(0, wait=True)
