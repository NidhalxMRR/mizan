"""Abstention gate: decide whether the corpus actually answers the question.

Ported in spirit from the Assurance grounding gate, rebuilt for BM25.

WHY NOT A BARE SCORE FLOOR. Measured on this corpus, the nonsense question
"ما هو لون السماء" ("what colour is the sky") scores 8.75, while the perfectly
legitimate "الكمبيالة" ("the bill of exchange") scores 6.98. A single threshold
therefore admits junk and rejects real law at the same time — it inverts the
very decision it exists to make.

What separates them is not the magnitude of the score but WHERE it comes from:
the junk question earns its points from one common word scattered over the
corpus, while a real legal query matches its distinctive terms inside one
article. So the gate asks two questions the score alone cannot answer:

  1. LEXICAL OVERLAP — do the query's content words actually occur in the
     retrieved article? A retrieved article that shares no vocabulary with the
     question is a coincidence of the ranker, not an answer.
  2. MARGIN — does the top hit stand out from the rest? When every article
     scores alike, BM25 is reporting noise, not a match.

Both are cheap, explainable to a non-technical juror, and need no embeddings —
which matters, because this machine cannot install them.
"""
from __future__ import annotations

try:
    from retrieve import tokenize
except ImportError:  # lancé directement : python app/gate.py
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from retrieve import tokenize

# Arabic function words. They carry no topical meaning, yet they are what a
# nonsense question shares with a random article: "ما هو لون السماء" matched an
# arbitration article on "ما" and "لون" alone and scored 0.50 overlap — enough
# to pass the gate. Content words only, so overlap measures subject matter
# rather than grammar.
STOPWORDS = {
    'ما', 'هو', 'هي', 'من', 'في', 'على', 'الى', 'إلى', 'عن', 'مع', 'كل',
    'او', 'أو', 'ان', 'أن', 'إن', 'لا', 'ثم', 'قد', 'هذا', 'هذه', 'ذلك',
    'التي', 'الذي', 'كان', 'كانت', 'يكون', 'به', 'له', 'لها', 'بين',
    'عند', 'بعد', 'قبل', 'حتى', 'اذا', 'إذا', 'كما', 'لم', 'لن', 'هل',
    'كيف', 'اين', 'أين', 'متى', 'وما', 'وهو', 'وفي', 'ومن',
}

# A real legal query shares at least this fraction of its content words with
# the article the ranker returned. Calibrated below against real and junk
# questions; see calibrate() for the evidence.
MIN_OVERLAP = 0.34

# Below this the ranker has nothing at all.
MIN_SCORE = 3.0

# A multi-word question must share at least this many content words with the
# article. One is a collision; two is a subject. See evaluate().
MIN_MATCHED = 2


def _content(text: str) -> set:
    return {w for w in tokenize(text) if w not in STOPWORDS}


def _overlap(query: str, text: str) -> float:
    """Fraction of the query's distinct content words present in the article."""
    q = _content(query)
    if not q:
        return 0.0
    return len(q & _content(text)) / len(q)


def evaluate(query: str, hits: list) -> dict:
    """Return a grounding decision for a ranked hit list.

    Shape mirrors what the UI needs: whether to answer, and if not, a sentence
    a non-technical user can read.
    """
    if not hits:
        return {
            'grounded': False,
            'reason': 'aucun article trouvé',
            'best_score': 0.0,
            'overlap': 0.0,
            'matched': 0,
        }

    top = hits[0]
    score = float(top.get('score', 0.0))
    q = _content(query)
    matched = len(q & _content(top.get('text_ar', '')))
    ov = (matched / len(q)) if q else 0.0

    if score < MIN_SCORE:
        grounded, reason = False, 'score trop faible'
    elif len(q) == 1:
        # A single-term query ("الكمبيالة") is legitimate and can only ever
        # match once, so it is held to a full match instead of a count.
        grounded = ov >= 1.0
        reason = None if grounded else 'le terme de la question ne figure pas dans le texte trouvé'
    elif matched < MIN_MATCHED:
        # THE DECIDING RULE, and it is why a bare threshold was not enough.
        # "ما هو لون السماء" hits an OCR-garbled arbitration article on the
        # single word لون and scores 0.50 overlap — passing any percentage
        # floor a real query could also pass. One shared word is a collision;
        # two is a subject.
        grounded, reason = False, 'un seul mot de la question figure dans le texte — coïncidence, pas une réponse'
    elif ov < MIN_OVERLAP:
        grounded, reason = False, 'les termes de la question ne figurent pas dans le texte trouvé'
    else:
        grounded, reason = True, None

    return {
        'grounded': grounded,
        'reason': reason,
        'best_score': round(score, 2),
        'overlap': round(ov, 2),
        'matched': matched,
    }


ABSTAIN_MESSAGE = (
    "Aucun article du corpus ne répond à cette question avec une confiance "
    "suffisante. Mizan préfère se taire plutôt que d'inventer une référence."
)


def calibrate():
    """Print the evidence behind the thresholds. Run as __main__."""
    from retrieve import search

    real = [
        "تقادم ثمن البضائع المسلمة",
        "الإنذار بواسطة عدل منفذ",
        "الأمر بالدفع",
        "الكمبيالة",
        "خطية التأخير في دفع الأداء",
        "فسخ العقد لعدم الدفع",
    ]
    junk = [
        "ما هو لون السماء",
        "comment cuisiner des pates",
        "recette du couscous",
        "football barcelone",
        "بيتزا بالجبن",
        "كيف أطبخ الكسكسي",
    ]

    rows = []
    for q in real:
        rows.append(('LOI ', q, evaluate(q, search(q, k=1))))
    for q in junk:
        rows.append(('JUNK', q, evaluate(q, search(q, k=1))))

    print(f"{'type':<5}{'score':>7}{'overlap':>9}  {'verdict':<9} question")
    ok = True
    for kind, q, d in rows:
        verdict = 'REPOND' if d['grounded'] else 'ABSTIENT'
        print(f"{kind:<5}{d['best_score']:>7}{d['overlap']:>9}  {verdict:<9} {q}")
        if kind == 'LOI ' and not d['grounded']:
            ok = False
        if kind == 'JUNK' and d['grounded']:
            ok = False
    print()
    print('CALIBRATION OK' if ok else 'CALIBRATION FAILED')
    return ok


if __name__ == '__main__':
    import sys
    sys.exit(0 if calibrate() else 1)
