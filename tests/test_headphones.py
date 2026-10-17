"""Headphone correction: AutoEQ files become a curve, the index is searchable, the EQ applies the curve."""
import json

import numpy as np
import pytest

from hallucinate import eq, headphones

PARAMETRIC = """Preamp: -6.3 dB
Filter 1: ON LSC Fc 105 Hz Gain 6.5 dB Q 0.70
Filter 2: ON PK Fc 1000 Hz Gain -3.0 dB Q 1.41
Filter 3: ON HSC Fc 10000 Hz Gain 2.0 dB Q 0.70
"""
GRAPHIC = "GraphicEQ: 20 -4.0; 1000 0.0; 20000 3.5"
INDEX = """# Index
- [Sennheiser HD 600](./oratory1990/over-ear/Sennheiser%20HD%20600) by oratory1990
- [Sennheiser HD 600](./crinacle/GRAS%2043AG-7%20over-ear/Sennheiser%20HD%20600) by crinacle on GRAS 43AG-7
- [Sennheiser HD 650](./oratory1990/over-ear/Sennheiser%20HD%20650) by oratory1990
- [Sony WH-1000XM4](./oratory1990/over-ear/Sony%20WH-1000XM4) by oratory1990
"""


def at(curve, f):
    fs, gs = zip(*curve)
    return float(np.interp(np.log10(f), np.log10(fs), gs))


def test_parametric_profile_becomes_a_curve():
    curve = headphones.parse(PARAMETRIC)
    assert len(curve) == headphones.CURVE_POINTS and curve[0][0] == 20 and curve[-1][0] == pytest.approx(20000)
    assert at(curve, 20) == pytest.approx(6.5, abs=0.4)    # low shelf
    assert at(curve, 1000) == pytest.approx(-3.0, abs=0.4)  # peak cut
    assert at(curve, 18000) == pytest.approx(2.0, abs=0.4)  # high shelf


def test_graphic_profile_and_bad_files():
    assert headphones.parse(GRAPHIC) == [[20.0, -4.0], [1000.0, 0.0], [20000.0, 3.5]]
    with pytest.raises(ValueError):
        headphones.parse("hello")


def test_index_and_search():
    entries = headphones.parse_index(INDEX)
    assert len(entries) == 4 and entries[1]["source"] == "crinacle on GRAS 43AG-7"
    assert entries[0]["path"] == "oratory1990/over-ear/Sennheiser HD 600"
    names = [e["name"] for e in headphones.search(entries, "hd 6")]
    assert names == ["Sennheiser HD 600", "Sennheiser HD 600", "Sennheiser HD 650"]
    assert headphones.search(entries, "xm4")[0]["name"] == "Sony WH-1000XM4" and headphones.search(entries, " ") == []
    assert headphones.profile_url(entries[0]).endswith(
        "oratory1990/over-ear/Sennheiser%20HD%20600/Sennheiser%20HD%20600%20ParametricEQ.txt")


def test_eq_adds_the_curve_without_clipping():
    curve = [[20, 6.0], [1000, 0.0], [20000, 0.0]]
    h = eq.design_fir([0] * 10, 48000, curve=curve)
    spectrum = np.abs(np.fft.rfft(h, 65536))
    freqs = np.fft.rfftfreq(65536, 1 / 48000)

    def db(f):
        return 20 * np.log10(spectrum[np.argmin(np.abs(freqs - f))])

    assert db(1000) == pytest.approx(-6.0, abs=0.5)  # lowered by the largest boost…
    assert db(40) - db(1000) == pytest.approx(5.2, abs=0.8)  # …while keeping the shape
    assert db(1000) < 0.1 and max(db(f) for f in (30, 100, 1000, 10000)) <= 0.3
    proc = eq.EqProcessor()
    assert proc.flat
    proc.set_curve(curve)
    assert not proc.flat


def test_player_keeps_the_headphone_profile(qapp, tmp_path):
    from hallucinate.player import Player

    curve = headphones.parse(GRAPHIC)
    player = Player(session_file=tmp_path / "s.json")
    try:
        player.setHeadphoneProfile("Test Phones", json.dumps(curve))
        assert player.headphoneName == "Test Phones" and player.eqEnabled == eq.available()
        player.setHeadphoneProfile("Broken", "not json")
        assert player.headphoneName == "Test Phones"
    finally:
        player.shutdown()
    again = Player(session_file=tmp_path / "s2.json")
    try:
        assert again.headphoneName == "Test Phones" and again.headphoneCurve == curve
        again.clearHeadphone()
        assert again.headphoneName == "" and again.headphoneCurve == []
    finally:
        again.setEqEnabled(False)  # settings persist between tests
        again.shutdown()


def test_finder_imports_files(qapp, tmp_path):
    from hallucinate.player import Player

    player = Player(session_file=tmp_path / "s.json")
    finder = headphones.HeadphoneFinder(tmp_path / "cache", player)
    try:
        good = tmp_path / "My Phones ParametricEQ.txt"
        good.write_text(PARAMETRIC)
        assert finder.importFile(good.as_uri()) == "" and player.headphoneName == "My Phones"
        bad = tmp_path / "notes.txt"
        bad.write_text("nothing here")
        assert finder.importFile(str(bad)) and player.headphoneName == "My Phones"
    finally:
        finder.shutdown()
        player.clearHeadphone()
        player.setEqEnabled(False)
        player.shutdown()


@pytest.mark.parametrize("text", [
    "GraphicEQ: 20 nan; 1000 0",
    "GraphicEQ: 20 inf; 1000 0",
    "Filter 1: ON PK Fc 0 Hz Gain 3 dB Q 1",
    "Filter 1: ON PK Fc 100 Hz Gain 3 dB Q 0",
    "Filter 1: ON PK Fc 100 Hz Gain 900 dB Q 1",
])
def test_broken_eq_files_are_refused(text):
    from hallucinate import headphones

    with pytest.raises(ValueError):
        headphones.parse(text)
