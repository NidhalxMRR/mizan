"""Amorçage des chemins d'import.

Les modules métier vivent dans `packages/` et s'importent entre eux de deux
façons : `from packages.legal import ...` depuis la racine, mais aussi
`from retrieve import tokenize` à l'intérieur de `gate.py`. L'API doit donc
présenter les deux racines avant le premier import métier, sinon `gate.py`
lève ModuleNotFoundError.

Ce fichier ne fait que cela, et il est importé en premier par `main.py`.
"""
from __future__ import annotations

import sys
from pathlib import Path

# api/amorce.py -> api/ -> racine du dépôt
RACINE = Path(__file__).resolve().parents[1]
LEGAL = RACINE / "packages" / "legal"

for chemin in (RACINE, LEGAL):
    p = str(chemin)
    if p not in sys.path:
        sys.path.insert(0, p)
