"""Les deux livrables institutionnels du brief §4 : l'acte et le greffe.

POST /documents/mise-en-demeure — le projet d'acte (إنذار) que la PME emporte.
GET  /greffe/dossiers           — le tableau du greffier du tribunal de commerce.

Deux règles gouvernent ce routeur, et elles ne sont pas négociables.

La première : Mizan RÉDIGE, elle ne SIGNIFIE pas. CPCC art. 5 et 60 réservent
la signification à l'huissier de justice (عدل منفذ). Tout ce qui sort d'ici
porte la mention « PROJET — NON SIGNIFIÉ », et le schéma de réponse la rend
obligatoire : un document sans mention ne peut littéralement pas être
sérialisé.

La seconde : aucun article de loi ne vient d'un modèle de langage. Les
citations sont celles que `legal_engine` a retenues, reproduites en arabe mot
pour mot depuis le corpus indexé. Ce routeur n'appelle aucun modèle.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from api import amorce  # noqa: F401  — installe sys.path avant les imports métier

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from packages.legal import greffe, notice
from packages.legal.legal_engine import DateImpossible, assess
from packages.legal.notice import CreancePrescrite

logger = logging.getLogger("mizan.api.documents")

routeur = APIRouter(tags=["documents"])


# ---------------------------------------------------------------------------
# Schémas
# ---------------------------------------------------------------------------

class DemandeMiseEnDemeure(BaseModel):
    montant_tnd: float = Field(
        gt=0, description="Montant réclamé en dinars tunisiens.",
        json_schema_extra={"example": 9520.0},
    )
    date_facture: str = Field(
        description="Date de la facture, au format AAAA-MM-JJ.",
        json_schema_extra={"example": "2026-05-12"},
    )
    activite: str = Field(
        default="menuiserie",
        description="Activité du créancier : elle décide du régime de prescription.",
    )
    creancier_nom: str = Field(
        default="", description="Nom du créancier tel qu'il figurera sur l'acte.")
    debiteur_nom: str = Field(
        default="", description="Nom du débiteur tel qu'il figurera sur l'acte.")
    creancier_adresse: str = ""
    creancier_ville: str = "Sfax"
    creancier_matricule: str = ""
    debiteur_adresse: str = ""
    numero_facture: str = ""
    aujourdhui: str | None = Field(
        default=None,
        description="Date de référence (AAAA-MM-JJ), pour des démonstrations "
                    "reproductibles. Par défaut, la date du jour.",
    )


class ArticleCite(BaseModel):
    code_id: str
    article: int
    citation_ar: str = Field(
        description="La citation arabe, reproduite mot pour mot depuis le corpus.")
    label_fr: str
    short_fr: str


class MiseEnDemeureRendue(BaseModel):
    """Le projet d'acte.

    `mention_projet` n'a pas de valeur par défaut : elle est obligatoire. Si
    un jour quelqu'un la retire du générateur, cette réponse cesse de se
    construire — l'API tombe en erreur plutôt que de livrer un document qui
    se ferait passer pour un acte signifié.
    """
    mention_projet: str
    mention_projet_longue: str
    signifie: bool = Field(
        default=False,
        description="Toujours faux. Mizan ne signifie pas : seul un huissier "
                    "de justice le peut (CPCC art. 5 et 60).",
    )
    texte: str = Field(description="Le projet d'acte, bilingue, en texte brut.")
    titre_fr: str
    titre_ar: str
    creancier: dict[str, Any]
    debiteur: dict[str, Any]
    facture: dict[str, Any]
    montant_tnd: float
    montant_fr: str
    corps: list[str]
    sommation_ar: list[str]
    delai_jours: int
    delai_est_legal: bool = Field(
        description="Vrai si le délai est celui de CPCC art. 60 ; faux s'il "
                    "s'agit d'un délai d'usage sous le seuil de l'huissier.",
    )
    date_limite: str
    huissier_requis: bool
    articles: list[ArticleCite]
    prescription: dict[str, Any]
    lieu: str
    date_acte: str
    avertissement: str
    origine: str = "moteur_deterministe"


class PieceGreffe(BaseModel):
    kind: str | None = None
    label: str | None = None
    sha256: str | None = None
    n_bytes: int | None = None
    gate_ok: bool | None = None
    gate_reason: str | None = None
    format: str | None = None


class Controle(BaseModel):
    controle: str
    libelle: str
    bloquant: bool


class DossierGreffe(BaseModel):
    reference: str | None = None
    etat: str | None = None
    etat_libelle: str | None = None
    depose_le: str | None = None
    mis_a_jour_le: str | None = None
    statut_depot: str | None = None
    parties: dict[str, Any] = {}
    creance: dict[str, Any] = {}
    prescription: dict[str, Any] = {}
    pieces: list[PieceGreffe] = []
    pieces_manquantes: list[dict[str, Any]] = []
    instruisable: bool = False
    fondement_juridique: list[dict[str, Any]] = []
    controles_a_effectuer: list[Controle] = []
    journal: list[dict[str, Any]] = []
    actions_possibles: list[dict[str, Any]] = []


class TableauGreffier(BaseModel):
    dossiers: list[DossierGreffe]
    etats: dict[str, str]
    controles: dict[str, str]
    charge: dict[str, int]
    statistiques: dict[str, Any]
    avertissement: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@routeur.post("/documents/mise-en-demeure", response_model=MiseEnDemeureRendue,
              summary="Projet de mise en demeure (إنذار) — non signifié")
def mise_en_demeure(demande: DemandeMiseEnDemeure) -> MiseEnDemeureRendue:
    """Rédige le projet de mise en demeure, articles cités à l'appui.

    L'ordre est toujours le même : le moteur déterministe calcule le régime de
    prescription et retient les articles, puis le générateur met en forme. Le
    générateur ne choisit aucun article et n'en invente aucun.

    Refus possibles, et ils sont voulus :
    - 400 si la date est impossible (facture datée de demain, montant nul) ;
    - 409 si la créance est PRESCRITE. Mettre en demeure sur une créance
      éteinte fait payer un huissier au créancier pour s'entendre opposer la
      prescription. Le refus est le bon service à lui rendre.
    """
    jour = None
    if demande.aujourdhui:
        try:
            jour = date.fromisoformat(demande.aujourdhui)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400,
                detail="Le champ « aujourdhui » doit être une date au format "
                       f"AAAA-MM-JJ. Reçu : « {demande.aujourdhui} ».",
            )

    try:
        evaluation = assess(demande.montant_tnd, demande.date_facture,
                            demande.activite, today=jour)
    except DateImpossible as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Date de facture illisible : {exc}. Format attendu : AAAA-MM-JJ.",
        )

    creancier = {
        'name': demande.creancier_nom or 'Le créancier',
        'address': demande.creancier_adresse,
        'tax_id': demande.creancier_matricule,
        'city': demande.creancier_ville,
    }
    debiteur = {
        'name': demande.debiteur_nom or 'Le débiteur',
        'address': demande.debiteur_adresse,
    }
    facture = {
        'invoice_no': demande.numero_facture,
        'invoice_date': demande.date_facture,
    }

    try:
        doc = notice.construire(evaluation, creancier, debiteur, facture)
    except CreancePrescrite as exc:
        # 409 et non 400 : la demande est bien formée, c'est l'état du droit
        # qui s'y oppose. Le client doit pouvoir distinguer les deux.
        raise HTTPException(status_code=409, detail=str(exc))

    d = doc.to_dict()

    # Ceinture après les bretelles. La mention est produite par le générateur
    # et le schéma l'exige déjà ; on vérifie en plus qu'elle est bien DANS le
    # texte livré. Un document dont l'en-tête annonce un projet mais dont le
    # corps ne le dit pas serait copié-collé sans sa mention.
    if notice.MENTION_PROJET not in d['texte']:
        logger.error("mention de projet absente du texte généré")
        raise HTTPException(
            status_code=500,
            detail="Le document généré ne porte pas la mention « projet — non "
                   "signifié ». Il n'est pas livré : Mizan ne produit pas de "
                   "document qui pourrait passer pour un acte signifié.",
        )

    return MiseEnDemeureRendue(**d, signifie=False)


@routeur.get("/greffe/dossiers", response_model=TableauGreffier,
             summary="Tableau greffier : la file et ses contrôles")
def greffe_dossiers(
    etat: str | None = Query(
        None, description="Filtre sur l'état : recu, recevable, incomplet, "
                          "mediation, injonction."),
) -> TableauGreffier:
    """La file du greffe, triée par ce qui est instruisable et urgent.

    La projection est une liste blanche (`greffe.vue_greffier`) : le contenu
    extrait des pièces, les coordonnées des parties et tout champ non
    explicitement autorisé restent côté créancier. Le greffier voit ce qui
    fonde la recevabilité — présence des pièces obligatoires, empreintes,
    prescription — et le contrôle que chaque dossier appelle.
    """
    if etat is not None and etat not in greffe.ETATS:
        raise HTTPException(
            status_code=400,
            detail=f"État inconnu : « {etat} ». États valides : "
                   f"{', '.join(greffe.ETATS)}.",
        )

    t = greffe.tableau()
    if etat is not None:
        dossiers = [d for d in t['dossiers'] if d['etat'] == etat]
        t = {**t, 'dossiers': dossiers, 'charge': {
            **t['charge'],
            'total': len(dossiers),
            'instruisables': sum(1 for d in dossiers if d['instruisable']),
        }}
    return TableauGreffier(**t)
