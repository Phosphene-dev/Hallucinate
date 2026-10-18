"""A keyring that doesn't answer (locked, its unlock prompt never showing) doesn't hang the app."""
import threading
import time

from hallucinate import keyringwait


def test_a_quick_keyring_answers_at_once():
    got = keyringwait.read(lambda k: {"token": "t"}.get(k), ("token", "user"))
    assert got == {"values": {"token": "t", "user": ""}, "error": ""}


def test_a_keyring_that_doesnt_answer_is_waited_for_in_the_background():
    gate, late = threading.Event(), []
    began = time.monotonic()
    got = keyringwait.read(lambda k: gate.wait() and "secret", ("token",), late=late.append, timeout=0.3)
    assert got is None and time.monotonic() - began < 1.5  # the caller carries on
    gate.set()  # the keyring unlocks
    for _ in range(50):
        if late:
            break
        time.sleep(0.05)
    assert late == [{"values": {"token": "secret"}, "error": ""}]


def test_a_broken_keyring_says_why():
    def broken(_k):
        raise RuntimeError("no backend")

    assert keyringwait.read(broken, ("token",)) == {"values": {}, "error": "no backend"}


def test_call_reports_success_errors_and_no_answer():
    import threading

    from hallucinate import keyringwait

    assert keyringwait.call(lambda: None) == ""
    assert "locked" in keyringwait.call(lambda: (_ for _ in ()).throw(RuntimeError("locked")))
    gate = threading.Event()
    assert keyringwait.call(lambda: gate.wait(5), timeout=0.05) == keyringwait.NO_ANSWER
    gate.set()


def test_once_the_keyring_is_stuck_later_reads_dont_wait_for_it_too():
    import threading
    import time

    from hallucinate import keyringwait

    release = threading.Event()
    assert keyringwait.read(lambda k: release.wait(5) and "x", ("a",), timeout=0.2) is None
    started = time.monotonic()
    assert keyringwait.read(lambda k: release.wait(5) and "y", ("b",), timeout=3) is None
    assert time.monotonic() - started < 0.5  # not another three seconds
    release.set()
    deadline = time.monotonic() + 5
    while keyringwait._unanswered[0] and time.monotonic() < deadline:
        time.sleep(0.01)
    assert keyringwait._unanswered[0] == 0
    assert keyringwait.read(lambda k: "z", ("c",))["values"] == {"c": "z"}
