"""Les dossiers, rangés par organisation.

POURQUOI CE FICHIER EXISTE
--------------------------
Le cloisonnement entre organisations ne se démontre pas sur une base vide. Si
l'entreprise B n'a aucun dossier, refuser à l'entreprise A de les lire ne prouve
rien du tout : on ne saurait pas distinguer un cloisonnement qui fonctionne
d'une base qui ne contient rien.

Ce dépôt en mémoire contient donc de vrais dossiers pour PLUSIEURS
organisations. Le test hostile peut alors vérifier ce qui compte : que les
dossiers de l'autre entreprise existent bel et bien, et que l'agent est
malgré tout incapable de les atteindre.

Il s'agit d'un jeu d'essai pour la démonstration ; en production, ces dossiers
viendront de la base PostgreSQL dont le schéma se trouve dans `db/schema.sql`,
avec le même invariant : la clause de restriction par organisation est posée
par le serveur, jamais par l'appelant.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DossierClient:
    """Un dossier de recouvrement, tel qu'il apparaît à son propriétaire."""

    reference: str
    organisation: str
    debiteur: str
    montant_tnd: float
    date_facture: str
    activite: str = "menuiserie"
    etat: str = "en cours"

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "debiteur": self.debiteur,
            "montant_tnd": self.montant_tnd,
            "date_facture": self.date_facture,
            "activite": self.activite,
            "etat": self.etat,
        }


@dataclass
class DepotDossiers:
    """Le dépôt. Une seule méthode de lecture, et elle exige l'organisation.

    Il n'existe volontairement aucune méthode `tous()` ni `par_reference()`
    sans organisation. Une méthode qui rendrait tous les dossiers de la
    plateforme serait, tôt ou tard, appelée depuis un endroit où l'on aurait
    oublié de filtrer. On ne la fournit donc pas.
    """

    _par_organisation: dict[str, list[DossierClient]] = field(default_factory=dict)

    def ajouter(self, dossier: DossierClient) -> None:
        self._par_organisation.setdefault(dossier.organisation, []).append(dossier)

    def de_l_organisation(self, organisation: str) -> list[DossierClient]:
        """Les dossiers de CETTE organisation, et rien d'autre.

        Une organisation inconnue reçoit une liste vide — la même réponse
        qu'une organisation connue mais sans dossier. C'est délibéré : la
        différence entre les deux réponses renseignerait sur l'existence d'un
        client de la plateforme.
        """
        return list(self._par_organisation.get(organisation, ()))


def depot_demonstration() -> DepotDossiers:
    """Le jeu d'essai : deux organisations distinctes, chacune avec ses dossiers.

    Les noms sont fictifs. « Menuiserie Ahmed » est le dossier fil rouge de la
    démonstration Mizan ; « Société Hela Textile » n'existe que pour prouver que
    l'agent d'Ahmed ne peut pas la lire.
    """
    depot = DepotDossiers()
    depot.ajouter(DossierClient(
        reference="MIZ-2026-0001",
        organisation="org-ahmed",
        debiteur="Société Le Bon Meuble",
        montant_tnd=9520.0,
        date_facture="2025-11-04",
        activite="menuiserie",
    ))
    depot.ajouter(DossierClient(
        reference="MIZ-2026-0002",
        organisation="org-ahmed",
        debiteur="Résidence Les Oliviers",
        montant_tnd=3100.0,
        date_facture="2026-02-18",
        activite="menuiserie",
    ))
    # L'organisation témoin : ses dossiers EXISTENT, et c'est le but.
    depot.ajouter(DossierClient(
        reference="MIZ-2026-0044",
        organisation="org-hela",
        debiteur="Confection du Sahel",
        montant_tnd=48000.0,
        date_facture="2025-12-01",
        activite="textile",
    ))
    return depot
