"""Tests de la chaîne d'agents Mizan.

Le test qui compte est `test_redacteur_ne_peut_pas_citer_hors_liste` et sa
variante adversariale. Les autres vérifient que les refus et les abstentions
fonctionnent, et que la chaîne reste utilisable sans modèle de langage.

Aucun test n'exige la présence du modèle : ceux qui en ont besoin sont
marqués et sautés s'il est injoignable, pour que la suite reste verte sur une
machine hors-ligne. Ils ne sont jamais silencieusement neutralisés.
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

from agents import amorce  # noqa: F401

from agents import chaine, chercheur, lecteur, redacteur
from packages.legal.legal_engine import assess
from packages.models.client import ModeleIndisponible, Reponse

RACINE = Path(__file__).resolve().parents[1]
FACTURE = RACINE / "samples" / "facture_ahmed.pdf"
INTRUS = RACINE / "samples" / "not_an_invoice_joining_instructions.pdf"

# Date figée : sans cela, les délais changent tous les jours et les tests
# deviennent faux avec le temps plutôt qu'avec le code.
AUJOURDHUI = date(2026, 9, 13)


def modele_joignable() -> bool:
    try:
        from packages.models.client import ClientLLM

        return ClientLLM().disponible()
    except Exception:
        return False


besoin_modele = pytest.mark.skipif(
    not modele_joignable(),
    reason="modèle local injoignable — test exécuté seulement si le tunnel est ouvert",
)


# ---------------------------------------------------------------------------
# Agent 1 — lecteur
# ---------------------------------------------------------------------------

def test_lecteur_extrait_les_faits_avec_page_et_empreinte():
    r = lecteur.lire(FACTURE)

    assert r.accepte is True
    assert len(r.sha256) == 64                    # SHA-256 en hexadécimal
    assert r.valeur("montant_tnd") == 9520.0
    assert r.valeur("date_facture") == "2026-05-12"
    assert r.valeur("nature_creance") == "livraison de marchandises"

    # Chaque fait doit être re-vérifiable dans le document : une page ET la
    # ligne qui le porte. Un fait sans origine n'est pas traçable.
    for f in r.faits:
        assert f.page == 1, f"{f.cle} n'a pas de page d'origine"
        assert f.ligne, f"{f.cle} n'a pas de ligne d'origine"


def test_lecteur_empreinte_stable_et_dependante_du_contenu(tmp_path):
    a = lecteur.empreinte(FACTURE)
    assert a == lecteur.empreinte(FACTURE)        # stable

    copie = tmp_path / "modifiee.pdf"
    copie.write_bytes(FACTURE.read_bytes() + b"%modif")
    assert lecteur.empreinte(copie) != a          # un octet suffit


@pytest.mark.skipif(not INTRUS.exists(), reason="échantillon intrus absent")
def test_lecteur_refuse_un_document_qui_nest_pas_une_facture():
    """LE refus qui a motivé la porte d'entrée : un PDF d'agenda de hackathon.

    Mizan avait produit une mise en demeure exécutoire à partir de ce fichier.
    Le lecteur doit refuser ET ne produire AUCUN fait : ce sont les faits qui
    deviennent une créance en aval.
    """
    r = lecteur.lire(INTRUS)

    assert r.accepte is False
    assert r.motif_refus
    assert r.faits == [], "un document refusé ne doit produire aucun fait"
    assert len(r.sha256) == 64      # il reste identifiable, même refusé


def test_lecteur_refuse_un_devis(tmp_path):
    """Un devis ressemble à une facture mais ne constate aucune créance."""
    from packages.legal import doc_gate

    devis = (
        "MENUISERIE AHMED\nMatricule fiscal : 1234567/A/M/000\n"
        "DEVIS N° 2026-007\nDésignation Qté P.U. (DT)\n"
        "Table de réunion 2 1,800.000\nTOTAL 3,600.000 DT\n"
    )
    v = doc_gate.inspect(devis)
    assert v["is_invoice"] is False


def test_lecteur_signale_un_fichier_absent():
    with pytest.raises(FileNotFoundError):
        lecteur.lire(RACINE / "samples" / "inexistant.pdf")


# ---------------------------------------------------------------------------
# Agent 2 — chercheur
# ---------------------------------------------------------------------------

def test_chercheur_ne_retourne_que_des_articles_du_corpus():
    faits = {"montant_tnd": 9520.0, "nature_creance": "livraison de marchandises"}
    r = chercheur.chercher(faits)

    assert r.fonde is True
    assert r.articles, "aucun article trouvé sur un cas standard"

    for a in r.articles:
        doc = chercheur.existe(a.code_id, a.article)
        assert doc is not None, f"{a.cle} n'existe pas dans le corpus"
        # La citation doit correspondre au caractère près à celle du corpus.
        assert a.citation_ar == doc["citation_ar"]
        assert a.text_ar


def test_chercheur_trouve_la_prescription_des_marchandises():
    """Le droit attendu sur une livraison impayée : COC 403 (un an)."""
    faits = {"montant_tnd": 9520.0, "nature_creance": "livraison de marchandises"}
    r = chercheur.chercher(faits)
    assert "coc:403" in r.cles_autorisees
    # Et la procédure applicable au-delà de 150 DT.
    assert "procciv:60" in r.cles_autorisees


def test_chercheur_sabstient_sur_une_question_hors_corpus():
    """Droit spatial : le corpus tunisien n'en contient rien.

    BM25 retourne TOUJOURS un classement — il y a toujours cinq « meilleurs »
    articles. Les présenter serait la pire forme d'hallucination : de vrais
    articles, à la mauvaise place. L'agent doit s'abstenir.
    """
    r = chercheur.chercher_question(
        "قانون الفضاء الخارجي والكواكب والأقمار الصناعية")

    assert r.fonde is False
    assert r.articles == [], "aucun article ne doit être retourné hors corpus"
    assert r.motif_abstention
    assert r.abstentions and r.abstentions[0]["raison"]


@pytest.mark.parametrize("question", [
    "recette du couscous au poisson",
    "comment réparer un moteur diesel",
    "ما هو لون السماء",
])
def test_chercheur_sabstient_sur_des_questions_absurdes(question):
    r = chercheur.chercher_question(question)
    assert r.fonde is False, f"a répondu à « {question} »"
    assert r.articles == []


def test_ancrer_ignore_un_article_absent_du_corpus():
    """Un article que le moteur citerait sans qu'il existe est écarté."""
    faux = [{"code_id": "coc", "article": 99999, "label_fr": "article inventé"}]
    assert chercheur.ancrer(faux) == []

    vrai = [{"code_id": "coc", "article": 403, "label_fr": "prescription"}]
    confirmes = chercheur.ancrer(vrai)
    assert len(confirmes) == 1 and confirmes[0].article == "403"


# ---------------------------------------------------------------------------
# Extraction des numéros d'articles — l'outil du test principal
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("texte,attendu", [
    ("L'article 403 s'applique.", {"403"}),
    ("Voir art. 59 et article 60.", {"59", "60"}),
    ("COC art. 403 et CPCC 59", {"403", "59"}),
    ("الفصل 278 من مجلة الالتزامات", {"278"}),
    ("l'article 1044 du code des obligations", {"1044"}),
    ("Aucune référence légale ici.", set()),
    ("Vous avez 241 jours et 9520 DT.", set()),   # des nombres, pas des articles
])
def test_extraction_des_numeros_darticles(texte, attendu):
    """Le détecteur doit voir les citations, et seulement elles.

    Si cette fonction rate une forme de citation, la garantie du rédacteur
    devient creuse : c'est elle qui la rend vérifiable.
    """
    assert redacteur.numeros_cites(texte) == attendu


# ---------------------------------------------------------------------------
# Agent 3 — LE TEST QUI COMPTE
# ---------------------------------------------------------------------------

@dataclass
class _RechercheFactice:
    """Une sortie d'agent 2 réduite à un seul article."""

    articles: list
    motif_abstention: str | None = None


def _un_seul_article(code_id="coc", article=403):
    doc = chercheur.existe(code_id, article)
    assert doc is not None, "l'article de référence doit exister dans le corpus"
    return _RechercheFactice(articles=[chercheur.ArticleTrouve(
        code_id=doc["code_id"],
        code_fr=doc["code_fr"],
        article=str(doc["article"]),
        citation_ar=doc["citation_ar"],
        text_ar=doc["text_ar"],
        score=50.0,
        question="test",
        motif_fr="Prescription du prix des marchandises livrées.",
    )])


FAITS_TEST = {
    "montant_tnd": 9520.0,
    "date_facture": "2026-05-12",
    "client": "Société El Amen SARL",
    "vendeur": "MENUISERIE AHMED",
    "nature_creance": "livraison de marchandises",
}


def _evaluation_test():
    return assess(9520.0, "2026-05-12", "menuiserie", today=AUJOURDHUI).to_dict()


class _ModeleQuiHallucine:
    """Un modèle qui cite des articles qu'on ne lui a jamais donnés.

    C'est le cœur de la démonstration. On ne peut pas prouver une garantie en
    espérant que le vrai modèle se trompe un jour : il faut provoquer la
    faute. Ce faux client la provoque à tous les coups.
    """

    def __init__(self, texte):
        self.texte = texte
        self.appele = False

    def generer(self, invite, *, systeme=None, max_tokens=512, temperature=0.3):
        self.appele = True
        return Reponse(texte=self.texte, origine="local", duree_s=0.01)


def test_redacteur_rejette_un_texte_citant_un_article_hors_liste():
    """LE TEST CENTRAL — un article inventé doit faire tomber tout le texte.

    L'agent 2 n'a fourni QUE l'article 403. Le modèle en cite quatre autres,
    dont un (« article 9999 ») qui n'existe dans aucun code. Le rédacteur doit
    jeter la rédaction entière et retomber sur la version déterministe.
    """
    recherche = _un_seul_article()
    menteur = _ModeleQuiHallucine(
        "Votre créance relève de l'article 403 du code des obligations. "
        "Mais il faut aussi appliquer l'article 1234 et l'art. 9999, "
        "ainsi que الفصل 777 et le CPCC 58 qui encadrent la procédure."
    )

    r = redacteur.rediger(FAITS_TEST, recherche, _evaluation_test(),
                          client=menteur, utiliser_modele=True)

    assert menteur.appele, "le modèle devait être interrogé"
    # Le texte du menteur ne doit pas survivre.
    assert "9999" not in r.texte
    assert "1234" not in r.texte
    assert r.origine == "deterministe"
    assert r.motif_repli and "absents de la liste vérifiée" in r.motif_repli

    # Et la sortie finale reste dans la liste blanche.
    assert r.verification["viole"] is False
    assert set(r.articles_cites) <= {"403"}


def test_redacteur_conserve_un_texte_conforme():
    """Le contrôle ne doit pas jeter un texte légitime."""
    recherche = _un_seul_article()
    sage = _ModeleQuiHallucine(
        "Votre créance porte sur des marchandises livrées. L'article 403 "
        "du code des obligations fixe un délai d'un an pour agir. "
        "Adressez-vous à un huissier de justice sans tarder."
    )

    r = redacteur.rediger(FAITS_TEST, recherche, _evaluation_test(),
                          client=sage, utiliser_modele=True)

    assert r.origine == "local", "un texte conforme doit être conservé"
    assert r.motif_repli is None
    assert r.verification["viole"] is False
    assert r.articles_cites == ["403"]


@besoin_modele
def test_redacteur_ne_peut_pas_citer_hors_liste_avec_le_vrai_modele():
    """LA PROPRIÉTÉ, vérifiée contre le vrai qwen2.5 local.

    On ne donne qu'UN article (COC 403) et on lit la sortie réelle du modèle.
    L'invariant tient de deux façons : soit le modèle respecte la consigne,
    soit le contrôle l'écarte. Dans les deux cas, aucun autre numéro
    d'article ne peut apparaître dans le texte rendu à la PME.

    Si un article étranger survit, ce test échoue — c'est exactement ce qu'on
    veut qu'il fasse.
    """
    recherche = _un_seul_article()

    r = redacteur.rediger(FAITS_TEST, recherche, _evaluation_test(),
                          utiliser_modele=True)

    cites = redacteur.numeros_cites(r.texte)
    interdits = cites - {"403"}

    assert not interdits, (
        f"le texte rendu cite des articles non fournis : {sorted(interdits)}\n"
        f"origine : {r.origine}\n--- texte ---\n{r.texte}"
    )
    assert r.verification["viole"] is False


def test_redacteur_fonctionne_sans_modele():
    """Mode dégradé : le droit reste dit, sans modèle de langage."""
    recherche = _un_seul_article()

    r = redacteur.rediger(FAITS_TEST, recherche, _evaluation_test(),
                          utiliser_modele=False)

    assert r.origine == "deterministe"
    assert r.texte.strip(), "le mode dégradé doit produire un texte"
    assert "403" in r.texte
    assert r.verification["viole"] is False
    # Le montant et l'échéance viennent du moteur, pas d'un modèle.
    assert "9520" in r.texte
    assert "2027-05-12" in r.texte


def test_redacteur_ne_cite_rien_si_le_modele_est_indisponible():
    """Un modèle en panne ne doit pas faire disparaître le droit."""

    class _EnPanne:
        def generer(self, *a, **k):
            raise ModeleIndisponible("aucun hébergement n'a répondu — test")

    recherche = _un_seul_article()
    r = redacteur.rediger(FAITS_TEST, recherche, _evaluation_test(),
                          client=_EnPanne(), utiliser_modele=True)

    assert r.origine == "deterministe"
    assert r.motif_repli and "aucun modèle disponible" in r.motif_repli
    assert "403" in r.texte


def test_redacteur_sabstient_quand_lagent_2_na_rien_fonde():
    vide = _RechercheFactice(articles=[], motif_abstention="hors corpus")
    r = redacteur.rediger(FAITS_TEST, vide, {}, utiliser_modele=False)

    assert redacteur.numeros_cites(r.texte) == set(), \
        "une abstention ne doit citer aucun article"
    assert r.verification["viole"] is False


# ---------------------------------------------------------------------------
# La chaîne complète
# ---------------------------------------------------------------------------

def test_chaine_complete_sans_modele():
    """Le parcours de bout en bout doit tenir sans modèle de langage."""
    r = chaine.traiter(FACTURE, utiliser_modele=False, aujourdhui=AUJOURDHUI)

    assert r.ok is True
    assert r.arret is None
    assert len(r.sha256) == 64
    assert r.faits["montant_tnd"] == 9520.0
    assert r.evaluation["regime"] == "goods_1y"
    assert r.evaluation["deadline"] == "2027-05-12"
    assert r.evaluation["needs_bailiff"] is True
    assert r.origine_texte == "deterministe"
    assert r.verification["viole"] is False

    # Les trois agents + le moteur ont tous été journalisés, avec leur durée.
    agents = [e.agent for e in r.etapes]
    assert agents == ["lecteur", "chercheur", "moteur_juridique", "redacteur"]
    for e in r.etapes:
        assert e.duree_s >= 0.0
        assert e.resume


def test_chaine_ne_cite_que_des_articles_du_corpus():
    """Propriété de bout en bout : tout ce qui est cité existe vraiment."""
    r = chaine.traiter(FACTURE, utiliser_modele=False, aujourdhui=AUJOURDHUI)

    autorises = set(r.verification["autorises"])
    for num in redacteur.numeros_cites(r.explication):
        assert num in autorises, f"article {num} cité hors liste vérifiée"

    for a in r.articles:
        assert chercheur.existe(a["code_id"], a["article"]) is not None


@pytest.mark.skipif(not INTRUS.exists(), reason="échantillon intrus absent")
def test_chaine_sarrete_sur_une_piece_non_facture():
    """La chaîne doit s'arrêter au premier agent, sans produire de droit."""
    r = chaine.traiter(INTRUS, utiliser_modele=False, aujourdhui=AUJOURDHUI)

    assert r.ok is False
    assert "lecteur" in r.arret
    assert r.articles == [], "aucun article ne doit être produit"
    assert r.evaluation == {}, "aucun délai ne doit être calculé"
    assert redacteur.numeros_cites(r.explication) == set()
    assert len(r.etapes) == 1, "la chaîne ne doit pas dépasser l'agent 1"


@besoin_modele
def test_chaine_complete_avec_le_vrai_modele():
    """Le même parcours, modèle branché : l'invariant ne change pas."""
    r = chaine.traiter(FACTURE, utiliser_modele=True, aujourdhui=AUJOURDHUI)

    assert r.ok is True
    autorises = set(r.verification["autorises"])
    interdits = redacteur.numeros_cites(r.explication) - autorises
    assert not interdits, (
        f"la chaîne a cité des articles hors corpus : {sorted(interdits)}\n"
        f"origine : {r.origine_texte}\n{r.explication}"
    )


def test_ligne_de_commande():
    """L'orchestrateur doit marcher tel qu'il est documenté."""
    r = subprocess.run(
        [sys.executable, "-m", "agents.chaine",
         "samples/facture_ahmed.pdf", "--sans-modele"],
        cwd=RACINE, capture_output=True, text=True, timeout=180,
    )

    assert r.returncode == 0, r.stderr
    assert "MIZAN — chaîne d'agents" in r.stdout
    assert "JOURNAL DES AGENTS" in r.stdout
    assert "CONTRÔLE ANTI-HALLUCINATION" in r.stdout
    assert "Violation                        : non" in r.stdout
