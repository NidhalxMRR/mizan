"""Amorçage des chemins d'import pour la chaîne d'agents.

Même contrainte que `api/amorce.py` : les modules métier vivent dans
`packages/` et s'importent entre eux de deux façons. `from packages.legal
import retrieve` suppose la racine du dépôt dans sys.path, mais `gate.py`
fait `from retrieve import tokenize`, ce qui suppose `packages/legal/`.

Les deux racines doivent donc être présentes AVANT le premier import métier.
Ce module est importé en tête de chaque agent.
"""
from __future__ import annotations

import sys
from pathlib import Path

# agents/amorce.py -> agents/ -> racine du dépôt
RACINE = Path(__file__).resolve().parents[1]
LEGAL = RACINE / "packages" / "legal"

for _chemin in (RACINE, LEGAL):
    _p = str(_chemin)
    if _p not in sys.path:
        sys.path.insert(0, _p)
