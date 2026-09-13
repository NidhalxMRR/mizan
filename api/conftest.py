"""Rend le dépôt importable quel que soit le répertoire d'appel de pytest.

`from api import amorce` suppose la racine du dépôt dans sys.path. Lancé
depuis ~/mizan c'est le cas ; lancé depuis api/ ça ne l'est pas. conftest.py
est chargé par pytest avant le premier test, donc avant tout import de
`api.main`.
"""
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))
