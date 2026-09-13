"""Met packages/ecma et packages/legal sur le chemin d'import pour pytest.

Le projet n'installe pas ses paquets : `packages/legal/gate.py` fait
`from retrieve import tokenize`, donc le répertoire doit être sur sys.path.
On aligne ici la collecte de pytest sur ce que fait le module lui-même, plutôt
que de réécrire les imports de packages/legal — qui appartient à un autre
périmètre.
"""
import pathlib
import sys

_ICI = pathlib.Path(__file__).resolve().parent
_RACINE = _ICI.parents[1]

for chemin in (_ICI, _RACINE / 'packages' / 'legal', _RACINE):
    if str(chemin) not in sys.path:
        sys.path.insert(0, str(chemin))
