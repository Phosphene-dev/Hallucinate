"""The web remote's queue in a real browser: songs move by their handle (dragged, or with the arrow keys), and a
swipe sideways takes one out, with Undo. Drives Chromium through Node's Playwright; skipped where it isn't there."""
import json
import shutil
import subprocess
import threading

import pytest
from conftest import wait_for
from test_webremote import remote  # noqa: F401 - the fixture

NODE = shutil.which("node")


def node_playwright():
    if not NODE:
        return False
    return subprocess.run([NODE, "-e", "require('playwright')"], capture_output=True).returncode == 0


pytestmark = pytest.mark.skipif(not node_playwright(), reason="needs Node with Playwright")

STEPS = r"""
const { chromium } = require('playwright');
const [url, code] = process.argv.slice(2);
const titles = (page) => page.$$eval('#queueList .row .title > span:first-child', (els) => els.map((e) => e.textContent));
const firstIsNot = (page, t) => page.waitForFunction(
  (t) => document.querySelector('#queueList .row .title > span').textContent !== t, t);
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 420, height: 860 }, hasTouch: true });
  const seen = {};
  try {
    await page.goto(url);
    await page.fill('#pairCode', code);
    await page.press('#pairCode', 'Enter');
    await page.waitForSelector('#app:not([hidden])');
    await page.click('button[data-view=queue]');
    await page.waitForSelector('#queueList .row');
    seen.first = await titles(page);
    // the arrow keys on a handle move its song
    await page.focus('#queueList .row:nth-child(1) .grip');
    await page.keyboard.press('ArrowDown');
    await firstIsNot(page, seen.first[0]);
    seen.keyed = await titles(page);
    await page.waitForTimeout(700);  // (the server's "queue changed" event redraws the list once more)
    // a redraw while a song is held waits until it's let go
    await page.evaluate(() => { queueGesture = true; loadQueue(); });
    const held = await page.evaluate(() => queueStale);
    await page.evaluate(() => gestureDone());
    seen.heldRedraw = held;
    await page.waitForTimeout(500);
    // dragging a handle down past the next row
    const grip = await page.locator('#queueList .row:nth-child(1) .grip').boundingBox();
    const rowH = (await page.locator('#queueList .row:nth-child(1)').boundingBox()).height;
    const gx = grip.x + grip.width / 2, gy = grip.y + grip.height / 2;
    await page.mouse.move(gx, gy);
    await page.mouse.down();
    await page.mouse.move(gx, gy + rowH * 1.1, { steps: 8 });
    await page.mouse.up();
    await firstIsNot(page, seen.keyed[0]);
    seen.dragged = await titles(page);
    await page.waitForTimeout(700);
    // a finger swiping the last one sideways takes it out, and Undo puts it back
    const row = await page.locator('#queueList .row:last-child').boundingBox();
    await page.evaluate(([x0, y, w]) => {
      const r = document.querySelector('#queueList .row:last-child');
      const ev = (type, x) => r.dispatchEvent(new PointerEvent(type, { pointerId: 7, pointerType: 'touch',
        clientX: x, clientY: y, bubbles: true }));
      ev('pointerdown', x0);
      for (let k = 1; k <= 10; k++) ev('pointermove', x0 + k * w * 0.07);
      ev('pointerup', x0 + w * 0.7);
    }, [row.x + 20, row.y + row.height / 2, row.width]);
    await page.waitForFunction((n) => document.querySelectorAll('#queueList .row').length === n - 1, seen.first.length);
    seen.swiped = await titles(page);
    await page.click('#toast button');
    await page.waitForFunction((n) => document.querySelectorAll('#queueList .row').length === n, seen.first.length);
    seen.undone = await titles(page);
  } catch (e) {
    seen.error = String(e);
  }
  await browser.close();
  console.log(JSON.stringify(seen));
})();
"""


def test_queue_moves_by_its_handle_and_swipes_away(remote, tmp_path):  # noqa: F811
    server, lib, player = remote
    server.configure(enabled=True)
    albums = server.api.call("albums", {})["albums"]
    ids = [s["id"] for a in albums for s in server.api.call("album", {"key": a["key"]})["songs"]][:4]
    assert len(ids) >= 3
    server.api.call("play.songs", {"ids": ids})
    player.pause()
    script = tmp_path / "queue.js"
    script.write_text(STEPS)
    out = {}

    # the browser runs on another thread: the server answers its commands on this one, which must keep spinning
    def go():
        r = subprocess.run([NODE, str(script), f"http://127.0.0.1:{server.port}/", server.new_code()],
                           capture_output=True, text=True, timeout=90)
        out["stdout"], out["stderr"] = r.stdout, r.stderr

    t = threading.Thread(target=go)
    t.start()
    assert wait_for(lambda: not t.is_alive(), timeout=100)
    seen = json.loads(out["stdout"].strip().splitlines()[-1]) if out.get("stdout") else {"error": out.get("stderr")}
    assert "error" not in seen, seen
    first = seen["first"]
    assert len(first) >= 3
    assert seen["keyed"][:2] == [first[1], first[0]]
    assert seen["heldRedraw"] is True
    assert seen["dragged"][:2] == [first[0], first[1]]  # dragged back down past the other
    assert seen["swiped"] == seen["dragged"][:-1]
    assert sorted(seen["undone"]) == sorted(first)
