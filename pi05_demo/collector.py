"""Collector identity and durable, lifetime success numbering (offline storage only)."""
from contextlib import contextmanager
import argparse
import json
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import h5py

METADATA_FIELDS = ('collector_name', 'collection_date', 'collector_index',
                   'collection_total_index', 'display_title')


def collection_date():
    return datetime.now(ZoneInfo('Asia/Taipei')).date().isoformat()


def normalize_name(value):
    name = unicodedata.normalize('NFKC', value).strip().casefold()
    if not 1 <= len(name) <= 40 or any(not (c.isalnum() or c in '_-') for c in name):
        raise ValueError('姓名需为 1–40 个中文、字母、数字、下划线或短横线；不能含空格或路径符号。')
    return name


def title(name, day, personal, total):
    return f'{day} · {name} · 第 {personal} 条 · 总第 {total} 条'


class Registry:
    def __init__(self, root, *, mock=False, refresh=False):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / ('.collection_counts.mock.sqlite3' if mock else '.collection_counts.sqlite3')
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS episodes (source TEXT PRIMARY KEY, collector TEXT NOT NULL, personal INTEGER NOT NULL, total INTEGER UNIQUE NOT NULL, day TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY)')
            db.execute('BEGIN IMMEDIATE')
            if refresh or not db.execute("SELECT 1 FROM settings WHERE key='initialized'").fetchone():
                existing = {row[0] for row in db.execute('SELECT source FROM episodes')}
                records = []
                for path in sorted(self.root.rglob('*.h5')):
                    source = str(path.resolve())
                    if source in existing: continue
                    with h5py.File(path, 'r') as f:
                        if (not f.attrs.get('complete') or f.attrs.get('outcome') != 'success'
                                or bool(f.attrs.get('mock')) != mock or 'review_source' in f.attrs):
                            continue
                        name = str(f.attrs.get('collector_name', ''))
                        records.append((source, name, int(f.attrs.get('collector_index', 0)),
                                        int(f.attrs.get('collection_total_index', 0)),
                                        str(f.attrs.get('collection_date', ''))))
                # Restore explicit historical ordinals first if rebuilding a ledger.
                for source, name, personal, total, day in sorted(records, key=lambda r: (r[3] == 0, r[3], r[0])):
                    if not total: total = self.counts(db, name)[1]+1
                    if name and not personal: personal = self.counts(db, name)[0]+1
                    db.execute('INSERT INTO episodes VALUES (?,?,?,?,?)', (source, name, personal, total, day))
                db.execute("INSERT OR IGNORE INTO settings VALUES ('initialized')")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def counts(db, name):
        personal = db.execute('SELECT COALESCE(MAX(personal),0) FROM episodes WHERE collector=?', (name,)).fetchone()[0]
        total = db.execute('SELECT COALESCE(MAX(total),0) FROM episodes').fetchone()[0]
        return personal, total

    def preview(self, name):
        name = normalize_name(name)
        with self.connect() as db:
            personal, total = self.counts(db, name)
        return {'name': name, 'counter_root': str(self.root), 'saved_personal': personal, 'saved_total': total}

    def save_success(self, source, name, day, publish):
        """Serialize numbering and H5 publication, outside the control thread.

        If publication raises, the DB transaction rolls back. If the process
        dies after publication but before commit, next startup recovers the
        ordinals from the completed H5 attributes.
        """
        name = normalize_name(name)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            personal, total = self.counts(db, name)
            metadata = dict(collector_name=name, collection_date=day, collector_index=personal+1,
                            collection_total_index=total+1, display_title=title(name, day, personal+1, total+1))
            db.execute('INSERT INTO episodes VALUES (?,?,?,?,?)',
                       (str(Path(source).resolve()), name, personal+1, total+1, day))
            publish(metadata)
        return metadata


def prompt_identity(root, *, mock=False, read=input):
    registry = Registry(root, mock=mock, refresh=True)
    while True:
        raw = read('请输入采集者姓名（例如 zyp；输入 q 退出）：')
        if raw.strip().casefold() == 'q': raise SystemExit(130)
        try: name = normalize_name(raw)
        except ValueError as exc:
            print(exc, flush=True)
            continue
        info = registry.preview(name)
        print(f"采集日期：{collection_date()}（自动）\n"
              f"{name} 已保存 {info['saved_personal']} 条；累计总量 {info['saved_total']} 条。\n"
              f"下一条：{title(name, collection_date(), info['saved_personal']+1, info['saved_total']+1)}", flush=True)
        return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--identity', required=True)
    args = parser.parse_args()
    info = prompt_identity(args.root)
    Path(args.identity).write_text(json.dumps(info, ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__': main()
