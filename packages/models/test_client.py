"""
Vérifie que la bascule local → Modal fonctionne réellement.

Ces tests n'appellent aucun service distant : ils simulent les pannes qu'on
redoute pendant la démonstration, parce qu'on ne peut pas provoquer une panne
de GPU devant un jury pour vérifier que le secours marche.

    ./.venv/bin/python -m pytest packages/models/test_client.py -v
"""

from __future__ import annotations

import httpx
import pytest

from packages.models.client import (
    ClientLLM,
    Hebergement,
    ModeleIndisponible,
    _nettoyer,
)

LOCAL = Hebergement(nom="local", base_url="http://local/v1", modele="q", delai_s=5)
MODAL = Hebergement(nom="modal", base_url="http://modal/v1", modele="q", delai_s=5)


def _reponse(texte: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": texte}}]},
        request=httpx.Request("POST", "http://x"),
    )


def test_le_local_est_essaye_en_premier(monkeypatch):
    """La souveraineté des données n'est pas négociable : le local d'abord."""
    appels: list[str] = []

    def faux_post(url, **kw):
        appels.append(url)
        return _reponse("réponse locale")

    monkeypatch.setattr(httpx, "post", faux_post)
    rep = ClientLLM([LOCAL, MODAL]).generer("question")

    assert rep.origine == "local"
    assert appels == ["http://local/v1/chat/completions"]
    assert "modal" not in " ".join(appels)


def test_bascule_vers_modal_quand_le_gpu_local_tombe(monkeypatch):
    """Le scénario qu'on redoute : le GPU sature pendant la démonstration."""
    appels: list[str] = []

    def faux_post(url, **kw):
        appels.append(url)
        if "local" in url:
            raise httpx.ConnectError("GPU saturé", request=httpx.Request("POST", url))
        return _reponse("réponse de secours")

    monkeypatch.setattr(httpx, "post", faux_post)
    rep = ClientLLM([LOCAL, MODAL]).generer("question")

    assert rep.origine == "modal"
    assert len(appels) == 2, "le local doit avoir été tenté avant la bascule"


def test_bascule_aussi_sur_un_delai_depasse(monkeypatch):
    """Un GPU qui répond en 90 s est aussi inutilisable qu'un GPU éteint."""

    def faux_post(url, **kw):
        if "local" in url:
            raise httpx.ReadTimeout("trop lent", request=httpx.Request("POST", url))
        return _reponse("secours")

    monkeypatch.setattr(httpx, "post", faux_post)
    assert ClientLLM([LOCAL, MODAL]).generer("q").origine == "modal"


def test_bascule_sur_une_erreur_serveur(monkeypatch):
    """Un HTTP 500 local ne doit pas non plus bloquer la démonstration."""

    def faux_post(url, **kw):
        if "local" in url:
            return httpx.Response(500, request=httpx.Request("POST", url))
        return _reponse("secours")

    monkeypatch.setattr(httpx, "post", faux_post)
    assert ClientLLM([LOCAL, MODAL]).generer("q").origine == "modal"


def test_les_deux_tombent_le_motif_de_chacun_est_donne(monkeypatch):
    """
    Si tout tombe, l'appelant doit savoir pourquoi — et l'application doit
    continuer sans modèle, le moteur juridique étant déterministe.
    """

    def faux_post(url, **kw):
        raise httpx.ConnectError("injoignable", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", faux_post)

    with pytest.raises(ModeleIndisponible) as err:
        ClientLLM([LOCAL, MODAL]).generer("q")

    message = str(err.value)
    assert "local" in message and "modal" in message, (
        "le motif de chaque hébergement doit apparaître, "
        "sinon on cherche la panne à l'aveugle"
    )


def test_fonctionne_sans_modal_configure(monkeypatch):
    """Retirer Modal doit être possible : c'est ainsi qu'on démontre le hors-ligne."""
    monkeypatch.setattr(httpx, "post", lambda url, **kw: _reponse("local seul"))
    assert ClientLLM([LOCAL]).generer("q").origine == "local"


def test_le_raisonnement_interne_de_qwen3_est_retire():
    """
    Mesuré sur le déploiement de Zied : Qwen3 émet ses hésitations entre
    <think> et </think>. Une PME ne doit jamais lire « Wait, but I should
    make sure » en réponse à une question sur son litige.
    """
    brut = "<think>Wait, but I should make sure. Let me think.</think>La conciliation évite le procès."
    assert _nettoyer(brut) == "La conciliation évite le procès."


def test_le_sondage_donne_le_motif_pas_un_simple_booleen(monkeypatch):
    """
    Un `except Exception: return False` masque la cause et fait perdre du
    temps exactement quand on n'en a pas.
    """

    def faux_get(url, **kw):
        raise httpx.ConnectError("refusée", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", faux_get)
    resultats = ClientLLM([LOCAL]).sonder()

    _, ok, motif = resultats[0]
    assert ok is False
    assert "ConnectError" in motif, "le motif exact doit remonter"


def test_ordre_de_preference_par_defaut(monkeypatch):
    """Par défaut, sans configuration, le local passe avant Modal."""
    monkeypatch.setenv("MIZAN_LLM_LOCAL", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("MIZAN_LLM_MODAL", "https://exemple.modal.run/v1")

    noms = [h.nom for h in ClientLLM().hebergements]
    assert noms == ["local", "modal"]
