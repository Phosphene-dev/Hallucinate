"""Installing updates from inside the app: only where it owns its files, and only a download that matches."""
import hashlib
import io
from types import SimpleNamespace

import pytest

from hallucinate import selfupdate, updates

PAYLOAD = b"new hallucinate build" * 1000
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()
URL = selfupdate.DOWNLOAD_PREFIX + "v9.0.0/hallucinate-9.0.0-x86_64.AppImage"


def release_assets(digest=DIGEST, url=URL, size=len(PAYLOAD)):
    return [
        {"name": "hallucinate-9.0.0-windows-x64-setup.exe", "url": selfupdate.DOWNLOAD_PREFIX + "v9.0.0/x.exe",
         "size": 10, "digest": "sha256:" + "0" * 64},
        {"name": "hallucinate-9.0.0-x86_64.AppImage", "url": url, "size": size, "digest": f"sha256:{digest}"},
    ]


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def opener_for(data):
    return lambda req, timeout, limit=None: Resp(data)


def test_install_kind_only_where_the_app_owns_its_files(tmp_path):
    image = tmp_path / "Hallucinate.AppImage"
    image.write_bytes(b"x")
    assert selfupdate.install_kind({"APPIMAGE": str(image)}, "linux", False, "/usr/bin/python3") == "appimage"
    assert selfupdate.install_kind({"APPIMAGE": str(image), "FLATPAK_ID": "x"}, "linux", False, "/x") == ""
    assert selfupdate.install_kind({}, "linux", False, "/usr/bin/python3") == ""  # pip, AUR, distro packages
    exe = tmp_path / "Hallucinate" / "Hallucinate.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"")
    assert selfupdate.install_kind({}, "win32", True, str(exe)) == ""  # the portable zip
    (exe.parent / "unins000.exe").write_bytes(b"")
    assert selfupdate.install_kind({}, "win32", True, str(exe)) == "windows"  # installed with the setup program
    assert selfupdate.install_kind({}, "darwin", True, "/Applications/Hallucinate.app/x") == ""


def test_pick_asset_needs_the_right_file_a_github_url_and_a_digest():
    picked = selfupdate.pick_asset(release_assets(), "9.0.0", "appimage")
    assert picked == {"name": "hallucinate-9.0.0-x86_64.AppImage", "url": URL, "size": len(PAYLOAD), "sha256": DIGEST}
    assert selfupdate.pick_asset(release_assets(), "9.0.1", "appimage") is None
    assert selfupdate.pick_asset(release_assets(url="https://example.com/evil.AppImage"), "9.0.0", "appimage") is None
    assert selfupdate.pick_asset(release_assets(digest="nothex"), "9.0.0", "appimage") is None
    assert selfupdate.pick_asset([{**release_assets()[1], "digest": None}], "9.0.0", "appimage") is None


def test_download_checks_size_and_checksum(tmp_path):
    asset = selfupdate.pick_asset(release_assets(), "9.0.0", "appimage")
    seen = []
    out = selfupdate.download(asset, tmp_path / "ok", seen.append, opener=opener_for(PAYLOAD))
    assert out.read_bytes() == PAYLOAD and seen[-1] == 1.0
    for bad in (PAYLOAD[:-1] + b"!", PAYLOAD[:-5], PAYLOAD + b"more"):
        with pytest.raises(ValueError):
            selfupdate.download(asset, tmp_path / "bad", opener=opener_for(bad))
        assert not (tmp_path / "bad").exists()  # never left behind half-checked
    with pytest.raises(OSError, match="cancelled"):
        selfupdate.download(asset, tmp_path / "c", cancelled=lambda: True, opener=opener_for(PAYLOAD))
    assert not (tmp_path / "c").exists()


def test_download_respects_offline_mode(tmp_path):
    from hallucinate.core import net

    asset = selfupdate.pick_asset(release_assets(), "9.0.0", "appimage")
    net.set_offline(True)
    try:
        with pytest.raises(OSError, match="Offline"):
            selfupdate.download(asset, tmp_path / "x")
    finally:
        net.set_offline(False)


def test_swap_appimage_replaces_and_relaunches_after_exit(tmp_path):
    target = tmp_path / "Hallucinate.AppImage"
    target.write_bytes(b"old")
    new = tmp_path / ".new"
    new.write_bytes(b"new")
    calls = []
    env = {"HOME": "/home/me", "APPIMAGE": str(target), "APPDIR": "/tmp/.mount_abc", "ARGV0": "x",
           "LD_LIBRARY_PATH": "/tmp/.mount_abc/usr/lib", "PATH": "/usr/bin"}
    selfupdate.verified(new, hashlib.sha256(b"new").hexdigest())  # as the updater does, just before swapping
    selfupdate.swap_appimage(new, target, 4242, env, popen=lambda args, **kw: calls.append((args, kw)))
    assert target.read_bytes() == b"new" and not new.exists() and target.stat().st_mode & 0o111
    args, kw = calls[0]
    assert "kill -0 4242" in args[2] and str(target) in args[2]
    assert kw["env"] == {"HOME": "/home/me", "PATH": "/usr/bin"}  # the old mount's paths are gone
    assert kw["start_new_session"]


def test_windows_installer_runs_silently():
    calls = []
    selfupdate.run_windows_installer("C:/Temp/setup.exe", popen=lambda args, **kw: calls.append(args))
    assert calls == [["C:/Temp/setup.exe", "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]]


def test_install_now_downloads_checks_and_swaps(qapp, tmp_path, monkeypatch):
    from conftest import wait_for

    image = tmp_path / "Hallucinate.AppImage"
    image.write_bytes(b"old")
    monkeypatch.setenv("APPIMAGE", str(image))
    swapped, quits = [], []
    monkeypatch.setattr(updates.selfupdate, "swap_appimage", lambda new, target, pid: swapped.append((new, target)))
    monkeypatch.setattr(updates, "QCoreApplication", SimpleNamespace(quit=lambda: quits.append(1)))

    def fake_download(asset, dest, progress, cancelled):
        progress(0.5)
        return selfupdate.download(asset, dest, progress, cancelled, opener=opener_for(PAYLOAD))

    latest = {"version": "9.0.0", "url": "https://github.com/x", "assets": release_assets()}
    checker = updates.UpdateChecker(fetch=lambda: latest, kind="appimage", download=fake_download)
    try:
        assert checker.canInstall
        checker.installNow()
        assert wait_for(lambda: swapped and quits, timeout=4)
        new, target = swapped[0]
        assert target == str(image) and open(new, "rb").read() == PAYLOAD
        assert not checker.installing and "Installing" in checker.status
    finally:
        checker.shutdown()


def test_install_now_refuses_a_bad_download(qapp, tmp_path, monkeypatch):
    from conftest import wait_for

    image = tmp_path / "Hallucinate.AppImage"
    image.write_bytes(b"old")
    monkeypatch.setenv("APPIMAGE", str(image))
    monkeypatch.setattr(updates.selfupdate, "swap_appimage", lambda *a: pytest.fail("installed a bad file"))

    def tampered(asset, dest, progress, cancelled):
        return selfupdate.download(asset, dest, progress, cancelled, opener=opener_for(b"tampered"))

    latest = {"version": "9.0.0", "url": "https://github.com/x", "assets": release_assets()}
    checker = updates.UpdateChecker(fetch=lambda: latest, kind="appimage", download=tampered)
    try:
        checker.installNow()
        assert wait_for(lambda: not checker.installing, timeout=4)
        assert "checksum" in checker.status or "larger" in checker.status
        assert image.read_bytes() == b"old" and list(tmp_path.glob(".*part")) == []
    finally:
        checker.shutdown()


def test_no_self_install_for_packaged_copies():
    assert updates.system_package(frozen=False, module="/usr/lib/python3.13/site-packages/hallucinate/updates.py")
    assert not updates.system_package(frozen=False, module="/home/me/src/hallucinate/updates.py")
    assert not updates.system_package(frozen=True, module="/usr/whatever")
    checker = updates.UpdateChecker(kind="")
    assert not checker.canInstall
    checker.shutdown()


def test_an_update_swapped_after_its_check_is_refused(tmp_path):
    good = hashlib.sha256(b"release").hexdigest()
    part = tmp_path / ".x.part"
    part.write_bytes(b"something else")
    with pytest.raises(ValueError):
        selfupdate.verified(part, good)
    part.unlink()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.write_bytes(b"release")
    part.symlink_to(elsewhere)
    with pytest.raises(ValueError):
        selfupdate.verified(part, good)  # a link put in its place isn't followed


def test_a_download_never_writes_through_a_planted_link(tmp_path):
    victim = tmp_path / "victim"
    victim.write_bytes(b"precious")
    dest = tmp_path / ".x.part"
    dest.symlink_to(victim)

    class Resp:
        def __init__(self):
            self.left = [b"abc"]

        def read(self, n):
            return self.left.pop() if self.left else b""

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    asset = {"url": "https://example/x", "size": 3, "sha256": hashlib.sha256(b"abc").hexdigest()}
    selfupdate.download(asset, dest, opener=lambda req, timeout=0, limit=0: Resp())
    assert victim.read_bytes() == b"precious" and dest.read_bytes() == b"abc" and not dest.is_symlink()
