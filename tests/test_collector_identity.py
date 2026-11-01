import contextlib
import io
import json
import tempfile
import unittest
import shutil
import subprocess
import sys
from pathlib import Path

import h5py
from pi05_demo.episode import EpisodeWriter
import test_episode


class CollectorIdentityTests(unittest.TestCase):
    def save(self, root, name, outcome='success', task_id='rlt'):
        writer = EpisodeWriter(Path(root)/'raw'/'session', mock=True, task='test',
            session='session', config={}, collector={'name': name, 'task_id': task_id,
                'counter_root': str(Path(root)/'raw')})
        writer.append(**test_episode.EpisodeTests().sample())
        return writer.finish(outcome)

    def test_zyp_returns_after_another_collector_and_continues_both_numbers(self):
        with tempfile.TemporaryDirectory() as root:
            for _ in range(10): self.save(root, 'zyp')
            for _ in range(20): self.save(root, 'xxx')
            for i in range(30):
                path = self.save(root, 'zyp')
                with h5py.File(path) as f:
                    self.assertEqual(f.attrs['collector_index'], 11+i)
                    self.assertEqual(f.attrs['collection_total_index'], 31+i)
                    self.assertTrue(f.attrs['display_title'].endswith(f'总第 {31+i} 条'))
                    mmdd = f.attrs['collection_date'].replace('-', '')[4:]
                    self.assertEqual(path.name, f'rlt_{mmdd}_zyp_{11+i}_total{31+i}.h5')

    def test_task_prefix_and_automatic_october_date_are_in_actual_filename(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as root, patch('pi05_demo.collector.collection_date', return_value='2026-10-31'):
            path = self.save(root, 'zyp', task_id='plug')
            self.assertEqual(path.name, 'plug_1031_zyp_1_total1.h5')
            from pi05_demo.collector import Registry
            reloaded = Registry(Path(root)/'raw', mock=True, refresh=True).preview('zyp')
            self.assertEqual((reloaded['saved_personal'], reloaded['saved_total']), (1, 1))

    def test_named_file_never_overwrites_existing_data(self):
        from unittest.mock import patch
        from pi05_demo.collector import Registry
        with tempfile.TemporaryDirectory() as root, patch('pi05_demo.collector.collection_date', return_value='2026-10-31'):
            writer = EpisodeWriter(root, mock=True, task='test', session='session', config={},
                collector={'name': 'zyp', 'task_id': 'rlt', 'counter_root': root})
            writer.append(**test_episode.EpisodeTests().sample())
            target = Path(root)/'rlt_1031_zyp_1_total1.h5'
            target.write_bytes(b'existing data')
            with self.assertRaises(FileExistsError): writer.finish('success')
            self.assertEqual(target.read_bytes(), b'existing data')
            self.assertEqual(Registry(root, mock=True).preview('zyp')['saved_total'], 0)

    def test_failed_trials_do_not_count_and_identity_does_not_change_config_hash(self):
        with tempfile.TemporaryDirectory() as root:
            first = self.save(root, 'zyp')
            self.save(root, 'zyp', 'aborted')
            self.save(root, 'xxx', 'failure')
            second = self.save(root, 'xxx')
            with h5py.File(first) as a, h5py.File(second) as b:
                self.assertEqual(a.attrs['config_sha256'], b.attrs['config_sha256'])
                self.assertEqual(b.attrs['collector_index'], 1)
                self.assertEqual(b.attrs['collection_total_index'], 2)

    def test_numbers_survive_file_removal_and_date_change(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as root:
            first = self.save(root, 'zyp')
            first.unlink()
            with patch('pi05_demo.collector.collection_date', return_value='2026-11-02'):
                second = self.save(root, 'zyp')
            with h5py.File(second) as f:
                self.assertEqual(f.attrs['collection_date'], '2026-11-02')
                self.assertEqual(f.attrs['collector_index'], 2)
                self.assertEqual(f.attrs['collection_total_index'], 2)

    def test_legacy_success_counts_only_towards_total_and_mock_is_separate(self):
        from pi05_demo.collector import Registry
        with tempfile.TemporaryDirectory() as root:
            writer = EpisodeWriter(root, mock=False, task='test', session='legacy', config={})
            writer.append(**test_episode.EpisodeTests().sample())
            writer.finish('success')
            real = Registry(root).preview(' ZYP ')
            self.assertEqual((real['name'], real['saved_personal'], real['saved_total']), ('zyp', 0, 1))
            self.assertEqual(Registry(root, mock=True).preview('zyp')['saved_total'], 0)

    def test_publication_failure_rolls_back_number_and_retry_uses_same_number(self):
        from pi05_demo.collector import Registry
        with tempfile.TemporaryDirectory() as root:
            registry = Registry(root)
            def fail(metadata): raise OSError('disk full')
            with self.assertRaises(OSError):
                registry.save_success(Path(root)/'episode.h5', 'zyp', '2026-11-01', fail)
            self.assertEqual(registry.preview('zyp')['saved_total'], 0)

    def test_prompt_retries_invalid_name_and_reads_only_one_valid_name(self):
        from pi05_demo.collector import prompt_identity
        with tempfile.TemporaryDirectory() as root, contextlib.redirect_stdout(io.StringIO()) as out:
            answers = iter(['', '../bad', ' ZYP '])
            identity = prompt_identity(root, read=lambda _: next(answers))
            self.assertEqual(identity['name'], 'zyp')
            self.assertIn('总第 1 条', out.getvalue())

    def test_guide_keeps_next_number_after_aborted_episode(self):
        from pi05_demo.operator_guide import OperatorGuide
        guide = OperatorGuide()
        guide('collector', name='zyp', saved_personal=10, saved_total=30)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            guide('saved', collector_name='zyp', collection_date='2026-11-01',
                  frames=3, outcome='aborted', episode='aborted.h5')
            guide('alignment', robolab=True, ready=True)
        self.assertIn('zyp · 第 11 条 · 总第 31 条', out.getvalue())

    @unittest.skipUnless(shutil.which('flock'), 'Linux collection launcher')
    def test_launcher_name_prompt_precedes_first_enter_and_q_opens_no_devices(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'scripts').mkdir()
            shutil.copy(repo/'scripts/try_one.sh', root/'scripts/try_one.sh')
            (root/'pi05_demo').symlink_to(repo/'pi05_demo', target_is_directory=True)
            (root/'.venv').symlink_to(Path(sys.prefix), target_is_directory=True)
            (root/'reports/robolab_restore_20261030').mkdir(parents=True)
            proc = subprocess.Popen(['bash', str(root/'scripts/try_one.sh'), '--continuous'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            try:
                proc.stdin.write('zyp\n'); proc.stdin.flush()
                lines = []
                for _ in range(30):
                    line = proc.stdout.readline()
                    lines.append(line)
                    if '输入 q 后 Enter 退出' in line or not line: break
                tail, _ = proc.communicate('q\n', timeout=15)
                output = ''.join(lines) + tail
                self.assertEqual(proc.returncode, 0, output)
            finally:
                if proc.poll() is None: proc.kill(); proc.wait()
            self.assertLess(output.index('请输入采集者姓名'), output.index('启动 Enter'))
            self.assertIn('zyp · 第 1 条 · 总第 1 条', output)
            self.assertEqual(list(root.rglob('desk-before.json')), [])
            self.assertEqual(list(root.rglob('*.h5')), [])
            self.assertEqual(list((root/'data/raw').glob('collection_*')), [])

    def test_async_storage_retains_numbered_metadata(self):
        from pi05_demo.async_episode import AsyncEpisodeWriter
        with tempfile.TemporaryDirectory() as root:
            writer = AsyncEpisodeWriter(root, mock=True, task='test', session='s',
                config={}, collector={'name': 'zyp', 'counter_root': root})
            writer.append(**test_episode.EpisodeTests().sample())
            path = writer.finish('success')
            self.assertEqual(writer.collection_metadata['collector_index'], 1)
            with h5py.File(path) as f:
                self.assertEqual(f.attrs['collection_total_index'], 1)


if __name__ == '__main__': unittest.main()
