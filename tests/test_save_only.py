"""Interactive collection publishes only explicitly accepted success episodes."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pi05_demo.episode import EpisodeWriter
from pi05_demo.async_episode import AsyncEpisodeWriter
import test_episode
import test_resdq


class SaveOnlyTests(unittest.TestCase):
    def test_discard_and_failure_leave_neither_h5_nor_partial(self):
        for outcome in ('aborted', 'failure'):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as root:
                writer = EpisodeWriter(root, mock=True, task='test', session='s', config={}, save_success_only=True)
                writer.append(**test_episode.EpisodeTests().sample())
                self.assertIsNone(writer.finish(outcome))
                self.assertEqual(list(Path(root).glob('*.h5*')), [])

    def test_async_discard_completes_and_removes_pending_file(self):
        with tempfile.TemporaryDirectory() as root:
            writer = AsyncEpisodeWriter(root, mock=True, task='test', session='s', config={}, save_success_only=True)
            writer.append(**test_episode.EpisodeTests().sample())
            self.assertIsNone(writer.finish('aborted'))
            self.assertTrue(writer.finished)
            self.assertEqual(list(Path(root).glob('*.h5*')), [])

    def test_q_before_s_keeps_no_recording(self):
        with tempfile.TemporaryDirectory() as root, patch('time.monotonic', return_value=100.):
            session, _ = test_resdq.RecordingKeysTests().make(root)
            session.tick(['r']); session.tick(); session.tick(['q'])
            self.assertEqual(list(Path(root).glob('*.h5*')), [])

    def test_interrupted_write_cleanup_keeps_no_partial(self):
        with tempfile.TemporaryDirectory() as root:
            writer = EpisodeWriter(root, mock=True, task='test', session='s', config={}, save_success_only=True)
            writer.append(**test_episode.EpisodeTests().sample())
            writer.close_incomplete()
            self.assertEqual(list(Path(root).glob('*.h5*')), [])

    def test_background_write_failure_cleans_up_its_hdf5_file(self):
        class BrokenAppend(EpisodeWriter):
            def append(self, **kwargs):
                raise OSError('simulated disk failure')
        with tempfile.TemporaryDirectory() as root:
            writer = AsyncEpisodeWriter(root, mock=True, task='test', session='s', config={},
                save_success_only=True, writer_factory=BrokenAppend)
            writer.append(**test_episode.EpisodeTests().sample())
            self.assertTrue(writer._done.wait(2))
            with self.assertRaisesRegex(RuntimeError, 'simulated disk failure'): writer.check()
            self.assertEqual(list(Path(root).glob('*.h5*')), [])

    def test_s_already_accepted_is_preserved_when_exiting_during_drain(self):
        with tempfile.TemporaryDirectory() as root:
            session, _ = test_resdq.RecordingKeysTests().make(root)
            writer = AsyncEpisodeWriter(root, mock=True, task='test', session='s', config={}, save_success_only=True)
            writer.append(**test_episode.EpisodeTests().sample())
            session.writer = writer
            session._finish('success')
            session.close('operator exit during accepted save')
            self.assertEqual(len(list(Path(root).glob('*.h5'))), 1)
            self.assertEqual(list(Path(root).glob('*.inprogress')), [])
