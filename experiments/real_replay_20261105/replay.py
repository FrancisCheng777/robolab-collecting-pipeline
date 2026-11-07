"""Replay recorded absolute leader targets through the unchanged collection bridge."""
import argparse,fcntl,hashlib,json,os,select,signal,subprocess,sys,termios,time,tty,uuid
from pathlib import Path
import h5py,numpy as np
from .episode import inspect_episode
from .session import CollectionSession,Keys
from .transport import Bridge
from .teleop_runtime import configure_runtime
from .socket_preflight import clear_stale_socket
ROOT=Path(__file__).resolve().parents[1]

class Trajectory:
    def __init__(self,path,speed=1.):
        if not np.isfinite(speed) or not 0<speed<=1:raise ValueError('speed must be in (0,1]')
        self.path=Path(path).resolve();self.info=inspect_episode(self.path,allow_mock=False)
        if self.info['outcome']!='success':raise ValueError('replay requires a successful complete real episode')
        with h5py.File(self.path) as f:
            if f.attrs['schema']!='pi05_plug_demo/2':raise ValueError('replay requires RoboLab absolute-target recordings')
            self.config=json.loads(f.attrs['config_json']);self.times=np.asarray(f['timestamp'],float)
            self.q=np.asarray(f['q'],float);self.targets=np.asarray(f['q_target'],float)
            self.widths=np.asarray(f['gripper_command_width'],float)
            self.start_width=float(f['gripper_width'][0])
        self.times-=self.times[0]
        if len(self.times)<2 or np.max(np.diff(self.times))>.2:raise ValueError('episode too short or recording gap exceeds 200 ms')
        if self.config.get('teleop_controller')!='robolab_torque':raise ValueError('RoboLab torque recording required')
        if self.start_width<.080:raise ValueError('this replay entry requires an initially open gripper')
        self.speed=speed;self.duration=float(self.times[-1]/speed)
    def sample(self,elapsed):
        t=float(np.clip(elapsed*self.speed,0,self.times[-1]))
        target=np.array([np.interp(t,self.times,self.targets[:,j]) for j in range(7)])
        i=max(0,min(len(self.times)-1,int(np.searchsorted(self.times,t+1e-10,side='right')-1)))
        return target,float(self.widths[i])
    def summary(self):
        return dict(episode=str(self.path),frames=len(self.times),duration_s=self.duration,speed=self.speed,
                    source='recorded absolute q_target interpolated on original timestamps; commanded gripper width held until next sample')

class ReplayLeader:
    def __init__(self,trajectory):self.trajectory=trajectory;self.started=None
    def read(self):
        if self.started is None:return self.trajectory.q[0].copy(),self.trajectory.start_width
        return self.trajectory.sample(time.monotonic()-self.started)

class ReplayStartGate:
    """Discard start keys during homing; require a fresh r after reaching standby."""
    def __init__(self):self.ready=False
    def request(self,phase,keys,*,automatic=False):
        if phase!='standby':return False
        if not self.ready:
            self.ready=True
            return automatic
        return automatic or 'r' in keys

def source_digest(path):
    digest=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()

def no_physical_bridge():
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:args=(proc/'cmdline').read_bytes().split(b'\0')
        except (OSError,PermissionError):continue
        if args and Path(args[0].decode(errors='replace')).name=='pi05_franka_bridge' and b'--mock' not in args:
            raise RuntimeError('Existing physical bridge PID '+proc.name+'; exit its owning session first')

def real_preflight(config_path,run,calibration):
    if os.getpriority(os.PRIO_PROCESS,0)!=0:raise RuntimeError('Replay requires a normal nice=0 terminal')
    if not {12,13}.issubset(os.sched_getaffinity(0)):raise RuntimeError('Replay requires control CPUs 12/13 available')
    sys.path.insert(0,str(ROOT/'scripts'))
    from fix_fci_network_priority import discover
    network=discover()
    if network['policy']!=os.SCHED_FIFO or network['priority']!=50:
        raise RuntimeError('请先执行 sudo /usr/bin/python3 '+str(ROOT/'scripts/fix_fci_network_priority.py')+' --apply，再启动回放')
    from .gripper_teleop import unowned
    unowned(calibration['gripper_device'])
    with (run/'desk.log').open('w') as log:
        subprocess.run([sys.executable,str(ROOT/'scripts/check_desk_tool.py'),'--config',str(config_path),
                        '--output',str(run/'desk.json')],check=True,stdout=log,stderr=subprocess.STDOUT)
    desk=json.loads((run/'desk.json').read_text())
    if not desk['matches_expected_tool'] or desk['state']['robot_mode']!='Idle' or desk['state']['current_errors']:
        raise RuntimeError('Desk tool mismatch or robot not fault-free Idle; see '+str(run/'desk.json'))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode',required=True,type=Path)
    mode=parser.add_mutually_exclusive_group();mode.add_argument('--execute',action='store_true');mode.add_argument('--mock',action='store_true')
    parser.add_argument('--speed',type=float,default=1.)
    parser.add_argument('--confirmed',action='store_true',help='Operator has explicitly confirmed that objects and motion path are reset')
    args=parser.parse_args();os.chdir(ROOT)
    if args.execute and not sys.stdin.isatty():raise RuntimeError('真机回放需要可按 q 停止的交互终端')
    tr=Trajectory(args.episode,args.speed);print(json.dumps(tr.summary(),ensure_ascii=False),flush=True)
    if not args.execute and not args.mock:return 0
    config_path=ROOT/'configs/latency/responsive_recording/bridge.trial.json'
    calibration=json.loads(config_path.read_text());stored=tr.config.get('bridge_calibration')
    if stored is None or {k:v for k,v in stored.items() if k!='_comment'}!={k:v for k,v in calibration.items() if k!='_comment'}:
        raise RuntimeError('Recorded bridge calibration differs from current recording profile')
    # Also exclude A1/Stage-1 sessions, which use a different collection lock.
    model_lock=None
    if args.execute:
        model_lock_path=Path.home()/'.cache/pi05-stage1-8000/session.lock'
        model_lock_path.parent.mkdir(parents=True,exist_ok=True)
        model_lock=open(model_lock_path,'a');fcntl.flock(model_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    lock=open('/tmp/pi05-replay-mock.lock' if args.mock else '/tmp/pi05-robolab-trial-20261030.lock','a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise RuntimeError('采集或回放会话仍在运行；请先在原窗口按 q 正常退出。') from None
    if args.execute:no_physical_bridge()
    if args.execute and not args.confirmed:
        if not sys.stdin.isatty():raise RuntimeError('Interactive terminal required without --confirmed')
        answer=input(f'物品和回位路径已复位后按 Enter：先移动到记录起点，停稳后按 r 以 {tr.speed:g} 倍速回放一次；q 取消。\n')
        if answer.strip().lower()=='q':return 0
    run=ROOT/'reports/replays'/('replay_'+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]);run.mkdir(parents=True)
    (ROOT/'reports/replays/latest_run.txt').write_text(str(run)+'\n')
    if args.execute:real_preflight(config_path,run,calibration)
    if args.execute:no_physical_bridge()
    sock='/tmp/robolab-replay-'+uuid.uuid4().hex[:10]+'.sock';clear_stale_socket(sock)
    env=os.environ.copy();env.pop('LD_LIBRARY_PATH',None);env['PI05_CONTROL_CPU']='12'
    command=['taskset','-c','14-19',str(ROOT/'build/pi05_franka_bridge'),'--config',str(config_path),'--socket',sock]
    command+=['--mock'] if args.mock else ['--robot','172.16.0.40','--fault-log',str(run/'franka_fault.csv')]
    events=[];trace=[];session=bridge=proc=None;terminal=None;error=None;completed=False;cancelled=False
    previous_signals={}
    def interrupted(signum,frame):raise KeyboardInterrupt()
    for sig in (signal.SIGTERM,signal.SIGHUP):
        previous_signals[sig]=signal.signal(sig,interrupted)
    log=(run/'bridge.log').open('w');leader=ReplayLeader(tr)
    def announce(event,**data):
        events.append(dict(event=event,**data))
        if event=='homing':print('正在到达该条记录的起始位；到位后等待 r。q / Ctrl-C 停止。',flush=True)
        elif event=='recording':print(f'正在以 {tr.speed:g} 倍速回放本条动作；q / Ctrl-C 停止。',flush=True)
    try:
        proc=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT)
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            if proc.poll() is not None:raise RuntimeError('bridge exited; see '+str(run/'bridge.log'))
            try:bridge=Bridge(sock,mock=args.mock);break
            except (OSError,RuntimeError):time.sleep(.02)
        if bridge is None:raise RuntimeError('bridge startup timeout')
        cfg={**tr.config,'arm_home':tr.q[0].tolist(),'recording_enabled':False}
        cfg.pop('episode_keys',None)  # Replay uses its own explicit start/stop state machine.
        configure_runtime(cfg)
        session=CollectionSession(bridge,None,leader,cfg,run/'unused','replay',mock=args.mock,auto_home=True,announce=announce)
        if sys.stdin.isatty():
            terminal=termios.tcgetattr(sys.stdin);termios.tcflush(sys.stdin,termios.TCIFLUSH);tty.setcbreak(sys.stdin.fileno())
        keys=Keys();deadline=time.monotonic();end_sent=False;final_sample_sent=False;start_gate=ReplayStartGate()
        while True:
            received=keys.read(sys.stdin.fileno()) if terminal is not None else []
            if 'q' in received:cancelled=True;break
            phase=session.phase;inputs=[]
            if phase=='standby' and leader.started is None:
                # Use q[0] for takeover alignment; switch to recorded q_target only once recording starts.
                first_ready=not start_gate.ready
                if start_gate.request(phase,received,automatic=args.mock):inputs=['toggle']
                if first_ready and not args.mock:print('[到达记录起点｜保持中] 按 r 回放一次，q 退出。',flush=True)
            elif phase=='recording':
                elapsed=time.monotonic()-leader.started
                # Send the final interpolated joint/gripper sample before ending.
                if elapsed>=tr.duration:
                    if final_sample_sent:inputs=['toggle'];end_sent=True
                    else:final_sample_sent=True
                if time.monotonic()-deadline>.05:raise RuntimeError('replay control loop missed deadline by over 50 ms')
                state=bridge.last_state
                trace.append(dict(elapsed_s=elapsed,q=state['q'],reference=leader.read()[0].tolist(),gripper_width=state['gripper_width']))
            session.tick(inputs)
            if phase=='standby' and session.phase=='recording':leader.started=time.monotonic()
            if end_sent and session.completed_episodes:completed=True;break
            deadline+=.01
            if time.monotonic()-deadline>.01:deadline=time.monotonic()
            time.sleep(max(0,deadline-time.monotonic()))
    except KeyboardInterrupt:cancelled=True
    except BaseException as exc:error=f'{type(exc).__name__}: {exc}'
    finally:
        try:
            if session:session.close('replay complete' if completed else 'replay stopped')
            elif bridge:bridge.close()
        except Exception as exc:error=error or f'stop failed: {exc}'
        if terminal is not None:termios.tcsetattr(sys.stdin,termios.TCSADRAIN,terminal)
        if proc is not None:
            proc.terminate()
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
        log.close()
        report={**tr.summary(),'mock_bridge':args.mock,'completed':completed,'cancelled':cancelled,'error':error,
                'real_motion_requested':args.execute,'source_sha256':source_digest(tr.path),'ticks':len(trace),'report_dir':str(run)}
        (run/'result.json').write_text(json.dumps(report,indent=2)+'\n')
        (run/'events.json').write_text(json.dumps(events,indent=2)+'\n')
        (run/'trace.json').write_text(json.dumps(trace)+'\n')
        print(json.dumps(report,ensure_ascii=False),flush=True)
        lock.close()
        if model_lock is not None:model_lock.close()
        for sig,handler in previous_signals.items():signal.signal(sig,handler)
    return 1 if error else 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (RuntimeError,ValueError,OSError) as exc:raise SystemExit(str(exc))
