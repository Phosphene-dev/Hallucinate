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
