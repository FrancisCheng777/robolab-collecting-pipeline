"""Host adaptation for the standalone Panda replay; no robot motion here."""
import json
import os
from pathlib import Path
import resource
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def settings():
    values=json.loads((ROOT/'host.json').read_text())
    allowed=sorted(os.sched_getaffinity(0))
    if len(allowed)<2:raise RuntimeError('回放需要至少两个可用 CPU 核')
    control=values.get('control_cpu')
    if control is None:control=allowed[-1]
    worker=values.get('worker_cpu')
    if worker is None:worker=next(x for x in allowed if x!=control)
    if control not in allowed or worker not in allowed or control==worker:
        raise RuntimeError('host.json 中控制核和 Python 核必须不同且可用')
    return dict(values,control_cpu=control,worker_cpu=worker,
                background_cpus=','.join(str(x) for x in allowed if x!=control))

def cpu_list(value):
    cpus=set()
    for part in value.strip().split(','):
        if not part:continue
        ends=part.split('-')
        cpus.update(range(int(ends[0]),int(ends[-1])+1))
    return sorted(cpus)

def network_state():
    host=settings()
    nic=host.get('network_interface')
    if not nic:
        rows=json.loads(subprocess.check_output(['ip','-j','route','get',host['robot_ip']],text=True))
        nic=rows[0]['dev']
    path=Path('/sys/class/net')/nic
    if nic=='lo' or (path/'wireless').exists():raise RuntimeError('机器人应通过有线直连网卡连接；检查 host.json 和 IP 路由')
    cpus=set()
    for irq in (path/'device/msi_irqs').iterdir():
        cpus.update(cpu_list((Path('/proc/irq')/irq.name/'effective_affinity_list').read_text()))
    if not cpus:raise RuntimeError('无法识别机器人网卡 IRQ CPU：'+nic)
    threads=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            name=(proc/'comm').read_text().strip()
            if name.startswith('ksoftirqd/') and int(name.split('/')[1]) in cpus:
                pid=int(proc.name)
                threads.append(dict(pid=pid,cpu=int(name.split('/')[1]),
                    policy=os.sched_getscheduler(pid),priority=os.sched_getparam(pid).sched_priority,
                    start=(proc/'stat').read_text().rsplit(')',1)[1].split()[19]))
        except (OSError,ValueError):continue
    if len(threads)!=len(cpus):raise RuntimeError('无法读取全部机器人网卡接收线程')
    return dict(nic=nic,cpus=sorted(cpus),threads=threads)

def gripper_path():
    host=settings()
    config=json.loads((ROOT/'configs/latency/responsive_recording/bridge.trial.json').read_text())
    return Path(host.get('gripper_device') or config['gripper_device'])

def usb_latency_path():
    tty=gripper_path().resolve(strict=True).name
    path=Path('/sys/bus/usb-serial/devices')/tty/'latency_timer'
    if not path.is_file():raise RuntimeError('无法读取 Robotiq FTDI 延迟：'+str(path))
    return path

def require_station():
    if not Path('/sys/kernel/realtime').exists() or Path('/sys/kernel/realtime').read_text().strip()!='1':
        raise RuntimeError('请使用 PREEMPT_RT 实时内核')
    if os.getpriority(os.PRIO_PROCESS,0)!=0:raise RuntimeError('请从 nice=0 的普通终端运行')
    if resource.getrlimit(resource.RLIMIT_RTPRIO)[0]<99:
        raise RuntimeError('当前终端实时优先级权限不足：ulimit -r 应为 99；请按 README 设置实时权限并重新登录')
    network=network_state()
    if any(x['policy']!=os.SCHED_FIFO or x['priority']<50 for x in network['threads']):
        raise RuntimeError('请先运行 bash prepare_station.sh，恢复本机网卡接收调度')
    if int(usb_latency_path().read_text())!=1:
        raise RuntimeError('请先运行 bash prepare_station.sh，将 Robotiq USB latency 设为 1 ms')
    return network
