# Security policy

## Reporting a vulnerability
Please report vulnerabilities privately via GitHub's
["Report a vulnerability"](../../security/advisories/new) form rather than a public issue.
Expect an initial response within a week.

## How Hallucinate protects you
- **Nothing about you leaves your computer** unless you turn something on: no telemetry. The only
  connections are the ones you enable (lyrics and cover lookups, Last.fm, ListenBrainz, headphone EQ
  profiles, the update check), and **offline mode** stops all of them. Every request goes through one
  place in the code (`hallucinate/core/net.py`), and a test fails if anything bypasses it.
- **The interface never goes online.** Tags, lyrics and lookup results are shown as plain text, so a
  crafted title can't format the window or load a remote image (a tracking pixel), and the interface's
  network access refuses anything that isn't local (`hallucinate/qmlnet.py`).
- **Online answers are size-capped** and time-limited; servers can't stream without end into memory.
- **Downloads are signed.** Each release's `SHA256SUMS` covers every file and is signed with the project
  key (fingerprint `617F 8316 D150 EC7C 1C19 AE07 659A 60CE E59B AC24`), each file has GitHub's signed build
  provenance, and the Flatpak repository and bundle are signed with the same key. See
  [Checking a download](README.md#checking-a-download). Release builds install exact, checksummed
  dependency versions only.
- **Updates** (the AppImage and the Windows installer build only) are downloaded from this repository's
  releases and checked against the SHA-256 digest GitHub publishes before they're installed.
- **Credentials** (Last.fm, ListenBrainz, Discogs, your music servers) live only in the system keyring, never
  in plain files; a keyring that would store them in a plain file is refused.
- **The web interface and phone remote** are off until you turn them on, listen on this computer only unless
  you allow your network, and answer only devices you've paired with a one-time code (only a hash of each
  device's key is kept, and any device can be removed). Other web pages can't drive it (host, origin and
  header checks), and it can only play, queue, browse, like and rate: it can't read your files or paths, edit
  tags, delete anything or change settings.
- **The control socket** used by `hallucinate cmd`, `hallucinate tui`, `--pair`, `--next` and friends is private to
  your user account. A headless server in a container runs as its own unprivileged user.
- **Your data is backed up**: the library database (likes, plays, playlists, history) is backed up
  daily; a damaged one is set aside and the backup restored. Removing albums is reversible, and
  "Move to trash" uses the system trash.
- **Malformed files** (audio, CUE sheets, playlists, other players' libraries, themes) are fuzz-tested:
  each is read or rejected cleanly, without crashing or hanging. Dependencies are checked against known
  vulnerabilities in CI.

## Scope notes
Reports about crashes or unsafe handling of malformed input (audio files, tags, CUE sheets, playlists,
library imports, theme JSON) are welcome, as is anything that makes Hallucinate connect somewhere it
shouldn't.
