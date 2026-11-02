"""Playing on DLNA/UPnP renderers: smart TVs, AV receivers, network speakers, Kodi, and so on.

Finding them: an SSDP search (a few lines of HTTP over multicast UDP) brings answers naming a description file;
that XML lists the device's name and the addresses of its controls. Playing: SOAP requests to the AVTransport
service (set the song's address, play, pause, seek, what's the position) and RenderingControl (volume).

Everything a device sends is checked: answers and files are size-capped, XML with a DOCTYPE or entities is
refused, and every address a device gives must be on the machine that answered, so a device on the network
can't send us to fetch something from elsewhere."""
import ipaddress
import re
import select
import socket
import time
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, wait
from xml.sax.saxutils import escape

GROUP = ("239.255.255.250", 1900)
RENDERER = "urn:schemas-upnp-org:device:MediaRenderer:1"
AVTRANSPORT = "urn:schemas-upnp-org:service:AVTransport:1"
RENDERING = "urn:schemas-upnp-org:service:RenderingControl:1"
CONNECTION = "urn:schemas-upnp-org:service:ConnectionManager:1"
MAX_ANSWER = 4096
MAX_XML = 512 * 1024
MAX_PER_MACHINE = 4  # description files one machine may name (a TV may have a couple; a flood is cut short)
MAX_FOUND = 32
DESCRIBE_DEADLINE = 8.0  # all the description files are read at once, and the search waits no longer than this
TIMEOUT = 5.0
USER_AGENT = "Hallucinate UPnP/1.0 DLNADOC/1.50"


class UpnpError(Exception):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def search_message(target=RENDERER, wait=2):
    return ("M-SEARCH * HTTP/1.1\r\n"
            f"HOST: {GROUP[0]}:{GROUP[1]}\r\n"
            'MAN: "ssdp:discover"\r\n'
            f"MX: {int(wait)}\r\n"
            f"ST: {target}\r\n"
            f"USER-AGENT: {USER_AGENT}\r\n\r\n").encode("ascii")


def parse_answer(data):
    """The headers of one SSDP answer (lower-case names), or None if it isn't one."""
    try:
        text = data[:MAX_ANSWER].decode("utf-8", "replace")
    except Exception:  # pragma: no cover - decode with "replace" doesn't raise
        return None
    lines = text.split("\r\n")
    if not lines or not lines[0].upper().startswith(("HTTP/1.1 200", "NOTIFY")):
        return None
    out = {}
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out


def same_machine(url, sender):
    """`url` if it's plain http on the address that answered (or a name for it), else None."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return None
    if parts.scheme != "http" or not parts.hostname:
        return None
    try:
        if ipaddress.ip_address(parts.hostname) != ipaddress.ip_address(sender):
            return None
    except ValueError:
        return None  # a name could resolve anywhere; devices always give their address
    try:
        port = parts.port
    except ValueError:
        return None
    if port is not None and not 0 < port < 65536:
        return None
    return url


def safe_xml(raw):
    """Parses XML a device sent. A DOCTYPE or entity anywhere is refused (no device needs one; they're how XML
    bombs and file reads work)."""
    if len(raw) > MAX_XML:
        raise UpnpError("answer too large")
    if re.search(rb"<!(?:ENTITY|DOCTYPE)", raw, re.IGNORECASE):
        raise UpnpError("XML with a DOCTYPE")
    try:
        return ET.fromstring(raw)
    except ET.ParseError as e:
        raise UpnpError(f"unreadable XML: {e}") from e


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _child(el, name):
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _text(el, name):
    c = _child(el, name) if el is not None else None
    return (c.text or "").strip() if c is not None else ""


def http_request(url, method="GET", body=None, headers=None, timeout=TIMEOUT):
    """(status, body bytes) for one plain-HTTP request to a device on the local network (through the gate in
    core/net.py: never in offline mode, never off your network); redirects aren't followed and the answer is
    capped."""
    from .. import net

    try:
        return net.local_http(url, method, body, dict({"User-Agent": USER_AGENT}, **(headers or {})), timeout,
                              limit=MAX_XML)
    except (OSError, ValueError) as e:  # (URLErrors are OSErrors; ResponseTooLarge too)
        raise UpnpError(str(e)) from e


def describe(location, sender, fetch=http_request):
    """A renderer's details from its description file: {"id", "name", "model", "maker", "host", "controls":
    {service type: control URL}}. Raises UpnpError if it isn't usable (no AVTransport control)."""
    if not same_machine(location, sender):
        raise UpnpError("description address isn't on the device that answered")
    status, raw = fetch(location)
    if status != 200:
        raise UpnpError(f"description answered {status}")
    root = safe_xml(raw)
    base = _text(root, "URLBase") or location
    if not same_machine(base, sender):
        base = location

    def devices(el):
        for d in el.iter():
            if _local(d.tag) == "device":
                yield d

    found = None
    for dev in devices(root):
        controls = {}
        services = _child(dev, "serviceList")
        for svc in (services if services is not None else []):
            stype, ctl = _text(svc, "serviceType"), _text(svc, "controlURL")
            for want in (AVTRANSPORT, RENDERING, CONNECTION):
                if stype.split(":")[:-1] == want.split(":")[:-1] and ctl:  # any version
                    url = same_machine(urllib.parse.urljoin(base, ctl), sender)
                    if url:
                        controls[want] = url
        if AVTRANSPORT in controls:
            found = {
                "id": _text(dev, "UDN")[:100] or location,
                "name": (_text(dev, "friendlyName") or sender)[:100],
                "model": _text(dev, "modelName")[:100],
                "maker": _text(dev, "manufacturer")[:100],
                "host": sender,
                "controls": controls,
            }
            break
    if found is None:
        raise UpnpError("not a media player")
    return found


def search(timeout=2.0, interfaces=("",), target=RENDERER):
    """SSDP answers for `target` gathered for `timeout` seconds: {location: sender address}."""
    socks = []
    for iface in interfaces:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
            if iface:
                s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(iface))
            s.bind((iface, 0))
            s.setblocking(False)
            msg = search_message(target, max(1, int(timeout)))
            s.sendto(msg, GROUP)
            s.sendto(msg, GROUP)  # UDP can drop one; the spec suggests sending more than once
            socks.append(s)
        except OSError:
            continue
    found, per_machine = {}, {}
    deadline = time.monotonic() + timeout
    try:
        while socks and len(found) < MAX_FOUND:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            ready, _, _ = select.select(socks, [], [], left)
            for s in ready:
                try:
                    data, (sender, _port) = s.recvfrom(MAX_ANSWER)
                except OSError:
                    continue
                headers = parse_answer(data)
                if not headers or (headers.get("st") and headers["st"] != target):
                    continue
                location = headers.get("location", "")
                if same_machine(location, sender) and location not in found:
                    if per_machine.get(sender, 0) >= MAX_PER_MACHINE:
                        continue
                    per_machine[sender] = per_machine.get(sender, 0) + 1
                    found[location] = sender
    finally:
        for s in socks:
            s.close()
    return found


def discover(timeout=2.0, interfaces=("",), fetch=http_request, deadline=DESCRIBE_DEADLINE):
    """Renderers on the network: {id: details} (see describe). Their description files are read side by side, and
    one that's slow to answer is left out rather than holding the search up."""
    answers = search(timeout, interfaces)
    out = {}
    if not answers:
        return out
    pool = ThreadPoolExecutor(max_workers=min(8, len(answers)), thread_name_prefix="upnp-describe")
    try:
        jobs = {pool.submit(describe, location, sender, fetch): location for location, sender in answers.items()}
        done, _late = wait(jobs, timeout=deadline)
        for job in done:
            try:
                dev = job.result()
            except UpnpError:
                continue
            out[dev["id"]] = dev
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return out


# --- controlling one ------------------------------------------------------------------------------------------
def hms(seconds):
    seconds = max(0.0, float(seconds or 0))
    h, rest = divmod(int(seconds), 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}"


def seconds(value):
    """Seconds from "H:MM:SS(.fff)", or None ("NOT_IMPLEMENTED" and other junk)."""
    m = re.fullmatch(r"\s*(\d{1,4}):(\d{1,2}):(\d{1,2}(?:\.\d+)?)\s*", value or "")
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def didl(url, content_type, title="", artist="", album="", image="", duration=None):
    """DIDL-Lite metadata describing one song (what the TV shows while it plays)."""
    res_attrs = f' protocolInfo="http-get:*:{escape(content_type, {chr(34): "&quot;"})}:*"'
    if duration:
        res_attrs += f' duration="{hms(duration)}.000"'
    art = f"<upnp:albumArtURI>{escape(image)}</upnp:albumArtURI>" if image else ""
    return ('<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
            '<item id="1" parentID="0" restricted="1">'
            f"<dc:title>{escape(title or '')}</dc:title>"
            f"<upnp:artist>{escape(artist or '')}</upnp:artist>"
            f"<dc:creator>{escape(artist or '')}</dc:creator>"
            f"<upnp:album>{escape(album or '')}</upnp:album>{art}"
            "<upnp:class>object.item.audioItem.musicTrack</upnp:class>"
            f"<res{res_attrs}>{escape(url)}</res></item></DIDL-Lite>")


class Renderer:
    """One DLNA/UPnP renderer, controlled by SOAP requests. Each call blocks (run it on a worker thread)."""

    def __init__(self, device, request=http_request):
        self.device = device
        self._request = request

    def _soap(self, service, action, **args):
        url = self.device["controls"].get(service)
        if not url:
            raise UpnpError(f"the device has no {service.split(':')[-2]}")
        body = "".join(f"<{k}>{escape(str(v))}</{k}>" for k, v in args.items())
        envelope = ('<?xml version="1.0" encoding="utf-8"?>'
                    '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
                    's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
                    f'<u:{action} xmlns:u="{service}">{body}</u:{action}></s:Body></s:Envelope>').encode("utf-8")
        status, raw = self._request(url, "POST", envelope, {
            "Content-Type": 'text/xml; charset="utf-8"', "SOAPACTION": f'"{service}#{action}"'})
        root = safe_xml(raw) if raw.strip() else None
        if status != 200:
            code = desc = None
            if root is not None:
                for el in root.iter():
                    if _local(el.tag) == "errorCode":
                        code = (el.text or "").strip()
                    elif _local(el.tag) == "errorDescription":
                        desc = (el.text or "").strip()
            raise UpnpError(f"{action} failed: {(desc or str(status))[:200]}", (code or "")[:20] or None)
        out = {}
        if root is not None:
            for el in root.iter():
                if _local(el.tag) == f"{action}Response":
                    for c in el:
                        out[_local(c.tag)] = (c.text or "").strip()
        return out

    def load(self, url, content_type, title="", artist="", album="", image="", duration=None):
        meta = didl(url, content_type, title, artist, album, image, duration)
        try:
            self._soap(AVTRANSPORT, "Stop", InstanceID=0)
        except UpnpError:
            pass  # nothing was playing
        self._soap(AVTRANSPORT, "SetAVTransportURI", InstanceID=0, CurrentURI=url, CurrentURIMetaData=meta)

    def set_next(self, url, content_type, title="", artist="", album="", image="", duration=None):
        """Queue the next song for gapless playback; returns False if the device can't."""
        meta = didl(url, content_type, title, artist, album, image, duration)
        try:
            self._soap(AVTRANSPORT, "SetNextAVTransportURI", InstanceID=0, NextURI=url, NextURIMetaData=meta)
            return True
        except UpnpError:
            return False

    def play(self):
        self._soap(AVTRANSPORT, "Play", InstanceID=0, Speed=1)

    def pause(self):
        self._soap(AVTRANSPORT, "Pause", InstanceID=0)

    def stop(self):
        self._soap(AVTRANSPORT, "Stop", InstanceID=0)

    def seek(self, secs):
        self._soap(AVTRANSPORT, "Seek", InstanceID=0, Unit="REL_TIME", Target=hms(secs))

    def status(self):
        """{"state": PLAYING/PAUSED/STOPPED/TRANSITIONING/NO_MEDIA, "position", "duration", "uri"}."""
        info = self._soap(AVTRANSPORT, "GetTransportInfo", InstanceID=0)
        pos = self._soap(AVTRANSPORT, "GetPositionInfo", InstanceID=0)
        state = info.get("CurrentTransportState", "")
        state = {"PAUSED_PLAYBACK": "PAUSED", "NO_MEDIA_PRESENT": "NO_MEDIA"}.get(state, state)
        return {"state": state, "position": seconds(pos.get("RelTime")),
                "duration": seconds(pos.get("TrackDuration")), "uri": pos.get("TrackURI", "")[:2048]}

    def volume(self):
        """0..1, or None if the device doesn't say."""
        try:
            v = self._soap(RENDERING, "GetVolume", InstanceID=0, Channel="Master").get("CurrentVolume", "")
            return max(0, min(100, int(v))) / 100
        except (UpnpError, ValueError):
            return None

    def set_volume(self, level):
        self._soap(RENDERING, "SetVolume", InstanceID=0, Channel="Master",
                   DesiredVolume=round(100 * min(1.0, max(0.0, float(level)))))

    def set_muted(self, muted):
        self._soap(RENDERING, "SetMute", InstanceID=0, Channel="Master", DesiredMute=1 if muted else 0)

    def formats(self):
        """The audio types the device says it plays (lower-case MIME types), or an empty set if it won't say."""
        try:
            sink = self._soap(CONNECTION, "GetProtocolInfo").get("Sink", "")
        except UpnpError:
            return set()
        out = set()
        for entry in sink.split(",")[:500]:
            parts = entry.strip().split(":")
            if len(parts) >= 3 and parts[0] == "http-get" and parts[2].lower().startswith("audio/"):
                out.add(parts[2].lower().split(";")[0])
        return out


def local_interfaces():
    """This computer's IPv4 addresses that reach a network (for asking on each). Falls back to the default."""
    ips = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # no packet is sent: this only picks the outgoing address
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    ips = sorted(i for i in ips if not i.startswith("127."))
    return tuple(ips) or ("",)

