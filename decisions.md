# Decisions

The calls I made myself about what Hallucinate is and what goes into it. It lists only ideas that started with
me. Features I picked from a list of suggestions (gapless playback, smart playlists, radio, the album timeline,
star ratings and many others) are good additions, but they weren't my idea, so they aren't here.

This record starts at version 0.3.2. Versions in brackets are where each decision shipped.

## What Hallucinate is

- **The name stays Hallucinate.** When I moved the project to the Phosphene-dev organisation and dropped my old
  account name, the project kept its name. [0.8.1]
- **Spotify was a reference, never the template.** The early design pointed at Spotify for familiarity, not as
  something to clone. Once the app worked well, I decided it should stop looking like a streaming-app derivative
  and get an identity of its own, while staying very usable, polished and modern. That led to the redesign. [0.5.0]
- **It stays an audio player.** When choosing new features, nothing goes beyond what a music player should do.
- **No gimmicky voice.** I turned down giving features cute names ("Drift" for radio and the like) and writing
  the interface in that voice. Labels stay plain.
- **Stability and safety come first.** These are the things to keep in mind on every change, ahead of new
  features.

## Features

- **A full listening history, and summaries built on it.** I wanted a complete play log people can look back
  through, next to the heatmaps, and eventually weekly, monthly and yearly summaries along the lines of a yearly
  "Wrapped". This became the History page [0.5.0] and Recap [0.6.0].
- **Pride themes.** Trans Pride and other flag themes, kept calm and readable rather than loud rainbow colours.
  [0.7.0]
- **Updating from inside the app.** Hallucinate can notice a new version and install it itself, so nobody has to
  go and download it by hand. [0.9.0]
- **An internet kill switch.** One setting that stops Hallucinate making any outside connection, for people who
  want that. It's a quiet option in Settings, not a headline feature. This became offline mode. [0.9.0]
- **Choosing what closing the window does.** Quit, minimise, or keep playing in the tray. [0.9.0]
- **Acting on albums directly.** Right-click an album, or select several, to remove them from the library and do
  the other album actions without opening each one. [0.9.2]
- **Hardening and leak hunting.** Before going further, the app is made safe wherever it talks to the internet
  and checked for memory leaks, without changing how it feels to use. [0.9.3]
- **Libraries bigger than mine.** Hallucinate has to keep up with collections much larger than my own, not just
  with mine. [0.9.4]
- **Options, and every desktop.** Where people could reasonably want different things, Hallucinate gives them the
  choice in Settings rather than picking one for everybody, and it has to work properly on all the main Linux
  desktops (GNOME, KDE Plasma, Xfce, Cinnamon, tiling window managers and the rest), not just mine.
- **Choosing when a song counts.** When Last.fm's scrobbling broke, the app still said "Scrobbling now". I wanted
  to choose when a song is scrobbled or counts as a listen, and to be able to switch the "Scrobbling now" notice
  off. [1.4.1]
- **Select anything, from anywhere.** I wanted to select several of anything at once (songs from an artist or
  album to add to a playlist, and every other sensible kind of item) with the usual methods: clicking with
  Ctrl and Shift, dragging the mouse, and the rest. When asked, I chose that a selection gathers across pages,
  that a drag paints a selection or carries one depending on where it starts, and that every kind of item can be
  selected (artists, genres and composers; sidebar playlists; queue entries; history, folders, podcasts and
  radio). [1.6.0]
- **Tiling window managers are first-class.** A tiling window manager (Hyprland) is my main desktop, so the app
  has to work properly there, not only on floating desktops. [0.6.1, 0.9.0]

## Bugs I found that shaped releases

From testing the app on my own library, on Linux (Hyprland) and Windows:

- The Stats page's top artists and top albums showed as white rows with unreadable text. [0.6.1]
- The sidebar's entries piled on top of each other in a tiled window. [0.6.1]
- The Recap card's glows squared off its rounded corners. I made this its own release. [0.8.2]
- Typing a search froze the window in a big library. [0.9.1]
- "Find cover online" stopped at an HTTP 500 error. [0.9.2]

## The project around the app

- **Releases without me tagging by hand.** Releases are started from a workflow that tags and publishes in one
  step, so they don't wait on me. [0.3.3]
- **A free website that keeps itself up to date.** No paid hosting and no domain. It's styled after the logo's
  purple look and rebuilt automatically after each release. [0.5.0]
- **A better GitHub page.** I decided the repository page needed work, so first-time visitors find downloads
  quickly. [repository page, after 0.4.0]
- **A new home for the project.** The repository moved to the Phosphene-dev organisation, and I changed my
  account name. [0.8.1]
- **Testers, ethically and for free.** Hallucinate goes in front of people to try without spending money or
  promoting it dishonestly. [0.9.0]
- **No paid macOS signing.** I won't pay Apple's $99 a year to sign for a platform I don't use. Windows signing
  is worth doing, but it waits for now (SignPath).
- **Lighter point releases.** Building every package for every release was wasting resources. Point releases
  build only the AppImage, the Flatpak and the Windows installer; macOS and the .deb/.rpm come with the major
  releases. [1.6.1]
- **Packages for other distributions.** Besides the AppImage and Flatpak, Hallucinate ships a .deb, an .rpm and a
  Nix flake, so people on Debian, Ubuntu, Fedora, openSUSE and NixOS can install it the way they're used to.
  [1.5.1]
- **The AUR package waits.** It goes up once AUR account sign-ups reopen.
- **No Flathub; our own Flatpak repository instead.** I don't want to deal with Flathub's submission process,
  and I prefer AppImages anyway. Hallucinate ships its Flatpak from its own signed repository on the website,
  which updates like any other Flatpak, and the AppImage stays the main Linux download.

## My ideas that changed shape or were set aside

- **projectM visualizer.** I asked about going all out on the visualizer with projectM (MilkDrop presets). I chose
  Hallucinate's own shader visualizers instead, tinted by the album cover, which was the alternative suggested to
  me. They fit the app's look better and need no extra library.
- **No libre.fm.** A tester asked for libre.fm scrobbling. I looked at libre.fm's AI policy and decided against
  supporting it.
- **No Soulseek.** I'm keeping Soulseek integration out of Hallucinate.
