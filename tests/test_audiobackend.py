"""Qt Multimedia crashed on start when the PipeWire client library was installed with no PipeWire server running
(a server, a container, an LXC): it's told to use PulseAudio then."""
from hallucinate import audiobackend


def test_no_pipewire_server_means_pulseaudio(tmp_path):
    env = {"XDG_RUNTIME_DIR": str(tmp_path)}
    assert audiobackend.choose(env, "linux") == "pulseaudio" and env["QT_AUDIO_BACKEND"] == "pulseaudio"


def test_a_running_pipewire_is_left_to_qt(tmp_path):
    (tmp_path / "pipewire-0").touch()
    env = {"XDG_RUNTIME_DIR": str(tmp_path)}
    assert audiobackend.choose(env, "linux") == "" and "QT_AUDIO_BACKEND" not in env
    env = {"PIPEWIRE_REMOTE": str(tmp_path / "pipewire-0")}  # a socket named by its full path
    assert audiobackend.pipewire_running(env)


def test_your_own_choice_and_other_systems_are_left_alone(tmp_path):
    env = {"XDG_RUNTIME_DIR": str(tmp_path), "QT_AUDIO_BACKEND": "alsa"}
    assert audiobackend.choose(env, "linux") == "alsa"
    env = {}
    assert audiobackend.choose(env, "win32") == "" and env == {}


def test_starting_with_the_library_but_no_server_doesnt_crash(tmp_path):
    """The real thing, in a fresh process: importing Hallucinate first, then listing the sound outputs."""
    import os
    import subprocess
    import sys

    code = ("import hallucinate, sys\nfrom PySide6.QtWidgets import QApplication\napp = QApplication(sys.argv)\n"
            "from PySide6.QtMultimedia import QMediaDevices\nQMediaDevices().audioOutputs()\nprint('ok')")
    env = {k: v for k, v in os.environ.items() if k not in ("QT_AUDIO_BACKEND", "PIPEWIRE_REMOTE")}
    env.update(QT_QPA_PLATFORM="offscreen", XDG_RUNTIME_DIR=str(tmp_path),
               PYTHONPATH=os.path.dirname(os.path.dirname(os.path.abspath(audiobackend.__file__))))
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr[-1500:]
