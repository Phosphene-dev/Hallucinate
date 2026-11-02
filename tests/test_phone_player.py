"""The phone remote as the player: in a real browser (Chromium), the phone picks "This phone", plays what the
computer sends it, follows the computer's controls, moves on when a song ends, and hands back."""
import json
import shutil
import subprocess
import threading

import pytest
from audio import FFMPEG, encode
from conftest import wait_for
from test_webremote import remote  # noqa: F401 - the fixture

NODE = shutil.which("node")


def node_playwright():
    return bool(NODE) and subprocess.run([NODE, "-e", "require('playwright')"], capture_output=True).returncode == 0


pytestmark = pytest.mark.skipif(not (FFMPEG and node_playwright()), reason="needs ffmpeg and Node with Playwright")

# The phone: pairs, opens Play on, picks This phone, and plays until told to stop (stdin closes): then The computer.
PHONE = r"""
const { chromium } = require('playwright');
const [url, code] = process.argv.slice(2);
const log = (o) => console.log(JSON.stringify(o));
(async () => {
  const browser = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] });
  const page = await browser.newPage({ viewport: { width: 420, height: 860 } });
  page.on('pageerror', (e) => log({ pageerror: String(e) }));
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') log({ console: m.text() }); });
  try {
    await page.goto(url);
    await page.fill('#pairCode', code);
    await page.press('#pairCode', 'Enter');
    await page.waitForSelector('#app:not([hidden])');
    await page.waitForSelector('#btnCast:not([hidden])');
    await page.click('#btnCast');
    await page.click('#pickBody button:has-text("This phone")');
    log({ step: 'picked' });
    // play until the test closes stdin, then hand the music back
    await new Promise((resolve) => { process.stdin.on('end', resolve); process.stdin.resume(); });
    await page.click('#btnCast');
    await page.click('#pickBody button:has-text("The computer")');
    await page.waitForTimeout(500);
    log({ step: 'back' });
  } catch (e) {
    log({ error: String(e) });
  }
  await browser.close();
})();
"""


def test_the_phone_plays_the_music_itself(remote, qapp, tmp_path):  # noqa: F811
    from hallucinate.cast import Casting

    server, _lib, player = remote
    server.configure(enabled=True)
    casting = Casting(player)
    server.api.casting = casting
    casting.notify_remote = server._soon
    songs = [{"id": i, "path": str(encode(tmp_path / f"p{i}.flac", "flac", seconds=3.0)), "title": f"P{i}",
              "artist": "A", "album": "B", "duration": 3.0, "artUrl": ""} for i in range(3)]
    player.playList(songs, 0)
    assert wait_for(lambda: player.state == "Playing")
    script = tmp_path / "phone.js"
    script.write_text(PHONE)
    proc = subprocess.Popen([NODE, str(script), f"http://127.0.0.1:{server.port}/", server.new_code()],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    lines = []

    def read():
        for line in proc.stdout:
            try:
                lines.append(json.loads(line))
            except ValueError:
                pass
    threading.Thread(target=read, daemon=True).start()
    try:
        assert wait_for(lambda: player.casting, timeout=60), lines
        assert not [x for x in lines if "error" in x], lines
        assert casting.deviceKind == "phone"
        assert wait_for(lambda: player.state == "Playing" and player.position > 200, timeout=45), (player.state, lines[-3:])
        assert all(v.player.playbackState().name != "PlayingState" for v in player._voices)  # the computer is quiet
        player.next()  # the computer's controls drive the phone
        assert wait_for(lambda: player.currentIndex == 1 and player.state == "Playing" and player.position > 200,
                        timeout=45)
        assert wait_for(lambda: player.currentIndex == 2, timeout=45)  # the song ended on the phone: the next one
        player.pause()
        assert wait_for(lambda: player.state == "Paused", timeout=10)
    finally:
        proc.stdin.close()  # the phone picks "The computer" (the event loop runs meanwhile: it answers the phone)
        assert wait_for(lambda: proc.poll() is not None, timeout=60)
    assert wait_for(lambda: not player.casting, timeout=10), lines[-3:]
    assert player.currentIndex == 2
    casting.shutdown()
    server.api.casting, casting.notify_remote = None, (lambda: None)  # (the two point at each other)
