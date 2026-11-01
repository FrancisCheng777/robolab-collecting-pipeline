"""Optional Chromium workflow test; requires Playwright and installed Chromium."""
import json
import os
import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from urllib.request import urlopen

from test_curation import episode


@unittest.skipUnless(os.environ.get('CURATION_BROWSER_TEST') == '1', 'opt-in browser integration')
class CurationBrowserTests(unittest.TestCase):
    def test_wrist_play_cut_undo_save_reload_and_export(self):
        import sys
        from playwright.sync_api import sync_playwright
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            episode(root/'raw', collector={'name': 'zyp', 'counter_root': str(root/'raw')})
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            with (root/'server.log').open('w') as log:
                proc = subprocess.Popen([sys.executable, '-m', 'pi05_demo.curation',
                    '--input', str(root/'raw'), '--output', str(root/'selected'),
                    '--clips', str(root/'clips.json'), '--port', str(port)], stdout=log, stderr=log)
                try:
                    url = f'http://127.0.0.1:{port}'
                    for _ in range(100):
                        try:
                            with urlopen(url+'/api/recordings', timeout=.2): break
                        except OSError: time.sleep(.1)
                    else: self.fail((root/'server.log').read_text())
                    with sync_playwright() as pw:
                        browser = pw.chromium.launch(headless=True)
                        page = browser.new_page(viewport={'width': 1400, 'height': 1100})
                        errors = []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.goto(url)
                        page.wait_for_selector('#wrist.loaded')
                        self.assertEqual(page.locator('#videos img').count(), 1)
                        self.assertIn('zyp · 第 1 条 · 总第 1 条', page.locator('#title').inner_text())
                        page.fill('#search', 'ZYP')
                        self.assertEqual(page.locator('#recordings button').count(), 1)
                        page.click('#play')
                        page.wait_for_function("document.querySelector('#frame').textContent !== '帧 1 / 16'")
                        page.click('#play')
                        page.fill('#start', str(5/15))
                        page.fill('#end', str(8/15))
                        page.click('#addClip')
                        self.assertIn('12 / 16', page.locator('#clipInfo').inner_text())
                        page.click('#undo')
                        self.assertIn('16 / 16', page.locator('#clipInfo').inner_text())
                        page.click('#addClip')
                        page.click('#save')
                        page.wait_for_function("document.querySelector('#saved').textContent === '已保存'")
                        page.reload()
                        page.wait_for_selector('#wrist.loaded')
                        self.assertIn('12 / 16', page.locator('#clipInfo').inner_text())
                        page.click('#export')
                        page.wait_for_function("document.querySelector('#exportStatus').textContent.includes('导出完成')", timeout=30000)
                        report = json.loads((root/'selected/export_report.json').read_text())
                        self.assertEqual(report['total_episodes'], 2)
                        self.assertEqual(report['total_frames'], 12)
                        page.fill('#search', '')
                        episode(root/'raw')
                        page.wait_for_function("document.querySelectorAll('#recordings button').length === 2", timeout=12000)
                        self.assertIn('zyp · 第 1 条 · 总第 1 条', page.locator('#title').inner_text())
                        self.assertEqual(errors, [])
                        browser.close()
                finally:
                    proc.terminate()
                    proc.wait(timeout=10)


if __name__ == '__main__':
    unittest.main()
