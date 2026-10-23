"""Browsing fixes in the whole window: Back to the search results, song rows from the keyboard, the mute key,
the welcome having the keys, taking songs out of a playlist with Undo, and genres in search and Ctrl+K."""

import test_screens
from PySide6.QtCore import Q_ARG, Q_RETURN_ARG, QMetaObject, QObject, QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from test_screens import find_item, plain

app_window = test_screens.app_window  # the fixture: the whole window over test_screens' seeded library


def invoker(qapp, window):
    def invoke(method, *args, target=None):
        QMetaObject.invokeMethod(target or window, method, Qt.ConnectionType.DirectConnection,
                                 *[Q_ARG("QVariant", a) for a in args])
        for _ in range(3):
            qapp.processEvents()
    return invoke


def current(window):
    return window.findChild(QObject, "pageStack").property("currentItem")


def focus_window(window):
    window.show()
    window.requestActivate()
    QTest.qWait(50)


def test_back_from_a_search_result_returns_to_the_results(qapp, app_window):
    from conftest import wait_for

    window, objects, warnings = app_window
    invoke = invoker(qapp, window)
    stack = window.findChild(QObject, "pageStack")
    search = find_item(window, "searchField")
    search.setProperty("text", "Aurora")
    assert wait_for(lambda: current(window).objectName() == "search")
    invoke("openAlbum", "k0")
    invoke("openAlbum", "k0")  # already there: no second copy of the page
    assert current(window).objectName() == "album" and stack.property("depth") == 3
    invoke("openArtist", "Aurora Vale")
    invoke("goBack")
    assert current(window).objectName() == "album"
    invoke("goBack")
    assert current(window).objectName() == "search"
    assert search.property("text") == "Aurora"  # the search is still typed in
    invoke("goBack")  # and Back from the results leaves the search
    assert wait_for(lambda: current(window).objectName() != "search")
    assert not [w for w in warnings if "main.qml" in w], warnings


def test_repeater_rows_move_with_the_arrows_and_space_plays_the_row(qapp, app_window):
    """On an artist's page the rows aren't a ListView: Up/Down still move between them (not the volume), and
    Space plays the focused song rather than pausing."""
    from conftest import wait_for

    window, objects, warnings = app_window
    player = objects["player"]
    invoke = invoker(qapp, window)
    focus_window(window)
    invoke("openArtist", "Aurora Vale")
    assert wait_for(lambda: find_item(window, "trackRow") is not None)
    first = find_item(window, "trackRow")
    QMetaObject.invokeMethod(first, "forceActiveFocus")
    start = first.property("rowIndex")
    volume = player.volume
    QTest.keyClick(window, Qt.Key.Key_Down)
    assert window.property("activeFocusItem").property("rowIndex") == start + 1
    assert player.volume == volume
    QTest.keyClick(window, Qt.Key.Key_Up)
    assert window.property("activeFocusItem").property("rowIndex") == start
    row = window.property("activeFocusItem")
    played = []
    row.activated.connect(lambda: played.append(True))
    QTest.keyClick(window, Qt.Key.Key_Space)
    assert played == [True]  # the row's own Space, not the window's play/pause
    # the row's hover buttons aren't Tab stops of their own, and show while the row has the focus
    assert row.property("showButtons")
    del first, row
    assert not warnings, warnings[:3]


def test_m_mutes_and_brings_the_volume_back(qapp, app_window):
    window, objects, warnings = app_window
    player = objects["player"]
    focus_window(window)
    window.contentItem().forceActiveFocus()
    player.setVolume(0.42)
    QTest.keyClick(window, Qt.Key.Key_M)
    assert player.volume == 0
    QTest.keyClick(window, Qt.Key.Key_M)
    assert abs(player.volume - 0.42) < 0.01
    assert not warnings, warnings[:3]


def test_the_welcome_has_the_keys_while_open(qapp, app_window):
    window, objects, warnings = app_window
    player = objects["player"]
    focus_window(window)
    welcome = window.findChild(QObject, "welcome")
    welcome.setProperty("open", True)
    for _ in range(5):
        qapp.processEvents()
    assert window.property("typing")  # the window's single-key shortcuts stand aside
    player.setVolume(0.5)
    QTest.keyClick(window, Qt.Key.Key_M)
    assert player.volume == 0.5
    skip = window.findChild(QObject, "welcomeSkip")
    assert skip.property("activeFocusOnTab")
    QMetaObject.invokeMethod(skip, "forceActiveFocus")
    QTest.keyClick(window, Qt.Key.Key_Return)  # Enter on "Skip setup" skips
    assert not welcome.property("open")
    for _ in range(3):
        qapp.processEvents()
    assert not window.property("typing")
    assert not warnings, warnings[:3]


def test_removing_from_a_playlist_can_be_undone(qapp, app_window):
    from conftest import wait_for

    window, objects, warnings = app_window
    user_lib, library = objects["userLib"], objects["library"]
    invoke = invoker(qapp, window)
    pid = user_lib.playlists.get(0)["id"]
    tracks = library.allTracks()
    user_lib.addPathsToPlaylist(pid, [tracks[4]["path"], tracks[5]["path"]])
    invoke("openPlaylist", pid, user_lib.playlists.get(0)["name"])
    model = user_lib.playlistTracks
    assert wait_for(lambda: model.count == 3)
    before = [model.get(i)["path"] for i in range(model.count)]
    menu = window.findChild(QObject, "trackMenu")
    invoke("removeFromPlaylist", [0, 2], target=menu)
    assert wait_for(lambda: model.count == 1)
    assert model.get(0)["path"] == before[1]
    toast = window.findChild(QObject, "toast")
    assert "2 songs removed" in toast.property("message")
    action = find_item(window, "toastAction")
    assert wait_for(lambda: toast.property("opacity") == 1)
    centre = action.mapToScene(QPointF(action.width() / 2, action.height() / 2))
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(int(centre.x()), int(centre.y())))
    assert wait_for(lambda: [model.get(i)["path"] for i in range(model.count)] == before)  # back in their places
    del action
    assert not warnings, warnings[:3]


def test_genres_in_search_and_in_the_palette(qapp, app_window):
    from conftest import wait_for

    window, objects, warnings = app_window
    search = find_item(window, "searchField")
    search.setProperty("text", "dream")
    assert wait_for(lambda: current(window).objectName() == "search")
    page = current(window)
    assert wait_for(lambda: [g["name"] for g in plain(page.property("genreHits"))] == ["Dream Pop"])
    search.setProperty("text", "")
    palette = window.findChild(QObject, "commandPalette")
    QMetaObject.invokeMethod(palette, "show")
    field = window.findChild(QObject, "paletteField")
    field.setProperty("text", "dream")
    QMetaObject.invokeMethod(palette, "rebuild")
    titles = [r["t"] for r in plain(palette.property("results"))]
    assert "Dream Pop" in titles
    commands = QMetaObject.invokeMethod(palette, "commands", Qt.ConnectionType.DirectConnection,
                                        Q_RETURN_ARG("QVariant"))
    names = [c["t"] for c in plain(commands)]
    assert {"Back", "Forward", "Find duplicates", "Evening"} <= set(names)
    if objects["player"].hasTrack:
        assert "Go to what's playing" in names
    QMetaObject.invokeMethod(palette, "close")
    assert not warnings, warnings[:3]


def test_genre_and_album_menus(qapp, app_window):
    from conftest import wait_for

    window, objects, warnings = app_window
    library = objects["library"]
    invoke = invoker(qapp, window)
    invoke("openGenre", "Dream Pop")
    page = current(window)
    menu = page.findChild(QObject, "genreMenu")
    invoke("showGenre", "Dream Pop", target=menu)
    assert wait_for(lambda: menu.property("opened"))
    assert menu.findChild(QObject, "collectionGoToGenre").property("visible")
    assert not menu.findChild(QObject, "collectionTrash").property("visible")  # not a whole genre from one click
    assert sorted(plain(QMetaObject.invokeMethod(menu, "paths", Qt.ConnectionType.DirectConnection,
                                                 Q_RETURN_ARG("QVariant")))) == sorted(t["path"] for t in library.allTracks())
    QMetaObject.invokeMethod(menu, "close")
    albums = window.findChild(QObject, "albumMenu")
    QMetaObject.invokeMethod(albums, "show", Qt.ConnectionType.DirectConnection, Q_ARG("QVariant", ["k0"]),
                             Q_ARG("QVariant", "Northern Lights"), Q_ARG("QVariant", "Aurora Vale"))
    assert wait_for(lambda: albums.property("opened"))
    assert albums.property("genre") == "Dream Pop"
    assert albums.findChild(QObject, "albumGoToGenre").property("visible")
    assert albums.findChild(QObject, "albumLikeAll").property("text") == "Like all songs"  # one of four is liked
    QMetaObject.invokeMethod(albums, "close")
    assert not warnings, warnings[:3]


def test_a_composers_page_and_the_composers_view(qapp, app_window):
    from conftest import wait_for

    window, objects, warnings = app_window
    library = objects["library"]
    invoke = invoker(qapp, window)
    paths = [t["path"] for t in library.allTracks()[:3]]
    db = library._db
    for n, p in enumerate(paths, 1):
        db.conn.execute("UPDATE tracks SET composer='Erik Satie', s_composer='erik satie', work='Gymnopédies', "
                        "movement=?, movement_no=? WHERE path=?", (f"Part {n}", n, p))
    db.commit()
    library.reload()
    assert wait_for(lambda: [c["name"] for c in library.composerList] == ["Erik Satie"])
    invoke("openComposer", "Erik Satie")
    page = current(window)
    assert page.objectName() == "composer"
    assert wait_for(lambda: find_item(window, "composerTitle").property("text") == "Erik Satie")
    assert "1 work" in find_item(window, "composerFacts").property("text")
    assert find_item(window, "composerWorks").property("visible")
    invoke("go", "artists")
    artists = current(window)
    QMetaObject.invokeMethod(artists, "setView", Qt.ConnectionType.DirectConnection, Q_ARG("QVariant", True))
    qapp.processEvents()
    assert artists.property("composers")
    QMetaObject.invokeMethod(artists, "setView", Qt.ConnectionType.DirectConnection, Q_ARG("QVariant", False))
    assert not warnings, warnings[:3]


def test_a_playlist_in_a_folder_shows_in_the_sidebar(qapp, app_window):
    from conftest import wait_for

    window, objects, warnings = app_window
    user_lib = objects["userLib"]
    pid = user_lib.playlists.get(0)["id"]
    user_lib.setPlaylistFolder(pid, False, "Moods")
    assert wait_for(lambda: user_lib.playlists.get(0)["folder"] == "Moods")
    assert wait_for(lambda: find_item(window, "playlistFolder_Moods") is not None)
    user_lib.renamePlaylistFolder("Moods", "")
    assert wait_for(lambda: find_item(window, "playlistFolder_Moods") is None)
    assert not warnings, warnings[:3]
