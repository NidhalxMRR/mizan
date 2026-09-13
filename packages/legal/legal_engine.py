"""Legal engine: prescription clock + procedure path for an unpaid invoice.

Every number returned here is backed by a real article of Tunisian law that
lives in the indexed corpus. Nothing is invented; if the corpus cannot support
a claim, the engine says so instead of guessing.
"""
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta

# --- Legal constants, each tied to its source article -----------------------
# COC art. 403: actions for the price of goods delivered by sellers and
#   workshop owners prescribe after 365 days.
# COC art. 402: the general limitation period is 15 years.
# CPC art. 60: above 150 TND the creditor must serve a formal notice through a
#   bailiff, giving the debtor 5 full days before the payment order.
# CPC art. 59: the payment-order procedure applies to a determined debt of
#   contractual origin.

PRESCRIPTION_GOODS_DAYS = 365
PRESCRIPTION_GENERAL_YEARS = 15
BAILIFF_THRESHOLD_TND = 150
NOTICE_GRACE_DAYS = 5

SOURCES = {
    'prescription_goods': {
        'code_id': 'coc', 'article': 403,
        'citation_ar': 'الفصل 403 من مجلة الالتزامات والعقود',
        'label_fr': "Prescription d'un an — prix des marchandises livrées",
        'short_fr': 'COC art. 403',
    },
    'prescription_general': {
        'code_id': 'coc', 'article': 402,
        'citation_ar': 'الفصل 402 من مجلة الالتزامات والعقود',
        'label_fr': 'Prescription générale de quinze ans',
        'short_fr': 'COC art. 402',
    },
    'bailiff_notice': {
        'code_id': 'procciv', 'article': 60,
        'citation_ar': 'الفصل 60 من مجلة المرافعات المدنية والتجارية',
        'label_fr': "Mise en demeure par huissier — créances supérieures à 150 DT",
        'short_fr': 'CPCC art. 60',
    },
    'payment_order': {
        'code_id': 'procciv', 'article': 59,
        'citation_ar': 'الفصل 59 من مجلة المرافعات المدنية والتجارية',
        'label_fr': "Procédure d'injonction de payer",
        'short_fr': 'CPCC art. 59',
    },
    'damages': {
        'code_id': 'coc', 'article': 278,
        'citation_ar': 'الفصل 278 من مجلة الالتزامات والعقود',
        'label_fr': 'Réparation du préjudice — perte subie et gain manqué',
        'short_fr': 'COC art. 278',
    },
    'default_no_fault': {
        'code_id': 'coc', 'article': 277,
        'citation_ar': 'الفصل 277 من مجلة الالتزامات والعقود',
        'label_fr': "L'inexécution ou le retard ouvre droit à réparation",
        'short_fr': 'COC art. 277',
    },
}

# Activities covered by the one-year rule of COC art. 403.
GOODS_ACTIVITIES = {
    'menuiserie', 'artisanat', 'fabrication', 'industrie',
    'commerce', 'agriculture', 'atelier',
    # Ajoutés après un test sur une file réelle : ces métiers livrent un bien
    # et relevaient à tort du délai de quinze ans.
    'textile', 'imprimerie', 'boulangerie', 'menuiserie_alu',
    'metallurgie', 'plasturgie', 'ceramique', 'mobilier',
    'agroalimentaire', 'confection', 'papeterie', 'quincaillerie',
}

# Activités explicitement qualifiées comme prestations de service : le délai
# général s'applique, et c'est une décision, pas un défaut de liste.
SERVICE_ACTIVITIES = {
    'transport', 'conseil', 'nettoyage', 'gardiennage', 'maintenance',
    'informatique', 'comptabilite', 'formation', 'publicite',
    'ingenierie', 'architecture', 'traduction', 'securite',
}

# Tout ce que le moteur sait qualifier. Hors de cet ensemble, il le dit
# au lieu de choisir en silence.
KNOWN_ACTIVITIES = GOODS_ACTIVITIES | SERVICE_ACTIVITIES


@dataclass
class Step:
    order: int
    title_fr: str
    detail_fr: str
    citation_ar: str
    code_id: str
    article: int


@dataclass
class Assessment:
    amount_tnd: float
    invoice_date: str
    today: str
    regime: str                 # 'goods_1y' | 'general_15y'
    deadline: str
    days_left: int
    is_expired: bool
    urgency: str                # 'expired' | 'critical' | 'warning' | 'ok'
    needs_bailiff: bool
    grace_days: int
    regime_reason_fr: str = ''
    sources: list = field(default_factory=list)
    steps: list = field(default_factory=list)

    def to_dict(self):
        d = asdict(self)
        d['steps'] = [asdict(s) if not isinstance(s, dict) else s
                      for s in self.steps]
        return d


def _urgency(days_left):
    if days_left < 0:
        return 'expired'
    if days_left <= 60:
        return 'critical'
    if days_left <= 150:
        return 'warning'
    return 'ok'


class DateImpossible(ValueError):
    """Une date que le droit ne peut pas traiter comme point de départ."""


def assess(amount_tnd, invoice_date, activity='menuiserie', today=None):
    """Compute where the creditor stands, with a citation behind every claim."""
    today = today or date.today()
    if isinstance(invoice_date, str):
        invoice_date = date.fromisoformat(invoice_date)

    # Une créance ne peut pas se prescrire avant d'exister. Le délai court à
    # compter de la livraison — pas d'une date qu'on choisit. Accepter une
    # facture datée de demain, c'est calculer une échéance sur un fait qui
    # n'a pas eu lieu : le moteur doit refuser, pas répondre poliment.
    if invoice_date > today:
        raise DateImpossible(
            f"La facture est datée du {invoice_date.strftime('%d/%m/%Y')}, "
            f"soit après aujourd'hui ({today.strftime('%d/%m/%Y')}). "
            "Une créance ne peut pas commencer à se prescrire avant d'exister : "
            "le délai court à compter de la livraison. Vérifiez la date portée "
            "sur la facture."
        )

    # Une date antérieure à l'entrée en vigueur du COC (1906) relève de la
    # faute de saisie, pas d'une créance : 1899 donnerait une prescription
    # éteinte depuis un siècle, présentée avec le même aplomb.
    if invoice_date.year < 1906:
        raise DateImpossible(
            f"La date saisie ({invoice_date.strftime('%d/%m/%Y')}) est "
            "antérieure au Code des obligations et des contrats (1906). "
            "Vérifiez la saisie."
        )

    if amount_tnd is not None and amount_tnd <= 0:
        raise DateImpossible(
            "Le montant réclamé doit être strictement positif. "
            "Une créance de zéro dinar n'ouvre aucun droit."
        )

    is_goods = activity.lower() in GOODS_ACTIVITIES
    is_known = activity.lower() in KNOWN_ACTIVITIES
    if is_goods:
        regime = 'goods_1y'
        deadline = invoice_date + timedelta(days=PRESCRIPTION_GOODS_DAYS)
        src_presc = SOURCES['prescription_goods']
    else:
        regime = 'general_15y'
        deadline = date(invoice_date.year + PRESCRIPTION_GENERAL_YEARS,
                        invoice_date.month, invoice_date.day)
        src_presc = SOURCES['prescription_general']

    days_left = (deadline - today).days
    needs_bailiff = amount_tnd > BAILIFF_THRESHOLD_TND

    if is_goods:
        reason = (
            "Meubles fabriqués puis livrés au client : la créance porte sur le prix "
            "de marchandises livrées, non sur une simple prestation de service. "
            "C'est le délai d'un an qui s'applique, et non celui de quinze ans."
        )
    elif is_known:
        reason = (
            "Votre activité ne porte pas sur la livraison de marchandises : "
            "le délai général de quinze ans s'applique."
        )
    else:
        # Une activité inconnue ne doit JAMAIS tomber en silence sur le délai
        # le plus long. Annoncer quinze ans à un créancier qui en a un seul,
        # c'est lui faire rater sa prescription — l'erreur la plus coûteuse
        # que cet outil puisse commettre. On affiche donc le délai le plus
        # long comme hypothèse NON CONFIRMÉE, et on le dit.
        regime = 'indetermine'
        reason = (
            f"L'activité « {activity} » n'est pas qualifiée par le moteur. "
            "Le régime affiché est le délai général de quinze ans, mais il "
            "n'est PAS confirmé : si votre créance porte sur le prix de "
            "marchandises livrées, la prescription est d'un an (COC art. 403) "
            "et le délai réel est bien plus court. À faire confirmer avant "
            "toute démarche."
        )

    sources = [src_presc, SOURCES['default_no_fault'], SOURCES['damages']]
    steps = [
        Step(1, "Mise en demeure",
             (f"Votre créance dépasse {BAILIFF_THRESHOLD_TND} DT : la sommation "
              f"doit être signifiée par huissier de justice. Le débiteur dispose "
              f"alors de {NOTICE_GRACE_DAYS} jours francs pour payer.")
             if needs_bailiff else
             (f"Votre créance est inférieure ou égale à {BAILIFF_THRESHOLD_TND} DT : "
              f"la sommation par huissier n'est pas exigée à ce seuil."),
             SOURCES['bailiff_notice']['citation_ar'], 'procciv', 60),
        Step(2, "Injonction de payer",
             ("Passé le délai, vous pouvez demander une injonction de payer : "
              "la dette est déterminée et d'origine contractuelle."),
             SOURCES['payment_order']['citation_ar'], 'procciv', 59),
        Step(3, "Réparation du préjudice",
             ("Le retard ouvre droit à réparation : perte subie et gain manqué, "
              "même sans mauvaise foi du débiteur."),
             SOURCES['damages']['citation_ar'], 'coc', 278),
    ]
    if needs_bailiff:
        sources.insert(1, SOURCES['bailiff_notice'])
    sources.append(SOURCES['payment_order'])

    return Assessment(
        amount_tnd=amount_tnd,
        invoice_date=invoice_date.isoformat(),
        today=today.isoformat(),
        regime=regime,
        deadline=deadline.isoformat(),
        days_left=days_left,
        is_expired=days_left < 0,
        urgency=_urgency(days_left),
        needs_bailiff=needs_bailiff,
        regime_reason_fr=reason,
        grace_days=NOTICE_GRACE_DAYS,
        sources=sources,
        steps=steps,
    )
