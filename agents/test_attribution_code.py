"""
Le bon numéro dans le mauvais code reste une erreur de droit.

Ce fichier est né d'une faute observée en conditions réelles, pas d'un cas
imaginé. Le 13/09/2026 à 3h20, la chaîne complète a tourné sur la facture
d'Ahmed avec le modèle local, et l'agent 3 a écrit :

    « Cette procédure est obligatoire car la créance dépasse 150 dinars
      (Code des Obligations et des Contrats, article 60). »

L'article 60 appartient au Code de procédure civile et commerciale, pas au
Code des obligations et des contrats. Le contrôle anti-hallucination n'a rien
signalé : il comparait des NUMÉROS, et le 60 figurait bien dans la liste
fournie par l'agent 2. La garantie était donc creuse sur ce point précis —
un magistrat qui lit cette phrase cesse de faire confiance au reste.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

from redacteur import attributions_citees, numeros_cites, rediger
from chercheur import ArticleTrouve


def _article(code_id, numero, citation_ar):
    """Construit un ArticleTrouve comme l'agent 2 en produit réellement."""
    return ArticleTrouve(
        code_id=code_id,
        code_fr={"coc": "Code des obligations et des contrats",
                 "procciv": "Code de procédure civile et commerciale"}[code_id],
        article=str(numero),
        citation_ar=citation_ar,
        text_ar="",
        score=9.9,
        question="dossier de test",
        motif_fr="article retenu pour ce test",
    )


# La phrase exacte produite par qwen2.5:7b-instruct-q4_K_M, conservée telle
# quelle : un test écrit à partir du vrai défaut vaut mieux qu'un test écrit
# à partir de l'idée qu'on s'en fait.
PHRASE_FAUTIVE = (
    "Cette procédure est obligatoire car la créance dépasse 150 dinars "
    "(Code des Obligations et des Contrats, article 60). Laissez 5 jours "
    "au débiteur pour répondre."
)

ARTICLES_AUTORISES = [
    _article("coc", 403, "الفصل 403 من مجلة الالتزامات والعقود"),
    _article("procciv", 60, "الفصل 60 من مجلة المرافعات المدنية والتجارية"),
]

FAITS = {"montant_tnd": 9520.0, "date_facture": "2026-05-12"}
EVALUATION = {
    "regime": "goods_1y",
    "jours_restants": 241,
    "echeance": "2027-05-12",
    "huissier_requis": True,
    "jours_francs": 5,
}


class ModeleQuiSeTrompeDeCode:
    """Un modèle qui cite un numéro autorisé sous le mauvais code."""

    origine = "simulacre"

    def generer(self, invite, systeme=None, max_tokens=None):
        from types import SimpleNamespace
        return SimpleNamespace(
            texte=PHRASE_FAUTIVE, origine="simulacre", duree_s=0.01
        )


class ModeleCorrect:
    """Le même contenu, avec la bonne attribution."""

    origine = "simulacre"

    def generer(self, invite, systeme=None, max_tokens=None):
        from types import SimpleNamespace
        return SimpleNamespace(
            texte=(
                "Le Code de procédure civile et commerciale, article 60, "
                "impose l'intervention d'un huissier de justice. Le Code des "
                "obligations et des contrats, article 403, fixe le délai."
            ),
            origine="simulacre",
            duree_s=0.01,
        )


def test_le_numero_seul_ne_suffisait_pas_a_voir_la_faute():
    """Preuve que l'ancien contrôle était aveugle à cette erreur."""
    # Le 60 est bien dans la liste blanche : le contrôle par numéro passe.
    assert "60" in numeros_cites(PHRASE_FAUTIVE)
    autorises = {str(a.article) for a in ARTICLES_AUTORISES}
    assert not (numeros_cites(PHRASE_FAUTIVE) - autorises), (
        "l'ancien contrôle ne voyait aucune violation — c'est précisément "
        "pourquoi ce fichier existe"
    )


def test_l_attribution_au_mauvais_code_est_detectee():
    """Le nouveau contrôle, lui, voit la faute."""
    assert ("coc", "60") in attributions_citees(PHRASE_FAUTIVE)


def test_l_attribution_correcte_n_est_pas_signalee():
    """Un garde qui refuse tout ne garde rien : il doit laisser passer le juste."""
    correct = "Le Code de procédure civile, article 60, impose l'huissier."
    assert ("procciv", "60") in attributions_citees(correct)
    assert ("coc", "60") not in attributions_citees(correct)


def test_la_redaction_fautive_est_ecartee_en_entier():
    """Le texte mal attribué ne doit jamais atteindre la PME."""
    r = rediger(
        FAITS, ARTICLES_AUTORISES, EVALUATION,
        client=ModeleQuiSeTrompeDeCode(), utiliser_modele=True,
    )
    assert r.origine == "deterministe", (
        "un texte qui rattache un article au mauvais code doit être écarté"
    )
    assert r.motif_repli and "mauvais code" in r.motif_repli
    assert "Code des Obligations et des Contrats, article 60" not in r.texte


def test_la_redaction_correcte_est_conservee():
    """Sans faute, la rédaction du modèle est bien celle qui est servie."""
    r = rediger(
        FAITS, ARTICLES_AUTORISES, EVALUATION,
        client=ModeleCorrect(), utiliser_modele=True,
    )
    assert r.origine == "simulacre", (
        f"rédaction correcte écartée à tort : {r.motif_repli}"
    )
    assert r.motif_repli is None


def test_la_pme_recoit_toujours_un_texte():
    """Même écarté, le dossier reste explicable : le droit est déterministe."""
    r = rediger(
        FAITS, ARTICLES_AUTORISES, EVALUATION,
        client=ModeleQuiSeTrompeDeCode(), utiliser_modele=True,
    )
    assert len(r.texte) > 100
    assert "403" in r.texte
