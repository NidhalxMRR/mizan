"""Couche d'identité cryptographique de Mizan : sceller, vérifier, attribuer.

Un document que personne ne peut attribuer ne vaut rien dans un litige.
Ce paquet rend chaque échange attribuable et non-répudiable — sous des
réserves qui sont documentées et jamais tues (voir `signature.py` et
`attribution.py`).

e-Houwiya (Mobile ID officiel tunisien, adossé à TunTrust/ANCE) est déclaré
NON IMPLÉMENTÉ : `FournisseurEHouwiya` lève une exception explicite. Voir
EHOUWIYA.md.
"""

from packages.identite.signature import (
    ALGORITHME_EMPREINTE,
    ALGORITHME_SIGNATURE,
    VERSION_SCELLE,
    DocumentVide,
    ErreurIdentite,
    FournisseurEHouwiya,
    FournisseurIdentite,
    FournisseurIndisponible,
    FournisseurLocal,
    RegistreDeCles,
    ResultatVerification,
    Scelle,
    ScelleInvalide,
    empreinte,
    sceller,
    verifier,
)
from packages.identite.attribution import (
    RESERVES_PERMANENTES,
    RapportAttribution,
    attribuer,
)

__all__ = [
    "ALGORITHME_EMPREINTE",
    "ALGORITHME_SIGNATURE",
    "VERSION_SCELLE",
    "DocumentVide",
    "ErreurIdentite",
    "FournisseurEHouwiya",
    "FournisseurIdentite",
    "FournisseurIndisponible",
    "FournisseurLocal",
    "RESERVES_PERMANENTES",
    "RapportAttribution",
    "RegistreDeCles",
    "ResultatVerification",
    "Scelle",
    "ScelleInvalide",
    "attribuer",
    "empreinte",
    "sceller",
    "verifier",
]
