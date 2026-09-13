"""Schémas d'entrée et de sortie de l'API. Tout est en français."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# --- /sante -----------------------------------------------------------------

class EtatHebergement(BaseModel):
    nom: str
    base_url: str
    modele: str
    disponible: bool
    motif: str = Field(
        description="« ok » ou la cause exacte de l'indisponibilité."
    )


class Sante(BaseModel):
    service: str
    version: str
    moteur_juridique: Literal["deterministe"]
    modele_disponible: bool
    motif_modele: str
    hebergements: list[EtatHebergement]
    articles_indexes: int
    index_charge: bool
    principe: str


# --- /dossiers/analyser -----------------------------------------------------

class ActeInterruptifEntree(BaseModel):
    """Un acte invoqué comme ayant interrompu la prescription (COC 396-398)."""
    type: Literal[
        "sommation_huissier",
        "demande_justice",
        "saisie_conservatoire",
        "reconnaissance_dette",
        "paiement_partiel",
        "arrete_compte",
    ] = Field(
        description="Nature de l'acte. Les trois premiers émanent du créancier "
                    "(COC art. 396), les trois derniers du débiteur "
                    "(COC art. 397).",
        json_schema_extra={"example": "sommation_huissier"},
    )
    date: str = Field(
        description="Date de l'acte, au format AAAA-MM-JJ.",
        json_schema_extra={"example": "2026-09-01"},
    )
    description: str = Field(
        default="",
        description="Précision libre : nom de l'huissier, référence du reçu…",
    )


class DemandeAnalyse(BaseModel):
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
    aujourdhui: str | None = Field(
        default=None,
        description="Date de référence (AAAA-MM-JJ). Sert aux tests et aux "
                    "démonstrations reproductibles ; par défaut, la date du jour.",
    )
    actes_interruptifs: list[ActeInterruptifEntree] = Field(
        default_factory=list,
        description="Actes ayant interrompu la prescription (COC art. 396 et "
                    "397). Chaque interruption valide annule le temps écoulé "
                    "et fait repartir le délai à zéro (COC art. 398). Un acte "
                    "postérieur à l'expiration n'interrompt rien.",
    )


class Source(BaseModel):
    code_id: str
    article: int
    citation_ar: str
    label_fr: str
    short_fr: str


class Etape(BaseModel):
    order: int
    title_fr: str
    detail_fr: str
    citation_ar: str
    code_id: str
    article: int


class InterruptionRetenue(BaseModel):
    """Une interruption effectivement retenue par le moteur."""
    type: str
    libelle_fr: str
    date: str
    description: str = ""
    article_cause: int = Field(
        description="396 (acte du créancier) ou 397 (reconnaissance du débiteur)."
    )
    fondement_fr: str
    effet_fr: str
    nouvelle_echeance: str
    articles: list[Source]


class ActeSansEffet(BaseModel):
    """Un acte produit mais qui n'a rien interrompu, avec le motif."""
    type: str
    libelle_fr: str
    date: str
    description: str = ""
    motif_fr: str
    articles: list[Source]


class Interruption(BaseModel):
    """Le sort de la prescription : interrompue ou non, par quoi, de combien."""
    interrompu: bool = Field(
        description="Le délai a-t-il été interrompu par au moins un acte valide ?"
    )
    date_depart_initiale: str
    date_depart_effective: str = Field(
        description="Date à partir de laquelle le délai court réellement, "
                    "après application de COC art. 398."
    )
    echeance_initiale: str
    echeance_effective: str
    jours_gagnes: int = Field(
        description="Nombre de jours dont la créance a été prolongée par "
                    "l'interruption. Zéro si aucun acte n'a produit d'effet."
    )
    interruptions: list[InterruptionRetenue]
    actes_sans_effet: list[ActeSansEffet]
    sources: list[Source]
    resume_fr: str


class Analyse(BaseModel):
    montant_tnd: float
    date_facture: str
    aujourdhui: str
    regime: str
    regime_reason_fr: str
    echeance: str
    jours_restants: int
    est_prescrit: bool
    urgence: str
    huissier_requis: bool
    jours_francs: int
    sources: list[Source]
    etapes: list[Etape]
    interruption: Interruption | None = Field(
        default=None,
        description="Renseigné uniquement si des actes interruptifs ont été "
                    "transmis. Absent sinon : le délai court alors sans "
                    "interruption depuis la facture.",
    )
    origine: Literal["moteur_deterministe"] = "moteur_deterministe"


# --- /dossiers/deposer-piece ------------------------------------------------

class PieceDeposee(BaseModel):
    acceptee: bool
    nom_fichier: str
    sha256: str
    taille_octets: int
    methode_extraction: str | None = None
    motif_refus: str | None = None
    indices_trouves: list[str] = []
    indices_manquants: list[str] = []
    ligne_montant: str | None = None
    montant_tnd: float | None = None
    date_facture: str | None = None
    dates_trouvees: list[str] = []
    numero_facture: str | None = None
    client: str | None = None
    avertissement: str


# --- /corpus/rechercher -----------------------------------------------------

class ArticleTrouve(BaseModel):
    id: str
    code_id: str
    code_fr: str
    code_ar: str
    article: int | str
    citation_ar: str
    text_ar: str
    score: float


class Recherche(BaseModel):
    requete: str
    nombre: int
    fonde: bool = Field(
        description="Verdict du garde-fou d'abstention : le corpus répond-il "
                    "vraiment à cette question ?"
    )
    motif_abstention: str | None = None
    message: str | None = None
    resultats: list[ArticleTrouve]


# --- /assistant/expliquer ---------------------------------------------------

class DemandeExplication(BaseModel):
    """L'évaluation à reformuler.

    On accepte soit une analyse déjà produite par /dossiers/analyser (champ
    `analyse`), soit les trois valeurs qui permettent de la recalculer. Dans
    les deux cas, l'API recalcule ou revalide côté moteur : aucune donnée
    juridique n'est acceptée sur parole depuis le client.
    """
    analyse: dict[str, Any] | None = None
    montant_tnd: float | None = None
    date_facture: str | None = None
    activite: str = "menuiserie"
    aujourdhui: str | None = None
    question: str | None = Field(
        default=None,
        description="Question libre de la PME, facultative.",
    )


class Explication(BaseModel):
    texte: str
    origine: Literal["local", "modal", "aucune"]
    duree_s: float
    mode_degrade: bool
    motif_degradation: str | None = None
    analyse: Analyse
    sources: list[Source]
    avertissement: str
