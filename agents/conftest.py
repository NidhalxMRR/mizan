"""Rend le dépôt importable quel que soit le répertoire d'appel de pytest.

pytest charge conftest.py avant le premier test, donc avant tout import de
`agents.chaine`. Sans cela, `pytest agents/` lancé depuis agents/ échoue à
l'import alors que le même test passe depuis la racine.
"""
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
LEGAL = RACINE / "packages" / "legal"

for _chemin in (RACINE, LEGAL):
    _p = str(_chemin)
    if _p not in sys.path:
        sys.path.insert(0, _p)
