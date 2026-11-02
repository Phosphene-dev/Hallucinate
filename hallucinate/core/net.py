"""The one door to the internet. Every request Hallucinate makes goes through `urlopen` here, so offline mode
can close it in one place (tests/test_offline.py checks that nothing else calls urllib directly)."""
import http.client
import ipaddress
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request

from .i18n import fill, translate

_lock = threading.Lock()
_offline = False


class OfflineError(urllib.error.URLError):
    """Raised instead of connecting while offline mode is on. A URLError (so an OSError), which every caller
    already treats as "no network": nothing is cached as missing and queued scrobbles stay queued."""

    def __init__(self):
        super().__init__("Offline mode is on")

    def __str__(self):
        return "Offline mode is on"


def describe(exc):
    """A network or feed error in plain words, for showing to people instead of urllib's text
    ("<urlopen error [Errno -2] Name or service not known>")."""
    import http.client
    import socket
    import ssl

    if isinstance(exc, OfflineError):
        return translate("Net", "offline mode is on")
    if isinstance(exc, NotWebLink):
        return translate("Net", "that isn't a web link")
    if isinstance(exc, ResponseTooLarge):
        return translate("Net", "the server sent far more than expected")
    if isinstance(exc, urllib.error.HTTPError):
        return {401: translate("Net", "it needs a login"), 403: translate("Net", "the server refused"), 404: translate("Net", "nothing was found at that link"),
                410: translate("Net", "it's gone from that link"), 429: translate("Net", "the server is busy; try again later")}.get(
            exc.code, fill(translate("Net", "the server answered with an error (%1)"), exc.code) if exc.code < 500
            else translate("Net", "the server is having trouble; try again later"))
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(reason, (socket.timeout, TimeoutError)):
        return translate("Net", "the server took too long to answer")
    if isinstance(reason, ssl.SSLError):
        return translate("Net", "the secure connection couldn't be set up")
    if isinstance(reason, socket.gaierror):
        return translate("Net", "the server couldn't be found (check the link and your connection)")
    if isinstance(reason, ConnectionRefusedError):
        return translate("Net", "the server refused the connection")
    if isinstance(reason, (ConnectionError, http.client.HTTPException)):
        return translate("Net", "the connection dropped")
    if type(exc) is OSError and len(exc.args) == 1 and isinstance(exc.args[0], str):
        text = exc.args[0]  # one of ours, already in words
        return text[:1].lower() + text[1:]
    if isinstance(exc, urllib.error.URLError) or isinstance(reason, OSError):
        if "tunnel" in str(reason).lower() or "proxy" in str(reason).lower():
            return translate("Net", "the proxy wouldn't connect")
        return translate("Net", "the server couldn't be reached")
    if isinstance(exc, ValueError):
        text = str(exc).strip()
        return text[:1].lower() + text[1:] if text else translate("Net", "that doesn't look like what was expected")
    return str(exc)


def set_offline(on):
    global _offline
    with _lock:
        _offline = bool(on)


def is_offline():
    return _offline


# No answer Hallucinate expects is anywhere near this; a server sending more is broken or hostile.
MAX_RESPONSE = 32 * 1024 * 1024


class ResponseTooLarge(OSError, ValueError):
    """The server sent more than allowed. Both an OSError and a ValueError, so every caller's existing "bad
    answer" handling catches it."""


SCHEMES = ("http", "https")


class NotWebLink(urllib.error.URLError):
    """A link that isn't http(s): a feed, playlist or server can name file://, ftp:// or data: links, which
    urllib would happily open (a feed's "episode" at file:///home/you/.ssh/id_rsa would be copied into the
    downloads folder). Nothing Hallucinate fetches is anything but a web address."""

    def __init__(self, url):
        super().__init__(f"not a web link ({urllib.parse.urlsplit(url).scheme or 'no scheme'})")


def is_web_url(url):
    return isinstance(url, str) and urllib.parse.urlsplit(url.strip()).scheme.lower() in SCHEMES


class _WebOnlyRedirects(urllib.request.HTTPRedirectHandler):
    """Follow redirects only to other web addresses (urllib already refuses file://, but not ftp://)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urljoin(req.full_url, newurl)
        if not is_web_url(target):
            raise NotWebLink(newurl)
        # Python 3.10 doesn't know 308 (a permanent 307): asked as a 307 it's followed the same way
        new = super().redirect_request(req, fp, 307 if code == 308 else code, msg, headers, newurl)
        if new is not None:
            # Every hop, as (status, link), on the request the caller holds (`redirects`): a feed follows a
            # move for good (301, 308) but not a temporary one
            hops = getattr(req, "redirects", None)
            if hops is None:
                hops = req.redirects = []
            hops.append((code, target))
            new.redirects = hops
        old, to = urllib.parse.urlsplit(req.full_url), urllib.parse.urlsplit(target)
        if new is not None and (to.netloc != old.netloc or to.scheme.lower() != old.scheme.lower()):
            # urllib forwards every header: a token meant for one server mustn't reach the next one, nor go
            # out unencrypted when a secure link redirects to a plain one
            for name in list(new.headers):
                if name.lower() in ("authorization", "cookie"):
                    del new.headers[name]
            for name in list(new.unredirected_hdrs):
                if name.lower() in ("authorization", "cookie"):
                    del new.unredirected_hdrs[name]
        return new


# (Python 3.11 and later already handle 308 themselves)
if not hasattr(urllib.request.HTTPRedirectHandler, "http_error_308"):
    _WebOnlyRedirects.http_error_308 = urllib.request.HTTPRedirectHandler.http_error_302


urllib.request.install_opener(urllib.request.build_opener(_WebOnlyRedirects))


def _as_url_error(exc):
    """http.client's protocol errors (a cut-off body, a garbled status line, too many headers) aren't
    OSErrors, so callers' "no network" handling would miss them and a worker could die without reporting
    back. They become URLErrors, which every caller already handles."""
    err = urllib.error.URLError(f"the server's answer was broken ({type(exc).__name__})")
    err.__cause__ = exc
    return err


class _Limited:
    """A response that refuses to read past `limit` bytes in total."""

    def __init__(self, resp, limit):
        self._resp, self._left = resp, limit

    def read(self, amt=-1):
        want = self._left + 1 if amt is None or amt < 0 else min(amt, self._left + 1)
        try:
            data = self._resp.read(want)
        except http.client.HTTPException as exc:
            raise _as_url_error(exc) from exc
        self._left -= len(data)
        if self._left < 0:
            raise ResponseTooLarge("The server's answer was too large")
        return data

    def __getattr__(self, name):
        return getattr(self._resp, name)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._resp.close()
        return False


def urlopen(request, timeout=10, limit=MAX_RESPONSE):
    """Open a URL unless offline mode is on. Reading more than `limit` bytes raises ResponseTooLarge."""
    if _offline:
        raise OfflineError()
    url = request.full_url if isinstance(request, urllib.request.Request) else str(request)
    if not is_web_url(url):
        raise NotWebLink(url)
    try:
        resp = urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - http(s) only, checked above
    except http.client.HTTPException as exc:
        raise _as_url_error(exc) from exc
    return _Limited(resp, limit)


# --- the local network (casting) -------------------------------------------------------------------------------
class NotLocal(OSError):
    """An address that isn't on this computer's own network: casting never connects to the internet."""


def is_local_address(host):
    """Whether `host` is an address on a local network (private, link-local or this computer): never a name, which
    could resolve anywhere."""
    try:
        ip = ipaddress.ip_address(str(host).strip("[]"))
    except ValueError:
        return False
    if getattr(ip, "ipv4_mapped", None) is not None:
        ip = ip.ipv4_mapped
    return (ip.is_private or ip.is_link_local or ip.is_loopback) and not ip.is_multicast and not ip.is_unspecified


def same_address(a, b):
    """Whether two addresses are the same machine's, an IPv4 address and its IPv6-mapped form ("::ffff:1.2.3.4",
    as a dual-stack server sees IPv4 clients) counting as one."""
    def plain(x):
        try:
            ip = ipaddress.ip_address(str(x).strip("[]"))
        except ValueError:
            return None
        return getattr(ip, "ipv4_mapped", None) or ip
    pa, pb = plain(a), plain(b)
    return pa is not None and pa == pb


def _local_or_refuse(host):
    if _offline:
        raise OfflineError()
    if not is_local_address(host):
        raise NotLocal(f"not an address on your network: {host}")


def connect_local(host, port, timeout=10.0):
    """A TCP connection to a device on the local network (a Chromecast). Refused in offline mode, and for any
    address that isn't local."""
    _local_or_refuse(host)
    return socket.create_connection((host, int(port)), timeout=timeout)


def local_http(url, method="GET", body=None, headers=None, timeout=5.0, limit=512 * 1024):
    """(status, body) for one plain-HTTP request to a device on the local network (a DLNA renderer). Redirects
    aren't followed, the answer is capped at `limit` (raising ResponseTooLarge), offline mode and non-local
    addresses are refused."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "http" or not parts.hostname:
        raise NotLocal(f"not a plain local link: {url[:100]}")
    _local_or_refuse(parts.hostname)
    conn = http.client.HTTPConnection(parts.hostname, parts.port or 80, timeout=timeout)
    try:
        path = (parts.path or "/") + ("?" + parts.query if parts.query else "")
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        data = resp.read(limit + 1)
        if len(data) > limit:
            raise ResponseTooLarge("The device's answer was too large")
        return resp.status, data
    except http.client.HTTPException as exc:
        raise _as_url_error(exc) from exc
    finally:
        conn.close()
