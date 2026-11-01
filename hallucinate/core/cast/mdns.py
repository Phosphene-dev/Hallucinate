"""Finding Chromecasts with multicast DNS (what "Bonjour"/Avahi do), without a library or a daemon.

A question for _googlecast._tcp.local is sent to the mDNS group from an ordinary port, so devices answer straight
back to us ("legacy unicast", RFC 6762 §6.7): no need for port 5353, which Avahi or Bonjour usually hold.

The answers come from anything on the network, so the parser never trusts them: every read is bounds-checked,
compressed names can only point backwards and at most a few times, and a reply that breaks a rule is dropped."""
import os
import select
import socket
import struct
import time

GROUP = ("224.0.0.251", 5353)
CHROMECAST = "_googlecast._tcp.local"
T_A, T_PTR, T_TXT, T_SRV = 1, 12, 16, 33
MAX_PACKET = 9000  # mDNS allows up to the interface's MTU; 9000 covers jumbo frames
MAX_JUMPS = 16  # compression pointers followed in one name
MAX_RECORDS = 200  # records read from one reply
MAX_NAME = 255


class Malformed(ValueError):
    pass


def encode_name(name):
    out = b""
    for label in name.rstrip(".").split("."):
        raw = label.encode("utf-8")
        if not 0 < len(raw) < 64:
            raise ValueError(f"bad DNS label in {name!r}")
        out += bytes([len(raw)]) + raw
    return out + b"\0"


def query(service=CHROMECAST, qid=0):
    """A PTR question for `service`, asking for a unicast answer (the QU bit)."""
    header = struct.pack("!HHHHHH", qid, 0, 1, 0, 0, 0)
    return header + encode_name(service) + struct.pack("!HH", T_PTR, 0x8001)


def _name(data, pos):
    """Reads a (maybe compressed) name at `pos`; returns (name, position after it)."""
    labels, jumps, end, total = [], 0, None, 0
    while True:
        if pos >= len(data):
            raise Malformed("name runs off the end")
        n = data[pos]
        if n & 0xC0 == 0xC0:
            if pos + 1 >= len(data):
                raise Malformed("cut-off pointer")
            target = ((n & 0x3F) << 8) | data[pos + 1]
            if target >= pos or jumps >= MAX_JUMPS:  # only backwards, and not for ever
                raise Malformed("bad pointer")
            jumps += 1
            if end is None:
                end = pos + 2
            pos = target
            continue
        if n & 0xC0:
            raise Malformed("unknown label type")
        if n == 0:
            return ".".join(labels), (end if end is not None else pos + 1)
        if pos + 1 + n > len(data):
            raise Malformed("label runs off the end")
        total += n + 1
        if total > MAX_NAME:
            raise Malformed("name too long")
        labels.append(data[pos + 1:pos + 1 + n].decode("utf-8", "replace"))
        pos += 1 + n


def _txt(rdata):
    out, pos = {}, 0
    while pos < len(rdata):
        n = rdata[pos]
        item = rdata[pos + 1:pos + 1 + n]
        pos += 1 + n
        if b"=" in item:
            k, v = item.split(b"=", 1)
            out[k.decode("ascii", "replace").lower()] = v.decode("utf-8", "replace")
    return out


def parse(data):
    """The records in one reply: a list of (name, type, value). PTR/SRV-target values are names, SRV is
    (target, port), TXT is a dict, A is a dotted address. Raises Malformed for anything that breaks the rules."""
    if len(data) < 12:
        raise Malformed("too short")
    _qid, flags, qd, an, ns, ar = struct.unpack("!HHHHHH", data[:12])
    if not flags & 0x8000:
        raise Malformed("not a response")
    if qd + an + ns + ar > MAX_RECORDS:
        raise Malformed("too many records")
    pos = 12
    for _ in range(qd):
        _, pos = _name(data, pos)
        pos += 4
    records = []
    for _ in range(an + ns + ar):
        name, pos = _name(data, pos)
        if pos + 10 > len(data):
            raise Malformed("cut-off record")
        rtype, _cls, _ttl, rdlen = struct.unpack("!HHIH", data[pos:pos + 10])
        pos += 10
        if pos + rdlen > len(data):
            raise Malformed("record data runs off the end")
        rdata = data[pos:pos + rdlen]
        if rtype == T_PTR:
            records.append((name, T_PTR, _name(data, pos)[0]))
        elif rtype == T_SRV and rdlen >= 7:
            port = struct.unpack("!H", rdata[4:6])[0]
            records.append((name, T_SRV, (_name(data, pos + 6)[0], port)))
        elif rtype == T_TXT:
            records.append((name, T_TXT, _txt(rdata)))
        elif rtype == T_A and rdlen == 4:
            records.append((name, T_A, socket.inet_ntoa(rdata)))
        pos += rdlen
    return records


def services(records, service=CHROMECAST, sender=None):
    """Chromecasts described by a set of records: {instance: {"name", "model", "id", "host", "port"}}.

    `sender` is the address the reply came from. A device may only describe itself: an address record that
    points somewhere else is ignored and the sender's address is used, so a reply can't send us to another
    machine."""
    by = {}
    for name, rtype, value in records:
        by.setdefault((name.lower(), rtype), value)
    found = {}
    for name, rtype, value in records:
        if rtype != T_PTR or name.lower() != service.lower():
            continue
        instance = value
        srv = by.get((instance.lower(), T_SRV))
        txt = by.get((instance.lower(), T_TXT)) or {}
        if not srv:
            continue
        target, port = srv
        address = by.get((target.lower(), T_A))
        if sender and address != sender:
            address = sender
        if not address or not 0 < port < 65536:
            continue
        label = instance[:-len(service) - 1] if instance.lower().endswith("." + service.lower()) else instance
        found[instance] = {
            "name": (txt.get("fn") or label)[:100],
            "model": txt.get("md", "")[:100],
            "id": (txt.get("id") or label)[:64],
            "host": address,
            "port": port,
        }
    return found


def browse(timeout=2.0, interfaces=("",), service=CHROMECAST):
    """Asks the network for Chromecasts and gathers answers for `timeout` seconds. `interfaces` are this
    computer's IPv4 addresses to ask on ("" lets the system pick). Returns {id: device dict}."""
    socks = []
    for iface in interfaces:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
            if iface:
                s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(iface))
            s.bind((iface, 0))
            s.setblocking(False)
            s.sendto(query(service, int.from_bytes(os.urandom(2), "big") & 0x7FFF), GROUP)
            socks.append(s)
        except OSError:
            continue
    found = {}
    deadline = time.monotonic() + timeout
    try:
        while socks:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            ready, _, _ = select.select(socks, [], [], left)
            for s in ready:
                try:
                    data, (sender, _port) = s.recvfrom(MAX_PACKET)
                    for device in services(parse(data), service, sender).values():
                        found[device["id"]] = device
                except (OSError, Malformed, UnicodeError, struct.error):
                    continue
    finally:
        for s in socks:
            s.close()
    return found
