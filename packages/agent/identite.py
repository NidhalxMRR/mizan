"""Qui agit, au nom de qui, et avec quels droits.

C'est le fichier le plus important du paquet, et le plus court. Tout ce que
l'agent est autorisé à faire découle d'un seul objet, `Identite`, construit à
partir du jeton de session — jamais à partir de la demande de l'utilisateur,
et jamais à partir de ce que le modèle de langage a cru comprendre.

LA RÈGLE DE CLOISONNEMENT, ET POURQUOI ELLE EST ÉCRITE ICI
-----------------------------------------------------------
Deux entreprises en litige peuvent l'une et l'autre être clientes de Mizan.
Que l'agent de l'une puisse lire le dossier de l'autre ne serait pas un défaut
d'affichage : ce serait une violation du secret des affaires, et la plateforme
serait inutilisable devant un tribunal de commerce.

Le cloisonnement tient donc à une décision de conception : l'organisation
n'est PAS un paramètre d'outil. Aucun outil n'accepte d'organisation en
entrée ; tous lisent celle de l'`Identite`. Un utilisateur peut écrire
« consulte les dossiers de l'entreprise Untel » autant qu'il le voudra, il n'y
a pas de chemin de code par lequel cette phrase devienne une organisation.

LE REFUS NE DOIT RIEN APPRENDRE
-------------------------------
Quand quelqu'un demande les dossiers d'une autre organisation, la réponse ne
dit pas « cette organisation existe mais vous n'y avez pas accès » — elle ne
dit pas non plus « elle n'existe pas ». Elle dit que l'agent ne travaille que
sur le périmètre de l'organisation de l'appelant, et elle s'arrête là. Un
message d'erreur qui distingue les deux cas est un annuaire d'entreprises
clientes offert à qui prend la peine de poser la question.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from packages.comptes.roles import (
    LIBELLES_PERMISSIONS,
    PERMISSIONS,
    libelle_permission,
    libelle_role,
)


class IdentiteInvalide(ValueError):
    """On a tenté de faire agir l'agent sans identité exploitable."""


# --- Ce que la loi oppose à un rôle, en toutes lettres ----------------------
# Un refus d'accès sur une plateforme judiciaire n'est pas un incident
# technique : c'est une règle de droit qui s'applique. Pour les privilèges dont
# le refus a un fondement légal identifié, on l'énonce. Pour les autres, le
# refus reste un refus d'habilitation, et on ne va pas inventer un article.
MOTIFS_JURIDIQUES: dict[str, str] = {
    "issue_formal_notice": (
        "La signification d'une mise en demeure relève du monopole légal de "
        "l'huissier de justice (عدل منفذ) : le code de procédure civile et "
        "commerciale réserve à lui seul la citation, la notification et "
        "l'exécution des actes (art. 5), et impose son intervention pour toute "
        "sommation au-delà de 150 dinars (art. 60). Mizan rédige le projet "
        "d'acte ; elle ne le signifie pas, et personne ne peut le signifier à "
        "la place de l'huissier."
    ),
    "sign_settlement": (
        "Le procès-verbal de conciliation est signé par le professionnel "
        "accrédité qui a conduit la séance, parce qu'il engage sa "
        "responsabilité professionnelle. Une plateforme n'exerce pas cet "
        "office."
    ),
    "approve_dossier": (
        "La recevabilité d'un dossier est appréciée par le greffe du tribunal "
        "de commerce. Ni la partie demanderesse ni la plateforme ne peuvent "
        "déclarer recevable ce que le greffe n'a pas examiné."
    ),
    "manage_tenants": (
        "L'administration des organisations inscrites relève de l'exploitation "
        "de la plateforme. Elle est sans rapport avec l'office exercé par "
        "votre profession, et elle ne vous est donc pas ouverte."
    ),
    "manage_users": (
        "La gestion des comptes appartient à l'administration de la "
        "plateforme et, dans votre organisation, à la personne qui en a reçu "
        "la charge."
    ),
    "manage_corpus": (
        "Le corpus des codes tunisiens est tenu par l'administration de la "
        "plateforme. Son intégrité conditionne toutes les citations produites "
        "par Mizan : il n'est modifiable par aucun compte utilisateur."
    ),
    "record_service": (
        "La date de signification est consignée par l'huissier de justice qui "
        "a signifié l'acte, parce que c'est cette date — et elle seule — qui "
        "fait courir le délai laissé au débiteur."
    ),
}


@dataclass(frozen=True)
class Refus:
    """Un refus motivé, destiné à être lu par un juriste.

    Gelé, comme la session dont il découle : un refus qu'un traitement ultérieur
    pourrait requalifier en autorisation ne serait pas un refus.

    `divulgue_autrui` est le champ que le test hostile vérifie. Il vaut faux
    quand le message a été rédigé de façon à ne rien apprendre sur l'existence
    ou l'inexistence de données appartenant à une autre organisation.
    """

    motif: str
    outil: str = ""
    privilege_manquant: str = ""
    divulgue_autrui: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "refuse": True,
            "motif": self.motif,
            "outil": self.outil,
            "privilege_manquant": self.privilege_manquant,
        }


@dataclass(frozen=True)
class Identite:
    """L'appelant, tel que le serveur l'a authentifié.

    Volontairement construite à partir d'une `Session` (packages.comptes.jetons)
    et jamais depuis un corps de requête : ce qui a été signé reste ce qui a été
    signé. Les champs sont un sous-ensemble délibéré de la session — l'agent n'a
    besoin de rien d'autre, et ce dont il ne dispose pas, il ne peut pas le
    laisser fuir.
    """

    organisation: str
    role: str
    permissions: tuple[str, ...] = ()
    nom_organisation: str = ""
    email: str = ""
    compte_id: str = ""

    # -- construction -------------------------------------------------------

    @staticmethod
    def depuis_session(session: Any) -> "Identite":
        """Traduit une session authentifiée en identité d'agent.

        Accepte tout objet portant les attributs d'une `Session`. On ne
        l'importe pas par son type : le paquet `comptes` évolue en parallèle
        pendant le hackathon, et l'agent n'a pas à tomber en panne parce qu'un
        champ a été ajouté à côté.
        """
        organisation = getattr(session, "organisation", None)
        role = getattr(session, "role", None)
        if not organisation or not role:
            raise IdentiteInvalide(
                "L'agent ne peut pas agir : la session ne dit ni pour quelle "
                "organisation ni à quel titre. Merci de vous reconnecter."
            )
        permissions = tuple(getattr(session, "permissions", ()) or ())
        # Une session sans privilège explicite reçoit ceux de son rôle. C'est
        # le cas des sessions forgées par un script de démonstration ; ça ne
        # relâche rien, puisque la matrice des rôles fait autorité.
        if not permissions:
            permissions = tuple(PERMISSIONS.get(role, ()))
        return Identite(
            organisation=str(organisation),
            role=str(role),
            permissions=permissions,
            nom_organisation=str(getattr(session, "nom_organisation", "") or ""),
            email=str(getattr(session, "email", "") or ""),
            compte_id=str(getattr(session, "compte_id", "") or ""),
        )

    # -- interrogation ------------------------------------------------------

    def peut(self, privilege: str) -> bool:
        """Vrai si l'identité porte ce privilège."""
        return privilege in self.permissions

    def meme_organisation(self, organisation: str) -> bool:
        """Vrai si l'organisation visée est bien celle de l'appelant."""
        return bool(organisation) and self.organisation == organisation

    @property
    def libelle_role(self) -> str:
        return libelle_role(self.role)

    @property
    def organisation_affichee(self) -> str:
        """Le nom lisible de l'organisation, ou son identifiant à défaut."""
        return self.nom_organisation or self.organisation

    def to_dict(self) -> dict[str, Any]:
        """Forme affichable. Ne contient rien qui n'appartienne à l'appelant."""
        return {
            "organisation": self.organisation,
            "nom_organisation": self.nom_organisation,
            "role": self.role,
            "libelle_role": self.libelle_role,
            "permissions": list(self.permissions),
        }


def _elider(verbe: str) -> str:
    """« de administrer » ne se dit pas.

    Repris de `packages/comptes/garde.py`, volontairement recopié plutôt
    qu'importé : cette fonction est privée là-bas, et l'agent ne doit pas
    dépendre d'un détail interne d'un autre paquet qu'un collègue peut
    renommer ce matin même.
    """
    return f"d'{verbe}" if verbe[:1].lower() in "aeéèêiouy" else f"de {verbe}"


def refuser_privilege(identite: Identite, privilege: str, outil: str = "") -> Refus:
    """Compose le refus opposé à un rôle qui ne porte pas ce privilège.

    Le message se lit en trois temps : ce que vous êtes, ce que vous avez
    tenté, pourquoi la loi ou l'organisation de la plateforme s'y oppose. Un
    juriste doit pouvoir contester ce refus ; pour cela il faut qu'il le
    comprenne.
    """
    action = libelle_permission(privilege)
    phrase = (
        f"Votre compte agit pour {identite.organisation_affichee} en qualité "
        f"de « {identite.libelle_role} ». Ce rôle ne permet pas "
        f"{_elider(action)} sur Mizan."
    )
    fondement = MOTIFS_JURIDIQUES.get(privilege)
    if fondement:
        phrase += " " + fondement

    # Qui, alors ? Un refus qui laisse la personne sans porte de sortie la
    # renvoie vers le téléphone du support. On nomme le rôle compétent.
    competents = [
        libelle_role(r) for r, p in PERMISSIONS.items() if privilege in p
    ]
    if competents and privilege in LIBELLES_PERMISSIONS:
        liste = ", ".join(f"« {c} »" for c in competents)
        phrase += (
            f" Sur Mizan, cette action est ouverte à : {liste}. "
            "Vous pouvez préparer le dossier et le lui transmettre."
        )

    return Refus(
        motif=phrase,
        outil=outil,
        privilege_manquant=privilege,
        divulgue_autrui=False,
    )


# Le message opposé à toute tentative de sortie du périmètre de l'organisation.
# Il est une CONSTANTE et non une chaîne composée sur place, pour une raison
# précise : composer le message avec le nom de l'organisation visée le ferait
# fuiter. Ici, il n'y a rien à interpoler, donc rien à faire fuiter.
MESSAGE_CLOISONNEMENT = (
    "L'agent de Mizan ne travaille que sur les dossiers de votre propre "
    "organisation. Il n'a accès à aucun dossier, aucune pièce et aucune donnée "
    "relevant d'une autre entreprise, et il ne peut pas vous dire si une telle "
    "entreprise est ou n'est pas cliente de la plateforme : le secret des "
    "affaires l'interdit, dans votre intérêt comme dans celui des autres. "
    "Si vous êtes en litige avec un tiers, décrivez-moi VOTRE créance — montant, "
    "date de facture, activité — et je l'analyserai pour vous."
)


def refuser_hors_organisation(outil: str = "") -> Refus:
    """Le refus opposé à toute demande visant une autre organisation.

    Ne prend délibérément PAS l'organisation visée en paramètre. On ne peut
    pas divulguer ce qu'on ne reçoit pas : c'est plus solide qu'une consigne
    de ne pas l'afficher, qu'un correctif pressé peut effacer.
    """
    return Refus(
        motif=MESSAGE_CLOISONNEMENT,
        outil=outil,
        privilege_manquant="",
        divulgue_autrui=False,
    )
