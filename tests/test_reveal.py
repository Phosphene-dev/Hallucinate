"""Show in folder: the portal in the Flatpak (it opened nothing there, issue 95), the file manager outside."""
from hallucinate import reveal


class Reply:
    def __init__(self, kind):
        self.header = type("H", (), {"message_type": type("T", (), {"name": kind})()})()


class Bus:
    def __init__(self, answers):
        self.sent, self.answers, self.closed = [], list(answers), False

    def send_and_get_reply(self, msg, timeout=0):
        self.sent.append(msg)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return Reply(answer)

    def close(self):
        self.closed = True


def test_in_the_flatpak_the_portal_opens_the_song_s_folder(tmp_path):
    song = tmp_path / "a.flac"
    song.write_bytes(b"x")
    bus = Bus(["method_return"])
    assert reveal.show(str(song), flatpak=True, connect=lambda: bus)
    msg = bus.sent[0]
    member = [v for k, v in msg.header.fields.items() if getattr(k, "name", "") == "member"][0]
    dest = [v for k, v in msg.header.fields.items() if getattr(k, "name", "") == "destination"][0]
    assert member == "OpenDirectory" and dest == "org.freedesktop.portal.Desktop"
    assert bus.closed


def test_when_the_portal_refuses_the_file_its_folder_is_opened(tmp_path):
    """Issue 95 again: an image saved in Pictures/Hallucinate wasn't shown; the folder alone is the fallback."""
    image = tmp_path / "recap.png"
    image.write_bytes(b"x")
    bus = Bus(["error", "method_return"])
    assert reveal.show(str(image), flatpak=True, connect=lambda: bus)
    members = [[v for k, v in m.header.fields.items() if getattr(k, "name", "") == "member"][0] for m in bus.sent]
    assert members == ["OpenDirectory", "OpenFile"]


def test_a_folder_in_the_flatpak_is_opened_as_a_file(tmp_path):
    bus = Bus(["method_return"])
    assert reveal.show(str(tmp_path), flatpak=True, connect=lambda: bus)
    member = [v for k, v in bus.sent[0].header.fields.items() if getattr(k, "name", "") == "member"][0]
    assert member == "OpenFile"


def test_outside_the_file_manager_selects_it_and_failure_falls_back(tmp_path):
    song = tmp_path / "a b.flac"
    song.write_bytes(b"x")
    bus = Bus(["method_return"])
    assert reveal.show(str(song), flatpak=False, connect=lambda: bus)
    msg = bus.sent[0]
    member = [v for k, v in msg.header.fields.items() if getattr(k, "name", "") == "member"][0]
    assert member == "ShowItems" and msg.body[0] == [song.as_uri()]
    assert not reveal.show(str(song), flatpak=False, connect=lambda: Bus(["error"]))  # no file manager
    assert not reveal.show(str(song), flatpak=False, connect=lambda: Bus([OSError("gone")]))

    def no_bus():
        raise OSError("no session bus")
    assert not reveal.show(str(song), flatpak=False, connect=no_bus)
