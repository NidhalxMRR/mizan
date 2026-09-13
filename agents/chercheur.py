"""Agent 2 — CHERCHEUR DE DROIT.

Il ne rédige rien. Il ne conclut rien. Il rapporte du droit qui EXISTE.

La règle absolue, et comment elle est tenue
-------------------------------------------
Tout article sorti d'ici vient du corpus indexé — 4 087 articles réels des
codes tunisiens — et repasse par une vérification d'existence AVANT d'être
retourné. Deux barrières, volontairement redondantes :

  1. RÉCUPÉRATION : `retrieve.search()` ne peut retourner que des documents
     présents dans l'index. Un article inventé n'a aucun chemin pour entrer.
  2. VÉRIFICATION : chaque article retenu est relu dans le corpus par son
     couple (code_id, numéro), et sa `citation_ar` doit correspondre au
     caractère près. Si elle diverge, l'article est écarté.

La seconde barrière paraît superflue tant que la première tient. Elle existe
parce que l'agent 3, lui, parle à un modèle de langage : la liste blanche
qu'il reçoit doit être vérifiée à la source, pas seulement plausible.

L'abstention n'est pas un échec
-------------------------------
Quand `gate.py` juge qu'une question n'est pas fondée sur le corpus, cet
agent retourne une abstention explicite au lieu des cinq meilleurs scores
BM25. Sur une question de droit spatial, les cinq meilleurs scores existent
toujours — ils sont simplement sans rapport. Les retourner serait la forme
la plus coûteuse d'hallucination : des vrais articles, à la mauvaise place.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

from agents import amorce  # noqa: F401

from packages.legal import gate, retrieve

NOM = "chercheur"


@dataclass
class ArticleTrouve:
    """Un article du corpus, avec la question qui l'a fait remonter."""

    code_id: str
    code_fr: str
    article: str
    citation_ar: str
    text_ar: str
    score: float
    question: str
    motif_fr: str

    @property
    def cle(self):
        return f"{self.code_id}:{self.article}"

    def to_dict(self):
        d = asdict(self)
        d["cle"] = self.cle
        # Le texte intégral alourdit le journal sans rien prouver de plus.
        d["text_ar"] = self.text_ar[:300]
        return d


@dataclass
class Recherche:
    """Sortie de l'agent 2."""

    fonde: bool
    articles: list = field(default_factory=list)
    abstentions: list = field(default_factory=list)
    questions: list = field(default_factory=list)
    motif_abstention: str | None = None

    @property
    def cles_autorisees(self) -> set:
        """La liste blanche que l'agent 3 n'a pas le droit de dépasser."""
        return {a.cle for a in self.articles}

    @property
    def numeros_autorises(self) -> set:
        """Les numéros d'articles citables, en texte."""
        return {str(a.article) for a in self.articles}

    def to_dict(self):
        return {
            "fonde": self.fonde,
            "articles": [a.to_dict() for a in self.articles],
            "abstentions": self.abstentions,
            "questions": self.questions,
            "motif_abstention": self.motif_abstention,
        }


# --- Vérification d'existence ----------------------------------------------

_INDEX_EXACT: dict[str, dict] = {}


def _charger_index():
    """Index (code_id, article) -> document, construit une fois."""
    if not _INDEX_EXACT:
        for d in retrieve.load_docs():
            _INDEX_EXACT[f"{d['code_id']}:{d['article']}"] = d
    return _INDEX_EXACT


def existe(code_id, article) -> dict | None:
    """Le corpus contient-il réellement cet article ? Retourne le document."""
    return _charger_index().get(f"{code_id}:{article}")


def _verifier(hit) -> bool:
    """Seconde barrière : l'article retenu est-il bien celui du corpus ?"""
    doc = existe(hit.get("code_id"), hit.get("article"))
    if doc is None:
        return False
    return doc["citation_ar"] == hit.get("citation_ar")


# --- Questions dérivées des faits ------------------------------------------
# Chaque question est posée en arabe : le corpus est arabe, et BM25 ne fait
# aucune traduction. Le `motif_fr` dit pourquoi elle est posée — c'est ce qui
# permet de relire la chaîne sans lire l'arabe.

def questions_depuis_faits(faits: dict) -> list[dict]:
    """Traduit des faits en interrogations du corpus.

    Les faits pilotent les questions : une créance sur marchandises livrées
    n'interroge pas le même droit qu'une prestation de service.
    """
    montant = faits.get("montant_tnd")
    nature = (faits.get("nature_creance") or "").lower()

    questions = []

    if "marchandise" in nature:
        questions.append({
            "q": "تسقط الدعوى بمضي عام فيما يطلبه الباعة وأرباب المصانع من ثمن ما سلموه",
            "motif_fr": "Prescription du prix des marchandises livrées "
                        "(la facture porte sur une livraison).",
        })
    else:
        questions.append({
            "q": "كل دعوى ناشئة عن تعمير الذمة لا تسمع بعد مضي خمس عشرة سنة",
            "motif_fr": "Prescription générale (la créance ne porte pas sur "
                        "une livraison de marchandises).",
        })

    if montant is not None and float(montant) > 150:
        questions.append({
            "q": "إذا تجاوز الدين مائة وخمسين دينارا فعلى الدائن قبل تقديم العريضة أن ينذر المدين بواسطة عدل منفذ",
            "motif_fr": "Mise en demeure par huissier : la créance dépasse "
                        "150 DT.",
        })

    questions += [
        {
            "q": "يمكن تطبيق إجراءات الأمر بالدفع في الدين المعين المقدار الثابت بكتب",
            "motif_fr": "Procédure d'injonction de payer pour une créance "
                        "déterminée d'origine contractuelle.",
        },
        {
            "q": "عدم الوفاء بالعقد أو المماطلة فيه يوجبان القيام بالخسارة",
            "motif_fr": "Le retard de paiement ouvre droit à réparation.",
        },
    ]
    return questions


def _interroger(question: str, motif_fr: str, k: int) -> tuple[list, dict | None]:
    """Une question -> des articles vérifiés, ou une abstention motivée."""
    hits = retrieve.search(question, k=k)
    verdict = gate.evaluate(question, hits)

    if not verdict["grounded"]:
        return [], {
            "question": question,
            "motif_fr": motif_fr,
            "raison": verdict["reason"],
            "meilleur_score": verdict["best_score"],
            "mots_communs": verdict["matched"],
        }

    retenus = []
    for h in hits:
        if not _verifier(h):
            # Un hit non vérifiable est écarté en silence côté droit, mais
            # jamais transformé en réponse.
            continue
        retenus.append(ArticleTrouve(
            code_id=h["code_id"],
            code_fr=h["code_fr"],
            article=str(h["article"]),
            citation_ar=h["citation_ar"],
            text_ar=h["text_ar"],
            score=float(h["score"]),
            question=question,
            motif_fr=motif_fr,
        ))
    return retenus, None


def chercher(faits: dict, k: int = 2) -> Recherche:
    """Cherche le droit applicable aux faits de l'agent 1.

    `k` reste petit : au-delà des deux meilleurs articles par question, BM25
    remonte du contexte, pas du fondement.
    """
    questions = questions_depuis_faits(faits)
    articles: list[ArticleTrouve] = []
    abstentions: list[dict] = []
    vus: set[str] = set()

    for item in questions:
        trouves, abstention = _interroger(item["q"], item["motif_fr"], k)
        if abstention:
            abstentions.append(abstention)
            continue
        for a in trouves:
            if a.cle in vus:
                continue
            vus.add(a.cle)
            articles.append(a)

    fonde = bool(articles)
    return Recherche(
        fonde=fonde,
        articles=articles,
        abstentions=abstentions,
        questions=[q["q"] for q in questions],
        motif_abstention=None if fonde else (
            "Aucune des questions posées au corpus n'est fondée : "
            + " | ".join(a["raison"] or "?" for a in abstentions)
        ),
    )


def chercher_question(question: str, k: int = 3) -> Recherche:
    """Interroge le corpus sur une question libre.

    Sert la voie « une PME pose une question » et, accessoirement, rend
    l'abstention testable sur une question hors corpus.
    """
    trouves, abstention = _interroger(question, "question libre", k)
    if abstention:
        return Recherche(
            fonde=False,
            articles=[],
            abstentions=[abstention],
            questions=[question],
            motif_abstention=gate.ABSTAIN_MESSAGE,
        )
    return Recherche(
        fonde=bool(trouves),
        articles=trouves,
        abstentions=[],
        questions=[question],
        motif_abstention=None if trouves else gate.ABSTAIN_MESSAGE,
    )


def ancrer(sources: list) -> list:
    """Confirme dans le corpus les articles cités par le moteur déterministe.

    Le moteur (`legal_engine`) raisonne sur des constantes adossées à des
    articles précis. Ces articles sont ici RELUS dans le corpus : ce qui n'y
    figure pas ne sera pas citable par l'agent 3, même si le moteur s'en sert.
    """
    confirmes = []
    vus = set()
    for s in sources or []:
        code_id, art = s.get("code_id"), s.get("article")
        doc = existe(code_id, art)
        if doc is None:
            continue
        cle = f"{code_id}:{art}"
        if cle in vus:
            continue
        vus.add(cle)
        confirmes.append(ArticleTrouve(
            code_id=doc["code_id"],
            code_fr=doc["code_fr"],
            article=str(doc["article"]),
            citation_ar=doc["citation_ar"],
            text_ar=doc["text_ar"],
            score=0.0,
            question=f"vérification d'existence : {cle}",
            motif_fr=s.get("label_fr", "article retenu par le moteur juridique"),
        ))
    return confirmes


if __name__ == "__main__":  # pragma: no cover
    import json
    import sys

    if len(sys.argv) > 1:
        r = chercher_question(" ".join(sys.argv[1:]))
    else:
        r = chercher({
            "montant_tnd": 9520.0,
            "nature_creance": "livraison de marchandises",
        })
    print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2))
