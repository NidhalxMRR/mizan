"""Amorçage des chemins d'import, pour ce paquet uniquement.

Le même besoin que `api/amorce.py`, et pour la même raison : `packages/legal/
gate.py` s'importe lui-même par `from retrieve import tokenize`, ce qui exige
que `packages/legal/` figure dans le chemin de recherche en plus de la racine
du dépôt.

On duplique ces quelques lignes plutôt que d'importer `api.amorce` : le
cerveau de l'agent doit rester utilisable depuis un script en ligne de
commande, sans que rien du serveur web ne soit chargé.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# packages/agent/amorce.py -> packages/agent/ -> packages/ -> racine
RACINE = Path(__file__).resolve().parents[2]
LEGAL = RACINE / "packages" / "legal"

for _chemin in (RACINE, LEGAL):
    _p = str(_chemin)
    if _p not in sys.path:
        sys.path.insert(0, _p)


def charger_configuration() -> None:
    """Lit `.env` à la racine et pose ce qui n'est pas déjà dans l'environnement.

    POURQUOI L'AGENT LE FAIT ALORS QUE PERSONNE D'AUTRE NE LE FAIT.
    Le fichier `.env` du dépôt indique où joindre le modèle hébergé, mais aucun
    module ne le lit : le serveur est lancé par un script qui exporte ces
    variables lui-même. Un script en ligne de commande — la démonstration, un
    essai d'atelier — n'en bénéficie pas, et le client bascule alors sur un
    modèle local absent. La réponse reste juste, car le moteur ne dépend pas du
    modèle, mais elle arrive sans reformulation, ce qui donne à tort
    l'impression que le service est en panne.

    On ne fait que COMPLÉTER l'environnement : une variable déjà posée n'est
    jamais écrasée. Ce qui vient du système d'exploitation l'emporte toujours
    sur ce qui vient d'un fichier du dépôt — sans quoi il deviendrait
    impossible de pointer ailleurs le temps d'un essai.

    Écrit sans dépendance : `python-dotenv` ferait la même chose, et la
    consigne du projet est de n'en ajouter aucune.
    """
    fichier = RACINE / ".env"
    try:
        lignes = fichier.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        # Pas de fichier, ou illisible : ce n'est pas une erreur. La
        # configuration peut parfaitement venir de l'environnement seul.
        return

    for ligne in lignes:
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, _, valeur = ligne.partition("=")
        cle = cle.strip()
        if cle.startswith("export "):
            cle = cle[len("export "):].strip()
        valeur = valeur.strip().strip("'\"")
        if cle and cle not in os.environ:
            os.environ[cle] = valeur


charger_configuration()
