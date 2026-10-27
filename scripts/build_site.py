"""Build the website into a folder: python scripts/build_site.py [OUT] [--flatpak-repo DIR] (default: _site).

Fills site/index.html with the current version, its release date and its CHANGELOG entry, and copies the
README screenshots, logo and social preview next to it. The Pages workflow runs this on every release and
whenever the site, screenshots or changelog change, so the site always matches the latest release.

With --flatpak-repo (the signed repository from the newest release, see packaging/flatpak/README.md) the site
also serves it at flatpak/repo/, with the .flatpakref and .flatpakrepo files software centres open, and the
download section offers it."""
import argparse
import base64
import datetime
import html
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "https://github.com/Phosphene-dev/Hallucinate"
SITE_URL = os.environ.get("SITE_URL", "https://phosphene-dev.github.io/Hallucinate/")
FLATPAK_KEY = ROOT / "packaging" / "flatpak" / "hallucinate-repo.gpg"
APP_ID = "io.github.phosphene_dev.Hallucinate"
WAVE_HEIGHTS = [10, 18, 28, 40, 26, 48, 34, 56, 34, 48, 26, 40, 28, 18, 10]


def project_version():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version\s*=\s*"([^"]+)"', text, re.M).group(1)


def released_version():
    """The newest vX.Y.Z tag, so a version bump merged ahead of its release doesn't advertise it early.

    Falls back to pyproject.toml when there are no tags (e.g. a shallow checkout); SITE_VERSION overrides."""
    if os.environ.get("SITE_VERSION"):
        return os.environ["SITE_VERSION"]
    try:
        tags = subprocess.run(["git", "tag", "--list", "v[0-9]*", "--sort=-v:refname"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        tags = []
    return tags[0][1:] if tags else project_version()


def changelog_entry(version):
    """(date, markdown body) of the CHANGELOG section for `version`."""
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(rf"^## \[{re.escape(version)}\](?: - (\S+))?\s*$(.*?)(?=^## \[|\Z)", text, re.M | re.S)
    if not match:
        raise SystemExit(f"CHANGELOG.md has no section for {version}")
    return match.group(1), match.group(2).strip()


def inline(text):
    """Markdown inline code and links to HTML; everything else is escaped."""
    out = []
    for part in re.split(r"(`[^`]+`|\[[^\]]+\]\([^)]+\))", text):
        if part.startswith("`") and part.endswith("`"):
            out.append(f"<code>{html.escape(part[1:-1])}</code>")
        elif part.startswith("[") and "](" in part:
            label, url = re.match(r"\[([^\]]+)\]\(([^)]+)\)", part).groups()
            out.append(f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>')
        else:
            out.append(html.escape(part).replace("**", ""))
    return "".join(out)


def render_changes(markdown):
    """The small subset of Markdown the changelog uses: ### headings and "- " bullets (wrapped lines allowed)."""
    lines, items, out = markdown.splitlines(), [], []

    def flush():
        if items:
            out.append("<ul>" + "".join(f"<li>{inline(i)}</li>" for i in items) + "</ul>")
            items.clear()

    for line in lines:
        if line.startswith("### "):
            flush()
            out.append(f"<h3>{html.escape(line[4:].strip())}</h3>")
        elif line.startswith("- "):
            items.append(line[2:].strip())
        elif line.strip() and items:
            items[-1] += " " + line.strip()  # continuation of a wrapped bullet
    flush()
    return "\n        ".join(out)


def pretty_date(iso):
    if not iso:
        return "latest release"
    date = datetime.date.fromisoformat(iso)
    return f"{date:%B} {date.day}, {date.year}"


def flatpak_files(out, repo):
    """Serve the Flatpak repository and write the files that add it. False when there is none to serve."""
    if not repo or not (Path(repo) / "config").is_file() or not FLATPAK_KEY.is_file():
        return False
    shutil.copytree(repo, out / "flatpak" / "repo")
    key = base64.b64encode(FLATPAK_KEY.read_bytes()).decode()
    url = f"{SITE_URL}flatpak/repo/"
    icon = f"{SITE_URL}img/icon-64.png"
    common = (f"Title=Hallucinate\nUrl={url}\nHomepage={SITE_URL}\nIcon={icon}\n"
              f"Comment=A music player for your own library\nGPGKey={key}\n")
    (out / "flatpak" / "hallucinate.flatpakrepo").write_text("[Flatpak Repo]\n" + common, encoding="utf-8")
    (out / "hallucinate.flatpakref").write_text(
        f"[Flatpak Ref]\nName={APP_ID}\nBranch=stable\nIsRuntime=false\nSuggestRemoteName=hallucinate\n"
        "RuntimeRepo=https://dl.flathub.org/repo/flathub.flatpakrepo\n" + common, encoding="utf-8")
    return True


def newest_with(pattern, releases=None):
    """The newest release with an asset whose name matches `pattern`, as (its page, {name: download URL}), or
    None. Point releases carry only the AppImage, Flatpak and Windows builds; macOS and the .deb/.rpm come with
    the bigger ones, so their links go to the newest release that has them, not to "latest"."""
    if releases is None:
        try:
            r = subprocess.run(["gh", "api", "repos/Phosphene-dev/Hallucinate/releases?per_page=30"],
                               capture_output=True, text=True, timeout=60, check=True)
            releases = json.loads(r.stdout)
        except (OSError, subprocess.SubprocessError, ValueError):
            return None
    for rel in releases:
        if rel.get("draft") or rel.get("prerelease"):
            continue
        assets = {a.get("name", ""): a.get("browser_download_url", "") for a in rel.get("assets") or []}
        if any(re.fullmatch(pattern, name) for name in assets):
            return rel.get("html_url", f"{REPO}/releases"), assets
    return None


def build(out, flatpak_repo=None, releases=None):
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "site", out)
    shutil.copytree(ROOT / "docs" / "screenshots", out / "screenshots")
    shutil.copy2(ROOT / "assets" / "logo" / "social-preview.png", out / "img" / "social-preview.png")
    if FLATPAK_KEY.is_file():  # the public key that signs the downloads' checksums and the Flatpak
        shutil.copy2(FLATPAK_KEY, out / "hallucinate-signing-key.gpg")

    version = released_version()
    date, changes = changelog_entry(version)
    wave = "".join(f'<b style="height:{h}px;animation-delay:-{i * 0.13:.2f}s"></b>'
                   for i, h in enumerate(WAVE_HEIGHTS))
    values = {
        "VERSION": version, "RELEASE_DATE": pretty_date(date), "CHANGES": render_changes(changes),
        "WAVE": wave, "REPO": REPO, "RELEASES": f"{REPO}/releases", "SITE_URL": SITE_URL,
    }
    mac = newest_with(r"Hallucinate-macos-arm64\.zip", releases)
    values["MAC_URL"] = mac[1]["Hallucinate-macos-arm64.zip"] if mac else f"{REPO}/releases/latest/download/Hallucinate-macos-arm64.zip"
    packages = newest_with(r"hallucinate.*\.(deb|rpm)", releases)
    values["PACKAGES_URL"] = packages[0] if packages else f"{REPO}/releases/latest"
    if flatpak_files(out, flatpak_repo):
        values["LINUX_MORE"] = (
            'Prefer Flatpak? <a href="hallucinate.flatpakref">Install it from our signed repository</a> and it '
            f'updates with your other apps, or get the <a href="{REPO}/releases/latest/download/Hallucinate-x86_64.flatpak">'
            'single-file bundle</a>. Software centres may call it "unverified": it isn\'t on Flathub, but it is '
            f'signed. Arch users can build the <a href="{REPO}#arch-linux">package</a> from source.')
    else:
        values["LINUX_MORE"] = f'Flatpak and Arch (AUR) packages can be <a href="{REPO}#install">built from source</a>.'

    page = (out / "index.html").read_text(encoding="utf-8")
    page = re.sub(r"\{\{([A-Z_]+)\}\}", lambda m: values[m.group(1)], page)
    (out / "index.html").write_text(page, encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")  # serve files as-is
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default=ROOT / "_site")
    ap.add_argument("--flatpak-repo")
    args = ap.parse_args()
    print(build(args.out, args.flatpak_repo))
