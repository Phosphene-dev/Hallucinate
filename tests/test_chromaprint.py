"""Fingerprints as Chromaprint makes them (core/chromaprint.py), and what AcoustID's answers are made into
(core/acoustid.py)."""
import shutil
import subprocess
import wave

import numpy as np
import pytest

from hallucinate.core import acoustid, chromaprint

# fpcalc 1.5.1's fingerprint of song() below (20 seconds, 44.1 kHz mono)
FPCALC = "AQAAjFIqLXbQU8IoqQ_opMfTB7tZeJQyJM81Ie8iRqj-YsqPK5Uk_InAZ9geJcTzIjliPsa5E2VoXIbrD33DBdGVH8kDJg93lHGJd7iTHVz2CGKTLD8uYw9l_CizdYfDqETSTGqO3Am8H2V2_D8ahUcyKY6RZ8exB3eO5kkQMruiIKksXB6eRHODfw0-oueDhsM_JF6SIT1OfIoC5nmCRstHPFEe_EEeiOexL8cXJccfhHlGPEoyVEpk4Bb-JLhyBWdmJN4RK8txHj_hxk7wC8NRZRuJKVOmMMP34BWao2uWEW94_BsuHz_CexCP8AnO4rsw8yD5YjqNIz3kHVey4MkH8SHy46KU40l0XF_gHyeDPEuhPwht6tgThkvwC_SDlseUiAme43gu1Dr84xmDH32CK0klPFMsVAnDoyeSvggJN-GNVwAJmCAGCIAAoEgZAgADiwAmgCCAC0GAUAAwRwQglgABhACIMWoUc4IQAawQyEBHBWEEEccFEUBAppBgTjAAjCACCWbgQRIBYggUDBGgGEAKCEckEYxKARghCCBEBBNEEMcAICApIwAhQiEEBCMM"


def song(seconds=20, rate=44100, seed=7):
    """Twenty seconds of chords and a little noise, the same every time (numpy's generator is stable)."""
    rng = np.random.default_rng(seed)
    t = np.arange(rate * seconds) / rate
    sig = np.zeros_like(t)
    seg = rate // 2
    for i in range(seconds * 2):
        root = 220 * 2 ** (int(rng.integers(-3, 13)) / 12)
        s = slice(i * seg, (i + 1) * seg)
        for mult in (1, 1.26, 1.5, 2):
            for h in range(1, 5):
                sig[s] += 0.15 / h * np.sin(2 * np.pi * root * mult * h * t[s] + rng.random())
    sig += 0.02 * rng.standard_normal(len(sig))
    return (sig / np.abs(sig).max() * 0.8 * 32767).astype("<i2")


def test_the_fingerprint_is_chromaprints():
    algorithm, ref = chromaprint.decode(FPCALC)
    assert algorithm == chromaprint.ALGORITHM and len(ref) == 140
    mine = chromaprint.fingerprint(song() / 32768.0, 44100)
    assert len(mine) == len(ref)
    assert chromaprint.similarity(mine, ref) > 0.99
    # and encoded as fpcalc does: the same text for the same sub-fingerprints
    assert chromaprint.encode(ref) == FPCALC


def test_resampled_and_short_songs():
    s = song() / 32768.0
    at48 = np.interp(np.arange(int(len(s) * 48000 / 44100)) * (44100 / 48000), np.arange(len(s)), s)
    ref = chromaprint.decode(FPCALC)[1]
    assert chromaprint.similarity(chromaprint.fingerprint(at48, 48000), ref) > 0.95
    assert len(chromaprint.fingerprint(np.zeros(2000), 44100)) == 0  # (too short for a single frame)
    c = chromaprint.Collector()
    assert c.add(np.zeros((44100, 2), np.float32), 44100)  # (more, please)
    assert c.result() is None  # silence: no fingerprint


@pytest.mark.skipif(not shutil.which("fpcalc"), reason="fpcalc isn't installed")
def test_against_fpcalc_itself(tmp_path):
    path = tmp_path / "s.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(song(seed=3).tobytes())
    out = subprocess.run(["fpcalc", "-raw", str(path)], capture_output=True, text=True).stdout
    ref = [int(x) for x in out.split("FINGERPRINT=")[1].split(",")]
    assert chromaprint.similarity(chromaprint.fingerprint(song(seed=3) / 32768.0, 44100), ref) > 0.99


ANSWER = [{"id": "x", "score": 0.94, "recordings": [{
    "id": "rec-1", "title": "Lower Your Eyelids to Die With the Sun", "duration": 639,
    "artists": [{"id": "a", "name": "M83"}],
    "releasegroups": [
        {"id": "g1", "title": "Before the Dawn Heals Us", "type": "Album", "artists": [{"name": "M83"}],
         "releases": [{"id": "r1", "title": "Before the Dawn Heals Us", "date": {"year": 2005}, "medium_count": 1,
                       "mediums": [{"position": 1, "track_count": 15, "tracks": [{"id": "t", "position": 15}]}]}]},
        {"id": "g2", "title": "Best of Something", "type": "Album", "secondarytypes": ["Compilation"],
         "artists": [{"name": "Various Artists"}],
         "releases": [{"id": "r2", "title": "Best of Something", "date": {"year": 2003}, "medium_count": 2,
                       "mediums": [{"position": 2, "track_count": 12, "tracks": [{"id": "t2", "position": 3}]}]}]},
    ]}]}, {"id": "y", "score": 0.3, "recordings": [{"id": "rec-2", "title": "Something Else"}]}]


def test_acoustid_answers_become_tags():
    got = acoustid.candidates(ANSWER, duration=640)
    assert len(got) == 1  # (the weak match is left out)
    best = got[0]
    # the album of its own wins over the earlier compilation
    assert (best["title"], best["artist"], best["album"], best["album_artist"], best["year"], best["track_no"],
            best["disc_no"], best["score"]) == ("Lower Your Eyelids to Die With the Sun", "M83",
                                                "Before the Dawn Heals Us", "M83", 2005, 15, 1, 0.94)
    # the album it's tagged with now wins, though
    assert acoustid.candidates(ANSWER, album_hint="best of something")[0]["album"] == "Best of Something"
    # another length: an edit or a live take, not this recording
    assert acoustid.candidates(ANSWER, duration=300) == []


def test_acoustid_refusals(monkeypatch):
    import io
    import json
    import urllib.error

    def refuse(request, timeout=10, limit=0):
        raise urllib.error.HTTPError(request.full_url, 400, "Bad", {}, io.BytesIO(json.dumps(
            {"status": "error", "error": {"code": 4, "message": "invalid API key"}}).encode()))

    monkeypatch.setattr(acoustid.net, "urlopen", refuse)
    with pytest.raises(acoustid.AcoustIDError) as err:
        acoustid.lookup("bad", "AQAA", 200)
    assert err.value.code == 4
