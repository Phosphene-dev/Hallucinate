__version__ = "1.7.1"

from . import audiobackend as _audiobackend  # noqa: E402

_audiobackend.choose()  # before anything loads Qt Multimedia (see audiobackend)
