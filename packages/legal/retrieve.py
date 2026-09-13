"""Arabic BM25 retrieval over the Tunisian legal corpus, with mandatory citations."""
import json, pickle, re, unicodedata
from pathlib import Path
from rank_bm25 import BM25Okapi

# La racine du projet, pas le dossier du module : `retrieve.py` vit désormais
# dans packages/legal/ alors que le corpus reste à la racine du dépôt.
ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / 'corpus'
INDEX = ROOT / 'index.pkl'

# Arabic diacritics + tatweel
DIAC = re.compile(r'[\u064B-\u0652\u0640]')
NONWORD = re.compile(r'[^\u0600-\u06FF0-9a-zA-Z]+')


def normalize(t):
    t = unicodedata.normalize('NFKC', t)
    t = DIAC.sub('', t)
    t = (t.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
           .replace('ة', 'ه').replace('ى', 'ي').replace('ؤ', 'و')
           .replace('ئ', 'ي'))
    return t


def tokenize(t):
    return [w for w in NONWORD.split(normalize(t)) if len(w) > 1]


def load_docs():
    docs = []
    for f in sorted(CORPUS.glob('*.jsonl')):
        for ln in f.open(encoding='utf-8'):
            docs.append(json.loads(ln))
    return docs


def build():
    docs = load_docs()
    toks = [tokenize(d['text_ar']) for d in docs]
    bm25 = BM25Okapi(toks)
    with INDEX.open('wb') as fh:
        pickle.dump({'docs': docs, 'bm25': bm25}, fh)
    codes = {}
    for d in docs:
        codes[d['code_fr']] = codes.get(d['code_fr'], 0) + 1
    print(f'indexed {len(docs)} articles')
    for k, v in sorted(codes.items()):
        print(f'  {v:5d}  {k}')
    return docs


_CACHE = {}


def search(query, k=5, code_id=None):
    if not _CACHE:
        with INDEX.open('rb') as fh:
            _CACHE.update(pickle.load(fh))
    docs, bm25 = _CACHE['docs'], _CACHE['bm25']
    scores = bm25.get_scores(tokenize(query))
    order = sorted(range(len(docs)), key=lambda i: -scores[i])
    out = []
    for i in order:
        if code_id and docs[i]['code_id'] != code_id:
            continue
        if scores[i] <= 0:
            break
        d = dict(docs[i]); d['score'] = round(float(scores[i]), 2)
        out.append(d)
        if len(out) >= k:
            break
    return out


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'build':
        build()
    else:
        q = ' '.join(sys.argv[1:]) or 'تقادم ثمن البضائع'
        for r in search(q):
            print(f"\n[{r['score']}] {r['citation_ar']}")
            print(r['text_ar'][:240].replace('\n', ' '))
