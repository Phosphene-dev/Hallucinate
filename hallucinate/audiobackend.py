"""Which sound system Qt Multimedia talks to on Linux.

Qt picks its PipeWire backend whenever the PipeWire client library is installed, even when no PipeWire server is
running, and then crashes on start (seen with Qt 6.12 on a headless server and in containers, where other
packages bring the library in). When no PipeWire server can be reached, use PulseAudio instead: it plays through
a PulseAudio server (or PipeWire's) and starts cleanly with no sound server at all. Someone who set
QT_AUDIO_BACKEND themselves keeps their choice."""
import os
import sys


def pipewire_running(env=None):
    env = os.environ if env is None else env
    remote = env.get("PIPEWIRE_REMOTE") or "pipewire-0"
    if os.path.isabs(remote):
        return os.path.exists(remote)
    for folder in (env.get("PIPEWIRE_RUNTIME_DIR"), env.get("XDG_RUNTIME_DIR"), env.get("USERPROFILE")):
        if folder and os.path.exists(os.path.join(folder, remote)):
            return True
    return False


def choose(env=None, platform=None):
    """Set QT_AUDIO_BACKEND before Qt Multimedia loads; returns what was chosen ("" for Qt's own choice)."""
    env = os.environ if env is None else env
    if not (platform or sys.platform).startswith("linux") or "QT_AUDIO_BACKEND" in env:
        return env.get("QT_AUDIO_BACKEND", "")
    if pipewire_running(env):
        return ""
    env["QT_AUDIO_BACKEND"] = "pulseaudio"
    return "pulseaudio"
