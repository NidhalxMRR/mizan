"""Moteur d'analyse des risques juridiques d'une facture impayée.

Ce que ce module décide, et ce qu'il refuse de décider
------------------------------------------------------
Il répond à une question que le créancier pose avant de saisir un tribunal :
« qu'est-ce qui, dans ma facture, peut m'être opposé ? ». Il y répond par une
liste de risques dont chacun porte trois choses indissociables :

  * la CONSTATATION — un fait lu dans le document, cité tel qu'il y figure ;
  * le FONDEMENT — un article du corpus, retrouvé et prouvé à l'exécution ;
  * la GRAVITÉ — ce que le créancier perd si le risque se réalise.

Séparer ces trois éléments n'est pas une coquetterie de présentation. Un
risque sans constatation est une généralité ; une constatation sans fondement
est une opinion ; et un fondement qu'on n'a pas vérifié est une fausse
référence. Les trois ensemble font une analyse qu'un juriste peut contredire,
ce qui est précisément ce qu'on lui demande de pouvoir faire.

LA RÈGLE D'ABSTENTION. Si `ancrage.ancrer` ne retrouve pas l'article, le
risque n'est pas produit — pas dégradé, pas assorti d'un avertissement :
absent. Un rapport qui omet un risque faute de texte laisse le juriste faire
son travail ; un rapport qui invente l'article le lui fait mal faire en lui
donnant confiance. L'abstention est la fonctionnalité, pas le mode dégradé.

Ce module ne modifie rien et n'appelle aucun réseau. Il lit le document, le
corpus, et rend un objet.
"""
from __future__ import annotations

import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
if str(RACINE) not in sys.path:  # pragma: no cover - confort d'import
    sys.path.insert(0, str(RACINE))

from packages.legal import doc_gate  # noqa: E402
from packages.legal.legal_engine import (  # noqa: E402
    BAILIFF_THRESHOLD_TND,
    DateImpossible,
    assess,
)
from packages.risques import fondements  # noqa: E402
from packages.risques.ancrage import Article, ancrer  # noqa: E402

# Gravités, du plus grave au moins grave. L'ordre sert au tri du rapport :
# un juriste pressé lit la première ligne, elle doit être la pire.
ELEVE, MOYEN, FAIBLE = 'eleve', 'moyen', 'faible'
_RANG = {ELEVE: 0, MOYEN: 1, FAIBLE: 2}

# Seuil au-delà duquel la prescription est dite « proche ». Deux mois, c'est
# le temps qu'il faut pour faire signifier une sommation par huissier et
# déposer une requête sans travailler dans l'urgence.
JOURS_ALERTE_PRESCRIPTION = 60

# Tolérance sur le rapprochement HT + TVA = TTC. Les factures tunisiennes
# comptent en millimes ; un écart d'un millime est un arrondi, pas une
# incohérence.
TOLERANCE_MILLIMES = 0.005

# Le taux affiché sur la facture (« TVA 19% »), à ne pas confondre avec un
# taux légal : le corpus n'en contient aucun (voir fondements.LACUNES).
_TAUX_AFFICHE = re.compile(r'(?:tva|الأداء)[^\n%]{0,20}?(\d{1,2}(?:[.,]\d+)?)\s*%',
                           re.I)
_LIGNE_HT = re.compile(r'(?:total\s+ht|hors\s+taxe|\bht\b|المبلغ\s+دون)', re.I)
_LIGNE_TVA = re.compile(r'(?:\btva\b|الأداء\s+على\s+القيمة)', re.I)
_MATRICULE = re.compile(
    r'(matricule\s+fiscal|identifiant\s+fiscal|\bm\.?f\.?\s*:|المعرف\s+الجبائي)',
    re.I)
_NUMERO = re.compile(
    r'(?:facture|invoice|فاتورة)\s*(?:n[°ºbrodeum.\s]*|num[eé]ro\s*|:)\s*'
    r'([A-Za-z0-9][A-Za-z0-9\-/]{1,20})', re.I)
_LIVRAISON = re.compile(
    r'(livr[ée]e?s?|r[ée]ceptionn[ée]e?s?|bon\s+de\s+livraison|'
    r'r[ée]ception|sans\s+r[ée]serve|تسليم|تسلم|استلام|قبض)', re.I)
_NOMBRE = re.compile(r'\d[\d\s.,]*\d|\d')


@dataclass(frozen=True)
class Risque:
    """Un risque juridique, sa constatation factuelle et son fondement.

    `constatation_fr` doit toujours pouvoir être retrouvée dans le document
    par un lecteur humain : soit elle cite une ligne, soit elle énonce une
    absence vérifiable. Jamais une inférence présentée comme un fait.
    """

    identifiant: str
    intitule_fr: str
    gravite: str
    constatation_fr: str
    consequence_fr: str
    fondement: Article
    extrait_document: str | None = None

    def to_dict(self) -> dict:
        donnees = asdict(self)
        donnees['fondement'] = self.fondement.to_dict()
        return donnees


@dataclass(frozen=True)
class Abstention:
    """Un contrôle qui n'a pas pu être mené, et la raison exacte.

    Rendre les abstentions visibles est le pendant de la règle d'abstention :
    se taire sans le dire laisserait croire que le contrôle a été fait et
    qu'il est négatif.
    """

    sujet_fr: str
    motif_fr: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RapportRisques:
    """Le résultat complet : ce qui a été trouvé, et ce qui n'a pas pu l'être."""

    risques: list = field(default_factory=list)
    abstentions: list = field(default_factory=list)
    document_analyse: bool = True
    motif_rejet_fr: str | None = None

    @property
    def gravite_maximale(self) -> str | None:
        """La pire gravité présente, ou None si aucun risque n'est retenu."""
        if not self.risques:
            return None
        return min((r.gravite for r in self.risques), key=lambda g: _RANG[g])

    def to_dict(self) -> dict:
        return {
            'risques': [r.to_dict() for r in self.risques],
            'abstentions': [a.to_dict() for a in self.abstentions],
            'document_analyse': self.document_analyse,
            'motif_rejet_fr': self.motif_rejet_fr,
            'gravite_maximale': self.gravite_maximale,
        }


def _nombre(brut: str) -> float | None:
    """Lit « 9,520.000 » comme « 9 520,000 » : deux écritures, une somme.

    Une facture tunisienne écrit indifféremment la virgule en séparateur de
    milliers ou en séparateur décimal. Trancher au hasard produirait un écart
    de TVA imaginaire sur une facture parfaitement régulière.
    """
    compact = brut.strip().replace(' ', '').replace('\u00a0', '')
    if not compact:
        return None
    lectures = [compact.replace(',', ''), compact.replace(',', '.')]
    if compact.count(',') == 1 and '.' not in compact:
        lectures.insert(0, compact.replace(',', '.'))
    for lecture in lectures:
        try:
            valeur = float(lecture)
        except ValueError:
            continue
        if valeur >= 0:
            return valeur
    return None


def _valeur_sur_ligne(texte: str, motif: re.Pattern) -> tuple[float | None, str | None]:
    """Plus grand nombre porté par une ligne qui répond au motif.

    On retient le plus grand parce qu'une ligne « TVA 19% 1,520.000 » contient
    aussi le taux : entre 19 et 1520, la somme est la seconde.
    """
    meilleure: float | None = None
    ligne_retenue: str | None = None
    for ligne in texte.splitlines():
        if not motif.search(ligne):
            continue
        for brut in _NOMBRE.findall(ligne):
            valeur = _nombre(brut)
            if valeur is None or valeur <= 0:
                continue
            if meilleure is None or valeur > meilleure:
                meilleure, ligne_retenue = valeur, ligne.strip()[:90]
    return meilleure, ligne_retenue


def _risque_prescription(texte: str, montant: float | None, date_facture: str | None,
                         activite: str, aujourdhui: date,
                         abstentions: list) -> list:
    """Prescription acquise ou proche, sur le calcul déjà éprouvé du moteur.

    On ne recalcule pas la prescription ici : `legal_engine.assess` la tient
    déjà, avec ses régimes et ses refus de dates impossibles. Dupliquer ce
    calcul, c'est créer deux vérités qui finiront par diverger.
    """
    if not date_facture:
        abstentions.append(Abstention(
            sujet_fr='Prescription',
            motif_fr="Aucune date n'a pu être lue sur le document : le point "
                     "de départ du délai est inconnu, et une prescription "
                     "calculée sur une date supposée serait une invention.",
        ))
        return []

    try:
        bilan = assess(montant, date_facture, activite, today=aujourdhui)
    except DateImpossible as refus:
        abstentions.append(Abstention(
            sujet_fr='Prescription',
            motif_fr=str(refus),
        ))
        return []
    except (ValueError, TypeError) as refus:
        abstentions.append(Abstention(
            sujet_fr='Prescription',
            motif_fr=f"La date « {date_facture} » n'est pas exploitable : {refus}",
        ))
        return []

    choix = (fondements.PRESCRIPTION_UN_AN if bilan.regime == 'goods_1y'
             else fondements.PRESCRIPTION_GENERALE)
    article = ancrer(choix.code_id, choix.article, choix.marqueur_ar)
    if article is None:
        abstentions.append(Abstention(
            sujet_fr='Prescription',
            motif_fr=f"L'article {choix.article} n'a pas été retrouvé dans le "
                     "corpus : le risque n'est pas produit.",
        ))
        return []

    echeance = date.fromisoformat(bilan.deadline).strftime('%d/%m/%Y')
    emission = date.fromisoformat(bilan.invoice_date).strftime('%d/%m/%Y')

    if bilan.is_expired:
        return [Risque(
            identifiant='prescription_acquise',
            intitule_fr='Action prescrite : la créance ne peut plus être réclamée en justice',
            gravite=ELEVE,
            constatation_fr=(
                f"La facture est datée du {emission}. Le délai a expiré le "
                f"{echeance}, soit il y a {abs(bilan.days_left)} jours."
            ),
            consequence_fr=(
                "Le débiteur peut opposer la prescription et faire rejeter la "
                "demande sans que le fond soit examiné. Seule une interruption "
                "antérieure du délai (COC art. 396) pourrait encore sauver "
                "l'action : il faut rechercher tout acte de poursuite ou toute "
                "reconnaissance de dette intervenus avant l'échéance."
            ),
            fondement=article,
            extrait_document=f'Date : {emission}',
        )]

    if bilan.days_left <= JOURS_ALERTE_PRESCRIPTION:
        return [Risque(
            identifiant='prescription_proche',
            intitule_fr='Prescription imminente : le délai pour agir se referme',
            gravite=ELEVE,
            constatation_fr=(
                f"La facture est datée du {emission}. Le délai expire le "
                f"{echeance} : il reste {bilan.days_left} jours."
            ),
            consequence_fr=(
                "Passé cette date, l'action est éteinte. La sommation par "
                "huissier et le dépôt de la requête doivent être engagés "
                "immédiatement, ou le délai doit être interrompu."
            ),
            fondement=article,
            extrait_document=f'Date : {emission}',
        )]

    return []


def _risque_seuil_150(montant: float | None, abstentions: list) -> list:
    """Le seuil de 150 DT change la NATURE de la sommation, pas son ton.

    Sous le seuil, une relance écrite suffit. Au-dessus, la sommation par
    huissier est un préalable de procédure : l'injonction de payer déposée
    sans elle est irrecevable. Le risque n'est donc pas de mal rédiger une
    lettre, c'est de perdre des mois sur une requête qui ne sera pas examinée.
    """
    if montant is None or montant <= 0:
        return []
    article = ancrer(fondements.SEUIL_HUISSIER.code_id,
                     fondements.SEUIL_HUISSIER.article,
                     fondements.SEUIL_HUISSIER.marqueur_ar)
    if article is None:
        abstentions.append(Abstention(
            sujet_fr='Seuil de 150 dinars',
            motif_fr="L'article 60 du Code de procédure civile et commerciale "
                     "n'a pas été retrouvé dans le corpus.",
        ))
        return []

    if montant > BAILIFF_THRESHOLD_TND:
        return [Risque(
            identifiant='sommation_huissier_obligatoire',
            intitule_fr="Sommation par huissier obligatoire avant toute injonction de payer",
            gravite=MOYEN,
            constatation_fr=(
                f"Le montant réclamé est de {_dinars(montant)} DT, supérieur "
                f"au seuil de {BAILIFF_THRESHOLD_TND} DT."
            ),
            consequence_fr=(
                "Une simple relance ne suffit pas. Le débiteur doit être "
                "sommé par huissier de justice et disposer de cinq jours "
                "francs pour payer ; le procès-verbal de sommation doit être "
                "accompagné d'une copie du titre de la créance. Une requête "
                "déposée sans cette formalité s'expose au rejet."
            ),
            fondement=article,
        )]

    return [Risque(
        identifiant='sommation_huissier_non_exigee',
        intitule_fr="Sommation par huissier non exigée à ce montant",
        gravite=FAIBLE,
        constatation_fr=(
            f"Le montant réclamé est de {_dinars(montant)} DT, inférieur ou "
            f"égal au seuil de {BAILIFF_THRESHOLD_TND} DT."
        ),
        consequence_fr=(
            "Le préalable de la sommation par huissier ne s'impose pas à ce "
            "montant. Le coût de l'huissier peut dépasser l'enjeu : il faut "
            "mettre en balance le recouvrement et sa dépense."
        ),
        fondement=article,
    )]


def _risque_mentions(texte: str, abstentions: list) -> list:
    """Numéro et identifiant fiscal : les deux seules mentions que le corpus fonde.

    La date manquante n'est pas traitée ici comme un manquement : aucun
    article indexé ne l'impose (voir fondements.LACUNES). Elle est renvoyée en
    abstention par `_risque_prescription`, qui constate qu'il lui manque un
    point de départ — ce qui est un fait, pas une qualification juridique.
    """
    risques = []

    if not _NUMERO.search(texte):
        article = ancrer(fondements.NUMEROTATION.code_id,
                         fondements.NUMEROTATION.article,
                         fondements.NUMEROTATION.marqueur_ar)
        if article is None:
            abstentions.append(Abstention(
                sujet_fr='Numérotation de la facture',
                motif_fr="Le corpus ne contient aucun article sanctionnant "
                         "l'absence de numéro : le risque n'est pas produit.",
            ))
        else:
            risques.append(Risque(
                identifiant='numero_absent',
                intitule_fr='Numéro de facture absent ou illisible',
                gravite=MOYEN,
                constatation_fr=(
                    "Aucun numéro de facture n'a été trouvé dans le document."
                ),
                consequence_fr=(
                    "Une facture non numérotée, ou numérotée en série "
                    "irrégulière, expose l'émetteur à une amende de 50 à "
                    "1000 dinars par facture. Elle affaiblit aussi la pièce "
                    "devant le juge : une facture qu'on ne peut pas rattacher "
                    "à une série se discute plus facilement."
                ),
                fondement=article,
            ))

    if not _MATRICULE.search(texte):
        article = ancrer(fondements.IDENTIFIANT_FISCAL.code_id,
                         fondements.IDENTIFIANT_FISCAL.article,
                         fondements.IDENTIFIANT_FISCAL.marqueur_ar)
        if article is None:
            abstentions.append(Abstention(
                sujet_fr='Identifiant fiscal',
                motif_fr="Le corpus ne contient aucun article imposant la "
                         "mention de l'identifiant fiscal : le risque n'est "
                         "pas produit.",
            ))
        else:
            risques.append(Risque(
                identifiant='identifiant_fiscal_absent',
                intitule_fr="Identifiant fiscal absent de la facture",
                gravite=MOYEN,
                constatation_fr=(
                    "Aucun identifiant fiscal (matricule fiscal) n'a été "
                    "trouvé dans le document."
                ),
                consequence_fr=(
                    "L'identifiant fiscal doit figurer sur tous les documents "
                    "relatifs à l'activité. Un document qui ne le porte pas "
                    "ne peut pas être retenu, ce qui fragilise la facture "
                    "comme pièce du dossier."
                ),
                fondement=article,
            ))

    return risques


def _risque_preuve_livraison(texte: str, abstentions: list) -> list:
    """Sans trace de livraison, la facture n'est qu'une prétention chiffrée.

    COC 441 range parmi les preuves écrites « les factures ACCEPTÉES ». Le
    qualificatif est dans le texte : une facture qu'on a émise soi-même, sans
    bon de livraison signé ni accusé de réception, n'établit pas que la
    marchandise a été reçue. Et COC 420 met la charge de cette preuve sur
    celui qui réclame. Le créancier qui ignore ce point découvre à l'audience
    que sa pièce maîtresse ne prouve rien.
    """
    if _LIVRAISON.search(texte):
        return []

    preuve = ancrer(fondements.FACTURE_ACCEPTEE.code_id,
                    fondements.FACTURE_ACCEPTEE.article,
                    fondements.FACTURE_ACCEPTEE.marqueur_ar)
    charge = ancrer(fondements.CHARGE_PREUVE.code_id,
                    fondements.CHARGE_PREUVE.article,
                    fondements.CHARGE_PREUVE.marqueur_ar)
    if preuve is None or charge is None:
        abstentions.append(Abstention(
            sujet_fr='Preuve de la livraison',
            motif_fr="Les articles du corpus sur la preuve écrite n'ont pas "
                     "été retrouvés : le risque n'est pas produit.",
        ))
        return []

    return [Risque(
        identifiant='preuve_livraison_absente',
        intitule_fr="Aucune trace de livraison ou de réception sur la facture",
        gravite=ELEVE,
        constatation_fr=(
            "Le document ne porte aucune mention de livraison, de réception "
            "ou de bon de livraison signé."
        ),
        consequence_fr=(
            "La preuve de l'obligation incombe à celui qui la réclame "
            f"({charge.citation_ar}). Or la loi ne retient comme preuve "
            "écrite que les factures ACCEPTÉES : une facture émise "
            "unilatéralement, sans bon de livraison signé ni accusé de "
            "réception, n'établit pas que la marchandise a été reçue. Il faut "
            "réunir avant toute procédure le bon de livraison signé, un "
            "courrier du client ou tout écrit valant reconnaissance."
        ),
        fondement=preuve,
    )]


def _risque_montant_non_ancre(texte: str, montant: float | None,
                              abstentions: list) -> list:
    """Un montant qui ne repose sur aucune ligne du document est une invention.

    C'est le contrôle qui a manqué le jour où Mizan a réclamé 2 083,000 DT au
    titre d'une « facture n° 34848 » lue dans le programme du hackathon.
    `doc_gate` sait déjà rattacher un montant à une ligne de total ; on
    l'appelle plutôt que de réécrire cette logique.

    Ce risque ne cite aucun article, et c'est délibéré : il ne dit pas que la
    loi est violée, il dit que la pièce ne porte pas le chiffre réclamé. Un
    défaut de lecture n'est pas un manquement juridique, et lui coller un
    article serait exactement le travers que ce module combat. Il est donc
    renvoyé en abstention motivée, où le juriste le verra.
    """
    if montant is None or montant <= 0:
        return []
    verdict = doc_gate.inspect(texte, montant=montant)
    ligne = verdict.get('anchored_line')
    if ligne and _nombre_present(ligne, montant):
        return []
    abstentions.append(Abstention(
        sujet_fr='Ancrage du montant réclamé',
        motif_fr=(
            f"Le montant de {_dinars(montant)} DT n'est porté par aucune "
            "ligne de total du document. Mizan ne produit pas de risque "
            "chiffré sur un montant qu'il ne peut pas montrer dans la pièce : "
            "vérifiez la lecture du document avant toute démarche."
        ),
    ))
    return []


def _nombre_present(ligne: str, montant: float) -> bool:
    """La ligne porte-t-elle réellement ce montant ?"""
    for brut in _NOMBRE.findall(ligne):
        valeur = _nombre(brut)
        if valeur is not None and abs(valeur - montant) < 0.01:
            return True
    return False


def _dinars(montant: float) -> str:
    """Écrit un montant en dinars et millimes, espace en séparateur de milliers.

    Passe par un format nombre isolé plutôt que par un remplacement sur la
    phrase entière : remplacer les virgules dans « 9,520.000 DT, supérieur au
    seuil » emporte aussi la virgule de la phrase et donne « 9 520.000 DT
    supérieur au seuil ». Le texte doit rester lisible par un juriste.
    """
    return f'{montant:,.3f}'.replace(',', ' ')


def _risque_tva(texte: str, abstentions: list) -> list:
    """Écart entre HT + TVA et le net à payer : un constat, pas une infraction.

    Le corpus ne contient aucun taux légal de TVA (vérifié : zéro occurrence
    de « 19 % » sous toutes ses graphies). On peut donc constater que les
    chiffres de la facture ne s'additionnent pas — c'est de l'arithmétique,
    elle se vérifie à l'œil — mais on ne peut pas dire quelle règle fiscale
    est enfreinte. Le module s'arrête à ce qu'il peut prouver et renvoie le
    constat en abstention motivée plutôt qu'en risque fondé.
    """
    ht, ligne_ht = _valeur_sur_ligne(texte, _LIGNE_HT)
    tva, ligne_tva = _valeur_sur_ligne(texte, _LIGNE_TVA)
    if ht is None or tva is None:
        return []

    taux = _TAUX_AFFICHE.search(texte)
    if not taux:
        return []
    valeur_taux = _nombre(taux.group(1))
    if valeur_taux is None or valeur_taux <= 0:
        return []

    attendu = ht * valeur_taux / 100.0
    if abs(attendu - tva) <= max(TOLERANCE_MILLIMES, attendu * 0.001):
        return []

    abstentions.append(Abstention(
        sujet_fr='Cohérence de la TVA',
        motif_fr=(
            f"La facture porte « {ligne_ht} » et « {ligne_tva} » avec un taux "
            f"affiché de {valeur_taux:g} %. Ce taux appliqué au montant hors "
            f"taxe donnerait {attendu:.3f} DT, et non {tva:.3f} DT. Mizan "
            "signale l'écart de calcul mais ne le qualifie pas : aucun article "
            "du corpus indexé ne fixe de taux légal de TVA, et affirmer une "
            "infraction fiscale sans texte serait une invention."
        )
    ))
    return []


def analyser(texte: str, montant: float | None = None,
             date_facture: str | None = None, activite: str = 'menuiserie',
             aujourdhui: date | None = None) -> RapportRisques:
    """Analyse une facture et renvoie ses risques juridiques fondés.

    `texte` est le texte brut du document (couche texte ou OCR). `montant` et
    `date_facture` sont ceux déjà retenus par l'extraction en amont ; quand
    ils sont absents, les contrôles qui en dépendent s'abstiennent au lieu de
    deviner.

    Le rapport renvoyé porte les risques ET les abstentions. Un appelant qui
    n'affiche que les risques montre une analyse plus rassurante qu'elle ne
    l'est : les abstentions disent ce qui n'a pas pu être vérifié, et c'est
    souvent là que se trouve le vrai danger.
    """
    aujourdhui = aujourdhui or date.today()
    abstentions: list = []

    if not texte or not texte.strip():
        return RapportRisques(
            risques=[],
            abstentions=[Abstention(
                sujet_fr='Analyse du document',
                motif_fr="Le document ne contient aucun texte exploitable. "
                         "S'il s'agit d'un PDF scanné, il doit d'abord passer "
                         "par la reconnaissance de caractères : analyser une "
                         "page vide reviendrait à inventer son contenu.",
            )],
            document_analyse=False,
            motif_rejet_fr='document vide ou sans couche texte',
        )

    # La porte d'entrée existante décide si le document est une facture. On ne
    # la double pas : un contrat ou une mise en demeure analysés comme une
    # facture produiraient des risques sur une pièce qui n'en porte aucun.
    verdict = doc_gate.inspect(texte, montant=montant)
    if not verdict['is_invoice']:
        return RapportRisques(
            risques=[],
            abstentions=[Abstention(
                sujet_fr='Analyse du document',
                motif_fr=(verdict.get('reason') or verdict.get('detail')
                          or "le document n'a pas été reconnu comme une facture"),
            )],
            document_analyse=False,
            motif_rejet_fr=(verdict.get('reason') or verdict.get('detail')),
        )

    risques: list = []
    risques += _risque_prescription(texte, montant, date_facture, activite,
                                    aujourdhui, abstentions)
    risques += _risque_seuil_150(montant, abstentions)
    risques += _risque_mentions(texte, abstentions)
    risques += _risque_preuve_livraison(texte, abstentions)
    risques += _risque_montant_non_ancre(texte, montant, abstentions)
    risques += _risque_tva(texte, abstentions)

    # Le plus grave d'abord : un juriste qui ne lit qu'une ligne doit lire
    # celle qui lui coûte son dossier.
    risques.sort(key=lambda r: _RANG[r.gravite])

    return RapportRisques(risques=risques, abstentions=abstentions)
