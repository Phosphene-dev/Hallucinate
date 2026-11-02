"""AutoEQ's parametric profiles applied exactly: their own filters (magnitude and phase), switchable one by one,
under the 10-band equalizer, with only as much headroom taken as the correction needs."""
import json

import numpy as np
import pytest

PROFILE = """Preamp: -6.4 dB
Filter 1: ON LSC Fc 105 Hz Gain 6.2 dB Q 0.70
Filter 2: ON PK Fc 2900 Hz Gain -4.1 dB Q 2.50
Filter 3: ON PK Fc 6100 Hz Gain 3.0 dB Q 4.00
Filter 4: ON HSC Fc 10000 Hz Gain -3.0 dB Q 0.70
"""


def test_a_parametric_profile_keeps_its_filters():
    from hallucinate.headphones import profile

    p = profile(PROFILE)
    assert [f["type"] for f in p["filters"]] == ["LSC", "PK", "PK", "HSC"]
    assert p["filters"][1] == {"type": "PK", "fc": 2900.0, "gain": -4.1, "q": 2.5, "on": True}
    assert p["preamp"] == -6.4 and len(p["curve"]) > 100
    graphic = profile("GraphicEQ: 20 2.0; 1000 0.0; 20000 -3.0")
    assert graphic["filters"] == [] and graphic["curve"][0] == [20.0, 2.0]


def test_the_equalizer_applies_them_exactly(qapp):
    from hallucinate import eq
    from hallucinate.headphones import profile

    filters = profile(PROFILE)["filters"]
    rate = 48000
    h = eq.design_fir([0] * 10, rate, filters=filters)
    n = 1 << 17
    got, want = np.fft.rfft(h, n), eq.parametric_response(filters, rate, n)
    f = np.fft.rfftfreq(n, 1 / rate)
    band = (f > 20) & (f < 20000)
    diff_db = 20 * np.log10(np.abs(got[band])) - 20 * np.log10(np.abs(want[band]))
    assert np.ptp(diff_db) < 0.05  # the measured shape, not an approximation of it
    peak = 20 * np.log10(np.abs(want[band])).max()
    assert abs(diff_db.mean() + peak) < 0.05  # lowered by its largest boost (6.2 dB), no more
    # the phase is the filters' own (as Equalizer APO's), apart from the bands' constant delay
    delay = (eq.TAPS // 2)
    phase_err = np.angle(got[band] * np.exp(2j * np.pi * f[band] * delay / rate) / want[band])
    assert np.max(np.abs(phase_err)) < 0.02


def test_music_through_the_equalizer_comes_out_corrected(qapp):
    from hallucinate import eq
    from hallucinate.headphones import profile

    p = eq.EqProcessor()
    p.set_filters(profile(PROFILE)["filters"])
    p.configure(48000, 2)
    rate, secs = 48000, 2.0
    t = np.arange(int(rate * secs)) / rate
    tone = (0.25 * np.sin(2 * np.pi * 2900 * t)).astype(np.float32)  # right on the -4.1 dB peak
    x = np.repeat(tone[:, None], 2, axis=1)
    out = np.concatenate([p.process(b) for b in np.array_split(x, 37)])
    settled = out[rate // 2:, 0]
    want = abs(eq.parametric_response(profile(PROFILE)["filters"], rate, 1 << 16)[
        int(round(2900 / (rate / (1 << 16))))])
    level = np.sqrt(2) * np.std(settled) / 0.25
    headroom = 10 ** (-6.2 / 20)
    assert abs(20 * np.log10(level) - 20 * np.log10(want * headroom)) < 0.3


@pytest.fixture
def player(qapp, tmp_path):
    from hallucinate.player import Player

    p = Player(session_file=tmp_path / "s.json")
    yield p
    p.clearHeadphone()
    p.setEqEnabled(False)
    p.shutdown()


def test_filters_can_be_switched_off_one_by_one(player):
    from hallucinate.headphones import profile

    player.setHeadphoneProfile("HD 600", json.dumps(profile(PROFILE)))
    assert player.headphoneName == "HD 600" and len(player.headphoneFilters) == 4
    assert player.headphonePreamp == -6.4
    before = player.headphoneCurve
    player.setHeadphoneFilter(0, False)  # the bass shelf off
    assert player.headphoneFilters[0]["on"] is False
    after = player.headphoneCurve
    assert after[0][1] < before[0][1] - 4  # the drawn curve follows: no bass lift
    proc = player._voices[0].tap.processor if player._voices[0].tap is not None else None
    if proc is not None:
        assert proc.filters[0]["on"] is False


def test_profiles_kept_by_older_versions_and_broken_ones(player):
    player.setHeadphoneProfile("Old", json.dumps([[20, 3.0], [1000, 0.0], [20000, -2.0]]))
    assert player.headphoneName == "Old" and player.headphoneFilters == []
    bad = {"curve": [[20, 0.0], [20000, 0.0]], "filters": [{"type": "PK", "fc": 0, "gain": 3, "q": 1}]}
    player.setHeadphoneProfile("Broken", json.dumps(bad))
    assert player.headphoneName == "Old"  # a 0 Hz filter is refused; what was there stays
    player.setHeadphoneProfile("Nan", '{"curve": [[20, NaN], [20000, 0]]}')
    assert player.headphoneName == "Old"


def test_a_damaged_saved_profile_is_ignored():
    from hallucinate.player import _clean_headphone

    assert _clean_headphone("X", {"curve": [[20, 1], [20000, 1]], "filters": [{"type": "EVIL"}]}) is None
    assert _clean_headphone("", {"curve": [[20, 1], [20000, 1]]}) is None
    ok = _clean_headphone("X", {"curve": [[20, 1], [20000, 1]], "filters": [
        {"type": "PK", "fc": 1000, "gain": 2, "q": 1}]})
    assert ok["filters"][0]["on"] is True
