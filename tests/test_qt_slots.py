"""Every slot a page can call is there by the name it's called by. A Slot made from a function takes that function's
name, so setters made in a loop (all called set_) were registered under one name and the page couldn't reach any
of them: Discover's and Sounds like this's settings snapped back when chosen."""
import importlib
import inspect
import pkgutil

from PySide6.QtCore import QObject

import hallucinate


def test_every_slot_is_reachable_by_its_name(qapp):
    bad = []
    for info in pkgutil.walk_packages(hallucinate.__path__, "hallucinate."):
        try:
            module = importlib.import_module(info.name)
        except Exception:  # noqa: BLE001 - (a module for another system: Windows, macOS)
            continue
        for name, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ != module.__name__ or not issubclass(cls, QObject):
                continue
            meta, seen = cls.staticMetaObject, set()
            for i in range(meta.methodOffset(), meta.methodCount()):
                method = meta.method(i)
                signature = bytes(method.methodSignature()).decode()
                if signature in seen or not hasattr(cls, bytes(method.name()).decode()):
                    bad.append(f"{info.name}.{name}: {signature}")
                seen.add(signature)
    assert not bad, bad
