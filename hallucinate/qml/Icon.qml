import QtQuick
import "."

Canvas {
    id: c
    property string name: ""
    property bool filled: false
    property color color: Theme.text
    implicitWidth: 20
    implicitHeight: 20
    onNameChanged: requestPaint()
    onFilledChanged: requestPaint()
    onColorChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    onPaint: {
        var ctx = getContext("2d")
        ctx.reset()
        var w = width, h = height
        ctx.fillStyle = color
        ctx.strokeStyle = color
        ctx.lineWidth = Math.max(1.6, w / 11)
        ctx.lineCap = "round"
        ctx.lineJoin = "round"
        function tri(a, b, c2, d, e, f) {
            ctx.beginPath(); ctx.moveTo(a, b); ctx.lineTo(c2, d); ctx.lineTo(e, f); ctx.closePath(); ctx.fill()
        }
        function line(pts) {
            ctx.beginPath(); ctx.moveTo(pts[0] * w, pts[1] * h)
            for (var i = 2; i < pts.length; i += 2) ctx.lineTo(pts[i] * w, pts[i + 1] * h)
            ctx.stroke()
        }
        var kind = name.split(":")[0], arg = name.split(":")[1] || ""
        switch (kind) {
        case "play": tri(w*.25, h*.12, w*.25, h*.88, w*.88, h*.5); break
        case "pause": ctx.fillRect(w*.2, h*.14, w*.2, h*.72); ctx.fillRect(w*.6, h*.14, w*.2, h*.72); break
        case "next": tri(w*.12, h*.2, w*.12, h*.8, w*.66, h*.5); ctx.fillRect(w*.72, h*.2, w*.14, h*.6); break
        case "prev": tri(w*.88, h*.2, w*.88, h*.8, w*.34, h*.5); ctx.fillRect(w*.14, h*.2, w*.14, h*.6); break
        case "shuffle":
            line([.08,.3,.38,.3,.62,.7,.8,.7]); line([.08,.7,.38,.7,.62,.3,.8,.3])
            tri(w*.78,h*.18,w*.96,h*.3,w*.78,h*.42); tri(w*.78,h*.58,w*.96,h*.7,w*.78,h*.82); break
        case "repeat": case "repeat1":
            line([.15,.5,.15,.3,.78,.3]); tri(w*.74,h*.14,w*.96,h*.3,w*.74,h*.46)
            line([.85,.5,.85,.7,.22,.7]); tri(w*.26,h*.54,w*.04,h*.7,w*.26,h*.86)
            if (name === "repeat1") { ctx.font = "bold " + Math.round(h*.45) + "px sans-serif"; ctx.textAlign = "center"; ctx.fillText("1", w*.5, h*.62) }  // i18n: keep
            break
        case "radio":  // broadcast waves around a dot
            ctx.beginPath(); ctx.arc(w*.5, h*.5, w*.09, 0, 2*Math.PI); ctx.fill()
            for (var r = 1; r <= 2; r++) {
                ctx.beginPath(); ctx.arc(w*.5, h*.5, w*(.12 + .17*r), -Math.PI/4, Math.PI/4); ctx.stroke()
                ctx.beginPath(); ctx.arc(w*.5, h*.5, w*(.12 + .17*r), Math.PI*3/4, Math.PI*5/4); ctx.stroke()
            }
            break
        case "cast":  // a screen with waves rising from its corner (playing on another device)
            line([.1,.4,.1,.2,.9,.2,.9,.8,.62,.8])
            ctx.beginPath(); ctx.moveTo(w*.1, h*.84); ctx.arc(w*.1, h*.84, w*.12, -Math.PI/2, 0); ctx.closePath(); ctx.fill()
            for (var cr = 1; cr <= 2; cr++) { ctx.beginPath(); ctx.arc(w*.1, h*.84, w*(.12 + .17*cr), -Math.PI/2, 0); ctx.stroke() }
            break
        case "computer": line([.1,.16,.9,.16,.9,.66,.1,.66,.1,.16]); line([.5,.66,.5,.82]); line([.3,.84,.7,.84]); break
        case "speaker":
            line([.28,.08,.72,.08,.72,.92,.28,.92,.28,.08])
            ctx.beginPath(); ctx.arc(w*.5, h*.62, w*.15, 0, 2*Math.PI); ctx.stroke()
            ctx.beginPath(); ctx.arc(w*.5, h*.26, w*.05, 0, 2*Math.PI); ctx.fill()
            break
        case "phone": line([.3,.06,.7,.06,.7,.94,.3,.94,.3,.06]); line([.44,.84,.56,.84]); break
        case "tv": line([.08,.2,.92,.2,.92,.76,.08,.76,.08,.2]); line([.34,.88,.66,.88]); line([.36,.06,.5,.2,.64,.06]); break
        case "expand": line([.15,.55,.15,.15,.55,.15]); line([.85,.45,.85,.85,.45,.85]); line([.15,.15,.45,.45]); line([.85,.85,.55,.55]); break
        case "queue": line([.1,.25,.9,.25]); line([.1,.5,.9,.5]); line([.1,.75,.55,.75]); break
        case "volume":
            ctx.beginPath(); ctx.moveTo(w*.1,h*.38); ctx.lineTo(w*.3,h*.38); ctx.lineTo(w*.52,h*.18); ctx.lineTo(w*.52,h*.82); ctx.lineTo(w*.3,h*.62); ctx.lineTo(w*.1,h*.62); ctx.closePath(); ctx.fill()
            ctx.beginPath(); ctx.arc(w*.5, h*.5, w*.3, -0.9, 0.9); ctx.stroke(); break
        case "plus": line([.5,.18,.5,.82]); line([.18,.5,.82,.5]); break
        case "minus": line([.18,.5,.82,.5]); break
        case "heart":
            ctx.beginPath()
            ctx.moveTo(w*.5, h*.86)
            ctx.bezierCurveTo(w*.05, h*.55, w*.05, h*.18, w*.28, h*.18)
            ctx.bezierCurveTo(w*.42, h*.18, w*.5, h*.3, w*.5, h*.3)
            ctx.bezierCurveTo(w*.5, h*.3, w*.58, h*.18, w*.72, h*.18)
            ctx.bezierCurveTo(w*.95, h*.18, w*.95, h*.55, w*.5, h*.86)
            ctx.closePath()
            if (filled) ctx.fill(); else ctx.stroke()
            break
        case "grip":  // a reorder handle: three short bars, as lists that drag rows use
            line([.22,.34,.78,.34]); line([.22,.5,.78,.5]); line([.22,.66,.78,.66]); break
        case "more":
            for (var k = 0; k < 3; k++) { ctx.beginPath(); ctx.arc(w*(.2 + .3*k), h*.5, w*.075, 0, Math.PI*2); ctx.fill() }
            break
        case "note":
            ctx.beginPath(); ctx.arc(w*.3, h*.75, w*.14, 0, Math.PI*2); ctx.fill(); line([.44,.75,.44,.15,.8,.25])
            break
        case "close": line([.22,.22,.78,.78]); line([.78,.22,.22,.78]); break
        // the window's own buttons (the title bar built into the window)
        case "winmin": line([.24,.62,.76,.62]); break
        case "winmax": line([.24,.24,.76,.24,.76,.76,.24,.76,.24,.24]); break
        case "winrestore":  // two windows, one behind the other
            line([.36,.36,.36,.2,.8,.2,.8,.64,.64,.64]); line([.2,.36,.64,.36,.64,.8,.2,.8,.2,.36]); break
        case "trash":  // a bin with a lid
            line([.16,.26,.84,.26]); line([.4,.26,.4,.14,.6,.14,.6,.26])
            line([.24,.26,.3,.86,.7,.86,.76,.26]); line([.43,.42,.43,.7]); line([.57,.42,.57,.7]); break
        case "edit":  // a pencil
            line([.18,.82,.22,.64,.66,.2,.8,.34,.36,.78,.18,.82]); line([.58,.28,.72,.42]); break
        case "remove":  // a circled minus
            ctx.beginPath(); ctx.arc(w*.5, h*.5, w*.36, 0, Math.PI*2); ctx.stroke(); line([.32,.5,.68,.5]); break
        case "back": line([.62,.15,.3,.5,.62,.85]); break
        case "forward": line([.38,.15,.7,.5,.38,.85]); break
        case "home":
            line([.12,.48,.5,.14,.88,.48]); line([.22,.4,.22,.86,.78,.86,.78,.4]); line([.42,.86,.42,.62,.58,.62,.58,.86]); break
        case "album":  // a record
            ctx.beginPath(); ctx.arc(w*.5, h*.5, w*.38, 0, Math.PI*2); ctx.stroke()
            ctx.beginPath(); ctx.arc(w*.5, h*.5, w*.1, 0, Math.PI*2); ctx.fill()
            ctx.beginPath(); ctx.arc(w*.5, h*.5, w*.24, -0.6, 0.4); ctx.stroke(); break
        case "artist":
            ctx.beginPath(); ctx.arc(w*.5, h*.34, w*.17, 0, Math.PI*2); ctx.stroke()
            ctx.beginPath(); ctx.arc(w*.5, h*.98, w*.34, Math.PI*1.12, Math.PI*1.88); ctx.stroke(); break
        case "songs":
            line([.1,.24,.56,.24]); line([.1,.46,.56,.46]); line([.1,.68,.4,.68])
            ctx.beginPath(); ctx.arc(w*.68, h*.76, w*.1, 0, Math.PI*2); ctx.fill(); line([.78,.76,.78,.2,.92,.26]); break
        case "stats":
            ctx.fillRect(w*.14, h*.52, w*.16, h*.34); ctx.fillRect(w*.42, h*.18, w*.16, h*.68); ctx.fillRect(w*.7, h*.38, w*.16, h*.48); break
        case "wave":  // the logo's waveform bars
            var bars = [.2, .45, .75, .4, .9, .55, .3]
            for (var b = 0; b < bars.length; b++) {
                var bx = w * (.12 + b * .127), bh = h * bars[b]
                ctx.fillRect(bx, (h - bh) / 2, Math.max(1.5, w * .07), bh)
            }
            break
        case "settings":
            ctx.beginPath(); ctx.arc(w*.5, h*.5, w*.14, 0, Math.PI*2); ctx.stroke()
            for (var g = 0; g < 8; g++) {
                var a = g * Math.PI / 4
                line([.5 + .26*Math.cos(a), .5 + .26*Math.sin(a), .5 + .4*Math.cos(a), .5 + .4*Math.sin(a)])
            }
            ctx.beginPath(); ctx.arc(w*.5, h*.5, w*.27, 0, Math.PI*2); ctx.stroke(); break
        case "playlist":
            line([.1,.24,.62,.24]); line([.1,.46,.62,.46]); line([.1,.68,.42,.68]); tri(w*.6,h*.56,w*.6,h*.88,w*.9,h*.72); break
        case "sidebar":
            ctx.strokeRect(w*.12, h*.18, w*.76, h*.64); line([.38,.18,.38,.82]); break
        case "recap":  // a calendar with a small bar chart: a period summed up
            ctx.strokeRect(w*.14, h*.2, w*.72, h*.66); line([.14,.38,.86,.38]); line([.34,.12,.34,.26]); line([.66,.12,.66,.26])
            ctx.fillRect(w*.28, h*.6, w*.1, h*.16); ctx.fillRect(w*.45, h*.5, w*.1, h*.26); ctx.fillRect(w*.62, h*.56, w*.1, h*.2); break
        case "smartlist":  // a list beside a filter funnel: a playlist made from rules
            line([.08,.24,.44,.24]); line([.08,.46,.38,.46]); line([.08,.68,.32,.68])
            line([.52,.2,.92,.2,.76,.48,.76,.8,.68,.74,.68,.48,.52,.2]); break
        case "health":  // a pulse line
            line([.06,.54,.28,.54,.4,.22,.58,.82,.7,.54,.94,.54]); break
        case "duplicates":  // two overlapping pages
            ctx.strokeRect(w*.14, h*.14, w*.48, h*.56); ctx.strokeRect(w*.38, h*.32, w*.48, h*.56); break
        case "download":  // an arrow into a tray
            line([.5,.12,.5,.62]); line([.3,.44,.5,.64,.7,.44]); line([.14,.66,.14,.86,.86,.86,.86,.66]); break
        case "dice":
            ctx.strokeRect(w*.16, h*.16, w*.68, h*.68)
            var pips = [[.34,.34],[.66,.66],[.5,.5],[.66,.34],[.34,.66]]
            for (var q = 0; q < pips.length; q++) { ctx.beginPath(); ctx.arc(w*pips[q][0], h*pips[q][1], w*.06, 0, Math.PI*2); ctx.fill() }
            break
        case "fullscreen":  // four corners
            line([.14,.36,.14,.14]); line([.14,.14,.36,.14]); line([.64,.14,.86,.14]); line([.86,.14,.86,.36])
            line([.86,.64,.86,.86]); line([.86,.86,.64,.86]); line([.36,.86,.14,.86]); line([.14,.86,.14,.64]); break
        case "sort":  // lines shortening downwards, beside an arrow: put in order
            line([.1,.24,.56,.24]); line([.1,.46,.44,.46]); line([.1,.68,.32,.68])
            line([.76,.18,.76,.82]); line([.64,.68,.76,.82,.88,.68]); break
        case "down":
            line([.22,.38,.5,.66]); line([.5,.66,.78,.38]); break
        case "up":
            line([.22,.62,.5,.34]); line([.5,.34,.78,.62]); break
        case "vinyl":
            ctx.beginPath(); ctx.arc(w*.5, h*.5, w*.4, 0, Math.PI*2); ctx.stroke()
            ctx.beginPath(); ctx.arc(w*.5, h*.5, w*.24, -0.6, 1.2); ctx.stroke()
            ctx.beginPath(); ctx.arc(w*.5, h*.5, w*.08, 0, Math.PI*2); ctx.fill(); break
        case "deck":  // a cassette: the shell, its two reels and the tape window
            ctx.beginPath(); ctx.moveTo(w*.08, h*.22); ctx.lineTo(w*.92, h*.22); ctx.lineTo(w*.92, h*.8)
            ctx.lineTo(w*.08, h*.8); ctx.closePath(); ctx.stroke()
            ctx.beginPath(); ctx.arc(w*.32, h*.46, w*.09, 0, Math.PI*2); ctx.stroke()
            ctx.beginPath(); ctx.arc(w*.68, h*.46, w*.09, 0, Math.PI*2); ctx.stroke()
            line([.24,.8,.3,.66,.7,.66,.76,.8]); break
        case "genre":  // a tag, with the hole it hangs by
            line([.12,.5,.12,.2,.42,.2,.88,.6,.58,.9,.12,.5])
            ctx.beginPath(); ctx.arc(w*.28, h*.36, w*.06, 0, Math.PI*2); ctx.stroke(); break
        case "folder":
            line([.1,.26,.1,.82,.9,.82,.9,.34,.48,.34,.4,.22,.1,.22,.1,.3]); break
        case "history":  // a clock
            ctx.beginPath(); ctx.arc(w*.5, h*.5, w*.38, 0, Math.PI*2); ctx.stroke()
            line([.5,.26,.5,.5]); line([.5,.5,.67,.62]); break
        case "station":  // a radio set: an antenna, the body, a dial and its speaker grille
            line([.3,.32,.72,.1])
            ctx.beginPath(); ctx.moveTo(w*.18, h*.34); ctx.lineTo(w*.82, h*.34); ctx.lineTo(w*.82, h*.86)
            ctx.lineTo(w*.18, h*.86); ctx.closePath(); ctx.stroke()
            ctx.beginPath(); ctx.arc(w*.64, h*.6, w*.1, 0, Math.PI*2); ctx.stroke()
            line([.28,.52,.42,.52]); line([.28,.68,.42,.68]); break
        case "podcast":  // a microphone on a stand
            ctx.beginPath(); ctx.moveTo(w*.38, h*.24); ctx.arc(w*.5, h*.24, w*.12, Math.PI, 0)
            ctx.lineTo(w*.62, h*.46); ctx.arc(w*.5, h*.46, w*.12, 0, Math.PI); ctx.closePath(); ctx.stroke()
            ctx.beginPath(); ctx.arc(w*.5, h*.46, w*.24, 0, Math.PI); ctx.stroke()
            line([.5,.7,.5,.88]); line([.34,.88,.66,.88]); break
        case "skipback":  // a circular arrow turning back, with the seconds in it
        case "skipfwd":
            var back = kind === "skipback"
            ctx.beginPath()
            if (back) ctx.arc(w*.5, h*.54, w*.36, Math.PI*1.25, Math.PI*0.95, false)
            else ctx.arc(w*.5, h*.54, w*.36, Math.PI*1.75, Math.PI*2.05, true)
            ctx.stroke()
            if (back) line([.16,.12,.24,.3,.42,.22])
            else line([.84,.12,.76,.3,.58,.22])
            ctx.font = "bold " + Math.round(h * .42) + "px sans-serif"  // i18n: keep
            ctx.textAlign = "center"; ctx.textBaseline = "middle"
            ctx.fillText(arg || (back ? "15" : "30"), w*.5, h*.57)
            break
        case "check": line([.18,.52,.42,.76,.84,.28]); break
        case "search":
            ctx.beginPath(); ctx.arc(w*.42, h*.42, w*.28, 0, Math.PI*2); ctx.stroke(); line([.64,.64,.9,.9]); break
        }
    }
}
