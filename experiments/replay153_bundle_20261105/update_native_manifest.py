import json
from pathlib import Path
from verify_bundle import digest
root=Path(__file__).resolve().parents[1]
p=root/'manifest.json'
m=json.loads(p.read_text())
for key in list(m['sha256']):
    if key.startswith(('native/bin/','native/lib/')):del m['sha256'][key]
for directory in ['native/bin','native/lib']:
    for path in (root/directory).iterdir():
        if path.is_file():m['sha256'][str(path.relative_to(root))]=digest(path)
m['native_rebuilt_on_recipient']=True
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
