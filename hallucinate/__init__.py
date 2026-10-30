__version__ = "1.6.3"

from . import audiobackend as _audiobackend  # noqa: E402

_audiobackend.choose()  # before anything loads Qt Multimedia (see audiobackend)
