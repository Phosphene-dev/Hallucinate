# Audio output on each system

Hallucinate plays through Qt Multimedia's normal output by default: the system's default output device, or the
one chosen in Settings → Playback (a chosen device that is unplugged falls back to the default until it returns).
When the equalizer, crossfeed or headphone correction is on, or a DSD song plays, decoded audio goes through
Hallucinate's own output (`eq.EqTap`, a Qt audio sink on the same device) so it can be processed first.

## Bit-perfect playback

Settings → Sound → **Bit-perfect playback** sends every song to the output exactly as it was decoded, in its own
sample format, with everything in Hallucinate that would change it set aside: the equalizer, crossfeed,
ReplayGain, crossfade, fades, speed and Hallucinate's volume (the system's or the amplifier's volume is the one to
use). DSD songs are the exception: they're converted to PCM first (`dsd.py`), and bit-perfect from there on.

What's left is the system's mixer, which converts any song whose rate isn't the output's. Each system is handled
its own way:

| System | How the song's own rate is kept | Where |
|---|---|---|
| Linux with PipeWire | PipeWire is asked to run at each song's rate (`clock.force-rate` in its "settings" metadata, through `pw-metadata`), and given its own choice back when bit-perfect is switched off or Hallucinate quits. Other sounds play at that rate meanwhile (PipeWire converts them). | `bitperfect.py` |
| macOS | The output device's own ("nominal") rate is set to each song's, where the device has that rate, and the rate it had is put back afterwards. Core Audio's mixer is 32-bit float, so at full volume and the song's own rate the samples pass through unchanged. | `coreaudio.py` (ctypes) |
| Windows | The output is taken in **exclusive mode** (WASAPI), opened at each song's own rate and format: 24-bit songs as 24-in-32 or packed 24-bit, whichever the device takes. Other apps are silent while Hallucinate holds it; it's given back a few seconds after pausing and taken again on play. It can be switched off (Settings → Sound), and if the output can't be had (another app holds it, exclusive mode is disallowed in the device's Properties → Advanced, or the format isn't supported) the song plays through the shared mixer and the signal path says why. | `wasapi.py` (ctypes) |
| Other Linux sound systems, the Flatpak | Nothing is asked: the system may resample, and the signal path says so. (The Flatpak can't run the host's `pw-metadata`.) | |

The signal path (the button beside the song's format) shows what happens to the current song: "Bit-perfect"
only when nothing between the file and the output changes it.

## Not done

- Native PipeWire streams or ALSA `hw:` devices (bypassing PipeWire altogether). The rate request above gives the
  same result on PipeWire systems without a second audio backend.
- Native DSD (DoP) to DACs that take it: DSD is converted to PCM (88.2, 176.4 or 352.8 kHz).
- macOS hog mode (taking a device by itself): Core Audio's mixer is transparent at the song's rate, so it isn't
  needed for bit-perfect output.

Exclusive mode and the Mac's rate switching can only be checked against real hardware: CI runs
`tests/test_native_audio.py` on its Windows and macOS machines, and `docs/manual-qa.md` lists the checks to do
with a real DAC.
