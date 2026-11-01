"""Preserve episode data and schema checks while caching HDF5 handles."""
import tempfile
import unittest

import h5py
import numpy as np

from pi05_demo.episode import EpisodeWriter, inspect_episode
import test_timing


class EpisodeStorageTests(unittest.TestCase):
    def sample(self, index):
        sample = test_timing.TimingTests().sample()
        offset = index / 15
        sample['timestamp'] += offset
        sample['timing'] = {k: v + offset for k, v in sample['timing'].items()}
        for name, (rgb, stamp) in sample['frames'].items():
            sample['frames'][name] = (np.full_like(rgb, index), stamp + offset)
            meta = sample['camera_metadata'][name]
            for key in ('receive_monotonic_s', 'ready_monotonic_s', 'source_time_s'):
                meta[key] += offset
            meta['frame_id'] += index
        sample['command_sequence'] += index
        return sample

    def test_multiframe_data_and_metadata_survive_reopening(self):
        with tempfile.TemporaryDirectory() as root:
            writer = EpisodeWriter(root, mock=True, task='insert', session='test', config={})
            for i in range(20):
                writer.append(**self.sample(i))
            path = writer.finish('success')
            self.assertEqual(inspect_episode(path, allow_mock=True)['frames'], 20)
            with h5py.File(path) as f:
                for i in range(20):
                    sample = self.sample(i)
                    for name in ('main', 'wrist'):
                        np.testing.assert_array_equal(f['images/' + name][i], sample['frames'][name][0])
                        self.assertEqual(f['camera_frame_id/' + name][i], 42 + i)
                    self.assertEqual(f['timestamp'][i], sample['timestamp'])
                    for key, value in sample['timing'].items():
                        self.assertEqual(f['timing/' + key][i], value)

    def test_schema_and_clock_changes_still_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            writer = EpisodeWriter(root, mock=True, task='insert', session='test', config={})
            try:
                writer.append(**self.sample(0))
                changed = self.sample(1)
                changed.pop('timing')
                with self.assertRaisesRegex(ValueError, 'timing schema'):
                    writer.append(**changed)
                changed = self.sample(1)
                changed['camera_metadata']['wrist']['source_clock'] = 'different_clock'
                with self.assertRaisesRegex(ValueError, 'clock domain'):
                    writer.append(**changed)
                self.assertEqual(writer.count, 1)
                writer.append(**self.sample(1))
                path = writer.finish('success')
                self.assertEqual(inspect_episode(path, allow_mock=True)['frames'], 2)
            finally:
                writer.close_incomplete()
