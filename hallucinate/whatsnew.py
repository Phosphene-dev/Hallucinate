"""What's new in this version, shown once after an update (not on a first start). A few lines a person reads
in ten seconds; the changelog has the rest."""

HIGHLIGHTS = {
    "1.2.0": [
        "Two retro themes, Hi-Fi Deck and Beige Box, restyle the whole app like 90s hardware. They open Now "
        "Playing as the Deck: a hi-fi front panel with a cassette, a glowing display, an analyser and VU meters "
        "(the cassette button there switches to it in any theme).",
        "Run Hallucinate without a window on a home server (hallucinate --headless), and control it from the "
        "command line (hallucinate cmd) or a terminal player (hallucinate tui).",
    ],
    "1.1.0": [
        "Control Hallucinate from your phone or another computer's browser: Settings → Remote & web. It's off "
        "until you switch it on, and only devices you pair with a one-time code can use it.",
        "A security pass: every download is now in one signed checksum list, and notifications show song "
        "titles as plain text.",
    ],
    "1.0.0": [
        "Composers: Artists → Composers, and a page for each with their works and movements in order. Tempo and "
        "key from the tags too, to sort by and use in smart playlists.",
        "Playlist folders in the sidebar (right-click a playlist → Move to folder).",
        "Music server songs can be kept on this computer, to play without the server, offline mode included.",
        "Search forgives typos, finds songs by genre and composer, and artist pages can show similar artists "
        "from Last.fm. Your library reads its files once more, for the new tags.",
    ],
    "0.9.9.9": [
        "Settings is calmer: rarely needed options sit in subsections you can open, and Internet is now Online & "
        "privacy and Scrobbling & sharing. There's a text size choice too.",
        "Mute with the volume icon or M; the queue shows the time left and can clear what's coming up.",
        "Song rows link to their artist and album, artist and genre pages have a ⋯ menu, and Ctrl+K finds genres.",
        "Lots of fixes: moved files keep their plays and likes, scrobbles never get stuck, Play next works with "
        "shuffle, and the equalizer can't distort.",
    ],
    "0.9.9.8": [
        "Every genre has a page with its albums, artists and songs. Click a genre on an album, an artist, Now "
        "Playing or a song's menu to open it.",
        "Albums → Genres shows every genre, and Songs can be sorted by genre (or artist, album or year).",
    ],
    "0.9.9.7": [
        "Albums can have several genres, the main one first. Filters and smart playlists match any of them, "
        "and Settings → Library chooses whether pages show all of them or just the main one.",
        "Genres can also come from Discogs (with a personal token) and Last.fm, next to MusicBrainz. Genres "
        "you set yourself are never replaced.",
        "Artist pages can show a bio from Wikipedia, Last.fm or Discogs (switch on looking them up in Settings → "
        "Internet & sharing), or one you write yourself.",
        "Pages stay a readable width on ultrawide screens.",
    ],
    "0.9.9.6": [
        "Saving genres found online for many albums is much faster, shows how far it has got (with Stop), "
        "and no longer makes the library rescan over and over.",
        "Tags that fit in the room a file keeps for them are written in place, so editing tags is quicker too.",
    ],
    "0.9.9.5": [
        "Fixed: the window could stop responding while ReplayGain measured your music. Songs are now measured "
        "in a separate helper, so a file the decoder chokes on can't freeze the app.",
        "The Aurora, Halo and Waves visualizers work on every graphics driver, and glow for dark covers too.",
        "Narrow windows: nothing runs off the edge, the sidebar folds to icons when there's no room, and the "
        "player bar keeps its parts apart.",
        "Shrimp Boat, a soft peach, as an accent colour.",
    ],
    "0.9.9.4": [
        "Music servers: songs on your Jellyfin, Navidrome or other Subsonic server join your library "
        "(switch it on in Settings → Features, then add a server in Settings → Music servers).",
        "Star ratings are saved in the songs' own tags, and a cover you add is saved as cover.jpg in the "
        "album's folder, so other players see them too.",
        "What you choose stays chosen: a cover you picked, a rating you cleared and your own lyrics are no "
        "longer replaced.",
        "Fixed: the window could stop responding while left open, with a radio station from last time. "
        "Slow networks, sleeping disks and locked keyrings can't freeze it any more.",
    ],
    "0.9.9.3": [
        "Rearrange the sidebar: drag an entry, right-click it, or use Settings → Features.",
        "Find genres online, for one album in Edit album or for every album without one in Library health. "
        "You check what's found before anything is saved.",
        "Internet radio lists the songs you heard, and radio and podcasts show how much you've listened.",
        "Podcast episodes can count on Last.fm and ListenBrainz if you want (Settings → Internet & sharing).",
        "A full review for bugs and safety: safer links, downloads, updates and saving, and many small fixes.",
    ],
    "0.9.9.2": [
        "Undo on the toasts after removing songs, clearing the queue, removing a station or marking a show played.",
        "Click the playing song's cover or title to go to its album, station or show.",
        "Song and episode lists work from the keyboard: arrows, Page Up/Down, Home, End, Enter and the Menu key.",
        "Podcasts get their own settings: skip lengths, how often feeds are checked, what's kept, Up next across "
        "shows, show settings (speed, skip intro and outro, oldest first) and new-episode notifications.",
        "Your own accent colour, themes that follow the system's light or dark mode, making your own theme, "
        "and the new Ribbon theme.",
        "Two new visualizer styles, Halo and Waves, and a Reduce motion setting.",
        "Back up and restore your likes, ratings, playlists, history, stations and podcasts (Settings → Library).",
        "Search covers stations and podcasts too, and pages remember where you'd scrolled to.",
        "An equalizer for each output device, Liked Songs in step with Last.fm loves, MusicBrainz lookup in the "
        "album tag editor, and ReplayGain measured for new music by itself (each is optional).",
    ],
}


def highlights(version):
    return list(HIGHLIGHTS.get(version, []))
