"""
Annuaire des professionnels accrédités : profils, notation vérifiée, mise en relation.

Pourquoi ce module existe. MIZAN règle des litiges à l'amiable, et un règlement
amiable est conduit par un être humain accrédité : conciliateur, médiateur,
arbitre ou avocat. Sans eux, la plateforme n'a aucun opérateur. Trouver le bon
professionnel n'est donc pas une commodité, c'est une condition de
fonctionnement.

Trois garde-fous structurent tout le fichier.

1. L'IA RECOMMANDE, les parties CHOISISSENT. Le moteur rend une liste ORDONNÉE
   de propositions motivées. Il ne désigne jamais d'office, et il n'existe
   volontairement aucune fonction qui renvoie un professionnel unique.

2. Une note doit être adossée à un dossier réellement clôturé. Une note achetée
   sans dossier est une note qui ment : `Annuaire.noter` refuse, avec un motif
   lisible, toute notation qui ne s'appuie pas sur une résolution terminée.

3. Un professionnel déjà intervenu pour la partie adverse est écarté, sans
   arbitrage de score. Le conflit d'intérêts n'est pas une pénalité, c'est une
   exclusion.

Quand rien ne correspond, le moteur le dit en toutes lettres. Une liste vide
silencieuse laisserait croire à une panne d'affichage ; l'abstention est un
résultat, et elle est écrite.

Dépendances : bibliothèque standard uniquement.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Literal, Mapping, Sequence

__all__ = [
    "Annuaire",
    "Avis",
    "ConflitInterets",
    "Dossier",
    "GOUVERNORATS",
    "Litige",
    "NotationRefusee",
    "ProfilInvalide",
    "Professionnel",
    "Proposition",
    "Recommandation",
    "QUALITES",
    "VOIES",
]

# --------------------------------------------------------------------------
# Vocabulaire métier
# --------------------------------------------------------------------------

Qualite = Literal["avocat", "conciliateur", "mediateur", "arbitre"]
Voie = Literal["mediation", "conciliation", "arbitrage", "conseil"]
Langue = Literal["francais", "arabe"]

QUALITES: frozenset[str] = frozenset({"avocat", "conciliateur", "mediateur", "arbitre"})
VOIES: frozenset[str] = frozenset({"mediation", "conciliation", "arbitrage", "conseil"})
LANGUES: frozenset[str] = frozenset({"francais", "arabe"})

#: Domaines d'expertise reconnus par la plateforme.
EXPERTISES: frozenset[str] = frozenset(
    {
        "mediation",
        "conciliation",
        "arbitrage",
        "commercial",
        "travail",
        "construction",
        "bail",
        "recouvrement",
    }
)

#: Les 24 gouvernorats tunisiens. Un ressort hors de cette liste est un profil
#: invalide : on préfère refuser l'inscription que recommander une adresse fausse.
GOUVERNORATS: frozenset[str] = frozenset(
    {
        "ariana",
        "beja",
        "ben arous",
        "bizerte",
        "gabes",
        "gafsa",
        "jendouba",
        "kairouan",
        "kasserine",
        "kebili",
        "kef",
        "mahdia",
        "manouba",
        "medenine",
        "monastir",
        "nabeul",
        "sfax",
        "sidi bouzid",
        "siliana",
        "sousse",
        "tataouine",
        "tozeur",
        "tunis",
        "zaghouan",
    }
)

#: Voisinage géographique simplifié, utilisé uniquement pour nuancer la
#: proximité (« même gouvernorat » > « gouvernorat limitrophe » > « éloigné »).
#: Ce n'est pas une carte administrative, c'est une aide au classement.
_LIMITROPHES: Mapping[str, frozenset[str]] = {
    "tunis": frozenset({"ariana", "ben arous", "manouba"}),
    "ariana": frozenset({"tunis", "manouba", "bizerte", "ben arous"}),
    "ben arous": frozenset({"tunis", "ariana", "manouba", "zaghouan", "nabeul"}),
    "manouba": frozenset({"tunis", "ariana", "ben arous", "bizerte", "beja", "zaghouan"}),
    "nabeul": frozenset({"ben arous", "zaghouan", "sousse"}),
    "zaghouan": frozenset({"ben arous", "manouba", "nabeul", "sousse", "kairouan", "siliana"}),
    "bizerte": frozenset({"ariana", "manouba", "beja"}),
    "beja": frozenset({"bizerte", "manouba", "jendouba", "siliana", "kef"}),
    "jendouba": frozenset({"beja", "kef", "siliana"}),
    "kef": frozenset({"jendouba", "beja", "siliana", "kasserine"}),
    "siliana": frozenset({"kef", "beja", "zaghouan", "kairouan", "kasserine"}),
    "sousse": frozenset({"nabeul", "zaghouan", "kairouan", "monastir", "mahdia"}),
    "monastir": frozenset({"sousse", "mahdia"}),
    "mahdia": frozenset({"monastir", "sousse", "kairouan", "sfax"}),
    "kairouan": frozenset({"sousse", "zaghouan", "siliana", "kasserine", "sidi bouzid", "mahdia", "sfax"}),
    "kasserine": frozenset({"kef", "siliana", "kairouan", "sidi bouzid", "gafsa"}),
    "sidi bouzid": frozenset({"kairouan", "kasserine", "gafsa", "sfax", "mahdia"}),
    "sfax": frozenset({"mahdia", "kairouan", "sidi bouzid", "gabes", "gafsa"}),
    "gafsa": frozenset({"kasserine", "sidi bouzid", "sfax", "gabes", "tozeur", "kebili"}),
    "tozeur": frozenset({"gafsa", "kebili"}),
    "kebili": frozenset({"tozeur", "gafsa", "gabes", "tataouine"}),
    "gabes": frozenset({"sfax", "gafsa", "kebili", "medenine"}),
    "medenine": frozenset({"gabes", "tataouine"}),
    "tataouine": frozenset({"medenine", "kebili"}),
}

#: Qualités compétentes pour conduire chaque voie de règlement.
#: L'avocat assiste dans toutes les voies ; il ne tranche que par le conseil.
_QUALITES_PAR_VOIE: Mapping[str, frozenset[str]] = {
    "mediation": frozenset({"mediateur", "avocat"}),
    "conciliation": frozenset({"conciliateur", "avocat"}),
    "arbitrage": frozenset({"arbitre", "avocat"}),
    "conseil": frozenset({"avocat"}),
}

#: Natures de litige fréquentes rattachées à leurs domaines d'expertise.
#: Sert à élargir un mot-clé isolé (« impayé » → « recouvrement »).
_SYNONYMES_NATURE: Mapping[str, frozenset[str]] = {
    "impaye": frozenset({"recouvrement", "commercial"}),
    "impayes": frozenset({"recouvrement", "commercial"}),
    "facture": frozenset({"recouvrement", "commercial"}),
    "creance": frozenset({"recouvrement", "commercial"}),
    "recouvrement": frozenset({"recouvrement"}),
    "commercial": frozenset({"commercial"}),
    "loyer": frozenset({"bail"}),
    "bail": frozenset({"bail"}),
    "location": frozenset({"bail"}),
    "licenciement": frozenset({"travail"}),
    "travail": frozenset({"travail"}),
    "salaire": frozenset({"travail"}),
    "chantier": frozenset({"construction"}),
    "construction": frozenset({"construction"}),
    "malfacon": frozenset({"construction"}),
}


class ProfilInvalide(ValueError):
    """Le profil professionnel ne peut pas entrer à l'annuaire (motif en français)."""


class NotationRefusee(ValueError):
    """La note n'est pas adossée à une résolution réellement terminée."""


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------


def _normaliser(texte: str) -> str:
    """
    Ramène un libellé à sa forme comparable : minuscules, sans accent latin,
    espaces resserrés.

    Les caractères arabes traversent la fonction sans être altérés : un nom
    écrit « محمد الطرابلسي » doit rester lisible, seule la casse latine est
    concernée.
    """
    if not isinstance(texte, str):
        raise ProfilInvalide("Un libellé texte était attendu.")
    decompose = unicodedata.normalize("NFD", texte.strip().lower())
    sans_accent = "".join(c for c in decompose if unicodedata.category(c) != "Mn")
    return " ".join(unicodedata.normalize("NFC", sans_accent).split())


def _normaliser_mots_cles(mots: Iterable[str]) -> frozenset[str]:
    """Normalise une collection de mots-clés en écartant les entrées vides."""
    return frozenset(m for m in (_normaliser(mot) for mot in mots) if m)


# --------------------------------------------------------------------------
# Modèle de données
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Professionnel:
    """
    Profil d'un professionnel accrédité.

    Un profil sans numéro d'inscription à l'ordre ou d'accréditation n'est pas
    un profil incomplet : c'est un profil refusé. La plateforme ne met en
    relation que des praticiens dont l'habilitation peut être vérifiée auprès
    de l'autorité qui l'a délivrée.

    Attributs :
        identifiant : clé technique stable (ex. « pro-001 »).
        nom : nom d'usage, en caractères latins ou arabes.
        qualite : avocat, conciliateur, mediateur ou arbitre.
        numero_accreditation : numéro d'inscription à l'ordre ou d'accréditation.
        expertises : mots-clés de domaines (voir EXPERTISES).
        langues : langues de travail (francais, arabe).
        gouvernorat : ressort géographique principal.
        montant_minimum_dt : seuil en dinars en dessous duquel le professionnel
            n'accepte pas de dossier (0 = pas de seuil).
        actif : un professionnel suspendu reste en base mais n'est plus proposé.
    """

    identifiant: str
    nom: str
    qualite: Qualite
    numero_accreditation: str
    expertises: frozenset[str]
    langues: frozenset[str]
    gouvernorat: str
    montant_minimum_dt: float = 0.0
    actif: bool = True

    @staticmethod
    def creer(
        identifiant: str,
        nom: str,
        qualite: str,
        numero_accreditation: str,
        expertises: Sequence[str],
        langues: Sequence[str],
        gouvernorat: str,
        montant_minimum_dt: float = 0.0,
        actif: bool = True,
    ) -> "Professionnel":
        """
        Construit un profil valide ou lève `ProfilInvalide` avec un motif clair.

        Les vérifications sont faites ici, à l'entrée, plutôt qu'au moment de la
        recommandation : un annuaire ne doit jamais contenir un praticien qu'on
        serait incapable de justifier devant un juriste.
        """
        if not _normaliser(identifiant):
            raise ProfilInvalide("Identifiant manquant : un profil doit être adressable.")
        if not nom or not nom.strip():
            raise ProfilInvalide("Nom manquant : un profil anonyme ne peut pas être proposé.")

        qualite_n = _normaliser(qualite)
        if qualite_n not in QUALITES:
            raise ProfilInvalide(
                f"Qualité inconnue « {qualite} ». Attendu : "
                + ", ".join(sorted(QUALITES))
                + "."
            )

        if not numero_accreditation or not numero_accreditation.strip():
            raise ProfilInvalide(
                f"{nom} n'a pas de numéro d'inscription à l'ordre ou d'accréditation : "
                "profil refusé, la plateforme ne met en relation que des professionnels "
                "dont l'habilitation est vérifiable."
            )

        gouvernorat_n = _normaliser(gouvernorat)
        if gouvernorat_n not in GOUVERNORATS:
            raise ProfilInvalide(
                f"Ressort géographique inconnu « {gouvernorat} » : "
                "un gouvernorat tunisien était attendu."
            )

        langues_n = _normaliser_mots_cles(langues)
        if not langues_n:
            raise ProfilInvalide(f"{nom} : aucune langue de travail déclarée.")
        inconnues = langues_n - LANGUES
        if inconnues:
            raise ProfilInvalide(
                "Langue non prise en charge : " + ", ".join(sorted(inconnues)) + "."
            )

        expertises_n = _normaliser_mots_cles(expertises)
        if not expertises_n:
            raise ProfilInvalide(f"{nom} : aucun domaine d'expertise déclaré.")

        if montant_minimum_dt < 0:
            raise ProfilInvalide("Le montant minimum de dossier ne peut pas être négatif.")

        return Professionnel(
            identifiant=_normaliser(identifiant),
            nom=nom.strip(),
            qualite=qualite_n,  # type: ignore[arg-type]
            numero_accreditation=numero_accreditation.strip(),
            expertises=expertises_n,
            langues=langues_n,  # type: ignore[arg-type]
            gouvernorat=gouvernorat_n,
            montant_minimum_dt=float(montant_minimum_dt),
            actif=actif,
        )

    def libelle_qualite(self) -> str:
        """Rend la qualité en français lisible (« médiateur », « arbitre »…)."""
        return {
            "avocat": "avocat",
            "conciliateur": "conciliateur",
            "mediateur": "médiateur",
            "arbitre": "arbitre",
        }[self.qualite]

    def qualite_elidee(self) -> str:
        """
        Rend la qualité précédée de « de » ou « d' » selon l'initiale.

        Détail de forme, mais ce texte est lu par un juriste : « qualité de
        avocat » décrédibilise une phrase par ailleurs juste.
        """
        libelle = self.libelle_qualite()
        return f"d'{libelle}" if libelle[0] in "aeiouyéèêh" else f"de {libelle}"


@dataclass(frozen=True)
class Dossier:
    """
    Un dossier confié à un professionnel.

    C'est la seule preuve qu'une relation de travail a existé. La notation s'y
    adosse, et la détection de conflit d'intérêts s'y adosse aussi.

    Attributs :
        identifiant : référence du dossier.
        parties : identifiants des parties (demandeur, défendeur…).
        professionnel : identifiant du professionnel intervenu.
        cloture : vrai si la résolution est terminée.
    """

    identifiant: str
    parties: frozenset[str]
    professionnel: str
    cloture: bool = False

    @staticmethod
    def creer(
        identifiant: str,
        parties: Sequence[str],
        professionnel: str,
        cloture: bool = False,
    ) -> "Dossier":
        """Construit un dossier normalisé (identifiants ramenés en minuscules)."""
        parties_n = _normaliser_mots_cles(parties)
        if not parties_n:
            raise ValueError("Un dossier sans partie n'a pas de sens.")
        return Dossier(
            identifiant=_normaliser(identifiant),
            parties=parties_n,
            professionnel=_normaliser(professionnel),
            cloture=bool(cloture),
        )


@dataclass(frozen=True)
class Avis:
    """
    Une note vérifiée : étoiles de 1 à 5, rattachée à un dossier clôturé.

    L'avis ne peut pas exister sans `dossier` : le champ n'est pas optionnel,
    et c'est volontaire.
    """

    professionnel: str
    auteur: str
    dossier: str
    etoiles: int
    commentaire: str = ""


@dataclass(frozen=True)
class ConflitInterets:
    """Constat d'un conflit d'intérêts, avec le dossier qui le fonde."""

    professionnel: str
    partie_adverse: str
    dossier: str

    def explication(self, nom_professionnel: str) -> str:
        """Phrase d'explication destinée à l'écran et au procès-verbal."""
        return (
            f"{nom_professionnel} est écarté : il est déjà intervenu pour la partie "
            f"adverse ({self.partie_adverse}) dans le dossier {self.dossier}."
        )


@dataclass(frozen=True)
class Litige:
    """
    Le litige pour lequel on cherche un professionnel.

    Attributs :
        nature : mots-clés décrivant le litige (« recouvrement », « commercial »…).
        montant_dt : montant réclamé en dinars tunisiens.
        gouvernorat : ressort du litige ; peut être absent (None), auquel cas la
            proximité géographique ne peut pas être invoquée et le moteur le dit.
        langue : langue de travail souhaitée par les parties.
        voie : voie de règlement choisie (médiation, conciliation, arbitrage, conseil).
        demandeur : identifiant de la partie demanderesse.
        partie_adverse : identifiant de la partie adverse, utilisé pour la garde
            anti-conflit d'intérêts.
    """

    nature: frozenset[str]
    montant_dt: float
    gouvernorat: str | None
    langue: str
    voie: str
    demandeur: str = ""
    partie_adverse: str = ""

    @staticmethod
    def creer(
        nature: Sequence[str] | str,
        montant_dt: float,
        gouvernorat: str | None,
        langue: str,
        voie: str,
        demandeur: str = "",
        partie_adverse: str = "",
    ) -> "Litige":
        """
        Construit un litige normalisé.

        Un gouvernorat absent est accepté : beaucoup de saisines arrivent
        incomplètes, et refuser la recherche serait pire que la conduire sans
        critère de proximité.
        """
        mots = [nature] if isinstance(nature, str) else list(nature)
        nature_n = _normaliser_mots_cles(mots)

        gouvernorat_n: str | None = None
        if gouvernorat is not None and _normaliser(gouvernorat):
            candidat = _normaliser(gouvernorat)
            gouvernorat_n = candidat if candidat in GOUVERNORATS else None

        langue_n = _normaliser(langue) or "francais"
        voie_n = _normaliser(voie)

        try:
            montant = float(montant_dt)
        except (TypeError, ValueError) as erreur:
            raise ValueError("Montant du litige illisible.") from erreur
        if montant < 0:
            raise ValueError("Le montant d'un litige ne peut pas être négatif.")

        return Litige(
            nature=nature_n,
            montant_dt=montant,
            gouvernorat=gouvernorat_n,
            langue=langue_n,
            voie=voie_n,
            demandeur=_normaliser(demandeur),
            partie_adverse=_normaliser(partie_adverse),
        )

    def domaines(self) -> frozenset[str]:
        """
        Domaines d'expertise déduits de la nature du litige.

        Un utilisateur écrit « impayé », pas « recouvrement ». La table de
        synonymes fait la traduction ; les mots inconnus sont conservés tels
        quels, pour qu'une expertise exacte puisse quand même matcher.
        """
        domaines: set[str] = set()
        for mot in self.nature:
            domaines |= set(_SYNONYMES_NATURE.get(mot, frozenset({mot})))
        return frozenset(domaines)


@dataclass(frozen=True)
class Proposition:
    """
    Une proposition motivée. Ce n'est pas une désignation : les parties restent
    libres de retenir le troisième de la liste, ou aucun.
    """

    professionnel: Professionnel
    score: float
    note_moyenne: float | None
    nombre_avis: int
    motifs: tuple[str, ...]

    def explication(self) -> str:
        """Rend les motifs en une phrase française lisible à l'écran."""
        return " ".join(self.motifs)


@dataclass(frozen=True)
class Recommandation:
    """
    Résultat complet d'une recherche : des propositions ordonnées, les motifs
    d'écartement, et une abstention explicite quand rien ne correspond.
    """

    propositions: tuple[Proposition, ...]
    ecartes: tuple[str, ...] = ()
    message: str = ""
    abstention: bool = False

    def __bool__(self) -> bool:
        return bool(self.propositions)

    def texte(self) -> str:
        """
        Rend la recommandation sous forme de texte destiné aux parties.

        Le rappel « la décision vous appartient » n'est pas décoratif : c'est la
        règle du projet, et elle doit apparaître sur la même page que la liste.
        """
        if self.abstention:
            return self.message
        lignes = [self.message] if self.message else []
        for rang, proposition in enumerate(self.propositions, start=1):
            pro = proposition.professionnel
            lignes.append(
                f"{rang}. {pro.nom} — {pro.libelle_qualite()} "
                f"({pro.gouvernorat.title()}, accréditation {pro.numero_accreditation})"
            )
            lignes.append(f"   Pourquoi : {proposition.explication()}")
        lignes.append(
            "Ces professionnels vous sont proposés, pas imposés : "
            "le choix appartient aux parties."
        )
        return "\n".join(lignes)


# --------------------------------------------------------------------------
# Moteur
# --------------------------------------------------------------------------

_ABSTENTION = "Aucun professionnel accrédité ne correspond"


@dataclass
class Annuaire:
    """
    Registre des professionnels, des dossiers et des avis vérifiés.

    L'annuaire est volontairement en mémoire : à ce stade du projet, la
    persistance est un détail d'infrastructure, la règle métier ne l'est pas.
    """

    professionnels: dict[str, Professionnel] = field(default_factory=dict)
    dossiers: dict[str, Dossier] = field(default_factory=dict)
    avis: list[Avis] = field(default_factory=list)

    # ---------------------------------------------------------------- profils

    def inscrire(self, professionnel: Professionnel) -> None:
        """Ajoute un profil déjà validé ; refuse un doublon d'identifiant."""
        if professionnel.identifiant in self.professionnels:
            raise ProfilInvalide(
                f"Identifiant déjà utilisé : {professionnel.identifiant}."
            )
        if not professionnel.numero_accreditation.strip():
            raise ProfilInvalide(
                f"{professionnel.nom} n'a pas de numéro d'accréditation : profil refusé."
            )
        self.professionnels[professionnel.identifiant] = professionnel

    def enregistrer_dossier(self, dossier: Dossier) -> None:
        """Enregistre ou met à jour un dossier (la clôture est une mise à jour)."""
        self.dossiers[dossier.identifiant] = dossier

    def cloturer(self, identifiant_dossier: str) -> None:
        """Marque un dossier comme clôturé, ouvrant le droit de noter."""
        cle = _normaliser(identifiant_dossier)
        dossier = self.dossiers.get(cle)
        if dossier is None:
            raise KeyError(f"Dossier inconnu : {identifiant_dossier}")
        self.dossiers[cle] = Dossier(
            identifiant=dossier.identifiant,
            parties=dossier.parties,
            professionnel=dossier.professionnel,
            cloture=True,
        )

    # --------------------------------------------------------------- notation

    def noter(
        self,
        professionnel: str,
        auteur: str,
        dossier: str,
        etoiles: int,
        commentaire: str = "",
    ) -> Avis:
        """
        Enregistre une note d'étoiles, à la condition stricte qu'elle soit
        adossée à une résolution réellement terminée.

        Sont refusés, avec un motif explicite :
          - un nombre d'étoiles hors de la fourchette 1 à 5 (0, 6, -1) ;
          - un dossier inconnu de la plateforme ;
          - un dossier non clôturé (la résolution n'est pas terminée) ;
          - un auteur qui n'était pas partie à ce dossier ;
          - un professionnel qui n'est pas celui intervenu au dossier ;
          - une seconde note du même auteur sur le même dossier.

        Lève :
            NotationRefusee : avec le motif, en français.
        """
        if isinstance(etoiles, bool) or not isinstance(etoiles, int):
            raise NotationRefusee(
                "Note refusée : le nombre d'étoiles doit être un entier de 1 à 5."
            )
        if not 1 <= etoiles <= 5:
            raise NotationRefusee(
                f"Note refusée : {etoiles} étoiles est hors de la fourchette 1 à 5."
            )

        cle_dossier = _normaliser(dossier)
        cle_pro = _normaliser(professionnel)
        cle_auteur = _normaliser(auteur)

        reference = self.dossiers.get(cle_dossier)
        if reference is None:
            raise NotationRefusee(
                f"Note refusée : aucun dossier « {dossier} » sur la plateforme. "
                "Une note sans dossier est une note qui ment."
            )
        if not reference.cloture:
            raise NotationRefusee(
                f"Note refusée : le dossier {reference.identifiant} n'est pas clôturé. "
                "Seule une résolution terminée ouvre le droit de noter."
            )
        if cle_auteur not in reference.parties:
            raise NotationRefusee(
                f"Note refusée : {auteur} n'était pas partie au dossier "
                f"{reference.identifiant}."
            )
        if reference.professionnel != cle_pro:
            raise NotationRefusee(
                f"Note refusée : le dossier {reference.identifiant} n'a pas été conduit "
                f"par {professionnel}."
            )
        if any(a.dossier == cle_dossier and a.auteur == cle_auteur for a in self.avis):
            raise NotationRefusee(
                f"Note refusée : {auteur} a déjà noté le dossier {reference.identifiant}."
            )

        avis = Avis(
            professionnel=cle_pro,
            auteur=cle_auteur,
            dossier=cle_dossier,
            etoiles=etoiles,
            commentaire=commentaire.strip(),
        )
        self.avis.append(avis)
        return avis

    def note_moyenne(self, professionnel: str) -> tuple[float | None, int]:
        """
        Rend (moyenne arrondie au dixième, nombre d'avis).

        Sans avis, la moyenne est None et non zéro : un professionnel nouveau
        n'est pas un mauvais professionnel, et l'écran doit pouvoir écrire
        « pas encore noté ».
        """
        cle = _normaliser(professionnel)
        notes = [a.etoiles for a in self.avis if a.professionnel == cle]
        if not notes:
            return None, 0
        return round(sum(notes) / len(notes), 1), len(notes)

    # ------------------------------------------------- conflit d'intérêts

    def conflit_interets(
        self, professionnel: str, partie_adverse: str
    ) -> ConflitInterets | None:
        """
        Cherche un dossier où ce professionnel est intervenu alors que la partie
        adverse y était partie.

        Peu importe que ce dossier soit clos ou en cours : un praticien qui a
        travaillé sur le dossier de l'adversaire ne peut pas être proposé ici.
        """
        cle_pro = _normaliser(professionnel)
        cle_partie = _normaliser(partie_adverse)
        if not cle_partie:
            return None
        for dossier in self.dossiers.values():
            if dossier.professionnel == cle_pro and cle_partie in dossier.parties:
                return ConflitInterets(
                    professionnel=cle_pro,
                    partie_adverse=cle_partie,
                    dossier=dossier.identifiant,
                )
        return None

    # --------------------------------------------------------- recommandation

    def recommander(self, litige: Litige, limite: int = 3) -> Recommandation:
        """
        Classe les professionnels pertinents pour ce litige et explique chaque
        proposition en français clair.

        Le moteur écarte d'abord — profil suspendu, langue non pratiquée,
        qualité incompétente pour la voie choisie, conflit d'intérêts, aucun
        domaine correspondant — puis classe ce qui reste selon l'expertise, la
        proximité et la note vérifiée.

        Il ne rend jamais un choix unique imposé : la sortie est une liste
        ordonnée, et quand elle est vide, l'abstention est écrite en toutes
        lettres plutôt que renvoyée en silence.
        """
        if not self.professionnels:
            return Recommandation(
                propositions=(),
                ecartes=(),
                abstention=True,
                message=(
                    f"{_ABSTENTION} : l'annuaire ne contient aucun professionnel inscrit. "
                    "Aucune mise en relation n'est possible pour l'instant."
                ),
            )

        domaines = litige.domaines()
        qualites_competentes = _QUALITES_PAR_VOIE.get(litige.voie)

        propositions: list[Proposition] = []
        ecartes: list[str] = []

        for pro in self.professionnels.values():
            if not pro.actif:
                ecartes.append(f"{pro.nom} : profil suspendu, non proposé.")
                continue
            if not pro.numero_accreditation.strip():
                ecartes.append(f"{pro.nom} : accréditation absente, non proposé.")
                continue

            conflit = self.conflit_interets(pro.identifiant, litige.partie_adverse)
            if conflit is not None:
                ecartes.append(conflit.explication(pro.nom))
                continue

            if litige.langue not in pro.langues:
                ecartes.append(
                    f"{pro.nom} : ne travaille pas en {litige.langue}."
                )
                continue

            if qualites_competentes is None:
                ecartes.append(
                    f"{pro.nom} : voie de règlement « {litige.voie} » inconnue de la "
                    "plateforme."
                )
                continue
            if pro.qualite not in qualites_competentes:
                ecartes.append(
                    f"{pro.nom} : {pro.libelle_qualite()}, non compétent pour la voie "
                    f"« {litige.voie} » (elle relève "
                    + " ou ".join(sorted(qualites_competentes))
                    + ")."
                )
                continue

            if litige.montant_dt < pro.montant_minimum_dt:
                ecartes.append(
                    f"{pro.nom} : n'accepte pas les dossiers inférieurs à "
                    f"{pro.montant_minimum_dt:.0f} DT."
                )
                continue

            communs = domaines & pro.expertises
            if not communs:
                ecartes.append(
                    f"{pro.nom} : aucun domaine correspondant à "
                    f"{', '.join(sorted(domaines)) or 'la nature déclarée'}."
                )
                continue

            propositions.append(self._evaluer(pro, litige, communs))

        if not propositions:
            details = (
                " Motifs d'écartement : " + " ".join(ecartes) if ecartes else ""
            )
            return Recommandation(
                propositions=(),
                ecartes=tuple(ecartes),
                abstention=True,
                message=(
                    f"{_ABSTENTION} à ce litige "
                    f"({', '.join(sorted(litige.nature)) or 'nature non précisée'}, "
                    f"voie {litige.voie}, langue {litige.langue})." + details
                ),
            )

        propositions.sort(
            key=lambda p: (
                -p.score,
                -(p.note_moyenne or 0.0),
                -p.nombre_avis,
                p.professionnel.nom,
            )
        )
        retenues = tuple(propositions[: max(1, limite)])

        return Recommandation(
            propositions=retenues,
            ecartes=tuple(ecartes),
            abstention=False,
            message=(
                f"{len(retenues)} professionnel(s) accrédité(s) proposé(s) pour ce "
                f"litige, par ordre de pertinence."
            ),
        )

    # ------------------------------------------------------------- évaluation

    def _evaluer(
        self, pro: Professionnel, litige: Litige, communs: frozenset[str]
    ) -> Proposition:
        """
        Calcule le score d'un professionnel et rédige les motifs de sa proposition.

        Le score n'est pas montré aux parties ; les motifs, si. C'est le texte
        qui doit tenir devant un juriste, pas le nombre.
        """
        motifs: list[str] = []
        score = 0.0

        score += 2.0 * len(communs)
        motifs.append(
            "Expertise en " + ", ".join(sorted(communs)) + ", qui correspond au litige."
        )

        if litige.voie in pro.expertises:
            score += 3.0
            motifs.append(f"Pratique déclarée de la {litige.voie}.")
        motifs.append(
            f"Qualité {pro.qualite_elidee()}, compétente pour la voie "
            f"« {litige.voie} »."
        )

        if litige.gouvernorat is None:
            motifs.append(
                "Aucun gouvernorat n'a été précisé dans le litige : la proximité "
                "géographique n'a pas pu être prise en compte."
            )
        elif pro.gouvernorat == litige.gouvernorat:
            score += 3.0
            motifs.append(f"Exerce à {pro.gouvernorat.title()}, sur le lieu du litige.")
        elif pro.gouvernorat in _LIMITROPHES.get(litige.gouvernorat, frozenset()):
            score += 1.5
            motifs.append(
                f"Exerce à {pro.gouvernorat.title()}, gouvernorat limitrophe de "
                f"{litige.gouvernorat.title()}."
            )
        else:
            motifs.append(
                f"Exerce à {pro.gouvernorat.title()}, éloigné de "
                f"{litige.gouvernorat.title()} : prévoir des échanges à distance."
            )

        moyenne, nombre = self.note_moyenne(pro.identifiant)
        if moyenne is None:
            motifs.append(
                "Pas encore noté sur la plateforme : aucune résolution terminée ne "
                "permet d'afficher une note vérifiée."
            )
        else:
            score += moyenne * 0.8
            motifs.append(
                f"Note vérifiée de {moyenne}/5 sur {nombre} "
                f"{'dossier clôturé' if nombre == 1 else 'dossiers clôturés'}."
            )

        motifs.append(f"Langue de travail : {litige.langue}.")

        return Proposition(
            professionnel=pro,
            score=round(score, 2),
            note_moyenne=moyenne,
            nombre_avis=nombre,
            motifs=tuple(motifs),
        )
