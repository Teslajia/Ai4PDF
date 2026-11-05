"""Keep installed resources separate from writable, per-user application data."""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path


def configuration_root(resource_root, *, frozen=None, environ=None):
    environ = os.environ if environ is None else environ
    frozen = getattr(sys, 'frozen', False) if frozen is None else frozen
    override = environ.get('AI4PDF_HOME')
    if override:
        return Path(override).expanduser().resolve()
    if frozen:
        base = Path(environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
        return base / 'Ai4PDF'
    return Path(resource_root)


def instance_id(config_root):
    # Compare instances without exposing the user's absolute filesystem paths.
    normalized = os.path.normcase(str(Path(config_root).resolve()))
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:24]
