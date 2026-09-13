"""Tests de l'API Mizan.

Lancer : ./.venv/bin/python -m pytest api/ -q   (depuis ~/mizan)

Ce que ces tests vérifient n'est pas « l'API répond 200 ». C'est :
  - qu'une entrée juridiquement impossible est REFUSÉE avec un 400 lisible,
    pas avalée ni transformée en 500 ;
  - que les articles affichés viennent du moteur et pas d'un modèle ;
  - que la plateforme reste utilisable quand le modèle est débranché.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import main
from api.main import app
from packages.models.client import Hebergement, ModeleIndisponible, Reponse

RACINE = Path(__file__).resolve().parents[1]
FACTURE = RACINE / "samples" / "facture_ahmed.pdf"
INTRUS = RACINE / "samples" / "not_an_invoice_joining_instructions.pdf"

# Jour du hackathon, figé : un test qui dépend de la date du jour ment un jour.
JOUR = "2026-09-12"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class _ClientAbsent:
    """Un ClientLLM dont aucun hébergement ne répond."""

    hebergements = [
        Hebergement(nom="local", base_url="http://127.0.0.1:11434/v1",
                    modele="qwen2.5", delai_s=1.0),
    ]

    def sonder(self):
        return [(self.hebergements[0], False, "ConnectError: [Errno 111] refusé")]

    def disponible(self):
        return False

    def generer(self, *a, **kw):
        raise ModeleIndisponible(
            "aucun hébergement n'a répondu — local: ConnectError: refusé"
        )


class _ClientBavard:
    """Un modèle qui répond — et qui cite un article, ce qu'il ne doit pas."""

    hebergements = _ClientAbsent.hebergements

    def sonder(self):
        return [(self.hebergements[0], True, "ok")]

    def disponible(self):
        return True

    def generer(self, invite, **kw):
        return Reponse(
            texte=("Votre créance est encore recouvrable. Selon l'article 403 "
                   "du COC et الفصل 60, vous devez agir vite."),
            origine="local", duree_s=1.4,
        )


@pytest.fixture
def modele_absent(monkeypatch):
    monkeypatch.setattr(main, "client_llm", lambda: _ClientAbsent())


@pytest.fixture
def modele_bavard(monkeypatch):
    monkeypatch.setattr(main, "client_llm", lambda: _ClientBavard())


# ---------------------------------------------------------------------------
# /sante
# ---------------------------------------------------------------------------

def test_sante_repond(client):
    r = client.get("/sante")
    assert r.status_code == 200
    d = r.json()
    assert d["service"] == "mizan-api"
    assert d["moteur_juridique"] == "deterministe"
    assert d["version"]
    # L'index réel du dépôt contient plusieurs milliers d'articles.
    assert d["articles_indexes"] > 1000
    assert d["index_charge"] is True
    assert isinstance(d["modele_disponible"], bool)
    assert d["motif_modele"]  # jamais vide : ok, ou la cause exacte


def test_sante_dit_pourquoi_le_modele_manque(client, modele_absent):
    d = client.get("/sante").json()
    assert d["modele_disponible"] is False
    assert "ConnectError" in d["motif_modele"]
    assert d["hebergements"][0]["disponible"] is False


# ---------------------------------------------------------------------------
# /dossiers/analyser
# ---------------------------------------------------------------------------

def test_analyser_dossier_ahmed(client):
    """Le dossier de démonstration : 9520 DT, facture du 12/05/2026, menuisier."""
    r = client.post("/dossiers/analyser", json={
        "montant_tnd": 9520.0,
        "date_facture": "2026-05-12",
        "activite": "menuiserie",
    })
    assert r.status_code == 200
    d = r.json()

    # Le point du projet : un an, pas quinze.
    assert d["regime"] == "goods_1y"
    assert d["echeance"] == "2027-05-12"
    assert d["est_prescrit"] is False
    assert 0 < d["jours_restants"] < 365
    assert d["huissier_requis"] is True
    assert d["jours_francs"] == 5

    # COC art. 403 doit figurer dans les sources, avec sa citation arabe.
    coc403 = [s for s in d["sources"]
              if s["code_id"] == "coc" and s["article"] == 403]
    assert coc403, f"COC 403 absent des sources : {d['sources']}"
    assert "403" in coc403[0]["citation_ar"]
    assert coc403[0]["short_fr"] == "COC art. 403"

    assert d["origine"] == "moteur_deterministe"
    assert len(d["etapes"]) == 3


def test_analyser_avec_jour_fige_donne_241_jours(client):
    """Avec une date de référence figée, le compte est vérifiable exactement."""
    r = client.post("/dossiers/analyser", json={
        "montant_tnd": 9520.0, "date_facture": "2026-05-12",
        "activite": "menuiserie", "aujourdhui": JOUR,
    })
    assert r.status_code == 200
    # 2026-05-12 + 365 j = 2027-05-12 ; depuis le 2026-09-12 il reste 242 jours.
    assert r.json()["jours_restants"] == 242


def test_analyser_refuse_une_facture_datee_dans_le_futur(client):
    """Le moteur lève DateImpossible : l'API doit répondre 400, pas 500."""
    demain = (date.today() + timedelta(days=1)).isoformat()
    r = client.post("/dossiers/analyser", json={
        "montant_tnd": 9520.0, "date_facture": demain, "activite": "menuiserie",
    })
    assert r.status_code == 400, f"attendu 400, reçu {r.status_code}"
    detail = r.json()["detail"]
    assert "après aujourd'hui" in detail
    assert "prescrire avant d'exister" in detail


def test_analyser_refuse_un_montant_nul(client):
    r = client.post("/dossiers/analyser", json={
        "montant_tnd": 0, "date_facture": "2026-05-12", "activite": "menuiserie",
    })
    # Le schéma pydantic barre la route avant le moteur : 422 est aussi un refus.
    assert r.status_code in (400, 422)


def test_analyser_refuse_une_date_illisible(client):
    r = client.post("/dossiers/analyser", json={
        "montant_tnd": 100.0, "date_facture": "12/05/2026", "activite": "menuiserie",
    })
    assert r.status_code == 400
    assert "AAAA-MM-JJ" in r.json()["detail"]


def test_activite_inconnue_est_signalee_et_pas_devinee(client):
    r = client.post("/dossiers/analyser", json={
        "montant_tnd": 5000.0, "date_facture": "2026-05-12",
        "activite": "sculpture_sur_glace", "aujourdhui": JOUR,
    })
    assert r.status_code == 200
    d = r.json()
    assert d["regime"] == "indetermine"
    assert "n'est PAS confirmé" in d["regime_reason_fr"]


# ---------------------------------------------------------------------------
# /corpus/rechercher
# ---------------------------------------------------------------------------

def test_recherche_arabe_retourne_des_articles(client):
    r = client.get("/corpus/rechercher", params={"q": "تقادم ثمن البضائع", "k": 5})
    assert r.status_code == 200
    d = r.json()
    assert d["nombre"] > 0
    premier = d["resultats"][0]
    assert premier["citation_ar"]
    assert "الفصل" in premier["citation_ar"]
    assert premier["text_ar"]
    assert premier["score"] > 0


def test_recherche_filtree_par_code(client):
    r = client.get("/corpus/rechercher",
                   params={"q": "الأمر بالدفع", "k": 3, "code_id": "procciv"})
    assert r.status_code == 200
    for a in r.json()["resultats"]:
        assert a["code_id"] == "procciv"


def test_recherche_sabstient_sur_une_question_hors_sujet(client):
    """Le garde-fou doit le dire quand le corpus ne répond pas."""
    r = client.get("/corpus/rechercher", params={"q": "recette du couscous"})
    assert r.status_code == 200
    d = r.json()
    assert d["fonde"] is False
    assert d["message"] and "inventer" in d["message"]


# ---------------------------------------------------------------------------
# /dossiers/deposer-piece
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not FACTURE.exists(), reason="facture de démonstration absente")
def test_depot_de_la_facture_ahmed(client):
    with FACTURE.open("rb") as fh:
        r = client.post("/dossiers/deposer-piece",
                        files={"fichier": ("facture_ahmed.pdf", fh, "application/pdf")})
    assert r.status_code == 200
    d = r.json()
    assert d["acceptee"] is True
    assert len(d["sha256"]) == 64
    assert d["montant_tnd"] == pytest.approx(9520.0)
    assert d["date_facture"] == "2026-05-12"
    assert d["motif_refus"] is None


@pytest.mark.skipif(not FACTURE.exists(), reason="facture de démonstration absente")
def test_empreinte_sha256_est_celle_du_fichier(client):
    import hashlib
    attendu = hashlib.sha256(FACTURE.read_bytes()).hexdigest()
    with FACTURE.open("rb") as fh:
        d = client.post("/dossiers/deposer-piece",
                        files={"fichier": ("f.pdf", fh, "application/pdf")}).json()
    assert d["sha256"] == attendu


@pytest.mark.skipif(not INTRUS.exists(), reason="intrus de démonstration absent")
def test_depot_refuse_un_document_qui_nest_pas_une_facture(client):
    with INTRUS.open("rb") as fh:
        r = client.post("/dossiers/deposer-piece",
                        files={"fichier": ("joining.pdf", fh, "application/pdf")})
    assert r.status_code == 200          # un refus motivé, pas une panne
    d = r.json()
    assert d["acceptee"] is False
    assert d["motif_refus"]
    assert d["montant_tnd"] is None      # rien n'est deviné
    assert len(d["sha256"]) == 64        # la trace existe quand même


def test_depot_refuse_un_fichier_vide(client):
    r = client.post("/dossiers/deposer-piece",
                    files={"fichier": ("vide.pdf", b"", "application/pdf")})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# /assistant/expliquer
# ---------------------------------------------------------------------------

def test_expliquer_en_mode_degrade_quand_le_modele_est_absent(client, modele_absent):
    """L'exigence centrale : pas de 500 quand le GPU est débranché."""
    r = client.post("/assistant/expliquer", json={
        "montant_tnd": 9520.0, "date_facture": "2026-05-12",
        "activite": "menuiserie", "aujourdhui": JOUR,
    })
    assert r.status_code == 200, f"le mode dégradé doit rester utilisable, reçu {r.status_code}"
    d = r.json()
    assert d["mode_degrade"] is True
    assert d["origine"] == "aucune"
    assert d["motif_degradation"]
    # Le droit, lui, est intact.
    assert d["analyse"]["regime"] == "goods_1y"
    assert d["analyse"]["jours_restants"] == 242
    assert any(s["short_fr"] == "COC art. 403" for s in d["sources"])
    # Le texte dégradé reste exploitable par une PME.
    assert "242" in d["texte"] and "2027-05-12" in d["texte"]


def test_expliquer_accepte_une_analyse_deja_produite(client, modele_absent):
    analyse = client.post("/dossiers/analyser", json={
        "montant_tnd": 9520.0, "date_facture": "2026-05-12",
        "activite": "menuiserie", "aujourdhui": JOUR,
    }).json()
    r = client.post("/assistant/expliquer", json={"analyse": analyse})
    assert r.status_code == 200
    assert r.json()["analyse"]["echeance"] == "2027-05-12"


def test_expliquer_retire_les_articles_inventes_par_le_modele(client, modele_bavard):
    """« L'IA propose, le droit dispose » : un article sorti du modèle est retiré."""
    r = client.post("/assistant/expliquer", json={
        "montant_tnd": 9520.0, "date_facture": "2026-05-12",
        "activite": "menuiserie", "aujourdhui": JOUR,
    })
    assert r.status_code == 200
    d = r.json()
    assert d["mode_degrade"] is False
    assert d["origine"] == "local"
    assert d["duree_s"] > 0
    texte = d["texte"]
    assert "article 403" not in texte.lower()
    assert "الفصل 60" not in texte
    assert main.MENTION_PURGE in texte
    # Mais les vraies références, elles, sont bien là — venues du moteur.
    assert any(s["short_fr"] == "COC art. 403" for s in d["sources"])


def test_expliquer_ne_fait_pas_confiance_a_une_analyse_falsifiee(client, modele_absent):
    """Un client qui envoie « 9999 jours restants » ne doit pas être cru."""
    r = client.post("/assistant/expliquer", json={
        "analyse": {
            "montant_tnd": 9520.0, "date_facture": "2026-05-12",
            "aujourdhui": JOUR, "jours_restants": 9999, "est_prescrit": False,
        },
    })
    assert r.status_code == 200
    assert r.json()["analyse"]["jours_restants"] == 242


def test_expliquer_refuse_une_demande_sans_montant(client, modele_absent):
    r = client.post("/assistant/expliquer", json={"activite": "menuiserie"})
    assert r.status_code == 400


def test_expliquer_refuse_une_facture_future(client, modele_absent):
    demain = (date.today() + timedelta(days=1)).isoformat()
    r = client.post("/assistant/expliquer", json={
        "montant_tnd": 9520.0, "date_facture": demain,
    })
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Garde-fou transverse
# ---------------------------------------------------------------------------

def test_purge_des_references_darticle():
    for brut in ["selon l'article 403", "Art. 60 du code", "الفصل 403",
                 "COC art. 278", "voir articles 12 et 13"]:
        purge, touche = main._purger_articles(brut)
        assert touche, f"référence non détectée : {brut}"
        assert main.MENTION_PURGE in purge


def test_un_texte_sans_reference_nest_pas_modifie():
    brut = "Il vous reste 242 jours pour agir. Contactez un huissier."
    purge, touche = main._purger_articles(brut)
    assert not touche
    assert purge == brut


def test_cors_autorise_le_frontend(client):
    r = client.options("/sante", headers={
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "GET",
    })
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
