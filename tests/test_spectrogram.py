"""The spectrum analyzer (#96): a song's spectrogram, decoded in the helper process and drawn as Spek does."""
import numpy as np
import pytest
from audio import encode
from conftest import wait_for

from hallucinate import spectrogram as sg


def test_a_tone_lands_in_its_frequency_row():
    acc = sg.Accumulator()
    rate = 44100
    t = np.arange(rate * 2) / rate
    tone = (0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    for chunk in np.array_split(np.stack([tone, tone], axis=1), 7):  # in buffers, as the decoder hands them
        acc.add(chunk, rate)
    got = acc.result()
    cols = got["columns"]
    assert got["rate"] == rate and got["channels"] == 2 and cols.shape == (rate * 2 // sg.FFT, sg.ROWS)
    row = int(np.argmax(cols.mean(axis=0)))
    hz = (row + 0.5) * (rate / 2) / sg.ROWS
    assert abs(hz - 1000) < 60  # the 1 kHz tone, in its row
    assert cols[:, row].min() > 200 and cols[:, -50:].max() < 60  # loud there, near silence high up


def test_columns_fit_any_width():
    cols = np.arange(10, dtype=np.uint8)[:, None].repeat(sg.ROWS, axis=1)
    assert sg.fit_columns(cols, 5)[:, 0].tolist() == [1, 3, 5, 7, 9]  # the loudest of each pair
    assert sg.fit_columns(cols, 20).shape == (20, sg.ROWS)
    assert sg.fit_columns(np.zeros((0, sg.ROWS), np.uint8), 4).shape == (4, sg.ROWS)


def test_the_image_has_its_scales(qapp):
    cols = np.full((300, sg.ROWS), 128, np.uint8)
    image = sg.render(cols, 44100, "Artist – Song", "FLAC  ·  44.1 kHz  ·  16-bit", width=400, height=200)
    assert image.width() == sg.LEFT + 400 + sg.RIGHT and image.height() == sg.TOP + 200 + sg.BOTTOM
    assert image.pixelColor(sg.LEFT + 200, sg.TOP + 100).name() != "#0b0b10"  # the plot is drawn


def test_a_song_is_analysed_saved_and_kept(qapp, tmp_path, monkeypatch):
    from hallucinate.core import paths
    from hallucinate.core.db import Database

    song = encode(tmp_path / "s.flac", "flac", seconds=4, title="Tone", artist="Sine")
    from hallucinate.core import tags

    db = Database(tmp_path / "library.db")
    db.upsert_track(tags.read_track(str(song)))
    db.commit()
    db.close()
    monkeypatch.setattr(paths, "pictures_dir", lambda: tmp_path / "Pictures" / "Hallucinate")
    spec = sg.Spectrograms(tmp_path / "library.db", tmp_path / "cache")
    try:
        spec.open(str(song))
        assert spec.busy
        assert wait_for(lambda: not spec.busy, timeout=60), "never finished"
        assert spec.error == "" and spec.imageUrl.startswith("file://")
        assert spec.title == "Sine – Tone" and "44.1 kHz" in spec.details and "stereo" in spec.details
        saved = spec.save()
        assert saved.endswith("Sine – Tone (spectrogram).png") and (tmp_path / "Pictures" / "Hallucinate").is_dir()
        spec.open(str(song))  # again: from the cache, at once
        assert not spec.busy and spec.imageUrl
        spec.open("subsonic://server/1")
        assert spec.error and not spec.imageUrl
    finally:
        spec.shutdown()


@pytest.mark.parametrize("bad", ["missing.flac"])
def test_a_file_that_cant_be_decoded_says_so(qapp, tmp_path, bad):
    (tmp_path / bad).write_bytes(b"not audio at all")
    spec = sg.Spectrograms(tmp_path / "library.db", tmp_path / "cache")
    try:
        spec.open(str(tmp_path / bad))
        assert wait_for(lambda: not spec.busy, timeout=60)
        assert spec.error and not spec.imageUrl
    finally:
        spec.shutdown()
