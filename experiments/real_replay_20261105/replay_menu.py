"""Select a saved successful demonstration for one physical trajectory replay."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import h5py
import numpy as np

ROOT=Path(__file__).resolve().parents[1]

def list_episodes(root):
    rows=[]
    for path in Path(root).rglob('*.h5'):
        try:
            with h5py.File(path,'r') as f:
                if (not f.attrs.get('complete') or f.attrs.get('outcome')!='success'
                    or bool(f.attrs.get('mock')) or f.attrs.get('schema')!='pi05_plug_demo/2'):
                    continue
                n=len(f['timestamp'])
                if n<2:continue
                duration=float(f['timestamp'][-1]-f['timestamp'][0])
                if not np.isfinite(duration) or duration<=0:continue
                rows.append(dict(path=str(path.resolve()),frames=n,duration_s=duration,
                    collector=str(f.attrs.get('collector_name','')),
                    total_index=int(f.attrs['collection_total_index']) if 'collection_total_index' in f.attrs else None,
                    collection_date=str(f.attrs.get('collection_date','日期未标注')),
                    mtime=path.stat().st_mtime))
        except (OSError,KeyError,ValueError):continue
    return sorted(rows,key=lambda row:(row['mtime'],row['path']),reverse=True)

def select(rows,answer):
    answer=answer.strip()
    if answer.isdecimal():
        matches=[row for row in rows if row.get('total_index')==int(answer)]
        if not matches:raise ValueError('找不到采集总第 '+answer+' 条；数字是采集总编号，不是列表行号。无总编号的旧文件请输入完整文件名。')
    else:
        matches=[row for row in rows if Path(row['path']).name==answer]
    if len(matches)!=1:raise ValueError('无法唯一确定文件，请使用 --episode 指定完整路径。')
    return Path(matches[0]['path'])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--episode',type=Path)
    group.add_argument('--latest',action='store_true')
    parser.add_argument('--data-root',type=Path,default=ROOT/'data/raw')
    parser.add_argument('--speed',type=float,default=.5)
    parser.add_argument('--list',action='store_true',help='List only; no hardware connection')
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--inspect',action='store_true',help='Validate selected file only')
    mode.add_argument('--mock',action='store_true',help='Use simulated bridge only')
    args=parser.parse_args()
    if not np.isfinite(args.speed) or not 0<args.speed<=1:parser.error('speed 必须在 (0,1]')
    episode=args.episode
    if episode is None or args.list:
        rows=list_episodes(args.data_root)
        if not rows:raise RuntimeError('没有已保存、完整的成功示范：'+str(args.data_root))
        print(f'已保存成功示范 {len(rows)} 条；按保存时间从新到旧排列。数字使用采集总编号，不使用列表行号。')
        for row in rows:
            label=f"总第 {row['total_index']} 条" if row['total_index'] is not None else '无总编号（输入文件名）'
            print(f"{label} | {Path(row['path']).name} | {row['collection_date']} | {row['duration_s']:.1f}秒 | {row['frames']}帧")
        if args.list:return 0
        if args.latest:episode=Path(rows[0]['path'])
        else:
            if not sys.stdin.isatty():raise RuntimeError('请在交互终端选择，或指定 --episode / --latest --inspect')
            while True:
                answer=input('输入采集总编号或完整文件名（例如 153；q 退出）：').strip()
                if answer.lower()=='q':return 0
                try:episode=select(rows,answer);break
                except ValueError as exc:print(exc)
    command=[sys.executable,'-m','pi05_demo.replay','--episode',str(episode.expanduser().resolve()),
             '--speed',str(args.speed)]
    if not args.inspect:command.append('--mock' if args.mock else '--execute')
    print(f'选择：{episode}\n回放速度：{args.speed:g} 倍；每次仅回放一遍。',flush=True)
    return subprocess.call(command,cwd=ROOT)

if __name__=='__main__':
    try:raise SystemExit(main())
    except (RuntimeError,ValueError,OSError) as exc:raise SystemExit(str(exc))
