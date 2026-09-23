"""Locate the source snapshot both in a wheel and a Bundle checkout."""
from pathlib import Path
import sys


def activate():
    try:
        import canopy_runtime
        root = Path(canopy_runtime.__file__).resolve().parent
    except ImportError:
        root = Path(__file__).resolve().parent/'runtime'
    paths = [root, root/'apps/api', root/'tools/local', root/'cloud/azure/pipelines/databricks', root/'cloud/azure/pipelines/weekly_analysis']
    for path in reversed(paths):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    return root
