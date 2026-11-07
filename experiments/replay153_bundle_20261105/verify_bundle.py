"""Verify the selected dataset and portable binaries without opening hardware."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
def digest(path):
    result=hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda:f.read(1024*1024),b''):result.update(part)
    return result.hexdigest()
def main():
    manifest=json.loads((ROOT/'manifest.json').read_text())
    for name,expected in manifest['sha256'].items():
        if digest(ROOT/name)!=expected:raise RuntimeError('文件校验失败：'+name)
    import h5py
    with h5py.File(ROOT/manifest['episode']) as f:
        assert int(f.attrs['collection_total_index'])==153
        assert f.attrs['complete'] and f.attrs['outcome']=='success' and not f.attrs['mock']
        assert len(f['timestamp'])==396
    print('校验通过：总第153条 / fg第2条 / 396帧；原始 H5 与打包源文件一致。')

if __name__=='__main__':main()
