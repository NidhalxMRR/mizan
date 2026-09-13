"""La route qui expose la chaîne d'agents : ce qu'elle doit refuser.

Une chaîne d'agents qui produit toujours quelque chose est une chaîne qui
invente. Ces tests vérifient l'inverse de ce qu'on teste d'habitude : que la
route s'ARRÊTE, qu'elle le dise, et surtout qu'elle ne produise AUCUN article
de loi quand elle s'est arrêtée avant d'avoir lu une facture.

C'est la propriété que le jury doit pouvoir éprouver en direct : déposer un
document quelconque et constater qu'il ne sort ni montant, ni article, ni
conclusion juridique.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app

RACINE = Path(__file__).resolve().parent.parent
FACTURE = RACINE / "samples" / "facture_ahmed.pdf"
NON_FACTURE = RACINE / "samples" / "not_an_invoice_joining_instructions.pdf"

client = TestClient(app)


def _poster(chemin: Path):
    with chemin.open("rb") as f:
        return client.post(
            "/dossiers/traiter-piece",
            files={"fichier": (chemin.name, f, "application/pdf")},
        )


@pytest.mark.skipif(not FACTURE.exists(), reason="pièce d'exemple absente")
def test_facture_reelle_traverse_les_quatre_agents() -> None:
    """Sur une vraie facture, les quatre agents passent et citent le corpus."""
    r = _poster(FACTURE)
    assert r.status_code == 200
    d = r.json()

    assert d["ok"] is True
    agents = [e["agent"] for e in d["etapes"]]
    assert agents == ["lecteur", "chercheur", "moteur_juridique", "redacteur"]
    assert all(e["ok"] for e in d["etapes"])

    # Le fond : des articles réellement trouvés, et une explication rédigée.
    assert len(d["articles"]) > 0
    assert d["explication"].strip()

    # L'empreinte est calculée sur le contenu, pas sur le nom.
    assert len(d["sha256"]) == 64


@pytest.mark.skipif(not NON_FACTURE.exists(), reason="pièce d'exemple absente")
def test_un_document_qui_nest_pas_une_facture_ne_produit_aucun_article() -> None:
    """La garantie centrale : pas de facture lue, donc pas de droit produit."""
    r = _poster(NON_FACTURE)
    assert r.status_code == 200
    d = r.json()

    assert d["ok"] is False
    assert "lecteur" in d["arret"]

    # Rien de juridique ne doit sortir d'un document non qualifié.
    assert d["articles"] == []
    assert not d.get("evaluation")

    # Et l'explication doit DIRE pourquoi, sans jargon.
    assert "n'a pas traité" in d["explication"]


def test_fichier_vide_refuse() -> None:
    """Un fichier vide est une erreur du client, pas une créance de zéro."""
    r = client.post(
        "/dossiers/traiter-piece",
        files={"fichier": ("vide.pdf", b"", "application/pdf")},
    )
    assert r.status_code == 400


def test_le_chemin_temporaire_du_serveur_ne_fuit_jamais() -> None:
    """La réponse nomme la pièce déposée, jamais le fichier temporaire.

    Exposer « /tmp/tmpXXXX.pdf » dans une réponse publique renseigne un
    attaquant sur le système de fichiers du serveur, et n'apprend rien à
    l'utilisateur.
    """
    if not FACTURE.exists():
        pytest.skip("pièce d'exemple absente")
    d = _poster(FACTURE).json()
    assert d["piece"] == FACTURE.name
    assert "/tmp/" not in d["piece"]
