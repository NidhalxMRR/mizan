"""Inscription, connexion et identité des comptes Mizan.

POST /comptes/inscription — crée un compte ; le rôle choisi apporte ses privilèges.
POST /comptes/connexion   — vérifie les identifiants et délivre un jeton signé.
GET  /comptes/moi         — ce que le serveur sait du porteur du jeton.
GET  /comptes/roles       — la matrice publique des rôles, pour l'écran d'inscription.
GET  /comptes/organisation — les comptes de MON organisation, et d'aucune autre.

Une règle gouverne ce routeur : ce que le client envoie ne décide de rien. Le
formulaire d'inscription transmet un rôle, jamais une liste de privilèges ;
c'est le serveur qui relit la matrice et attribue. Un client qui posterait un
champ « permissions » verrait son champ ignoré, parce qu'il n'existe pas dans
le schéma.

Pour monter ce routeur, une seule ligne dans api/main.py :

    from api.comptes import routeur as routeur_comptes
    app.include_router(routeur_comptes)
"""
from __future__ import annotations

import logging

from api import amorce  # noqa: F401  — installe sys.path avant les imports métier

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from packages.comptes import roles as matrice
from packages.comptes.garde import exige, verifier_jeton
from packages.comptes.jetons import (
    DUREE_PAR_DEFAUT_SECONDES,
    Session,
    signature_de_developpement,
)
from packages.comptes.registre import (
    BASE_PAR_DEFAUT,
    Compte,
    ConnexionRefusee,
    InscriptionRefusee,
    Registre,
)

logger = logging.getLogger("mizan.api.comptes")

routeur = APIRouter(tags=["comptes"])

# Une seule connexion SQLite pour le processus. Elle est ouverte au premier
# appel et non au chargement du module : importer `api.comptes` ne doit pas
# créer de fichier sur le disque, sans quoi la simple collecte des tests
# laisserait des traces.
_registre: Registre | None = None


def registre() -> Registre:
    """La connexion au registre, ouverte paresseusement.

    Déclarée comme fonction plutôt que comme variable pour qu'un test puisse la
    remplacer par `app.dependency_overrides` et travailler en mémoire.
    """
    global _registre
    if _registre is None:
        _registre = Registre(BASE_PAR_DEFAUT)
        if signature_de_developpement():
            # Visible dans les journaux au démarrage : une plateforme qui
            # manipule des créances ne doit pas passer en production sur une
            # clé de signature écrite dans le dépôt.
            logger.warning(
                "MIZAN_SECRET n'est pas définie : les jetons sont signés avec "
                "la clé de développement, qui est publique. À ne jamais "
                "utiliser en production."
            )
    return _registre


# ---------------------------------------------------------------------------
# Schémas
# ---------------------------------------------------------------------------

class DemandeInscription(BaseModel):
    """Ce que le formulaire d'inscription envoie — et rien de plus.

    Aucun champ « permissions » : les privilèges ne se demandent pas, ils
    découlent du rôle. C'est ce schéma qui rend l'escalade impossible, avant
    même que la moindre ligne de logique ne s'exécute.
    """
    email: str = Field(
        description="Adresse électronique du compte. Elle sert d'identifiant.",
        json_schema_extra={"example": "ahmed@menuiserie-sfax.tn"},
    )
    mot_de_passe: str = Field(
        min_length=1,
        description="Au moins 8 caractères. Il n'est jamais stocké en clair.",
    )
    role: str = Field(
        description="Un des cinq rôles : platform_admin, msme, accredited_pro, "
                    "court_clerk, huissier.",
        json_schema_extra={"example": "msme"},
    )
    nom_organisation: str = Field(
        description="L'entreprise, l'étude ou le tribunal auquel le compte "
                    "appartient. C'est elle qui cloisonne les dossiers.",
        json_schema_extra={"example": "Menuiserie Ahmed"},
    )


class DemandeConnexion(BaseModel):
    email: str
    mot_de_passe: str


class CompteRendu(BaseModel):
    """Le compte tel qu'il est renvoyé au client. Aucune empreinte n'y figure."""
    compte_id: str
    email: str
    organisation: str
    nom_organisation: str
    role: str
    role_libelle: str
    role_libelle_ar: str
    permissions: list[str]
    cree_le: int


class InscriptionFaite(BaseModel):
    compte: CompteRendu
    message: str


class ConnexionFaite(BaseModel):
    jeton: str = Field(
        description="À renvoyer dans l'en-tête « Authorization: Bearer <jeton> »."
    )
    expire_dans_secondes: int
    compte: CompteRendu
    avertissement_securite: str | None = Field(
        default=None,
        description="Présent uniquement si le serveur tourne encore sur la clé "
                    "de signature de développement.",
    )


class RoleRendu(BaseModel):
    role: str
    libelle: str
    libelle_ar: str
    permissions: list[str]
    permissions_libelles: list[str]


class MatriceRendue(BaseModel):
    roles: list[RoleRendu]
    note: str


def _rendre(compte: Compte) -> CompteRendu:
    return CompteRendu(
        compte_id=compte.compte_id,
        email=compte.email,
        organisation=compte.organisation,
        nom_organisation=compte.nom_organisation,
        role=compte.role,
        role_libelle=matrice.libelle_role(compte.role),
        role_libelle_ar=matrice.LIBELLES_AR.get(compte.role, compte.role),
        permissions=list(compte.permissions),
        cree_le=compte.cree_le,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@routeur.post("/comptes/inscription", response_model=InscriptionFaite,
              status_code=201,
              summary="Créer un compte — le rôle apporte ses privilèges")
def inscription(demande: DemandeInscription,
                reg: Registre = Depends(registre)) -> InscriptionFaite:
    """Crée le compte et lui attache d'emblée les privilèges de son rôle.

    Il n'existe pas de seconde étape. Un huissier inscrit ce matin peut
    signifier ce matin, et ne pourra jamais administrer les organisations : ce
    n'est pas une case qu'un administrateur aurait oublié de cocher, c'est la
    matrice des rôles qui en a décidé à la création.

    Refus possibles, tous en 400 avec un message lisible : rôle inexistant,
    adresse déjà prise, mot de passe trop court, organisation vide.
    """
    try:
        compte = reg.inscrire(demande.email, demande.mot_de_passe,
                              demande.role, demande.nom_organisation)
    except InscriptionRefusee as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("compte créé : %s, rôle %s, organisation %s",
                compte.compte_id, compte.role, compte.organisation)
    return InscriptionFaite(
        compte=_rendre(compte),
        message=(
            f"Compte créé pour « {compte.nom_organisation} » avec le rôle "
            f"« {matrice.libelle_role(compte.role)} ». Ce rôle donne accès à "
            f"{len(compte.permissions)} actions sur Mizan."
        ),
    )


@routeur.post("/comptes/connexion", response_model=ConnexionFaite,
              summary="Ouvrir une session et recevoir un jeton signé")
def connexion(demande: DemandeConnexion,
              reg: Registre = Depends(registre)) -> ConnexionFaite:
    """Vérifie les identifiants et délivre le jeton de session.

    Le refus est un 401 et le message est le même que l'adresse soit inconnue
    ou que le mot de passe soit faux. Deux messages distincts transformeraient
    ce formulaire en outil pour savoir qui est client de Mizan, donc qui est
    probablement en litige.
    """
    try:
        jeton, compte = reg.connexion(demande.email, demande.mot_de_passe)
    except ConnexionRefusee as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    return ConnexionFaite(
        jeton=jeton,
        expire_dans_secondes=DUREE_PAR_DEFAUT_SECONDES,
        compte=_rendre(compte),
        avertissement_securite=(
            "Ce serveur signe ses jetons avec la clé de développement. "
            "Définissez MIZAN_SECRET avant toute mise en production."
            if signature_de_developpement() else None
        ),
    )


@routeur.get("/comptes/moi", response_model=CompteRendu,
             summary="Le compte porteur du jeton")
def moi(session: Session = Depends(verifier_jeton),
        reg: Registre = Depends(registre)) -> CompteRendu:
    """Ce que le serveur sait de l'appelant.

    On relit le compte en base plutôt que de recopier le jeton : un compte
    désactivé depuis l'émission du jeton doit apparaître comme tel, et les
    privilèges renvoyés doivent être ceux de la matrice actuelle.
    """
    compte = reg.compte_par_id(session.compte_id)
    if compte is None:
        raise HTTPException(
            status_code=401,
            detail="Ce compte n'existe plus. Merci de vous reconnecter.",
        )
    return _rendre(compte)


@routeur.get("/comptes/roles", response_model=MatriceRendue,
             summary="Les cinq rôles et leurs privilèges")
def liste_des_roles() -> MatriceRendue:
    """La matrice, en accès libre : l'écran d'inscription en a besoin.

    Aucun secret ici. Savoir que seul l'huissier signifie est une règle de
    droit publiée au CPCC, pas une information à protéger.
    """
    return MatriceRendue(
        roles=[
            RoleRendu(
                role=r,
                libelle=matrice.LIBELLES[r],
                libelle_ar=matrice.LIBELLES_AR[r],
                permissions=list(matrice.PERMISSIONS[r]),
                permissions_libelles=[
                    matrice.libelle_permission(p) for p in matrice.PERMISSIONS[r]
                ],
            )
            for r in matrice.ROLES
        ],
        note="Les privilèges sont attribués automatiquement à la création du "
             "compte, d'après le rôle choisi. Ils ne se modifient pas compte "
             "par compte.",
    )


@routeur.get("/comptes/organisation", response_model=list[CompteRendu],
             summary="Les comptes de mon organisation")
def comptes_de_mon_organisation(
    session: Session = Depends(exige("manage_users")),
    reg: Registre = Depends(registre),
) -> list[CompteRendu]:
    """La liste est bornée à l'organisation du jeton, jamais à une autre.

    L'organisation n'est pas un paramètre de requête : elle est LUE dans le
    jeton signé. Un paramètre se change à la main dans l'URL ; un jeton signé,
    non. C'est ce choix, et pas un contrôle ajouté ensuite, qui rend la
    traversée entre organisations impossible.
    """
    comptes = reg.comptes_de_l_organisation(session.organisation)
    return [_rendre(c) for c in comptes]
