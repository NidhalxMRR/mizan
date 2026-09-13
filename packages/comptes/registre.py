"""Le registre des comptes : inscription, connexion, cloisonnement.

C'est ici que se tient la promesse centrale du module : à l'inscription, le
compte reçoit AUTOMATIQUEMENT les privilèges de son rôle. Il n'existe pas de
seconde étape où un administrateur cocherait des cases. Le rôle EST le jeu de
privilèges, et la matrice de `roles.py` en est la seule source.

Le stockage est un fichier SQLite, par le module `sqlite3` de la bibliothèque
standard. Un dictionnaire en mémoire aurait été plus court à écrire, mais les
comptes s'évaporeraient au redémarrage : le matin de la démonstration, il
faudrait réinscrire tout le monde. Un fichier survit, et se relit avec
n'importe quel outil, ce qui rend le test « le mot de passe n'est nulle part
en clair » vérifiable pour de bon.

Sur le cloisonnement multi-organisations : chaque compte appartient à une
organisation, et chaque lecture qui pourrait traverser cette frontière exige
l'organisation en argument plutôt que de la déduire. Passer l'organisation
explicitement rend l'oubli visible à la lecture du code ; la déduire l'aurait
rendu invisible.
"""
from __future__ import annotations

import re
import secrets
import sqlite3
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from packages.comptes import empreintes
from packages.comptes.jetons import (
    DUREE_PAR_DEFAUT_SECONDES,
    Session,
    creer_jeton,
)
from packages.comptes.roles import (
    RoleInconnu,
    libelle_role,
    permissions_du_role,
    verifier_role,
)

# Le dossier est hors de `packages/` : ce sont des données d'exploitation, pas
# du code. Il est créé à la volée pour qu'un `git clone` suivi d'un lancement
# fonctionne sans étape d'installation.
DOSSIER_DONNEES = Path(__file__).resolve().parents[2] / ".donnees"
BASE_PAR_DEFAUT = DOSSIER_DONNEES / "comptes.db"

# Volontairement permissif : il s'agit d'écarter les saisies manifestement
# fautives, pas de prétendre valider une adresse. Seul un courriel envoyé
# prouve qu'une adresse existe, et Mizan n'en envoie pas à ce stade.
_FORME_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class InscriptionRefusee(ValueError):
    """L'inscription ne peut pas aboutir, et la raison est explicable."""


class ConnexionRefusee(ValueError):
    """Les identifiants présentés ne permettent pas d'ouvrir une session."""


class AccesRefuse(PermissionError):
    """Le compte existe, mais n'a pas le droit de faire ce qu'il demande."""


@dataclass(frozen=True)
class Compte:
    """Un compte tel qu'il est relu depuis la base.

    L'empreinte du mot de passe ne figure pas dans cette structure. Un objet
    qui la transporterait finirait tôt ou tard sérialisé dans une réponse
    d'API ou dans un journal. Elle reste dans la base, et ne sort que le temps
    d'une vérification, à l'intérieur de `connexion`.
    """
    compte_id: str
    email: str
    organisation: str
    nom_organisation: str
    role: str
    permissions: tuple[str, ...]
    cree_le: int
    actif: bool = True

    @property
    def libelle_role(self) -> str:
        return libelle_role(self.role)

    def en_clair(self) -> dict[str, object]:
        return {
            "compte_id": self.compte_id,
            "email": self.email,
            "organisation": self.organisation,
            "nom_organisation": self.nom_organisation,
            "role": self.role,
            "role_libelle": self.libelle_role,
            "permissions": list(self.permissions),
            "cree_le": self.cree_le,
            "actif": self.actif,
        }


def normaliser_email(email: str) -> str:
    """Ramène une adresse à sa forme de comparaison, et la valide.

    La casse et les espaces de bord sont retirés parce que « Ahmed@X.tn » et
    « ahmed@x.tn » désignent la même personne : sans cette normalisation, la
    règle « un seul compte par adresse » se contournerait avec une majuscule.
    """
    if not isinstance(email, str) or not email.strip():
        raise InscriptionRefusee(
            "L'adresse électronique est vide. Elle est nécessaire pour créer "
            "le compte."
        )
    propre = unicodedata.normalize("NFKC", email).strip().lower()
    if not _FORME_EMAIL.match(propre):
        raise InscriptionRefusee(
            f"L'adresse « {email.strip()} » ne ressemble pas à une adresse "
            "électronique. Exemple attendu : nom@entreprise.tn"
        )
    return propre


def identifiant_organisation(nom: str) -> str:
    """Fabrique un identifiant stable à partir du nom de l'organisation.

    « Menuiserie Ahmed » et « menuiserie  ahmed » doivent rejoindre la même
    organisation, sinon deux collègues de la même entreprise se retrouveraient
    cloisonnés l'un de l'autre et aucun ne verrait le dossier commun. Les
    accents sont dépliés pour que « Société » et « Societe » ne divergent pas.
    """
    if not isinstance(nom, str) or not nom.strip():
        raise InscriptionRefusee(
            "Le nom de l'organisation est vide. Chaque compte Mizan appartient "
            "à une organisation : c'est elle qui cloisonne les dossiers."
        )
    deplie = unicodedata.normalize("NFKD", nom.strip().lower())
    sans_accents = "".join(c for c in deplie if not unicodedata.combining(c))
    identifiant = re.sub(r"[^a-z0-9]+", "-", sans_accents).strip("-")
    if not identifiant:
        # Un nom entièrement en arabe est légitime : il ne produit simplement
        # aucun caractère latin. On lui donne un identifiant opaque plutôt que
        # de refuser l'inscription.
        identifiant = "org-" + secrets.token_hex(4)
    return identifiant[:64]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS comptes (
    compte_id         TEXT PRIMARY KEY,
    email             TEXT NOT NULL UNIQUE,
    empreinte         TEXT NOT NULL,
    organisation      TEXT NOT NULL,
    nom_organisation  TEXT NOT NULL DEFAULT '',
    role              TEXT NOT NULL,
    permissions       TEXT NOT NULL DEFAULT '',
    cree_le           INTEGER NOT NULL,
    actif             INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_comptes_organisation ON comptes(organisation);
"""


class Registre:
    """Le registre des comptes, adossé à un fichier SQLite.

    Une instance ouvre sa propre connexion. Les tests passent
    `chemin=":memory:"` pour rester sans trace, l'API passe le fichier de
    `.donnees/`.
    """

    def __init__(self, chemin: str | Path | None = None) -> None:
        self.chemin = Path(chemin) if chemin not in (None, ":memory:") else chemin
        if self.chemin not in (None, ":memory:"):
            self.chemin.parent.mkdir(parents=True, exist_ok=True)
            cible = str(self.chemin)
        else:
            cible = ":memory:"
            self.chemin = cible
        self._cx = sqlite3.connect(cible, check_same_thread=False)
        self._cx.row_factory = sqlite3.Row
        # Les contraintes de clé étrangère et l'unicité de l'adresse sont
        # appliquées par SQLite lui-même : c'est la seule garantie qui tienne
        # si deux requêtes d'inscription arrivent en même temps.
        self._cx.execute("PRAGMA foreign_keys = ON")
        self._cx.executescript(_SCHEMA)
        self._cx.commit()

    def fermer(self) -> None:
        self._cx.close()

    def __enter__(self) -> "Registre":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.fermer()

    # -- Inscription --------------------------------------------------------

    def inscrire(
        self,
        email: str,
        mot_de_passe: str,
        role: str,
        nom_organisation: str,
        *,
        maintenant: int | None = None,
    ) -> Compte:
        """Crée un compte et lui attache d'emblée les privilèges de son rôle.

        Les contrôles sont faits dans l'ordre où ils coûtent le moins cher :
        rôle, adresse, organisation, puis seulement le scellement du mot de
        passe, qui prend un dixième de seconde. Inutile de faire travailler la
        machine pour une inscription qu'on va refuser de toute façon.
        """
        try:
            verifier_role(role)
        except RoleInconnu as exc:
            raise InscriptionRefusee(str(exc)) from exc

        adresse = normaliser_email(email)
        organisation = identifiant_organisation(nom_organisation)

        try:
            empreinte = empreintes.sceller(mot_de_passe)
        except empreintes.MotDePasseInvalide as exc:
            raise InscriptionRefusee(str(exc)) from exc

        privileges = permissions_du_role(role)
        compte_id = "cpt-" + secrets.token_hex(8)
        instant = int(time.time()) if maintenant is None else int(maintenant)

        try:
            self._cx.execute(
                "INSERT INTO comptes (compte_id, email, empreinte, organisation,"
                " nom_organisation, role, permissions, cree_le, actif)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
                (compte_id, adresse, empreinte, organisation,
                 nom_organisation.strip(), role, ",".join(privileges), instant),
            )
            self._cx.commit()
        except sqlite3.IntegrityError as exc:
            # L'unicité vient de la base, pas d'un SELECT préalable. Un contrôle
            # « est-ce que cette adresse existe ? » suivi d'un INSERT laisse une
            # fenêtre où deux inscriptions simultanées passent toutes les deux.
            self._cx.rollback()
            raise InscriptionRefusee(
                f"Un compte existe déjà pour l'adresse « {adresse} ». "
                "Utilisez la page de connexion, ou choisissez une autre adresse."
            ) from exc

        return Compte(
            compte_id=compte_id, email=adresse, organisation=organisation,
            nom_organisation=nom_organisation.strip(), role=role,
            permissions=privileges, cree_le=instant, actif=True,
        )

    # -- Connexion ----------------------------------------------------------

    def connexion(
        self,
        email: str,
        mot_de_passe: str,
        *,
        duree_secondes: int = DUREE_PAR_DEFAUT_SECONDES,
        maintenant: int | None = None,
    ) -> tuple[str, Compte]:
        """Vérifie les identifiants et délivre un jeton de session signé.

        Le même message répond à « cette adresse n'existe pas » et à « le mot
        de passe est faux ». Distinguer les deux transformerait le formulaire
        de connexion en outil pour savoir qui est client de Mizan — donc qui
        est en litige. Dans une plateforme judiciaire, c'est une information
        sensible en soi.
        """
        refus = ConnexionRefusee(
            "Adresse électronique ou mot de passe incorrect."
        )
        try:
            adresse = normaliser_email(email)
        except InscriptionRefusee:
            raise refus from None

        ligne = self._cx.execute(
            "SELECT * FROM comptes WHERE email = ?", (adresse,)
        ).fetchone()

        if ligne is None:
            # On calcule quand même une empreinte sur une valeur factice. Sans
            # cela, un refus instantané signalerait « cette adresse est
            # inconnue » alors qu'un refus lent signalerait « l'adresse existe,
            # le mot de passe est faux » : le temps de réponse trahirait ce que
            # le message refuse de dire.
            empreintes.correspond(
                mot_de_passe if isinstance(mot_de_passe, str) else "",
                empreintes.sceller("mot-de-passe-factice-anti-chronometrage"),
            )
            raise refus

        if not empreintes.correspond(mot_de_passe, ligne["empreinte"]):
            raise refus

        if not ligne["actif"]:
            raise ConnexionRefusee(
                "Ce compte a été désactivé. Contactez l'administrateur de "
                "votre organisation."
            )

        compte = self._depuis_ligne(ligne)
        jeton = creer_jeton(
            compte.compte_id, compte.email, compte.organisation, compte.role,
            nom_organisation=compte.nom_organisation,
            duree_secondes=duree_secondes, maintenant=maintenant,
        )
        return jeton, compte

    # -- Lectures cloisonnées ----------------------------------------------

    def compte_par_id(self, compte_id: str) -> Compte | None:
        ligne = self._cx.execute(
            "SELECT * FROM comptes WHERE compte_id = ?", (compte_id,)
        ).fetchone()
        return self._depuis_ligne(ligne) if ligne else None

    def comptes_de_l_organisation(self, organisation: str) -> list[Compte]:
        """Les comptes d'une organisation, et rien d'autre.

        L'organisation est un argument obligatoire, jamais une valeur par
        défaut. Il n'existe volontairement pas de `tous_les_comptes()` : une
        fonction qui renvoie tout finit toujours par être appelée depuis une
        route où le filtrage par organisation a été oublié.
        """
        lignes = self._cx.execute(
            "SELECT * FROM comptes WHERE organisation = ? ORDER BY cree_le",
            (organisation,),
        ).fetchall()
        return [self._depuis_ligne(l) for l in lignes]

    def _depuis_ligne(self, ligne: sqlite3.Row) -> Compte:
        # Les privilèges sont relus depuis la matrice plutôt que depuis la
        # colonne. La colonne garde la trace de ce qui a été attribué à la
        # création — utile pour un audit — mais si la matrice évolue, c'est
        # elle qui fait foi. Une base retouchée à la main ne peut donc pas
        # accorder un privilège que le rôle ne porte pas.
        return Compte(
            compte_id=ligne["compte_id"],
            email=ligne["email"],
            organisation=ligne["organisation"],
            nom_organisation=ligne["nom_organisation"],
            role=ligne["role"],
            permissions=permissions_du_role(ligne["role"]),
            cree_le=int(ligne["cree_le"]),
            actif=bool(ligne["actif"]),
        )


def verifier_acces_organisation(session: Session, organisation: str) -> None:
    """Refuse si la session tente d'agir au nom d'une autre organisation.

    Le message ne confirme PAS que l'organisation visée existe. Répondre
    « cette organisation n'est pas la vôtre » suffit ; répondre « le dossier
    de la société X ne vous appartient pas » apprendrait à l'appelant que la
    société X est cliente de Mizan, donc probablement en litige.
    """
    if not session.meme_organisation(organisation):
        raise AccesRefuse(
            "Ce dossier appartient à une autre organisation. Votre compte "
            f"n'a accès qu'aux dossiers de « {session.nom_organisation or session.organisation} »."
        )
