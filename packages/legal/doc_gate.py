"""Porte d'entrée : ce document est-il vraiment une facture ?

Pourquoi ce fichier existe
--------------------------
Nidhal a déposé les *joining instructions* du hackathon dans Mizan. L'app a
répondu par une mise en demeure exécutoire réclamant 2 083,000 DT au titre
d'une « facture n° 34848 » — trois valeurs ramassées au hasard dans un PDF
qui n'est pas une facture. Rien de tout cela n'existait.

C'est exactement ce que Mizan promet de ne jamais faire. Le gate d'abstention
(gate.py) protège la *recherche juridique* ; il n'y avait aucun contrôle sur
la porte d'entrée. Un document illisible doit produire un REFUS, pas un acte.

Le principe est le même qu'en recherche : on n'accepte pas sur un score nu,
on exige des PREUVES nommées, et on dit lesquelles manquent.
"""
import re

# --- preuves positives -------------------------------------------------------
KW_FACTURE = re.compile(r'\b(facture|invoice|فاتورة|فوترة)\b', re.I)
TOTAL_HINT = re.compile(
    r'(total|montant|net\s+[àa]\s+payer|ttc|hors\s+taxe|\bht\b|tva|'
    r'المبلغ|الجملة|المجموع|الأداء)', re.I)
CURRENCY = re.compile(r'\b(dt|tnd|dinars?|dinar|millimes?|د\.?ت|دينار)\b', re.I)
SELLER = re.compile(
    r'(matricule\s+fiscal|registre\s+de\s+commerce|\brc\b|\bmf\b|'
    r'المعرف\s+الجبائي|السجل\s+التجاري)', re.I)
LINE_ITEM = re.compile(
    r'(d[ée]signation|qt[ée]|quantit[ée]|p\.?u\.?|prix\s+unitaire|'
    r'الكمية|السعر|البيان)', re.I)

# --- preuves NÉGATIVES : le document dit lui-même ce qu'il est ---------------
# Une mise en demeure CITE une facture sans en être une. Sans ces marqueurs,
# Mizan avalerait son propre PDF de sortie et bouclerait sur lui-même.
NOT_INVOICE = [
    (re.compile(r'mise\s+en\s+demeure|إنذار|acte\s+[àa]\s+signifier', re.I),
     "ce document est une mise en demeure, pas une facture"),
    (re.compile(r'joining\s+instructions|hackathon|agenda|code\s+of\s+conduct',
                re.I),
     "ce document est un programme d'événement"),
    (re.compile(r'\b(contrat|convention|bail|statuts)\b', re.I),
     "ce document est un contrat, pas une facture"),
    (re.compile(r'(jugement|ordonnance|requ[êe]te|حكم|قرار)', re.I),
     "ce document est une pièce de procédure"),
    (re.compile(r'(curriculum\s+vitae|\bcv\b|lettre\s+de\s+motivation)', re.I),
     "ce document est un CV"),
    # Un devis ressemble beaucoup à une facture (lignes, total, MF) mais ne
    # constate AUCUNE créance : rien n'a été livré, la prescription ne court
    # pas. Testé sur un intrus non prévu — il passait à 4/5.
    (re.compile(r'\b(devis|proforma|pro\s*forma|bon\s+de\s+commande|عرض\s+سعر)\b',
                re.I),
     "ce document est un devis ou un bon de commande : il ne constate pas "
     "encore de créance, rien n'a été livré ni facturé"),
]

MIN_SIGNALS = 3          # sur 5 preuves positives
NEEDS_ANCHORED_AMOUNT = True


def _anchored_amount(text, montant=None):
    """Un montant posé sur une ligne qui parle de total — pas un nombre isolé.

    C'est la différence entre « Total TTC : 9 520,000 DT » et le « 34848 »
    qui traînait dans un PDF d'agenda.

    Quand on sait déjà quel montant a été retenu (`montant`), on renvoie la
    ligne qui le PORTE, et non la première ligne de total venue. Sur la
    facture d'Ahmed, les deux diffèrent :

        TOTAL HT      8,000.000     <- première ligne de total
        TVA 19%       1,520.000
        NET A PAYER   9,520.000     <- le montant réclamé

    Les deux chiffres sont exacts, mais afficher « TOTAL HT 8,000.000 » comme
    justification d'une créance de 9 520 DT donne à lire une incohérence là
    où il n'y en a pas. Devant un juge comme devant un jury, une pièce qui
    semble se contredire ne se discute plus : elle se rejette.
    """
    lignes = [l for l in text.splitlines()
              if TOTAL_HINT.search(l) and re.search(r'\d', l)]
    if not lignes:
        return False, None

    if montant is not None:
        # Une facture tunisienne écrit indifféremment « 9,520.000 » (virgule
        # de milliers) ou « 9 520,000 » (espace de milliers, virgule
        # décimale). Les deux désignent la même somme : il faut donc essayer
        # les deux lectures avant de conclure qu'un nombre ne correspond pas.
        for ligne in lignes:
            for brut in re.findall(r'\d[\d\s.,]*\d|\d', ligne):
                compact = brut.replace(' ', '')
                lectures = {
                    compact.replace(',', ''),          # 9,520.000 -> 9520.000
                    compact.replace(',', '.'),         # 9520,000  -> 9520.000
                }
                if compact.count(',') == 1 and '.' not in compact:
                    # « 9 520,000 » : la virgule est décimale.
                    lectures.add(compact.replace(',', '.'))
                for lecture in lectures:
                    try:
                        if abs(float(lecture) - float(montant)) < 0.01:
                            return True, ligne.strip()[:90]
                    except ValueError:
                        continue

    return True, lignes[0].strip()[:90]


def inspect(text, montant=None):
    """Renvoie le verdict d'entrée. Aucun effet de bord, testable seul.

    `montant` est facultatif : quand l'appelant a déjà extrait le montant
    retenu, la ligne d'ancrage renvoyée est celle qui le porte.
    """
    t = text or ''

    for rx, why in NOT_INVOICE:
        m = rx.search(t)
        if m:
            return {
                'is_invoice': False,
                'signals': [],
                'missing': [],
                'reason': why,
                'detail': f"marqueur trouvé : « {m.group(0)[:40]} »",
                'anchored_line': None,
            }

    checks = [
        ('mot « facture »', bool(KW_FACTURE.search(t))),
        ('ligne de total', bool(TOTAL_HINT.search(t))),
        ('devise (DT/TND)', bool(CURRENCY.search(t))),
        ('identifiant vendeur', bool(SELLER.search(t))),
        ('lignes d\'articles', bool(LINE_ITEM.search(t))),
    ]
    present = [n for n, ok in checks if ok]
    missing = [n for n, ok in checks if not ok]

    anchored, line = _anchored_amount(t, montant)

    ok = len(present) >= MIN_SIGNALS and (anchored or not NEEDS_ANCHORED_AMOUNT)

    if ok:
        reason = None
    elif not anchored:
        reason = ("aucun montant n'est rattaché à une ligne de total : "
                  "les nombres présents sont isolés, les prendre pour une "
                  "créance serait une invention")
    else:
        reason = (f"seulement {len(present)} indice(s) de facture sur 5 ; "
                  f"il manque : {', '.join(missing)}")

    return {
        'is_invoice': ok,
        'signals': present,
        'missing': missing,
        'reason': reason,
        'detail': None,
        'anchored_line': line,
    }


# ---------------------------------------------------------------------------
# Calibration : `python app/doc_gate.py`
# Le vrai test n'est pas « la facture passe » — c'est « l'intrus est refusé ».
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.invoice import extract_text

    ROOT = Path(__file__).resolve().parent.parent
    CACHE = Path.home() / '.hermes' / 'cache' / 'documents'

    cases = [
        (ROOT / 'samples' / 'facture_ahmed.pdf', True, 'vraie facture'),
        (CACHE / 'doc_c0d0f1f36971_Joining instructions H4J September 26.pdf',
         False, 'joining instructions du hackathon'),
        (CACHE / 'doc_ebfc2af3a730_mise_en_demeure_95aae0fe.pdf',
         False, 'mise en demeure produite par Mizan'),
    ]

    ok = 0
    for path, expected, label in cases:
        if not path.exists():
            print(f'  SKIP  {label} (absent)')
            continue
        text, _ = extract_text(str(path))
        v = inspect(text)
        good = v['is_invoice'] == expected
        ok += good
        print(f"  {'OK  ' if good else 'FAIL'}  {label}: "
              f"is_invoice={v['is_invoice']} (attendu {expected})")
        if not v['is_invoice']:
            print(f"         motif : {v['reason'] or v['detail']}")
    print(f"\n{ok}/{len([c for c in cases if c[0].exists()])} CALIBRATION")
