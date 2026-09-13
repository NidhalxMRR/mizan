"""Rend le dépôt importable quel que soit le répertoire d'appel de pytest.

`from packages.risques import facture` suppose la racine du dépôt dans
sys.path. Lancé depuis ~/mizan c'est le cas ; lancé depuis packages/risques/
ça ne l'est pas. Même mécanique que api/conftest.py.
"""
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))
