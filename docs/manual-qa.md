# Manual QA checklist

## Release testing for 1.0

The checks people do by hand before 1.0: things that need real hardware, real accounts, real services or a
real desktop, which the automated suite can't reach. Tick what passes; for anything that doesn't, report:

- what you did, what you expected and what happened (a screenshot or a short clip helps)
- Settings → About → **Copy debug info** (version, OS, Qt, audio backend and device; no personal paths)
- if it crashed: the report the next start offers, copied in full
- for sound problems: the file's format (the badge or the signal path readout) and the output device

Run from a terminal (`hallucinate` or the AppImage) so any warnings it prints can be pasted too.

Already confirmed on Hyprland with 0.9.9.2: finding, adding and playing internet radio stations, and
finding, following and playing podcasts.

### 1. Everyday use (a week on your real library)
- [ ] Start-up time from launch to a usable window, first start and later starts (rough seconds is fine).
- [ ] Scan your whole library: how long, and do the counts on Home look right? Any songs missing or doubled?
- [ ] Leave it playing for hours: no stutters, no growing memory (check `htop` or a system monitor now and
  then and note the number), no rising CPU while paused or hidden.
- [ ] Gapless albums (a live album or a DJ mix, in FLAC and in MP3): no clicks, gaps or doubled audio at the
  joins.
- [ ] Crossfade on, then off: transitions sound right both ways.
- [ ] ReplayGain on (track, then album): loud and quiet albums come out about even.
- [ ] Settings → Playback → **Measure new music by itself after each scan**: add an album without ReplayGain tags, rescan,
  and check it gets measured (the signal path shows a gain) without slowing the app down.
- [ ] Anything that looks wrong at your window sizes, including tiled half and quarter screen: clipped text,
  overlapping buttons, things spilling out of cards.

### 2. Hyprland and the desktop
- [ ] Media keys and `playerctl play-pause / next / previous / position 30`, with the window focused and not.
- [ ] Desktop notifications on track change (Settings → Desktop) and for new podcast episodes.
- [ ] The tray icon (if your bar has a tray): click, middle-click, menu; "keep playing in the tray".
- [ ] The mini player (`Ctrl+M`): floats on top, with LIVE for a station and skip buttons for an episode.
- [ ] Mouse back and forward buttons step through pages; pages come back scrolled where you left them.
- [ ] Drag files and folders in from your file manager.
- [ ] Discord Rich Presence, if you use it: songs, stations and episodes all show sensibly.
- [ ] HiDPI or fractional scaling, if you use it: sharp covers and text, nothing clipped.

### 3. Sound hardware
- [ ] Switch output device during playback (speakers, headphones, a USB DAC or Bluetooth): audio moves
  without a restart. Unplug the chosen one: it falls back to the default; plug it back: it returns.
- [ ] Equalizer → **Separate settings for each output**: set a different curve on two devices,
  switch between them (and unplug/replug), and check each keeps its own.
- [ ] Headphone correction (search your model) and crossfeed: audible, and the signal path says so.
- [ ] Bluetooth headphones: play/pause buttons on the headset work.

### 4. Online accounts and services
- [ ] Last.fm: connect, scrobble a few songs, check they appear on your profile once each.
- [ ] Settings → Scrobbling & sharing → **Liking a song loves it on Last.fm**: like a song, check it's loved on Last.fm;
  unlike it, check the love goes. Then **Like the songs I've loved on Last.fm**: the toast's count looks right and those songs
  appear in Liked Songs.
- [ ] ListenBrainz: connect with a token and check listens arrive.
- [ ] Edit album → **Look up on MusicBrainz** on a few albums (one well-known, one obscure, one multi-disc,
  one with odd characters in its name): the right release is near the top, and saving fills in title, album
  artist, year, genre and (if ticked) track titles correctly. Check the files with another tagger if you can.
- [ ] Fetch a missing cover, and **Fetch all missing covers** from Library health.
- [ ] Lyrics: synced lyrics for a few well-known songs; nudge the timing and save.
- [ ] Turn on offline mode, then use the app normally for a while: nothing online should happen (no covers,
  no lyrics, no feeds), and scrobbles should go once it's off again.
- [ ] A feed or station link that's wrong or down: the message says why in plain words.

### 5. Podcasts beyond the basics
- [ ] Up next: line up episodes from two shows, reorder by "Put first", play through; each one leaves Up
  next when played.
- [ ] Show settings: oldest first, hide played, a speed of its own (change the speed while it plays and
  check the show keeps it), skip intro and outro.
- [ ] Settings → Podcasts: skip lengths (the buttons follow), what plays after an episode, how close to the
  end counts as played, and each "keep downloads" choice (until played, newest few, until removed).
- [ ] Downloads: download an episode, go offline, play it. Remove all downloads, check the space shown.
- [ ] Leave the app running past a refresh interval: new episodes appear, and a notification comes.
- [ ] OPML: export your shows, import them into another podcast app (and back).
- [ ] Internet radio: leave a station on for an hour (song titles keep updating; a dropped connection comes
  back by itself).

### 6. Your data
- [ ] Settings → Library → **Back up…**, then on another account, computer or a fresh config:
  **Restore…**. Likes, ratings, playlists, play counts, history, stations and podcasts with their progress all
  come back. Restore the same backup twice: nothing doubles.
- [ ] Import from another player you've used (Strawberry, Clementine, Rhythmbox, MusicBee, iTunes,
  foobar2000).
- [ ] Update from an older version (keep your config): the **What's new** card shows once and nothing is lost.
- [ ] AppImage: Settings → About → check for updates, then "Update now" when the next release is out.

### 7. Feature switches and settings
- [ ] Settings → Features: switch each one off and look for anything of it left anywhere (sidebar, Ctrl+K,
  search results, menus, Home, Settings, shortcuts, notifications). Switch it back: everything returns.
- [ ] Read through every Settings section as a new user would: anything confusing, badly worded, in the wrong
  section or hard to find with the settings search?

### 8. Looks
- [ ] Every theme (including Ribbon and the pride themes): text, hover, selection and disabled controls stay
  readable. Your own accent colour on a light and a dark theme.
- [ ] **Follow the system's light or dark mode**: flip it in your desktop settings (or `gsettings set
  org.gnome.desktop.interface color-scheme prefer-dark`) and the app follows.
- [ ] **Make my own theme…**: edit some colours, save, restart: it's still there and selectable.
- [ ] Every visualizer in Now Playing (F) and on the Visualizer page, especially Halo and Waves: smooth, in the
  cover's colours, nothing stuck after a song change.
- [ ] **Reduce motion**: nothing slides, zooms, spins or drifts.

### 9. Accessibility
- [ ] With Orca on: move through the sidebar, a song list, a podcast's episodes, Settings and a dialog; every
  control says what it is and does.
- [ ] The whole app from the keyboard alone: Tab through every page, arrows in lists, Enter to play, Menu key
  (or Shift+F10) for menus, Esc closes dialogs.

### 8a. New in 1.4, on every desktop
Run these on each desktop you have: KDE Plasma (Wayland and X11), GNOME (Wayland, with and without the
AppIndicator extension), Cinnamon, XFCE, MATE, COSMIC, and the tiling compositors (Hyprland, niri, Sway with
Waybar's tray). Note which desktop and session (`echo $XDG_CURRENT_DESKTOP $XDG_SESSION_TYPE`) with any failure.
- [ ] Tray icon, from the Flatpak too: it appears with the window open, stays while it's open, and turns up
  even if the bar's tray starts after Hallucinate. Click brings the window back; the menu's Go to opens each
  page; Play/Pause, Previous and Next work. GNOME without the AppIndicator extension: no icon, and closing to
  the background says how to get the window back.
- [ ] Title bar default on a fresh config: built in on GNOME Wayland, Hyprland, niri and Sway; the desktop's
  own frame on KDE, COSMIC and X11 desktops. Buttons on the left (Settings → Desktop) put close first.
- [ ] Mouse wheel: one notch moves the same distance on every page (Settings is the long one); quick notches
  add up; a high-resolution wheel (Logitech G502 X and similar) moves as far as a normal one; Scroll speed
  changes it. A touchpad still scrolls smoothly.
- [ ] Notifications: none while Hallucinate's window is in front, one per song while you're in another window
  (and every time with "Even while … in front").
- [ ] Crossfade on: an album plays gaplessly; shuffle across albums crossfades. Fade on pause and play; play
  pressed during the fade-out comes straight back.
- [ ] Volume step and maximum volume (Settings → Playback) apply to the wheel on every volume control and to
  the Up/Down keys.
- [ ] Open on: Home, a page, or "the page I left it on"; Start playing when Hallucinate opens.
- [ ] Library: switching off the start-up scan and the folder watcher; Rescan still finds new songs.
- [ ] Visualizer in the background: full, slower, paused (watch CPU in a system monitor).

### 9a. New in 1.3 (the first tester's report)
- [ ] Settings → Desktop → "Show desktop notifications when tracks change": the next song shows a notification
  with its album and cover (mako, dunst, swaync and GNOME/KDE alike); skipping through songs updates one
  notification instead of stacking them.
- [ ] "When I close the window: Ask every time": closing asks. "Keep playing in the background" hides the window
  and the music goes on; opening Hallucinate again (launcher, `hallucinate`) brings it back. On Hyprland
  without a tray in the bar, a notification says so the first time.
- [ ] New playlist (and Rename, Save queue as playlist): the name field fits inside the dialog.
- [ ] Lyrics in the side panel and in Now Playing keep clear of the edges; long lines wrap.
- [ ] The Visualizer page and an album, artist and podcast page: rounded corners, no square edge to the glow.
- [ ] A 24-bit FLAC shows Hi-Res; an iTunes/Qobuz download marked explicit shows E (song lists, the player bar,
  Now Playing, the web remote, `hallucinate cmd status`). Settings → Appearance switches each off, and can show
  every song's bit depth.
- [ ] Volume: scroll over the icon (5% a notch), middle-click mutes; Now Playing's volume icon opens a slider
  above it; in a narrow window the bar's icon does too. The mini player's icon scrolls and mutes.
- [ ] Linux: the window has the built-in title bar (no Qt frame on Hyprland). Drag the top row or the sidebar's
  name to move it (floating), double-click to maximize, resize by the edges, Minimize/Maximize/Close work and
  Close asks as above. Settings → Desktop: hide Minimize; switch back to the system title bar (no restart).
- [ ] The mini player follows the title bar setting (no Qt frame; drag it by its background).
- [ ] Retro themes: the window buttons, badges and volume slider fit Hi-Fi Deck and Beige Box.
- [ ] A server or LXC with PipeWire libraries but no PipeWire running: `hallucinate --headless` starts (it uses
  PulseAudio then; Copy debug info says which sound system it chose).

### 9b. New in 1.0
- [ ] Tag a few songs with a composer, work and movement (tag editor → More fields): Artists → Composers lists
  them; the composer's page shows the work with its movements in order. Play a work; Play all.
- [ ] Album page: Composer links. Song menu: Go to composer. Search and Ctrl+K: a composer's name.
- [ ] A FLAC with BPM and INITIALKEY: Songs → Sort by tempo shows "128 BPM · Am". A smart playlist "Tempo is
  more than 120" finds it; one "Key is Am" too.
- [ ] Search "radiohed" (or any name with a letter wrong): "Showing results for radiohead".
- [ ] Right-click a playlist → Move to folder → New folder…; the sidebar shows the folder, which opens and
  closes and is remembered. Rename the folder, then Ungroup it.
- [ ] With a music server: right-click an album → Keep on this computer; Settings → Music servers counts it.
  Switch offline mode on: the album still plays. Remove the copies.
- [ ] With Last.fm set up, switch on similar artists: an artist page lists them; Play a mix plays songs by them.
- [ ] Upgrading from 0.9.9.9: the library reads its files again once, and everything carries on working.

### 10. New in 1.0 (earlier in the cycle)
- [ ] Search a genre name (say "shoegaze"): songs with that genre are listed, songs named for it first.
- [ ] Songs → Most played and Recently added; Artists → the drop-down's four orders, kept after a restart.
- [ ] A genre page → ⋯ → Rename genre…: type a new name; the page shows it once the songs are retagged. Rename
  one to a genre you already have: the note says they join, and afterwards there's one page.
- [ ] A playlist → ⋯ → Make a copy; add a song twice → Remove repeats; the header shows its length.
- [ ] Queue → Shuffle (shuffle mode off): the songs to come are mixed, the playing one stays; Undo.
- [ ] Sleep timer → End of this album: playback pauses when the next song is from another album.
- [ ] Songs → filter by a genre → Shuffle: only the shown songs play. Search → Play all.

### 10b. New in 0.9.9.9
- [ ] Settings: subsections start closed; open one, leave Settings and come back, it's still open. Search
  "preamp" or "discogs": the subsection holding it opens. Text size changes the whole app.
- [ ] Online & privacy → Offline mode while a radio station plays: it stops; a podcast download pauses and
  carries on when offline mode is switched off.
- [ ] Mute with the volume icon and with M; the volume comes back as it was.
- [ ] Queue: Delete on a song removes it (Undo brings it back); "Clear upcoming"; the header shows time left.
- [ ] Shuffle on, then Play next on a song: it plays next.
- [ ] Move an album's folder within your music folder and rescan: its likes, plays and ratings are kept.
- [ ] Song rows: click the artist or album; the artist and genre pages' ⋯ menus; Ctrl+K "genre name".
- [ ] Keyboard only: Tab to a song row (it highlights), Space plays it; arrows move on an artist page.

### 11. New in 0.9.9.8
- [ ] An album with several genres: click each genre under Genres; its page lists the albums, artists and songs
  carrying it, and "Goes with" lists genres found alongside. Play all and Shuffle play every song of it.
- [ ] The same from an artist page, from Now Playing (the view closes) and from a song's right-click menu.
- [ ] Albums → Genres: a tile per genre; Most songs and A–Z reorder them.
- [ ] Songs → Sort by genre: grouped by main genre, songs without one last; the order is kept after a restart.

### 12. New in 0.9.9.7
- [ ] Library health → Albums without a genre → **Find all online**: each album suggests up to three genres;
  click the genres found to add or remove them. Save: the album page shows them all, the first as the main one.
- [ ] Songs → filter by one of an album's later genres: its songs are listed. A smart playlist "Genre is" that
  genre finds them too.
- [ ] Settings → Library: switch off "Show every genre on album and artist pages": only the main genre shows.
  Switch on "Show every genre of the playing song": Now Playing lists them all.
- [ ] Settings → Online & privacy → paste a Discogs token → **Connect Discogs**: "Connected as <you>". Find a
  genre in the tag editor: the note says which sources it came from.
- [ ] A fresh start (move the config folder aside): the welcome's third step lists features and going-online
  choices; internet radio, podcasts, music servers and bio lookups start off; what you tick is on afterwards.
- [ ] Settings → Online & privacy → switch on "Look up an artist's bio". Open an artist: About shows a bio
  (from Wikipedia) with its source; click the source to open it. Pick
  another source for them; **Write your own**, Save; it stays after a restart. **Remove mine** brings the
  fetched one back. With "Look up an artist's bio" off, or offline mode on, nothing is looked up.
- [ ] On an ultrawide screen (or a maximised window wider than about 2200 pixels): Home, an artist, an album,
  Stats and Settings stay centred at a readable width.

### 13. New in 0.9.9.6
- [ ] Library health → Albums without a genre → **Find all online**, then save them all: "Saving genres to your
  files: n of m albums" counts up, the number of albums without a genre goes down as it goes, and the library
  doesn't keep rescanning. **Stop** part-way keeps the ones done.
- [ ] Edit a song's tags (a genre, a rating): it saves at once, and the song still plays.

### 14. New in 0.9.9.5
- [ ] Settings → **Measure songs without ReplayGain** (search "ReplayGain") on your whole library: the window keeps
  responding throughout, and it finishes (a few songs may count as failed). `htop` shows a second Hallucinate
  process while it measures, gone a minute after.
- [ ] Play a few songs: the waveform appears in the seek bar for each.
- [ ] Visualizer: every style draws, including Aurora, Halo and Waves, and also with a black or grey cover.
- [ ] Shrink the window to half the screen, and open the queue: the sidebar folds to icons, nothing in
  Settings runs off the right edge, and the player bar's title, badges, controls and time don't overlap.
- [ ] Settings → Appearance → the Shrimp Boat accent (peach).

### 15. New in 0.9.9.4
- [ ] **Leave it open overnight** with a radio station restored from last time, not playing: still responding
  in the morning. Then press play: the station connects and plays what's on now.
- [ ] Pause a station for a few minutes, then play: it reconnects without fuss.
- [ ] Music servers (Settings → Features → Music servers, then Settings → Music servers): add your Navidrome or
  Jellyfin server; its songs appear in Songs, Albums, Artists and search, and play, seek and skip like files.
  Stop the server: its songs are passed over, and come back within a few minutes of it returning. Remove it:
  its songs leave the library.
- [ ] Rate a song, then look in another player (or a tagger): the rating is in the file. Clear it, rescan:
  it stays cleared.
- [ ] Add a cover to an album: cover.jpg appears in its folder (and in the files, if "Also embed" is on).
- [ ] With your music on a USB or network drive that's gone to sleep: play a song from it, and switch songs
  while it wakes. The window keeps responding ("Opening…" shows while it waits).
- [ ] Lock your keyring (or log in without it unlocked) and start the app: it opens, and Last.fm says it's
  waiting for the keyring.

### 16. New in 0.9.9.3
- [ ] Sidebar: drag entries into a new order, right-click → Move up/down, Alt+Up/Down on a focused entry, and the
  list in Settings → Features (with Reset). The order survives a restart, and switching a page off and on keeps
  its place.
- [ ] Library health → Albums without a genre → **Find all online** on your real library (it takes a couple of
  seconds an album; **Stop** works part-way). In the review: are the genres right? Are the artist-based ones
  (unticked) sensible? Change one, pick an alternative for another, untick a few, Save, and check the files'
  tags in another tagger.
- [ ] **Find genre** on a single Library health row, and **Find online** next to Genre in Edit album and Edit
  tags (one song).
- [ ] Internet radio → **Heard on the radio**: after an hour on a station the songs are listed with the right
  times; search, Find in your library, Copy, Remove and Clear work.
- [ ] **Your listening** on the radio and Podcasts pages: the hours look about right for this week, month and
  all time.
- [ ] Last.fm/ListenBrainz with radio scrobbling on: songs heard on the radio scrobble with no album (not the
  station's name). With **Count podcast episodes** on, an episode scrobbles as the show and its title.
- [ ] CPU with the window focused and music playing, on your real GPU (`htop`): note the number; turn off
  **Animated background** in Settings → Appearance and note it again.

### 14. macOS (Apple Silicon)
The macOS app isn't signed, so the first start needs **right-click → Open** (or `xattr -dr
com.apple.quarantine /Applications/Hallucinate.app`). Then:
- [ ] It opens, scans `~/Music` or a chosen folder, and plays FLAC, MP3, AAC/ALAC, Opus and WAV.
- [ ] Seek, pause, next; gapless and crossfade sound right.
- [ ] Output device switching (built-in speakers, headphones, AirPods or a DAC).
- [ ] Covers, Now Playing (F) and the visualizers draw (they use Metal there), and themes look right.
- [ ] Menu-bar/tray icon, the mini player, drag and drop from Finder, Cmd-key shortcuts where expected.
- [ ] Last.fm sign-in through the browser, and that it's remembered (the macOS keychain).
- [ ] Known gap: the keyboard's media keys and Control Centre's Now Playing aren't connected on macOS yet.
  Say whether that matters to them.
- [ ] Note the macOS version and Mac model in the report.

## Detailed checks

Use representative files from a library you are permitted to test. Record the
OS, Qt/PySide6 version, FFmpeg backend version, audio device, sample filename,
and result for each run. For codec checks, verify both imported metadata and
actual audible playback in this app; successful scanning alone is not proof a
codec decodes.

## Formats, tags, and playback

- [ ] FLAC: tagged file, cover art, play, pause, seek forward/backward, next.
- [ ] MP3: ID3v2 tags/art, VBR file, playback and seeking.
- [ ] OGG/Vorbis: tags/art, playback and seeking.
- [ ] Opus: tags/art, playback and seeking.
- [ ] M4A/AAC: tags/art, playback and seeking.
- [ ] M4A/ALAC: lossless playback and seeking.
- [ ] WAV: RIFF INFO tags, ID3-tagged WAV, untagged filename fallback, seeking.
- [ ] APE: real APE audio file, APEv2 tags, playback and seeking. Automated tests
  currently exercise APE metadata using a synthetic header only, not a decoder.
- [ ] WMA: tags, playback and seeking.
- [ ] WavPack and AIFF: playback, seeking, and tag fallback.
- [ ] Missing tags, Unicode tags/paths, multi-disc/track numbers, and embedded art.
- [ ] Zero-byte, truncated, malformed-tag, and random-byte files: scans complete,
  invalid files are counted/ignored, and valid neighboring files remain usable.
- [ ] Seek to start, middle, and near end; pause/resume after each seek.
- [ ] Change volume repeatedly; verify it persists after restart.
- [ ] Play a queue through multiple transitions, including short tracks; listen for
  cut-off or silence at transitions. Play a gapless album (a live album or DJ mix, in
  FLAC and in MP3) and listen for clicks, gaps or doubled audio at each join. Each track
  should play to its end; the next starts ~20 ms early (`HANDOFF_LEAD_MS`) to cover
  its startup on the audio device.
- [ ] Verify repeat off stops, repeat all wraps, repeat one repeats, and shuffle
  visits every queued item before starting a new cycle.
- [ ] Add next, enqueue, reorder, remove current/other items, clear queue, then
  play again. Remove a file during playback and verify the UI reports/skips it.
- [ ] Settings → Playback → Output device: switch between two devices (e.g. speakers and a
  USB DAC or headset) during playback, with the equalizer off and on; audio moves without
  a restart. Unplug the chosen device: playback continues on the default and the picker
  shows it as "not connected"; plug it back in and audio returns to it. Restart and
  verify the choice is kept.
- [ ] Radio: turn on the radio button, play a single song, and verify about ten similar
  songs are appended before it ends and that playback continues without a gap. Let it
  run through a few batches; check that artists vary and that recently heard songs are
  not repeated. Turn repeat on and verify nothing more is added.
- [ ] Smart playlists: create "Liked is yes" + "Last played not in the last 60 days";
  like and play songs and verify the list updates without reopening it. Edit the
  rules (field, operator, between, limit, sort) and check the preview count. Play
  it with radio on and verify added songs still match the rules. Delete it.
- [ ] Drag a folder from the file manager onto the window: it plays in album order.
  Drag files onto the queue panel: they are appended. Drop a file outside the library.
- [ ] Queue panel → Save: the new playlist opens with the queue's tracks in order.
- [ ] Restart the app with a non-empty queue; verify queue, current track, position,
  shuffle, and repeat restore paused. Delete a queued file before restart and
  verify it is dropped without losing the remaining queue.

## Library and search

- [ ] Add one folder, scan it, then rescan unchanged: no duplicate tracks or
  unnecessary metadata updates.
- [ ] Modify a tag and file size/mtime; verify metadata/search updates.
- [ ] Rename and move a track within the watched root; verify old path is removed
  and new path appears.
- [ ] Delete a track and a whole subfolder; verify stale search and browse results
  disappear. Disconnect/move the entire root and verify the library is retained
  until the root is available or explicitly removed.
- [ ] Add/remove a folder in Settings; verify its contents and counts update.
- [ ] Search mixed case, diacritics, non-Latin text, punctuation, slash-containing
  artist names, and multi-token artist/album/title queries.
- [ ] Run against a 50,000+ track library; search, browse, open an album, and
  compare first display latency to the automated query thresholds in
  `tests/test_library_robust.py`.
- [ ] Run `python scripts/scale_check.py` (250,000 songs); nothing should be marked slow.
- [ ] Restart with the large library; verify startup does not reparse unchanged files.

## Linux desktop integration

- [ ] In a graphical Arch-based desktop session, verify `org.mpris.MediaPlayer2`
  appears on D-Bus with correct metadata, playback state, position, repeat, shuffle,
  and volume.
- [ ] Test desktop media-key Play/Pause, Next, Previous, and Stop while the player
  is focused and unfocused; confirm competing players do not consume the keys.
- [ ] Test MPRIS calls from a desktop widget or `playerctl`, including seeking and
  changing repeat/shuffle.
- [ ] Confirm the desktop entry launches the installed app and the icon resolves.
- [ ] Test the installed Arch package on a clean machine/container and verify the
  Qt FFmpeg plugin and codecs are present.

## Last.fm integration

- [ ] Enter API credentials in Settings, restart, and verify they remain available
  without appearing in application config files or logs.
- [ ] Connect through the browser authorization flow; verify the username and
  connected state appear, then disconnect and reconnect.
- [ ] Start, pause, resume, seek, and switch tracks; verify now-playing updates
  only for the active track and seeking/paused time does not count toward a
  scrobble.
- [ ] Verify a short track scrobbles after half its duration and a long track
  after four minutes of actual listening; verify each track is submitted once.
- [ ] Disconnect networking during playback; verify a threshold-qualified
  scrobble persists across restart and is retried after network access returns.
- [ ] Disconnect the Last.fm account with queued scrobbles; verify the queue is
  retained and delivered after reconnecting.
- [ ] Test with an unavailable system keyring; verify the UI reports the failure
  and credentials/session keys are never written as plaintext.

## Themes

- [ ] Switch through all built-in themes; verify text, disabled controls, hover,
  selection, error, and accent contrast remain readable in both light and dark
  palettes.
- [ ] Change theme while browsing and while playback is active; verify the
  player, queue, dialogs, sliders, and Settings update immediately.
- [ ] Enable album-art accent mode, switch between albums with different covers,
  then play a track without artwork; verify the accent follows the cover and
  falls back to the selected theme when no art is available.
- [ ] Add a valid custom theme JSON under the displayed user theme directory,
  select **Reload themes**, and verify its colors, radius, family, and font scale
  apply live and persist after restart.
- [ ] Add malformed or incomplete theme JSON, reload, and verify the app logs
  the skipped file while the other themes remain selectable.

## Packages

- [ ] Flatpak: play MP3, AAC/M4A, FLAC and Opus files (codecs come from the runtime); add a folder outside
  `~/Music` through the folder picker; connect Last.fm or ListenBrainz with the desktop keyring; check that
  media keys, notifications and Discord Rich Presence (native and Flatpak Discord) work; the window and
  MPRIS controls show the Hallucinate icon.
- [ ] AUR: install `hallucinate` and `hallucinate-git` on a clean Arch system with `makepkg -si`; launch from
  the application menu and check playback.

## Automated coverage

The automated suite covers real FFmpeg-generated FLAC, MP3, Vorbis, Opus, AAC,
ALAC, WAV, WMA, WavPack, and AIFF playback/seek files, common tag/fallback/corrupt
inputs, player queue/session behavior, a D-Bus MPRIS session, and 50,000-row
database query performance, plus mocked Last.fm signing, authorization, listen
thresholds, and offline queue/retry behavior. Theme tests cover built-in/custom
theme loading, persistence, album-art accent selection, and live QML color/font
updates. It does not replace testing actual device media keys, live Last.fm
authorization, all user-supplied codec variants, or real APE decoding on the
target system.

## Desktop integration (0.2.0)
- [ ] Tray icon appears (KDE/GNOME with AppIndicator extension/Windows); left-click toggles the window, middle-click toggles playback, menu actions work.
- [ ] Settings → Desktop: disabling the tray makes closing the window quit; "keep playing in the tray" hides the window instead.
- [ ] `Ctrl+M` opens the mini player (main window hides); Esc / expand button restores it; closing the mini window restores the main window.
- [ ] Tab moves keyboard focus through sidebar, transport buttons, rows and album cards with a visible ring; Enter/Space activates.
- [ ] Windows media controls: play a track with cover art and check the media overlay
  (volume keys or Win+A) and lock screen show title, artist, album and artwork. Use the
  keyboard media keys and the overlay's play/pause, next, previous, seek bar, shuffle
  and repeat; Hallucinate follows each, and the overlay updates when changed in the app.
- [ ] Orca (Linux) / Narrator (Windows) announce button names (Play, Next, Queue, Lyrics…).
- [ ] HiDPI: at 150%/200% scaling covers and text are sharp and nothing clips (also `QT_SCALE_FACTOR=2`).
