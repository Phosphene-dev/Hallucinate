"""The website build (scripts/build_site.py): every placeholder filled, every local file present."""
import base64
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_site  # noqa: E402


class _Refs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in ("src", "href", "srcset") and value:
                self.refs.append(value)


def test_site_builds_with_local_assets(tmp_path, monkeypatch):
    monkeypatch.setenv("SITE_VERSION", build_site.project_version())
    out = build_site.build(tmp_path / "site", releases=[])
    page = (out / "index.html").read_text(encoding="utf-8")
    assert "{{" not in page and "}}" not in page
    assert f"Download Hallucinate {build_site.project_version()}" in page
    parser = _Refs()
    parser.feed(page)
    local = {re.split(r"[?#]", r)[0] for r in parser.refs if not r.startswith(("http", "#", "mailto:"))}
    assert local, "no local references found"
    missing = [r for r in local if not (out / r).is_file()]
    assert not missing, missing
    assert (out / ".nojekyll").exists()


def test_changelog_rendering():
    html = build_site.render_changes(
        "### Added\n- Radio mode with `code` and a [link](https://example.com).\n  Wrapped line.\n"
        "- Escapes <script>\n\n### Fixed\n- A fix"
    )
    assert html.count("<h3>") == 2 and html.count("<li>") == 3
    assert "<code>code</code>" in html and '<a href="https://example.com">link</a>' in html
    assert "Wrapped line." in html and "&lt;script&gt;" in html


def test_released_version_override(monkeypatch):
    monkeypatch.setenv("SITE_VERSION", "9.9.9")
    assert build_site.released_version() == "9.9.9"


def test_flatpak_repository_is_served_with_install_files(tmp_path, monkeypatch):
    monkeypatch.setenv("SITE_VERSION", build_site.project_version())
    key = tmp_path / "key.gpg"
    key.write_bytes(b"\x99\x01public key bytes")
    monkeypatch.setattr(build_site, "FLATPAK_KEY", key)
    repo = tmp_path / "flatpak-repo"
    (repo / "objects").mkdir(parents=True)
    (repo / "config").write_text("[core]\nrepo_version=1\nmode=archive-z2\n")
    (repo / "summary").write_bytes(b"summary")

    out = build_site.build(tmp_path / "site", repo, releases=[])
    page = (out / "index.html").read_text(encoding="utf-8")
    assert 'href="hallucinate.flatpakref"' in page and "Hallucinate-x86_64.flatpak" in page
    assert (out / "flatpak" / "repo" / "summary").read_bytes() == b"summary"
    ref = (out / "hallucinate.flatpakref").read_text()
    assert ref.startswith("[Flatpak Ref]\n") and "Name=io.github.phosphene_dev.Hallucinate\n" in ref
    assert "Branch=stable\n" in ref and f"Url={build_site.SITE_URL}flatpak/repo/\n" in ref
    assert f"GPGKey={base64.b64encode(key.read_bytes()).decode()}\n" in ref
    assert (out / "flatpak" / "hallucinate.flatpakrepo").read_text().startswith("[Flatpak Repo]\n")
    assert (out / "img" / "icon-64.png").is_file()

    # without a repository (or before any release has one) the page points at building from source
    out = build_site.build(tmp_path / "plain", tmp_path / "missing", releases=[])
    page = (out / "index.html").read_text(encoding="utf-8")
    assert 'href="hallucinate.flatpakref"' not in page and "built from source" in page
    assert not (out / "flatpak").exists()


def test_mac_and_package_links_go_to_the_newest_release_that_has_them(tmp_path):
    """Point releases carry only the AppImage, Flatpak and Windows builds: the Mac button and the .deb/.rpm link
    go to the newest release with those, not to "latest" (which would 404)."""
    base = "https://github.com/Phosphene-dev/Hallucinate/releases"
    releases = [
        {"html_url": base + "/tag/v1.6.1", "assets": [{"name": "Hallucinate-x86_64.AppImage", "browser_download_url": "a"}]},
        {"html_url": base + "/tag/v1.6.0-rc", "prerelease": True,
         "assets": [{"name": "Hallucinate-macos-arm64.zip", "browser_download_url": "rc"}]},
        {"html_url": base + "/tag/v1.6.0", "assets": [
            {"name": "Hallucinate-macos-arm64.zip", "browser_download_url": base + "/download/v1.6.0/Hallucinate-macos-arm64.zip"},
            {"name": "hallucinate_1.6.0_amd64.deb", "browser_download_url": "d"}]},
    ]
    page = (build_site.build(tmp_path / "site", releases=releases) / "index.html").read_text(encoding="utf-8")
    assert 'href="' + base + '/download/v1.6.0/Hallucinate-macos-arm64.zip"' in page
    assert 'href="' + base + '/tag/v1.6.0">.deb or .rpm' in page
    page = (build_site.build(tmp_path / "none", releases=[]) / "index.html").read_text(encoding="utf-8")
    assert "/releases/latest/download/Hallucinate-macos-arm64.zip" in page  # nothing known: the usual link
