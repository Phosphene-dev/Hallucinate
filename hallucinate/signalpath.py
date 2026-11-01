"""What happens to the sound between the file and the speakers, for the signal path readout.

`describe` is pure so it can be tested without audio hardware; the Player feeds it its current state."""
import math
import os
import re
import time

from .core.i18n import fill, translate
from .core.insights import LOSSLESS

# How the output's rate is found out (Settings → Playback → "Output sample rate"):
#   auto: PipeWire's allowed rates when it runs (it switches the output to a song's rate when that rate is
#         allowed and nothing else is playing at another), otherwise the device's own rate
#   follows: the output takes each song's rate (a DAC set up for it, ALSA hw:, PipeWire set up by hand)
#   fixed: the output stays at the device's rate and anything else is converted
RATE_MODES = ("auto", "follows", "fixed")
_ALLOWED = re.compile(r"default\.clock\.allowed-rates\s*=\s*\[([^\]]*)\]")
_cache = {"at": 0.0, "rates": frozenset()}


def _pipewire_conf_files(env):
    """PipeWire's config, in the order later ones win: the defaults, the system's, then yours (and, in the
    Flatpak, the host's through /run/host)."""
    home = env.get("HOME") or os.path.expanduser("~")
    user = env.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
    out = []
    for root in ("/usr/share/pipewire", "/run/host/usr/share/pipewire", "/etc/pipewire", "/run/host/etc/pipewire",
                 os.path.join(user, "pipewire")):
        main = os.path.join(root, "pipewire.conf")
        if os.path.isfile(main):
            out.append(main)
        drop_ins = os.path.join(root, "pipewire.conf.d")
        try:
            out += [os.path.join(drop_ins, n) for n in sorted(os.listdir(drop_ins)) if n.endswith(".conf")]
        except OSError:
            pass
    return out


def _rates_in(text):
    """The rates a `default.clock.allowed-rates = [ 44100 48000 ]` line lists (comments left out)."""
    text = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
    found = _ALLOWED.findall(text)
    if not found:
        return None
    return frozenset(int(r) for r in re.findall(r"\d+", found[-1].replace(",", " ")) if 8000 <= int(r) <= 768000)


def pipewire_allowed_rates(env=None, run=None):
    """The sample rates PipeWire may switch the output to (empty: PipeWire isn't running here, or it keeps one
    rate). The live setting (pw-metadata) first, then the config files. Looked up at most every 15 seconds."""
    env = os.environ if env is None else env
    now = time.monotonic()
    if run is None and now - _cache["at"] < 15:
        return _cache["rates"]
    rates = frozenset()
    runtime = env.get("PIPEWIRE_RUNTIME_DIR") or env.get("XDG_RUNTIME_DIR") or ""
    # (the Flatpak reaches the sound server as PulseAudio, so it has no PipeWire socket to see: it reads the
    # config it's allowed to, your own)
    if env.get("FLATPAK_ID") or (runtime and os.path.exists(os.path.join(runtime, env.get("PIPEWIRE_REMOTE") or "pipewire-0"))):
        live = None
        try:
            import subprocess

            r = (run or subprocess.run)(["pw-metadata", "-n", "settings", "0", "clock.allowed-rates"],
                                        capture_output=True, text=True, timeout=1.5)
            m = re.search(r"value:'\[?([^'\]]*)\]?'", r.stdout or "")
            if m:
                live = frozenset(int(x) for x in re.findall(r"\d+", m.group(1)) if 8000 <= int(x) <= 768000)
        except Exception:  # noqa: BLE001 - no pw-metadata (the Flatpak): the files say
            live = None
        if live is None:
            for path in _pipewire_conf_files(env):
                try:
                    with open(path, encoding="utf-8", errors="replace") as fh:
                        found = _rates_in(fh.read())
                except OSError:
                    continue
                if found is not None:
                    live = found
        rates = live or frozenset()
    if run is None:
        _cache.update(at=now, rates=rates)
    return rates


def output_follows(rate, mode="auto", allowed=None):
    """Whether the output runs at the song's own rate: "follows" says so, "fixed" says not, and "auto" asks
    PipeWire (a rate among its allowed rates, of which there's more than one)."""
    if mode == "follows":
        return True
    if mode == "fixed" or not rate:
        return False
    allowed = pipewire_allowed_rates() if allowed is None else allowed
    return len(allowed) > 1 and rate in allowed


def _rate(hz):
    return f"{hz / 1000:.1f}".rstrip("0").rstrip(".") + " kHz" if hz else ""


CAST_RATE = 48000  # what Hallucinate's sound and converted songs are sent at, at most (see cast.py)


def _describe_cast(track, cast, rg_factor, rg_mode, eq_enabled, eq_preset, crossfeed):
    """The path when the song plays on a cast device: what's done here, then what's sent and where."""
    full = describe(track, rg_factor=rg_factor, rg_mode=rg_mode, eq_enabled=eq_enabled, eq_preset=eq_preset,
                    crossfeed=crossfeed)
    stages = [full["stages"][0]]  # the source
    sent = cast.get("sent") or "original"
    rate = int(track.get("sample_rate") or 0)
    depth = int(track.get("bit_depth") or 0)
    if sent == "processed":
        stages += [st for st in full["stages"] if st["key"] in ("replaygain", "eq", "crossfeed")]
    if sent in ("processed", "converted"):
        out_rate = min(rate, CAST_RATE) if rate else CAST_RATE
        lossy = depth > 16 or rate > CAST_RATE  # 16-bit and 48 kHz at most: a hi-res song loses some on the way
        stages.append({"key": "convert", "name": translate("SignalPath", "Sent as"),
                       "detail": "  ·  ".join(["WAV", "16-bit", _rate(out_rate)]), "active": lossy})
    else:
        stages.append({"key": "convert", "name": translate("SignalPath", "Sent as"),
                       "detail": translate("SignalPath", "The original file"), "active": False})
    stages.append({"key": "output", "name": translate("SignalPath", "Output"),
                   "detail": fill(translate("SignalPath", "%1 (casting)"), cast.get("device") or "?"), "active": False})
    changed = [st["name"].lower() for st in stages if st["active"]]
    untouched = not changed
    summary = translate("SignalPath", "Untouched") if untouched else fill(translate("SignalPath", "Changed by %1"),
                                                                         ", ".join(changed))
    if sent == "original":
        advice = fill(translate("SignalPath", "Sent untouched to %1, which plays the file itself. Your equalizer and "
                                "crossfeed don't apply; Settings → Casting → Hallucinate's sound sends them along."),
                      cast.get("device") or "?")
    elif sent == "converted":
        advice = fill(translate("SignalPath", "%1 can't play this file as it is, so it's converted for it."),
                      cast.get("device") or "?")
    else:
        advice = fill(translate("SignalPath", "Played through your sound settings here, then sent to %1."),
                      cast.get("device") or "?")
    return {"stages": stages, "untouched": untouched, "summary": summary, "advice": [advice]}


def describe(track, *, rg_factor=1.0, rg_mode="off", volume=1.0, speed=1.0, eq_enabled=False, eq_preset="", crossfeed="",
             crossfade=0, device_name="", device_rate=0, rate_follows=False, rate_source="", cast=None):
    """Stages from the file to the output, each {"name", "detail", "active"} where active means it changes the
    sound, and whether the path is untouched: nothing between file and device alters the samples (the system
    mixer may still resample when the device runs at another rate, which is reported too). rate_follows: the
    output switches to the song's rate (see output_follows); rate_source says who switches it ("PipeWire").
    cast: while playing on another device, {"device": its name, "sent": "original" | "processed" | "converted"}
    (see cast.py): the path then ends there instead."""
    if not track:
        return {"stages": [], "untouched": False, "summary": ""}
    if cast:
        return _describe_cast(track, cast, rg_factor, rg_mode, eq_enabled, eq_preset, crossfeed)
    codec = (track.get("codec") or track.get("fmt") or "").upper()
    rate = int(track.get("sample_rate") or 0)
    lossless = codec in LOSSLESS
    source = [codec] if codec else []
    if rate:
        source.append(_rate(rate))
    if not lossless and track.get("bitrate"):
        source.append(fill(translate("SignalPath", "%1 kbps"), round(track["bitrate"] / 1000)))
    if lossless:
        source.append(translate("SignalPath", "lossless"))
    stages = [{"key": "source", "name": translate("SignalPath", "Source"), "detail": "  ·  ".join(source), "active": False}]

    rg_db = 20 * math.log10(rg_factor) if rg_factor > 0 else 0.0
    rg_on = rg_mode in ("track", "album") and abs(rg_db) >= 0.05
    if rg_mode in ("track", "album"):
        gain = f"{rg_db:+.1f}"
        if rg_on and track.get("rg_measured"):
            detail = fill(translate("SignalPath", "Track gain %1 dB (measured)") if rg_mode == "track"
                          else translate("SignalPath", "Album gain %1 dB (measured)"), gain)
        elif rg_on:
            detail = fill(translate("SignalPath", "Track gain %1 dB") if rg_mode == "track"
                          else translate("SignalPath", "Album gain %1 dB"), gain)
        else:
            detail = (translate("SignalPath", "Track gain: none tagged") if rg_mode == "track"
                      else translate("SignalPath", "Album gain: none tagged"))
    else:
        detail = translate("SignalPath", "Off")
    stages.append({"key": "replaygain", "name": translate("SignalPath", "ReplayGain"), "detail": detail, "active": rg_on})

    eq_on = bool(eq_enabled)
    stages.append({"key": "eq", "name": translate("SignalPath", "Equalizer"),
                   "detail": (eq_preset or translate("SignalPath", "Custom")) if eq_on else translate("SignalPath", "Off"),
                   "active": eq_on})
    if crossfeed:
        strength = {"light": translate("SignalPath", "Light"), "medium": translate("SignalPath", "Medium"),
                    "strong": translate("SignalPath", "Strong")}.get(crossfeed, crossfeed.capitalize())
        stages.append({"key": "crossfeed", "name": translate("SignalPath", "Crossfeed"),
                       "detail": fill(translate("SignalPath", "%1 (headphones)"), strength), "active": True})

    speed_on = abs(speed - 1.0) > 1e-3
    stages.append({"key": "speed", "name": translate("SignalPath", "Speed"),
                   "detail": f"{speed:g}×" if speed_on else translate("SignalPath", "Normal"), "active": speed_on})

    vol_on = volume < 0.999
    stages.append({"key": "volume", "name": translate("SignalPath", "Volume"), "detail": f"{round(volume * 100)}%", "active": vol_on})

    if crossfade:
        stages.append({"key": "crossfade", "name": translate("SignalPath", "Crossfade"),
                       "detail": fill(translate("SignalPath", "%1 s between tracks"), crossfade), "active": False})

    follows = bool(rate_follows and rate)
    resampled = bool(rate and device_rate and rate != device_rate and not follows)
    out = [device_name or translate("SignalPath", "System default")]
    if follows:
        out.append(fill(translate("SignalPath", "%1 (switched by %2)"), _rate(rate), rate_source)
                   if rate_source and rate != device_rate else _rate(rate))
    elif device_rate:
        out.append(fill(translate("SignalPath", "%1 (resampled from %2)"), _rate(device_rate), _rate(rate))
                   if resampled else _rate(device_rate))
    stages.append({"key": "output", "name": translate("SignalPath", "Output"), "detail": "  ·  ".join(out), "active": resampled})

    changed = [translate("SignalPath", "resampling") if s["key"] == "output" else s["name"].lower()
               for s in stages if s["active"]]
    untouched = not changed
    summary = translate("SignalPath", "Untouched") if untouched else fill(translate("SignalPath", "Changed by %1"), ", ".join(changed))
    # Why, in plain words, and what would leave the sound untouched (the two that surprise people most)
    advice = []
    if resampled:
        advice.append(fill(translate("SignalPath", "Your output runs at %1 and this song is %2, so it's converted on the way. "
                                     "Songs at %1 play untouched; on Linux, PipeWire can switch the output to each song's "
                                     "rate (its allowed-rates setting). If your output already follows each song, say so in "
                                     "Settings → Playback → Output sample rate."), _rate(device_rate), _rate(rate)))
    elif follows and rate_source and rate != device_rate:
        advice.append(fill(translate("SignalPath", "%1 switches the output to %2 for this song, as long as nothing else is "
                                     "playing at another rate at the same time (then it's converted)."), rate_source, _rate(rate)))
    if vol_on:
        advice.append(fill(translate("SignalPath", "Hallucinate's volume is at %1%, which scales the samples. Leave it at 100% "
                                     "and turn your system or amplifier down instead for an untouched path."), round(volume * 100)))
    return {"stages": stages, "untouched": untouched, "summary": summary, "advice": advice}
