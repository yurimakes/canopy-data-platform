"""Build in a fresh directory so removed modules cannot leak into the wheel."""
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
folder=Path(__file__).resolve().parent
shared=folder.parent/'_shared'
(folder/'dist').mkdir(exist_ok=True)
with TemporaryDirectory(prefix='canopy-downstream-build-') as temporary:
    subprocess.run([sys.executable,'setup.py','build','--build-base',str(Path(temporary)/'build'),
                    'bdist_wheel','--bdist-dir',str(Path(temporary)/'wheel'),
                    '--dist-dir',str(folder/'dist')],cwd=shared,check=True)
