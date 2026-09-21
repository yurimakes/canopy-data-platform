"""Verify that the imported runtime and model assets match the source release."""
from pathlib import Path
import hashlib
import json
root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'source-manifest.json').read_text())['sha256']
for name,expected in manifest.items():
    source=root/'runtime'/name
    if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=expected:
        raise SystemExit('Source snapshot differs: '+name)
print(f'Verified {len(manifest)} source/model/reference files')
