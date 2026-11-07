"""Assemble explicit files only; exclude unrelated data, environments and credentials."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

OVERLAY=Path(__file__).resolve().parent
SOURCE=Path.home()/'robolab-control-system'
ROOT=Path.home()/'replay153-delivery-20261105/franka_replay_153'
if ROOT.exists():raise SystemExit('Refusing to overwrite existing bundle '+str(ROOT))
ROOT.mkdir(parents=True)

def copy(src,dst):
    dst=ROOT/dst;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
def tree(src,dst):
    shutil.copytree(src,ROOT/dst,ignore=shutil.ignore_patterns('.git','__pycache__','*.pyc','build','.DS_Store','._*'))

for path in (SOURCE/'pi05_demo').glob('*.py'):copy(path,'pi05_demo/'+path.name)
for name in ['replay_session.sh','replay_episode.sh','check_desk_tool.py']:
    copy(SOURCE/'scripts'/name,'scripts/'+name)
copy(SOURCE/'data/raw/rlt_1105_fg_2_total153.h5','data/rlt_1105_fg_2_total153.h5')
for name in ['bridge.trial.json','collection.trial.json']:
    copy(SOURCE/'configs/latency/responsive_recording'/name,'configs/latency/responsive_recording/'+name)
tree(SOURCE/'cpp','cpp')
tree(SOURCE/'vendor/cppdeps','vendor/cppdeps')
tree(SOURCE/'vendor/robotiq_grippers','vendor/robotiq_grippers')
tree(Path.home()/'libfranka-0.9.0','sources/libfranka-0.9.0')
copy(SOURCE/'build/pi05_franka_bridge','native/bin/pi05_franka_bridge')
copy(Path.home()/'libfranka-0.9.0/build/examples/echo_robot_state','native/bin/echo_robot_state')
libraries={
 'libruckig.so':SOURCE/'build/_deps/ruckig-build/libruckig.so',
 'libgrippers_sdk.so':SOURCE/'build/robotiq_sdk/libgrippers_sdk.so',
 'libfranka.so.0.9':Path('/usr/local/lib/libfranka.so.0.9'),
 'libPocoNet.so.62':Path('/lib/x86_64-linux-gnu/libPocoNet.so.62'),
 'libPocoFoundation.so.62':Path('/lib/x86_64-linux-gnu/libPocoFoundation.so.62'),
 'libpcre.so.3':Path('/lib/x86_64-linux-gnu/libpcre.so.3'),
 'libz.so.1':Path('/lib/x86_64-linux-gnu/libz.so.1'),
}
for name,source in libraries.items():copy(source.resolve(),'native/lib/'+name)
for name in ['libpoconet62','libpcre3','zlib1g']:
    copy(Path('/usr/share/doc')/name/'copyright','licenses/'+name+'.copyright')
for source,name in [(Path.home()/'libfranka-0.9.0/LICENSE','libfranka.LICENSE'),
    (SOURCE/'vendor/robotiq_grippers/LICENSE','robotiq.LICENSE'),
    (SOURCE/'vendor/cppdeps/ruckig-0.15.3/LICENSE','ruckig.LICENSE')]:copy(source,'licenses/'+name)
for path in OVERLAY.iterdir():
    if path.name in ['build_bundle.py'] or not path.is_file():continue
    if path.name=='portable_host.py':copy(path,'pi05_demo/'+path.name)
    elif path.suffix=='.py':copy(path,'scripts/'+path.name)
    else:copy(path,path.name)
(ROOT/'requirements.txt').write_text('numpy==1.26.4\nh5py==3.12.1\nPillow==11.0.0\n')
(ROOT/'host.json').write_text(json.dumps(dict(robot_ip='172.16.0.40',network_interface=None,
    gripper_device=None,control_cpu=None,worker_cpu=None),indent=2)+'\n')

p=ROOT/'pi05_demo/replay.py';s=p.read_text()
s=s.replace('from .teleop_runtime import configure_runtime','from .teleop_runtime import configure_runtime\nfrom .portable_host import settings, require_station')
start=s.index("    if os.getpriority(os.PRIO_PROCESS,0)!=0:",s.index('def real_preflight'))
end=s.index('    from .gripper_teleop import unowned',start)
s=s[:start]+"    require_station()\n"+s[end:]
s=s.replace("'--output',str(run/'desk.json')],check=True", "'--output',str(run/'desk.json'),'--ip',settings()['robot_ip']],check=True")
s=s.replace("env['PI05_CONTROL_CPU']='12'", "env['PI05_CONTROL_CPU']=str(host['control_cpu']);env['LD_LIBRARY_PATH']=str(ROOT/'native/lib')")
s=s.replace("command=['taskset','-c','14-19',str(ROOT/'build/pi05_franka_bridge')", "command=['taskset','-c',host['background_cpus'],str(ROOT/'native/bin/pi05_franka_bridge')")
s=s.replace("['--robot','172.16.0.40','--fault-log'", "['--robot',host['robot_ip'],'--fault-log'")
s=s.replace("    if args.execute:real_preflight(config_path,run,calibration)",
    "    host=settings()\n    if host.get('gripper_device'):\n        calibration={**calibration,'gripper_device':host['gripper_device']}\n        config_path=run/'bridge.runtime.json'\n        config_path.write_text(json.dumps(calibration,indent=2))\n    if args.execute:real_preflight(config_path,run,calibration)")
s=s.replace("        configure_runtime(cfg)", "        cfg['teleop_main_cpu']=host['worker_cpu']\n        configure_runtime(cfg)")
assert "'14-19'" not in s and "ROOT/'build/pi05_franka_bridge'" not in s
compile(s,str(p),'exec');p.write_text(s)
p=ROOT/'pi05_demo/teleop_runtime.py';s=p.read_text().replace('cpu in (11, 12)', "cpu == int(os.environ.get('PI05_CONTROL_CPU', '-1'))")
p.write_text(s)
p=ROOT/'scripts/check_desk_tool.py';s=p.read_text().replace('"/home/heinrich/libfranka-0.9.0/build/examples/echo_robot_state"', 'str(ROOT/"native/bin/echo_robot_state")')
s=s.replace('result.stderr[-1500:]','(result.stderr or result.stdout)[-1500:]');p.write_text(s)
# The wrapper alone controls library paths; do not inherit arbitrary ROS libraries.
for name in ['replay_session.sh','replay_episode.sh']:
    p=ROOT/'scripts'/name;s=p.read_text().replace('exec env -u LD_LIBRARY_PATH', 'export LD_LIBRARY_PATH="$REPLAY_ROOT/native/lib"\nexec env')
    p.write_text(s)
# Rebuild using bundled Ruckig/JSON sources, avoiding network FetchContent.
p=ROOT/'cpp/bridge/CMakeLists.txt';s=p.read_text()
start=s.index('if(PI05_FETCH_DEPS)');end=s.index('find_package(Threads REQUIRED)',start)
s=s[:start]+'''set(BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(BUILD_PYTHON_MODULE OFF CACHE BOOL "" FORCE)
set(BUILD_CLOUD_CLIENT OFF CACHE BOOL "" FORCE)
add_subdirectory(${CMAKE_CURRENT_SOURCE_DIR}/../../vendor/cppdeps/ruckig-0.15.3 ${CMAKE_CURRENT_BINARY_DIR}/ruckig)
add_subdirectory(${CMAKE_CURRENT_SOURCE_DIR}/../../vendor/cppdeps/json-3.11.3 ${CMAKE_CURRENT_BINARY_DIR}/json)
'''+s[end:];p.write_text(s)
for name in ['test_replay.py','test_replay_menu.py']:
    copy(SOURCE/'tests'/name,'tests/'+name)
for p in ROOT.glob('*.sh'):p.chmod(0o755)
def digest(p):
    d=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):d.update(block)
    return d.hexdigest()
manifest=dict(episode='data/rlt_1105_fg_2_total153.h5',collection_total_index=153,
    collector='fg',frames=396,task_description_by_operator='flower arrangement',
    original_h5_task_text_preserved=True,platform='Ubuntu 24.04 x86_64 PREEMPT_RT / Panda / Robotiq 2F-85',
    native_build_origin='Ubuntu 20.04 x86_64; libfranka 0.9.0',
    robot_motion_during_packaging=False,sha256={})
for p in ROOT.rglob('*'):
    if p.is_file() and p.name!='host.json':manifest['sha256'][str(p.relative_to(ROOT))]=digest(p)
original=digest(SOURCE/'data/raw/rlt_1105_fg_2_total153.h5')
assert original==manifest['sha256'][manifest['episode']]
(ROOT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(dict(root=str(ROOT),files=len(manifest['sha256']),episode_sha256=original),ensure_ascii=False))
