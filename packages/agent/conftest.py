"""Rend le dépôt importable quel que soit le répertoire d'appel de pytest.

Même mécanique que `packages/risques/conftest.py` : lancé depuis la racine,
`from packages.agent import ...` fonctionne ; lancé depuis ce dossier, non.
On ajoute en plus `packages/legal/`, parce que la garde d'abstention
(`gate.py`) s'importe par son nom court.
"""
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
LEGAL = RACINE / "packages" / "legal"

for _chemin in (RACINE, LEGAL):
    if str(_chemin) not in sys.path:
        sys.path.insert(0, str(_chemin))
