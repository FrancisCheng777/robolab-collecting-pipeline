"""Explicit, temporary host scheduling/USB setup; does not connect to Franka."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pi05_demo.portable_host import network_state,usb_latency_path

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--rollback',type=Path)
    args=parser.parse_args()
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:argv=(proc/'cmdline').read_bytes().split(b'\0')
        except OSError:continue
        if argv and Path(argv[0].decode(errors='replace')).name=='pi05_franka_bridge' and b'--mock' not in argv:
            raise RuntimeError('已有真机控制进程，请先退出：'+proc.name)
    if args.apply or args.rollback:
        if os.geteuid()!=0:raise RuntimeError('请通过 sudo 执行主机设置')
    if args.rollback:
        path=args.rollback.resolve()
        if path.parent!=Path('/var/backups') or path.stat().st_uid!=0:raise RuntimeError('只接受 /var/backups 下的 root 备份')
        saved=json.loads(path.read_text())
        if saved['boot_id']!=Path('/proc/sys/kernel/random/boot_id').read_text().strip():raise RuntimeError('主机已重启；不应用旧备份')
        for thread in saved['network']['threads']:
            now=(Path('/proc')/str(thread['pid'])/'stat').read_text().rsplit(')',1)[1].split()[19]
            if now!=thread['start']:raise RuntimeError('线程身份变化，停止恢复')
            if os.sched_getscheduler(thread['pid'])!=os.SCHED_FIFO or os.sched_getparam(thread['pid']).sched_priority!=50:
                if thread['policy']==os.sched_getscheduler(thread['pid']) and thread['priority']==os.sched_getparam(thread['pid']).sched_priority:continue
                raise RuntimeError('线程调度已被其他程序修改，停止恢复')
            os.sched_setscheduler(thread['pid'],thread['policy'],os.sched_param(thread['priority']))
        Path(saved['usb_path']).write_text(str(saved['usb_latency']))
        print('已恢复原调度和 USB 延迟');return
    network=network_state();usb=usb_latency_path()
    saved=dict(network=network,usb_path=str(usb),usb_latency=int(usb.read_text()),
               boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    print(json.dumps(saved,indent=2))
    if not args.apply:return
    for thread in network['threads']:
        if thread['policy']==os.SCHED_FIFO and thread['priority']>=50:continue
        if thread['policy']!=os.SCHED_OTHER or thread['priority']!=0:raise RuntimeError('已有自定义调度；不自动覆盖')
    backup=Path('/var/backups')/('franka-replay153-station-'+str(time.time_ns())+'.json')
    backup.write_text(json.dumps(saved,indent=2));backup.chmod(0o600)
    try:
        for thread in network['threads']:
            if thread['policy']==os.SCHED_OTHER:os.sched_setscheduler(thread['pid'],os.SCHED_FIFO,os.sched_param(50))
        usb.write_text('1')
    except BaseException:
        for thread in network['threads']:os.sched_setscheduler(thread['pid'],thread['policy'],os.sched_param(thread['priority']))
        usb.write_text(str(saved['usb_latency']));raise
    actual=network_state()
    assert all(t['policy']==os.SCHED_FIFO and t['priority']>=50 for t in actual['threads'])
    assert int(usb.read_text())==1
    print('主机设置已验证；未连接或移动机械臂。备份：'+str(backup))

if __name__=='__main__':main()
