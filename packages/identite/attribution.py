"""Répondre au juge : QUI a signé, QUAND, et le document a-t-il changé ?

Pourquoi ce module est séparé de `signature.py`
------------------------------------------------
`signature.py` répond en termes cryptographiques : empreinte, signature
Ed25519, clé publique. Aucune de ces notions ne se plaide. Un magistrat, un
avocat ou le gérant d'une PME qui reçoit une mise en demeure n'a pas à savoir
ce qu'est une courbe elliptique pour comprendre si le document qu'il tient
est bien celui qui a été envoyé.

Ce module traduit. Il ne calcule rien de nouveau : il prend le résultat de
`verifier()` et l'énonce en français, avec ses réserves. Les réserves sont
la partie la plus importante : un rapport qui affirme plus que ce que la
technique établit est pire qu'un rapport qui n'affirme rien, parce qu'il
sera détruit à la première contestation sérieuse.

Ce que le rapport dit toujours, même quand tout va bien
--------------------------------------------------------
- que l'horodatage n'est pas un horodatage qualifié (RFC 3161) et ne vaut
  pas date certaine opposable à un tiers ;
- que la signature n'est pas une signature électronique qualifiée, faute de
  certificat délivré par un prestataire reconnu (TunTrust/ANCE) ;
- que sceller n'est pas signifier : un projet de mise en demeure scellé
  reste un projet non signifié, et seul un huissier (عدل منفذ) signifie.

Un rapport d'attribution honnête vaut mieux qu'un rapport flatteur.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any

from packages.identite.signature import (
    ResultatVerification,
    RegistreDeCles,
    Scelle,
    ScelleInvalide,
    nettoyer_pour_affichage,
    verifier,
)

MOIS_FR = ["", "janvier", "février", "mars", "avril", "mai", "juin",
           "juillet", "août", "septembre", "octobre", "novembre", "décembre"]

# Ces réserves accompagnent TOUT rapport, y compris ceux qui concluent à la
# validité. Elles sont des constantes pour qu'on ne puisse pas les oublier
# sur un chemin d'exécution particulier, et un test les verrouille.
RESERVE_HORODATAGE = (
    "L'heure indiquée est celle de la machine qui a scellé le document. Ce "
    "n'est pas un horodatage qualifié délivré par une autorité "
    "d'horodatage : il établit la cohérence interne du sceau, non une date "
    "certaine opposable à un tiers."
)

RESERVE_SIGNATURE = (
    "La signature est une signature technique produite par une clé générée "
    "localement. Ce n'est pas une signature électronique qualifiée : aucun "
    "certificat délivré par un prestataire de confiance reconnu "
    "(TunTrust/ANCE) n'atteste que le détenteur de cette clé est bien la "
    "personne nommée."
)

RESERVE_SIGNIFICATION = (
    "Sceller n'est pas signifier. Un projet de mise en demeure scellé reste "
    "un projet non signifié et ne produit aucun effet de droit : seul un "
    "huissier de justice (عدل منفذ) signifie, et c'est la signification qui "
    "fait courir les délais."
)

RESERVES_PERMANENTES: tuple[str, ...] = (
    RESERVE_HORODATAGE,
    RESERVE_SIGNATURE,
    RESERVE_SIGNIFICATION,
)


def _date_lisible(horodatage_iso: str) -> str:
    """« 2026-09-13T09:41:02+00:00 » → « 13 septembre 2026 à 09h41 (UTC) ».

    Le format ISO est exact mais illisible dans une pièce de procédure. Si
    l'horodatage est illisible, on le rend tel quel plutôt que d'inventer une
    date : un rapport ne corrige pas silencieusement ce qu'il constate.
    """
    try:
        d = datetime.fromisoformat(horodatage_iso)
    except (ValueError, TypeError):
        return f"date illisible ({horodatage_iso!r})"
    decalage = d.utcoffset()
    if decalage is None:
        fuseau = "fuseau non précisé"
    elif decalage.total_seconds() == 0:
        fuseau = "UTC"
    else:
        fuseau = d.tzname() or f"UTC{decalage}"
    return (
        f"{d.day} {MOIS_FR[d.month]} {d.year} à "
        f"{d.hour:02d}h{d.minute:02d} ({fuseau})"
    )


@dataclass(frozen=True)
class RapportAttribution:
    """La réponse aux trois questions, en français, avec ses réserves.

    Champs :
        signataire_declare  : le nom porté par le sceau.
        signataire_confirme : True seulement si une clé de référence connue
                              d'avance correspond. False signifie « je ne sais
                              pas qui c'est », pas « c'est un imposteur ».
        date_scellement     : l'horodatage, en français lisible.
        document_modifie    : True si le document présenté ne correspond plus.
        conclusion          : le paragraphe à lire en premier.
        details             : les constats, un par ligne.
        reserves            : ce que ce rapport n'établit PAS. Toujours rempli.
    """

    signataire_declare: str
    signataire_confirme: bool
    date_scellement: str
    document_modifie: bool
    conclusion: str
    details: list[str] = field(default_factory=list)
    reserves: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def en_texte(self) -> str:
        """Le rapport en texte brut, prêt à être joint à un dossier."""
        lignes: list[str] = []
        lignes.append("RAPPORT D'ATTRIBUTION")
        lignes.append("=" * 68)
        lignes.append("")
        lignes.append("QUI a scellé ce document ?")
        nom = nettoyer_pour_affichage(self.signataire_declare)
        if self.signataire_confirme:
            lignes.append(f"    {nom} — identité confirmée.")
        else:
            lignes.append(
                f"    Le sceau porte le nom « {nom} », mais cette identité "
                "n'est PAS confirmée."
            )
        lignes.append("")
        lignes.append("QUAND ?")
        lignes.append(f"    {self.date_scellement}")
        lignes.append("")
        lignes.append("Le document a-t-il été modifié depuis ?")
        lignes.append(
            "    OUI — le document présenté n'est pas celui qui a été scellé."
            if self.document_modifie else
            "    NON — le document est identique à celui qui a été scellé."
        )
        lignes.append("")
        lignes.append("CONCLUSION")
        lignes.append(f"    {self.conclusion}")
        if self.details:
            lignes.append("")
            lignes.append("CONSTATS")
            for d in self.details:
                lignes.append(f"    — {d}")
        lignes.append("")
        lignes.append("CE QUE CE RAPPORT N'ÉTABLIT PAS")
        for r in self.reserves:
            lignes.append(f"    — {r}")
        return "\n".join(lignes)


def attribuer(
    scelle: Scelle | dict[str, Any],
    document: str | bytes,
    *,
    registre: RegistreDeCles | None = None,
    cle_publique_reference: str | None = None,
) -> RapportAttribution:
    """Produit le rapport d'attribution d'un document scellé.

    C'est la fonction qu'on appelle quand quelqu'un conteste : « ce document
    n'est pas celui que j'ai reçu », ou « je n'ai jamais envoyé ça ».

    Args:
        scelle: le sceau apposé au moment de l'envoi.
        document: le document tel qu'il est produit aujourd'hui au débat.
        registre: le registre des clés publiques reconnues. C'est LUI qui
            permet de confirmer une identité ; sans registre ni clé de
            référence, le rapport conclura honnêtement qu'on ignore qui a
            signé.
        cle_publique_reference: alternative au registre, quand une seule clé
            est en cause et qu'elle a été reçue hors bande.

    Returns:
        Un `RapportAttribution` en français.

    Raises:
        ScelleInvalide: le sceau est illisible ou malformé.
    """
    if isinstance(scelle, dict):
        scelle = Scelle.from_dict(scelle)
    if not isinstance(scelle, Scelle):
        raise ScelleInvalide("L'attribution attend un sceau.")

    if registre is not None:
        resultat: ResultatVerification = registre.verifier_scelle(scelle, document)
    else:
        resultat = verifier(
            scelle, document, cle_publique_reference=cle_publique_reference
        )

    details: list[str] = list(resultat.anomalies)
    if resultat.document_intact:
        details.insert(
            0,
            "L'empreinte du document présenté correspond exactement à celle "
            "portée par le sceau : pas un caractère n'a changé.",
        )
    if resultat.signature_valide:
        details.insert(
            0,
            "La signature apposée sur le sceau est cohérente : ni le "
            "signataire déclaré, ni la date, ni le contexte n'ont été "
            "retouchés après signature.",
        )

    nom = nettoyer_pour_affichage(scelle.identifiant_signataire)

    if resultat.valide and resultat.attribution_etablie:
        conclusion = (
            f"Le document est intact et il a été scellé par {nom}. "
            "L'intéressé ne peut pas soutenir qu'il n'en est pas l'auteur "
            "sans contester la détention de sa propre clé, sous les réserves "
            "énoncées ci-dessous."
        )
    elif resultat.valide:
        conclusion = (
            "Le document n'a pas été modifié depuis son scellement, et le "
            "sceau est cohérent avec lui-même. En revanche, l'identité du "
            f"signataire n'est pas confirmée : le nom « {nom} » est celui que "
            "le sceau affirme, sans qu'aucune clé connue d'avance ne vienne "
            "l'établir."
        )
    elif not resultat.document_intact:
        conclusion = (
            "Le document produit aujourd'hui N'EST PAS celui qui a été "
            "scellé. Il a été modifié depuis, ou bien ce sceau appartient à "
            "un autre document. Dans les deux cas, il ne peut pas être "
            "opposé au signataire en l'état."
        )
    else:
        conclusion = (
            "La signature du sceau n'est pas valide : le sceau lui-même a "
            "été altéré, tronqué ou fabriqué. Il n'établit rien."
        )

    return RapportAttribution(
        signataire_declare=scelle.identifiant_signataire,
        signataire_confirme=resultat.attribution_etablie,
        date_scellement=_date_lisible(scelle.horodatage),
        document_modifie=not resultat.document_intact,
        conclusion=conclusion,
        details=details,
        reserves=list(RESERVES_PERMANENTES),
    )
