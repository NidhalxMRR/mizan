"""Les articles du corpus sur lesquels l'analyse de contrat s'appuie.

POURQUOI CE FICHIER EXISTE SÉPARÉMENT
-------------------------------------
Un moteur qui écrit lui-même ses citations arabes finit toujours par en
inventer une. Ici, aucune citation arabe n'est écrite à la main : on ne
déclare qu'un COUPLE (code, numéro d'article), et le texte comme la citation
sont RELUS dans le corpus au chargement.

Conséquence directe et voulue : si un article disparaît du corpus, la clause
qu'il fondait disparaît de l'analyse. Le moteur perd une détection plutôt que
de produire une référence que le juriste ne pourra pas ouvrir à l'audience.

Chaque couple ci-dessous a été vérifié dans le corpus avant d'être écrit, et
`packages/contrats/test_analyse.py` le revérifie à chaque exécution via BM25
avec la garde d'abstention du projet (MIN_SCORE=3.0, MIN_MATCHED=2).
"""
from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path

# La racine du dépôt : fondements.py vit dans packages/contrats/.
RACINE = Path(__file__).resolve().parents[2]
CORPUS = RACINE / 'corpus'

# Reprise stricte des seuils de packages/legal/gate.py. Ils ne sont pas
# redéfinis ici par confort : ils sont RÉIMPORTÉS quand c'est possible, pour
# qu'un durcissement du gate d'abstention du projet durcisse aussi celui-ci.
MIN_SCORE = 3.0
MIN_MATCHED = 2


@dataclass(frozen=True)
class Fondement:
    """Un article du corpus, relu tel quel — jamais reconstruit."""

    code_id: str
    article: int          # ATTENTION : le corpus stocke un INT, pas une str.
    code_fr: str
    code_ar: str
    citation_ar: str      # lue dans le corpus
    texte_ar: str         # texte intégral de l'article, tel qu'indexé
    extrait_ar: str       # les premiers caractères, pour affichage

    def to_dict(self) -> dict:
        return {
            'code_id': self.code_id,
            'article': self.article,
            'code_fr': self.code_fr,
            'code_ar': self.code_ar,
            'citation_ar': self.citation_ar,
            'extrait_ar': self.extrait_ar,
        }


_INDEX: dict[tuple[str, int], Fondement] = {}


def _nettoyer(t: str) -> str:
    """Normalise l'espace d'un texte OCRisé sans en altérer les mots.

    Le corpus vient d'un OCR de l'Imprimerie Officielle : il porte des retours
    à la ligne au milieu des phrases. On les aplatit pour l'affichage, mais on
    ne touche à AUCUN caractère arabe — une citation retouchée n'est plus une
    citation.
    """
    return ' '.join(unicodedata.normalize('NFKC', t).split())


def charger() -> dict[tuple[str, int], Fondement]:
    """Charge le corpus une fois et l'indexe par (code, article).

    Le corpus compte ~4000 articles répartis sur six codes ; l'index tient en
    mémoire et évite de relire les .jsonl à chaque contrat analysé.
    """
    if _INDEX:
        return _INDEX
    for fichier in sorted(CORPUS.glob('*.jsonl')):
        with fichier.open(encoding='utf-8') as fh:
            for ligne in fh:
                ligne = ligne.strip()
                if not ligne:
                    continue
                d = json.loads(ligne)
                cle = (d['code_id'], int(d['article']))
                # Certains articles apparaissent deux fois (pages OCR
                # dupliquées). On garde la première occurrence, qui est la
                # plus complète dans tous les cas observés.
                if cle in _INDEX:
                    continue
                texte = _nettoyer(d.get('text_ar', ''))
                _INDEX[cle] = Fondement(
                    code_id=d['code_id'],
                    article=int(d['article']),
                    code_fr=d.get('code_fr', ''),
                    code_ar=d.get('code_ar', ''),
                    citation_ar=d.get('citation_ar', ''),
                    texte_ar=texte,
                    extrait_ar=texte[:320],
                )
    return _INDEX


def fondement(code_id: str, article: int) -> Fondement | None:
    """Renvoie l'article demandé, ou None s'il n'est pas dans le corpus.

    None n'est pas une erreur : c'est la réponse honnête quand le corpus ne
    porte pas l'article, et l'appelant doit alors renoncer à la clause.
    """
    return charger().get((code_id, int(article)))


# ---------------------------------------------------------------------------
# Ce que le corpus NE fonde PAS.
#
# Cette liste vaut autant que les détections : elle est relue à voix haute
# dans le rapport final, pour qu'un juriste sache exactement où l'outil ne
# l'aide pas. Chaque entrée a été cherchée dans le corpus, pas supposée.
# ---------------------------------------------------------------------------
LACUNES = {
    'clause_penale': (
        "Aucun article du corpus ne traite nommément du « شرط جزائي » "
        "(clause pénale) : le pouvoir du juge de réduire une indemnité "
        "forfaitaire manifestement excessive n'est donc PAS fondé ici. "
        "L'analyse se limite à ce que le corpus dit réellement : "
        "l'évaluation du préjudice relève de l'appréciation du tribunal "
        "(COC art. 278), ce qui suffit à signaler la clause sans prétendre "
        "en dire le sort."
    ),
    'clause_abusive': (
        "Le corpus ne contient AUCUN texte de droit de la consommation : ni "
        "loi 92-117 relative à la protection du consommateur, ni article "
        "mentionnant « المستهلك » ou le contrat d'adhésion. La qualification "
        "de clause abusive entre commerçant et non-commerçant ne peut donc "
        "pas être fondée sur ce corpus, et le moteur s'abstient de la rendre."
    ),
    'reserve_propriete': (
        "Aucun article du corpus ne traite du « شرط الاحتفاظ بالملكية » "
        "(réserve de propriété) en tant que tel, ni de son opposabilité en "
        "procédure collective. Seule la règle qu'une telle clause écarte est "
        "fondée (COC art. 583 : la propriété passe à l'acheteur dès l'accord "
        "des parties). La clause est donc signalée comme dérogatoire, sans "
        "affirmation sur sa validité."
    ),
    'limitation_responsabilite': (
        "Le corpus ne porte pas d'article général frappant de nullité la "
        "clause qui exonère le débiteur de son dol ou de sa faute lourde. Les "
        "fondements disponibles sont SPÉCIAUX : transport de marchandises "
        "(Code de commerce art. 643) et action sociale contre le dirigeant "
        "(Code des sociétés art. 118). Hors de ces deux terrains, le moteur "
        "signale la clause mais ne se prononce pas sur sa nullité."
    ),
}
