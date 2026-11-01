import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

import h5py
from pi05_demo.collector import Registry
from pi05_demo.raw_layout import flatten, digest
from test_curation import episode


class RawLayoutTests(unittest.TestCase):
    def test_flatten_preserves_bytes_session_counter_and_clip_decisions(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'raw'
            source=episode(root/'session-A',collector={'name':'zyp','counter_root':str(root)})
            before=digest(source)
            plan=Path(temp)/'clips.json'
            plan.write_text(json.dumps({'version':1,'recordings':{'session-A/'+source.name:{'exclude':[[.1,.2]]}}}))
            report=flatten(root,Path(temp)/'backup',clips=[plan],apply=True,lock_path=Path(temp)/'lock')
            target=root/source.name
            self.assertTrue(report['applied'])
            self.assertFalse(source.exists())
            self.assertEqual(digest(target),before)
            self.assertEqual(list(root.glob('*.h5')),[target])
            self.assertEqual(json.loads(plan.read_text())['recordings'],{target.name:{'exclude':[[.1,.2]]}})
            with h5py.File(target) as f:self.assertEqual(f.attrs['session'],'session-A')
            counts=Registry(root,mock=True,refresh=True).preview('zyp')
            self.assertEqual((counts['saved_personal'],counts['saved_total']),(1,1))
            with sqlite3.connect(root/'.collection_counts.mock.sqlite3') as db:
                self.assertEqual(db.execute('select source from episodes').fetchone()[0],str(target.resolve()))
            self.assertFalse((root/'session-A').exists())

    def test_collision_refuses_before_any_move(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'raw'
            source=episode(root/'session-A')
            (root/source.name).write_bytes(b'existing')
            with self.assertRaisesRegex(ValueError,'Duplicate'):
                flatten(root,Path(temp)/'backup',apply=True,lock_path=Path(temp)/'lock')
            self.assertTrue(source.exists())
            self.assertEqual((root/source.name).read_bytes(),b'existing')

    def test_session_audit_only_reads_the_current_session_in_flat_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'raw'
            source=episode(root,mock=False)
            other=episode(root,mock=False)
            with h5py.File(other,'r+') as f:f.attrs['session']='session-B'
            report=Path(temp)/'audit.json'
            subprocess.run([sys.executable,'scripts/check_session.py','--input',str(root),
                '--report',str(report),'--session','session-A'],check=True,capture_output=True,text=True)
            records=json.loads(report.read_text())['episodes']
            self.assertEqual([r['path'] for r in records],[str(source)])
            self.assertTrue(records[0]['passed'])


if __name__=='__main__':unittest.main()
