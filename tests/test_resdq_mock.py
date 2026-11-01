"""Exercise actual async storage and C++ mock with the production recording profile."""
import json,tempfile,time,unittest
from pathlib import Path
import h5py,numpy as np
from pi05_demo.cameras import SyntheticPair
from pi05_demo.collect import MockLeader
from pi05_demo.session import CollectionSession
from test_collection_session import mock_bridge,ROOT

class ResdqMockTests(unittest.TestCase):
    def test_home_open_review_save_discard_and_aborted_exit(self):
        cfg=json.loads((ROOT/'configs/latency/responsive_recording/collection.trial.json').read_text())
        cfg['episode_keys']='resdq'
        calibration=json.loads((ROOT/'configs/latency/responsive_recording/bridge.trial.json').read_text())
        events=[]
        with mock_bridge(robolab=True,config_overrides=calibration) as bridge,tempfile.TemporaryDirectory() as root:
            s=CollectionSession(bridge,SyntheticPair(cfg['cameras']),MockLeader(bridge),cfg,root,'resdq',mock=True,auto_home=True,announce=lambda e,**d:events.append((e,d)))
            def until(predicate,timeout=15):
                deadline=time.monotonic()+timeout
                while not predicate():
                    if time.monotonic()>deadline:self.fail('timeout in '+s.phase)
                    s.tick();time.sleep(.01)
            try:
                until(lambda:s.phase=='standby')
                for choice in ('s','d'):
                    s.tick(['r']);self.assertEqual(s.phase,'recording')
                    until(lambda:s.writer.count>=10)
                    count=s.writer.count;s.tick(['e'])
                    until(lambda:s.phase=='review')
                    self.assertEqual(s.writer.count,count)
                    self.assertLess(np.max(np.abs(np.array(bridge.state()['q'])-cfg['arm_home'])),.05)
                    self.assertAlmostEqual(bridge.state()['gripper_width'],.085,delta=.005)
                    s.tick([choice]);until(lambda:s.phase=='standby')
                s.tick(['r']);until(lambda:s.writer.count>=3);self.assertFalse(s.tick(['q']))
                outcomes=[]
                for p in Path(root).glob('*.h5'):
                    with h5py.File(p) as f:
                        outcomes.append(str(f.attrs['outcome']))
                        self.assertNotIn('episode_keys',json.loads(f.attrs['config_json']))
                self.assertCountEqual(outcomes,['success','aborted'])
                self.assertEqual(len(list(Path(root).rglob('*.h5'))),2)
                self.assertEqual(list(Path(root).glob('*.inprogress')),[])
            finally:s.close()
