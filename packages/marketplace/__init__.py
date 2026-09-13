"""
Place de marché des professionnels accrédités de MIZAN.

Sans conciliateur, sans médiateur, sans arbitre et sans avocat, le module de
règlement amiable n'a pas d'opérateurs : il n'y a personne pour conduire la
procédure. Ce paquet est donc l'annuaire qui permet aux parties de trouver le
bon professionnel, et rien d'autre.

Règle absolue, rappelée dans chaque sortie du moteur :
l'IA RECOMMANDE, les parties CHOISISSENT. Aucune désignation d'office.
"""

from packages.marketplace.annuaire import (
    Annuaire,
    Avis,
    ConflitInterets,
    Dossier,
    Litige,
    NotationRefusee,
    ProfilInvalide,
    Professionnel,
    Proposition,
    Recommandation,
)

__all__ = [
    "Annuaire",
    "Avis",
    "ConflitInterets",
    "Dossier",
    "Litige",
    "NotationRefusee",
    "ProfilInvalide",
    "Professionnel",
    "Proposition",
    "Recommandation",
]
