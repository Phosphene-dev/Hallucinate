# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- Settings → Features: switch off what you don't use (Liked Songs, Folders, Stats, History, Recap, Visualizer, Library health, lyrics, and each card on Home). It disappears everywhere: the sidebar, Ctrl+K, links and shortcuts. Switch it back on and everything is still there.
- Internet radio (off until you switch it on in Settings → Features). Save stations by their stream link (.pls and .m3u links work too), import or export them as playlist files, or find them in the Radio Browser directory. The song a station is playing shows as the artist and title everywhere, including the tray, media keys and Discord. Dropped streams reconnect by themselves. Radio never counts toward your stats, history or recap; songs heard on the radio can count on Last.fm and ListenBrainz if you choose to (Settings → Internet & sharing). Offline mode stops it all.
- Podcasts (off until you switch them on in Settings → Features). Follow shows by their feed link, find them in the Apple Podcasts directory, bring your list from another app (OPML import and export), or add a folder of episode files. Episodes pick up where you stopped, show how much is left, and are marked played when you finish them; Podcasts shows what you were listening to and what's new. Download episodes to listen offline, by hand or automatically for a show, and have them removed once played. Chapters, skip back 15 s and forward 30 s, and a playback speed of their own (up to 3×) that doesn't change the music's. Episodes never count toward your stats, history or recap.

### Fixed
- The right-click menu in text fields uses the app's theme (it was a native menu with a white highlight that was hard to read).

## [0.9.9] - 2026-10-16

Right-click menus everywhere, back and forward like a browser, and fixes for narrow windows.

### Added
- Right-click works on everything you'd expect: songs everywhere (lists, queue, history, the playing song, Now Playing's cover), artists, folders, playlists in the sidebar, top artists and albums on Stats, and the random album on Home. The menus match the rest of the app.
- Songs can be removed from the library or moved to the trash, one at a time or as a selection ("More…" on the selection bar). The song menu also has Go to album, Go to artist, Show in folder, and Remove from the queue.
- Library health: every listed item opens its usual menu on right-click or long press, and clicking it opens the album or plays the song. Duplicates gets "Keep the best copies", which hides every copy but the best one of each song (lossless first, then bitrate and sample rate). Nothing is deleted.
- Back and forward like a browser: the mouse's back and forward buttons, plus Alt+← and Alt+→, step through the pages you've visited, across sections too.

### Fixed
- Home at narrow window sizes: the format breakdown no longer spills out of its card (the four facts go two by two when space is short), and this month's top artists stay inside the Listening card.
- The 12-month heatmap on History shows the most recent weeks that fit instead of running past its card in a narrow window.
- Letters on covers without art (artist avatars, Library health rows) are readable in every theme.

## [0.9.8] - 2026-10-13

Getting ready for testers: crashes leave a report, downloads are less than half the size, and the app starts
faster, uses less power while it waits and works better with screen readers.

### Added
- If Hallucinate crashes or runs into an error it can't handle, the next start offers a report to copy into a bug report: what went wrong, with the same setup details as Copy debug info. It never includes file paths, names or anything from your library.

### Changed
- Much smaller downloads: the AppImage is 108 MB instead of 270 MB, the macOS app 66 MB instead of 179 MB, and the Windows downloads less than half their size. They used to carry all of Qt, including a web browser engine Hallucinate never uses. Every build is now checked to play MP3, AAC, ALAC, FLAC, Ogg, Opus and WAV before release.
- Faster start: with a big library the window opens in under a second on later starts (the full database check now runs only after a crash, or weekly).
- Less power while idle: the backdrop drifts at a gentler frame rate, the seek bar stops redrawing the window ten times a second while another window has the focus, and a paused Now Playing stops drawing altogether instead of running the visualizer.
- Screen readers: every button, link, card, slider and field now has a spoken name and role, including the main Play/Pause button, album tiles, links on artist and album names, the listening heatmaps and the equalizer bands. Icon buttons say what they do ("Previous track") and toggles say whether they're on.

## [0.9.7.1] - 2026-10-13

### Changed
- New icons in place of the four-point sparkle, each saying what it's for: a calendar with a small chart for Recap, a list with a filter for smart playlists, a pulse line for Library health, overlapping pages for duplicates, and a download arrow for an available update.
- Screenshots and the tour clip show the new icons.

## [0.9.7] - 2026-10-13

### Fixed
- Album covers and artist pictures had jagged, stair-stepped rounded corners, and small round pictures (such as the top artists on Home and Stats) came out as octagons. Their edges are now smooth at every size.
- The update check reads four-part version numbers (such as 1.2.3.4), in case a release ever uses one.

### Changed
- The tour clip at the top of the README is sharp again; it had turned blocky from being compressed twice.
- A new social preview showing the app as it looks now, and the website and README brought up to date.

## [0.9.6] - 2026-10-13

A polish release: menus, dialogs and empty pages now look like the rest of Hallucinate.

### Changed
- Menus, dialogs, dropdowns, tooltips and text fields share the app's look: glass panels with soft shadows, rounded corners, the display font for dialog titles, pill buttons (the confirming one in the accent colour) and a short fade as they open. The page behind a dialog dims.
- Menu items have icons, and "Remove from library" and "Move to trash" are in the warning colour.
- Confirmations name their action ("Move to trash", "Remove", "Update now") instead of a bare "OK", and the trash confirmation's button is red.
- Pages with nothing to show explain what to do, with a button where there's an obvious next step: Songs, Albums and Artists before any music is added ("Open Settings"), Liked Songs and empty playlists, smart playlists with no matches ("Edit rules"), the queue, Search, Folders and History.
- New screenshots throughout, and a looping tour of the app at the top of the README and the website.

### Added
- Deleting a playlist or smart playlist asks first.

### Fixed
- The menu item under the pointer was white on white in dark themes, so it couldn't be read. It's now tinted with the theme's accent and stays readable in every theme.
- With "Show track info" on, artist pages and Recap drew an empty dark pill after each song in their lists. They now show the song's format, or nothing when it isn't known.
- Dropdowns cut their text short ("All ye…"), and the queue panel's buttons ran into its title when the panel was narrow.

## [0.9.5] - 2026-10-12

### Added
- Hallucinate has its own Flatpak repository: install it from the website (or with `flatpak install --user https://phosphene-dev.github.io/Hallucinate/hallucinate.flatpakref`) and it updates with your other Flatpak apps, through your software centre or `flatpak update`. Updates download only what changed. Every release also has a single-file `.flatpak` bundle that sets up the same repository. Everything is signed with the project's key. Hallucinate won't be submitted to Flathub; the runtime still comes from there.

### Changed
- Settings no longer says updates come "through Flathub": in the Flatpak and in distribution packages, they come through your software centre or package manager.
- The Flathub submission helper (`scripts/flathub_manifest.py`) is gone.

## [0.9.4] - 2026-10-12

Big libraries: Hallucinate is now tested with a quarter of a million songs (and a 300,000-listen history), and stays smooth at that size.

### Improved
- Faster with large libraries. On a 250,000-song test library: ready 8.7 → 5.5 s after start-up, a rescan or tag edit applies in 6.7 s instead of 12.7, and memory use is a third lower (1.5 → 1.1 GB).
- No more stalls on big libraries: opening Albums (half a second → under 0.1), the timeline (a third of a second → under 0.1) and applying a rescan (two-thirds of a second → a quarter or less) no longer hold the window up. A rescan that changes nothing no longer redraws anything.
- The timeline shows two rows of each year with "Show all" for the rest, so a year with hundreds of albums doesn't make you scroll past it.
- Search's album and artist results, smart playlists, radio and Home's mix no longer slow down as a library grows.
- An album's page opens without scanning the whole listening history.

## [0.9.3] - 2026-10-12

A safety and stability release: nothing looks different, but more can go wrong without hurting you.

### Security
- Song titles, lyrics and online lookup results can no longer format the interface or make it go online. A tag containing an image link used to make the window fetch it (a tracking pixel that also slipped past offline mode). All text is now shown as plain text, and the interface refuses any request that isn't local.
- Answers from online services are capped in size, so a broken or hostile server can't fill memory.
- The update check keeps only the version number from a release and only opens this project's own release page.
- The control socket (`hallucinate --next` and friends) now lives in your private runtime folder, so another user on the same computer can't block Hallucinate from starting.
- Dependencies are checked against known vulnerabilities in CI (none today).

### Stability
- The library database (likes, plays, playlists, history) is backed up once a day, keeping five. If it's ever damaged (a crash mid-write, a failing disk), it's set aside and the newest backup restored automatically, with a message saying so; nothing is deleted.
- A memory leak is fixed: each library reload (after a rescan, a tag edit or a folder change) left the previous album and artist song lists in memory for the rest of the session. The cache of visited pages is also capped.
- The cover thumbnail (512 MB) and waveform (256 MB) caches are kept to a size limit, dropping the least recently used.
- A damaged iTunes/MusicBee library file now gives a clear "this file looks damaged" message when importing.
- Malformed audio files, CUE sheets, playlists, lyrics, library imports, themes and Hallucinate's own state files are now fuzz-tested.
- Long-running checks on a 12,000-song library (every page, search, theme changes, rescans, queue changes) show memory levelling off with no further growth.

## [0.9.2] - 2026-10-12

### Added
- Album menus: right-click an album (or its "…" button, or the "…" on its page) to play it, play it next, queue it, add it to a playlist, edit its info, go to the artist, remove it from the library or move it to the trash. Works on the album grid, the colour wall, the timeline, Home, Search, Stats and artist pages.
- Select several albums with Ctrl/Shift+click in the album grid, the colour wall or search; a bar then plays, queues, adds to a playlist, removes or trashes them all. Right-clicking a selected album acts on the whole selection.
- Remove from library: the files stay on disk and rescans leave them out; Settings → Library brings them back. Plays, likes and playlists are kept.
- Move to trash: the music files go to the system trash (recoverable there), and a folder left with only covers or logs goes too. Nothing is ever deleted outright, and library folders themselves are never trashed.

### Fixed
- "Find cover online" no longer stops at "Network error: HTTP Error 500" when the Cover Art Archive (archive.org) fails one image: it tries a smaller size, the next matching release and the album's release-group cover, retries MusicBrainz once if it's busy, and says plainly when the servers are having trouble.

## [0.9.1] - 2026-10-12

### Fixed
- Typing a search in a big library no longer freezes the window. Results came over one value at a time, and each value had to wait for any background work in Python (a rescan, cover thumbnails, the equalizer), so a page of results could stall for most of a second on every keystroke. They now come over as one list, and song rows look up likes, the playing song and the format setting once per page instead of once per row (every song list benefits).
- Searches typed slowly no longer queue up behind each other: a search that's already been overtaken by more typing is skipped, so the latest results arrive straight away.

## [0.9.0] - 2026-10-12

### Added
- Offline mode (Settings → Internet & sharing): Hallucinate makes no internet connections at all. Lyrics and cover lookups, Last.fm and ListenBrainz, headphone EQ downloads and update checks stay off, and Discord status shows no cover art. Scrobbles wait in their queues and are sent when it's turned off; nothing is remembered as "not found" because of it. Every request goes through one place in the code, and a test fails if new code connects any other way.
- Update now: with the update check on, the Windows installer build and the AppImage can install a new release themselves. The download is checked against the SHA-256 digest GitHub publishes for it, then the installer runs silently (Windows) or the AppImage is swapped in place, and Hallucinate reopens on the new version.

### Changed
- "Scrobbling & sharing" in Settings is now "Internet & sharing".
- Closing the window now asks whether to quit, minimize or keep playing in the tray, with "Remember my choice"; Settings → Desktop → "When I close the window" changes it later. Minimize isn't offered on tiling window managers that have none (Hyprland, Sway, i3 and others). Anyone who had "Keep playing in the tray" on keeps it.
- Copies installed by a system package manager (AUR and other distribution packages) no longer offer the update check; the package manager updates them.

## [0.8.2] - 2026-10-12

### Fixed
- The Recap card's glows no longer square off its rounded corners; they now follow the card's shape, in the app and in saved images.

## [0.8.1] - 2026-10-12

### Changed
- Hallucinate now lives at https://github.com/Phosphene-dev/Hallucinate and its website at https://phosphene-dev.github.io/Hallucinate/. Old links redirect for now. The update check, "Report a bug" and the lyrics lookup's user agent point to the new address.
- The app ID is now `io.github.phosphene_dev.Hallucinate` (Flatpak, macOS bundle and Windows taskbar), ready for Flathub.

## [0.8.0] - 2026-10-12

### Added
- Select several songs at once: Ctrl+click toggles a song and Shift+click selects a range in any song list (songs, albums, artists, playlists, smart playlists, folders, search, stats, recap). A bar above the player then plays them, plays them next, queues them, adds them to a playlist (or a new one), likes or unlikes them, rates them or edits their tags together; fields that differ between them are marked mixed and left alone. Esc or leaving the page clears the selection.
- Undo queue changes (Ctrl+Z, or Undo in the queue panel, 20 steps): clearing the queue, removing or moving a song, or replacing the queue by playing something else. The playing song carries on when it can.
- Skip tracking: moving on by hand from a playing song before it counts as a play records a skip. Smart playlists get a Skip count field, and radio plays songs you keep skipping less (unless they're liked).
- Import from other players (Settings → Library): play counts, skips, last played, ratings and playlists from Strawberry, Clementine, Rhythmbox, MusicBee and iTunes/Apple Music, and foobar2000 play counts written to tags. Libraries in their usual places are found for you; importing again never counts twice, and ratings set here are kept.
- Find every missing cover at once from Library health (MusicBrainz and the Cover Art Archive, paced to MusicBrainz's one request a second, with progress and Stop).
- Headphone crossfeed (Settings → Sound): Light, Medium or Strong, so hard-panned stereo is easier on headphones. Shown in the signal path.
- Lyrics timing: nudge synced lyrics 0.25 s earlier or later in the lyrics panel or Now Playing, and save the corrected timing as an .lrc file next to the song. LRC [offset:] tags are honoured.
- CUE sheets stored inside the audio file (a CUESHEET tag in FLAC, Ogg, WavPack or Monkey's Audio, or FLAC's native cuesheet block) split it into songs, and CUE songs now get their own waveform seek bar.
- Copy debug info (Settings → About): versions, system, display and scaling, audio output, playback settings and the recent log for bug reports, with the home folder redacted and no file paths or account names. A Report a bug link sits next to it.
- An optional update check, off by default: when turned on it asks GitHub for the latest release at most once a day and shows "Update to …" in the sidebar when a newer version is out. It's off inside the Flatpak, where Flathub delivers updates.
- `scripts/flathub_manifest.py` writes the Flathub submission manifest for a release tag.

### Changed
- Settings are grouped into Appearance, Playback, Sound, Library, Scrobbling & sharing, Desktop and About, with chips to jump to each and a search box that keeps only the sections matching what you type.
- Small and tiled windows: the player bar sizes its controls to fit (no more overlap with the seek bar in narrow windows; the mini player button hides below 1100 px, Ctrl+M still works), and the selection bar sits over the page with short labels when space is tight.
- Every page, the queue, Now Playing and the welcome are now tested in all 17 themes for warnings and unthemed white areas.

## [0.7.0] - 2026-10-12

### Added
- Pride themes: Pride, Trans Pride (dark and light), Bi Pride, Lesbian Pride, Nonbinary Pride, Pan Pride and Ace Pride. Each is a calm, readable theme built around its flag: the flag's colours drift through the backdrop (very bright stripes are softened, and black, white and grey stripes stay out of it), a slim flag stripe sits under the logo, and the accent comes from the flag. Every text and accent colour meets WCAG AA contrast. Themes can now carry a `palette` of their own colours.
- The welcome's theme picker scrolls and shows each flag on its tile.

## [0.6.1] - 2026-10-12

### Fixed
- The Stats page's top artists and top albums showed as white rows with unreadable text.
- The sidebar no longer piles its entries on top of each other in short windows (tiling window managers, fractional scaling): entries tighten up, and whatever still doesn't fit scrolls above Settings.
- An accent taken from a dark album cover (Settings → Appearance → album colours) could make the playing song's title nearly invisible; it is now lightened (or darkened on light themes) until it reads.

## [0.6.0] - 2026-10-11

### Added
- Artist pages: a round picture lit by its own colours, facts (albums, songs, hours, years active, genres), your listening (plays, time, rank among your artists, first listen, plays per month for the last year), most played songs, the discography grouped by year, albums they appear on, and every song on demand. Radio starts from their most played song.
- Recap (in the sidebar): a week, month or year of listening summed up, with listening time against the period before, plays, songs, artists and days, top artists, albums and songs, new artists, top genres, the busiest day, the longest streak, when you listen (time of day, day of the week, and month by month for a year) and albums added. Step back through earlier periods, and save the highlights card as an image in Pictures.
- ReplayGain analysis: songs whose files have no ReplayGain tags can be measured (EBU R128 / ITU-R BS.1770 loudness, ReplayGain 2.0's -18 LUFS reference), with album gain from each album measured as a whole. Start it from Settings → Playback or from the new "Songs without ReplayGain" check on the Library health page. Files are never changed: results are kept in the library, survive rescans while the file is unchanged, and tags always win. The signal path marks measured gain.
- Headphone correction: search AutoEQ's 8,800+ headphone profiles in Settings → Equalizer (or import a ParametricEQ / GraphicEQ file) and the equalizer corrects your headphones towards neutral, under your own band settings, with headroom so it can't clip. The signal path names the profile.
- Lyrics in Now Playing: the lyrics button (or L) shows synced lyrics karaoke-style beside the cover, the sung line large and the others fading; click a line to jump there. Unsynced lyrics scroll.
- Playlist files: import M3U, M3U8 and PLS playlists (Playlists → + → Import; songs are matched by path, then by artist and title, then by file name, so playlists from another computer still work) and export any playlist, smart playlist, Liked Songs or the queue as M3U8, with relative paths when the songs sit below the playlist's folder.
- Star ratings: rate songs one to five stars from the track menu, the player or Now Playing (Ctrl+1…5, Ctrl+0 clears; clicking the same rating again clears it). Ratings written by other players (POPM, RATING, FMPS_RATING) are picked up until you rate a song here, and smart playlists can use them ("Rating is at least 4", sort by rating).
- Folder view (in the sidebar): browse the library by its folders on disk, with breadcrumbs, subfolders showing their song count, length and a cover, and the songs in each folder. Play, shuffle or queue a folder and everything below it.
- CUE sheets: a single-file album with a .cue sheet (one big FLAC, APE, WavPack or WAV) appears as its separate songs, with titles, performers, album, year, genre and ReplayGain from the sheet. The songs play gaplessly as one piece, and likes, ratings, history and playlists work as for any other song. Sheets that name the WAV a rip was made from still find the encoded file. Tag editing is turned off for these songs (edit the .cue instead).
- A first-run welcome: a fresh install opens on choosing your music folders (with a live count of songs found), a theme (from live previews) and, optionally, ListenBrainz or Last.fm scrobbling, instead of an empty Home. It can be skipped, and everything can be changed later in Settings.
- `scripts/bench_library.py` times the heavy library queries against a synthetic 50,000-song library.

### Changed
- Faster with big libraries (measured on 50,000 songs and 200,000 listens): artist pages 660 → 13 ms, "On this day" 950 → 85 ms, the colour wall's first run 4.2 → 1 s, history totals 2 → 0.5 s. The play log keeps accent-folded copies of artist, title and album (added once on upgrade).

## [0.5.0] - 2026-10-11

### Changed
- A new look of its own, inspired by the logo: a slowly drifting, cover-tinted backdrop with fine film grain; frosted glass panels; a floating player; a navigation rail that collapses to icons (playlists move into a menu); and the Unbounded display typeface (SIL OFL, bundled) for headings. Album covers lift and glow on hover, and pages dissolve in. The background motion can be turned off in Settings → Appearance. Everything is drawn with gradients, so it also works without a GPU.

### Added
- A waveform seek bar: each track's loudness is drawn as bars in the player (the played part lit, the time under the pointer on hover, click or drag to seek). Tracks are analysed once in the background, the next one ahead of time, and cached on disk.
- Home is now about your own library instead of a feed: a random album to play (or roll again), a 26-week listening heatmap with your streak and this month's top artists, library facts (hours of music, size on disk, lossless share, formats), a "Rediscover" shelf of albums you haven't played in three months (or ever), "On this day" from past years, and recently added albums. Recently played and your mix move to the Stats page, next to its top tracks.
- Signal path: a pill in the player says whether the sound reaches the output untouched; click it for every stage from file to device (source format, ReplayGain, equalizer, speed, volume, crossfade, output device and its rate), with the ones that change the sound lit, including resampling when the device runs at another rate.
- Library health (Settings → Library, or the link on Home): a score and checks for missing library folders, songs missing artist or album tags, albums split in two by mixed album-artist tags, albums without a cover, track numbers, a year or a genre, probable duplicates and low-bitrate files, each with a fix next to it (find a cover, edit tags or the album, remove a folder).
- Command palette (Ctrl+K): jump to any page, run any command (playback, views, visualizer style, theme, new playlist, rescan…) or open an album, artist or song by typing a few letters.
- Album pages are now sleeves: the cover large and lit by its own colours, liner notes (genre, format and sample rate, discs, size, when it was added, your plays with first and last listen, liked songs) and tracks split by disc. Play starts the album in order.
- The Albums page has three views, remembered between visits: A–Z, a colour wall (covers edge to edge, ordered round the colour wheel, then greys; colours are measured once per cover and cached) and a timeline (decades, then each year with its albums).
- Now Playing: press F, or the new button in the player, for a full-window view with the visualizer as a living backdrop in the cover's colours, a large cover, the track, a waveform seek bar and the controls. It melts in, the controls and pointer fade away when the mouse rests, Esc closes it, and F11 makes it full screen. Vinyl mode slides the record out of its sleeve and spins it while the music plays.
- New visualizer styles drawn with GPU shaders and tinted by the current cover: Liquid (flowing ink), Aurora (curtains of light that rise with the spectrum) and Nebula (a turning cloud of gas and stars that breathes with the bass), plus the bars. The Visualizer page now fills the page. The shader styles need hardware graphics; with Qt's software renderer the bars are shown instead.
- A History page with every listen, newest first and grouped by day (with each day's plays and listening time). Search it, narrow it to today, 7 or 30 days, this month or this year, pick a day on the 12-month heatmap, filter by artist (click an artist's name) or by source (played here or imported from Last.fm/ListenBrainz), play a song again, or remove a listen that shouldn't count (its song's play count follows). Clicking a day on Home's heatmap opens it here. The queries behind it are built to drive weekly, monthly and yearly summaries later.
- Project website at https://phosphene-dev.github.io/Hallucinate/ (GitHub Pages), styled after the logo. It detects the visitor's OS for the download button, and is rebuilt automatically after every release and whenever the site, screenshots or changelog change.

## [0.4.0] - 2026-10-10

### Added
- Windows media controls (System Media Transport Controls): media keys, the volume/media overlay and the lock screen show the current track with artwork and timeline, and can play/pause, stop, skip, seek, and toggle shuffle and repeat. CI tests them against the real Windows API on a Windows runner; the Windows build bundles the WinRT bindings.
- Smart playlists: live rule-based playlists (title, artist, album, album artist, genre, format, path, year, length, bitrate, play count, date added, last played, liked; match all/any; sort; limit), listed under Playlists and re-evaluated as the library, likes and plays change. The rule editor previews the description and the number of matching songs. Rules are validated and compiled to parameterized SQL.
- Radio mode follows a smart playlist's rules when it continues one.
- Radio mode: when the queue is about to end, similar tracks from the local library are appended so playback continues gaplessly. Tracks are scored on listening-session co-plays with the recent tracks, shared and co-played artists, genre, year, likes and play counts, with recently played tracks held back and artists varied. Toggle it with the radio button in the now-playing bar.
- Output device picker in Settings → Playback. The choice persists; while the chosen device is unplugged, playback uses the system default and switches back when it returns. The equalizer follows the chosen device.
- Save the queue as a playlist from the queue panel.
- Drag audio files or folders onto the window to play them, or onto the queue panel to append them. Folders play in directory, disc and track order; files outside the library are read from their tags.

### Fixed
- On Python 3.10 and 3.11, PySide6 6.12.0 drops a reference to `True` on every signal emit, which eventually crashes the interpreter (CI caught it as a crash at exit). Those Pythons now stay on PySide6 6.11; Python 3.12+ is unaffected, as are the AppImage, Windows, macOS, Flatpak and AUR builds. A test guards against affected combinations.

## [0.3.3] - 2026-10-10

### Fixed
- Gapless playback no longer cuts off the end of each track: tracks play to their last sample and the next track starts just in time to join without a gap (within a few milliseconds in tests). The last track of a queue also plays to the end.

### Changed
- CI tests Python 3.10 through 3.14, checks that audio decodes inside the Flatpak, and requires the Flathub linter to pass.

## [0.3.2] - 2026-10-10

### Fixed
- The app could freeze permanently when changing track right after seeking (a deadlock between Qt's FFmpeg audio thread and Python); audio outputs are now created on the C++ side.
- In Flatpak, the window and MPRIS desktop entry now match the installed `.desktop` file, so desktops show the right icon.
- Intermittent CI segfaults and MPRIS test failures; tests now fail if they leave Qt objects in reference cycles.

### Changed
- Flatpak manifest is Flathub-ready: KDE 6.11 runtime with the PySide BaseApp, offline build with pinned Python dependencies, AppStream metainfo, and narrower sandbox permissions (no host config/data/cache access, so locally built Flatpaks start with fresh settings).
- AUR `hallucinate` PKGBUILD now packages 0.3.1 with a correct checksum; CI builds, lints and launches it in an Arch container.
- Minimum versions: PySide6 6.11.2, mutagen 1.48.1, keyring 25.7.0, setuptools 84 (build) and pytest 9.1.1 (tests); CI actions updated to checkout v7, setup-python v7 and upload-artifact v6.

## [0.3.1] - 2026-10-09

### Added
- Optional, theme-aware track format and approximate average-bitrate badges in song rows and now playing; configurable in Settings and off by default.
- Flatpak build and offscreen launch smoke test in CI, plus a stricter AppImage launch smoke test.

### Fixed
- Report detected codecs (including AAC vs ALAC and Vorbis vs Opus) separately from container extensions; legacy libraries are migrated and only ambiguous containers are rescanned.

## [0.3.0] - 2026-10-09

### Added
- Optional 24-band audio spectrum visualizer with worker-thread FFT processing, a dedicated UI page, and clean audio-tap shutdown.
- Flatpak manifest, native-architecture macOS release bundle workflow, and documentation of Qt/PipeWire output limitations.
- Drag-reorderable playback queue, play-next/add-to-queue, sleep timer and playback speed.
- ListenBrainz scrobbling and import of listening history from Last.fm/ListenBrainz.
- Discord Rich Presence with progress, artwork, privacy options and automatic reconnect.
- Listening statistics, a personal Home mix, genre/year/format filters and probable-duplicate detection.
- CLI playback controls, single-instance activation and optional desktop track-change notifications.
- Hallucinate branding, supplied logo and generated platform icons, Hallucinate color theme, `hallucinate` package/CLI, and first-run migration of the previous app's data, settings, cache and Last.fm credentials.
- Tests no longer touch the developer's real QSettings.

### Changed
- Require PySide6/Qt 6.8 or newer for audio-buffer processing.

## [0.2.0] - 2026-10-09

### Changed (performance)
- Library loading, search and model refreshes run on worker threads with their own SQLite connections; browse models update incrementally (row inserts/removes) instead of resetting.
- Play-all/album/artist actions are handled in Python, so large track lists never cross into QML; saved sessions keep a bounded queue window.
- Cover art is decoded and downscaled asynchronously by an `image://art` provider with an on-disk thumbnail cache.
- Artist lookups use an indexed folded-artist column (automatic migration).
- Theme switches cross-fade colors.
- 50k-track test: GUI-thread stalls during load/search stay far below 50 ms-class budgets in CI.

### Added
- Liked Songs and playlists; Recently played / Most played on Home.
- ReplayGain, crossfade and a 10-band FIR equalizer (numpy; audio is routed through a Qt audio tap while it is enabled).
- Tag editor (track/album), cover set/fetch (MusicBrainz + Cover Art Archive, optional embedding), and a synced lyrics panel (embedded, `.lrc`, LRCLIB).
- Mini player window and system tray icon (menu, tooltip, middle-click play/pause, close-to-tray option) in Settings → Desktop.
- Keyboard focus rings and accessible names/roles for buttons, rows and album cards; tooltips on icon buttons.
- `scripts/screenshots.py` renders README screenshots offscreen (also usable at `--scale 2` for HiDPI checks); screenshots and theme GIF in `docs/`.
- Scan progress bar, first-run "Choose music folder" flow, and loading/empty/error states (missing folders, unreadable files).

## [0.1.1] - 2026-10-09

### Added
- Windows build (PyInstaller onedir zip + Inno Setup installer) attached to releases; MPRIS skipped off Linux, Windows icon and config paths.
- AUR packaging (`hallucinate`, `hallucinate-git`) in `packaging/aur/`.
- AppImage build script and a release workflow that attaches it to tagged releases.
- Live-switchable file-backed themes (Dark, Light, Catppuccin Mocha/Latte, Nord,
  Gruvbox, Tokyo Night, Dracula), user themes, optional album-art accent.
- Last.fm scrobbling: keyring-backed auth, now-playing, offline retry queue.
- Format/playback/library hardening, MPRIS tests, manual QA checklist.
- CI (ruff + pytest), issue/PR templates, Dependabot.

## [0.1.0]

### Added
- Initial PySide6/QML music player: library scanning with SQLite FTS5 search,
  Spotify-style browse UI, queue, MPRIS2, Arch PKGBUILD.
