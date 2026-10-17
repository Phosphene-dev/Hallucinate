import threading
import time

from conftest import wait_for


def test_soon_answers_at_once_when_quick():
    from hallucinate import fileready

    assert fileready.soon(lambda: 42, lambda _v: None, 1.0) == (True, 42)
    assert fileready.soon(lambda: 1 / 0, lambda _v: None, 1.0) == (True, False)


def test_soon_hands_a_late_answer_on():
    from hallucinate import fileready

    gate, late = threading.Event(), []
    started = time.monotonic()
    assert fileready.soon(lambda: gate.wait(5) and "yes", late.append, 0.05) == (False, None)
    assert time.monotonic() - started < 1
    gate.set()
    assert wait_for(lambda: late == ["yes"])
