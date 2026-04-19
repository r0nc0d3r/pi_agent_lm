"""Fake litert_lm so tests import `main` without native wheel."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

_fake = MagicMock()
_fake.LogSeverity = MagicMock(ERROR=0)
_fake.Backend = MagicMock(CPU=0)
_fake.set_min_log_severity = lambda *_a, **_k: None
_fake.Engine = MagicMock
sys.modules.setdefault("litert_lm", _fake)
