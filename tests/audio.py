"""Helpers that synthesise real audio files in many formats with ffmpeg."""
import shutil
import struct
import subprocess

FFMPEG = shutil.which("ffmpeg")

# extension -> extra ffmpeg args
FORMATS = {
    "flac": [],
    "mp3": ["-c:a", "libmp3lame"],
    "ogg": ["-c:a", "libvorbis"],
    "opus": ["-c:a", "libopus", "-ar", "48000"],
    "m4a": ["-c:a", "aac"],
    "alac.m4a": ["-c:a", "alac"],
    "wav": [],
    "wma": ["-c:a", "wmav2"],
    "wv": ["-c:a", "wavpack"],
    "aiff": [],
}


def encode(path, ext, seconds=3.0, **meta):
    """Create `path` as `ext` (a key of FORMATS) with a sine tone and tags."""
    args = [FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
            "-ac", "2"]
    if "-ar" not in FORMATS[ext]:
        args += ["-ar", "44100"]
    for k, v in meta.items():
        args += ["-metadata", f"{k}={v}"]
    args += FORMATS[ext] + [str(path)]
    subprocess.run(args, check=True)
    return path


def make_ape(path, title="Ape Song", artist="Ape Artist", album="Ape Album", seconds=2):
    """A minimal Monkey's Audio header (version 3.99) plus an APEv2 tag.

    There's no APE encoder available, so this isn't decodable audio, but it is
    enough for the tag/duration reader, which is what the library needs.
    """
    rate = 44100
    blocks_per_frame = 73728
    total_blocks = rate * seconds
    frames = -(-total_blocks // blocks_per_frame)
    final = total_blocks - (frames - 1) * blocks_per_frame
    header = bytearray(b"MAC " + struct.pack("<H", 3990) + b"\0" * 50)
    header += struct.pack("<IIIHHI", blocks_per_frame, final, frames, 16, 2, rate)
    items = {"Title": title, "Artist": artist, "Album": album}
    body = b""
    for k, v in items.items():
        data = v.encode()
        body += struct.pack("<II", len(data), 0) + k.encode() + b"\0" + data
    footer_fields = struct.pack("<IIII", 2000, 32 + len(body), len(items), 0x80000000 | (1 << 29))
    footer = b"APETAGEX" + footer_fields + b"\0" * 8
    with open(path, "wb") as f:
        f.write(bytes(header) + b"\0" * 2000 + body + footer)
    return path


def _dsd_bits(seconds, freq, amp, rate):
    """A sine as a 1-bit stream: first-order sigma-delta modulation, which is just where the running sum of
    the wanted density crosses each whole number (so it needs no loop)."""
    import numpy as np

    n = int(rate * seconds) // 8 * 8
    density = (amp * np.sin(2 * np.pi * freq * np.arange(n) / rate) + 1) / 2
    ones = np.floor(np.cumsum(density))
    return np.diff(ones, prepend=0).astype(np.uint8), n


def make_dsf(path, seconds=2.0, freq=1000.0, amp=0.5, rate=2822400, channels=2):
    """A .dsf (Sony's DSD file): little-endian chunks, LSB first, channels in 4096-byte blocks."""
    import numpy as np

    bits, n = _dsd_bits(seconds, freq, amp, rate)
    block = 4096
    packed = np.packbits(bits.reshape(-1, 8)[:, ::-1], axis=1).ravel()
    packed = np.concatenate([packed, np.zeros((-len(packed)) % block, np.uint8)]).reshape(-1, block)
    data = np.repeat(packed[:, None, :], channels, axis=1).tobytes()
    fmt = struct.pack("<4sQIIIIIIQII", b"fmt ", 52, 1, 0, 2 if channels == 2 else 1, channels, rate, 1, n, block, 0)
    body = struct.pack("<4sQ", b"data", 12 + len(data)) + data
    with open(path, "wb") as f:
        f.write(struct.pack("<4sQQQ", b"DSD ", 28, 28 + len(fmt) + len(body), 0) + fmt + body)
    return path


def make_dff(path, seconds=2.0, freq=1000.0, amp=0.5, rate=2822400, channels=2):
    """A .dff (Philips' DSDIFF): big-endian chunks, MSB first, channels interleaved byte by byte."""
    import numpy as np

    bits, _n = _dsd_bits(seconds, freq, amp, rate)
    packed = np.packbits(bits.reshape(-1, 8), axis=1).ravel()
    data = np.repeat(packed[:, None], channels, axis=1).tobytes()

    def chunk(cid, body):
        return cid + struct.pack(">Q", len(body)) + body + (b"\0" if len(body) % 2 else b"")

    prop = (b"SND " + chunk(b"FS  ", struct.pack(">I", rate))
            + chunk(b"CHNL", struct.pack(">H", channels) + b"SLFTSRGT"[:4 * channels])
            + chunk(b"CMPR", b"DSD \x0enot compressed\0"))
    body = b"DSD " + chunk(b"FVER", struct.pack(">I", 0x01050000)) + chunk(b"PROP", prop) + chunk(b"DSD ", data)
    with open(path, "wb") as f:
        f.write(chunk(b"FRM8", body))
    return path
