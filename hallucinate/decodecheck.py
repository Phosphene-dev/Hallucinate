"""Check that Qt Multimedia can decode audio files: hallucinate --decode-check FILE...

The packaged builds run this in CI on clips of every format, since their codecs come from what the package
carries (PySide6's FFmpeg in the AppImage, Windows and macOS builds; the runtime in the Flatpak). Each file
passes once at least half a second of PCM has been decoded. The exit code says whether all of them did."""
import sys

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtMultimedia import QAudioBufferOutput, QMediaPlayer

NEEDED_SECONDS = 0.5
TIMEOUT_MS = 15_000


def decoded_seconds(path):
    player = QMediaPlayer()
    output = QAudioBufferOutput()
    player.setAudioBufferOutput(output)
    decoded = {"seconds": 0.0}
    errors = []

    def on_buffer(buffer):
        rate = buffer.format().sampleRate()
        if rate > 0:
            decoded["seconds"] += buffer.frameCount() / rate

    output.audioBufferReceived.connect(on_buffer)
    player.errorOccurred.connect(lambda _error, text: errors.append(text))
    player.setSource(QUrl.fromLocalFile(path))
    player.play()
    timer = QElapsedTimer()
    timer.start()
    while decoded["seconds"] < NEEDED_SECONDS and not errors and timer.elapsed() < TIMEOUT_MS:
        QCoreApplication.processEvents()
        QCoreApplication.instance().thread().msleep(10)
    player.stop()
    return decoded["seconds"], "; ".join(errors)


def main(paths):
    app = QGuiApplication.instance() or QGuiApplication([sys.argv[0]])  # noqa: F841 - keeps it alive
    failed = False
    for path in paths:
        seconds, error = decoded_seconds(path)
        ok = seconds >= NEEDED_SECONDS
        failed |= not ok
        detail = f"error: {error}" if error else f"{seconds:.2f} s decoded"
        if sys.stdout is not None:  # the Windows build has no console
            print(f"{'ok  ' if ok else 'FAIL'} {path}: {detail}", flush=True)
    if paths:
        ok, detail = helper_works(paths[0])
        failed |= not ok
        if sys.stdout is not None:
            print(f"{'ok  ' if ok else 'FAIL'} analysis helper: {detail}", flush=True)
    return 1 if failed else 0


def helper_works(path):
    """Whether this build can start its analysis helper (analysis.py) and have it measure a song."""
    from .analysis import Analyser

    analyser, got = Analyser(), []
    analyser.submit(path, "loudness", got.append)
    timer = QElapsedTimer()
    timer.start()
    while not got and timer.elapsed() < TIMEOUT_MS * 2:
        QCoreApplication.processEvents()
        QCoreApplication.instance().thread().msleep(10)
    analyser.shutdown()
    result = got[0] if got else None
    if not result or result.get("silent"):
        return False, "no answer" if not got else "couldn't measure the song"
    return True, f"measured {result['loudness']:.1f} LUFS"


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
