// Hallucinate's web interface and phone remote. Plain JavaScript, no libraries: everything it shows comes from
// the computer running Hallucinate (api.py), and every piece of text from the library is set as text, never as
// HTML, so a song title can't turn into markup or script.
"use strict";

const $ = (id) => document.getElementById(id);
let state = null;          // the latest state from the computer
let stateAt = 0;           // when it arrived (for counting the position on between updates)
let dragging = false;      // the seek bar is being dragged
let currentView = "now";
let libKind = "albums";
let detail = null;         // what the detail view shows: {kind, ...}
let menuSong = null;       // the song the song menu is for
let events = null;

// --- talking to the computer -----------------------------------------------------------------------------
async function call(method, params = {}) {
  const res = await fetch("api/call", {
    method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-Hallucinate": "1" },
    body: JSON.stringify({ method, params }),
  });
  if (res.status === 401) { showPairing(); throw new Error("not paired"); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { toast(data.error || "That didn't work"); throw new Error(data.error || res.status); }
  return data.result;
}

function art(albumKey, size = 256) {
  return albumKey ? `art/${encodeURIComponent(albumKey)}?s=${size}` : "";
}

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "text") e.textContent = v;
    else if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) e.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids) if (kid) e.append(kid);
  return e;
}

// An album without a cover: a clear pixel, so the soft placeholder behind it shows instead of a broken image
const NO_ART = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";
function noArt(i) {
  i.addEventListener("error", () => { if (i.src !== NO_ART) i.src = NO_ART; });
}

function img(albumKey, size, cls) {
  const i = el("img", { alt: "", loading: "lazy", class: cls });
  noArt(i);
  i.src = albumKey ? art(albumKey, size) : NO_ART;
  return i;
}

function fmt(seconds) {
  seconds = Math.max(0, Math.floor(seconds || 0));
  const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = seconds % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
}

let toastTimer = 0;
function toast(text) {
  const t = $("toast");
  t.textContent = text;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 2200);
}

// --- pairing ---------------------------------------------------------------------------------------------
function showPairing() {
  if (events) { events.close(); events = null; }
  $("app").hidden = true;
  $("pair").hidden = false;
  // nothing of the song stays behind the pairing form (#134); it's drawn afresh once paired again
  $("backdrop").style.backgroundImage = "none";
  render.key = undefined;
  $("pairCode").focus();
}

$("pairForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("pairError").textContent = "";
  const res = await fetch("api/pair", {
    method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-Hallucinate": "1" },
    body: JSON.stringify({ code: $("pairCode").value.trim(), name: $("pairName").value.trim() || guessName() }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { $("pairError").textContent = data.error || "That didn't work"; return; }
  $("pairCode").value = "";
  start();
});

function guessName() {
  const ua = navigator.userAgent;
  if (/iPhone/.test(ua)) return "iPhone";
  if (/iPad/.test(ua)) return "iPad";
  if (/Android/.test(ua)) return "Android phone";
  if (/Mac/.test(ua)) return "Mac browser";
  if (/Windows/.test(ua)) return "Windows browser";
  return "Browser";
}

// --- live state ------------------------------------------------------------------------------------------
function connect() {
  if (events) events.close();
  events = new EventSource("api/events");
  events.addEventListener("state", (e) => { state = JSON.parse(e.data); stateAt = Date.now(); render(); syncWakeLock(); });
  events.addEventListener("queue", () => { if (currentView === "queue") loadQueue(); });
  events.onerror = async () => {
    const hello = await fetch("api/hello", { credentials: "same-origin" }).then((r) => r.json()).catch(() => null);
    if (hello && !hello.paired) showPairing();
  };
}

function position() {
  if (!state) return 0;
  let pos = state.position;
  if (state.playing) pos += Date.now() - stateAt;
  return Math.min(pos, state.duration || pos);
}

function render() {
  const s = state;
  if (!s) return;
  const song = s.song;
  $("nowTitle").replaceChildren(song ? (song.streamTitle || song.title) : "Nothing playing",
    ...(song && !song.streamTitle ? badges(song) : []));
  $("nowArtist").textContent = song ? song.artist : "";
  $("nowAlbum").textContent = song ? [song.album, song.year || ""].filter(Boolean).join(" · ") : "";
  const key = song && song.albumKey;
  loadLyrics();
  if (key !== render.key) {
    render.key = key;
    $("nowArt").hidden = !key;
    $("nowArtEmpty").hidden = !!key;
    if (key) $("nowArt").src = art(key, 512);
    $("miniArt").src = key ? art(key, 64) : NO_ART;
    $("backdrop").style.backgroundImage = key ? `url("${art(key, 128)}")` : "none";
  }
  document.body.classList.toggle("playing", !!s.playing);
  $("icoPlay").toggleAttribute("hidden", s.playing);  // (an svg has no .hidden: #124)
  $("icoPause").toggleAttribute("hidden", !s.playing);
  $("btnPlay").setAttribute("aria-label", s.playing ? "Pause" : "Play");
  $("miniIco").setAttribute("d", s.playing ? "M7 5h4v14H7zM13 5h4v14h-4z" : "M8 5l11 7-11 7z");
  $("btnShuffle").classList.toggle("on", s.shuffle);
  $("btnRepeat").classList.toggle("on", s.repeat > 0);
  $("repeatOne").hidden = s.repeat !== 2;
  $("btnRadio").classList.toggle("on", s.radio);
  $("btnSleep").classList.toggle("on", s.sleepRemaining >= 0 || s.sleepAfterTrack || s.sleepAfterAlbum);
  $("btnLike").classList.toggle("on", !!(song && song.liked));
  $("btnLike").hidden = !(song && song.id);
  if (document.activeElement !== $("volume")) $("volume").value = Math.round(s.volume * 100);
  $("nowError").textContent = s.error || "";
  $("mini").hidden = !song || currentView === "now";
  $("miniTitle").textContent = song ? (song.streamTitle || song.title) : "";
  $("miniArtist").textContent = song ? song.artist : "";
  document.title = song ? `${song.title} · Hallucinate` : "Hallucinate";
  tick();
  if (currentView === "queue") markCurrent();
}

function tick() {
  if (!state) return;
  // a radio station has no end: how long you've listened, a bar that can't be moved, and LIVE (#138)
  const live = !!(state.song && state.song.kind === "station");
  const dur = state.duration / 1000, pos = position() / 1000;
  $("seek").disabled = live;
  $("seek").classList.toggle("live", live);
  if (!dragging) $("seek").value = live ? 1000 : dur ? Math.round((pos / dur) * 1000) : 0;
  $("posText").textContent = fmt(pos);
  $("durText").textContent = live ? "LIVE" : fmt(dur);
  $("durText").classList.toggle("live", live);
}
setInterval(tick, 500);

// --- now playing controls --------------------------------------------------------------------------------
$("btnPlay").onclick = () => call("toggle");
$("miniPlay").onclick = (e) => { e.stopPropagation(); call("toggle"); };
$("mini").onclick = () => show("now");
$("btnNext").onclick = () => call("next");
$("btnPrev").onclick = () => call("previous");
$("btnShuffle").onclick = () => call("shuffle");
$("btnRepeat").onclick = () => call("repeat");
$("btnRadio").onclick = () => call("radio").then((r) => toast(r.radio ? "Radio on: similar songs keep coming" : "Radio off"));
$("btnMute").onclick = () => call("mute");
$("btnLike").onclick = () => state && state.song && call("like", { id: state.song.id });
$("seek").addEventListener("input", () => { dragging = true; });
$("seek").addEventListener("change", () => {
  dragging = false;
  if (state && state.duration) call("seek", { position: Math.round(($("seek").value / 1000) * state.duration) });
});
let volTimer = 0;
$("volume").addEventListener("input", () => {
  clearTimeout(volTimer);
  volTimer = setTimeout(() => call("volume", { volume: $("volume").value / 100 }), 80);
});
$("btnSleep").onclick = () => pick("Sleep timer", [
  ["Off", () => call("sleep", { minutes: 0 })],
  ["15 minutes", () => call("sleep", { minutes: 15 })],
  ["30 minutes", () => call("sleep", { minutes: 30 })],
  ["1 hour", () => call("sleep", { minutes: 60 })],
  ["End of this song", () => call("sleep", { end: "track" })],
  ["End of this album", () => call("sleep", { end: "album" })],
]);

// --- the equaliser's presets ----------------------------------------------------------------------------
$("btnEq").onclick = async () => {
  const eq = await call("eq");
  if (!eq.available) { toast("The equaliser isn't available on this computer"); return; }
  pick("Equaliser", [
    [(eq.enabled ? "" : "✓ ") + "Off", () => call("eq.set", { enabled: false }).then(() => toast("Equaliser off"))],
    ...eq.presets.map((name) => [(eq.enabled && eq.preset === name ? "✓ " : "") + name,
      () => call("eq.set", { preset: name }).then(() => toast("Equaliser: " + name))]),
  ]);
};

// --- lyrics, following the song --------------------------------------------------------------------------
let lyrics = null;          // what the app has for the song playing
let lyricsKey = undefined;  // which song they're for
let lyricsLine = -1;
function lyricsOn() { return pref("lyrics", "0") === "1"; }
async function loadLyrics() {
  if (!lyricsOn()) return;
  const key = state && state.song ? `${state.song.id}|${state.song.title}` : "";
  if (key === lyricsKey) return;
  lyricsKey = key;
  lyricsLine = -1;
  const panel = $("lyricsPanel");
  if (!key) { lyrics = null; panel.replaceChildren(); return; }
  panel.replaceChildren(el("p", { class: "dim", text: "Looking for lyrics…" }));
  try { lyrics = await call("lyrics"); } catch (e) { lyrics = null; }
  if (!lyrics || (lyrics.status === "loading" && !lyrics.synced && !lyrics.plain)) {
    setTimeout(() => { lyricsKey = undefined; loadLyrics(); }, 2500);  // the app is still looking
    return;
  }
  if (lyrics.synced) {
    panel.replaceChildren(...lyrics.lines.map((l) => el("p", { class: "line", text: l.text || "♪" })));
  } else if (lyrics.plain) {
    panel.replaceChildren(...lyrics.plain.split("\n").map((l) => el("p", { text: l || "\u00a0" })));
  } else {
    panel.replaceChildren(el("p", { class: "dim", text: "No lyrics for this song" }));
  }
  followLyrics();
}
function followLyrics() {
  if (!lyricsOn() || !lyrics || !lyrics.synced) return;
  const pos = position() + (lyrics.offset || 0);
  let at = -1;
  for (let i = 0; i < lyrics.lines.length && lyrics.lines[i].t <= pos; i++) at = i;
  if (at === lyricsLine) return;
  const lines = $("lyricsPanel").children;
  if (lines[lyricsLine]) lines[lyricsLine].classList.remove("current");
  lyricsLine = at;
  if (lines[at]) {
    lines[at].classList.add("current");
    lines[at].scrollIntoView({ block: "center", behavior: "smooth" });
  }
}
function showLyrics() {
  $("lyricsPanel").hidden = !lyricsOn();
  $("btnLyrics").classList.toggle("on", lyricsOn());
  if (lyricsOn()) { lyricsKey = undefined; loadLyrics(); }
}
$("btnLyrics").onclick = () => { setPref("lyrics", lyricsOn() ? "0" : "1"); showLyrics(); };
showLyrics();
setInterval(followLyrics, 400);

// --- views -----------------------------------------------------------------------------------------------
function show(view) {
  currentView = view;
  for (const v of ["now", "queue", "library", "search", "detail", "settings"]) $(`view-${v}`).hidden = v !== view;
  for (const t of document.querySelectorAll(".tab")) t.classList.toggle("active", t.dataset.view === view ||
    (view === "detail" && t.dataset.view === "library"));
  $("mini").hidden = !(state && state.song) || view === "now";
  if (view === "queue") loadQueue();
  if (view === "library") loadLibrary();
  if (view === "search") $("searchField").focus();
  $("main").scrollTop = 0;
}
for (const t of document.querySelectorAll(".tab")) t.onclick = () => show(t.dataset.view);

// --- settings: light or dark (#123), and disconnecting this device (#125) ----------------------------------
function applyTheme(pick) {
  if (pick) document.documentElement.dataset.theme = pick;
  else delete document.documentElement.dataset.theme;
  for (const c of document.querySelectorAll("[data-theme-pick]")) {
    const on = c.dataset.themePick === (pick || "");
    c.classList.toggle("active", on);
    c.setAttribute("aria-checked", on ? "true" : "false");
  }
  const bg = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim();
  if (bg) document.querySelector('meta[name="theme-color"]').setAttribute("content", bg);
}
function savedTheme() {
  try { return localStorage.getItem("hallucinate.theme") || ""; } catch (_) { return ""; }
}
for (const c of document.querySelectorAll("[data-theme-pick]")) c.onclick = () => {
  try { localStorage.setItem("hallucinate.theme", c.dataset.themePick); } catch (_) { /* private window */ }
  applyTheme(c.dataset.themePick);
};
applyTheme(savedTheme());

// the rest of this browser's own choices: kept in its storage, never sent anywhere
function pref(name, fallback) {
  try { const v = localStorage.getItem("hallucinate." + name); return v === null ? fallback : v; } catch (_) { return fallback; }
}
function setPref(name, value) {
  try { localStorage.setItem("hallucinate." + name, value); } catch (_) { /* private window: for this visit only */ }
}
function markStart() {
  for (const c of document.querySelectorAll("[data-start-pick]")) {
    const on = c.dataset.startPick === pref("start", "now");
    c.classList.toggle("active", on);
    c.setAttribute("aria-checked", on ? "true" : "false");
  }
}
for (const c of document.querySelectorAll("[data-start-pick]")) c.onclick = () => { setPref("start", c.dataset.startPick); markStart(); };
markStart();

// the cover as a record, turning while the music plays (#135)
$("optSpin").checked = pref("spin", "0") === "1";
document.body.classList.toggle("spin", $("optSpin").checked);
$("optSpin").onchange = () => {
  setPref("spin", $("optSpin").checked ? "1" : "0");
  document.body.classList.toggle("spin", $("optSpin").checked);
};

$("optBackdrop").checked = pref("backdrop", "1") === "1";
document.body.classList.toggle("no-backdrop", !$("optBackdrop").checked);
$("optBackdrop").onchange = () => {
  setPref("backdrop", $("optBackdrop").checked ? "1" : "0");
  document.body.classList.toggle("no-backdrop", !$("optBackdrop").checked);
};

// Keep the screen on while something plays (where the browser can: the Screen Wake Lock API)
let wakeLock = null;
async function syncWakeLock() {
  const want = $("optAwake").checked && state && state.playing && document.visibilityState === "visible";
  if (want && !wakeLock && "wakeLock" in navigator) {
    try {
      wakeLock = await navigator.wakeLock.request("screen");
      wakeLock.addEventListener("release", () => { wakeLock = null; });
    } catch (_) { wakeLock = null; }
  } else if (!want && wakeLock) {
    wakeLock.release().catch(() => {});
    wakeLock = null;
  }
}
$("optAwake").checked = pref("awake", "0") === "1";
$("optAwake").disabled = !("wakeLock" in navigator);
$("optAwake").onchange = () => { setPref("awake", $("optAwake").checked ? "1" : "0"); syncWakeLock(); };
document.addEventListener("visibilitychange", syncWakeLock);

$("btnForget").onclick = async () => {
  if (!confirm("Disconnect this device from Hallucinate? You'll need a new pairing code to use it again.")) return;
  const res = await fetch("api/forget", {
    method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-Hallucinate": "1" }, body: "{}",
  }).catch(() => null);
  if (!res || !res.ok) { toast("Couldn't disconnect: is Hallucinate still running?"); return; }
  showPairing();
};

function songRow(song, index, onPlay, opts = {}) {
  const row = el("li", { class: "row", tabindex: "0" });
  if (opts.number) row.append(el("span", { class: "num", text: String(opts.number) }));
  if (opts.art !== false) row.append(img(song.albumKey, 64));
  row.append(el("div", { class: "text" }, el("span", { class: "title" }, el("span", { text: song.title }), ...badges(song)),
    el("span", { class: "dim small", text: [song.artist, opts.showAlbum === false ? "" : song.album].filter(Boolean).join(" · ") })));
  if (song.duration) row.append(el("span", { class: "time", text: fmt(song.duration) }));
  if (song.id) {
    row.append(el("button", { class: "icon", "aria-label": "More", onclick: (e) => { e.stopPropagation(); songMenu(song); } },
      svgDots()));
  }
  row.addEventListener("click", () => onPlay(index));
  row.addEventListener("keydown", (e) => { if (e.key === "Enter") onPlay(index); });
  return row;
}

// E for explicit, Hi-Res for 24-bit and up (1 bit is DSD), as the app shows them
function badges(song) {
  const out = [];
  if (song && song.explicit) out.push(el("span", { class: "badge explicit", title: "Explicit", text: "E" }));
  if (song && (song.bitDepth >= 24 || song.bitDepth === 1)) out.push(el("span", { class: "badge hires", text: "Hi-Res" }));
  return out;
}

function svgDots() {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 24 24");
  for (const x of [6, 12, 18]) {
    const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    c.setAttribute("cx", x); c.setAttribute("cy", 12); c.setAttribute("r", 1.4);
    s.append(c);
  }
  return s;
}

function card(title, sub, albumKey, onClick, placeholder) {
  const c = el("div", { class: "card", tabindex: "0", role: "button" });
  if (albumKey) c.append(img(albumKey, 256));
  else c.append(el("div", { class: "ph", text: placeholder || (title || "?").charAt(0) }));
  c.append(el("b", { text: title }), el("span", { text: sub }));
  c.addEventListener("click", onClick);
  c.addEventListener("keydown", (e) => { if (e.key === "Enter") onClick(); });
  return c;
}

// queue
async function loadQueue() {
  const q = await call("queue");
  const list = $("queueList");
  list.replaceChildren(...q.songs.map((s, i) => {
    const row = songRow(s, i, (idx) => call("queue.jump", { index: idx }), { art: true });
    row.dataset.index = i;
    const remove = el("button", { class: "icon", "aria-label": "Remove", onclick: (e) => { e.stopPropagation(); call("queue.remove", { index: i }).then(loadQueue); } });
    remove.textContent = "×";
    row.append(remove);
    return row;
  }));
  if (!q.songs.length) list.append(el("p", { class: "dim", text: "The queue is empty. Play something from your library." }));
  markCurrent();
}
function markCurrent() {
  for (const row of $("queueList").children) row.classList.toggle("current", state && Number(row.dataset.index) === state.index);
}
$("qShuffle").onclick = () => call("queue.shuffle").then(() => toast("Upcoming songs shuffled"));
$("qClear").onclick = () => call("queue.clear", { upcoming: true }).then(() => toast("Upcoming songs cleared"));
$("qUndo").onclick = () => call("queue.undo").then((r) => toast(r.undone ? `Undone: ${r.undone}` : "Nothing to undo"));

// library
for (const c of document.querySelectorAll("#libChips .chip")) {
  c.onclick = () => { libKind = c.dataset.lib; for (const o of document.querySelectorAll("#libChips .chip")) o.classList.toggle("active", o === c); loadLibrary(); };
}
async function loadLibrary() {
  const body = $("libBody");
  body.replaceChildren(el("p", { class: "dim", text: "Loading…" }));
  if (libKind === "albums") {
    const grid = el("div", { class: "grid" });
    let offset = 0;
    const more = el("button", { text: "Show more", onclick: () => page() });
    async function page() {
      const r = await call("albums", { offset, limit: 120, sort: "artist" });
      offset += r.albums.length;
      grid.append(...r.albums.map((a) => card(a.title, [a.artist, a.year || ""].filter(Boolean).join(" · "), a.key, () => openAlbum(a.key))));
      more.hidden = offset >= r.total;
    }
    body.replaceChildren(grid, el("p", {}, more));
    await page();
  } else if (libKind === "artists") {
    const r = await call("artists", { limit: 500 });
    body.replaceChildren(el("ul", { class: "list" }, ...r.artists.map((a) => {
      const row = el("li", { class: "row", tabindex: "0" }, el("div", { class: "text" }, el("span", { text: a.name }),
        el("span", { class: "dim small", text: `${a.albums} album${a.albums === 1 ? "" : "s"} · ${a.songs} songs` })));
      row.onclick = () => openArtist(a.name);
      return row;
    })));
  } else if (libKind === "playlists") {
    const r = await call("playlists");
    body.replaceChildren(el("ul", { class: "list" }, ...r.playlists.map((p) => {
      const row = el("li", { class: "row", tabindex: "0" }, el("div", { class: "text" },
        el("span", { text: (p.folder ? p.folder + " / " : "") + p.name }),
        el("span", { class: "dim small", text: p.smart ? "Smart playlist" : `${p.songs} songs` })));
      row.onclick = () => openPlaylist(p);
      return row;
    })));
    if (!r.playlists.length) body.append(el("p", { class: "dim", text: "No playlists yet." }));
  } else if (libKind === "genres") {
    const r = await call("genres");
    body.replaceChildren(el("div", { class: "grid" }, ...r.genres.map((g) =>
      card(g.name, `${g.songs} songs`, g.albumKey, () => openGenre(g.name)))));
  } else if (libKind === "recent") {  // what was listened to last; songs still in the library play again
    const r = await call("recent", { limit: 50 });
    body.replaceChildren(el("ul", { class: "list" }, ...r.plays.map((p) => {
      const row = el("li", { class: "row" + (p.id ? "" : " played"), tabindex: "0" }, img(p.albumKey, 64),
        el("div", { class: "text" }, el("span", { text: p.title }),
          el("span", { class: "dim small", text: [p.artist, p.album].filter(Boolean).join(" · ") })),
        el("span", { class: "time", text: p.time }));
      if (p.id) row.onclick = () => call("play.songs", { ids: [p.id] }).then(() => toast("Playing " + p.title));
      return row;
    })));
    if (!r.plays.length) body.append(el("p", { class: "dim", text: "Songs you listen to show up here." }));
  } else if (libKind === "stations") {  // internet radio (#128)
    const r = await call("stations");
    body.replaceChildren(el("div", { class: "grid" }, ...r.stations.map((st) =>
      card(st.name, st.detail, st.art, () => call("play.station", { id: st.id }).then(() => toast("Tuning in to " + st.name)), "📻"))));
    if (!r.stations.length) body.append(el("p", { class: "dim", text: "Stations you add in Hallucinate show up here." }));
  } else if (libKind === "podcasts") {
    const r = await call("podcasts");
    body.replaceChildren(el("div", { class: "grid" }, ...r.podcasts.map((p) =>
      card(p.title, p.unplayed ? `${p.unplayed} new` : (p.author || `${p.episodes} episodes`), p.art, () => openShow(p.id), "🎙"))));
    if (!r.podcasts.length) body.append(el("p", { class: "dim", text: "Shows you follow in Hallucinate show up here." }));
  } else if (libKind === "liked") {
    const r = await call("liked", { limit: 500 });
    const list = el("ol", { class: "list" }, ...r.songs.map((s, i) => songRow(s, i, (idx) => call("play.liked", { index: idx }))));
    body.replaceChildren(el("div", { class: "actions" },
      el("button", { class: "primary", text: "Play", onclick: () => call("play.liked") }),
      el("button", { text: "Shuffle", onclick: () => call("play.liked", { shuffle: true }) })), list);
    if (!r.songs.length) body.append(el("p", { class: "dim", text: "Songs you like show up here." }));
  }
}

// details
function openDetail(info, rows) {
  detail = info;
  $("detailKind").textContent = info.kind;
  $("detailTitle").textContent = info.title;
  $("detailSub").textContent = info.sub || "";
  $("detailArt").hidden = !info.albumKey;
  $("detailShuffle").hidden = info.kind === "Podcast";  // (a show plays its newest unplayed episode)
  if (info.albumKey) $("detailArt").src = art(info.albumKey, 256);
  $("detailBody").replaceChildren(...rows);
  show("detail");
}
$("detailBack").onclick = () => show("library");
$("detailPlay").onclick = () => detail && detail.play(false);
$("detailShuffle").onclick = () => detail && detail.play(true);

async function openShow(id) {
  const sh = await call("podcast", { id, limit: 100 });
  const firstNew = sh.episodes.find((e) => !e.played) || sh.episodes[0];
  const rows = sh.episodes.map((e) => {
    const when = e.published ? new Date(e.published * 1000).toLocaleDateString() : "";
    const left = e.position > 0 && !e.played && e.duration ? `${fmt(e.duration - e.position)} left` : (e.duration ? fmt(e.duration) : "");
    const row = el("li", { class: "row" + (e.played ? " played" : ""), tabindex: "0" },
      el("div", { class: "text" }, el("span", { text: e.title }),
        el("span", { class: "dim small", text: [when, left, e.played ? "Played" : ""].filter(Boolean).join(" · ") })),
      el("button", { class: "small", text: "Next", "aria-label": "Play next: " + e.title,
        onclick: (ev) => { ev.stopPropagation(); call("play.episode", { id: e.id, next: true }).then(() => toast("Plays next")); } }),
      el("button", { class: "small", text: "Queue", "aria-label": "Add to the queue: " + e.title,
        onclick: (ev) => { ev.stopPropagation(); call("play.episode", { id: e.id, queue: true }).then(() => toast("Added to the queue")); } }));
    row.onclick = () => call("play.episode", { id: e.id });
    row.addEventListener("keydown", (ev) => { if (ev.key === "Enter") row.onclick(); });
    return row;
  });
  openDetail({ kind: "Podcast", title: sh.title, sub: [sh.author, `${sh.total} episodes`].filter(Boolean).join(" · "),
    albumKey: sh.art, play: () => firstNew && call("play.episode", { id: firstNew.id }) }, [el("ol", { class: "list" }, ...rows)]);
}

async function openAlbum(key) {
  const a = await call("album", { key });
  openDetail({ kind: "Album", title: a.title, sub: [a.artist, a.year || "", `${a.songs.length} songs`].filter(Boolean).join(" · "),
    albumKey: a.key, play: (shuffle) => call("play.album", { key: a.key, shuffle }) },
  [el("ol", { class: "list" }, ...a.songs.map((s, i) => songRow(s, i, (idx) => call("play.album", { key: a.key, index: idx }),
    { number: s.trackNo || i + 1, art: false, showAlbum: false })))]);
}
async function openArtist(name) {
  const a = await call("artist", { name });
  openDetail({ kind: "Artist", title: a.name, sub: `${a.albums.length} albums`, play: (shuffle) => call("play.artist", { name: a.name, shuffle }) },
    [el("h3", { class: "section-title", text: "Albums" }),
     el("div", { class: "grid" }, ...a.albums.map((al) => card(al.title, String(al.year || ""), al.key, () => openAlbum(al.key)))),
     el("h3", { class: "section-title", text: "Songs" }),
     el("ol", { class: "list" }, ...a.songs.slice(0, 100).map((s, i) => songRow(s, i, () => call("play.songs", { ids: a.songs.map((x) => x.id), index: i }))))]);
}
async function openPlaylist(p) {
  const r = await call("playlist", { id: p.id, smart: p.smart });
  openDetail({ kind: p.smart ? "Smart playlist" : "Playlist", title: p.name, sub: `${r.total} songs`,
    play: (shuffle) => call("play.playlist", { id: p.id, smart: p.smart, shuffle }) },
  [el("ol", { class: "list" }, ...r.songs.map((s, i) => songRow(s, i, (idx) => call("play.playlist", { id: p.id, smart: p.smart, index: idx }))))]);
}
async function openGenre(name) {
  const g = await call("genre", { name });
  openDetail({ kind: "Genre", title: g.name, sub: `${g.albums.length} albums`, play: (shuffle) => call("play.genre", { name, shuffle }) },
    [el("div", { class: "grid" }, ...g.albums.slice(0, 60).map((al) => card(al.title, al.artist, al.key, () => openAlbum(al.key)))),
     el("h3", { class: "section-title", text: "Most played" }),
     el("ol", { class: "list" }, ...g.songs.slice(0, 100).map((s, i) => songRow(s, i, () => call("play.songs", { ids: g.songs.map((x) => x.id), index: i }))))]);
}

// search
let searchTimer = 0;
$("searchField").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(runSearch, 250);
});
async function runSearch() {
  const q = $("searchField").value.trim();
  const body = $("searchBody");
  $("searchNote").textContent = "";
  if (!q) { body.replaceChildren(); return; }
  const r = await call("search", { query: q });
  if (r.corrected) $("searchNote").textContent = `Nothing matches “${q}”. Showing results for “${r.corrected}”.`;
  const parts = [];
  if (r.artists.length) parts.push(el("h3", { class: "section-title", text: "Artists" }),
    el("ul", { class: "list" }, ...r.artists.map((a) => { const row = el("li", { class: "row" }, el("div", { class: "text" }, el("span", { text: a.name }))); row.onclick = () => openArtist(a.name); return row; })));
  if (r.albums.length) parts.push(el("h3", { class: "section-title", text: "Albums" }),
    el("div", { class: "grid" }, ...r.albums.map((a) => card(a.title, a.artist, a.key, () => openAlbum(a.key)))));
  if (r.songs.length) parts.push(el("h3", { class: "section-title", text: "Songs" }),
    el("ol", { class: "list" }, ...r.songs.map((s, i) => songRow(s, i, () => call("play.songs", { ids: r.songs.map((x) => x.id), index: i })))));
  if (!parts.length) parts.push(el("p", { class: "dim", text: "Nothing found." }));
  body.replaceChildren(...parts);
}

// --- menus -----------------------------------------------------------------------------------------------
function songMenu(song) {
  menuSong = song;
  $("songMenuTitle").textContent = song.title;
  $("songMenu").querySelector('[data-act="like"]').textContent = song.liked ? "Unlike" : "Like";
  $("songMenu").showModal();
}
$("songMenu").addEventListener("click", async (e) => {
  const act = e.target.dataset && e.target.dataset.act;
  if (!act) return;
  $("songMenu").close();
  const s = menuSong;
  if (!s || act === "close") return;
  if (act === "play") call("play.songs", { ids: [s.id] });
  else if (act === "next") call("queue.add", { ids: [s.id], next: true }).then(() => toast("Plays next"));
  else if (act === "queue") call("queue.add", { ids: [s.id] }).then(() => toast("Added to the queue"));
  else if (act === "like") call("like", { id: s.id }).then((r) => { s.liked = r.liked; toast(r.liked ? "Liked" : "Unliked"); });
  else if (act === "album") openAlbum(s.albumKey);
  else if (act === "artist") openArtist(s.albumArtist || s.artist);
  else if (act === "playlist") {
    const r = await call("playlists");
    pick("Add to playlist", r.playlists.filter((p) => !p.smart).map((p) => [p.name,
      () => call("playlist.add", { id: p.id, ids: [s.id] }).then(() => toast(`Added to ${p.name}`))]));
  }
});

function pick(title, options) {
  $("pickTitle").textContent = title;
  $("pickBody").replaceChildren(...options.map(([label, fn]) =>
    el("button", { text: label, onclick: () => { $("pickMenu").close(); fn(); } })));
  if (!options.length) $("pickBody").append(el("p", { class: "dim", text: "Nothing here yet." }));
  $("pickMenu").showModal();
}
$("pickCancel").onclick = () => $("pickMenu").close();

// keyboard, on a computer
document.addEventListener("keydown", (e) => {
  if (e.target.matches("input, textarea") || document.querySelector("dialog[open]")) return;
  if (e.key === " ") { e.preventDefault(); call("toggle"); }
  else if (e.key === "ArrowRight" && e.shiftKey) call("next");
  else if (e.key === "ArrowLeft" && e.shiftKey) call("previous");
  else if (e.key === "/") { e.preventDefault(); show("search"); }
});

// --- start -----------------------------------------------------------------------------------------------
async function start() {
  const hello = await fetch("api/hello", { credentials: "same-origin" }).then((r) => r.json()).catch(() => null);
  if (!hello) { document.body.textContent = "Hallucinate isn't answering. Is it still running?"; return; }
  if (!hello.paired) { showPairing(); return; }
  $("pair").hidden = true;
  $("app").hidden = false;
  connect();
  call("features").then((f) => {
    document.querySelector('[data-lib="stations"]').hidden = !f.stations;
    document.querySelector('[data-lib="podcasts"]').hidden = !f.podcasts;
  }).catch(() => {});
  show(pref("start", "now"));
}
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
// a pairing link from the app ("…/#pair=123456") fills the code in; it's taken out of the address at once
noArt($("miniArt"));
$("detailArt").addEventListener("error", () => { $("detailArt").hidden = true; });
$("nowArt").addEventListener("error", () => { $("nowArt").hidden = true; $("nowArtEmpty").hidden = false; });

const linked = /pair=(\d{6})/.exec(location.hash);
if (linked) { $("pairCode").value = linked[1]; history.replaceState(null, "", location.pathname); }
start();
