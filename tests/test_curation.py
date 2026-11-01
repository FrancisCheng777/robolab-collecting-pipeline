"""Native H5 curation keeps camera inventory, time, labels and cut boundaries."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np
from fastapi.testclient import TestClient

from pi05_demo.episode import EpisodeWriter, inspect_episode
from pi05_demo.export_actions import aligned_records
from pi05_demo.curation.core import Config, Recording, empty_plan, fingerprint
from pi05_demo.curation.server import create_app
from pi05_demo.curation.export import export_dataset


def episode(root, outcome='success', views=('wrist',), mock=True, collector=None):
    writer = EpisodeWriter(root, mock=mock, task='insert plug', session='session-A',
        collector=collector,
        config={'control_hz': 15, 'teleop_controller': 'robolab_torque',
                'cameras': {'views': list(views)}})
    q = np.array([0., -.6, 0., -2.5, 0., 1.8, 0.])
    for i in range(16):
        stamp = 100. + i / 15
        writer.append(q=q+i*.001, target=q+i*.001, width=.04, command_width=.04,
            frames={v: (np.full((224,224,3), i, np.uint8), stamp) for v in views},
            timestamp=stamp, state_sequence=i+1, command_sequence=i+1, ack=True)
    return writer.finish(outcome)


class CurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = self.root/'raw'
        self.source = episode(self.raw)
        self.config = Config(input_dir=str(self.raw), output=str(self.root/'selected'))

    def test_native_wrist_timeline_and_frame(self):
        rec = Recording(self.source, self.config)
        self.assertEqual(rec.summary()['camera_views'], ['wrist'])
        np.testing.assert_allclose(rec.seconds, np.arange(16)/15)
        with TestClient(create_app(self.config, self.root/'clips.json')) as client:
            listing = client.get('/api/recordings').json()['recordings']
            self.assertEqual(len(listing), 1)
            self.assertTrue(listing[0]['valid'])
            frame = client.get(f'/api/recordings/{self.source.name}/frame?index=3')
            self.assertEqual(frame.status_code, 200)
            self.assertEqual(set(frame.json()['images']), {'wrist'})
            self.assertEqual(client.get(f'/api/recordings/{self.source.name}/frame?index=16').status_code, 400)

    def test_new_recording_appears_without_restarting_review_or_losing_plan(self):
        with TestClient(create_app(self.config, self.root/'clips.json')) as client:
            revision = client.get('/api/plan').json()['revision']
            plan = {'version': 1, 'recordings': {self.source.name: {'drop': True}}}
            saved = client.put('/api/plan', json={'plan': plan, 'base_revision': revision}).json()
            newer = episode(self.raw, collector={'name': 'zyp', 'counter_root': str(self.raw)})
            entries = client.get('/api/recordings').json()['recordings']
            self.assertEqual({x['name'] for x in entries}, {self.source.name, newer.name})
            self.assertEqual(client.get('/api/plan').json(), saved)
            self.assertEqual(client.get(f'/api/recordings/{newer.name}/frame').status_code, 200)

    def test_middle_cut_splits_native_episodes_without_changing_source(self):
        before = hashlib.sha256(self.source.read_bytes()).hexdigest()
        plan = {'version': 1, 'recordings': {self.source.name: {
            'exclude': [[5/15, 8/15]], 'fingerprint': fingerprint(self.source)}}}
        report = export_dataset(self.config, plan)
        self.assertEqual(report['total_episodes'], 2)
        self.assertEqual(report['total_frames'], 12)
        files = sorted((self.root/'selected').glob('*.h5'))
        self.assertEqual(len(files), 2)
        for path, indices in zip(files, (np.arange(5), np.arange(9,16))):
            info = inspect_episode(path, allow_mock=True)
            self.assertEqual(info['session'], 'session-A')
            self.assertTrue(info['mock'])
            self.assertEqual(info['camera_views'], ['wrist'])
            with h5py.File(path) as f, h5py.File(self.source) as source:
                np.testing.assert_array_equal(f['timestamp'][:], source['timestamp'][indices])
                np.testing.assert_array_equal(f['images/wrist'][:,0,0,0], indices)
                states, actions, *_ = aligned_records(f, 15)
                self.assertEqual(len(actions), len(indices)-1)
                np.testing.assert_allclose(actions[:,:7], .02, atol=1e-5)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), before)

    def test_saved_plan_conflict_stale_source_and_recursive_sessions(self):
        nested = episode(self.raw/'session-B')
        with TestClient(create_app(self.config, self.root/'clips.json')) as client:
            name = 'session-B/'+nested.name
            self.assertEqual(client.get(f'/api/recordings/{name}/timeline').status_code, 200)
            revision = client.get('/api/plan').json()['revision']
            plan = {'version': 1, 'recordings': {name: {'drop': True}}}
            payload = {'plan': plan, 'base_revision': revision}
            saved = client.put('/api/plan', json=payload)
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(client.put('/api/plan', json=payload).status_code, 409)
            with h5py.File(nested, 'r+') as f: f.attrs['changed'] = True
            self.assertEqual(client.get(f'/api/recordings/{name}/timeline').status_code, 400)

    def test_dropped_failure_and_too_short_fragments_never_become_success(self):
        failure = episode(self.raw, outcome='failure')
        plan = {'version': 1, 'recordings': {self.source.name: {'exclude': [[1/15, 1.]]}}}
        with self.assertRaisesRegex(ValueError, 'No exportable'):
            export_dataset(self.config, plan)
        self.assertFalse((self.root/'selected').exists())
        self.assertEqual(inspect_episode(failure, allow_mock=True)['outcome'], 'failure')

    def test_two_cameras_are_preserved_when_present(self):
        source = episode(self.raw, views=('main','wrist'))
        with TestClient(create_app(self.config, self.root/'clips.json')) as client:
            frame = client.get(f'/api/recordings/{source.name}/frame').json()
            self.assertEqual(set(frame['images']), {'main','wrist'})

    def test_stale_plan_cannot_publish_or_replace_existing_export(self):
        plan = {'version': 1, 'recordings': {self.source.name: {
            'exclude': [], 'fingerprint': fingerprint(self.source)}}}
        export_dataset(self.config, plan)
        original = (self.root/'selected').resolve()
        with h5py.File(self.source, 'r+') as f: f.attrs['changed'] = True
        with self.assertRaisesRegex(ValueError, 'source version'):
            export_dataset(self.config, plan)
        self.assertEqual((self.root/'selected').resolve(), original)

    def test_collector_title_and_ordinals_survive_curation(self):
        from pi05_demo.collector import Registry
        source = episode(self.raw, collector={'name': 'zyp', 'counter_root': str(self.raw)})
        with TestClient(create_app(self.config, self.root/'clips.json')) as client:
            data = client.get(f'/api/recordings/{source.name}/timeline').json()
            self.assertEqual(data['collector_index'], 1)
            self.assertEqual(data['collection_total_index'], 2)  # one legacy source
            self.assertTrue(data['display_title'].endswith('总第 2 条'))
        report = export_dataset(self.config, {'version': 1, 'recordings': {
            self.source.name: {'drop': True}, source.name: {'exclude': [[5/15, 8/15]]}}})
        self.assertEqual(report['total_episodes'], 2)
        for path in (self.root/'selected').glob('*.h5'):
            with h5py.File(path) as f:
                self.assertEqual(f.attrs['collector_name'], 'zyp')
                self.assertEqual(f.attrs['collection_total_index'], 2)
        self.assertEqual(Registry(self.raw, mock=True).preview('zyp')['saved_personal'], 1)


if __name__ == '__main__':
    unittest.main()
