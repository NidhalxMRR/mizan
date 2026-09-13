"""Ancrage d'un risque sur un article RÉEL du corpus.

Pourquoi ce fichier existe
--------------------------
Un moteur de risques qui cite « COC art. 403 » sans l'avoir ouvert est un
générateur de fausses références : la phrase est plausible, la numérotation
est crédible, et un juriste qui la reprend en conclusions découvre à
l'audience que l'article dit autre chose. C'est la faute la plus grave que
cet outil puisse commettre, parce qu'elle est indétectable à l'œil nu.

La règle tenue ici est donc : AUCUN risque n'est produit sans que l'article
qui le fonde ait été retrouvé dans le corpus indexé ET que le passage précis
invoqué ait été retrouvé dans son texte. Deux vérifications, pas une :

  1. L'ARTICLE EXISTE — un couple (code, numéro) présent dans le corpus.
  2. LE PASSAGE EXISTE — un marqueur arabe littéral, choisi parce qu'il porte
     la règle invoquée, doit figurer dans le texte de l'article.

La seconde condition n'est pas une précaution de confort. Le corpus contient
352 couples (code, numéro) portés par plusieurs entrées : l'article 18 du
fichier `fiscal` à lui seul en compte huit, qui traitent de sujets sans aucun
rapport entre eux (identifiant fiscal, dossiers d'appel, conventions entre
services). Citer « article 18 » sans dire LEQUEL des huit, c'est citer au
hasard. Le marqueur désigne l'entrée, et l'extrait renvoyé est découpé autour
de lui : le juriste lit le passage exact sur lequel le risque repose.

Une réserve de qualification
----------------------------
Certaines entrées du corpus portent une étiquette de code qui contredit leur
propre texte. L'entrée qui fonde l'obligation de mentionner l'identifiant
fiscal est rangée sous « مجلة الحقوق والإجراءات الجبائية » alors que son
texte s'annonce lui-même comme « الفصل 18 من مجلة الأداء على القيمة المضافة ».
Le contenu est bon, le rattachement est douteux. Plutôt que de trancher en
silence, `ancrer` compare l'étiquette au texte et joint une RÉSERVE quand les
deux divergent : la citation reste utilisable, mais elle est à vérifier avant
d'être portée dans un acte.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
CORPUS = RACINE / 'corpus'

# Le texte d'un article commence souvent par sa propre auto-désignation :
# « الفصل 18 من مجلة الأداء على القيمة المضافة ». Quand ce code annoncé
# diffère de l'étiquette du corpus, la citation est à vérifier.
AUTO_DESIGNATION = re.compile(
    r'الفصل\s*\d+\s*(?:مكرر\s*)?من\s+((?:مجلة|القانون|المرسوم|الأمر)[^\n]{0,60})'
)

_DIACRITIQUES = re.compile(r'[\u064B-\u0652\u0640]')


@dataclass(frozen=True)
class Article:
    """Un article du corpus, retrouvé et prouvé, prêt à être cité.

    `extrait_ar` est découpé autour du marqueur : c'est le passage qui porte
    la règle, pas les premiers caractères de l'article. Un juriste doit
    pouvoir relire la phrase exacte qu'on lui oppose.
    """

    code_id: str
    code_fr: str
    article: int
    citation_ar: str
    extrait_ar: str
    reserve_fr: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _normaliser(texte: str) -> str:
    """Retire diacritiques et variantes de graphie pour comparer deux libellés.

    L'arabe du corpus vient d'OCR et de PDF d'origines différentes : le même
    mot s'y écrit avec ou sans chadda, avec أ ou ا. Comparer les chaînes
    brutes ferait conclure à une divergence là où il n'y en a pas.
    """
    t = unicodedata.normalize('NFKC', texte)
    t = _DIACRITIQUES.sub('', t)
    for source, cible in (('أ', 'ا'), ('إ', 'ا'), ('آ', 'ا'), ('ة', 'ه'),
                          ('ى', 'ي'), ('ؤ', 'و'), ('ئ', 'ي'), ('ّ', '')):
        t = t.replace(source, cible)
    return re.sub(r'\s+', ' ', t).strip()


_DOCUMENTS: list[dict] | None = None


def charger() -> list[dict]:
    """Charge les 4087 articles une fois pour toutes.

    Lecture directe des .jsonl et non de l'index BM25 : on ne cherche pas ici
    le meilleur article pour une question, on vérifie qu'un article nommé
    existe. Le classement lexical n'a rien à dire sur une question de
    présence, et l'index pèse 6,8 Mo qu'il est inutile de déplier pour cela.
    """
    global _DOCUMENTS
    if _DOCUMENTS is None:
        documents: list[dict] = []
        for fichier in sorted(CORPUS.glob('*.jsonl')):
            with fichier.open(encoding='utf-8') as flux:
                for ligne in flux:
                    ligne = ligne.strip()
                    if ligne:
                        documents.append(json.loads(ligne))
        _DOCUMENTS = documents
    return _DOCUMENTS


def _reserve(entree: dict) -> str | None:
    """Signale une entrée dont le texte se réclame d'un autre code.

    On ne corrige pas l'étiquette : on n'a pas autorité pour requalifier un
    article. On avertit, ce qui laisse la décision au juriste.
    """
    texte = entree.get('text_ar', '') or ''
    trouve = AUTO_DESIGNATION.search(texte[:400])
    if not trouve:
        return None
    annonce = _normaliser(trouve.group(1))
    etiquette = _normaliser(entree.get('code_ar', '') or '')
    if not annonce or not etiquette:
        return None
    if annonce.startswith(etiquette) or etiquette.startswith(annonce):
        return None
    return (
        "Le corpus range ce texte sous « {etiquette} », mais le texte "
        "lui-même s'annonce comme « {annonce} ». Le contenu cité est exact ; "
        "le rattachement au code est à vérifier avant de porter cette "
        "référence dans un acte."
    ).format(etiquette=entree.get('code_ar', ''), annonce=trouve.group(1).strip())


def _extrait(texte: str, marqueur: str, largeur: int = 200) -> str:
    """Découpe le passage autour du marqueur, sur des frontières de mots."""
    position = texte.find(marqueur)
    debut = max(0, position - largeur // 2)
    fin = min(len(texte), position + len(marqueur) + largeur // 2)
    morceau = re.sub(r'\s+', ' ', texte[debut:fin]).strip()
    if debut > 0:
        morceau = '… ' + morceau
    if fin < len(texte):
        morceau = morceau + ' …'
    return morceau


def ancrer(code_id: str, article: int, marqueur_ar: str) -> Article | None:
    """Retrouve l'article et prouve qu'il porte bien le passage invoqué.

    Renvoie None si le couple (code, numéro) est absent du corpus, ou si
    aucune de ses entrées ne contient le marqueur. `None` est une réponse
    légitime : l'appelant doit alors s'abstenir de produire le risque.
    """
    if not marqueur_ar:
        return None
    cible = _normaliser(marqueur_ar)
    for entree in charger():
        if entree.get('code_id') != code_id or entree.get('article') != article:
            continue
        texte = entree.get('text_ar', '') or ''
        if marqueur_ar in texte:
            brut = texte
        elif cible and cible in _normaliser(texte):
            brut = texte
        else:
            continue
        position = brut.find(marqueur_ar)
        extrait = (_extrait(brut, marqueur_ar) if position >= 0
                   else re.sub(r'\s+', ' ', brut[:220]).strip())
        return Article(
            code_id=entree['code_id'],
            code_fr=entree.get('code_fr', ''),
            article=entree['article'],
            citation_ar=entree.get('citation_ar', ''),
            extrait_ar=extrait,
            reserve_fr=_reserve(entree),
        )
    return None
