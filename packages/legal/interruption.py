"""Interruption de la prescription — COC art. 396, 397, 398 (et 401).

Pourquoi ce module existe
-------------------------
Le moteur calculait la prescription comme si le délai courait d'un trait, du
jour de la facture au jour de l'échéance. En droit tunisien c'est faux : la
prescription s'interrompt, et quand elle s'interrompt tout le temps déjà écoulé
est effacé.

Les trois règles, telles que le corpus les énonce
-------------------------------------------------
- COC art. 396 — LES CAUSES tenant au créancier : la demande en justice, la
  sommation ayant date certaine, la production au passif du failli, tout acte
  juridique de saisie ou d'exécution. « مرور الزمان المعين لسقوط الدعوى ينقطع… »
- COC art. 397 — LA CAUSE tenant au débiteur : tout fait emportant
  reconnaissance du droit du créancier — arrêté de compte, paiement partiel
  constaté par un écrit à date certaine, demande de délai, caution donnée.
  « ينقطع مرور الزمان بكل أمر يترتب عليه اعتراف المدين بحق غريمه… »
- COC art. 398 — L'EFFET : « فما مضى منها قبل الانقطاع يلغى وتستأنف المدة » —
  ce qui s'est écoulé avant l'interruption est ANNULÉ et le délai REPART À ZÉRO
  à compter de l'acte. Ce n'est pas une suspension : rien n'est mis en pause,
  tout est remis à zéro.
- COC art. 401 — le calcul se fait en jours entiers et le jour de départ ne
  compte pas. C'est déjà la convention du moteur (échéance = départ + N jours,
  le jour du départ étant le jour 0), on la conserve à l'identique.

Les deux pièges que ce module refuse de tomber dedans
-----------------------------------------------------
1. Un acte postérieur à l'expiration n'interrompt RIEN. On n'interrompt pas un
   délai qui n'existe plus : une créance éteinte ne se ressuscite pas par une
   sommation tardive. L'acte est conservé dans la réponse, mais marqué sans
   effet et motivé — c'est exactement l'erreur qu'un débiteur plaiderait.
2. Un acte antérieur à la facture est incohérent : on ne reconnaît pas une
   dette qui n'est pas née. Le module refuse, il ne devine pas.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, timedelta

# --- Le texte exact, relu dans le corpus indexé -----------------------------
# Les citations sont chargées depuis `retrieve` au premier appel : elles
# doivent être celles du corpus, mot pour mot, et non une chaîne recopiée à la
# main. Le repli n'est utilisé que si l'index est absent (poste de démo sans
# pickle construit) et reprend la forme canonique du corpus.

_ARTICLES_UTILES = (396, 397, 398, 401)

_CITATION_REPLI = {
    n: f"الفصل {n} من مجلة الالتزامات والعقود" for n in _ARTICLES_UTILES
}

_CACHE_CITATIONS: dict[int, str] = {}


def citations_corpus() -> dict[int, str]:
    """Retourne {article: citation_ar} lue dans le corpus, en cache."""
    if _CACHE_CITATIONS:
        return _CACHE_CITATIONS
    try:
        from . import retrieve  # type: ignore
    except ImportError:  # pragma: no cover - exécution hors paquet
        try:
            import retrieve  # type: ignore
        except ImportError:
            retrieve = None  # type: ignore
    try:
        docs = retrieve.load_docs()  # type: ignore[union-attr]
        # Le champ 'article' est tantôt un int, tantôt une chaîne : on normalise.
        trouve = {}
        for d in docs:
            if d.get('code_id') != 'coc':
                continue
            brut = str(d.get('article', '')).strip()
            if not brut.isdigit():
                continue
            n = int(brut)
            if n in _ARTICLES_UTILES:
                trouve[n] = d['citation_ar']
        _CACHE_CITATIONS.update({**_CITATION_REPLI, **trouve})
    except Exception:  # noqa: BLE001 — l'absence d'index ne doit rien casser
        _CACHE_CITATIONS.update(_CITATION_REPLI)
    return _CACHE_CITATIONS


def _source(article: int, label_fr: str, short_fr: str) -> dict:
    """Une source au format exact attendu par le moteur (mêmes clés)."""
    return {
        'code_id': 'coc',
        'article': article,
        'citation_ar': citations_corpus()[article],
        'label_fr': label_fr,
        'short_fr': short_fr,
    }


def source_396() -> dict:
    return _source(
        396,
        "Interruption de la prescription — acte du créancier "
        "(demande en justice, sommation à date certaine, saisie)",
        'COC art. 396',
    )


def source_397() -> dict:
    return _source(
        397,
        "Interruption de la prescription — reconnaissance de dette par le "
        "débiteur (arrêté de compte, paiement partiel, demande de délai)",
        'COC art. 397',
    )


def source_398() -> dict:
    return _source(
        398,
        "Effet de l'interruption — le temps écoulé est annulé et le délai "
        "recommence à courir en entier",
        'COC art. 398',
    )


def source_401() -> dict:
    return _source(
        401,
        "Calcul du délai en jours entiers — le jour de départ ne compte pas",
        'COC art. 401',
    )


# --- Les actes interruptifs reconnus ----------------------------------------
# Chaque type est rattaché à l'article qui le fonde. Un type qui ne figure pas
# ici n'est pas « traité par défaut » : il est refusé. Une plateforme qui
# accepte n'importe quel libellé comme cause d'interruption ment au créancier
# sur la solidité de son dossier.

TYPES_ACTES: dict[str, dict] = {
    'sommation_huissier': {
        'article': 396,
        'libelle_fr': "Sommation de payer signifiée par huissier de justice",
        'fondement_fr': (
            "La mise en demeure signifiée par huissier a date certaine : elle "
            "vaut réclamation du créancier au sens du 1° de l'article 396."
        ),
    },
    'demande_justice': {
        'article': 396,
        'libelle_fr': "Demande en justice (assignation, injonction de payer)",
        'fondement_fr': (
            "La demande en justice interrompt la prescription, même portée "
            "devant un tribunal incompétent ou entachée d'un vice de forme "
            "(article 396, 1°)."
        ),
    },
    'saisie_conservatoire': {
        'article': 396,
        'libelle_fr': "Saisie conservatoire ou acte d'exécution",
        'fondement_fr': (
            "Tout acte juridique tendant à saisir les biens du débiteur ou à "
            "s'en faire payer interrompt la prescription (article 396, 3°)."
        ),
    },
    'reconnaissance_dette': {
        'article': 397,
        'libelle_fr': "Reconnaissance de dette par le débiteur",
        'fondement_fr': (
            "Tout fait emportant reconnaissance du droit du créancier par le "
            "débiteur interrompt la prescription (article 397)."
        ),
    },
    'paiement_partiel': {
        'article': 397,
        'libelle_fr': "Paiement partiel imputé sur la dette",
        'fondement_fr': (
            "Le versement d'un acompte sur la dette vaut reconnaissance, à "
            "condition d'être constaté par un écrit à date certaine "
            "(article 397)."
        ),
    },
    'arrete_compte': {
        'article': 397,
        'libelle_fr': "Arrêté de compte signé entre les parties",
        'fondement_fr': (
            "L'arrêté de compte entre créancier et débiteur est expressément "
            "visé par l'article 397 comme acte de reconnaissance."
        ),
    },
}

# Les types cités nommément par la mission, dans l'ordre où ils y figurent.
TYPES_VALIDES = tuple(TYPES_ACTES)


class ActeImpossible(ValueError):
    """Un acte que le droit ne peut pas traiter comme interruptif.

    Se distingue de l'acte « sans effet » : ici la donnée est incohérente
    (date antérieure à la naissance de la créance, date future, type inconnu)
    et le moteur refuse au lieu de produire un calcul.
    """


@dataclass
class ActeInterruptif:
    """Un acte invoqué comme interrompant la prescription."""
    type: str
    date: str                      # ISO AAAA-MM-JJ
    description: str = ''

    def __post_init__(self):
        if self.type not in TYPES_ACTES:
            raise ActeImpossible(
                f"Type d'acte inconnu : « {self.type} ». Les actes reconnus "
                f"comme interruptifs sont : {', '.join(TYPES_VALIDES)}. "
                "Mizan refuse de tenir pour interruptif un acte dont le "
                "corpus ne fonde pas l'effet."
            )
        if isinstance(self.date, date):
            self.date = self.date.isoformat()
        try:
            date.fromisoformat(str(self.date))
        except (TypeError, ValueError):
            raise ActeImpossible(
                f"La date de l'acte « {self.date} » n'est pas une date valide "
                "au format AAAA-MM-JJ."
            )
        self.date = str(self.date)

    @property
    def jour(self) -> date:
        return date.fromisoformat(self.date)

    @property
    def article(self) -> int:
        return TYPES_ACTES[self.type]['article']

    @property
    def libelle_fr(self) -> str:
        return TYPES_ACTES[self.type]['libelle_fr']

    @property
    def fondement_fr(self) -> str:
        return TYPES_ACTES[self.type]['fondement_fr']


@dataclass
class ResultatInterruption:
    """Ce que l'interruption change, et ce qu'elle ne change pas."""
    interrompu: bool
    date_depart_initiale: str
    date_depart_effective: str
    echeance_initiale: str
    echeance_effective: str
    jours_gagnes: int
    interruptions: list = field(default_factory=list)
    actes_sans_effet: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    resume_fr: str = ''

    def to_dict(self) -> dict:
        return asdict(self)


def normaliser(actes) -> list[ActeInterruptif]:
    """Accepte des dataclasses, des dicts (API) ou des objets pydantic."""
    if not actes:
        return []
    sortie = []
    for a in actes:
        if isinstance(a, ActeInterruptif):
            sortie.append(a)
            continue
        if isinstance(a, dict):
            brut = a
        elif hasattr(a, 'model_dump'):
            brut = a.model_dump()
        elif hasattr(a, '__dict__'):
            brut = dict(a.__dict__)
        else:
            raise ActeImpossible(f"Acte illisible : {a!r}")
        manquants = [c for c in ('type', 'date') if not brut.get(c)]
        if manquants:
            raise ActeImpossible(
                "Un acte interruptif doit porter un type et une date. "
                f"Champs manquants : {', '.join(manquants)}."
            )
        sortie.append(ActeInterruptif(
            type=str(brut['type']),
            date=brut['date'],
            description=str(brut.get('description') or ''),
        ))
    return sortie


def _echeance(depart: date, regime_jours) -> date:
    """Échéance à partir d'un point de départ.

    `regime_jours` est soit un nombre de jours entiers (COC art. 401 : le jour
    de départ ne compte pas, l'échéance est donc départ + N), soit une fonction
    date -> date pour les régimes exprimés en années (prescription générale de
    quinze ans, COC art. 402).
    """
    if callable(regime_jours):
        calculee = regime_jours(depart)
        if isinstance(calculee, str):
            calculee = date.fromisoformat(calculee)
        assert isinstance(calculee, date)
        return calculee
    return depart + timedelta(days=int(regime_jours))


def appliquer(date_depart, actes, regime_jours, today=None) -> ResultatInterruption:
    """Applique les interruptions à un délai de prescription.

    Retourne le nouveau point de départ du délai et les articles qui fondent
    chaque interruption retenue.

    Règle appliquée, acte par acte, dans l'ordre chronologique :
    - un acte antérieur à la naissance de la créance est REFUSÉ (ActeImpossible) ;
    - un acte daté du futur est REFUSÉ (ActeImpossible) ;
    - un acte postérieur à l'échéance alors en cours est SANS EFFET : la
      créance est déjà éteinte, on ne la ressuscite pas (COC art. 398 ne joue
      que « في المدة المحدودة », à l'intérieur du délai) ;
    - sinon l'acte interrompt : le temps écoulé est annulé et le délai repart
      en entier depuis la date de l'acte (COC art. 398).

    C'est donc le DERNIER acte valide qui fixe le point de départ effectif.
    """
    if isinstance(date_depart, str):
        date_depart = date.fromisoformat(date_depart)
    today = today or date.today()
    if isinstance(today, str):
        today = date.fromisoformat(today)

    actes = normaliser(actes)
    echeance_initiale = _echeance(date_depart, regime_jours)

    depart_effectif = date_depart
    echeance_courante = echeance_initiale
    interruptions: list[dict] = []
    sans_effet: list[dict] = []

    for acte in sorted(actes, key=lambda a: a.jour):
        j = acte.jour

        if j < date_depart:
            raise ActeImpossible(
                f"L'acte « {acte.libelle_fr} » est daté du "
                f"{j.strftime('%d/%m/%Y')}, soit AVANT la facture du "
                f"{date_depart.strftime('%d/%m/%Y')}. Un acte ne peut pas "
                "interrompre la prescription d'une créance qui n'était pas "
                "encore née : on ne réclame pas, et on ne reconnaît pas, une "
                "dette qui n'existe pas. Vérifiez la date de l'acte ou celle "
                "de la facture."
            )

        if j > today:
            raise ActeImpossible(
                f"L'acte « {acte.libelle_fr} » est daté du "
                f"{j.strftime('%d/%m/%Y')}, soit après aujourd'hui "
                f"({today.strftime('%d/%m/%Y')}). Un acte qui n'a pas encore "
                "eu lieu n'interrompt rien. Mizan ne calcule pas sur une "
                "démarche seulement envisagée."
            )

        if j > echeance_courante:
            retard = (j - echeance_courante).days
            sans_effet.append({
                'type': acte.type,
                'libelle_fr': acte.libelle_fr,
                'date': acte.date,
                'description': acte.description,
                'motif_fr': (
                    f"Acte accompli le {j.strftime('%d/%m/%Y')}, soit "
                    f"{retard} jour(s) APRÈS l'expiration du délai le "
                    f"{echeance_courante.strftime('%d/%m/%Y')}. La prescription "
                    "était déjà acquise : il n'y avait plus de délai à "
                    "interrompre. Une créance éteinte ne se ranime pas par une "
                    "sommation tardive, et le débiteur peut opposer la "
                    "prescription malgré cet acte."
                ),
                'articles': [source_398()],
            })
            continue

        ancienne_echeance = echeance_courante
        depart_precedent = depart_effectif
        depart_effectif = j
        echeance_courante = _echeance(j, regime_jours)
        art = acte.article
        fondements = [source_396() if art == 396 else source_397(),
                      source_398()]
        interruptions.append({
            'type': acte.type,
            'libelle_fr': acte.libelle_fr,
            'date': acte.date,
            'description': acte.description,
            'article_cause': art,
            'fondement_fr': acte.fondement_fr,
            'effet_fr': (
                f"Le temps écoulé depuis le "
                f"{depart_precedent.strftime('%d/%m/%Y')} "
                f"({(j - depart_precedent).days} jours) est annulé : le délai "
                f"repart en entier à compter de cet acte. L'échéance passe du "
                f"{ancienne_echeance.strftime('%d/%m/%Y')} au "
                f"{echeance_courante.strftime('%d/%m/%Y')}."
            ),
            'nouvelle_echeance': echeance_courante.isoformat(),
            'articles': fondements,
        })

    jours_gagnes = (echeance_courante - echeance_initiale).days
    interrompu = bool(interruptions)

    if interrompu:
        dernier = interruptions[-1]
        resume = (
            f"Le délai de prescription a été interrompu "
            f"{len(interruptions)} fois. " if len(interruptions) > 1 else
            "Le délai de prescription a été interrompu. "
        )
        resume += (
            f"Le dernier acte interruptif retenu est « {dernier['libelle_fr']} » "
            f"du {date.fromisoformat(dernier['date']).strftime('%d/%m/%Y')}. "
            f"Tout le temps écoulé avant cet acte est annulé : le délai repart "
            f"à zéro depuis cette date et l'échéance est reportée au "
            f"{echeance_courante.strftime('%d/%m/%Y')}, soit "
            f"{jours_gagnes} jours de plus que sans interruption."
        )
    elif sans_effet:
        resume = (
            f"Aucune interruption retenue. Le ou les actes produits "
            f"({len(sans_effet)}) sont postérieurs à l'expiration du délai : "
            f"ils n'ont rien interrompu, et l'échéance reste fixée au "
            f"{echeance_initiale.strftime('%d/%m/%Y')}."
        )
    else:
        resume = (
            "Aucun acte interruptif n'a été produit : le délai court sans "
            f"interruption depuis le {date_depart.strftime('%d/%m/%Y')}."
        )

    sources: list[dict] = []
    vus: set[int] = set()
    for bloc in interruptions + sans_effet:
        for s in bloc['articles']:
            if s['article'] not in vus:
                vus.add(s['article'])
                sources.append(s)
    if interrompu:
        s401 = source_401()
        if s401['article'] not in vus:
            sources.append(s401)

    return ResultatInterruption(
        interrompu=interrompu,
        date_depart_initiale=date_depart.isoformat(),
        date_depart_effective=depart_effectif.isoformat(),
        echeance_initiale=echeance_initiale.isoformat(),
        echeance_effective=echeance_courante.isoformat(),
        jours_gagnes=jours_gagnes,
        interruptions=interruptions,
        actes_sans_effet=sans_effet,
        sources=sources,
        resume_fr=resume,
    )
