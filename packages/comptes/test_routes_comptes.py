"""Tests des routes HTTP du module comptes.

Les tests de `test_comptes.py` prouvent que la logique est juste. Ceux-ci
prouvent qu'elle est bien BRANCHÉE : qu'une inscription passe par HTTP, qu'un
jeton circule dans l'en-tête `Authorization`, et qu'une route protégée refuse
pour de bon quand le rôle ne porte pas le privilège.

Le registre est remplacé par une base en mémoire via `dependency_overrides` :
lancer les tests ne doit jamais écrire dans `.donnees/comptes.db`.
"""
from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.comptes import registre, routeur
from packages.comptes import roles
from packages.comptes.registre import Registre

MOT_DE_PASSE = "Hack4Justice2026!"


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """Une application minimale portant le seul routeur des comptes.

    On ne monte PAS `api.main` : ce routeur doit pouvoir être testé sans
    dépendre du reste de la plateforme, et sans que ses tests tombent quand un
    autre module est en cours de modification.
    """
    app = FastAPI()
    app.include_router(routeur)
    memoire = Registre(":memory:")
    app.dependency_overrides[registre] = lambda: memoire
    with TestClient(app) as c:
        yield c
    memoire.fermer()


def _inscrire(client: TestClient, email: str, role: str, org: str):
    return client.post("/comptes/inscription", json={
        "email": email, "mot_de_passe": MOT_DE_PASSE,
        "role": role, "nom_organisation": org,
    })


def test_l_inscription_renvoie_les_privileges_du_role(client: TestClient) -> None:
    reponse = _inscrire(client, "adl@bensalah.tn", "huissier", "Étude Ben Salah")
    assert reponse.status_code == 201
    compte = reponse.json()["compte"]
    assert compte["role_libelle"] == "Huissier de justice"
    assert compte["role_libelle_ar"] == "عدل منفذ"
    assert set(compte["permissions"]) == {
        "view_notice_request", "issue_formal_notice", "record_service"}
    assert "3 actions" in reponse.json()["message"]


def test_le_client_ne_peut_pas_se_donner_des_privileges(client: TestClient) -> None:
    """Un champ « permissions » posté est ignoré : il n'existe pas au schéma."""
    reponse = client.post("/comptes/inscription", json={
        "email": "ahmed@menuiserie.tn", "mot_de_passe": MOT_DE_PASSE,
        "role": "msme", "nom_organisation": "Menuiserie Ahmed",
        "permissions": ["manage_tenants", "issue_formal_notice"],
    })
    assert reponse.status_code == 201
    assert "manage_tenants" not in reponse.json()["compte"]["permissions"]
    assert "issue_formal_notice" not in reponse.json()["compte"]["permissions"]


def test_un_role_inconnu_renvoie_400_avec_un_message_lisible(client: TestClient) -> None:
    reponse = _inscrire(client, "x@y.tn", "juge_supreme", "Org X")
    assert reponse.status_code == 400
    assert "n'existe pas sur Mizan" in reponse.json()["detail"]


def test_un_email_deja_pris_renvoie_400(client: TestClient) -> None:
    _inscrire(client, "ahmed@menuiserie.tn", "msme", "Menuiserie Ahmed")
    reponse = _inscrire(client, "ahmed@menuiserie.tn", "court_clerk", "Tribunal")
    assert reponse.status_code == 400
    assert "existe déjà" in reponse.json()["detail"]


def test_la_connexion_delivre_un_jeton_utilisable(client: TestClient) -> None:
    _inscrire(client, "greffe@tribunal.tn", "court_clerk", "Tribunal de Sfax")
    reponse = client.post("/comptes/connexion", json={
        "email": "greffe@tribunal.tn", "mot_de_passe": MOT_DE_PASSE})
    assert reponse.status_code == 200
    jeton = reponse.json()["jeton"]

    moi = client.get("/comptes/moi", headers={"Authorization": f"Bearer {jeton}"})
    assert moi.status_code == 200
    assert moi.json()["role"] == "court_clerk"
    assert moi.json()["organisation"] == "tribunal-de-sfax"


def test_un_mauvais_mot_de_passe_renvoie_401(client: TestClient) -> None:
    _inscrire(client, "ahmed@menuiserie.tn", "msme", "Menuiserie Ahmed")
    reponse = client.post("/comptes/connexion", json={
        "email": "ahmed@menuiserie.tn", "mot_de_passe": "FauxMotDePasse1"})
    assert reponse.status_code == 401
    # Le même message qu'une adresse inconnue : on ne dit pas qui est client.
    inconnue = client.post("/comptes/connexion", json={
        "email": "personne@nulle-part.tn", "mot_de_passe": MOT_DE_PASSE})
    assert inconnue.json()["detail"] == reponse.json()["detail"]


def test_une_route_protegee_refuse_sans_jeton(client: TestClient) -> None:
    assert client.get("/comptes/moi").status_code == 401
    assert client.get("/comptes/organisation").status_code == 401


def test_un_jeton_altere_est_refuse_par_l_api(client: TestClient) -> None:
    _inscrire(client, "ahmed@menuiserie.tn", "msme", "Menuiserie Ahmed")
    jeton = client.post("/comptes/connexion", json={
        "email": "ahmed@menuiserie.tn",
        "mot_de_passe": MOT_DE_PASSE}).json()["jeton"]
    altere = jeton[:-1] + ("A" if jeton[-1] != "A" else "B")
    reponse = client.get("/comptes/moi",
                         headers={"Authorization": f"Bearer {altere}"})
    assert reponse.status_code == 401


def test_seul_l_administrateur_liste_les_comptes_de_son_organisation(
    client: TestClient,
) -> None:
    """`manage_users` garde la route ; l'organisation vient du jeton, pas de l'URL."""
    _inscrire(client, "admin@mizan.tn", "platform_admin", "Mizan")
    _inscrire(client, "ahmed@menuiserie.tn", "msme", "Menuiserie Ahmed")

    jeton_admin = client.post("/comptes/connexion", json={
        "email": "admin@mizan.tn", "mot_de_passe": MOT_DE_PASSE}).json()["jeton"]
    jeton_ahmed = client.post("/comptes/connexion", json={
        "email": "ahmed@menuiserie.tn",
        "mot_de_passe": MOT_DE_PASSE}).json()["jeton"]

    ok = client.get("/comptes/organisation",
                    headers={"Authorization": f"Bearer {jeton_admin}"})
    assert ok.status_code == 200
    # L'administrateur voit SON organisation (Mizan), pas Menuiserie Ahmed.
    assert [c["email"] for c in ok.json()] == ["admin@mizan.tn"]

    refus = client.get("/comptes/organisation",
                       headers={"Authorization": f"Bearer {jeton_ahmed}"})
    assert refus.status_code == 403
    assert "Entreprise" in refus.json()["detail"]
    assert "administrer les comptes" in refus.json()["detail"]


def test_la_matrice_des_roles_est_publique_et_complete(client: TestClient) -> None:
    reponse = client.get("/comptes/roles")
    assert reponse.status_code == 200
    donnees = reponse.json()["roles"]
    # On compare à la matrice, pas à un nombre écrit à la main : le jour où une
    # sixième qualité est ajoutée — l'avocat l'a été — un nombre figé fait
    # échouer un test qui n'avait rien à dire sur la nouveauté, et masque les
    # vraies régressions derrière un rouge sans intérêt.
    assert [r["role"] for r in donnees] == list(roles.ROLES)
    huissier = next(r for r in donnees if r["role"] == "huissier")
    avocat = next(r for r in donnees if r["role"] == "avocat")
    assert "représenter son client en justice" in avocat["permissions_libelles"]
    assert avocat["libelle"] == "Avocat"
    assert "signifier une mise en demeure" in huissier["permissions_libelles"]
    # Les libellés sont fournis pour l'écran d'inscription : autant de libellés
    # que de privilèges, sinon l'interface afficherait des identifiants bruts.
    for r in donnees:
        assert len(r["permissions"]) == len(r["permissions_libelles"])


def test_les_messages_de_refus_sont_en_francais_correct(client: TestClient) -> None:
    """Pas de « de administrer » : les juristes du jury lisent ces phrases."""
    _inscrire(client, "ahmed@menuiserie.tn", "msme", "Menuiserie Ahmed")
    jeton = client.post("/comptes/connexion", json={
        "email": "ahmed@menuiserie.tn",
        "mot_de_passe": MOT_DE_PASSE}).json()["jeton"]
    detail = client.get("/comptes/organisation",
                        headers={"Authorization": f"Bearer {jeton}"}).json()["detail"]
    assert "de administrer" not in detail
    assert "d'administrer" in detail
    # Aucune trace technique ne doit fuiter vers l'utilisateur.
    for jargon in ("Traceback", "sqlite3", "HTTPException", "None", "scrypt"):
        assert jargon not in detail
