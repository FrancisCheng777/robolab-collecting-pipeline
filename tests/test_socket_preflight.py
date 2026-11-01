import socket
import tempfile
import unittest
from pathlib import Path
from pi05_demo.socket_preflight import clear_stale_socket


class SocketPreflightTests(unittest.TestCase):
    def test_missing_and_stale(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bridge.sock'
            self.assertFalse(clear_stale_socket(path))
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(str(path))
            self.assertTrue(clear_stale_socket(path))
            self.assertFalse(path.exists())

    def test_bound_and_listening_are_preserved(self):
        for listening in (False, True):
            with self.subTest(listening=listening), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'bridge.sock'
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                    server.bind(str(path))
                    if listening:
                        server.listen(1)
                    with self.assertRaisesRegex(RuntimeError, 'live process'):
                        clear_stale_socket(path)
                    self.assertTrue(path.exists())

    def test_regular_file_and_symlink_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'target'
            target.write_text('keep')
            link = Path(folder) / 'link'
            link.symlink_to(target)
            for path in (target, link):
                with self.assertRaises(RuntimeError):
                    clear_stale_socket(path)
                self.assertTrue(path.exists())
            self.assertEqual(target.read_text(), 'keep')
