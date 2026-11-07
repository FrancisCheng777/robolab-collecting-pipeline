import tempfile
from pathlib import Path
import unittest
import h5py
from pi05_demo.replay_menu import list_episodes,select
from pi05_demo.replay import ReplayStartGate,source_digest

class ReplayMenuTests(unittest.TestCase):
    def test_ignores_incomplete_failure_and_mock_files(self):
        with tempfile.TemporaryDirectory() as directory:
            for name,complete,outcome,mock in [('good',True,'success',False),
                    ('unfinished',False,'success',False),('failed',True,'failure',False),
                    ('synthetic',True,'success',True)]:
                with h5py.File(Path(directory)/(name+'.h5'),'w') as f:
                    f.attrs.update(complete=complete,outcome=outcome,mock=mock,schema='pi05_plug_demo/2')
                    f.attrs['collection_total_index']=153
                    f['timestamp']=[10.,10.1]
            rows=list_episodes(directory)
            self.assertEqual(len(rows),1)
            self.assertEqual(select(rows,'153').name,'good.h5')
            self.assertEqual(select(rows,'good.h5').name,'good.h5')
            for invalid in ['0','1','2','-1','text']:
                with self.assertRaises(ValueError):select(rows,invalid)

    def test_total_id_is_never_interpreted_as_row_number(self):
        rows=[dict(path='/data/new_flower_total153.h5',total_index=153)]
        rows.extend(dict(path=f'/data/old_{i}.h5',total_index=i) for i in range(152,0,-1))
        self.assertEqual(select(rows,'153').name,'new_flower_total153.h5')
        self.assertNotEqual(select(rows,'153'),Path(rows[152]['path']))
        rows.reverse()
        self.assertEqual(select(rows,'153').name,'new_flower_total153.h5')

    def test_legacy_file_requires_its_name_and_duplicate_id_is_refused(self):
        rows=[dict(path='/data/legacy.h5',total_index=None)]
        self.assertEqual(select(rows,'legacy.h5').name,'legacy.h5')
        with self.assertRaises(ValueError):select(rows,'1')
        rows=[dict(path='/data/a.h5',total_index=153),dict(path='/data/b.h5',total_index=153)]
        with self.assertRaises(ValueError):select(rows,'153')

    def test_start_during_home_is_not_queued(self):
        gate=ReplayStartGate()
        self.assertFalse(gate.request('homing',['r']))
        self.assertFalse(gate.request('standby',['r']))
        self.assertFalse(gate.request('standby',[]))
        self.assertTrue(gate.request('standby',['r']))

    def test_mock_can_run_unattended(self):
        self.assertTrue(ReplayStartGate().request('standby',[],automatic=True))

    def test_streamed_digest(self):
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'file';p.write_bytes(b'original data')
            self.assertEqual(source_digest(p),hashlib.sha256(b'original data').hexdigest())
