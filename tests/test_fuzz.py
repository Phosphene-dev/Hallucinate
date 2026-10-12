"""Broken and hostile files: every parser either reads them or fails in its usual, handled way, quickly.

Inputs are random and mutated real files from a fixed seed, so a failure always reproduces."""
import json
import random
import time

import pytest
from conftest import make_mp3

from hallucinate.core import cue, lyrics, player_import, playlist_files, tags

SEED = 20261012


def mutations(seed_bytes, n, rng):
    """Random byte strings plus flipped, truncated, duplicated and spliced versions of seed_bytes."""
    yield b""
    for _ in range(n):
        data = bytearray(seed_bytes)
        kind = rng.randrange(5)
        if kind == 0 or not data:
            yield bytes(rng.randrange(256) for _ in range(rng.randrange(1, 600)))
            continue
        if kind == 1:
            for _ in range(rng.randrange(1, 20)):
                data[rng.randrange(len(data))] = rng.randrange(256)
        elif kind == 2:
            del data[rng.randrange(len(data)):]
        elif kind == 3:
            i = rng.randrange(len(data))
            data[i:i] = data[i:i + rng.randrange(1, 200)] * rng.randrange(1, 50)
        else:
            i = rng.randrange(len(data))
            data[i:i] = bytes(rng.randrange(256) for _ in range(rng.randrange(1, 100)))
        yield bytes(data)


def timed(fn, *args):
    t0 = time.perf_counter()
    result = fn(*args)
    assert time.perf_counter() - t0 < 2, "a single malformed input took over 2 s"
    return result


CUE = """REM GENRE Rock
PERFORMER "Band"
TITLE "Album"
FILE "album.flac" WAVE
  TRACK 01 AUDIO
    TITLE "One"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "Two"
    INDEX 00 03:58:70
    INDEX 01 04:00:00
"""


def test_text_parsers_never_raise():
    rng = random.Random(SEED)
    samples = {
        cue.parse: CUE,
        lyrics.parse_lrc: "[ar:x]\n[offset:+250]\n[00:01.00]one\n[00:02.50][00:05.00]two\n",
        (lambda t: playlist_files.parse_m3u(t, "/music")): "#EXTM3U\n#EXTINF:120,Band - Song\nsong.mp3\n",
        (lambda t: playlist_files.parse_pls(t, "/music")): "[playlist]\nFile1=a.mp3\nTitle1=A\nNumberOfEntries=1\n",
    }
    for parse, sample in samples.items():
        for data in mutations(sample.encode(), 300, rng):
            timed(parse, data.decode("utf-8", "replace"))


def test_tag_reader_returns_none_for_junk(tmp_path):
    rng = random.Random(SEED)
    make_mp3(tmp_path / "seed.mp3", "Title", "Artist", "Album", "Artist", "1/9")
    seed = (tmp_path / "seed.mp3").read_bytes()
    for ext in (".mp3", ".flac", ".ogg", ".m4a", ".opus", ".wav", ".ape", ".wv"):
        for n, data in enumerate(mutations(seed, 40, rng)):
            path = tmp_path / f"f{n}{ext}"
            path.write_bytes(data)
            result = timed(tags.read_track, str(path))  # the scanner relies on: a row or None, never an error
            assert result is None or isinstance(result, dict)
            path.unlink()


def test_cue_sheet_files_never_break_reading(tmp_path):
    rng = random.Random(SEED)
    for n, data in enumerate(mutations(CUE.encode("utf-8"), 100, rng)):
        path = tmp_path / f"s{n}.cue"
        path.write_bytes(data)
        timed(cue.read, str(path))


HANDLED = (ValueError, OSError)  # what the import screen reports as a readable message


def test_player_imports_fail_cleanly(tmp_path):
    """Whatever file is picked in "Import from another player", the import either works or reports a problem."""
    rng = random.Random(SEED)
    rhythmbox = (b'<?xml version="1.0"?><rhythmdb version="2.0"><entry type="song"><title>T</title>'
                 b"<artist>A</artist><location>file:///m/a.mp3</location><play-count>3</play-count></entry></rhythmdb>")
    plist = (b'<?xml version="1.0"?><!DOCTYPE plist><plist version="1.0"><dict><key>Tracks</key><dict><key>1</key>'
             b"<dict><key>Location</key><string>file:///m/a.mp3</string><key>Play Count</key><integer>2</integer>"
             b"</dict></dict></dict></plist>")
    for seed in (rhythmbox, plist):
        for n, data in enumerate(mutations(seed, 120, rng)):
            path = tmp_path / f"lib{n}.xml"
            path.write_bytes(data)
            try:
                result = timed(player_import.read, str(path))
            except HANDLED:
                continue
            assert isinstance(result, dict) and isinstance(result["songs"], list)


def test_xml_entity_bombs_are_refused(tmp_path):
    bomb = ['<?xml version="1.0"?><!DOCTYPE rhythmdb [<!ENTITY a "aaaaaaaaaa">']
    for i in range(1, 10):
        bomb.append(f'<!ENTITY {chr(97 + i)} "' + f"&{chr(96 + i)};" * 10 + '">')
    bomb.append(']><rhythmdb><entry type="song"><title>&j;</title></entry></rhythmdb>')
    path = tmp_path / "bomb.xml"
    path.write_text("".join(bomb))
    with pytest.raises(HANDLED):
        timed(player_import.read, str(path))
    plist = path.with_name("bomb.plist")
    plist.write_text('<?xml version="1.0"?><!DOCTYPE plist [<!ENTITY a "x">]><plist><dict><key>Tracks</key>'
                     "<string>&a;</string></dict></plist>")
    with pytest.raises(HANDLED):
        timed(player_import.read, str(plist))


def test_themes_reject_garbage(tmp_path):
    from hallucinate.themes import ThemeManager

    _validate = ThemeManager._validate

    rng = random.Random(SEED)
    good = json.dumps({"name": "T", "bg": "#101010", "panel": "#202020", "surface": "#303030", "text": "#ffffff",
                       "textDim": "#aaaaaa", "accent": "#ff00ff", "palette": ["#ff0000", "#00ff00"]}).encode()
    for data in mutations(good, 300, rng):
        try:
            value = json.loads(data.decode("utf-8", "replace"))
        except ValueError:
            continue
        try:
            timed(_validate, value)
        except (ValueError, TypeError, KeyError):
            pass


@pytest.mark.parametrize("junk", [b"", b"\x00\xff garbage", b"{", b"[]", b'{"queue": "not a list", "index": "x"}',
                                  b'{"queue": [{"path": 5}], "index": 99, "volume": "loud"}'])
def test_damaged_state_files_dont_stop_start_up(qapp, tmp_path, junk):
    """A corrupt session (queue, position, volume) or scrobble queue is ignored, not fatal."""
    from hallucinate import scrobbling
    from hallucinate.listenbrainz import ListenBrainzScrobbler
    from hallucinate.player import Player

    for name in ("get_password", "set_password", "delete_password"):
        setattr(scrobbling.keyring, name, lambda *_: None)
    (tmp_path / "session.json").write_bytes(junk)
    (tmp_path / "lastfm-scrobbles.json").write_bytes(junk)
    (tmp_path / "listenbrainz-listens.json").write_bytes(junk)
    player = Player(session_file=tmp_path / "session.json")
    lastfm = scrobbling.LastFmScrobbler(player, tmp_path)
    lb = ListenBrainzScrobbler(player, tmp_path)
    try:
        assert isinstance(player.queue, list)
    finally:
        for obj in (lb, lastfm, player):
            if hasattr(obj, "shutdown"):
                obj.shutdown()
