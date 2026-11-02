pragma Singleton
import QtQuick

QtObject {
    signal openAlbum(string key)
    signal openArtist(string name)
    signal openGenre(string name)
    signal openComposer(string name)
    signal openPodcast(int id)
    signal goToPlaying()  // the playing song's album, the station's page or the episode's show
    signal openSettings()
    signal openSettingsAt(string section)  // Settings, scrolled to one section (its id: "casting")
    signal openLiked()
    signal goHome()
    signal openHistory(string day)
    signal toggleNowPlaying()
    signal openHealth()
    signal openPalette()
    signal newSmartPlaylist()
    signal importPlaylist()
    signal exportPlaylist(string kind, string name)
    signal notify(string message)
    signal search(string text)  // search the library, as if typed in the search field
    signal notifyAction(string message, string actionText, var action)  // a toast with a button (Undo)
    signal openPlaylist(int id)
    signal openSmartPlaylist(int id, string name)
    signal editSmartPlaylist(int id, string name)
    signal trackMenu(string path, string title, string context, int index)
    signal newPlaylistWith(var paths)
    signal openSpectrum(string path)  // the spectrum analyzer window, for a song  // the new-playlist dialog, starting the playlist with these songs
    signal editTags(string path)
    signal editTagsMany(var paths)
    signal editAlbum(string key)
    signal findAlbumGenre(string key)  // open the album editor and look its genre up
    signal back()
    signal routeGone(string kind, int id)  // a playlist or show was deleted: Back and Forward skip it
    signal installUpdate()
    // keys: album keys; what: how to name them in messages ("“Album”" or "3 albums")
    signal albumMenu(var keys, string title, string artist)
    signal removeAlbums(var keys, string what)
    signal trashAlbums(var keys, string what)
    // songs by path (paths: one song, or a selection); `what` names them in the confirmation
    signal artistMenu(string name)
    signal selectionMenu()  // the song menu, for every song of what's selected
    // Every "Add to playlist" ends here: songs the playlist already holds are left out (issue 100), with an
    // "Add anyway" in the toast; `what` names what's added ("3 songs", "“Title”")
    signal addToPlaylist(int pid, string name, var paths, string what)
    signal removeFromPlaylistId(int pid, string name, var paths, string what)  // out of a playlist from a menu (issue 101)
    signal deleteInList(string context, string path, int index)  // Delete on a song row: out of a playlist, or unliked
    signal folderMenu(string path, string name)
    signal removeSongs(var paths, string what)
    signal removeFolder(string path)  // take a music folder out of the library, after asking
    signal trashSongs(var paths, string what)
}
