"""What's new in this version, shown once after an update (not on a first start). A few lines a person reads
in ten seconds; the changelog has the rest."""

HIGHLIGHTS = {
    "0.9.9.2": [
        "Undo on the toasts after removing songs, clearing the queue, removing a station or marking a show played.",
        "Click the playing song's cover or title to go to its album, station or show.",
        "Song and episode lists work from the keyboard: arrows, Page Up/Down, Home, End, Enter and the Menu key.",
        "Podcasts get their own settings: skip lengths, how often feeds are checked, what's kept, Up next across "
        "shows, show settings (speed, skip intro and outro, oldest first) and new-episode notifications.",
        "Your own accent colour, themes that follow the system's light or dark mode, making your own theme, "
        "and the new Ribbon theme.",
        "Two new visualizer styles, Halo and Waves, and a Reduce motion setting.",
    ],
}


def highlights(version):
    return list(HIGHLIGHTS.get(version, []))
