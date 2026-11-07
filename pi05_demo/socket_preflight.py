"""Remove abandoned Unix sockets while the caller holds the collection flock."""
import os
from pathlib import Path
import socket
import stat


def clear_stale_socket(path):
    path = Path(path)
    try:
        original = path.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISSOCK(original.st_mode) or original.st_uid != os.getuid():
        raise RuntimeError(f'Refusing to remove non-socket or foreign-owned path: {path}')
    # Includes sockets bound but not yet listening. Do not connect to a live
    # bridge: accepting a diagnostic connection could interfere with its client.
    try:
        registry = Path('/proc/net/unix').read_text()
    except OSError as exc:
        raise RuntimeError('Cannot verify socket ownership without readable /proc/net/unix; refusing cleanup') from exc
    for line in registry.splitlines()[1:]:
        fields = line.split(maxsplit=7)
        if len(fields) == 8 and fields[7] == str(path):
            raise RuntimeError(f'Socket is still owned by a live process: {path}')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        try:
            probe.connect(str(path))
        except ConnectionRefusedError:
            pass
        else:
            raise RuntimeError(f'Socket is active: {path}')
    current = path.lstat()
    if (current.st_dev, current.st_ino, current.st_ctime_ns) != (
        original.st_dev, original.st_ino, original.st_ctime_ns
    ):
        raise RuntimeError(f'Socket changed during preflight: {path}')
    path.unlink()
    return True
