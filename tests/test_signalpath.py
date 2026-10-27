"""The signal path readout: which stages change the sound, and when it is untouched."""
from hallucinate.signalpath import describe

FLAC = {"codec": "FLAC", "sample_rate": 44100, "bitrate": 900_000}


def names(path, active=True):
    return [s["name"] for s in path["stages"] if s["active"] == active]


def test_untouched_when_nothing_processes():
    path = describe(FLAC, device_name="DAC", device_rate=44100)
    assert path["untouched"] and path["summary"] == "Untouched" and names(path) == []
    assert path["stages"][0]["detail"] == "FLAC  ·  44.1 kHz  ·  lossless"
    assert path["stages"][-1]["detail"] == "DAC  ·  44.1 kHz"


def test_each_stage_that_changes_the_sound():
    path = describe(FLAC, rg_factor=0.5, rg_mode="album", volume=0.6, speed=1.25, eq_enabled=True,
                    eq_preset="Bass", crossfade=4, device_name="Speakers", device_rate=48000)
    assert not path["untouched"]
    assert names(path) == ["ReplayGain", "Equalizer", "Speed", "Volume", "Output"]
    details = {s["name"]: s["detail"] for s in path["stages"]}
    assert details["ReplayGain"] == "Album gain -6.0 dB" and details["Equalizer"] == "Bass"
    assert details["Speed"] == "1.25×" and details["Volume"] == "60%" and details["Crossfade"] == "4 s between tracks"
    assert details["Output"] == "Speakers  ·  48 kHz (resampled from 44.1 kHz)"
    assert path["summary"] == "Changed by replaygain, equalizer, speed, volume, resampling"


def test_lossy_source_and_untagged_replaygain():
    path = describe({"codec": "MP3", "sample_rate": 48000, "bitrate": 320_000}, rg_mode="track", device_rate=48000)
    assert path["stages"][0]["detail"] == "MP3  ·  48 kHz  ·  320 kbps"
    assert path["stages"][1]["detail"] == "Track gain: none tagged" and path["untouched"]
    assert describe(None)["stages"] == []


def test_player_exposes_signal_path(qapp, tmp_path):
    from hallucinate.player import Player

    player = Player(session_file=tmp_path / "s.json")
    try:
        assert player.signalPath["stages"] == []
        seen = []
        player.signalPathChanged.connect(lambda: seen.append(1))
        player.setSpeed(1.5)
        assert seen
    finally:
        player.shutdown()


def test_it_says_why_and_what_would_leave_the_sound_untouched():
    """A tester saw "Processed" with speed, equalizer and ReplayGain off: a 48 kHz output resamples a 44.1 kHz
    song, and a volume under 100% scales it. The popup says so in plain words."""
    path = describe(FLAC, volume=0.8, device_name="HD Audio", device_rate=48000)
    assert names(path) == ["Volume", "Output"]
    resample, volume = path["advice"]
    assert "48 kHz" in resample and "44.1 kHz" in resample and "PipeWire" in resample
    assert "80%" in volume and "100%" in volume
    assert describe(FLAC, device_rate=44100)["advice"] == []


def test_pipewire_switching_to_the_song_s_rate_is_untouched(tmp_path):
    """The tester's PipeWire allows 44100 and 48000: a 44.1 kHz FLAC isn't resampled to the 48 kHz the device
    reports, PipeWire switches the output to it."""
    from hallucinate import signalpath

    path = describe(FLAC, device_name="DAC", device_rate=48000, rate_follows=True, rate_source="PipeWire")
    assert path["untouched"] and path["stages"][-1]["detail"] == "DAC  ·  44.1 kHz (switched by PipeWire)"
    assert "nothing else is playing" in " ".join(path["advice"])
    fixed = describe(FLAC, device_name="DAC", device_rate=48000)
    assert not fixed["untouched"] and "Output sample rate" in " ".join(fixed["advice"])

    assert signalpath.output_follows(44100, "follows") and not signalpath.output_follows(44100, "fixed")
    assert signalpath.output_follows(44100, "auto", frozenset({44100, 48000}))
    assert not signalpath.output_follows(88200, "auto", frozenset({44100, 48000}))
    assert not signalpath.output_follows(44100, "auto", frozenset({48000}))  # one rate: it never switches


def test_allowed_rates_from_pipewire(tmp_path):
    from hallucinate import signalpath

    runtime = tmp_path / "run"
    runtime.mkdir()
    env = {"HOME": str(tmp_path), "XDG_RUNTIME_DIR": str(runtime)}

    class Done:
        def __init__(self, out):
            self.stdout = out

    def no_tool(*_a, **_k):
        raise FileNotFoundError("pw-metadata")

    assert signalpath.pipewire_allowed_rates(env, run=no_tool) == frozenset()  # PipeWire isn't running
    (runtime / "pipewire-0").write_text("")
    assert signalpath.pipewire_allowed_rates(env, run=no_tool) == frozenset()  # nothing set: one rate
    live = "Found \"settings\" metadata 31\nupdate: id:0 key:'clock.allowed-rates' value:'[ 44100 48000 96000 ]' type:''\n"
    assert signalpath.pipewire_allowed_rates(env, run=lambda *_a, **_k: Done(live)) == {44100, 48000, 96000}
    conf = tmp_path / ".config" / "pipewire" / "pipewire.conf.d"
    conf.mkdir(parents=True)
    (conf / "10-rates.conf").write_text(
        "context.properties = {\n  # default.clock.allowed-rates = [ 48000 ]\n"
        "  default.clock.allowed-rates = [ 44100, 48000, 88200, 96000 ]\n}\n")
    assert signalpath.pipewire_allowed_rates(env, run=no_tool) == {44100, 48000, 88200, 96000}
