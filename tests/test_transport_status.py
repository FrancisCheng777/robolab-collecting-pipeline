import unittest
import json
from unittest.mock import patch, MagicMock
import numpy as np
from pi05_demo.transport import Bridge

class TransportStatusTests(unittest.TestCase):
    def test_hold_rejection_does_not_consume_command_sequence(self):
        from pi05_demo.transport import HoldNotReady
        b=Bridge.__new__(Bridge)
        b.seq=7;b.session='session';b.owner='owner';b.path='/unused-test.sock'
        sock=MagicMock()
        sock.__enter__.return_value=sock
        sock.recv.side_effect=[
            b'{"ok":false,"error":"wait until arm and gripper are held before resuming"}\n',
            b'{"ok":true,"sequence":8}\n']
        with patch('pi05_demo.transport.socket.socket',return_value=sock):
            with self.assertRaises(HoldNotReady):
                b.command({'state_sequence':12},np.zeros(7),.04,motion_profile='home')
            self.assertEqual(b.seq,7)
            b.hold({'state_sequence':13})
        sent=[json.loads(c.args[0]) for c in sock.sendall.call_args_list]
        self.assertEqual([p['sequence'] for p in sent],[8,8])
        self.assertEqual(b.seq,8)

    def reader(self,**changes):
        b=Bridge.__new__(Bridge)
        st=dict(ready=True,fault='',stopped=False,stopping=False,state_age_s=.001,gripper_age_s=.02)
        st.update(changes);b.request=lambda _:st
        return b
    def test_control_fault_is_reported_before_stale_feedback(self):
        with self.assertRaisesRegex(RuntimeError,'libfranka failure'):
            self.reader(ready=False,fault='libfranka failure',state_age_s=1.).state()
    def test_robot_and_gripper_staleness_are_distinguishable(self):
        with self.assertRaisesRegex(RuntimeError,'stale robot feedback'):
            self.reader(state_age_s=.06).state()
        with self.assertRaisesRegex(RuntimeError,'stale gripper feedback'):
            self.reader(gripper_age_s=.6).state()
    def test_stopping_controller_is_never_ready(self):
        with self.assertRaisesRegex(RuntimeError,'controller stopping'):
            self.reader(stopping=True).state()
