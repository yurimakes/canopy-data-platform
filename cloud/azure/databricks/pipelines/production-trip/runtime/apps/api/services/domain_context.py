"""Request-scoped storage boundary for the shared journey/community domain."""
from contextvars import ContextVar
from contextlib import contextmanager

backend=ContextVar('canopy_domain_backend',default=None)

@contextmanager
def use_backend(value):
    token=backend.set(value)
    try:yield value
    finally:backend.reset(token)

def read_json(path,default=None):
    current=backend.get()
    if current is not None:return current.read_json(path,default)
    import json
    from pathlib import Path
    path=Path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
