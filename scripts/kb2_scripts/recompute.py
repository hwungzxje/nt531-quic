from pathlib import Path
import hashlib,json,tarfile,subprocess,sys
root=Path(__file__).resolve().parent.parent
(root/'logs').mkdir(exist_ok=True)
for item in json.loads((root/'data/archive_manifest.json').read_text()):
    p=root/'raw'/item['file']
    if hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:
        raise ValueError(f"Checksum mismatch: {p.name}")
    with tarfile.open(p) as t:
        t.extractall(root/'logs',filter='data')
subprocess.run([sys.executable,str(root/'scripts/analyze.py')],check=True)
print('Complete: results/data and results/figures')
