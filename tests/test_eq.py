import numpy as np
import pytest

from hallucinate import eq

RATE = 44100


def sine(freq, seconds=1.0, ch=2):
    t = np.arange(int(RATE * seconds)) / RATE
    return np.repeat((0.2 * np.sin(2 * np.pi * freq * t))[:, None], ch, axis=1).astype(np.float32)


def level(x):
    return float(np.sqrt(np.mean(x[RATE // 4:-RATE // 4] ** 2)))


def run(gains, x, chunk=4096):
    p = eq.EqProcessor()
    p.configure(RATE, x.shape[1])
    p.set_gains(gains)
    return np.concatenate([p.process(x[i:i + chunk]) for i in range(0, len(x), chunk)])


def gains_with(band, db):
    g = [0.0] * 10
    g[band] = db
    return g


@pytest.mark.parametrize("freq,band", [(125, 2), (1000, 5), (8000, 8)])
def test_band_boost_and_cut(freq, band):
    x = sine(freq)
    base = level(x)
    boosted = level(run(gains_with(band, 9), x)) / base
    cut = level(run(gains_with(band, -9), x)) / base
    assert 2.4 < boosted < 3.4  # +9 dB = 2.8x
    assert 0.25 < cut < 0.45  # -9 dB = 0.355x


def test_other_bands_unaffected_and_flat_is_transparent():
    x = sine(1000)
    assert level(run(gains_with(0, 12), x)) / level(x) == pytest.approx(1.0, abs=0.08)
    assert level(run([0.0] * 10, x)) / level(x) == pytest.approx(1.0, abs=0.03)


def test_chunking_is_seamless():
    x = sine(440, 0.5)
    g = gains_with(4, 6)
    a, b = run(g, x, 1024), run(g, x, 7000)
    assert np.allclose(a, b, atol=1e-4)


def test_mono_and_presets_valid():
    assert run(gains_with(5, 6), sine(1000, 0.3, ch=1)).shape == (int(RATE * 0.3), 1)
    assert all(len(v) == len(eq.BANDS) for v in eq.PRESETS.values())


def test_crossfeed_mixes_a_softened_copy_of_the_other_channel():
    import numpy as np

    from hallucinate import eq

    rate = 44100
    t = np.arange(rate) / rate
    low = np.sin(2 * np.pi * 200 * t).astype(np.float32)
    high = np.sin(2 * np.pi * 8000 * t).astype(np.float32)
    cf = eq.Crossfeed("medium", rate)

    def run(left, right):
        x = np.stack([left, right], axis=1)
        out = np.concatenate([cf.process(x[i:i + 1024]) for i in range(0, len(x), 1024)])  # streamed in blocks
        cf.reset()
        return out

    bass = run(low, np.zeros_like(low))  # bass hard left: some reaches the right ear
    treble = run(high, np.zeros_like(high))  # treble hard left: hardly any does
    rms = lambda a: float(np.sqrt(np.mean(a[2000:] ** 2)))  # noqa: E731
    assert rms(bass[:, 1]) / rms(bass[:, 0]) == pytest.approx(10 ** (-6 / 20), rel=0.12)
    assert rms(treble[:, 1]) / rms(treble[:, 0]) < 0.08
    centre = run(low, low)  # a centred sound stays within 1 dB of its level
    assert 10 ** (-1 / 20) < rms(centre[:, 0]) / rms(low) <= 1.0
    assert np.allclose(cf.process(np.zeros((0, 2), np.float32)), 0)


def test_player_crossfeed_setting(qapp):
    from hallucinate import eq
    from hallucinate.player import Player

    player = Player()
    try:
        player.setEqEnabled(False)
        player.setCrossfeed("strong")
        assert player.crossfeed == "strong"
        assert all(v.tap is not None for v in player._voices)  # processing runs for crossfeed alone
        processor = player._voices[0].tap.processor
        assert not processor.eq_on and processor.eq_flat and processor.crossfeed.preset == "strong"
        player.setCrossfeed("nonsense")
        assert player.crossfeed == "off" and all(v.tap is None for v in player._voices)
        assert player.crossfeedPresets == ["off", *eq.CROSSFEED]
    finally:
        player.setCrossfeed("off")
        player.shutdown()


def test_equalizer_settings_follow_the_output_device(qapp, tmp_path, monkeypatch):
    from hallucinate import eq as eq_module
    from hallucinate import player as player_module

    if not eq_module.available():
        import pytest

        pytest.skip("needs numpy")
    current = {"key": "speakers"}
    monkeypatch.setattr(player_module.Player, "_current_device_key", lambda self: current["key"])
    p = player_module.Player(session_file=None)
    try:
        p.setEqPerDevice(True)
        p.setEqEnabled(True)
        p.setEqBand(0, 6.0)
        current["key"] = "headphones"  # the sound moves to headphones: a new device starts from what was in use
        p._switch_device_eq()
        p.setEqBand(0, -3.0)
        p.setEqEnabled(False)
        current["key"] = "speakers"
        p._switch_device_eq()
        assert p.eqEnabled and p.eqGains[0] == 6.0
        current["key"] = "headphones"
        p._switch_device_eq()
        assert not p.eqEnabled and p.eqGains[0] == -3.0
        p.setEqPerDevice(False)
    finally:
        p.shutdown()
