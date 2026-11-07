"""Single real view remains single through recording, export, and model inputs."""
import importlib.util
import json
import tempfile
import threading
import time
import unittest
from collections import deque
from pathlib import Path
from unittest.mock import patch

import h5py
import numpy as np
from pi05_demo.cameras import Pair
from pi05_demo.episode import EpisodeWriter, inspect_episode
from pi05_demo.timing import audit_timing
from pi05_demo.export_actions import aligned_records

ROOT = Path(__file__).resolve().parents[1]

class WristOnlyTests(unittest.TestCase):
    def write_episode(self, root, session='train'):
        cfg={'control_hz':15,'teleop_controller':'robolab_torque','cameras':{'views':['wrist']}}
        writer=EpisodeWriter(root,mock=True,task='insert plug',session=session,config=cfg)
        t=time.monotonic()
        q=np.array([0.,-.6,0.,-2.5,0.,1.8,0.])
        try:
            for i in range(16):
                stamp=t+i/15
                writer.append(q=q+i*.001,target=q+i*.001,width=.04,command_width=.04,
                    frames={'wrist':(np.full((224,224,3),80+i,np.uint8),stamp)},
                    timestamp=stamp,state_sequence=i+1,command_sequence=i+1,ack=True)
            return writer.finish('success')
        finally:
            writer.close_incomplete()

    def test_only_wrist_is_saved_audited_and_aligned(self):
        with tempfile.TemporaryDirectory() as root:
            path=self.write_episode(root)
            info=inspect_episode(path,allow_mock=True)
            self.assertEqual(info['camera_views'],['wrist'])
            with h5py.File(path,'r') as f:
                self.assertEqual(set(f['images']),{'wrist'})
                report=audit_timing(f,15,allow_resampling=True)
                self.assertEqual(set(report['cameras']),{'wrist'})
                self.assertIsNone(report['host_receive_skew_ms'])
                states,actions,rows,cameras,grid=aligned_records(f,15)
                self.assertEqual(set(cameras),{'wrist'})
                self.assertEqual(actions.shape,(15,8))

    def test_missing_wrist_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path=self.write_episode(root)
            with h5py.File(path,'r+') as f:del f['images/wrist']
            with self.assertRaises(ValueError):inspect_episode(path,allow_mock=True)

    def test_dual_camera_config_cannot_silently_lose_main(self):
        with tempfile.TemporaryDirectory() as root:
            path=self.write_episode(root)
            with h5py.File(path,'r+') as f:
                cfg=json.loads(f.attrs['config_json']);cfg['cameras']['views']=['main','wrist']
                f.attrs['config_json']=json.dumps(cfg)
            with self.assertRaises(ValueError):inspect_episode(path,allow_mock=True)

    def test_single_capture_uses_latest_real_wrist_timestamp(self):
        p=Pair.__new__(Pair);p.lock=threading.Lock()
        image=np.zeros((224,224,3),np.uint8)
        p.history={'wrist':deque([(image,9.99,{'frame_id':8})])}
        with patch('pi05_demo.cameras.time.monotonic',return_value=10.):
            frames,metadata=p.capture_with_metadata()
        self.assertEqual(set(frames),{'wrist'})
        self.assertEqual(frames['wrist'][1],9.99)
        self.assertEqual(metadata['wrist']['frame_id'],8)
        with patch('pi05_demo.cameras.time.monotonic',return_value=11.):
            with self.assertRaises(ValueError):p.capture_with_metadata()

    def test_review_inventory_and_wrist_frame_without_main(self):
        import urllib.request
        import urllib.error
        from http.server import ThreadingHTTPServer
        from pi05_demo.review import handler
        with tempfile.TemporaryDirectory() as root:
            path=self.write_episode(root)
            server=ThreadingHTTPServer(('127.0.0.1',0),handler(root))
            worker=threading.Thread(target=server.serve_forever);worker.start()
            url=f'http://127.0.0.1:{server.server_port}'
            try:
                with urllib.request.urlopen(url+'/episodes') as response:
                    self.assertEqual(json.load(response)[0]['camera_views'],['wrist'])
                with urllib.request.urlopen(url+f'/frame?episode={path.name}&index=0&camera=wrist') as response:
                    self.assertEqual(response.headers['Content-Type'],'image/jpeg')
                with self.assertRaises(urllib.error.HTTPError):
                    urllib.request.urlopen(url+f'/frame?episode={path.name}&index=0&camera=main')
            finally:
                server.shutdown();worker.join();server.server_close()

    def test_single_and_continuous_entries_use_same_wrist_recording_profile(self):
        import subprocess
        configs=[]
        for entry in ['collect_one.sh','collect_session.sh']:
            result=subprocess.run(['bash',str(ROOT/'scripts'/entry),'--inspect'],
                                  capture_output=True,text=True,check=True,cwd=ROOT)
            config,_=json.JSONDecoder().raw_decode(result.stdout[result.stdout.index('{'):])
            configs.append(config)
        self.assertEqual(configs[0],configs[1])
        self.assertEqual(configs[0]['cameras']['views'],['wrist'])
        self.assertEqual(configs[0]['latency_profile'],'responsive_recording')
        self.assertEqual(configs[0]['teleop_hz'],100)
        self.assertEqual(configs[0]['control_hz'],15)
        self.assertTrue(configs[0]['async_recording'])

    def test_policy_slot_matches_rlinf_single_camera_convention(self):
        from pi05_demo.vision import policy_images
        row={'observation.images.wrist':np.ones((3,224,224),np.float32)*.25}
        images,masks=policy_images(row,['wrist'])
        self.assertEqual(masks,{'base_0_rgb':True,'left_wrist_0_rgb':False,'right_wrist_0_rgb':False})
        self.assertTrue(np.all(images['base_0_rgb']==64))
        self.assertFalse(images['left_wrist_0_rgb'].any())
        self.assertFalse(images['right_wrist_0_rgb'].any())

    @unittest.skipUnless(importlib.util.find_spec('lerobot') and
                         importlib.util.find_spec('lerobot.datasets'), 'official LeRobot environment required')
    def test_official_single_camera_export(self):
        from pi05_demo.export import export
        from lerobot.datasets.lerobot_dataset import LeRobotDataset
        from pi05_demo.vision import policy_images
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);raw=root/'raw'
            self.write_episode(raw,'train');self.write_episode(raw,'validation')
            report=export(raw,root/'dataset',validation_sessions=['validation'],allow_mock=True)
            self.assertEqual(report['camera_views'],['wrist'])
            ds=LeRobotDataset('local/pi05_plug_train',root=root/'dataset/train',video_backend='pyav')
            self.assertNotIn('observation.images.main',ds.features)
            images,masks=policy_images(ds[0],report['camera_views'])
            self.assertEqual(sum(masks.values()),1)
            self.assertTrue(masks['base_0_rgb'])
            self.assertEqual(images['base_0_rgb'].shape,(224,224,3))
