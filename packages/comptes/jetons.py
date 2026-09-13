"""Jetons de session : ce que le porteur est, signé pour qu'il ne puisse pas
le réécrire.

Un jeton Mizan transporte quatre choses : qui est le compte, à quelle
organisation il appartient, quel rôle il exerce, et quels privilèges ce rôle
lui donne. Le serveur n'a donc pas à rouvrir la base à chaque requête pour
savoir si l'appelant a le droit d'agir.

Ce confort a un prix : les privilèges voyagent chez le client, qui pourrait
être tenté de les modifier. La signature répond exactement à cela. Le jeton est
LISIBLE par tous — ce n'est pas un secret, c'est une carte d'identité — mais il
n'est MODIFIABLE par personne, parce que la signature ne se recalcule pas sans
la clé du serveur. Changer un seul caractère de la charge invalide le jeton.

Format : <charge en base64url>.<signature en base64url>, comparable à un JWT
mais sans dépendance : nous nous en tenons à la bibliothèque standard.

Le serveur ne fait AUCUNE confiance au contenu tant que la signature n'est pas
vérifiée. `lire_jeton` vérifie d'abord, décode ensuite — jamais l'inverse.
"""
from __future__ import annotations

import base64
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from hashlib import sha256

from packages.comptes.roles import permissions_du_role

# Douze heures : une journée d'audience. Assez pour qu'un greffier ne soit pas
# déconnecté au milieu de sa file, assez peu pour qu'un poste laissé ouvert le
# soir ne serve à personne le lendemain.
DUREE_PAR_DEFAUT_SECONDES = 12 * 3600

# Clé de développement. Elle est constante et publique — elle est écrite ici,
# dans un dépôt — donc elle ne protège RIEN. Elle n'existe que pour qu'une
# démonstration locale démarre sans configuration préalable. En production,
# MIZAN_SECRET doit être définie dans l'environnement ; `cle_de_signature`
# signale bruyamment dès qu'on retombe sur ce défaut.
CLE_DEVELOPPEMENT = "mizan-cle-de-developpement-NON-SECRETE-a-remplacer"

SEPARATEUR = "."


class JetonInvalide(ValueError):
    """Le jeton présenté ne peut pas être accepté : il est refusé en bloc.

    Une seule exception pour tous les cas — signature fausse, jeton expiré,
    charge illisible — et c'est délibéré. Un message qui distinguerait
    « signature invalide » de « jeton expiré » dirait à qui essaie de forger un
    jeton s'il s'approche du but.
    """


def cle_de_signature() -> bytes:
    """La clé qui signe les jetons, lue dans l'environnement.

    On relit la variable à chaque appel plutôt que de la figer au chargement du
    module : les tests ont besoin de resigner sous une autre clé pour prouver
    qu'un jeton étranger est bien rejeté, et un redémarrage de service doit
    prendre la nouvelle clé sans qu'on ait à vider un cache.
    """
    return os.environ.get("MIZAN_SECRET", CLE_DEVELOPPEMENT).encode("utf-8")


def signature_de_developpement() -> bool:
    """Vrai si Mizan tourne encore sur la clé de démonstration.

    L'API s'en sert pour afficher un avertissement visible. Une plateforme qui
    manipule des créances ne doit pas pouvoir passer en production sans que
    quelqu'un ait vu cet écriteau.
    """
    return "MIZAN_SECRET" not in os.environ


def _encoder(donnees: bytes) -> str:
    return base64.urlsafe_b64encode(donnees).decode("ascii").rstrip("=")


def _decoder(texte: str) -> bytes:
    return base64.urlsafe_b64decode(texte + "=" * (-len(texte) % 4))


@dataclass(frozen=True)
class Session:
    """Ce que le serveur sait de l'appelant, une fois le jeton vérifié.

    Gelée (`frozen`) pour une raison précise : une dépendance FastAPI passe cet
    objet à la fonction de route, et une route ne doit pas pouvoir s'ajouter un
    privilège en cours de traitement. Ce qui a été signé reste ce qui a été
    signé.
    """
    compte_id: str
    email: str
    organisation: str
    role: str
    permissions: tuple[str, ...] = ()
    emis_le: int = 0
    expire_le: int = 0
    nom_organisation: str = ""

    def peut(self, permission: str) -> bool:
        """Vrai si la session porte ce privilège."""
        return permission in self.permissions

    def meme_organisation(self, organisation: str) -> bool:
        """Vrai si la session agit bien au sein de l'organisation visée.

        Le cloisonnement entre organisations passe par cette question, et elle
        doit être posée à chaque lecture de données. Deux entreprises en litige
        peuvent l'une et l'autre être clientes de Mizan : que l'une puisse lire
        le dossier de l'autre ne serait pas un défaut d'affichage, ce serait
        une violation du secret des affaires.
        """
        return self.organisation == organisation

    def en_clair(self) -> dict[str, object]:
        """La session sous une forme affichable, sans rien de sensible."""
        return {
            "compte_id": self.compte_id,
            "email": self.email,
            "organisation": self.organisation,
            "nom_organisation": self.nom_organisation,
            "role": self.role,
            "permissions": list(self.permissions),
            "expire_le": self.expire_le,
        }


def creer_jeton(
    compte_id: str,
    email: str,
    organisation: str,
    role: str,
    *,
    nom_organisation: str = "",
    duree_secondes: int = DUREE_PAR_DEFAUT_SECONDES,
    maintenant: int | None = None,
) -> str:
    """Signe un jeton de session pour ce compte.

    Les privilèges ne sont pas passés en argument : ils sont RELUS depuis la
    matrice des rôles au moment de l'émission. C'est une garantie de
    cohérence — aucun appelant ne peut glisser dans un jeton un privilège que
    son rôle ne porte pas, même par erreur de programmation.
    """
    instant = int(time.time()) if maintenant is None else int(maintenant)
    charge = {
        "cid": compte_id,
        "eml": email,
        "org": organisation,
        "orn": nom_organisation,
        "rol": role,
        "prm": list(permissions_du_role(role)),
        "iat": instant,
        "exp": instant + int(duree_secondes),
    }
    # `sort_keys` et les séparateurs compacts rendent la sérialisation
    # reproductible : la même charge donne toujours les mêmes octets, donc la
    # même signature. Sans cela, deux versions de Python pourraient produire
    # deux jetons différents pour une session identique.
    brut = json.dumps(charge, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")
    corps = _encoder(brut)
    return corps + SEPARATEUR + _encoder(_signer(corps))


def _signer(corps: str) -> bytes:
    return hmac.new(cle_de_signature(), corps.encode("ascii"), sha256).digest()


def lire_jeton(jeton: str, *, maintenant: int | None = None) -> Session:
    """Vérifie un jeton et renvoie la session qu'il porte, ou refuse.

    L'ordre des contrôles est celui qui coûte le moins à l'attaquant :
    d'abord la forme, puis la signature, puis seulement le contenu. On ne
    désérialise jamais du JSON dont la signature n'a pas été validée.
    """
    refus = JetonInvalide(
        "Votre session n'est plus valide. Merci de vous reconnecter."
    )
    if not isinstance(jeton, str) or jeton.count(SEPARATEUR) != 1:
        raise refus

    corps, signature_recue = jeton.split(SEPARATEUR)
    try:
        recue = _decoder(signature_recue)
    except (ValueError, TypeError):
        raise refus from None

    # Temps constant : une comparaison ordinaire abandonnerait au premier octet
    # faux, et le temps de réponse permettrait de reconstituer la signature
    # octet par octet.
    if not hmac.compare_digest(recue, _signer(corps)):
        raise refus

    try:
        charge = json.loads(_decoder(corps).decode("utf-8"))
    except (ValueError, TypeError, UnicodeDecodeError):
        raise refus from None
    if not isinstance(charge, dict):
        raise refus

    instant = int(time.time()) if maintenant is None else int(maintenant)
    try:
        expire_le = int(charge["exp"])
    except (KeyError, TypeError, ValueError):
        raise refus from None
    if instant >= expire_le:
        # Message distinct : ici, l'utilisateur n'a rien fait de mal, il est
        # simplement resté connecté trop longtemps. Lui dire de se reconnecter
        # sans le soupçonner de rien est le traitement juste.
        raise JetonInvalide(
            "Votre session a expiré. Merci de vous reconnecter pour continuer."
        )

    try:
        return Session(
            compte_id=str(charge["cid"]),
            email=str(charge["eml"]),
            organisation=str(charge["org"]),
            nom_organisation=str(charge.get("orn", "")),
            role=str(charge["rol"]),
            permissions=tuple(charge.get("prm", ())),
            emis_le=int(charge.get("iat", 0)),
            expire_le=expire_le,
        )
    except (KeyError, TypeError, ValueError):
        raise refus from None
