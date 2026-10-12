"""Debug info for bug reports: what it says, and what it keeps private."""
import logging
import os


def test_report_lists_versions_audio_and_log_without_personal_paths(qapp, tmp_path):
    from hallucinate import __version__, diagnostics
    from hallucinate.player import Player

    diagnostics.install()
    home = os.path.expanduser("~")
    logging.getLogger("hallucinate.test").warning("Could not read %s/Music/secret.flac", home)
    player = Player()
    try:
        text = diagnostics.report(player=player)
    finally:
        player.shutdown()
    assert text.startswith(f"Hallucinate {__version__}")
    for part in ("OS:", "PySide6", "Qt ", "Display:", "Audio output:", "Playback: ReplayGain", "Recent log"):
        assert part in text, part
    assert "~/Music/secret.flac" in text and home + "/" not in text  # the home folder (user name) is redacted


def test_shell_copies_debug_info(qapp):
    from PySide6.QtGui import QIcon

    from hallucinate.player import Player
    from hallucinate.shell import DesktopShell

    player = Player()
    shell = DesktopShell(qapp, player, QIcon())
    try:
        text = shell.copyDebugInfo()
        assert "Hallucinate" in text and qapp.clipboard().text() == text
        assert shell.appVersion
    finally:
        shell.shutdown()
        player.shutdown()


def test_update_check_is_opt_in_and_compares_versions(qapp):
    from conftest import wait_for
    from PySide6.QtCore import QSettings

    from hallucinate import updates

    assert updates.is_newer("v0.9.0", "0.8.0") and updates.is_newer("1.0", "0.9.9")
    assert not updates.is_newer("0.8.0", "0.8.0") and not updates.is_newer("garbage", "0.8.0")
    QSettings("hallucinate", "hallucinate").remove("updates")
    asked = []

    def fake_fetch():
        asked.append(1)
        return {"version": "99.0.0", "url": "https://example.invalid/release"}

    checker = updates.UpdateChecker(fetch=fake_fetch)
    try:
        assert not checker.enabled and not checker.available and asked == []  # off by default, nothing sent
        checker.setEnabled(True)  # turning it on checks straight away
        assert wait_for(lambda: not checker.busy and asked)
        assert checker.available and checker.latestVersion == "99.0.0"
        assert checker.status == "Hallucinate 99.0.0 is available"
        checker.setEnabled(False)
        assert not checker.enabled
    finally:
        checker.shutdown()
        QSettings("hallucinate", "hallucinate").remove("updates")


def test_flathub_manifest_uses_the_tagged_release(tmp_path, monkeypatch):
    import importlib.util
    import subprocess
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("flathub_manifest", Path(__file__).parents[1] / "scripts" / "flathub_manifest.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="ab" * 20 + "\n"))
    assert script.main(["v9.9.9", str(tmp_path)]) == 0
    text = (tmp_path / f"{script.APP_ID}.yml").read_text(encoding="utf-8")
    assert "type: dir" not in text and "path: ../.." not in text
    assert "tag: v9.9.9" in text and "commit: " + "ab" * 20 in text and "url: https://github.com/" in text
    assert (tmp_path / "python3-requirements.yaml").exists()
    assert script.main(["latest"]) == 2


def test_update_check_is_off_inside_flatpak(qapp, monkeypatch):
    from hallucinate import updates

    monkeypatch.setenv("FLATPAK_ID", "io.github.bulmaspanties.Hallucinate")
    checker = updates.UpdateChecker(fetch=lambda: {"version": "99.0.0", "url": "x"})
    try:
        assert not checker.supported
        checker.checkNow()
        assert not checker.busy and not checker.available
    finally:
        checker.shutdown()
