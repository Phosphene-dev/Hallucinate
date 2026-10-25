# Hallucinate on a server, without a window

`hallucinate --headless` runs Hallucinate with no window: on a home server, a NAS, a Raspberry Pi, in a
container or a Proxmox LXC. It plays through that machine's sound output (a DAC, an amplifier, the speakers
plugged into it) and you control it from:

- **the web interface**, on your phone or any computer's browser (add it to your home screen and it opens
  like an app);
- **the command line**: `hallucinate cmd …` (play, queue, search, volume…; `hallucinate cmd --help`);
- **the terminal version**: `hallucinate tui`, a full-screen player in a terminal or an SSH session.

Your library, likes, ratings, playlists, listening history, scrobbling, ReplayGain and music servers all work
as in the app; the data folders are the same, so a library made with the window works without it and back.
Things that only make sense in a window (themes, visualizers, waveforms, lyrics) aren't loaded.

## Quick start

Any install of Hallucinate can run headless: the AppImage, pip, the Flatpak or a package.

```sh
hallucinate --headless /path/to/your/music      # music folders are remembered; next time just --headless
hallucinate --pair                               # in another terminal: a code for your phone
```

It prints the web interface's address. By default it answers **this computer only**; to use it from your phone,
let your network reach it (remembered for next time):

```sh
hallucinate --headless --network
```

Open the address it prints on your phone (e.g. `http://192.168.1.20:8483/`), enter the code from
`hallucinate --pair`, and you're in. The code works once, for five minutes; the phone stays paired until you
remove it (`hallucinate cmd remote` lists paired devices, `hallucinate cmd remote forget ID` removes one).

| What | How |
|---|---|
| What's playing | `hallucinate cmd status` |
| Play an album, artist, playlist… | `hallucinate cmd play-album Kind of Blue`, `play-artist`, `play-playlist`, `play-liked --shuffle` |
| Search (shows song ids) | `hallucinate cmd search coltrane` |
| Queue songs | `hallucinate cmd add 123 456 --next`; `hallucinate cmd queue` |
| Volume, seek | `hallucinate cmd volume 40`, `volume +5`, `seek 1:30`, `seek +30` |
| Web interface settings | `hallucinate cmd remote on/off`, `--network`/`--local`, `--port 8483` |
| New music copied in | it watches the folders; `hallucinate cmd rescan` looks again |
| For scripts | add `--json` to any `hallucinate cmd` command |

Stop it with Ctrl+C or SIGTERM; it saves the queue and position and picks up where it was next time.

## As a service (systemd)

On a computer you also use (your own account and sound session), use the **user service**:

```sh
mkdir -p ~/.config/systemd/user
cp packaging/server/hallucinate.service ~/.config/systemd/user/
systemctl --user enable --now hallucinate
loginctl enable-linger "$USER"     # keeps it running when you're logged out
```

On a machine that only plays music, with no desktop, use the **system service** with its own account
(`packaging/server/hallucinate-system.service`; the steps are at the top of the file). It plays straight to
the sound card through ALSA and reads music from `/music`.

## In a container (Docker, Podman)

```sh
docker build -f packaging/server/Dockerfile -t hallucinate .
docker run -d --name hallucinate --restart unless-stopped -p 8483:8483 \
  -v /path/to/music:/music:ro -v hallucinate-data:/data \
  --device /dev/snd --group-add audio hallucinate
docker exec hallucinate hallucinate --pair
docker exec -it hallucinate hallucinate tui
```

- **Sound**: `--device /dev/snd` gives it the host's sound cards (ALSA). To play through the host's PulseAudio
  or PipeWire instead, mount its socket and point at it:
  `-v /run/user/1000/pulse/native:/run/pulse/native -e PULSE_SERVER=unix:/run/pulse/native` (and drop
  `--device`).
- **Data**: everything it keeps (library, history, paired devices) is in the `/data` volume. Music is mounted
  read-only.
- **Network**: inside a container it listens on all of the container's addresses; who can reach it is decided by
  `-p`. `-p 127.0.0.1:8483:8483` keeps it to the host.

## Proxmox

**LXC container (lightweight; recommended)**: a Debian or Ubuntu container, with the host's sound card and your
music passed in. On the Proxmox host, in `/etc/pve/lxc/<id>.conf`:

```
# the sound card (ALSA devices are character devices 116)
lxc.cgroup2.devices.allow: c 116:* rwm
lxc.mount.entry: /dev/snd dev/snd none bind,optional,create=dir
# your music, read-only
mp0: /tank/music,mp=/music,ro=1
```

Then inside the container: install Hallucinate (with pip from a source checkout, see the README's Install
section; or the AppImage with `--appimage-extract-and-run`; or Docker if the container is set up for it), add the `hallucinate` account to the
`audio` group, and use the system service above. In an **unprivileged** container the device files belong to
`nobody`; either map the host's `audio` group into the container (`lxc.idmap`) or give the devices to the mapped
group on the host (`chgrp 100029 /dev/snd/*` for the default mapping of group 29).

**Virtual machine**: pass a USB DAC or sound card through (Hardware → Add → USB Device, or a PCI device) and
install as on any Linux machine. More isolated, but heavier than an LXC.

**No sound card on the host**: run Hallucinate where the speakers are, and keep the music on the server
(network share, or a music server: Jellyfin and Subsonic servers work in Hallucinate).

Check what sound devices it can see with `aplay -l` (alsa-utils) inside the container.

## Keeping it safe

- The web interface is **off** until switched on (headless switches it on), answers **only paired devices**,
  and can only play, queue, browse, like and rate: it can't read your files, edit tags, delete anything or
  change settings. Only a hash of each device's key is kept.
- It speaks plain HTTP: use `--network` on a network you trust (your home), not on public Wi-Fi. For HTTPS or
  access from outside your home, put it behind a reverse proxy with TLS (Caddy, nginx) or a VPN (WireGuard,
  Tailscale), and tell it the name it's reached by so it accepts it:
  `hallucinate cmd remote --host-name music.example.com`.
- The command line talks to it over a socket only your account can open.
- In a container it runs as its own unprivileged user.
