"""Private atomic operator artifacts and a reentrant, process-exclusive sync lock."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile
import threading

_owned = threading.local()


class SyncAlreadyRunning(RuntimeError):
    pass


@contextmanager
def source_write_lock(directory):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    key = str(directory)
    held = getattr(_owned, 'held', set())
    if key in held:
        yield
        return
    descriptor = os.open(directory / '.public-sync.lock',
                         os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SyncAlreadyRunning('Another source sync or backup is running; checkpoint preserved') from None
        _owned.held = held | {key}
        try:
            yield
        finally:
            _owned.held = held
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


@contextmanager
def atomic_text_file(path):
    """An interrupted writer leaves the previous complete UTF-8 file intact."""
    path = Path(path)
    descriptor, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path, value, *, compact=False):
    with atomic_text_file(path) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=None if compact else 2,
                  separators=(',', ':') if compact else None)
