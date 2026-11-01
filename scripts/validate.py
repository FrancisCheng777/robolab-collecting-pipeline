"""Hardware-free unit/C++/mock validation for this standalone repository."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-export', action='store_true',
                        help='Also validate LeRobot export using LEROBOT_PYTHON or .venv-lerobot')
    args = parser.parse_args()
    reports = ROOT / 'reports'
    reports.mkdir(exist_ok=True)
    env = {**os.environ, 'PYTHONPATH': str(ROOT)}
    summary = {'hardware_motion': False, 'checks': {}}

    def run(name, command, cwd=ROOT):
        path = reports / f'validation_{name}.log'
        with path.open('w') as log:
            result = subprocess.run(command, cwd=cwd, env=env,
                                    stdout=log, stderr=subprocess.STDOUT, timeout=300)
        summary['checks'][name] = {'exit_code': result.returncode, 'log': str(path)}
        if result.returncode:
            raise RuntimeError(f'{name} failed; see {path}')
        print(f'PASS {name}', flush=True)

    run('unit', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-q'])
    if not (ROOT / 'build/CTestTestfile.cmake').exists():
        raise RuntimeError('Build the C++ targets before running validation')
    run('cpp', ['ctest', '--output-on-failure'], cwd=ROOT / 'build')
    run('collection', [sys.executable, str(ROOT / 'scripts/smoke.py')])
    if args.with_export:
        smoke = json.loads((reports / 'latest_smoke.json').read_text())
        data = Path(smoke['run'])
        run('export', [str(ROOT / 'scripts/export.sh'), '--input', str(data / 'raw'),
                       '--output', str(data / 'dataset'), '--allow-mock',
                       '--validation-session', 'smoke_validation'])
    (reports / 'validation.json').write_text(json.dumps(summary, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
