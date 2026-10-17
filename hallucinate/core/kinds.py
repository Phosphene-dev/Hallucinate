"""What a queue entry is: a song from the library, an internet radio station or a podcast episode."""


def is_url(path):
    """Whether a queue entry's path is a web stream (an internet radio station, a streamed podcast episode)."""
    return isinstance(path, str) and path.startswith(("http://", "https://"))


def track_kind(track):
    """"music" for songs from the library; "station" (internet radio) and "episode" (a podcast) never count
    toward plays, stats or history."""
    return track.get("kind") or "music"


def counts_for_scrobbling(track):
    """Songs always do. A radio station only with its "scrobble" flag (Settings) and a song title from the
    stream; a podcast episode only with its own flag (off unless you turn it on)."""
    kind = track_kind(track)
    if kind == "music":
        return True
    if kind == "episode":
        return bool(track.get("scrobble") and track.get("artist") and track.get("title"))
    return kind == "station" and bool(track.get("scrobble") and track.get("artist") and track.get("stream_title"))


def scrobble_fields(track):
    """What a scrobble says about a queue entry: a song heard on the radio never has the station's name as its
    album (the entry's album, for showing), only the album of your own copy of the song if you have one; an
    episode is the show (as artist and album) and its title."""
    out = dict(track)
    if track_kind(track) == "station":
        out["album"] = track.get("song_album") or ""  # your copy's album when the song is in your library
    return out
