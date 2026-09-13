"""Sceller, signer, vérifier : rendre un échange ATTRIBUABLE et NON-RÉPUDIABLE.

Pourquoi ce module existe
-------------------------
Dans un litige précontentieux, un document que personne ne peut attribuer ne
vaut rien. Une mise en demeure dont on ne peut pas prouver l'expéditeur est
contestable : le débiteur dira « ce n'est pas moi qui ai reçu ça », ou
« le montant n'était pas celui-là », et le créancier n'aura rien à opposer.

Ce module répond à trois questions, et à trois seulement :

1. **Intégrité** — le document a-t-il été modifié depuis qu'il a été scellé ?
   Réponse par empreinte SHA-256 : un seul caractère changé, et l'empreinte
   n'est plus la même.
2. **Attribution** — qui a apposé ce sceau ? Réponse par signature Ed25519 :
   seul le détenteur de la clé privée a pu la produire.
3. **Antériorité déclarée** — quand ? Réponse par horodatage, avec une
   réserve capitale énoncée plus bas.

Ce qu'il NE fait PAS, et qu'il ne faut jamais laisser croire
------------------------------------------------------------
- **Ce n'est pas une signature électronique qualifiée.** Une signature
  qualifiée suppose un certificat délivré par un prestataire de confiance
  reconnu (en Tunisie : TunTrust/ANCE). Ici, les clés sont générées
  localement par la plateforme. La valeur probante est celle d'un faisceau
  d'indices techniques, pas celle d'une présomption légale.
- **L'horodatage n'est pas un horodatage qualifié.** Il provient de l'horloge
  de la machine qui scelle, pas d'une autorité d'horodatage (RFC 3161). Il
  prouve la cohérence interne du sceau, pas la date certaine opposable.
  Un sceau prouve qu'un document n'a pas bougé ; il ne prouve pas seul qu'il
  existait à telle date face à un tiers de mauvaise foi.
- **Sceller n'est pas signifier.** Le projet de mise en demeure produit par
  `packages/legal/notice.py` reste un PROJET NON SIGNIFIÉ, scellé ou non.
  Seul un huissier de justice (عدل منفذ) signifie. Le sceau n'ajoute aucun
  effet de droit au document ; il permet seulement de prouver ce qui a été
  rédigé, par qui, et que cela n'a pas été retouché depuis.

Le point dur : d'où vient la clé publique de vérification
----------------------------------------------------------
Un sceau transporte la clé publique du signataire, par commodité. Mais
vérifier une signature avec la clé que l'attaquant a lui-même jointe au
document ne prouve RIEN : il lui suffit de re-signer le document falsifié
avec sa propre paire de clés et de remplacer les deux champs.

C'est pourquoi `verifier()` distingue deux résultats :

- sans clé de référence fournie par l'appelant : on contrôle l'intégrité et
  la cohérence interne, et `attribution_etablie` vaut False ;
- avec une clé de référence connue d'avance (un `RegistreDeCles`, une clé
  échangée hors bande) : `attribution_etablie` peut valoir True.

Aucune fonction de ce module ne prétend attribuer un document à une personne
sur la seule foi de ce que ce document affirme de lui-même.

Choix techniques et licences
----------------------------
- Ed25519 (RFC 8032) via `cryptography` (Apache-2.0 OR BSD-3-Clause). Le
  projet est livré on-premise : aucune dépendance AGPL/GPL n'est admise, et
  `cryptography` satisfait cette règle.
- SHA-256 pour l'empreinte.
- L'empreinte porte sur les **octets UTF-8 exacts** du document, sans
  normalisation Unicode. C'est délibéré : deux textes visuellement identiques
  mais encodés différemment sont deux textes différents, et le droit de la
  preuve veut l'exactitude, pas la ressemblance.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

# --- Constantes de format ---------------------------------------------------
# La version du format de sceau est signée avec le reste : elle empêche qu'un
# sceau produit sous des règles anciennes soit relu sous des règles nouvelles
# sans que personne ne s'en aperçoive.
VERSION_SCELLE = "mizan-scelle-1"
ALGORITHME_EMPREINTE = "SHA-256"
ALGORITHME_SIGNATURE = "Ed25519"

# Longueur d'une signature Ed25519, en octets. Vérifiée explicitement pour que
# une signature tronquée soit rejetée avec un message clair plutôt qu'avec une
# erreur de bas niveau incompréhensible dans un rapport destiné à un juge.
LONGUEUR_SIGNATURE_ED25519 = 64


# --- Erreurs ----------------------------------------------------------------

class ErreurIdentite(Exception):
    """Toute erreur de la couche d'identité. Racine commune pour l'appelant."""


class DocumentVide(ErreurIdentite):
    """On ne scelle pas le néant.

    Sceller une chaîne vide produirait un sceau techniquement valide et
    juridiquement absurde : l'empreinte de la chaîne vide est une constante
    connue, que n'importe qui peut recalculer et rejouer. Un sceau doit
    engager sur un contenu, et un contenu vide n'engage personne.
    """


class ScelleInvalide(ErreurIdentite):
    """Le sceau est malformé : champs manquants, types faux, format inconnu.

    Distinct d'un sceau bien formé mais qui ne correspond pas au document :
    ce dernier cas n'est pas une exception, c'est un résultat de vérification
    négatif, qui doit être rapporté et non levé.
    """


class FournisseurIndisponible(ErreurIdentite, NotImplementedError):
    """Le fournisseur d'identité demandé n'est pas raccordé.

    Hérite de NotImplementedError pour que le code appelant qui attrape déjà
    NotImplementedError ne soit pas surpris, tout en restant rattaché à
    ErreurIdentite.
    """


# --- Empreinte --------------------------------------------------------------

def _octets(document: str | bytes) -> bytes:
    """Rend les octets exacts d'un document, sans rien normaliser.

    Le refus de normaliser est un choix juridique : si deux documents diffèrent
    d'un octet, ce sont deux documents, même si un lecteur humain ne voit pas
    la différence. Une plateforme de preuve ne doit pas décider que deux textes
    « se valent ».
    """
    if isinstance(document, bytes):
        return document
    if isinstance(document, str):
        return document.encode("utf-8")
    raise ScelleInvalide(
        f"Un document se scelle sous forme de texte ou d'octets, "
        f"pas sous forme de {type(document).__name__}."
    )


def empreinte(document: str | bytes) -> str:
    """Empreinte SHA-256 du document, en hexadécimal minuscule.

    C'est la pièce qui répond à « le document a-t-il changé ? ». Modifier un
    seul caractère change environ la moitié des bits de l'empreinte : il n'y a
    pas d'altération « petite » du point de vue de l'empreinte.

    Lève DocumentVide si le document ne contient aucun octet.
    """
    b = _octets(document)
    if not b:
        raise DocumentVide(
            "Document vide : il n'y a rien à sceller. Un sceau doit engager "
            "sur un contenu, et un contenu vide n'engage personne."
        )
    return hashlib.sha256(b).hexdigest()


# --- Le sceau ---------------------------------------------------------------

@dataclass(frozen=True)
class Scelle:
    """Ce qui est apposé sur un document, et ce qui sera produit au juge.

    Immuable (`frozen=True`) : un sceau qu'on peut modifier après coup en
    mémoire n'est pas un sceau. Pour sceller un autre contenu, on en fabrique
    un autre.

    Champs :
        version              : format du sceau, signé avec le reste.
        algorithme_empreinte : SHA-256.
        algorithme_signature : Ed25519.
        empreinte_document   : SHA-256 du document scellé, en hexadécimal.
        identifiant_signataire : qui déclare sceller (ex. « Menuiserie Ahmed »).
        horodatage           : date et heure UTC, ISO 8601. NON QUALIFIÉ.
        signature            : signature Ed25519 hexadécimale de la charge utile.
        cle_publique         : clé publique du signataire, hexadécimale. Jointe
                               par commodité ; ne vaut PAS preuve d'identité à
                               elle seule (voir l'en-tête du module).
        contexte             : champ libre (numéro de dossier, objet). Signé
                               lui aussi : on ne peut pas le réécrire après coup.
    """

    version: str
    algorithme_empreinte: str
    algorithme_signature: str
    empreinte_document: str
    identifiant_signataire: str
    horodatage: str
    signature: str
    cle_publique: str
    contexte: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Le sceau en dictionnaire, prêt pour JSON ou pour une base."""
        return asdict(self)

    def to_json(self) -> str:
        """Le sceau en JSON lisible, arabe compris (pas d'échappement \\uXXXX)."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2,
                          sort_keys=True)

    @staticmethod
    def from_dict(donnees: dict[str, Any]) -> "Scelle":
        """Relit un sceau. Lève ScelleInvalide si un champ manque ou détonne."""
        if not isinstance(donnees, dict):
            raise ScelleInvalide("Un sceau se relit depuis un dictionnaire.")
        attendus = {
            "version", "algorithme_empreinte", "algorithme_signature",
            "empreinte_document", "identifiant_signataire", "horodatage",
            "signature", "cle_publique", "contexte",
        }
        manquants = attendus - set(donnees)
        if manquants:
            raise ScelleInvalide(
                "Sceau incomplet, champs manquants : "
                + ", ".join(sorted(manquants))
            )
        contexte = donnees["contexte"]
        if not isinstance(contexte, dict):
            raise ScelleInvalide("Le champ « contexte » doit être un dictionnaire.")
        for champ in attendus - {"contexte"}:
            if not isinstance(donnees[champ], str):
                raise ScelleInvalide(
                    f"Le champ « {champ} » doit être une chaîne de caractères."
                )
        return Scelle(
            version=donnees["version"],
            algorithme_empreinte=donnees["algorithme_empreinte"],
            algorithme_signature=donnees["algorithme_signature"],
            empreinte_document=donnees["empreinte_document"],
            identifiant_signataire=donnees["identifiant_signataire"],
            horodatage=donnees["horodatage"],
            signature=donnees["signature"],
            cle_publique=donnees["cle_publique"],
            contexte=contexte,
        )

    @staticmethod
    def from_json(texte: str) -> "Scelle":
        """Relit un sceau depuis du JSON. Lève ScelleInvalide si illisible."""
        try:
            donnees = json.loads(texte)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ScelleInvalide(f"Sceau illisible : {exc}") from exc
        return Scelle.from_dict(donnees)


def _charge_utile(
    *,
    version: str,
    algorithme_empreinte: str,
    algorithme_signature: str,
    empreinte_document: str,
    identifiant_signataire: str,
    horodatage: str,
    contexte: dict[str, Any],
) -> bytes:
    """Les octets réellement signés.

    Ce n'est PAS le document : c'est l'empreinte du document PLUS les
    métadonnées qui l'accompagnent. Conséquence juridique recherchée : on ne
    peut pas détacher une signature de son horodatage, de son signataire
    déclaré ni de son contexte pour la recoller ailleurs. Signer la seule
    empreinte du document laisserait ces champs librement réécrivables.

    La sérialisation est canonique (clés triées, séparateurs fixes, UTF-8
    non échappé) : deux exécutions sur les mêmes données produisent
    exactement les mêmes octets, sinon la vérification serait un tirage au
    sort.
    """
    charge = {
        "version": version,
        "algorithme_empreinte": algorithme_empreinte,
        "algorithme_signature": algorithme_signature,
        "empreinte_document": empreinte_document,
        "identifiant_signataire": identifiant_signataire,
        "horodatage": horodatage,
        "contexte": contexte,
    }
    return json.dumps(
        charge, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


# --- Fournisseurs d'identité ------------------------------------------------

@runtime_checkable
class FournisseurIdentite(Protocol):
    """Ce que doit savoir faire une source d'identité, quelle qu'elle soit.

    L'abstraction existe pour une raison précise : la plateforme doit pouvoir
    passer d'une paire de clés locale (aujourd'hui, pour la démonstration et
    les déploiements on-premise) à une identité d'État (e-Houwiya, adossé à
    TunTrust/ANCE) sans réécrire la couche de scellement. Le jour où le
    raccordement existe, seule l'implémentation change.
    """

    @property
    def identifiant(self) -> str:
        """Qui signe, en clair : raison sociale, nom, ou identifiant national."""
        ...

    @property
    def cle_publique_hex(self) -> str:
        """La clé publique, en hexadécimal, telle qu'elle sera publiée."""
        ...

    def signer(self, charge_utile: bytes) -> bytes:
        """Signe des octets et rend la signature."""
        ...


class FournisseurLocal:
    """Identité locale : une paire de clés Ed25519 générée par la plateforme.

    Valeur probante : celle d'un indice technique. La plateforme atteste que
    le détenteur de cette clé privée a scellé ce document. Elle n'atteste pas
    que ce détenteur est bien la personne qu'il prétend être — aucune autorité
    de certification n'est intervenue pour le vérifier.

    C'est suffisant pour l'usage visé : prouver, entre deux parties qui se
    sont échangé leurs clés publiques, qu'un document n'a pas été retouché et
    qu'il vient bien de l'autre. C'est insuffisant pour opposer une signature
    à un tiers qui n'a jamais reconnu la clé.
    """

    def __init__(
        self,
        identifiant: str,
        cle_privee: Ed25519PrivateKey | None = None,
    ) -> None:
        """Crée une identité locale, en générant la paire de clés si besoin.

        `identifiant` ne peut pas être vide : un sceau sans signataire déclaré
        ne répond pas à la question du juge (« qui a signé ? »).
        """
        if not isinstance(identifiant, str) or not identifiant.strip():
            raise ErreurIdentite(
                "Un signataire doit être identifié : un sceau anonyme "
                "n'attribue rien."
            )
        self._identifiant = identifiant.strip()
        self._cle_privee = cle_privee or Ed25519PrivateKey.generate()

    @property
    def identifiant(self) -> str:
        return self._identifiant

    @property
    def cle_publique(self) -> Ed25519PublicKey:
        """La clé publique, objet cryptographique."""
        return self._cle_privee.public_key()

    @property
    def cle_publique_hex(self) -> str:
        """La clé publique en hexadécimal : ce qu'on publie et qu'on compare."""
        return self.cle_publique.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ).hex()

    def signer(self, charge_utile: bytes) -> bytes:
        """Signe les octets qui lui sont donnés. Rien d'autre.

        La méthode ne connaît pas les documents : elle signe ce qu'on lui
        présente. C'est `sceller()` qui décide ce qui mérite d'être signé.
        """
        if not isinstance(charge_utile, bytes):
            raise ErreurIdentite("On ne signe que des octets.")
        return self._cle_privee.sign(charge_utile)

    def exporter_cle_privee_pem(self, mot_de_passe: bytes | None = None) -> bytes:
        """Exporte la clé privée en PEM, chiffrée si un mot de passe est donné.

        Une clé privée en clair sur un disque est une signature que n'importe
        quel porteur du fichier peut produire à la place de son titulaire.
        Le mot de passe est donc fortement recommandé hors tests.
        """
        chiffrement: serialization.KeySerializationEncryption
        if mot_de_passe:
            chiffrement = serialization.BestAvailableEncryption(mot_de_passe)
        else:
            chiffrement = serialization.NoEncryption()
        return self._cle_privee.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=chiffrement,
        )

    @staticmethod
    def depuis_pem(
        identifiant: str,
        pem: bytes,
        mot_de_passe: bytes | None = None,
    ) -> "FournisseurLocal":
        """Recharge une identité locale depuis une clé privée PEM."""
        try:
            cle = serialization.load_pem_private_key(pem, password=mot_de_passe)
        except (ValueError, TypeError) as exc:
            raise ErreurIdentite(f"Clé privée illisible : {exc}") from exc
        if not isinstance(cle, Ed25519PrivateKey):
            raise ErreurIdentite(
                "Cette clé n'est pas une clé Ed25519 ; le format de sceau "
                f"{VERSION_SCELLE} n'accepte pas d'autre algorithme."
            )
        return FournisseurLocal(identifiant, cle_privee=cle)


class FournisseurEHouwiya:
    """e-Houwiya (الهوية الإلكترونية) — Mobile ID officiel tunisien. NON IMPLÉMENTÉ.

    Ce qui est établi et n'est pas discuté ici : e-Houwiya est le Mobile ID
    officiel de la Tunisie, adossé à TunTrust/ANCE, l'autorité de
    certification racine nationale. C'est une infrastructure d'État réelle.

    Ce qui n'est PAS établi, et que cette classe refuse de faire semblant de
    savoir : le protocole d'intégration exact, le format des certificats
    délivrés, les points d'accès, les modalités d'enrôlement d'un éditeur
    tiers. Aucune de ces spécifications n'a pu être vérifiée auprès d'une
    source officielle au moment de l'écriture de ce module (voir
    EHOUWIYA.md). Elles sont donc marquées UNKNOWN et ne sont pas devinées.

    Toute méthode lève FournisseurIndisponible. C'est volontaire et ce n'est
    pas un travail inachevé qu'on aurait oublié : une intégration d'État
    simulée qui produirait des sceaux « e-Houwiya » sans qu'aucun État n'y
    soit pour rien serait un faux. Le client exige qu'on n'annonce jamais
    comme fait ce qui ne l'est pas ; une exception explicite vaut mieux qu'une
    démonstration mensongère.

    Ce qu'il faudra pour la lever : un accord de raccordement avec
    TunTrust/ANCE, et la documentation d'intégration correspondante.
    """

    MESSAGE = (
        "e-Houwiya n'est pas raccordé. e-Houwiya est le Mobile ID officiel "
        "tunisien, adossé à TunTrust/ANCE (autorité de certification racine "
        "nationale) : y accéder suppose un accord de raccordement avec "
        "TunTrust/ANCE et la documentation d'intégration correspondante. "
        "Le protocole, le format de certificat et les points d'accès sont à "
        "ce jour UNKNOWN côté Mizan — ils n'ont pas pu être vérifiés auprès "
        "d'une source officielle et ne seront pas devinés. Aucun sceau "
        "e-Houwiya ne peut donc être produit. Utilisez FournisseurLocal, "
        "dont la valeur probante plus faible est documentée, plutôt qu'une "
        "intégration d'État simulée."
    )

    def __init__(self, identifiant_national: str | None = None) -> None:
        """Construire l'objet est permis ; s'en servir ne l'est pas.

        La construction reste possible pour que le câblage applicatif (choix
        d'un fournisseur en configuration) puisse être écrit et testé dès
        maintenant, et échoue au moment de l'usage avec un message qui
        explique ce qui manque — plutôt qu'au chargement, avec une trace
        obscure.
        """
        self._identifiant_national = identifiant_national

    @property
    def identifiant(self) -> str:
        raise FournisseurIndisponible(self.MESSAGE)

    @property
    def cle_publique_hex(self) -> str:
        raise FournisseurIndisponible(self.MESSAGE)

    def signer(self, charge_utile: bytes) -> bytes:
        raise FournisseurIndisponible(self.MESSAGE)


# --- Sceller ----------------------------------------------------------------

def sceller(
    document: str | bytes,
    fournisseur: FournisseurIdentite,
    *,
    contexte: dict[str, Any] | None = None,
    horodatage: datetime | None = None,
) -> Scelle:
    """Appose un sceau sur un document : empreinte, horodatage, signature.

    C'est l'opération qui rend un échange non-répudiable entre parties qui se
    connaissent : le signataire ne pourra pas soutenir plus tard qu'il n'a
    jamais produit ce texte, et le destinataire ne pourra pas soutenir en
    avoir reçu un autre.

    Args:
        document: le texte scellé — typiquement `MiseEnDemeure.texte` produit
            par `packages/legal/notice.py`. Sceller n'ajoute aucun effet de
            droit : un projet non signifié scellé reste un projet non signifié.
        fournisseur: l'identité qui scelle (voir `FournisseurIdentite`).
        contexte: métadonnées libres (numéro de dossier, objet), signées avec
            le reste et donc non réécrivables après coup.
        horodatage: forcé uniquement pour les tests. En production, l'heure
            courante UTC. Rappel : horodatage NON QUALIFIÉ.

    Returns:
        Le `Scelle`, à conserver à côté du document.

    Raises:
        DocumentVide: document sans aucun octet.
        FournisseurIndisponible: fournisseur non raccordé (e-Houwiya).
        ErreurIdentite: contexte non sérialisable, identité invalide.
    """
    emp = empreinte(document)  # lève DocumentVide avant toute autre chose

    if contexte is None:
        contexte = {}
    if not isinstance(contexte, dict):
        raise ErreurIdentite("Le contexte d'un sceau doit être un dictionnaire.")
    try:
        # Épreuve de sérialisation immédiate : un contexte qui ne passe pas en
        # JSON produirait un sceau invérifiable, découvert bien trop tard.
        json.dumps(contexte, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ErreurIdentite(
            f"Le contexte du sceau n'est pas sérialisable en JSON : {exc}"
        ) from exc

    quand = horodatage or datetime.now(timezone.utc)
    if quand.tzinfo is None:
        # Une heure sans fuseau n'est pas une heure : elle ne veut rien dire
        # dans un dossier où les parties peuvent être dans deux pays.
        raise ErreurIdentite(
            "L'horodatage doit porter un fuseau horaire explicite."
        )
    horodatage_iso = quand.astimezone(timezone.utc).isoformat()

    identifiant = fournisseur.identifiant  # peut lever FournisseurIndisponible
    cle_publique_hex = fournisseur.cle_publique_hex

    charge = _charge_utile(
        version=VERSION_SCELLE,
        algorithme_empreinte=ALGORITHME_EMPREINTE,
        algorithme_signature=ALGORITHME_SIGNATURE,
        empreinte_document=emp,
        identifiant_signataire=identifiant,
        horodatage=horodatage_iso,
        contexte=contexte,
    )
    signature = fournisseur.signer(charge)

    return Scelle(
        version=VERSION_SCELLE,
        algorithme_empreinte=ALGORITHME_EMPREINTE,
        algorithme_signature=ALGORITHME_SIGNATURE,
        empreinte_document=emp,
        identifiant_signataire=identifiant,
        horodatage=horodatage_iso,
        signature=signature.hex(),
        cle_publique=cle_publique_hex,
        contexte=contexte,
    )


# --- Vérifier ---------------------------------------------------------------

@dataclass(frozen=True)
class ResultatVerification:
    """Ce que la vérification a pu établir, et ce qu'elle n'a pas pu établir.

    Le résultat est délibérément un objet et non un booléen. « Vrai/faux » ne
    permet pas de dire au juge la différence entre « le document n'a pas
    bougé mais je ne sais pas qui l'a signé » et « le document a été
    modifié » — deux situations qui n'ont pas du tout les mêmes conséquences.

    Champs :
        valide              : intégrité ET signature cohérentes.
        document_intact     : l'empreinte du document correspond au sceau.
        signature_valide    : la signature correspond à la clé publique du sceau.
        attribution_etablie : une clé de référence connue d'avance a été
                              fournie, et elle correspond. Sans cela, on ne
                              sait pas QUI a signé, seulement que quelqu'un
                              disposant de la clé jointe l'a fait.
        motif               : phrase en français expliquant le résultat.
        anomalies           : liste des problèmes constatés, en français.
    """

    valide: bool
    document_intact: bool
    signature_valide: bool
    attribution_etablie: bool
    motif: str
    anomalies: list[str]

    def __bool__(self) -> bool:
        """Permet `if verifier(...)`, mais `valide` reste la lecture correcte."""
        return self.valide

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def verifier(
    scelle: Scelle | dict[str, Any],
    document: str | bytes,
    *,
    cle_publique_reference: str | Ed25519PublicKey | None = None,
) -> ResultatVerification:
    """Vérifie qu'un sceau correspond bien à ce document, et le dit en clair.

    Détecte, entre autres : l'altération d'un seul caractère, la signature
    tronquée ou bricolée, le rejeu d'un sceau valide sur un autre document,
    et — si une clé de référence est fournie — la signature apposée par une
    autre partie que celle attendue.

    Args:
        scelle: le sceau, objet `Scelle` ou dictionnaire relu depuis une base.
        document: le document tel qu'on le détient aujourd'hui.
        cle_publique_reference: la clé publique du signataire attendu, connue
            par un autre canal que le sceau lui-même. Sans elle, l'attribution
            n'est PAS établie : vérifier une signature avec la clé jointe au
            document ne prouve rien, l'attaquant ayant pu remplacer les deux.

    Returns:
        Un `ResultatVerification`. Cette fonction ne lève pas d'exception pour
        un sceau qui ne correspond pas : un échec de vérification est un
        résultat à rapporter, pas un incident technique. Elle lève en revanche
        ScelleInvalide si le sceau est malformé au point d'être illisible.
    """
    if isinstance(scelle, dict):
        scelle = Scelle.from_dict(scelle)
    if not isinstance(scelle, Scelle):
        raise ScelleInvalide(
            "La vérification attend un sceau (objet Scelle ou dictionnaire)."
        )

    anomalies: list[str] = []

    # 1. Format. Un sceau d'une autre version obéit peut-être à d'autres
    #    règles : le relire sous les règles d'aujourd'hui serait une faute.
    if scelle.version != VERSION_SCELLE:
        anomalies.append(
            f"Le sceau est au format « {scelle.version} », alors que cette "
            f"version de Mizan lit le format « {VERSION_SCELLE} ». "
            "Il n'est pas vérifiable ici."
        )
        return ResultatVerification(
            valide=False, document_intact=False, signature_valide=False,
            attribution_etablie=False,
            motif="Format de sceau inconnu : vérification impossible.",
            anomalies=anomalies,
        )
    if scelle.algorithme_empreinte != ALGORITHME_EMPREINTE:
        anomalies.append(
            f"Algorithme d'empreinte annoncé « {scelle.algorithme_empreinte} », "
            f"attendu « {ALGORITHME_EMPREINTE} »."
        )
    if scelle.algorithme_signature != ALGORITHME_SIGNATURE:
        anomalies.append(
            f"Algorithme de signature annoncé « {scelle.algorithme_signature} », "
            f"attendu « {ALGORITHME_SIGNATURE} »."
        )
    if anomalies:
        return ResultatVerification(
            valide=False, document_intact=False, signature_valide=False,
            attribution_etablie=False,
            motif="Algorithmes non conformes au format de sceau de Mizan.",
            anomalies=anomalies,
        )

    # 2. Intégrité du document.
    try:
        emp_actuelle = empreinte(document)
    except DocumentVide:
        return ResultatVerification(
            valide=False, document_intact=False, signature_valide=False,
            attribution_etablie=False,
            motif=("Le document présenté est vide : il ne peut correspondre "
                   "à aucun sceau."),
            anomalies=["Document présenté vide."],
        )
    document_intact = (emp_actuelle == scelle.empreinte_document)
    if not document_intact:
        anomalies.append(
            "Le document ne correspond pas au sceau : son empreinte est "
            f"« {emp_actuelle[:16]}… » alors que le sceau porte "
            f"« {scelle.empreinte_document[:16]}… ». Soit le document a été "
            "modifié depuis qu'il a été scellé, soit ce sceau appartient à "
            "un autre document."
        )

    # 3. Signature. Contrôles de forme d'abord, pour rendre une signature
    #    tronquée intelligible plutôt que de laisser remonter une erreur brute.
    signature_valide = False
    try:
        signature_octets = bytes.fromhex(scelle.signature)
    except ValueError:
        anomalies.append(
            "La signature n'est pas une valeur hexadécimale lisible : "
            "le sceau a été altéré ou mal recopié."
        )
        signature_octets = b""

    if signature_octets and len(signature_octets) != LONGUEUR_SIGNATURE_ED25519:
        anomalies.append(
            f"La signature fait {len(signature_octets)} octets au lieu des "
            f"{LONGUEUR_SIGNATURE_ED25519} attendus : elle est tronquée ou "
            "complétée. Un sceau incomplet ne prouve rien."
        )
        signature_octets = b""

    cle_du_scelle: Ed25519PublicKey | None = None
    try:
        cle_du_scelle = Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(scelle.cle_publique)
        )
    except (ValueError, TypeError):
        anomalies.append(
            "La clé publique jointe au sceau est illisible : "
            "impossible de contrôler la signature."
        )

    if signature_octets and cle_du_scelle is not None:
        charge = _charge_utile(
            version=scelle.version,
            algorithme_empreinte=scelle.algorithme_empreinte,
            algorithme_signature=scelle.algorithme_signature,
            empreinte_document=scelle.empreinte_document,
            identifiant_signataire=scelle.identifiant_signataire,
            horodatage=scelle.horodatage,
            contexte=scelle.contexte,
        )
        try:
            cle_du_scelle.verify(signature_octets, charge)
            signature_valide = True
        except InvalidSignature:
            anomalies.append(
                "La signature ne correspond pas au contenu du sceau : "
                "l'un des champs (empreinte, signataire, horodatage, "
                "contexte) a été modifié après la signature."
            )

    # 4. Attribution. Le point dur : avec QUELLE clé compare-t-on ?
    attribution_etablie = False
    if cle_publique_reference is not None:
        if isinstance(cle_publique_reference, Ed25519PublicKey):
            reference_hex = cle_publique_reference.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            ).hex()
        elif isinstance(cle_publique_reference, str):
            reference_hex = cle_publique_reference.strip().lower()
        else:
            raise ScelleInvalide(
                "La clé publique de référence doit être une chaîne "
                "hexadécimale ou une clé publique Ed25519."
            )
        if reference_hex != scelle.cle_publique.strip().lower():
            anomalies.append(
                "Le sceau a été apposé avec une autre clé que celle du "
                "signataire attendu. Le document est signé, mais pas par la "
                "partie que l'on croyait : il ne lui est pas opposable."
            )
        elif signature_valide and document_intact:
            attribution_etablie = True
    else:
        anomalies.append(
            "Aucune clé publique de référence n'a été fournie : on vérifie "
            "la signature avec la clé jointe au sceau lui-même. Cela "
            "établit que le document n'a pas bougé, mais PAS qui l'a signé."
        )

    valide = document_intact and signature_valide

    if valide and attribution_etablie:
        motif = (
            "Sceau valide. Le document est intact et il a bien été scellé "
            f"par {scelle.identifiant_signataire}."
        )
    elif valide:
        motif = (
            "Le document est intact et le sceau est cohérent, mais "
            "l'identité du signataire n'est pas confirmée : aucune clé de "
            "référence n'a été fournie ou elle ne correspond pas."
        )
    elif not document_intact:
        motif = (
            "Le document a été modifié depuis qu'il a été scellé, ou bien "
            "ce sceau ne lui appartient pas."
        )
    else:
        motif = "La signature du sceau n'est pas valide."

    return ResultatVerification(
        valide=valide,
        document_intact=document_intact,
        signature_valide=signature_valide,
        attribution_etablie=attribution_etablie,
        motif=motif,
        anomalies=anomalies,
    )


# --- Registre de clés -------------------------------------------------------

class RegistreDeCles:
    """Les clés publiques que la plateforme reconnaît, et à qui elles sont.

    Sans registre, `verifier()` ne peut jamais établir d'attribution : elle
    n'a que la clé que le document transporte, laquelle ne prouve rien. Le
    registre est donc l'endroit où une clé publique cesse d'être une suite
    d'octets pour devenir « la clé de Menuiserie Ahmed ».

    Il est délibérément minimal et en mémoire : la question de savoir COMMENT
    une clé entre dans ce registre (échange hors bande, dépôt contradictoire,
    un jour un certificat TunTrust) est une question de procédure, pas de
    code, et elle n'est pas tranchée ici.
    """

    def __init__(self) -> None:
        self._cles: dict[str, str] = {}

    def enregistrer(self, identifiant: str, cle_publique_hex: str) -> None:
        """Associe une clé publique à une partie.

        Refuse de réécrire silencieusement une clé déjà connue : changer la
        clé d'une partie sans le dire invaliderait des attributions passées
        sans que personne ne s'en aperçoive.
        """
        if not identifiant or not identifiant.strip():
            raise ErreurIdentite("Une clé s'enregistre au nom d'une partie.")
        identifiant = identifiant.strip()
        cle = cle_publique_hex.strip().lower()
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(cle))
        except (ValueError, TypeError) as exc:
            raise ErreurIdentite(
                f"Clé publique invalide pour « {identifiant} » : {exc}"
            ) from exc
        ancienne = self._cles.get(identifiant)
        if ancienne is not None and ancienne != cle:
            raise ErreurIdentite(
                f"Une autre clé est déjà enregistrée pour « {identifiant} ». "
                "Remplacer une clé sans procédure explicite invaliderait "
                "les attributions passées sans trace."
            )
        self._cles[identifiant] = cle

    def enregistrer_fournisseur(self, fournisseur: FournisseurIdentite) -> None:
        """Enregistre la clé publique d'un fournisseur d'identité."""
        self.enregistrer(fournisseur.identifiant, fournisseur.cle_publique_hex)

    def cle_de(self, identifiant: str) -> str | None:
        """La clé publique connue pour cette partie, ou None si inconnue."""
        return self._cles.get(identifiant.strip() if identifiant else "")

    def connait(self, identifiant: str) -> bool:
        return self.cle_de(identifiant) is not None

    def verifier_scelle(
        self,
        scelle: Scelle | dict[str, Any],
        document: str | bytes,
    ) -> ResultatVerification:
        """Vérifie un sceau en cherchant la clé de référence dans le registre.

        Si le signataire déclaré est inconnu du registre, la vérification se
        poursuit sans clé de référence : l'intégrité sera contrôlée, mais
        l'attribution restera non établie, et l'anomalie le dira.
        """
        if isinstance(scelle, dict):
            scelle = Scelle.from_dict(scelle)
        reference = self.cle_de(scelle.identifiant_signataire)
        resultat = verifier(scelle, document, cle_publique_reference=reference)
        if reference is None:
            return ResultatVerification(
                valide=resultat.valide,
                document_intact=resultat.document_intact,
                signature_valide=resultat.signature_valide,
                attribution_etablie=False,
                motif=resultat.motif,
                anomalies=resultat.anomalies + [
                    f"« {scelle.identifiant_signataire} » ne figure pas au "
                    "registre des clés : son identité ne peut pas être "
                    "confirmée."
                ],
            )
        return resultat


# --- Utilitaire d'affichage -------------------------------------------------

def nettoyer_pour_affichage(texte: str) -> str:
    """Retire les caractères de contrôle invisibles d'un identifiant affiché.

    Un identifiant contenant des marques de direction bidirectionnelle peut
    s'afficher à l'écran autrement qu'il n'est stocké — un nom arabe et un
    nom latin peuvent être visuellement intervertis. Le sceau, lui, porte
    toujours les octets exacts : cette fonction ne sert QU'À l'affichage et
    n'est jamais appelée avant de signer.
    """
    return "".join(
        c for c in texte
        if unicodedata.category(c) not in ("Cc", "Cf") or c in "\n\t"
    )
