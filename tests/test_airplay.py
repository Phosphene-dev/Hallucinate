"""AirPlay (RAOP) speakers: which are offered, the packets (ALAC frames stored uncompressed, sync, timing) and the
whole conversation with a stand-in speaker (RTSP over TCP, RTP over UDP): set up, the sound arrives in order and
in step, pause drops what the speaker holds and goes back to what was heard, missing packets are sent again,
the volume, and only the speaker may ask for anything."""
import re
import socket
import struct
import threading
import time
import wave

import numpy as np
import pytest

from hallucinate.core.cast import airplay, pcm


def service(**txt):
    base = {"et": "0,1", "cn": "0,1,2,3", "sr": "44100", "ss": "16", "ch": "2", "am": "AirPort10,115"}
    base.update(txt)
    return {"id": "A1B2C3D4E5F6@Kitchen", "name": "A1B2C3D4E5F6@Kitchen", "host": "192.168.1.30", "port": 7000,
            "txt": {k: v for k, v in base.items() if v is not None}}


def test_speakers_that_can_play_the_stream_are_offered():
    dev = airplay.describe(service())
    assert dev == {"id": "airplay:A1B2C3D4E5F6", "kind": "airplay", "name": "Kitchen", "model": "AirPort10,115",
                   "host": "192.168.1.30", "port": 7000}
    assert airplay.describe(service(et=None, cn=None))  # (nothing said: try)
    own_id = dict(service(), id="0123-4567")  # (a speaker whose announcement carries an id of its own)
    assert airplay.describe(own_id)["name"] == "Kitchen"
    for txt in ({"pw": "true"}, {"et": "1"}, {"et": "3,5"}, {"cn": "0"}, {"sr": "48000"}, {"ss": "24"}):
        assert airplay.describe(service(**txt)) is None, txt


def test_discovery_reads_the_announcements():
    seen = {}

    def browse(timeout, interfaces, service):
        seen["service"] = service
        return {"a": globals()["service"](), "b": globals()["service"](pw="true")}

    found = airplay.discover(browse=browse)
    assert seen["service"] == "_raop._tcp.local"
    assert list(found) == ["airplay:A1B2C3D4E5F6"]


def unpack_alac(frame):
    bits = np.unpackbits(np.frombuffer(frame, np.uint8))
    header = "".join(map(str, bits[:23]))
    body = bits[23:23 + airplay.PACKET_FRAMES * 32].reshape(-1, 2, 16)
    values = (body * (1 << np.arange(15, -1, -1))).sum(axis=2).astype(np.int64)
    end = "".join(map(str, bits[23 + airplay.PACKET_FRAMES * 32:][:3]))
    return header, np.where(values >= 32768, values - 65536, values), end


def test_an_alac_frame_holds_the_samples_exactly():
    samples = np.random.default_rng(3).integers(-32768, 32768, (airplay.PACKET_FRAMES, 2), dtype=np.int16)
    frame = airplay.alac_frame(samples.tobytes())
    assert len(frame) == 1412
    header, values, end = unpack_alac(frame)
    assert header == "001" + "0000" + "0" * 12 + "0" + "00" + "1"  # a channel pair, no size, not compressed
    assert np.array_equal(values, samples.astype(np.int64))
    assert end == "111"


def test_packets_sync_and_timing():
    p = airplay.rtp_packet(65535, 2**32 + 5, 0xABCDEF01, b"xy", first=True)
    assert p[:2] == b"\x80\xe0" and struct.unpack("!HII", p[2:12]) == (65535, 5, 0xABCDEF01) and p[12:] == b"xy"
    assert airplay.rtp_packet(1, 2, 3, b"")[1] == 0x60
    sync = airplay.sync_packet(100000, first=True, now=1000.5)
    proto, kind, seven, then, stamp, now_rtp = struct.unpack("!BBHIQI", sync)
    assert (proto, kind, seven) == (0x90, 0xD4, 7)
    assert now_rtp - then == airplay.LATENCY_FRAMES
    assert stamp == ((1000 + airplay.NTP_EPOCH) << 32) | (1 << 31)
    request = struct.pack("!BBHI", 0x80, 0xD2, 7, 0) + bytes(16) + b"SENTTIME"
    reply = airplay.timing_reply(request, now=5.0)
    assert reply[:2] == b"\x80\xd3" and reply[8:16] == b"SENTTIME" and len(reply) == 32
    assert airplay.timing_reply(b"\x80\xd4" + bytes(30)) is None
    assert airplay.volume_db(1) == 0 and airplay.volume_db(0.5) == -15 and airplay.volume_db(0) == -144


# --- a stand-in speaker ----------------------------------------------------------------------------------------
class FakeSpeaker:
    def __init__(self, refuse=None):
        self.refuse = refuse
        self.requests = []
        self.audio, self.syncs, self.timing = [], [], []
        self.tcp = socket.socket()
        self.tcp.bind(("127.0.0.1", 0))
        self.tcp.listen(1)
        self.port = self.tcp.getsockname()[1]
        self.udp = {}
        for name in ("server", "control", "timing"):
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind(("127.0.0.1", 0))
            s.settimeout(0.2)
            self.udp[name] = s
        self.their = {}
        self.stop = False
        self.threads = [threading.Thread(target=self._rtsp, daemon=True)]
        self.threads += [threading.Thread(target=self._listen, args=(n,), daemon=True) for n in self.udp]
        for t in self.threads:
            t.start()

    def _rtsp(self):
        conn, _ = self.tcp.accept()
        conn.settimeout(10)
        buf = b""
        while not self.stop:
            try:
                while b"\r\n\r\n" not in buf:
                    chunk = conn.recv(4096)
                    if not chunk:
                        return
                    buf += chunk
            except OSError:
                return
            head, buf = buf.split(b"\r\n\r\n", 1)
            lines = head.decode().split("\r\n")
            headers = dict(line.split(": ", 1) for line in lines[1:])
            length = int(headers.get("Content-Length", 0))
            while len(buf) < length:
                buf += conn.recv(4096)
            body, buf = buf[:length], buf[length:]
            method = lines[0].split()[0]
            self.requests.append((method, headers, body))
            extra = ""
            status = "200 OK"
            if self.refuse and method == self.refuse[0]:
                status = self.refuse[1]
            if method == "SETUP":
                t = headers["Transport"]
                self.their = {k: int(v) for k, v in re.findall(r"(control_port|timing_port)=(\d+)", t)}
                extra = ("Transport: RTP/AVP/UDP;unicast;mode=record;"
                         f"server_port={self.udp['server'].getsockname()[1]};"
                         f"control_port={self.udp['control'].getsockname()[1]};"
                         f"timing_port={self.udp['timing'].getsockname()[1]}\r\nSession: 4242\r\n")
            conn.sendall(f"RTSP/1.0 {status}\r\nCSeq: {headers['CSeq']}\r\n{extra}\r\n".encode())

    def _listen(self, name):
        s = self.udp[name]
        while not self.stop:
            try:
                data, addr = s.recvfrom(4096)
            except OSError:
                continue
            {"server": self.audio, "control": self.syncs, "timing": self.timing}[name].append((data, addr))

    def methods(self):
        return [m for m, _h, _b in self.requests]

    def close(self):
        self.stop = True
        for s in [self.tcp, *self.udp.values()]:
            s.close()


def plain(host, port, timeout):
    return socket.create_connection((host, port), timeout)


def wav(path, seconds, value):
    frames = int(airplay.RATE * seconds)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(airplay.RATE)
        w.writeframes(np.full(frames * 2, value, "<i2").tobytes())
    return str(path)


def first_sample(packet):
    _h, values, _e = unpack_alac(packet[12:])
    return int(values[0][0])


@pytest.fixture
def speaker():
    fake = FakeSpeaker()
    yield fake
    fake.close()


def test_a_song_plays_on_the_speaker(tmp_path, speaker, monkeypatch):
    monkeypatch.setattr(airplay, "LATENCY_FRAMES", 4410)  # (0.1 s, so the test doesn't wait two)
    events = []
    sp = airplay.Speaker("127.0.0.1", speaker.port, on_event=lambda k, t: events.append((k, t)), connect=plain)
    sp.connect()
    try:
        assert speaker.methods() == ["OPTIONS", "ANNOUNCE", "SETUP", "RECORD"]
        announce = speaker.requests[1]
        assert announce[1]["Content-Type"] == "application/sdp" and b"AppleLossless" in announce[2]
        assert b"a=fmtp:96 352 0 16 40 10 14 2 255 0 0 44100" in announce[2]
        assert "seq=" in speaker.requests[3][1]["RTP-Info"]
        assert speaker.requests[3][1]["Session"] == "4242"
        deadline = time.monotonic() + 2  # the speaker's timing port was spoken to first (a firewall lets it back)
        while not speaker.timing and time.monotonic() < deadline:
            time.sleep(0.02)
        assert speaker.timing and speaker.timing[0][0][1] == 0xD2
        sp.set_volume(0.5)
        assert speaker.requests[-1][0] == "SET_PARAMETER" and speaker.requests[-1][2] == b"volume: -15.000000\r\n"

        sp.load(wav(tmp_path / "a.wav", 0.5, 1000), tag="a")
        sp.queue_next(wav(tmp_path / "b.wav", 0.3, 2000), tag="b")
        deadline = time.monotonic() + 5
        while ("ended", "b") not in events and time.monotonic() < deadline:
            time.sleep(0.02)
        assert events == [("advanced", "b"), ("ended", "b")]
        packets = [d for d, _a in speaker.audio]
        seqs = [struct.unpack("!H", p[2:4])[0] for p in packets]
        stamps = [struct.unpack("!I", p[4:8])[0] for p in packets]
        assert all((b - a) & 0xFFFF == 1 for a, b in zip(seqs, seqs[1:]))
        assert all((b - a) & 0xFFFFFFFF == airplay.PACKET_FRAMES for a, b in zip(stamps, stamps[1:]))
        assert packets[0][1] == 0xE0 and all(p[1] == 0x60 for p in packets[1:])
        values = [first_sample(p) for p in packets]
        assert values[0] == 1000 and 2000 in values and values.index(2000) > 40  # a, then b, no gap between
        assert len(packets) == -(-int(0.8 * airplay.RATE) // airplay.PACKET_FRAMES)  # (the last one padded)
        syncs = [d for d, _a in speaker.syncs]
        assert syncs and syncs[0][:2] == b"\x90\xd4"
    finally:
        sp.close()
    assert speaker.methods()[-1] == "TEARDOWN"


def test_pause_drops_what_the_speaker_holds_and_resumes_where_it_was_heard(tmp_path, speaker, monkeypatch):
    monkeypatch.setattr(airplay, "LATENCY_FRAMES", 22050)  # 0.5 s
    sp = airplay.Speaker("127.0.0.1", speaker.port, connect=plain)
    sp.connect()
    try:
        sp.load(wav(tmp_path / "a.wav", 5.0, 1000), tag="a")
        time.sleep(1.2)
        tag, heard = sp.position()
        assert tag == "a" and 0.5 < heard < 0.9  # (about 1.2 s sent, 0.5 s of it not heard yet)
        sp.pause()
        assert speaker.methods()[-1] == "FLUSH"
        assert re.match(r"seq=\d+;rtptime=\d+", speaker.requests[-1][1]["RTP-Info"])
        _tag, paused_at = sp.position()
        assert abs(paused_at - heard) < 0.15  # back to what was being heard
        n = len(speaker.audio)
        time.sleep(0.3)
        assert len(speaker.audio) == n  # nothing sent while paused
        sp.play()
        time.sleep(0.3)
        assert speaker.audio[n][0][1] == 0xE0  # starting afresh
    finally:
        sp.close()


def test_pausing_while_the_song_before_still_plays_goes_back_into_it(tmp_path, speaker, monkeypatch):
    monkeypatch.setattr(airplay, "LATENCY_FRAMES", 44100)  # 1 s
    events = []
    sp = airplay.Speaker("127.0.0.1", speaker.port, on_event=lambda k, t: events.append(k), connect=plain)
    sp.connect()
    try:
        sp.load(wav(tmp_path / "a.wav", 0.5, 1000), tag="a")
        sp.queue_next(wav(tmp_path / "b.wav", 2.0, 2000), tag="b")
        time.sleep(0.8)  # a has all been sent, b has begun, but a is still being heard
        assert sp.position()[0] == "a"
        sp.pause()
        tag, at = sp.position()
        assert tag == "a" and at < 0.5 and events == []  # (b never began, as far as anyone heard)
        n = len(speaker.audio)
        sp.play()
        time.sleep(0.7)
        values = [first_sample(d) for d, _a in speaker.audio[n:]]
        assert values[0] == 1000 and 2000 in values  # the rest of a again, then on into b
        deadline = time.monotonic() + 3
        while "advanced" not in events and time.monotonic() < deadline:
            time.sleep(0.02)
        assert events == ["advanced"]
    finally:
        sp.close()


def test_missing_packets_are_sent_again_and_only_the_speaker_is_answered(tmp_path, speaker, monkeypatch):
    monkeypatch.setattr(airplay, "LATENCY_FRAMES", 4410)
    sp = airplay.Speaker("127.0.0.1", speaker.port, connect=plain)
    sp.connect()
    try:
        sp.load(wav(tmp_path / "a.wav", 2.0, 1000), tag="a")
        time.sleep(0.5)
        first_seq = struct.unpack("!H", speaker.audio[0][0][2:4])[0]
        ours = ("127.0.0.1", speaker.their["control_port"])
        speaker.udp["control"].sendto(struct.pack("!BBHHH", 0x80, 0xD5, 1, first_seq + 2, 2), ours)
        deadline = time.monotonic() + 2
        resent = []
        while len(resent) < 2 and time.monotonic() < deadline:
            resent = [d for d, _a in speaker.syncs if d[1] == 0xD6]
            time.sleep(0.02)
        assert [struct.unpack("!H", d[6:8])[0] for d in resent] == [first_seq + 2, first_seq + 3]
        assert resent[0][4:6] == b"\x80\x60" and resent[0][16:] == speaker.audio[2][0][12:]
        timing = ("127.0.0.1", speaker.their["timing_port"])
        speaker.udp["timing"].sendto(struct.pack("!BBHI", 0x80, 0xD2, 7, 0) + bytes(16) + b"ASKEDNOW", timing)
        deadline = time.monotonic() + 2
        while not any(d[1] == 0xD3 for d, _a in speaker.timing) and time.monotonic() < deadline:
            time.sleep(0.02)
        answer = next(d for d, _a in speaker.timing if d[1] == 0xD3)
        assert answer[8:16] == b"ASKEDNOW"
        stranger = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        stranger.bind(("127.0.0.2", 0))
        stranger.settimeout(0.5)
        stranger.sendto(struct.pack("!BBHI", 0x80, 0xD2, 7, 0) + bytes(24), timing)
        with pytest.raises(socket.timeout):
            stranger.recvfrom(100)  # (someone else on the network gets nothing)
        stranger.close()
    finally:
        sp.close()


@pytest.mark.parametrize("status", ["401 Unauthorized", "470 Connection Authorization Required"])
def test_a_refusal_says_what_the_speaker_answered(status):
    fake = FakeSpeaker(refuse=("ANNOUNCE", status))
    try:
        sp = airplay.Speaker("127.0.0.1", fake.port, connect=plain)
        with pytest.raises(airplay.Refused) as e:
            sp.connect()
        assert e.value.status == int(status[:3])
    finally:
        fake.close()


def test_the_queue_goes_back_into_a_song_still_being_heard(tmp_path):
    now = [0.0]
    q = pcm.Queue(airplay.RATE, lambda: now[0])
    q.load(wav(tmp_path / "a.wav", 1.0, 1), tag="a")
    q.queue_next(wav(tmp_path / "b.wav", 0.5, 2), tag="b")
    data, events = q.pull(int(airplay.RATE * 1.05), behind=1.0)
    assert events == [("advanced", "b")] and q.current.tag == "b"
    now[0] = 0.5  # a's last half second is still to be heard
    assert q.position(behind=1.0)[0] == "a"
    assert q.rewind(1.0) is True
    assert q.current.tag == "a" and q.next.tag == "b" and q.next.at == 0
    assert abs(q.current.at / airplay.RATE - 0.5) < 0.01
    assert q.rewind(0.0) is False
