"""Invoice ingestion: pull amount, dates and counterparty out of a PDF or photo.

Works on French and Arabic invoices. Falls back to OCR when the PDF carries no
usable text layer (the same situation as the Imprimerie Officielle codes).
"""
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path
from datetime import date

AR_DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')

MONTHS_FR = {
    'janvier': 1, 'fevrier': 2, 'février': 2, 'mars': 3, 'avril': 4,
    'mai': 5, 'juin': 6, 'juillet': 7, 'aout': 8, 'août': 8,
    'septembre': 9, 'octobre': 10, 'novembre': 11, 'decembre': 12,
    'décembre': 12,
}

AMOUNT_HINT = re.compile(
    r'(?:total|montant|net\s+a\s+payer|net\s+à\s+payer|somme|ttc|'
    r'المبلغ|الجملة|المجموع)', re.I)
NUMBER = re.compile(r'(\d[\d\s.,]{1,15}\d|\d)')
DATE_ISO = re.compile(r'\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b')
DATE_DMY = re.compile(r'\b(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})\b')
DATE_TXT = re.compile(
    r'\b(\d{1,2})\s+([a-zéû]+)\s+(20\d{2})\b', re.I)
INVOICE_NO = re.compile(
    r'(?:facture|invoice|فاتورة)\s*(?:n[°ordi]*\.?|num[eé]ro|:)?\s*'
    r'([A-Z0-9][A-Z0-9\-/]{1,20})', re.I)
CLIENT = re.compile(
    r'(?:client|doit|adress[eé]\s+[àa]|acheteur|الحريف|السيد)\s*:?\s*'
    r'([^\n]{2,60})', re.I)


def _norm(t):
    return unicodedata.normalize('NFKC', t).translate(AR_DIGITS)


def extract_text(path):
    """Return (text, method). Tries the text layer, then OCR."""
    path = str(path)
    if path.lower().endswith('.pdf'):
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                txt = '\n'.join((p.extract_text() or '') for p in pdf.pages)
            letters = sum(c.isalpha() for c in txt)
            if letters > 40:
                return _norm(txt), 'text-layer'
        except Exception:
            pass
        return _ocr_pdf(path), 'ocr'
    return _ocr_image(path), 'ocr'


def _ocr_pdf(path):
    with tempfile.TemporaryDirectory(dir=_scratch()) as td:
        stem = Path(td) / 'p'
        subprocess.run(['pdftoppm', '-r', '200', '-png', path, str(stem)],
                       capture_output=True, timeout=180)
        out = []
        for png in sorted(Path(td).glob('p*.png')):
            out.append(_tess(png))
    return _norm('\n'.join(out))


def _ocr_image(path):
    return _norm(_tess(path))


def _tess(img):
    r = subprocess.run(
        ['tesseract', str(img), 'stdout', '-l', 'ara+fra', '--psm', '6'],
        capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        r = subprocess.run(
            ['tesseract', str(img), 'stdout', '-l', 'ara', '--psm', '6'],
            capture_output=True, text=True, timeout=180)
    return r.stdout


def _scratch():
    s = Path(__file__).resolve().parent.parent / '.ocrtmp'
    s.mkdir(exist_ok=True)
    return str(s)


def _to_float(raw):
    """Lit un montant écrit sur une facture tunisienne.

    Le dinar vaut mille millimes, et l'usage local écrit cette partie
    fractionnaire avec trois décimales : 9,520.000 se lit neuf mille cinq
    cent vingt dinars, et 107.100 se lit cent sept dinars cent millimes.

    C'est l'inverse de la convention où le point sépare les milliers. Prendre
    l'une pour l'autre multiplie la créance par mille, franchit les seuils du
    code — cent cinquante dinars pour la sommation par huissier, vingt-cinq
    mille pour la représentation par avocat — et fait conseiller une
    procédure sans rapport avec ce que réclame l'entreprise.

    La règle retenue : quand les deux signes sont présents, le dernier des
    deux marque les décimales. Quand un seul est présent, il marque les
    décimales s'il n'est suivi que d'un groupe de chiffres et qu'aucun autre
    groupe de trois ne le précède en position de millier ; la virgule seule
    suivie d'exactement trois chiffres reste ambiguë et suit alors l'usage
    tunisien du séparateur de milliers.
    """
    s = raw.strip().replace(' ', '').replace('\u00a0', '')
    if not s:
        return None

    virgule, point = s.rfind(','), s.rfind('.')

    if virgule >= 0 and point >= 0:
        # Deux signes : le dernier porte les décimales, l'autre les milliers.
        if virgule > point:
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    elif virgule >= 0:
        fin = s.split(',')[-1]
        # Une virgule suivie de trois chiffres est, en Tunisie, un séparateur
        # de milliers : 47,362 vaut quarante-sept mille trois cent
        # soixante-deux. Au-delà ou en deçà, elle sépare les décimales.
        s = s.replace(',', '') if len(fin) == 3 else s.replace(',', '.')
    elif point >= 0:
        # Un point unique sépare toujours les décimales : trois chiffres
        # derrière, ce sont des millimes, et non un groupe de milliers.
        if s.count('.') > 1:
            return None

    try:
        return float(s)
    except ValueError:
        return None


def find_amount(text):
    """Largest number sitting on a line that mentions a total."""
    best = None
    for line in text.splitlines():
        if not AMOUNT_HINT.search(line):
            continue
        for m in NUMBER.finditer(line):
            v = _to_float(m.group(1))
            if v and 1 <= v < 10_000_000:
                best = v if best is None else max(best, v)
    if best is None:                       # fall back: biggest plausible number
        for m in NUMBER.finditer(text):
            v = _to_float(m.group(1))
            if v and 10 <= v < 10_000_000:
                best = v if best is None else max(best, v)
    return best


def find_dates(text):
    found = []
    for m in DATE_ISO.finditer(text):
        y, mo, d = map(int, m.groups())
        found.append(_safe(y, mo, d))
    for m in DATE_DMY.finditer(text):
        d, mo, y = map(int, m.groups())
        found.append(_safe(y, mo, d))
    for m in DATE_TXT.finditer(text):
        d, word, y = m.group(1), m.group(2).lower(), m.group(3)
        mo = MONTHS_FR.get(word)
        if mo:
            found.append(_safe(int(y), mo, int(d)))
    return sorted({f for f in found if f})


def _safe(y, mo, d):
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def parse_invoice(path):
    text, method = extract_text(path)
    dates = find_dates(text)
    no = INVOICE_NO.search(text)
    cli = CLIENT.search(text)
    return {
        'amount_tnd': find_amount(text),
        'invoice_date': dates[0].isoformat() if dates else None,
        'all_dates': [d.isoformat() for d in dates],
        'invoice_no': no.group(1).strip() if no else None,
        'client': cli.group(1).strip() if cli else None,
        'method': method,
        'n_chars': len(text),
        'text_head': text[:600],
        '_full_text': text,
    }
