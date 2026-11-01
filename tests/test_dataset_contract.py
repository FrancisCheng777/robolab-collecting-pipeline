import unittest
import numpy as np
from pi05_demo import contract
class DatasetContractTests(unittest.TestCase):
    def test_measured_j6_motion_round_trips_without_changing_bridge_codec(self):
        q=np.array([0.,-.6,0.,-2.5,0.,1.8,0.]);target=q.copy();target[5]+=.03634729728347086
        a=contract.encode_dataset(q,target,.04)
        self.assertAlmostEqual(float(a[5]),.03634729728347086/.05,places=6)
        decoded,width=contract.decode_dataset(q,a)
        np.testing.assert_allclose(decoded,target,atol=1e-8)
        self.assertAlmostEqual(width,.04,places=7)
        with self.assertRaises(ValueError):contract.encode(q,target,.04)
        self.assertIn('q0.05',contract.DATASET_CONTRACT_ID)
    def test_new_range_still_rejects_corrupt_large_delta(self):
        with self.assertRaises(ValueError):contract.encode_dataset(np.zeros(7),np.full(7,.051),.04)
