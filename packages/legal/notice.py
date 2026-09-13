"""La mise en demeure (إنذار) : un PROJET d'acte, jamais un acte signifié.

Repris du dépôt h4j (app/notice.py), qui produisait un PDF et rien d'autre.
Trois choses manquaient, et elles touchent au cœur du projet :

1. Le document ne disait nulle part qu'il n'était pas signifié. Un PDF qui
   porte l'en-tête « MISE EN DEMEURE », un cachet d'huissier à remplir et la
   mention « acte à signifier par huissier de justice » ressemble, pour une
   PME qui n'est pas juriste, à un acte qui produit ses effets. Il n'en
   produit aucun. CPC art. 5 et 60 : seul un huissier de justice
   (عدل منفذ) signifie, et c'est la signification — pas la rédaction — qui
   fait courir les délais. Mizan rédige ; elle ne signifie pas.

2. Le module ne savait produire qu'un PDF. L'API doit pouvoir rendre le
   TEXTE, avec ses articles, sans passer par un fichier binaire. Le texte est
   désormais la source ; le PDF n'en est qu'un rendu.

3. Rien n'empêchait de mettre en demeure sur une créance prescrite. C'est le
   pire conseil que cet outil puisse donner : le créancier paie un huissier
   pour réveiller un débiteur qui n'a qu'à opposer la prescription. Le module
   refuse désormais, et dit pourquoi.

Les citations d'articles viennent TOUJOURS de `legal_engine` (donc du corpus
indexé), jamais d'un modèle de langage, et sont reproduites en arabe mot pour
mot depuis `citation_ar`.
"""
import pathlib
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta

# --- Ce qui distingue un projet d'un acte ----------------------------------
# La mention est une constante, pas une chaîne recopiée à trois endroits :
# elle doit être impossible à perdre par inadvertance, et un test la verrouille.
MENTION_PROJET = "PROJET — NON SIGNIFIÉ"

MENTION_PROJET_LONGUE = (
    "PROJET — NON SIGNIFIÉ. Ce document est un projet d'acte rédigé par "
    "Mizan. Il n'a fait l'objet d'aucune signification et ne produit, en "
    "l'état, aucun effet de droit. Seul un huissier de justice (عدل منفذ) "
    "peut signifier une mise en demeure : c'est la signification, et elle "
    "seule, qui fait courir le délai laissé au débiteur."
)

AVERTISSEMENT_SOURCES = (
    "Les articles cités ci-dessus sont reproduits depuis le corpus des codes "
    "tunisiens indexé par Mizan. Aucun modèle de langage n'énonce ici une "
    "règle de droit."
)

# Le délai laissé au débiteur sous le seuil de l'huissier n'est fixé par aucun
# texte : c'est un délai d'usage. Il est nommé comme tel dans le document,
# sinon il se lit comme un délai légal qu'aucun article ne fonde.
DELAI_USAGE_JOURS = 8

FONT_PATH = '/usr/share/fonts/truetype/freefont/FreeSerif.ttf'
FONT_BOLD = '/usr/share/fonts/truetype/freefont/FreeSerifBold.ttf'

# Le dossier de sortie n'est créé qu'au moment où l'on écrit un PDF : importer
# ce module ne doit rien créer sur le disque.
OUT_DIR = pathlib.Path(__file__).resolve().parents[2] / 'generated'

MONTHS_FR = ['', 'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
             'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre']
NBSP = '\u00a0'


class CreancePrescrite(ValueError):
    """On ne met pas en demeure sur une créance éteinte.

    Le débiteur n'aurait qu'à opposer la prescription ; le créancier aurait
    payé un huissier pour se le faire dire. Le refus est la bonne réponse.
    """


def fr_date(iso):
    """2026-09-17 -> '17 septembre 2026' (français juridique, pas ISO)."""
    d = date.fromisoformat(iso) if isinstance(iso, str) else iso
    return f'{d.day} {MONTHS_FR[d.month]} {d.year}'


def fr_amount(v):
    """9520.0 -> '9 520,000' avec espaces insécables (sûr en bidi, français)."""
    return f'{v:,.3f}'.replace(',', NBSP).replace('.', ',')


def ar(text):
    """Met en forme + réordonne l'arabe pour que reportlab le dessine juste."""
    import arabic_reshaper
    from bidi.algorithm import get_display
    return get_display(arabic_reshaper.reshape(text))


@dataclass
class MiseEnDemeure:
    """Le projet d'acte, sous forme de données puis de texte.

    Tout ce qui est affiché, imprimé ou envoyé par l'API sort d'ici. Il n'y a
    donc qu'un seul endroit où la mention « projet — non signifié » peut
    exister, et un seul endroit où elle peut disparaître.
    """
    mention_projet: str
    mention_projet_longue: str
    titre_fr: str
    titre_ar: str
    creancier: dict
    debiteur: dict
    facture: dict
    montant_tnd: float
    montant_fr: str
    delai_jours: int
    delai_est_legal: bool
    date_limite: str
    huissier_requis: bool
    corps: list = field(default_factory=list)
    sommation_ar: list = field(default_factory=list)
    articles: list = field(default_factory=list)
    prescription: dict = field(default_factory=dict)
    lieu: str = ''
    date_acte: str = ''
    avertissement: str = AVERTISSEMENT_SOURCES
    texte: str = ''

    def to_dict(self):
        return asdict(self)


def construire(assessment, creancier, debiteur, facture=None):
    """Construit le projet de mise en demeure à partir de l'évaluation.

    `assessment` : la dataclass rendue par legal_engine.assess().
    `creancier`, `debiteur`, `facture` : des dicts.

    Lève CreancePrescrite si le délai de prescription est dépassé.
    """
    a = assessment
    facture = facture or {}

    # --- le garde-fou, avant toute rédaction -------------------------------
    if a.is_expired:
        raise CreancePrescrite(
            f"La créance est prescrite depuis {abs(a.days_left)} jours : le "
            f"délai a expiré le {fr_date(a.deadline)}. Mizan ne rédige pas de "
            f"mise en demeure sur une créance éteinte — le débiteur n'aurait "
            f"qu'à opposer la prescription, et la sommation aurait été payée "
            f"pour rien. {a.regime_reason_fr} Si vous estimez que le délai a "
            f"été interrompu (reconnaissance de dette, paiement partiel, acte "
            f"d'huissier), faites-le constater par un professionnel : "
            f"l'interruption ne se présume pas."
        )

    huissier = a.needs_bailiff
    delai = a.grace_days if huissier else DELAI_USAGE_JOURS
    date_limite = (date.fromisoformat(a.today) + timedelta(days=delai)).isoformat()

    nom_creancier = creancier.get('name') or creancier.get('nom') or 'le créancier'
    nom_debiteur = debiteur.get('name') or debiteur.get('nom') or 'le débiteur'
    num_facture = facture.get('invoice_no') or facture.get('numero') or '—'
    date_facture = facture.get('invoice_date') or facture.get('date') or a.invoice_date
    montant_fr = fr_amount(a.amount_tnd)

    corps = [
        f"Vous restez redevable envers {nom_creancier} de la somme de "
        f"{montant_fr} dinars tunisiens (DT), au titre de la facture "
        f"n° {num_facture} en date du {fr_date(date_facture)}, correspondant à "
        f"des marchandises livrées et réceptionnées sans réserve.",
    ]
    if huissier:
        corps.append(
            f"Par le présent projet d'acte, vous serez mis en demeure de régler "
            f"cette somme dans un délai de {delai} jours francs à compter de la "
            f"signification qui en sera faite par huissier de justice, soit au "
            f"plus tard le {fr_date(date_limite)} si la signification intervient "
            f"ce jour."
        )
    else:
        corps.append(
            f"Par le présent projet d'acte, vous serez invité à régler cette "
            f"somme dans un délai de {delai} jours, soit au plus tard le "
            f"{fr_date(date_limite)}. Ce délai est un délai d'usage : il n'est "
            f"fixé par aucun texte, le montant réclamé restant sous le seuil "
            f"au-delà duquel la sommation par huissier est requise."
        )
    corps.append(
        "À défaut de paiement dans ce délai, il sera procédé, sans autre avis, "
        "au recouvrement de la créance par voie d'injonction de payer, outre "
        "les intérêts de retard et la réparation du préjudice subi, ainsi que "
        "les frais de procédure."
    )
    corps.append("Sous toutes réserves de droit.")

    ar_montant = f'{a.amount_tnd:,.3f}'.replace(',', NBSP).replace('.', ',')
    sommation_ar = [
        f'ننبهكم بضرورة خلاص مبلغ {ar_montant} دينارا في أجل {delai} أيام كاملة',
        'وإلا سيقع القيام ضدكم طبق إجراءات الأمر بالدفع',
    ]

    # Les articles ne sont ni choisis ni reformulés ici : ce sont exactement
    # ceux que le moteur a retenus, avec leur citation arabe telle quelle.
    articles = [dict(s) for s in a.sources]

    doc = MiseEnDemeure(
        mention_projet=MENTION_PROJET,
        mention_projet_longue=MENTION_PROJET_LONGUE,
        titre_fr='MISE EN DEMEURE',
        titre_ar='إنــذار',
        creancier=dict(creancier),
        debiteur=dict(debiteur),
        facture={'numero': num_facture, 'date': date_facture},
        montant_tnd=a.amount_tnd,
        montant_fr=montant_fr,
        delai_jours=delai,
        delai_est_legal=huissier,
        date_limite=date_limite,
        huissier_requis=huissier,
        corps=corps,
        sommation_ar=sommation_ar,
        articles=articles,
        prescription={
            'regime': a.regime,
            'echeance': a.deadline,
            'jours_restants': a.days_left,
            'est_prescrit': a.is_expired,
            'urgence': a.urgency,
            'motif_fr': a.regime_reason_fr,
        },
        lieu=creancier.get('city') or creancier.get('ville') or 'Sfax',
        date_acte=a.today,
    )
    doc.texte = rendre_texte(doc)
    return doc


def rendre_texte(doc):
    """Le projet d'acte en texte brut, bilingue, prêt à être lu ou imprimé."""
    L = []
    A = L.append
    A(doc.mention_projet)
    A('=' * 68)
    A(doc.mention_projet_longue)
    A('')
    A(f'{doc.titre_fr}{" " * 24}{doc.titre_ar}')
    A('-' * 68)
    A("Projet de sommation de payer, à signifier par huissier de justice"
      if doc.huissier_requis else "Projet de sommation de payer")
    A('')
    A('LE CRÉANCIER — الدائــن')
    for c in ('name', 'nom'):
        if doc.creancier.get(c):
            A(f"  {doc.creancier[c]}")
            break
    for c in ('address', 'adresse'):
        if doc.creancier.get(c):
            A(f"  {doc.creancier[c]}")
            break
    if doc.creancier.get('tax_id'):
        A(f"  Matricule fiscal : {doc.creancier['tax_id']}")
    A('')
    A('LE DÉBITEUR — المديــن')
    for c in ('name', 'nom'):
        if doc.debiteur.get(c):
            A(f"  {doc.debiteur[c]}")
            break
    for c in ('address', 'adresse'):
        if doc.debiteur.get(c):
            A(f"  {doc.debiteur[c]}")
            break
    A('')
    for p in doc.corps:
        A(p)
        A('')
    for ligne in doc.sommation_ar:
        A(ligne)
    A('')
    A('FONDEMENT JURIDIQUE — السند القانوني')
    A('-' * 68)
    for s in doc.articles:
        A(f"  • {s['label_fr']} ({s['short_fr']})")
        A(f"    {s['citation_ar']}")
    A('')
    A(f"Délai de prescription applicable : échéance au "
      f"{fr_date(doc.prescription['echeance'])} "
      f"({doc.prescription['jours_restants']} jours restants).")
    A('')
    A(f"Fait à {doc.lieu}, le {fr_date(doc.date_acte)}")
    A('')
    A("Le créancier — signature / إمضاء الدائن : ____________________")
    A("Huissier de justice : ______________________  "
      "Circonscription : ______________")
    A("N° de l'acte : ____________  Date de signification : ____________  "
      "Coût : ____________")
    A('')
    A('-' * 68)
    A(doc.mention_projet_longue)
    A(doc.avertissement)
    return '\n'.join(L)


# ---------------------------------------------------------------------------
# Rendu PDF — repris tel quel de h4j, augmenté de la mention de projet.
# reportlab est importé à l'appel et non au chargement : l'API doit pouvoir
# rendre le TEXTE d'une mise en demeure même sur une machine où la police
# arabe n'est pas installée.
# ---------------------------------------------------------------------------

def _polices():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if 'Serif' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('Serif', FONT_PATH))
    if 'SerifB' not in pdfmetrics.getRegisteredFontNames():
        try:
            pdfmetrics.registerFont(TTFont('SerifB', FONT_BOLD))
        except Exception:
            pdfmetrics.registerFont(TTFont('SerifB', FONT_PATH))


def _wrap(c, text, x, y, width, font='Serif', size=10.5, leading=15):
    c.setFont(font, size)
    words, line = text.split(), ''
    for w in words:
        test = f'{line} {w}'.strip()
        if c.stringWidth(test, font, size) <= width:
            line = test
        else:
            c.drawString(x, y, line)
            y -= leading
            line = w
    if line:
        c.drawString(x, y, line)
        y -= leading
    return y


def build_notice(assessment, creditor, debtor, invoice, out_path=None):
    """Écrit le PDF du projet de mise en demeure. Retourne son chemin.

    Signature conservée depuis h4j. Le document passe désormais par
    `construire()`, donc par le garde-fou de prescription : le PDF ne peut
    plus être produit sur une créance éteinte.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    _polices()
    doc = construire(assessment, creditor, debtor, invoice)
    a = assessment

    if out_path is None:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUT_DIR / 'mise_en_demeure.pdf'
    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(out_path), pagesize=A4)
    w, h = A4
    M = 20 * mm
    y = h - M

    # --- bandeau de projet, avant tout le reste ---------------------------
    # Il est en tête, encadré et répété en pied de page. Un lecteur pressé ne
    # doit pas pouvoir prendre ce document pour un acte signifié.
    band_h = 9 * mm
    c.setFillColor(colors.Color(0.97, 0.90, 0.72))
    c.rect(M, y - band_h + 2, w - 2 * M, band_h, stroke=0, fill=1)
    c.setFillColor(colors.black)
    c.setFont('SerifB', 11)
    c.drawCentredString(w / 2, y - band_h + 5, MENTION_PROJET)
    y -= band_h + 6
    c.setFont('Serif', 8)
    y = _wrap(c, MENTION_PROJET_LONGUE, M, y, w - 2 * M, size=8, leading=10)
    y -= 10

    # --- en-tête, dans les deux langues -----------------------------------
    c.setFont('SerifB', 16)
    c.drawString(M, y, doc.titre_fr)
    c.setFont('SerifB', 15)
    c.drawRightString(w - M, y, ar(doc.titre_ar))
    y -= 8
    c.setLineWidth(1.1)
    c.line(M, y, w - M, y)
    y -= 22

    c.setFont('Serif', 9.5)
    c.drawString(M, y, "Projet d'acte à signifier par huissier de justice"
                 if a.needs_bailiff else "Projet de sommation de payer")
    c.drawRightString(w - M, y, ar('بواسطة عدل منفذ') if a.needs_bailiff else '')
    y -= 24

    # --- parties -----------------------------------------------------------
    c.setFont('SerifB', 11)
    c.drawString(M, y, 'LE CRÉANCIER')
    c.setFont('Serif', 11)
    c.drawRightString(w - M, y, ar('الدائــن'))
    y -= 15
    c.setFont('Serif', 10.5)
    for ln in [creditor.get('name', ''), creditor.get('address', ''),
               f"Matricule fiscal : {creditor['tax_id']}" if creditor.get('tax_id') else '']:
        if ln:
            c.drawString(M, y, ln)
            y -= 14
    y -= 8

    c.setFont('SerifB', 11)
    c.drawString(M, y, 'LE DÉBITEUR')
    c.setFont('Serif', 11)
    c.drawRightString(w - M, y, ar('المديــن'))
    y -= 15
    c.setFont('Serif', 10.5)
    for ln in [debtor.get('name', ''), debtor.get('address', '')]:
        if ln:
            c.drawString(M, y, ln)
            y -= 14
    y -= 12

    # --- corps -------------------------------------------------------------
    for para in doc.corps:
        y = _wrap(c, para, M, y, w - 2 * M)
        y -= 6
    y -= 12

    # --- phrase opératoire en arabe ---------------------------------------
    c.setFont('Serif', 11)
    for ligne in doc.sommation_ar:
        c.drawRightString(w - M, y, ar(ligne))
        y -= 16
    y -= 18

    # --- fondement juridique : chaque affirmation citée --------------------
    c.setFont('SerifB', 11)
    c.drawString(M, y, 'FONDEMENT JURIDIQUE')
    c.setFont('Serif', 11)
    c.drawRightString(w - M, y, ar('السند القانوني'))
    y -= 6
    c.setLineWidth(0.6)
    c.line(M, y, w - M, y)
    y -= 16

    # Le libellé français passe à la ligne plutôt que d'être tronqué : un acte
    # juridique ne doit jamais perdre du texte à cause de la mise en page.
    label_w = (w - 2 * M) * 0.52
    for s in doc.articles:
        c.setFont('Serif', 9.5)
        words = f"• {s['label_fr']}".split()
        lines, cur = [], ''
        for word in words:
            test = f'{cur} {word}'.strip()
            if c.stringWidth(test, 'Serif', 9.5) <= label_w:
                cur = test
            else:
                lines.append(cur)
                cur = '   ' + word
        if cur:
            lines.append(cur)
        c.setFont('Serif', 10)
        c.drawRightString(w - M, y, ar(s['citation_ar']))
        c.setFont('Serif', 9.5)
        for ln in lines:
            c.drawString(M + 4, y, ln)
            y -= 12
        y -= 4

    y -= 10
    c.setFont('Serif', 9)
    c.drawString(M, y, f"Délai de prescription applicable : échéance au "
                       f"{fr_date(a.deadline)} ({a.days_left} jours restants).")
    y -= 34

    # --- bloc signature ----------------------------------------------------
    c.setFont('Serif', 10.5)
    c.drawString(M, y, f"Fait à {doc.lieu}, le {fr_date(a.today)}")
    y -= 26
    box_w, box_h = 78 * mm, 30 * mm
    c.setLineWidth(0.5)
    c.rect(M, y - box_h, box_w, box_h)
    c.rect(w - M - box_w, y - box_h, box_w, box_h)
    c.setFont('Serif', 9)
    c.drawString(M + 4, y - 12, 'Le créancier — signature')
    c.drawRightString(w - M - 4, y - 12, ar('إمضاء الدائن'))
    c.drawString(w - M - box_w + 4, y - box_h + 6,
                 "Cachet de l'huissier de justice" if a.needs_bailiff else 'Cachet')
    y -= box_h + 18

    c.setFont('Serif', 8.5)
    c.drawString(M, y, "Huissier de justice : ______________________________  "
                       "Circonscription : ______________________")
    y -= 14
    c.drawString(M, y, "N° de l'acte : ______________  Date de signification : "
                       "______________  Coût : ______________")

    # --- pied de page : la mention, encore --------------------------------
    c.setFont('SerifB', 8)
    c.drawCentredString(w / 2, 17 * mm, MENTION_PROJET)
    c.setFont('Serif', 7.5)
    c.drawCentredString(w / 2, 13 * mm,
                        "Projet rédigé par Mizan — seul un huissier de justice "
                        "peut signifier cet acte (CPCC art. 5 et 60).")
    c.drawCentredString(w / 2, 10 * mm,
                        "Les références légales sont citées depuis le corpus "
                        "indexé et vérifiables dans les codes tunisiens en vigueur.")
    c.showPage()
    c.save()
    return out_path
