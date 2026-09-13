"""Moteur d'analyse de risques d'un contrat commercial tunisien.

CE QUE CE MODULE PROMET, ET CE QU'IL REFUSE DE PROMETTRE
--------------------------------------------------------
Il lit le texte d'un contrat (français, arabe, ou les deux — les contrats
tunisiens sont couramment bilingues) et signale les clauses qui engagent
lourdement le signataire.

Trois règles gouvernent tout le fichier, et elles expliquent la plupart des
choix qui suivraient sinon d'un caprice :

1. AUCUNE PARAPHRASE. Chaque clause détectée renvoie l'EXTRAIT EXACT du
   contrat, caractère pour caractère, avec sa position. Un juriste doit
   pouvoir le lire à l'audience sans vérifier que l'outil n'a pas reformulé.
   C'est aussi la seule preuve vérifiable qu'une détection n'est pas inventée.

2. AUCUNE CLAUSE SANS ARTICLE. Une clause n'est rendue que si un article du
   corpus la fonde, et cet article est RELU dans le corpus (fondements.py) —
   jamais écrit à la main. Si l'article manque, la détection est supprimée.

3. LE DROIT DIT CE QU'IL DIT. Quand le corpus ne tranche pas (clause pénale
   excessive, clause abusive au sens du droit de la consommation, réserve de
   propriété), le moteur le dit dans `lacunes` au lieu de combler le vide.
   Voir fondements.LACUNES.

POURQUOI LA NÉGATION EST TRAITÉE À PART
---------------------------------------
« Le présent contrat ne contient aucune clause pénale » contient les mots
« clause pénale ». Un détecteur par mots-clés y voit une clause pénale et
alerte sur son contraire exact. Un contrat produit ici une DÉCISION juridique :
alerter sur une clause absente, c'est faire renoncer un client à une signature
qui ne présentait pas ce risque. La négation est donc filtrée en amont
(_est_nie), en français et en arabe.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

try:  # importé comme paquet
    from .fondements import LACUNES, Fondement, fondement
except ImportError:  # pragma: no cover - exécution directe du fichier
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from fondements import LACUNES, Fondement, fondement  # type: ignore


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

# Diacritiques arabes et tatweel : « جزائيّ » et « جزائي » sont le même mot.
# Le PDF d'un contrat les porte de façon imprévisible selon la saisie.
_DIACRITIQUES = re.compile(r'[\u064B-\u0652\u0640]')

# Caractères de contrôle : un PDF mal extrait en charrie (\x00, \x0b, \x1f).
# Ils cassent les regex et rendent l'extrait illisible à l'écran. On les
# remplace par une espace — sans supprimer le caractère, pour que les
# positions renvoyées restent comparables au texte source.
_CONTROLES = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

_CHIFFRES_AR = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')

# Au-delà, le texte n'est plus un contrat mais un recueil : on analyse quand
# même, mais en bornant le travail des regex pour ne pas bloquer l'API.
LIMITE_CARACTERES = 400_000


def normaliser(texte: str) -> str:
    """Prépare le texte pour la RECHERCHE, sans jamais servir de citation.

    Le texte normalisé sert uniquement à faire matcher les motifs. Les extraits
    rendus au juriste sont toujours prélevés sur le texte D'ORIGINE, aux mêmes
    positions : la normalisation préserve la longueur, caractère pour
    caractère, ce qui est la condition pour que les positions restent valides.
    """
    if not texte:
        return ''
    t = unicodedata.normalize('NFKC', texte)
    if len(t) != len(texte):
        # NFKC a changé la longueur (ligature décomposée) : on repart du texte
        # brut plutôt que de rendre des positions fausses.
        t = texte
    t = _CONTROLES.sub(' ', t)
    t = t.translate(_CHIFFRES_AR)
    t = _DIACRITIQUES.sub(' ', t)       # substitution 1:1, longueur conservée
    # Unification des variantes de l'alif et du yaa : substitutions 1 pour 1.
    for source, cible in (('أ', 'ا'), ('إ', 'ا'), ('آ', 'ا'),
                          ('ى', 'ي'), ('ئ', 'ي'), ('ؤ', 'و')):
        t = t.replace(source, cible)
    return t


def _sans_accents(texte: str) -> str:
    """Retire les accents français, longueur conservée (NFD puis filtrage).

    « pénale » et « penale » doivent matcher : un contrat scanné perd ses
    accents une fois sur deux. On ne peut pas utiliser NFD tel quel — il
    allonge le texte et casse les positions — donc on remappe caractère par
    caractère.
    """
    sortie = []
    for car in texte:
        decompose = unicodedata.normalize('NFD', car)
        base = ''.join(c for c in decompose if not unicodedata.combining(c))
        sortie.append(base if len(base) == 1 else car)
    return ''.join(sortie)


# ---------------------------------------------------------------------------
# Négation
# ---------------------------------------------------------------------------

# Formules par lesquelles un contrat DÉNIE la clause qu'il nomme. Français et
# arabe, parce qu'un contrat bilingue nie dans une langue ce qu'il nomme dans
# l'autre.
_NEGATIONS = (
    r"ne\s+(?:contient|comporte|pr[ée]voit|stipule|inclut|renferme)\s+"
    r"(?:aucune?|pas\s+de|nulle)",
    r"(?:aucune?|nulle)\s+clause",
    r"n['’]\s*(?:est|a)\s+pas\s+(?:pr[ée]vue?|stipul[ée]e?|applicable)",
    r"sans\s+(?:aucune?\s+)?clause",
    r"exclu\w*\s+(?:toute?s?\s+)?clause",
    r"est\s+(?:express[ée]ment\s+)?[ée]cart[ée]e?",
    # Négation qui précède IMMÉDIATEMENT le motif, sans que le mot « clause »
    # les sépare : « Aucune pénalité de retard n'est applicable », « Les
    # parties excluent toute réserve de propriété ». Sans ces deux formes,
    # le filtre ne voyait la négation que lorsqu'elle portait littéralement
    # sur le mot « clause » — et laissait passer tout le reste.
    r"(?:aucune?|nulle?|nul)\s+(?:\w+[\s'’]+){0,3}$",
    r"exclu\w*\s+(?:toute?s?\s+)?(?:\w+[\s'’]+){0,3}$",
    # arabe
    r"لا\s+يتضمن",
    r"لا\s+يحتوي",
    r"لا\s+ينص",
    r"لا\s+يوجد",
    r"دون\s+اي\s+شرط",
    r"بدون\s+شرط",
    r"خال\s+من",
)
_NEGATION_RX = re.compile('|'.join(_NEGATIONS), re.IGNORECASE)

# Fenêtre, en caractères, dans laquelle une négation neutralise un mot-clé.
# 90 est la longueur typique d'une phrase de contrat : au-delà, la négation
# porte sur une autre stipulation. Calibré sur les contrats d'exemple.
PORTEE_NEGATION = 90


def _est_nie(texte_norm: str, debut: int) -> bool:
    """La clause trouvée à `debut` est-elle déniée par la phrase qui la porte ?

    On regarde EN AMONT seulement : en français comme en arabe, la négation
    précède l'objet nié (« ne contient aucune clause pénale », « لا يتضمن هذا
    العقد أي شرط تحكيم »). Chercher en aval ferait taire des clauses réelles
    suivies d'une phrase négative sans rapport.
    """
    amont = texte_norm[max(0, debut - PORTEE_NEGATION):debut]
    # La négation ne franchit pas une fin de phrase : un point sépare deux
    # stipulations distinctes.
    for separateur in ('. ', '.\n', '؛', '\n\n'):
        coupe = amont.rfind(separateur)
        if coupe != -1:
            amont = amont[coupe + len(separateur):]
    return bool(_NEGATION_RX.search(amont))


# ---------------------------------------------------------------------------
# Catalogue des clauses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Regle:
    """Une clause à chercher, et les articles qui la fondent.

    `fondements` est une liste de couples (code_id, article) VÉRIFIÉS dans le
    corpus. Si aucun n'est retrouvé au chargement, la règle est désactivée :
    le moteur perd une détection plutôt que de citer un article fantôme.
    """

    identifiant: str
    intitule_fr: str
    gravite: str                       # 'critique' | 'eleve' | 'moyen'
    motifs: tuple[str, ...]            # regex, FR et AR
    fondements: tuple[tuple[str, int], ...]
    explication_fr: str                # ce que risque le signataire, 1 phrase
    reserve_fr: str = ''               # ce que le corpus ne permet PAS de dire


GRAVITES = ('critique', 'eleve', 'moyen')

CATALOGUE: tuple[Regle, ...] = (
    Regle(
        identifiant='clause_penale',
        intitule_fr="Clause pénale / indemnité forfaitaire",
        gravite='eleve',
        motifs=(
            r"clause\s+p[ée]nale",
            r"indemnit[ée]\s+forfaitaire",
            r"p[ée]nalit[ée]\s+forfaitaire",
            r"[àa]\s+titre\s+de\s+dommages[\s\-]et[\s\-]int[ée]r[êe]ts\s+forfaitaires",
            r"dommages[\s\-]int[ée]r[êe]ts\s+(?:fix[ée]s|[ée]valu[ée]s)\s+forfaitairement",
            r"شرط\s+جزايي",          # جزائي normalisé : ئ -> ي
            r"الشرط\s+الجزايي",
            r"تعويض\s+جزافي",
            r"غرامة\s+جزافية",
        ),
        # COC 277 : l'inexécution ou le retard oblige à réparer, même sans
        # faute intentionnelle. COC 278 : c'est au tribunal qu'il revient
        # d'apprécier le préjudice ("موكولة لحكمة المجلس").
        fondements=(('coc', 277), ('coc', 278)),
        explication_fr=(
            "Vous devrez la somme fixée dès le premier manquement, sans que le "
            "créancier ait à prouver le moindre préjudice réel."
        ),
        reserve_fr=(
            "Le corpus ne contient aucun article nommant la clause pénale : "
            "il ne permet donc PAS d'affirmer que le juge pourrait en réduire "
            "le montant. Seul est fondé le principe que l'évaluation du "
            "préjudice relève du tribunal (COC art. 278)."
        ),
    ),
    Regle(
        identifiant='arbitrage',
        intitule_fr="Clause compromissoire (arbitrage)",
        gravite='critique',
        motifs=(
            r"clause\s+compromissoire",
            r"(?:soumis|tranch[ée]s?|r[ée]gl[ée]s?|r[ée]solus?)\s+"
            r"(?:[^.\n]{0,40})?par\s+(?:voie\s+d[e']\s*)?arbitrage",
            r"tribunal\s+arbitral",
            r"arbitre\s+unique",
            r"r[èe]glement\s+d[e']\s*arbitrage",
            r"centre\s+de\s+conciliation\s+et\s+d[e']\s*arbitrage",
            r"شرط\s+تحكيمي?",
            r"اتفاقية\s+التحكيم",
            r"هيية\s+التحكيم",        # هيئة après normalisation (ئ -> ي)
            r"عن\s+طريق\s+التحكيم",
            r"محكم\s+واحد",
        ),
        # Arbitrage 7 : on peut stipuler une clause compromissoire pour les
        # litiges à naître en matière civile et commerciale.
        # Arbitrage 5 : la convention n'est établie que par écrit.
        # Arbitrage 52 : saisi malgré la clause, le tribunal RENVOIE les
        # parties à l'arbitrage — c'est la conséquence que le signataire subit.
        fondements=(('arbitrage', 7), ('arbitrage', 5), ('arbitrage', 52)),
        explication_fr=(
            "Vous renoncez au juge étatique : saisi malgré cette clause, le "
            "tribunal renverra les parties à l'arbitrage, dont le coût est à "
            "votre charge."
        ),
    ),
    Regle(
        identifiant='attribution_juridiction',
        intitule_fr="Clause attributive de juridiction",
        gravite='eleve',
        motifs=(
            r"attribution\s+de\s+(?:juridiction|comp[ée]tence)",
            r"(?:seul|seuls?)\s+(?:le\s+)?tribuna(?:l|ux)\s+[^.\n]{0,50}"
            r"(?:sera|seront|est|sont)\s+comp[ée]tents?",
            r"comp[ée]tence\s+exclusive\s+(?:du|des|au)\s+tribuna",
            r"tribunal\s+de\s+[^.\n]{0,40}\s+sera\s+seul\s+comp[ée]tent",
            r"juridiction\s+exclusive",
            r"[ée]lection\s+de\s+domicile\s+[^.\n]{0,60}comp[ée]tence",
            r"الاختصاص\s+(?:الحصري|المطلق)",
            r"المحكمة\s+المختصة\s+حصريا",
            r"ترجع\s+بالنظر\s+حصريا",
            r"محاكم\s+[^.\n]{0,25}\s+دون\s+سواها",
        ),
        # CPCC 3 : « لا عمل على كل اتفاق من شأنه مخالفة الاختصاص الحكمي المعين
        # بالمجلة » — toute convention contraire à la compétence d'attribution
        # fixée par le code est SANS EFFET. C'est exactement le risque : la
        # clause peut être lettre morte, et le plaideur l'ignore.
        # CPCC 30 : la compétence territoriale de principe est celle du
        # domicile du défendeur.
        fondements=(('procciv', 3), ('procciv', 30)),
        explication_fr=(
            "Vous devrez plaider devant un tribunal éloigné de votre siège, "
            "alors que la règle par défaut vous aurait permis d'assigner au "
            "domicile du défendeur."
        ),
        reserve_fr=(
            "CPCC art. 3 prive d'effet toute convention contraire à la "
            "compétence d'ATTRIBUTION fixée par le code ; il ne dit pas que "
            "toute clause de compétence territoriale est nulle. Le moteur "
            "signale la clause et cite le texte, sans trancher sa validité."
        ),
    ),
    Regle(
        identifiant='penalite_retard',
        intitule_fr="Délai de paiement et pénalités de retard",
        gravite='moyen',
        motifs=(
            r"p[ée]nalit[ée]s?\s+de\s+retard",
            r"int[ée]r[êe]ts?\s+de\s+retard",
            r"int[ée]r[êe]ts?\s+moratoires",
            r"\d+\s*%\s*par\s+(?:jour|semaine|mois)\s+de\s+retard",
            r"major[ée]\s+de\s+\d+\s*%\s+par\s+(?:jour|mois)",
            r"tout\s+retard\s+de\s+paiement\s+entra[îi]ne",
            # « خطية التأخير » comme « خطية تأخير » : en arabe l'article
            # défini est facultatif dans ce syntagme, et les deux formes
            # s'écrivent couramment dans le même contrat.
            r"خطية\s+(?:ال)?تاخير",
            r"فوايض\s+(?:ال)?تاخير",       # فوائض normalisé (ئ -> ي)
            r"غرامة\s+(?:ال)?تاخير",
            r"نسبة\s+الفايض",
        ),
        # COC 269 : le débiteur est en demeure par l'échéance du terme convenu.
        # COC 278 al. 2 : pour une obligation de somme d'argent, la réparation
        # se limite au taux d'intérêt fixé par la loi.
        # COC 1100 : à défaut de taux convenu, le taux légal est de 7 % en
        # matière civile, et en matière commerciale le taux maximal des crédits
        # bancaires majoré d'un demi-point.
        fondements=(('coc', 269), ('coc', 278), ('coc', 1100)),
        explication_fr=(
            "Un simple dépassement de l'échéance vous met en demeure de plein "
            "droit et fait courir les pénalités, sans mise en demeure préalable."
        ),
    ),
    Regle(
        identifiant='clause_resolutoire',
        intitule_fr="Clause résolutoire de plein droit",
        gravite='critique',
        motifs=(
            r"clause\s+r[ée]solutoire",
            r"r[ée]solu\s+de\s+plein\s+droit",
            r"r[ée]siliation\s+de\s+plein\s+droit",
            r"r[ée]sili[ée]\s+de\s+plein\s+droit",
            r"r[ée]solution\s+de\s+plein\s+droit",
            r"sans\s+(?:aucune\s+)?(?:mise\s+en\s+demeure|formalit[ée]\s+"
            r"judiciaire|intervention\s+(?:du|d[e']\s*un)\s+juge)",
            r"sans\s+sommation\s+ni\s+mise\s+en\s+demeure",
            r"يفسخ\s+العقد\s+بقوة\s+القانون",
            r"فسخ\s+العقد\s+تلقاييا",   # تلقائيا normalisé
            r"ينفسخ\s+العقد\s+بمجرد",
            r"دون\s+حاجة\s+الى\s+(?:انذار|تنبيه)",
        ),
        # COC 274 : si les parties ont stipulé que l'inexécution emporte
        # résolution, le contrat est résolu DE PLEIN DROIT dès la survenance.
        # COC 680 (vente) : la même règle appliquée au défaut de paiement du
        # prix. COC 273 in fine : hors stipulation, « وفسخ العقد لا يكون إلا
        # بحكم » — la résolution suppose un jugement. C'est précisément la
        # protection que la clause fait perdre.
        fondements=(('coc', 274), ('coc', 680), ('coc', 273)),
        explication_fr=(
            "Le contrat s'éteint automatiquement au premier manquement, sans "
            "juge et sans le délai que le tribunal vous aurait accordé."
        ),
    ),
    Regle(
        identifiant='limitation_responsabilite',
        intitule_fr="Clause limitative ou exonératoire de responsabilité",
        gravite='eleve',
        motifs=(
            r"limitation\s+de\s+responsabilit[ée]",
            r"clause\s+(?:limitative|[ée]xon[ée]ratoire|exon[ée]ratoire)",
            r"responsabilit[ée]\s+(?:est\s+)?(?:strictement\s+)?limit[ée]e\s+"
            r"[àa]\s+",
            r"ne\s+(?:saurait|pourra)\s+[êe]tre\s+tenue?\s+responsable",
            r"d[ée]cline\s+toute\s+responsabilit[ée]",
            r"exon[ée]r[ée]e?\s+de\s+toute\s+responsabilit[ée]",
            r"aucune\s+indemnit[ée]\s+ne\s+(?:sera|pourra\s+[êe]tre)\s+"
            r"(?:due|r[ée]clam[ée]e)",
            # المسؤولية après normalisation : ؤ -> و, d'où « المسوولية ».
            r"شرط\s+الاعفاء\s+من\s+المسوولية",
            r"تحديد\s+المسوولية",
            r"تحدد\s+مسوولية",
            r"لا\s+يتحمل\s+اي\s+مسوولية",
            r"يعفى\s+من\s+كل\s+مسوولية",
        ),
        # Commerce 643 : en transport, le voiturier peut limiter sa
        # responsabilité MAIS « يكون باطلا كل شرط ... بإعفائه كليا من
        # المسؤولية » — l'exonération totale est nulle, et la limitation tombe
        # en cas de faute lourde ou intentionnelle (« خطأ فاحش أو تعمد الخطأ »).
        # Sociétés 118 : est nulle de nullité absolue la renonciation anticipée
        # à l'action en responsabilité contre le dirigeant.
        # COC 642 : en vente, la clause de non-garantie ne dispense jamais le
        # vendeur de restituer le prix, et tombe devant son propre fait.
        fondements=(('commerce', 643), ('societes', 118), ('coc', 642)),
        explication_fr=(
            "En cas de dommage, votre indemnisation sera plafonnée à un montant "
            "sans rapport avec votre préjudice réel."
        ),
        reserve_fr=(
            "Les articles disponibles sont SPÉCIAUX (transport, action "
            "sociale, garantie d'éviction). Le corpus ne porte aucune règle "
            "générale annulant l'exonération du dol ou de la faute lourde : "
            "hors de ces terrains, le moteur signale sans conclure à la nullité."
        ),
    ),
    Regle(
        identifiant='reserve_propriete',
        intitule_fr="Clause de réserve de propriété",
        gravite='moyen',
        motifs=(
            r"r[ée]serve\s+de\s+propri[ée]t[ée]",
            r"demeure(?:nt|ra|ront)?\s+(?:la\s+)?propri[ée]t[ée]\s+"
            r"(?:exclusive\s+)?(?:du|de\s+la)\s+vendeur",
            r"propri[ée]t[ée]\s+(?:n[e']\s*est|ne\s+sera)\s+transf[ée]r[ée]e\s+"
            r"qu[e']\s*(?:apr[èe]s|au)\s+(?:complet\s+)?paiement",
            r"transfert\s+de\s+propri[ée]t[ée]\s+[^.\n]{0,40}"
            r"(?:int[ée]gral|complet)\s+paiement",
            r"شرط\s+الاحتفاظ\s+بالملكية",
            r"تبقى\s+الملكية\s+للباي?ع",
            r"لا\s+تنتقل\s+الملكية\s+الا\s+بعد",
        ),
        # COC 583 : « إذا تم البيع بتراضي الجانبين انتقلت ملكية المشترى
        # للمشتري » — par principe la propriété passe dès l'accord. La clause
        # DÉROGE à ce texte, ce qui est précisément ce qu'il faut signaler.
        # COC 601 : le vendeur garde une rétention légale dans des cas listés,
        # sans avoir besoin de la clause.
        fondements=(('coc', 583), ('coc', 601)),
        explication_fr=(
            "Acheteur, vous détenez la marchandise sans en être propriétaire "
            "tant que le prix n'est pas intégralement payé, et vous ne pouvez "
            "donc ni la revendre librement ni la donner en garantie."
        ),
        reserve_fr=(
            "Aucun article du corpus ne régit la réserve de propriété en tant "
            "que telle ni son opposabilité en procédure collective. Seule la "
            "règle à laquelle elle déroge est fondée (COC art. 583)."
        ),
    ),
    Regle(
        identifiant='renonciation_prescription',
        intitule_fr="Renonciation anticipée à la prescription",
        gravite='critique',
        motifs=(
            r"renonce\s+(?:d[èe]s\s+[àa]\s+pr[ée]sent\s+)?"
            r"(?:express[ée]ment\s+)?[àa]\s+(?:se\s+pr[ée]valoir\s+de\s+)?"
            r"(?:la\s+|toute\s+)?prescription",
            r"renonciation\s+[àa]\s+(?:la\s+)?prescription",
            r"ne\s+(?:pourra|saurait)\s+(?:pas\s+)?(?:se\s+pr[ée]valoir|"
            r"invoquer|opposer)\s+(?:de\s+|la\s+)?(?:la\s+)?prescription",
            r"(?:d[ée]lai\s+de\s+)?prescription\s+(?:est\s+)?"
            r"(?:port[ée]|[ée]tendu|prolong[ée])\s+[àa]\s+\d+",
            r"التنازل\s+عن\s+التقادم",
            r"يتنازل\s+عن\s+(?:حق\s+)?التمسك\s+بالتقادم",
            r"لا\s+يجوز\s+له\s+التمسك\s+بمرور\s+الزمان",
        ),
        # COC 386, texte exact : « لا يسوغ ترك حق التمسك بمرور الزمان قبل
        # حصوله فإذا انقضى الزمان ساغ الترك ». Le corpus TRANCHE : la
        # renonciation ANTICIPÉE est interdite ; seule la renonciation
        # postérieure à l'acquisition est licite. C'est la seule des neuf
        # clauses où le moteur peut affirmer une nullité.
        fondements=(('coc', 386), ('coc', 402)),
        explication_fr=(
            "Cette renonciation est prise avant que la prescription ne soit "
            "acquise : COC art. 386 ne la permet pas, et vous ne pouvez donc "
            "pas compter dessus — dans un sens comme dans l'autre."
        ),
    ),
    Regle(
        identifiant='clause_potestative',
        intitule_fr="Clause laissée à la seule volonté d'une partie",
        gravite='eleve',
        motifs=(
            r"[àa]\s+(?:sa|son)\s+(?:seule\s+)?"
            r"(?:discr[ée]tion|convenance|gr[ée])\s+(?:absolue|exclusive)?",
            r"unilat[ée]ralement\s+et\s+sans\s+justification",
            r"se\s+r[ée]serve\s+le\s+droit\s+de\s+modifier\s+[àa]\s+tout\s+"
            r"moment",
            r"(?:modifier|r[ée]viser)\s+[^.\n]{0,40}\s+sans\s+(?:l[e']\s*)?"
            r"accord\s+(?:pr[ée]alable\s+)?(?:de\s+l[e']\s*autre|du\s+client)",
            r"حسب\s+ارادته\s+المنفردة",
            r"بمحض\s+ارادته",
            r"دون\s+موافقة\s+الطرف\s+الاخر",
        ),
        # COC 121 : « يبطل الالتزام إذا كان وجوده موقوفا على مجرد رضاء
        # الملتزم » — l'obligation dont l'existence dépend de la seule volonté
        # du débiteur est nulle. COC 119 : la condition contraire à l'essence
        # du contrat est nulle et emporte nullité du contrat.
        fondements=(('coc', 121), ('coc', 119)),
        explication_fr=(
            "Votre cocontractant peut faire varier seul l'étendue de son "
            "engagement, ce que COC art. 121 frappe de nullité lorsque "
            "l'obligation dépend de sa seule volonté."
        ),
    ),
)


# ---------------------------------------------------------------------------
# Détection de la langue et porte d'entrée « est-ce un contrat ? »
# ---------------------------------------------------------------------------

_ARABE = re.compile(r'[\u0600-\u06FF]')
_LATIN = re.compile(r'[A-Za-zÀ-ÿ]')

# Marqueurs qu'un texte est bien un contrat. Comme pour doc_gate.py sur les
# factures, on n'accepte pas sur un score nu : on exige des preuves nommées.
_MARQUEURS_CONTRAT = (
    (r"\b(?:contrat|convention|bail|march[ée]|protocole\s+d[e']\s*accord)\b",
     'mot « contrat » ou équivalent'),
    (r"\b(?:article|clause)\s+\d|\bart(?:icle)?\.?\s*\d", "articles numérotés"),
    (r"\b(?:les\s+parties|partie\s+de\s+(?:premi[èe]re|seconde)\s+part|"
     r"entre\s+les\s+soussign[ée]s|le\s+pr[ée]sent\s+contrat)\b",
     'désignation des parties'),
    (r"\b(?:s[e']\s*engage|s[e']\s*obligent?|convien(?:t|nent)|"
     r"il\s+a\s+[ée]t[ée]\s+(?:convenu|arr[êe]t[ée]))\b",
     "formule d'engagement"),
    (r"(?:عقد|اتفاقية|كراء|صفقة)", 'mot « عقد » / « اتفاقية »'),
    (r"(?:الفصل|البند)\s*\d", 'articles numérotés (arabe)'),
    (r"(?:الطرف\s+الاول|الطرف\s+الثاني|بين\s+الممضيين|هذا\s+العقد)",
     'désignation des parties (arabe)'),
    (r"(?:يلتزم|اتفق\s+الطرفان|تم\s+الاتفاق)", "formule d'engagement (arabe)"),
)

MIN_MARQUEURS = 2


def detecter_langues(texte: str) -> list[str]:
    """Quelles langues porte ce contrat ? ['fr'], ['ar'] ou les deux.

    Les contrats tunisiens sont couramment bilingues, et la version arabe fait
    foi devant les juridictions. Savoir quelle langue est présente permet au
    rapport de signaler qu'une seule des deux versions a pu être analysée.
    """
    langues = []
    n_ar = len(_ARABE.findall(texte or ''))
    n_fr = len(_LATIN.findall(texte or ''))
    total = n_ar + n_fr
    if total == 0:
        return []
    # 8 % : calibré sur exemples/contrat_ar_entreprise.txt, un contrat
    # tunisien réel dans sa forme — corps en arabe, avec les stipulations
    # sensibles doublées en français. La part française y pèse 11,5 % : un
    # seuil à 15 % classait ce contrat comme unilingue arabe et faisait
    # silence sur une version française qui engage pourtant le signataire.
    # Sous 8 %, il ne reste que des noms propres et un en-tête.
    if n_fr / total >= 0.08:
        langues.append('fr')
    if n_ar / total >= 0.08:
        langues.append('ar')
    return langues or (['fr'] if n_fr >= n_ar else ['ar'])


def est_un_contrat(texte: str) -> tuple[bool, str | None, list[str]]:
    """Porte d'entrée : ce texte est-il bien un contrat ?

    Même logique que packages/legal/doc_gate.py pour les factures, et pour la
    même raison : Mizan a déjà produit une mise en demeure à partir du
    programme du hackathon. Analyser un CV et en « détecter » des clauses
    à risque serait la version contrat de cette faute.
    """
    t = normaliser(texte or '')
    if not t.strip():
        return False, "le document est vide", []
    trouves = [nom for motif, nom in _MARQUEURS_CONTRAT
               if re.search(motif, t, re.IGNORECASE)]
    if len(trouves) < MIN_MARQUEURS:
        return (False,
                f"seulement {len(trouves)} indice(s) de contrat sur "
                f"{len(_MARQUEURS_CONTRAT)} ; ce document ne se présente pas "
                f"comme un contrat",
                trouves)
    return True, None, trouves


# ---------------------------------------------------------------------------
# Résultat
# ---------------------------------------------------------------------------

@dataclass
class ClauseDetectee:
    """Une clause à risque, avec la preuve textuelle et le fondement légal."""

    identifiant: str
    intitule_fr: str
    gravite: str
    extrait: str                 # VERBATIM du contrat, jamais reformulé
    position: int                # index du début de l'extrait dans le texte
    ligne: int                   # numéro de ligne, pour retrouver la clause
    explication_fr: str
    fondements: list = field(default_factory=list)
    reserve_fr: str = ''

    def to_dict(self) -> dict:
        return {
            'identifiant': self.identifiant,
            'intitule_fr': self.intitule_fr,
            'gravite': self.gravite,
            'extrait': self.extrait,
            'position': self.position,
            'ligne': self.ligne,
            'explication_fr': self.explication_fr,
            'fondements': [f.to_dict() for f in self.fondements],
            'reserve_fr': self.reserve_fr,
        }


@dataclass
class Rapport:
    """Ce que l'analyse rend, y compris quand elle ne rend rien."""

    analyse: bool                # False = le moteur s'est abstenu
    motif_abstention: str | None
    langues: list
    clauses: list = field(default_factory=list)
    niees: list = field(default_factory=list)   # clauses niées par le contrat
    lacunes: dict = field(default_factory=dict)
    n_caracteres: int = 0

    @property
    def gravite_max(self) -> str | None:
        """La gravité la plus haute rencontrée, pour l'affichage."""
        for niveau in GRAVITES:
            if any(c.gravite == niveau for c in self.clauses):
                return niveau
        return None

    def to_dict(self) -> dict:
        return {
            'analyse': self.analyse,
            'motif_abstention': self.motif_abstention,
            'langues': self.langues,
            'n_caracteres': self.n_caracteres,
            'gravite_max': self.gravite_max,
            'clauses': [c.to_dict() for c in self.clauses],
            'niees': self.niees,
            'lacunes': self.lacunes,
        }


MESSAGE_ABSTENTION = (
    "Mizan n'a pas analysé ce document : il ne se présente pas comme un "
    "contrat. Aucune clause n'est signalée, car signaler un risque dans un "
    "document qui n'en porte pas serait aussi grave que d'en manquer un."
)


# ---------------------------------------------------------------------------
# Extraction de l'extrait verbatim
# ---------------------------------------------------------------------------

# Longueur maximale d'un extrait rendu. Assez pour que la clause se comprenne
# seule, assez court pour tenir dans un rapport.
LONGUEUR_EXTRAIT = 320


def _extraire_phrase(texte: str, debut: int, fin: int) -> tuple[str, int, int]:
    """Remonte à la phrase entière qui porte le motif, dans le TEXTE D'ORIGINE.

    Un juriste ne cite pas trois mots : il cite la stipulation. On élargit
    donc le match jusqu'aux bornes de phrase, puis on renvoie la tranche du
    texte source — non normalisée, non reformulée, telle qu'elle est écrite
    dans le contrat.

    Renvoie (extrait, début, fin) : les deux bornes servent au dédoublonnage.
    Deux motifs différents de la même règle qui tombent dans la MÊME phrase
    décrivent une seule clause, et le juriste doit la voir une seule fois.
    """
    bornes = ('. ', '.\n', '\n\n', '؛', '؟', '!\n')
    gauche = max(0, debut - LONGUEUR_EXTRAIT)
    amont = texte[gauche:debut]
    coupe = max((amont.rfind(b) + len(b) for b in bornes if b in amont),
                default=0)
    # Une puce ou un numéro d'article est aussi une borne naturelle.
    saut = amont.rfind('\n')
    if saut != -1 and saut + 1 > coupe:
        coupe = saut + 1
    depart = gauche + coupe

    droite = min(len(texte), fin + LONGUEUR_EXTRAIT)
    aval = texte[fin:droite]
    stop = min((aval.find(b) + len(b) for b in bornes if b in aval),
               default=-1)
    if stop <= 0:
        saut = aval.find('\n')
        stop = saut if saut != -1 else len(aval)
    arrivee = fin + stop

    extrait = texte[depart:arrivee]
    # Les sauts de ligne internes d'un PDF ne portent aucun sens : on les
    # aplatit pour l'affichage. Aucun mot n'est modifié ni supprimé.
    extrait = ' '.join(extrait.split())
    if len(extrait) > LONGUEUR_EXTRAIT:
        extrait = extrait[:LONGUEUR_EXTRAIT].rstrip() + '…'
    return extrait, depart, arrivee


def _charger_fondements(regle: Regle) -> list[Fondement]:
    """Relit dans le corpus les articles de la règle. Absents = écartés."""
    trouves = []
    for code_id, article in regle.fondements:
        f = fondement(code_id, article)
        if f is not None:
            trouves.append(f)
    return trouves


# ---------------------------------------------------------------------------
# Analyse
# ---------------------------------------------------------------------------

def analyser(texte: str, exiger_contrat: bool = True) -> Rapport:
    """Analyse un contrat et rend les clauses à risque, chacune fondée.

    `exiger_contrat=False` désactive la porte d'entrée, pour analyser un
    extrait isolé de clause (usage test, ou fragment collé par l'utilisateur).
    Par défaut la porte est active : un document qui n'est pas un contrat
    produit une ABSTENTION, jamais une liste de clauses.
    """
    brut = texte or ''
    if len(brut) > LIMITE_CARACTERES:
        # On ne refuse pas un contrat long : on l'analyse jusqu'à la limite et
        # on le dit. Un recueil de 2 Mo qui bloque l'API est une panne ;
        # un contrat de 500 pages tronqué et signalé reste utilisable.
        brut = brut[:LIMITE_CARACTERES]

    langues = detecter_langues(brut)

    if exiger_contrat:
        ok, motif, _ = est_un_contrat(brut)
        if not ok:
            return Rapport(
                analyse=False,
                motif_abstention=motif,
                langues=langues,
                lacunes=dict(LACUNES),
                n_caracteres=len(brut),
            )
    elif not brut.strip():
        return Rapport(
            analyse=False,
            motif_abstention="le document est vide",
            langues=[],
            lacunes=dict(LACUNES),
            n_caracteres=0,
        )

    # Le texte normalisé sert au MATCH ; les extraits viennent du texte brut,
    # aux mêmes positions. normaliser() conserve la longueur : c'est ce qui
    # rend cette correspondance exacte.
    norme = normaliser(brut)
    # Pour le français, on travaille en plus sur une variante désaccentuée,
    # de même longueur, afin que « pénale » et « penale » matchent tous deux.
    norme_fr = _sans_accents(norme)

    clauses: list[ClauseDetectee] = []
    niees: list[dict] = []

    for regle in CATALOGUE:
        fonds = _charger_fondements(regle)
        if not fonds:
            # RÈGLE DÉSACTIVÉE : le corpus ne porte plus aucun de ses articles.
            # On préfère perdre la détection que citer un article introuvable.
            continue

        # Phrases déjà retenues pour CETTE règle, par leurs bornes. Deux
        # motifs qui désignent la même stipulation (« clause pénale » et
        # « indemnité forfaitaire » dans le même article) ne doivent produire
        # qu'une seule ligne de rapport : un juriste qui lit deux fois le même
        # risque cesse de faire confiance à la liste.
        retenues: list[tuple[int, int]] = []

        def _deja_vue(a: int, b: int) -> bool:
            """La phrase [a, b) recouvre-t-elle une phrase déjà retenue ?"""
            return any(a < fin_vue and deb_vue < b
                       for deb_vue, fin_vue in retenues)

        for motif in regle.motifs:
            rx = re.compile(motif, re.IGNORECASE)
            for cible in (norme, norme_fr):
                for m in rx.finditer(cible):
                    debut, fin = m.start(), m.end()
                    extrait, position, terme = _extraire_phrase(
                        brut, debut, fin)
                    if not extrait.strip() or _deja_vue(position, terme):
                        continue

                    if _est_nie(cible, debut):
                        retenues.append((position, terme))
                        niees.append({
                            'identifiant': regle.identifiant,
                            'intitule_fr': regle.intitule_fr,
                            'extrait': extrait,
                            'motif': (
                                "le contrat nie expressément cette clause ; "
                                "aucun risque n'est signalé sur ce fondement"
                            ),
                        })
                        continue

                    retenues.append((position, terme))
                    clauses.append(ClauseDetectee(
                        identifiant=regle.identifiant,
                        intitule_fr=regle.intitule_fr,
                        gravite=regle.gravite,
                        extrait=extrait,
                        position=position,
                        ligne=brut.count('\n', 0, position) + 1,
                        explication_fr=regle.explication_fr,
                        fondements=fonds,
                        reserve_fr=regle.reserve_fr,
                    ))

    clauses.sort(key=lambda c: (GRAVITES.index(c.gravite), c.position))

    return Rapport(
        analyse=True,
        motif_abstention=None,
        langues=langues,
        clauses=clauses,
        niees=niees,
        lacunes=dict(LACUNES),
        n_caracteres=len(brut),
    )


def analyser_pdf(chemin: str | Path, exiger_contrat: bool = True) -> Rapport:
    """Analyse un contrat livré en PDF.

    On réutilise l'extraction déjà éprouvée de packages/legal/doc_gate.py via
    invoice.extract_text : le projet n'a pas besoin d'un second extracteur, et
    PyMuPDF (AGPL) est proscrit — pypdf/pdfplumber (BSD/MIT) font le travail.
    """
    chemin = Path(chemin)
    if not chemin.exists():
        return Rapport(
            analyse=False,
            motif_abstention=f"fichier introuvable : {chemin}",
            langues=[],
            lacunes=dict(LACUNES),
        )
    texte = _lire_pdf(chemin)
    return analyser(texte, exiger_contrat=exiger_contrat)


def _lire_pdf(chemin: Path) -> str:
    """Extrait le texte d'un PDF. pypdf d'abord, pdfplumber en secours."""
    try:
        from pypdf import PdfReader
        pages = [p.extract_text() or '' for p in PdfReader(str(chemin)).pages]
        texte = '\n'.join(pages)
        if texte.strip():
            return texte
    except Exception:  # pragma: no cover - dépend du PDF fourni
        pass
    try:  # pragma: no cover
        import pdfplumber
        with pdfplumber.open(str(chemin)) as pdf:
            return '\n'.join(p.extract_text() or '' for p in pdf.pages)
    except Exception:
        return ''


# ---------------------------------------------------------------------------
# Rendu texte, pour la démo et le débogage
# ---------------------------------------------------------------------------

def rendre(rapport: Rapport) -> str:
    """Rend le rapport en texte lisible par un juriste, citations comprises."""
    lignes: list[str] = []
    if not rapport.analyse:
        lignes.append("ABSTENTION")
        lignes.append(f"  motif : {rapport.motif_abstention}")
        lignes.append('')
        lignes.append(MESSAGE_ABSTENTION)
        return '\n'.join(lignes)

    langues = '+'.join(rapport.langues) or 'indéterminée'
    lignes.append(f"CONTRAT ANALYSÉ — langue(s) : {langues} — "
                  f"{rapport.n_caracteres} caractères")
    lignes.append(f"{len(rapport.clauses)} clause(s) à risque détectée(s)"
                  + (f" — gravité maximale : {rapport.gravite_max}"
                     if rapport.gravite_max else ''))
    lignes.append('')

    for i, c in enumerate(rapport.clauses, 1):
        lignes.append(f"[{i}] {c.intitule_fr}  ({c.gravite.upper()})")
        lignes.append(f"    identifiant : {c.identifiant}  "
                      f"(ligne {c.ligne}, position {c.position})")
        lignes.append(f"    EXTRAIT DU CONTRAT : « {c.extrait} »")
        lignes.append(f"    RISQUE : {c.explication_fr}")
        for f in c.fondements:
            lignes.append(f"    FONDEMENT : {f.citation_ar}")
            lignes.append(f"               {f.extrait_ar}")
        if c.reserve_fr:
            lignes.append(f"    RÉSERVE : {c.reserve_fr}")
        lignes.append('')

    if rapport.niees:
        lignes.append("CLAUSES NOMMÉES MAIS ÉCARTÉES (le contrat les nie) :")
        for n in rapport.niees:
            lignes.append(f"  - {n['intitule_fr']} : « {n['extrait']} »")
        lignes.append('')

    if rapport.lacunes:
        lignes.append("CE QUE LE CORPUS NE FONDE PAS :")
        for cle, texte in rapport.lacunes.items():
            lignes.append(f"  - {cle} : {texte}")
    return '\n'.join(lignes)


if __name__ == '__main__':  # pragma: no cover
    import sys
    if len(sys.argv) < 2:
        print("usage: python analyse.py <fichier.txt|fichier.pdf>")
        raise SystemExit(2)
    cible = Path(sys.argv[1])
    if cible.suffix.lower() == '.pdf':
        print(rendre(analyser_pdf(cible)))
    else:
        print(rendre(analyser(cible.read_text(encoding='utf-8'))))
