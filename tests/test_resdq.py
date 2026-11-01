import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from pi05_demo.cameras import SyntheticPair
from pi05_demo.session import CollectionSession, Keys
from pi05_demo.episode import inspect_episode
from test_low_latency import StubBridge, Leader

class MovingBridge(StubBridge):
    def __init__(self):
        super().__init__();self.q=np.array(super().state()['q']);self.closed=False
    def state(self):
        s=super().state();s['q']=self.q.copy();s['calibration']['gripper_max_width']=.085
        return s
    def command(self,state,target,width,**kwargs):
        reply=super().command(state,target,width,**kwargs);self.q=np.asarray(target).copy();return reply
    def close(self): self.closed=True

class RecordingKeysTests(unittest.TestCase):
    def make(self,root):
        bridge=MovingBridge();events=[]
        cfg=dict(teleop_controller='robolab_torque',arm_home=bridge.q.tolist(),task='test',control_hz=15,episode_keys='resdq',cameras={'views':['wrist']})
        s=CollectionSession(bridge,SyntheticPair(cfg['cameras']),Leader(),cfg,root,'test',mock=True,announce=lambda e,**d:events.append((e,d)))
        s.phase='standby';return s,events
    def tick_until(self,s,phase,clock):
        for _ in range(300):
            if s.phase==phase:return
            clock.return_value+=.02;s.tick()
        self.fail('did not reach '+phase+': '+s.phase)
    def test_decode_keys(self):
        self.assertEqual(Keys().feed(b'rEdsq'),list('redsq'))
    def test_end_returns_home_without_recording_then_save_discard_and_repeat(self):
        with tempfile.TemporaryDirectory() as root, patch('time.monotonic',return_value=100.) as clock:
            s,events=self.make(root)
            try:
                s.tick(['toggle']);self.assertEqual(s.phase,'standby')
                for choice in ('s','d'):
                    s.tick(['r']);self.assertEqual(s.phase,'recording')
                    for _ in range(4):clock.return_value+=1/15;s.tick()
                    count=s.writer.count
                    s.tick(['e']);self.assertNotEqual(s.phase,'recording')
                    self.tick_until(s,'review',clock)
                    self.assertEqual(s.writer.count,count)
                    np.testing.assert_allclose(s.bridge.q,s.config['arm_home'],atol=1e-5)
                    s.tick(['r']);self.assertEqual(s.phase,'review')
                    s.tick([choice]);self.assertEqual(s.phase,'standby')
                files=list(Path(root).glob('*.h5'));self.assertEqual(len(files),1)
                self.assertEqual(inspect_episode(files[0],allow_mock=True)['outcome'],'success')
                self.assertEqual(len(list(Path(root).rglob('*.h5'))),1)
                self.assertEqual(list(Path(root).glob('*.inprogress')),[])
                self.assertTrue(any(e=='discarded' for e,_ in events))
                self.assertFalse(s.tick(['q']));self.assertTrue(s.bridge.closed)
            finally:s.close()
    def test_q_preserves_unconfirmed_as_aborted(self):
        with tempfile.TemporaryDirectory() as root, patch('time.monotonic',return_value=100.) as clock:
            s,_=self.make(root);s.tick(['r']);s.tick();s.tick(['q'])
            self.assertTrue(s.closed)
            self.assertEqual(inspect_episode(next(Path(root).glob('*.h5')),allow_mock=True)['outcome'],'aborted')
