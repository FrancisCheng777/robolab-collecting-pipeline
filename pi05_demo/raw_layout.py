"""Flatten completed raw H5 files, retaining session metadata and counter identities."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): value.update(block)
    return value.hexdigest()


def write_json(path, value):
    temp = path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    os.replace(temp, path)


def flatten(root, backup, *, clips=(), apply=False, lock_path='/tmp/pi05-robolab-trial-20261030.lock'):
    root, backup = Path(root).resolve(), Path(backup).resolve()
    if not root.is_dir() or backup == root or root in backup.parents:
        raise ValueError('Input must exist; backup must be outside the raw directory')
    with open(lock_path, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        sources = sorted(p for p in root.rglob('*.h5') if p.parent != root)
        targets = [root/p.name for p in sources]
        if len(set(targets)) != len(targets) or any(p.exists() for p in targets):
            raise ValueError('Duplicate H5 names; nothing moved')
        if any(p.is_symlink() or not p.resolve().is_relative_to(root) for p in sources):
            raise ValueError('External or symlink source; nothing moved')
        mapping = {str(p.relative_to(root)): q.name for p, q in zip(sources, targets)}
        plan_updates = []
        for raw_plan in clips:
            path = Path(raw_plan).resolve()
            if not path.exists(): continue
            original = json.loads(path.read_text())
            changed = {**original, 'recordings': {mapping.get(k,k): v for k,v in original.get('recordings',{}).items()}}
            if len(changed['recordings']) != len(original.get('recordings',{})):
                raise ValueError('Clip plan filename collision; nothing moved')
            plan_updates.append((path, original, changed))
        report = {'root': str(root), 'moves': mapping, 'files': len(sources), 'applied': False}
        if not apply: return report
        backup.mkdir(parents=True, exist_ok=False)
        report['sha256'] = {p.name: digest(p) for p in sources}
        report['original_directories'] = [str(p.relative_to(root)) for p in root.rglob('*') if p.is_dir()]
        write_json(backup/'manifest.json', report)
        connections, moved = [], []
        try:
            for path in sorted(root.glob('.collection_counts*.sqlite3')):
                connection = sqlite3.connect(path)
                saved = sqlite3.connect(backup/path.name)
                connection.backup(saved); saved.close()
                connection.execute('BEGIN IMMEDIATE')
                connections.append((path, connection))
            for i,(path,_,_) in enumerate(plan_updates): shutil.copy2(path, backup/f'clips-{i}.json')
            for source,target in zip(sources,targets):
                # Same-volume link/unlink preserves content, mtime and fingerprint;
                # link refuses to overwrite any file created since the preflight.
                os.link(source,target)
                moved.append((source,target))
                source.unlink()
                for _,connection in connections:
                    connection.execute('UPDATE episodes SET source=? WHERE source=?', (str(target),str(source)))
                if digest(target) != report['sha256'][target.name]:
                    raise RuntimeError('H5 content changed during relocation')
            for path,_,changed in plan_updates: write_json(path,changed)
            for _,connection in connections: connection.commit()
            for directory in sorted(root.rglob('*'), key=lambda p:len(p.parts), reverse=True):
                if directory.is_dir():
                    try: directory.rmdir()
                    except OSError: pass  # Only remove empty session wrappers.
            report['applied'] = True
            write_json(backup/'manifest.json', report)
        except BaseException:
            for _,connection in connections: connection.rollback()
            for source,target in reversed(moved):
                source.parent.mkdir(parents=True,exist_ok=True)
                if not source.exists(): os.link(target,source)
                target.unlink()
            for path,original,_ in plan_updates: write_json(path,original)
            for path,connection in connections:
                saved = sqlite3.connect(backup/path.name)
                saved.backup(connection); saved.close()
            raise
        finally:
            for _,connection in connections: connection.close()
        return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True)
    p.add_argument('--backup',required=True)
    p.add_argument('--clips',action='append',default=[])
    p.add_argument('--apply',action='store_true')
    args=p.parse_args()
    report=flatten(args.input,args.backup,clips=args.clips,apply=args.apply)
    print(json.dumps({'files':report['files'],'applied':report['applied'],'root':report['root']},indent=2))


if __name__=='__main__':main()
