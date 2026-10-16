"""What a queue entry is: a song from the library, an internet radio station or a podcast episode."""


def is_url(path):
    """Whether a queue entry's path is a web stream (an internet radio station, a streamed podcast episode)."""
    return isinstance(path, str) and path.startswith(("http://", "https://"))


def track_kind(track):
    """"music" for songs from the library; "station" (internet radio) and "episode" (a podcast) never count
    toward plays, stats or history."""
    return track.get("kind") or "music"


def counts_for_scrobbling(track):
    """Songs always do; a radio station only with its "scrobble" flag (Settings) and a song title from the
    stream; podcast episodes never."""
    kind = track_kind(track)
    if kind == "music":
        return True
    return kind == "station" and bool(track.get("scrobble") and track.get("artist") and track.get("stream_title"))
