"""Playing on other devices on your network: Chromecasts (and Google/Nest speakers, Android TVs) and DLNA/UPnP
renderers (smart TVs, AV receivers, network speakers).

Written with the standard library only, so every package (AppImage, Flatpak, Windows, macOS, deb/rpm, Nix) gets
it without compiled extras. Everything here reads what devices on the network send, so all of it is parsed
defensively: sizes are capped, names can't loop, XML with a DOCTYPE is refused, and a device can only point us
at addresses on its own machine.

Qt-free: the app's side (hallucinate/cast.py) runs these on worker threads and hands results to the window."""
