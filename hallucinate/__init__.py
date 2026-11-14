__version__ = "2.4.0"

from . import audiobackend as _audiobackend  # noqa: E402

_audiobackend.choose()  # before anything loads Qt Multimedia (see audiobackend)
