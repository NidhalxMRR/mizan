"""Comptes, rôles et privilèges de Mizan.

Le module répond à une exigence simple à énoncer et facile à trahir : au
moment où un compte est créé, il reçoit les privilèges de son rôle, et il n'en
reçoit jamais d'autres. Pas de seconde étape d'attribution, pas de case à
cocher, pas de privilège accordé compte par compte.

Quatre fichiers, quatre responsabilités :

  roles.py       la matrice des cinq rôles et de leurs privilèges, jumelle de
                 `web/lib/auth.ts` — un test échoue si les deux divergent ;
  empreintes.py  le scellement des mots de passe (scrypt, sel aléatoire) ;
  jetons.py      les jetons de session signés HMAC-SHA256, avec expiration ;
  registre.py    l'inscription, la connexion et le cloisonnement par
                 organisation, sur un fichier SQLite ;
  garde.py       `verifier_jeton` et `exige(privilège)` pour les routes.

Aucune dépendance hors de la bibliothèque standard, sauf `garde.py` qui parle
à FastAPI parce que c'est son rôle.
"""

from packages.comptes.empreintes import (
    MotDePasseInvalide,
    correspond,
    sceller,
)
from packages.comptes.jetons import (
    DUREE_PAR_DEFAUT_SECONDES,
    JetonInvalide,
    Session,
    creer_jeton,
    lire_jeton,
    signature_de_developpement,
)
from packages.comptes.registre import (
    AccesRefuse,
    BASE_PAR_DEFAUT,
    Compte,
    ConnexionRefusee,
    InscriptionRefusee,
    Registre,
    identifiant_organisation,
    normaliser_email,
    verifier_acces_organisation,
)
from packages.comptes.roles import (
    LIBELLES,
    LIBELLES_AR,
    PERMISSIONS,
    ROLES,
    RoleInconnu,
    libelle_permission,
    libelle_role,
    permissions_du_role,
    peut,
    verifier_role,
)

__all__ = [
    "AccesRefuse",
    "BASE_PAR_DEFAUT",
    "Compte",
    "ConnexionRefusee",
    "DUREE_PAR_DEFAUT_SECONDES",
    "InscriptionRefusee",
    "JetonInvalide",
    "LIBELLES",
    "LIBELLES_AR",
    "MotDePasseInvalide",
    "PERMISSIONS",
    "ROLES",
    "Registre",
    "RoleInconnu",
    "Session",
    "correspond",
    "creer_jeton",
    "identifiant_organisation",
    "libelle_permission",
    "libelle_role",
    "lire_jeton",
    "normaliser_email",
    "permissions_du_role",
    "peut",
    "sceller",
    "signature_de_developpement",
    "verifier_acces_organisation",
    "verifier_role",
]
