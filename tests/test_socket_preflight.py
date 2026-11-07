import socket
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from pi05_demo.socket_preflight import clear_stale_socket


class SocketPreflightTests(unittest.TestCase):
    def test_missing_and_stale(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bridge.sock'
            self.assertFalse(clear_stale_socket(path))
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(str(path))
            with patch('pi05_demo.socket_preflight.Path.read_text', return_value='Num RefCount Protocol Flags Type St Inode Path\n'):
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
                    registry = f'header\n0: 2 0 0 1 1 123 {path}\n'
                    with patch('pi05_demo.socket_preflight.Path.read_text', return_value=registry), self.assertRaisesRegex(RuntimeError, 'live process'):
                        clear_stale_socket(path)
                    self.assertTrue(path.exists())

    def test_unavailable_registry_never_authorizes_socket_removal(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bridge.sock'
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(str(path))
            with patch('pi05_demo.socket_preflight.Path.read_text', side_effect=FileNotFoundError), self.assertRaisesRegex(RuntimeError, 'refusing cleanup'):
                clear_stale_socket(path)
            self.assertTrue(path.exists())

    @unittest.skipUnless(Path('/proc/net/unix').exists(), 'Linux kernel socket registry required')
    def test_actual_kernel_registry_preserves_bound_socket(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bridge.sock'
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(str(path))
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
