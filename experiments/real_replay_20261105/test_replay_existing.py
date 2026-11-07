import tempfile,unittest
from pathlib import Path
import numpy as np,h5py
from pi05_demo.episode import EpisodeWriter
from pi05_demo.replay import Trajectory, ReplayLeader

class ReplayTests(unittest.TestCase):
    def make(self,root,outcome='success'):
        cfg={'teleop_controller':'robolab_torque','cameras':{'views':['wrist']},'control_hz':15}
        w=EpisodeWriter(root,mock=False,task='test',session='test',config=cfg)
        q=np.array([0,-.6,0,-2.5,0,1.8,0.])
        for i in range(3):
            t=100+i/15
            w.append(q=q+i*.01,target=q+.2,width=.085,command_width=.085-i*.02,
                     frames={'wrist':(np.zeros((16,16,3),np.uint8),t)},timestamp=t,
                     state_sequence=i+1,command_sequence=i+1,ack=True)
        return w.finish(outcome)
    def test_replay_uses_measured_q_and_holds_gripper_commands(self):
        with tempfile.TemporaryDirectory() as root:
            tr=Trajectory(self.make(root),speed=.5)
            q,width=tr.sample(1/15)
            np.testing.assert_allclose(q,np.array([0,-.6,0,-2.5,0,1.8,0.])+.2)
            self.assertAlmostEqual(width,.085)
            self.assertAlmostEqual(tr.duration,4/15)
            q,width=tr.sample(99)
            self.assertAlmostEqual(q[0],.2);self.assertAlmostEqual(width,.045)
    def test_no_looping_or_unbounded_speed(self):
        with tempfile.TemporaryDirectory() as root:
            p=self.make(root)
            for speed in (0,-1,2,float('nan')):
                with self.assertRaises(ValueError):Trajectory(p,speed=speed)
    def test_incomplete_and_aborted_refused(self):
        with tempfile.TemporaryDirectory() as root:
            p=self.make(root,'aborted')
            with self.assertRaises(ValueError):Trajectory(p)
            with h5py.File(p,'r+') as f:f.attrs['complete']=False
            with self.assertRaises(ValueError):Trajectory(p)
