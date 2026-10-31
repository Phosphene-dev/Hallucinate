import QtQuick
import QtQuick.Controls
import "."

// A neon theme's terminal Now Playing (NeonNowPlaying, mode "terminal"): live panes typed out in a monospace
// phosphor, and a console to type commands into. The panes are yours to choose and order (`pin`, `unpin`, or
// Settings → Appearance); anything a pane shows can also be printed once by typing its name. Commands drive the
// player through the same commands the web remote and the command line use (webRemote.runCommand).
//     NeonTerminal { np: theNeonNowPlaying }
Rectangle {
    id: term
    objectName: "neonTerminal"
    property var np
    color: Qt.rgba(Theme.bg.r * 0.6, Theme.bg.g * 0.6, Theme.bg.b * 0.6, 1)
    readonly property real fs: Math.max(12, 16 * np.u)
    readonly property real charW: fs * 0.6  // (a monospace face's advance, near enough)
    // the phosphor: green or amber like an old monitor, or the theme's own (Settings → Appearance, or `phosphor`)
    readonly property string phosphor: shell.ui.neonPhosphor || "theme"
    readonly property color ink: phosphor === "green" ? "#4dff8f" : phosphor === "amber" ? "#ffb43a" : Theme.neonLoud ? np.cb : Theme.text
    readonly property color prompt: phosphor === "theme" ? np.ca : Qt.lighter(ink, 1.25)
    readonly property color dim: Qt.rgba(ink.r, ink.g, ink.b, 0.55)
    readonly property color bad: Theme.error
    readonly property bool wide: width > 1100

    // --- the panes ------------------------------------------------------------------------------------------------
    readonly property var paneNames: ({
        now: "now_playing --verbose", wave: "waveform", spectrum: "spectrum", lyrics: "lyrics --scroll",
        queue: "queue --next", signal: "signal --path", stats: "stats --today", tags: "tags --raw",
        similar: "similar", whoami: "whoami", log: "tail -f afterimage.log"
    })
    readonly property var allPanes: ["now", "wave", "spectrum", "lyrics", "queue", "signal", "stats", "tags", "similar", "whoami", "log"]
    readonly property string defaultPanes: "now,wave,spectrum,lyrics,queue"
    readonly property var panes: {
        var v = shell.ui.neonTermPanes  // (blank: the usual ones; "none": every one unpinned)
        var list = (v === undefined || v === "" ? defaultPanes : v === "none" ? "" : v).split(",")
        return list.filter(function (p, i) { return term.allPanes.indexOf(p) >= 0 && list.indexOf(p) === i })
    }
    function setPanes(list) { shell.setUiValue("neonTermPanes", list.length ? list.join(",") : "none") }

    function pad(s, n) { s = String(s); return s.length >= n ? s : s + " ".repeat(n - s.length) }
    function bar(p, n) {
        var lit = Math.round(Math.max(0, Math.min(1, p)) * n)
        return "[" + "#".repeat(lit) + "-".repeat(Math.max(0, n - lit)) + "]"
    }
    // how many characters fit across the panes' column
    readonly property int cols: Math.max(24, Math.floor(paneArea.width / charW) - 2)

    // what the panes read, fetched when the song changes and only when a pane (or a command) wants it
    property var tagInfo: ({})
    property int similarRevision: 0
    function refreshTags() {
        tagInfo = player.hasTrack && np.track.path && np.track.kind !== "station" && np.track.kind !== "episode"
            ? metaEditor.trackInfo(np.track.path) : ({})
    }
    Connections {
        target: player
        function onCurrentChanged() {
            if (term.panes.indexOf("tags") >= 0) term.refreshTags()
            else term.tagInfo = ({})
            if (term.panes.indexOf("similar") >= 0 && np.track.artist) similarArtists.ensure(np.track.artist)
        }
    }
    Connections { target: similarArtists; function onChanged() { term.similarRevision++ } }
    Component.onCompleted: {
        if (panes.indexOf("tags") >= 0) refreshTags()
        if (panes.indexOf("similar") >= 0 && np.track.artist) similarArtists.ensure(np.track.artist)
        boot()
    }

    // Each pane's lines (the waveform has a pane of its own: two colours, played and to come)
    function paneLines(name) {
        var t = np.track, out = [], i
        switch (name) {
        case "now":
            out.push("  title    : " + (player.hasTrack ? t.title || "?" : "(nothing)"))
            out.push("  artist   : " + (t.artist || "-"))
            out.push("  album    : " + (t.album || "-") + (t.year ? " (" + t.year + ")" : ""))
            out.push("  signal   : " + np.signal.toLowerCase())
            out.push("  state    : " + (player.playing ? "playing" : "paused") + (player.shuffle ? " · shuffle" : "")
                     + (player.repeat === 2 ? " · repeat one" : player.repeat ? " · repeat" : "")
                     + (player.muted ? " · muted" : " · vol " + Math.round(player.volume * 100) + "%"))
            out.push("  " + bar(np.progress, Math.max(10, Math.min(60, cols - 30))) + " " + np.clock(player.position)
                     + " / " + np.clock(player.duration) + "  " + Math.round(np.progress * 100) + "%")
            return out
        case "spectrum":
            var lv = np.levels, blocks = " ▁▂▃▄▅▆▇█"
            if (!lv.length) return ["  (turn on “React to the music” on the Visualizer page to see the spectrum)"]
            for (var r = 3; r >= 0; r--) {
                var line = "  "
                for (i = 0; i < 24; i++) {
                    var h = Math.max(0, Math.min(1, lv[i] || 0)) * 4 - r
                    line += (h >= 1 ? "█" : h <= 0 ? " " : blocks[Math.round(h * 8)]) + " "
                }
                out.push(line)
            }
            return out
        case "lyrics":
            if (lyricsCtl.status === "loading") return ["  looking for lyrics..."]
            if (lyricsCtl.status !== "found") return ["  (no lyrics for this song)"]
            if (!lyricsCtl.synced) return String(lyricsCtl.plain || "").split("\n").slice(0, 6).map(function (l) { return "  " + l })
            var at = Math.max(0, lyricsCtl.currentLine), lines = lyricsCtl.lines || []
            for (i = Math.max(0, at - 2); i <= Math.min(lines.length - 1, at + 2); i++)
                out.push((i === at ? "> " : "  ") + ((lines[i] || {}).text || ""))
            return out.length ? out : ["  ..."]
        case "queue":
            if (!np.upNext.length) return ["  (nothing after this)"]
            return np.upNext.map(function (s, k) {
                return "  " + (k < 9 ? "0" : "") + (k + 1) + "  " + term.pad(s.title, Math.min(34, Math.max(12, term.cols - 28))).slice(0, 40) + "  " + (s.artist || "")
            })
        case "signal":
            var sp = player.signalPath || {}, stages = sp.stages || []
            if (!stages.length) return ["  (nothing playing)"]
            stages.forEach(function (s, k) {
                out.push("  " + (k ? " └─ " : "    ") + term.pad(s.name, 11) + (s.active ? "* " : "  ") + (s.detail || ""))
            })
            if (sp.summary) out.push("  " + sp.summary)
            return out
        case "stats":
            var hm = (userLib.home || {}).heatmap || {}, top = (userLib.home || {}).topArtists || []
            var days = hm.days || []
            out.push("  today    : " + Theme.num(days.length ? days[hm.today] || 0 : 0) + " plays")
            out.push("  streak   : " + Theme.num(hm.streak || 0) + (hm.streak === 1 ? " day" : " days"))
            out.push("  26 weeks : " + Theme.num(hm.total || 0) + " plays on " + Theme.num(hm.activeDays || 0) + " days")
            if (top.length) out.push("  top 30d  : " + top.slice(0, 5).map(function (a) { return a.name + (a.plays ? " (" + Theme.num(a.plays) + ")" : "") }).join(", "))
            return out
        case "whoami":
            var f = (userLib.home || {}).facts || {}
            out.push("  library  : " + Theme.num(f.tracks || library.trackCount) + " songs · " + Theme.num(f.albums || library.albumCount)
                     + " albums · " + Theme.num(f.artists || library.artistCount) + " artists")
            if (f.seconds) out.push("  length   : " + Theme.fmtHours(f.seconds) + " of music · " + Theme.fmtBytes(f.bytes || 0))
            if (f.tracks) out.push("  lossless : " + Math.round((f.lossless || 0) * 100) + "%")
            if (f.formats && f.formats.length) out.push("  formats  : " + f.formats.map(function (x) { return x.name + " " + Theme.num(x.count) }).join(" · "))
            return out
        case "tags":
            var ti = tagInfo, keys = Object.keys(ti).filter(function (k) {
                var v = ti[k]
                return v !== null && v !== undefined && v !== "" && v !== 0 && typeof v !== "object"
                    && ["artUrl", "art", "id", "mtime", "size", "aa_tag"].indexOf(k) < 0
            }).sort()
            if (!keys.length) return [player.hasTrack ? "  (no tags read for this one)" : "  (nothing playing)"]
            return keys.slice(0, 40).map(function (k) { return "  " + term.pad(k, 16) + ": " + String(ti[k]).slice(0, 200) })
        case "similar":
            var rev = similarRevision, found = t.artist ? similarArtists.similar(t.artist) : ({})
            if (!t.artist) return ["  (nothing playing)"]
            if (found.on !== true) return ["  (switch on similar artists in Settings → Online & privacy)"]
            if (found.busy) return ["  asking last.fm about " + t.artist + "..."]
            var have = (found.have || []).slice(0, 6).map(function (a) { return a.name }), more = (found.discover || []).slice(0, 6).map(function (a) { return a.name })
            if (have.length) out.push("  in your library : " + have.join(", "))
            if (more.length) out.push("  to discover     : " + more.join(", "))
            return out.length ? out : ["  (none found for " + t.artist + ")"]
        case "log":
            return np.log.slice(-10).map(function (l) { return "  " + l })
        }
        return []
    }

    // --- the console: what you typed and what came back ---------------------------------------------------------
    property var out: []          // [{t: text, k: "ink" | "dim" | "prompt" | "bad"}]
    property var typed: []        // your commands, oldest first (↑ and ↓ walk them)
    property int typedAt: -1
    function say(lines, kind) {
        var add = (Array.isArray(lines) ? lines : [lines]).map(function (l) { return { t: String(l), k: kind || "ink" } })
        out = out.concat(add).slice(-400)
    }
    // help: one command per line under a heading, its description in a column beside it, or on its own indented
    // line when the console is too narrow for both (then nothing wraps in the middle of a word or a command)
    readonly property var helpTopics: [
        ["playback", [["play [search]", "play songs matching, or carry on"], ["pause · p", "pause, or carry on"],
                      ["next [search] · n", "skip, or play a song next"], ["prev · b", "back a song"],
                      ["seek <1:30|+10|-10>", "move in the song"], ["vol <n|+n|-n> · v", "volume, 0 to 100"],
                      ["mute · m", "mute or unmute"], ["shuffle [on|off] · s", "shuffle"],
                      ["repeat [off|all|one] · r", "repeat"], ["like", "like the playing song"],
                      ["sleep <min|track|album|off>", "sleep timer"], ["radio [on|off]", "keep similar songs coming"]]],
        ["queue", [["queue <search> · q", "add the best match"], ["queue rm <n>", "take one out (numbers as up next shows them)"],
                   ["queue mv <from> <to>", "move one"], ["queue clear", "clear what's next"], ["queue shuffle", "shuffle what's next"]]],
        ["looking around", [["history [n]", "what you listened to last"], ["top [week|month|year|all] · t", "your most played"],
                            ["lyrics · l", "the whole text"], ["eq [off|<preset>]", "the equaliser"],
                            ["out [<n>|default]", "where the sound goes"],
                            ["<pane>", "print a pane once: " + allPanes.join(", ")]]],
        ["the terminal", [["pin <pane> / unpin <pane>", "what shows on the left"], ["panes", "which are showing"],
                          ["phosphor <green|amber|theme>", "the colour"], ["theme <name>", "another theme"],
                          ["boot · clear · cmds", "start over · empty this · what you typed"],
                          ["cockpit · classic", "switch Now Playing"], ["exit", "close it"],
                          ["up / down · Tab", "earlier commands · complete a command"]]]
    ]
    // `text` in lines of at most `width` characters, broken between words
    function wrapWords(text, width) {
        var lines = [], line = ""
        String(text).split(" ").forEach(function (w) {
            if (line && (line + " " + w).length > width) { lines.push(line); line = w }
            else line = line ? line + " " + w : w
        })
        if (line) lines.push(line)
        return lines.length ? lines : [""]
    }
    function help(topic) {
        var cols = Math.max(30, Math.floor((scrollback.width - 8) / Math.max(1, consoleChar.advanceWidth / 10)))
        var shown = helpTopics.filter(function (t) { return !topic || t[0].indexOf(topic) === 0 })
        if (!shown.length) { say("help topics: " + helpTopics.map(function (t) { return t[0] }).join(", "), "bad"); return }
        var widest = 0
        shown.forEach(function (t) { t[1].forEach(function (c) { widest = Math.max(widest, c[0].length) }) })
        var column = Math.min(widest + 3, 34)
        var side = cols >= column + 24  // room for the description beside it
        shown.forEach(function (t, k) {
            if (k) say(" ")
            say(t[0], "prompt")
            t[1].forEach(function (c) {
                if (side && c[0].length + 3 <= column) {
                    // a long description carries on in its own column, not back at the left edge
                    wrapWords(c[1], cols - column - 3).forEach(function (part, i) { say("  " + pad(i ? "" : c[0], column) + part) })
                } else {
                    say("  " + c[0])
                    wrapWords(c[1], cols - 7).forEach(function (part) { say("      " + part, "dim") })
                }
            })
        })
        if (!topic) say(["", "help <topic> for one of: " + helpTopics.map(function (t) { return t[0] }).join(", ")], "dim")
    }
    TextMetrics { id: consoleChar; font.family: np.mono; font.pixelSize: term.fs * 0.9; text: "MMMMMMMMMM" }  // (the console's own letters)
    function colorOf(k) { return k === "dim" ? dim : k === "prompt" ? prompt : k === "bad" ? bad : ink }

    // a short start-up, as an old machine would (Settings → Appearance; off, it only says how to get help)
    property var bootLines: []
    function boot() {
        var f = (userLib.home || {}).facts || {}, sp = player.signalPath || {}, stages = sp.stages || []
        var output = stages.length ? stages[stages.length - 1].detail || "" : ""
        var lines = ["AFTERIMAGE TERMINAL " + shell.appVersion,
                     "memory check ................ ok",
                     "mounting library ............ " + Theme.num(f.tracks || library.trackCount) + " songs",
                     "audio out ................... " + (output || "default device"),
                     "signal ...................... " + np.signal.toLowerCase(),
                     "connecting to the wired ..... ok",
                     "",
                     "type `help` for commands"]
        if (shell.ui.neonBoot === "0" || Theme.reduceMotion) { say(lines.slice(-1), "dim"); return }
        bootLines = lines
        bootTimer.start()
    }
    Timer {
        id: bootTimer
        interval: 70; repeat: true
        onTriggered: {
            if (!term.bootLines.length) { stop(); return }
            term.say(term.bootLines[0], "dim")
            term.bootLines = term.bootLines.slice(1)
        }
    }

    readonly property var commands: ["help", "clear", "play", "pause", "next", "prev", "queue", "vol", "mute", "seek",
        "shuffle", "repeat", "like", "sleep", "radio", "pin", "unpin", "panes", "phosphor", "theme", "boot", "history",
        "top", "eq", "out", "cmds", "cockpit", "classic", "exit"].concat(allPanes)
    // one-letter (or short) ways to say the everyday commands
    readonly property var aliases: ({ n: "next", b: "prev", v: "vol", s: "shuffle", r: "repeat", q: "queue",
        l: "lyrics", h: "help", m: "mute", t: "top", hist: "history", o: "out" })

    function call(method, params) {
        var r = webRemote.runCommand(method, params || {})
        if (!r.ok) say("error: " + r.error, "bad")
        return r.ok ? r.result : null
    }
    function seconds(s) {
        var m = /^(\d+):(\d{1,2})$/.exec(s)
        return m ? parseInt(m[1]) * 60 + parseInt(m[2]) : parseFloat(s)
    }
    function search(q) {
        var r = call("search", { query: q, limit: 50 })
        if (!r) return []
        if (r.corrected) say("(did you mean “" + r.corrected + "”?)", "dim")
        if (!r.songs.length) say("nothing found for “" + q + "”", "bad")
        return r.songs
    }

    function run(line) {
        line = String(line).trim()
        if (bootTimer.running) {  // typing while it starts up finishes the start-up first, so nothing interleaves
            bootTimer.stop()
            say(bootLines, "dim")
            bootLines = []
        }
        say("> " + line, "prompt")
        if (!line) return
        typed = typed.concat([line]).slice(-100)
        typedAt = -1
        var word = line.split(/\s+/)[0].toLowerCase(), arg = line.slice(word.length).trim(), argl = arg.toLowerCase()
        if (aliases[word]) word = aliases[word]
        var songs, n
        switch (word) {
        case "help": case "?":
            help(argl)
            return
        case "clear": bootTimer.stop(); bootLines = []; out = []; return  // (a start-up still typing stops too)
        case "boot": bootTimer.stop(); out = []; boot(); return
        case "cmds": say(typed.map(function (c, i) { return "  " + (i + 1) + "  " + c }), "dim"); return
        case "history":
            var rec = call("recent", { limit: Math.max(1, Math.min(50, parseInt(arg) || 10)) })
            if (!rec) return
            if (!rec.plays.length) { say("nothing listened to yet", "dim"); return }
            say(rec.plays.map(function (p) { return "  " + pad(p.day.slice(5) + " " + p.time, 12) + pad(p.title, 34).slice(0, 40) + "  " + p.artist }))
            return
        case "top":
            var period = ["week", "month", "year", "all"].indexOf(argl) >= 0 ? argl : "month"
            var tp = call("top", { period: period, limit: 5 })
            if (!tp) return
            var lines = ["  most played, " + (period === "all" ? "all time" : "this " + period)]
            lines.push("  artists : " + (tp.artists.map(function (a) { return a.name + " (" + Theme.num(a.plays) + ")" }).join(", ") || "-"))
            lines.push("  albums  : " + (tp.albums.map(function (a) { return a.album + " (" + Theme.num(a.plays) + ")" }).join(", ") || "-"))
            tp.songs.forEach(function (x, k) { lines.push("  " + (k + 1) + ".  " + pad(x.title, 34).slice(0, 40) + "  " + x.artist + "  ×" + Theme.num(x.plays)) })
            say(lines)
            return
        case "eq":
            var e = call("eq")
            if (!e) return
            if (!arg) { say("equaliser " + (e.enabled ? "on: " + e.preset : "off") + "   presets: " + e.presets.join(", "), "dim"); return }
            if (argl === "off" || argl === "on") { call("eq.set", { enabled: argl === "on" }); say("equaliser " + argl); return }
            var preset = e.presets.filter(function (x) { return x.toLowerCase() === argl })[0]
                || e.presets.filter(function (x) { return x.toLowerCase().indexOf(argl) === 0 })[0]
            if (!preset) { say("no preset called “" + arg + "” (eq lists them)", "bad"); return }
            call("eq.set", { preset: preset })
            say("equaliser: " + preset)
            return
        case "out":
            var devs = player.outputDevices
            if (!arg) {
                say(devs.map(function (d, k) { return "  " + k + "  " + d.name + (d.key === player.outputDevice ? "   ← in use" : "") }))
                say("out <number> to switch; out 0 (or default) follows the system", "dim")
                return
            }
            var pickAt = argl === "default" ? 0 : parseInt(arg)
            if (isNaN(pickAt) || pickAt < 0 || pickAt >= devs.length) { say("out takes a number from the list (type out)", "bad"); return }
            player.setOutputDevice(devs[pickAt].key)
            say("sound to: " + devs[pickAt].name)
            return
        case "lyrics":
            if (lyricsCtl.status !== "found") { say(lyricsCtl.status === "loading" ? "looking for lyrics..." : "no lyrics for this song", "dim"); return }
            say(lyricsCtl.synced ? lyricsCtl.lines.map(function (l) { return "  " + (l.text || "") }) : String(lyricsCtl.plain).split("\n").map(function (l) { return "  " + l }))
            return
        case "play":
            if (!arg) { call("play"); return }
            songs = search(arg)
            if (songs.length) { call("play.songs", { ids: songs.map(function (s) { return s.id }) }); say("playing " + Theme.num(songs.length) + (songs.length === 1 ? " song" : " songs") + " matching “" + arg + "”") }
            return
        case "pause": call("pause"); return
        case "toggle": case "p": call("toggle"); return
        case "next":
            if (!arg) { call("next"); return }
            songs = search(arg)
            if (songs.length) { call("queue.add", { ids: [songs[0].id], next: true }); say("next up: " + songs[0].title + " · " + (songs[0].artist || "")) }
            return
        case "prev": case "previous": call("previous"); return
        case "queue": case "enqueue":
            if (!arg) { say(paneLines("queue")); return }
            var qa = argl.split(/\s+/)
            if (qa[0] === "rm" || qa[0] === "remove") {  // numbers as up next shows them: 1 is the song after this one
                var at = parseInt(qa[1])
                if (isNaN(at) || at < 1) { say("queue rm <number>, as up next shows it", "bad"); return }
                var gone = player.queueModel.get(player.currentIndex + at)
                if (!gone.title) { say("nothing at " + at + " in what's next", "bad"); return }
                if (call("queue.remove", { index: player.currentIndex + at }) !== null) say("removed: " + gone.title)
                return
            }
            if (qa[0] === "mv" || qa[0] === "move") {
                var from = parseInt(qa[1]), to = parseInt(qa[2])
                if (isNaN(from) || isNaN(to) || from < 1 || to < 1) { say("queue mv <from> <to>, numbers as up next shows them", "bad"); return }
                if (call("queue.move", { src: player.currentIndex + from, dst: player.currentIndex + to }) !== null) say("moved " + from + " to " + to)
                return
            }
            if (qa[0] === "clear") { call("queue.clear", { upcoming: true }); say("cleared what's next"); return }
            if (qa[0] === "shuffle") { call("queue.shuffle"); say("shuffled what's next"); return }
            songs = search(arg)
            if (songs.length) { call("queue.add", { ids: [songs[0].id] }); say("queued: " + songs[0].title + " · " + (songs[0].artist || "")) }
            return
        case "vol": case "volume":
            if (!arg) { say("volume " + Math.round(player.volume * 100) + "%"); return }
            n = parseFloat(arg)
            if (isNaN(n)) { say("vol takes a number, like vol 50 or vol +5", "bad"); return }
            var r = /^[+-]/.test(arg) ? call("volume", { change: n / 100 }) : call("volume", { volume: n / 100 })
            if (r) say("volume " + Math.round(r.volume * 100) + "%")
            return
        case "mute": call("mute"); return
        case "seek":
            if (!player.hasTrack) { say("nothing playing", "bad"); return }
            n = seconds(arg.replace(/^[+-]/, ""))
            if (isNaN(n)) { say("seek takes a time, like seek 1:30, seek +10 or seek -10", "bad"); return }
            var to = arg[0] === "+" ? player.position + n * 1000 : arg[0] === "-" ? player.position - n * 1000 : n * 1000
            call("seek", { position: Math.max(0, Math.min(player.duration, to)) })
            return
        case "shuffle":
            var s = call("shuffle", argl === "on" ? { on: true } : argl === "off" ? { on: false } : {})
            if (s) say("shuffle " + (s.shuffle ? "on" : "off"))
            return
        case "repeat":
            var modes = { off: 0, all: 1, one: 2 }
            var rp = call("repeat", argl in modes ? { mode: modes[argl] } : {})
            if (rp) say("repeat " + ["off", "all", "one"][rp.repeat])
            return
        case "like":
            if (!player.hasTrack || !np.track.path) { say("nothing to like", "bad"); return }
            userLib.toggleLike(np.track.path)
            say(userLib.isLiked(np.track.path) ? "liked ♥" : "unliked")
            return
        case "sleep":
            if (argl === "track" || argl === "album") call("sleep", { end: argl })
            else if (argl === "off") call("sleep", { minutes: 0 })
            else if (!isNaN(parseInt(arg))) call("sleep", { minutes: parseInt(arg) })
            else { say("sleep takes minutes, track, album or off", "bad"); return }
            say("sleep timer: " + (argl === "off" ? "off" : arg))
            return
        case "radio":
            var rd = call("radio", argl === "on" ? { on: true } : argl === "off" ? { on: false } : {})
            if (rd) say("radio " + (rd.radio ? "on" : "off"))
            return
        case "pin": case "unpin":
            if (allPanes.indexOf(argl) < 0) { say("panes: " + allPanes.join(", "), "bad"); return }
            var list = panes.filter(function (p) { return p !== argl })
            if (word === "pin") list.push(argl)
            setPanes(list)
            if (word === "pin" && argl === "tags") refreshTags()
            if (word === "pin" && argl === "similar" && np.track.artist) similarArtists.ensure(np.track.artist)
            say(word === "pin" ? "pinned " + argl : "unpinned " + argl)
            return
        case "panes": say("showing: " + (panes.join(", ") || "(none)") + "   ·   all: " + allPanes.join(", "), "dim"); return
        case "phosphor":
            if (["green", "amber", "theme"].indexOf(argl) < 0) { say("phosphor green, amber or theme", "bad"); return }
            shell.setUiValue("neonPhosphor", argl)
            return
        case "theme":
            if (!arg) { say("themes: " + themeManager.availableThemes.join(", "), "dim"); return }
            var match = themeManager.availableThemes.filter(function (x) { return x.toLowerCase() === argl })[0]
            if (!match) { say("no theme called “" + arg + "”", "bad"); return }
            themeManager.selectTheme(match)
            return
        case "cockpit": case "classic": shell.setUiValue("neonNowPlaying", word); return
        case "exit": case "quit": case "logout": np.closeRequested(); return
        case "sudo": say("nice try. this is a music player.", "dim"); return
        }
        if (allPanes.indexOf(word) >= 0) {
            if (word === "tags") refreshTags()
            if (word === "similar" && np.track.artist) similarArtists.ensure(np.track.artist)
            say(paneLines(word))
            return
        }
        say(word + ": command not found (try help)", "bad")
    }

    // --- layout: the panes, and the console (beside them in a wide window, below them otherwise) ----------------
    Flickable {
        id: paneArea
        anchors { left: parent.left; top: parent.top; leftMargin: 32 * np.u; topMargin: 84
                  right: term.wide ? console_.left : parent.right; rightMargin: term.wide ? 24 : 32 * np.u
                  bottom: term.wide ? parent.bottom : console_.top; bottomMargin: term.wide ? 28 : 12 }
        contentHeight: paneCol.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}
        Column {
            id: paneCol
            width: paneArea.width
            spacing: 2
            Text {
                width: parent.width
                textFormat: Text.PlainText
                text: "AFTERIMAGE TERMINAL  ::  wired link " + (player.playing ? "up" : "idle")
                color: term.dim; font.family: np.mono; font.pixelSize: term.fs
            }
            Repeater {
                model: term.panes
                Column {
                    id: pane
                    required property string modelData
                    width: paneCol.width
                    topPadding: term.fs * 0.6
                    Text {
                        textFormat: Text.PlainText
                        text: "> " + term.paneNames[pane.modelData]
                        color: term.prompt; font.family: np.mono; font.pixelSize: term.fs
                    }
                    Text {
                        objectName: "terminalPane_" + pane.modelData
                        visible: pane.modelData !== "wave"
                        width: parent.width
                        textFormat: Text.PlainText
                        wrapMode: pane.modelData === "spectrum" ? Text.NoWrap : Text.Wrap
                        text: visible ? term.paneLines(pane.modelData).join("\n") : ""
                        color: term.ink; font.family: np.mono; font.pixelSize: term.fs
                        lineHeight: pane.modelData === "spectrum" ? 0.9 : 1
                    }
                    // the waveform: what's been played bright, what's to come dim, the playhead between
                    Row {
                        visible: pane.modelData === "wave"
                        readonly property var peaks: visible ? (player.waveform || []) : []
                        readonly property int n: Math.max(16, Math.min(160, term.cols - 2))
                        readonly property string chars: {
                            if (!peaks.length) return ""
                            var s = "", blocks = "▁▂▃▄▅▆▇█"
                            for (var i = 0; i < n; i++) {
                                var a = Math.floor(i * peaks.length / n), b = Math.max(a + 1, Math.floor((i + 1) * peaks.length / n)), m = 0
                                for (var j = a; j < b; j++) m = Math.max(m, peaks[j] || 0)
                                s += blocks[Math.max(0, Math.min(7, Math.round(m * 7)))]
                            }
                            return s
                        }
                        readonly property int at: Math.round(np.progress * n)
                        Text { textFormat: Text.PlainText; text: "  " + (parent.chars ? parent.chars.slice(0, parent.at) : "(the waveform is being worked out)"); color: term.ink; font.family: np.mono; font.pixelSize: term.fs }
                        Text { textFormat: Text.PlainText; text: parent.chars.slice(parent.at); color: term.dim; font.family: np.mono; font.pixelSize: term.fs }
                    }
                }
            }
            // the controls, as commands you can click
            Flow {
                width: paneCol.width
                topPadding: term.fs
                spacing: term.fs
                Repeater {
                    model: [
                        { t: "[ prev ]", c: "prev" }, { t: player.playing ? "[ pause ]" : "[ play ]", c: "p" },
                        { t: "[ next ]", c: "next" }, { t: player.shuffle ? "[ shuffle:on ]" : "[ shuffle:off ]", c: "shuffle" },
                        { t: player.repeat === 2 ? "[ repeat:one ]" : player.repeat ? "[ repeat:all ]" : "[ repeat:off ]", c: "repeat" }
                    ]
                    Text {
                        required property var modelData
                        textFormat: Text.PlainText
                        text: modelData.t
                        color: cmd.containsMouse ? Theme.onAccent : term.prompt
                        font.family: np.mono; font.pixelSize: term.fs
                        Rectangle { anchors.fill: parent; z: -1; color: term.prompt; visible: cmd.containsMouse }
                        MouseArea { id: cmd; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: term.run(modelData.c) }
                        Accessible.role: Accessible.Button
                        Accessible.name: modelData.t.replace(/[\[\]]/g, "").trim()
                        Accessible.onPressAction: term.run(modelData.c)
                    }
                }
            }
        }
    }

    // the console
    Rectangle {
        id: console_
        objectName: "terminalConsole"
        // (plain geometry, not anchors switched on and off: those left it stuck at the wide size)
        x: term.wide ? parent.width - width - 32 * np.u : 32 * np.u
        y: term.wide ? 84 : parent.height - height - 28
        width: term.wide ? parent.width * 0.4 : parent.width - 64 * np.u
        height: term.wide ? parent.height - 84 - 28 : Math.max(150, parent.height * 0.36)
        color: Qt.rgba(term.ink.r, term.ink.g, term.ink.b, 0.04)
        border.width: 1; border.color: Qt.rgba(term.ink.r, term.ink.g, term.ink.b, 0.35)
        ListView {
            id: scrollback
            anchors { left: parent.left; right: parent.right; top: parent.top; bottom: inputRow.top; margins: 12; bottomMargin: 4 }
            clip: true
            model: term.out
            boundsBehavior: Flickable.StopAtBounds
            delegate: Text {
                required property var modelData
                width: scrollback.width
                textFormat: Text.PlainText
                wrapMode: Text.Wrap  // (at spaces; a word longer than the line still breaks)
                text: modelData.t
                color: term.colorOf(modelData.k)
                font.family: np.mono; font.pixelSize: term.fs * 0.9
            }
            onCountChanged: Qt.callLater(positionViewAtEnd)
            ScrollBar.vertical: ScrollBar {}
        }
        Row {
            id: inputRow
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 12 }
            spacing: 6
            Text { id: caret; textFormat: Text.PlainText; text: ">"; color: term.prompt; font.family: np.mono; font.pixelSize: term.fs * 0.9 }
            TextInput {
                id: input
                objectName: "terminalInput"
                width: parent.width - caret.width - 6
                color: term.ink
                selectionColor: term.prompt
                selectedTextColor: Theme.onAccent
                font.family: np.mono; font.pixelSize: term.fs * 0.9
                cursorVisible: activeFocus
                maximumLength: 300
                Accessible.role: Accessible.EditableText
                Accessible.name: "Terminal command"
                Text {
                    visible: !input.text && !input.activeFocus
                    textFormat: Text.PlainText
                    text: "type a command (help)"
                    color: term.dim; font: input.font
                }
                Keys.onReturnPressed: { term.run(text); text = "" }
                Keys.onEnterPressed: { term.run(text); text = "" }
                Keys.onEscapePressed: function (event) { if (text) text = ""; else { focus = false; event.accepted = false } }
                Keys.onUpPressed: {
                    if (!term.typed.length) return
                    term.typedAt = term.typedAt < 0 ? term.typed.length - 1 : Math.max(0, term.typedAt - 1)
                    text = term.typed[term.typedAt]
                }
                Keys.onDownPressed: {
                    if (term.typedAt < 0) return
                    term.typedAt = term.typedAt + 1 >= term.typed.length ? -1 : term.typedAt + 1
                    text = term.typedAt < 0 ? "" : term.typed[term.typedAt]
                }
                Keys.onTabPressed: {
                    var w = text.trim().toLowerCase()
                    if (!w || w.indexOf(" ") >= 0) return
                    var hits = term.commands.filter(function (c) { return c.indexOf(w) === 0 })
                    if (hits.length === 1) text = hits[0] + " "
                    else if (hits.length > 1) term.say(hits.join("  "), "dim")
                }
            }
        }
        MouseArea {  // a click anywhere in the console types there
            anchors.fill: parent
            z: -1
            onClicked: input.forceActiveFocus()
            Accessible.role: Accessible.Pane
            Accessible.name: "Terminal console"
        }
    }
}
