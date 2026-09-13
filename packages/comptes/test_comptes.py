"""Tests hostiles du module comptes.

Ces tests ne cherchent pas à confirmer que le code marche : ils cherchent à le
faire tomber. Chacun reproduit une attaque ou une bévue plausible — un rôle
inventé dans le formulaire, un jeton dont on a changé une lettre, un compte qui
demande le dossier d'une autre entreprise.

La règle de lecture : si un test disparaît, la protection correspondante n'est
plus garantie, même si le code a l'air inchangé.
"""
from __future__ import annotations

import re
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from packages.comptes import empreintes, jetons, registre, roles
from packages.comptes.jetons import JetonInvalide, creer_jeton, lire_jeton
from packages.comptes.registre import (
    AccesRefuse,
    ConnexionRefusee,
    InscriptionRefusee,
    Registre,
    verifier_acces_organisation,
)
from packages.comptes.roles import RoleInconnu

RACINE = Path(__file__).resolve().parents[2]

BON_MOT_DE_PASSE = "Menuiserie2026!"


@pytest.fixture()
def reg() -> Iterator[Registre]:
    """Un registre neuf en mémoire : aucun test n'hérite de l'état d'un autre."""
    with Registre(":memory:") as r:
        yield r


@pytest.fixture()
def reg_fichier(tmp_path: Path) -> Iterator[Registre]:
    """Un registre sur un vrai fichier, quand le test doit relire les octets."""
    with Registre(tmp_path / "comptes.db") as r:
        yield r


# ---------------------------------------------------------------------------
# Inscription : ce qui doit être refusé
# ---------------------------------------------------------------------------

def test_un_role_inconnu_est_refuse(reg: Registre) -> None:
    """Un rôle inventé ne crée pas un compte sans privilèges : il ne crée rien."""
    with pytest.raises(InscriptionRefusee) as refus:
        reg.inscrire("ahmed@menuiserie.tn", BON_MOT_DE_PASSE,
                     "juge_supreme", "Menuiserie Ahmed")
    assert "juge_supreme" in str(refus.value)
    # Le message nomme les rôles possibles, en français : il est lisible par
    # quelqu'un qui n'a jamais vu le code.
    assert "Huissier de justice" in str(refus.value)
    assert reg.comptes_de_l_organisation("menuiserie-ahmed") == []


@pytest.mark.parametrize("role", roles.ROLES)
def test_chaque_role_declare_recoit_bien_ses_privileges(reg: Registre, role: str) -> None:
    """La promesse centrale : le rôle apporte ses privilèges à la création."""
    compte = reg.inscrire(f"{role}@exemple.tn", BON_MOT_DE_PASSE, role, "Org Test")
    assert compte.permissions == roles.PERMISSIONS[role]
    assert compte.permissions, "un rôle sans aucun privilège serait un compte muet"


def test_deux_inscriptions_avec_le_meme_email_la_seconde_est_refusee(reg: Registre) -> None:
    reg.inscrire("ahmed@menuiserie.tn", BON_MOT_DE_PASSE, "msme", "Menuiserie Ahmed")
    with pytest.raises(InscriptionRefusee) as refus:
        reg.inscrire("ahmed@menuiserie.tn", "UnAutreMotDePasse1", "court_clerk",
                     "Tribunal de Sfax")
    assert "existe déjà" in str(refus.value)
    # Et surtout : le second essai n'a pas écrasé le rôle du premier.
    _, compte = reg.connexion("ahmed@menuiserie.tn", BON_MOT_DE_PASSE)
    assert compte.role == "msme"


def test_la_casse_de_l_email_ne_permet_pas_de_doubler_un_compte(reg: Registre) -> None:
    """« Ahmed@X.tn » et « ahmed@x.tn » sont la même personne."""
    reg.inscrire("ahmed@menuiserie.tn", BON_MOT_DE_PASSE, "msme", "Menuiserie Ahmed")
    with pytest.raises(InscriptionRefusee):
        reg.inscrire("  AHMED@Menuiserie.TN ", BON_MOT_DE_PASSE, "msme",
                     "Menuiserie Ahmed")


@pytest.mark.parametrize("mauvais", ["", "   ", "court", "1234567"])
def test_un_mot_de_passe_vide_ou_trop_court_est_refuse(reg: Registre, mauvais: str) -> None:
    with pytest.raises(InscriptionRefusee) as refus:
        reg.inscrire("ahmed@menuiserie.tn", mauvais, "msme", "Menuiserie Ahmed")
    assert "mot de passe" in str(refus.value).lower()


def test_une_adresse_qui_n_en_est_pas_une_est_refusee(reg: Registre) -> None:
    with pytest.raises(InscriptionRefusee):
        reg.inscrire("ahmed-chez-moi", BON_MOT_DE_PASSE, "msme", "Menuiserie Ahmed")


def test_une_organisation_vide_est_refusee(reg: Registre) -> None:
    """Sans organisation, le cloisonnement n'a pas de frontière à tenir."""
    with pytest.raises(InscriptionRefusee) as refus:
        reg.inscrire("ahmed@menuiserie.tn", BON_MOT_DE_PASSE, "msme", "   ")
    assert "organisation" in str(refus.value).lower()


# ---------------------------------------------------------------------------
# Mots de passe : ce qui est écrit sur le disque
# ---------------------------------------------------------------------------

def test_le_mot_de_passe_n_apparait_nulle_part_en_clair_dans_la_base(
    reg_fichier: Registre,
) -> None:
    """On relit le fichier SQLite octet par octet, pas la colonne.

    Lire la colonne prouverait seulement que la colonne est propre. Lire le
    fichier attrape aussi ce qui traîne dans le journal d'écriture et dans les
    pages libérées — là où une donnée « supprimée » survit souvent.
    """
    secret = "MotDePasseTresParticulier2026!"
    reg_fichier.inscrire("ahmed@menuiserie.tn", secret, "msme", "Menuiserie Ahmed")

    chemin = Path(str(reg_fichier.chemin))
    octets = chemin.read_bytes()
    for voisin in chemin.parent.glob(chemin.name + "-*"):  # -wal, -journal, -shm
        octets += voisin.read_bytes()

    assert secret.encode("utf-8") not in octets
    assert secret.encode("utf-16-le") not in octets
    # Contre-épreuve : l'adresse, elle, EST bien dans le fichier. Sans cela, le
    # test passerait aussi sur une base vide et ne prouverait rien.
    assert b"ahmed@menuiserie.tn" in octets


def test_deux_comptes_avec_le_meme_mot_de_passe_ont_des_empreintes_differentes(
    reg_fichier: Registre,
) -> None:
    """C'est le sel aléatoire qui est testé ici, et rien d'autre."""
    reg_fichier.inscrire("ahmed@menuiserie.tn", BON_MOT_DE_PASSE, "msme", "Org A")
    reg_fichier.inscrire("sonia@zitouna.tn", BON_MOT_DE_PASSE, "msme", "Org B")

    cx = sqlite3.connect(str(reg_fichier.chemin))
    empreintes_lues = [l[0] for l in cx.execute("SELECT empreinte FROM comptes")]
    cx.close()

    assert len(empreintes_lues) == 2
    assert empreintes_lues[0] != empreintes_lues[1]
    # Et les deux se vérifient quand même avec le même mot de passe.
    assert all(empreintes.correspond(BON_MOT_DE_PASSE, e) for e in empreintes_lues)


def test_l_empreinte_porte_ses_parametres_et_un_sel_de_taille_suffisante() -> None:
    scelle = empreintes.sceller(BON_MOT_DE_PASSE)
    params = empreintes.relire_parametres(scelle)
    assert params["algorithme"] == "scrypt"
    assert int(params["n"]) >= 1 << 14
    assert int(params["octets_de_sel"]) >= 16


def test_un_mot_de_passe_faux_ne_correspond_pas() -> None:
    scelle = empreintes.sceller(BON_MOT_DE_PASSE)
    assert empreintes.correspond(BON_MOT_DE_PASSE, scelle)
    assert not empreintes.correspond(BON_MOT_DE_PASSE + "x", scelle)
    assert not empreintes.correspond("", scelle)
    # Une empreinte abîmée répond « non », elle ne fait pas tomber le serveur.
    assert not empreintes.correspond(BON_MOT_DE_PASSE, "n'importe quoi")


# ---------------------------------------------------------------------------
# Connexion
# ---------------------------------------------------------------------------

def test_la_connexion_delivre_un_jeton_portant_role_organisation_et_privileges(
    reg: Registre,
) -> None:
    reg.inscrire("greffe@tribunal-sfax.tn", BON_MOT_DE_PASSE, "court_clerk",
                 "Tribunal de Commerce de Sfax")
    jeton, compte = reg.connexion("greffe@tribunal-sfax.tn", BON_MOT_DE_PASSE)

    session = lire_jeton(jeton)
    assert session.compte_id == compte.compte_id
    assert session.organisation == "tribunal-de-commerce-de-sfax"
    assert session.role == "court_clerk"
    assert set(session.permissions) == set(roles.PERMISSIONS["court_clerk"])


def test_le_refus_de_connexion_ne_dit_pas_si_l_adresse_existe(reg: Registre) -> None:
    """Distinguer les deux refus dirait qui est client de Mizan, donc en litige."""
    reg.inscrire("ahmed@menuiserie.tn", BON_MOT_DE_PASSE, "msme", "Menuiserie Ahmed")

    with pytest.raises(ConnexionRefusee) as adresse_inconnue:
        reg.connexion("personne@nulle-part.tn", BON_MOT_DE_PASSE)
    with pytest.raises(ConnexionRefusee) as mot_de_passe_faux:
        reg.connexion("ahmed@menuiserie.tn", "MauvaisMotDePasse1")

    assert str(adresse_inconnue.value) == str(mot_de_passe_faux.value)


# ---------------------------------------------------------------------------
# Jetons : les quatre attaques
# ---------------------------------------------------------------------------

def test_un_jeton_dont_on_a_modifie_un_seul_caractere_est_refuse() -> None:
    jeton = creer_jeton("cpt-1", "a@b.tn", "org-a", "msme")
    corps, signature = jeton.split(".")

    # Un caractère changé dans la charge…
    altere = corps[:-1] + ("A" if corps[-1] != "A" else "B") + "." + signature
    with pytest.raises(JetonInvalide):
        lire_jeton(altere)

    # …et un caractère changé dans la signature.
    altere = corps + "." + signature[:-1] + ("A" if signature[-1] != "A" else "B")
    with pytest.raises(JetonInvalide):
        lire_jeton(altere)


def test_un_jeton_dont_on_a_ajoute_un_privilege_est_refuse() -> None:
    """L'attaque qui compte vraiment : se promouvoir huissier depuis le client."""
    import base64
    import json

    jeton = creer_jeton("cpt-1", "a@b.tn", "org-a", "msme")
    corps, _ = jeton.split(".")
    charge = json.loads(base64.urlsafe_b64decode(corps + "=" * (-len(corps) % 4)))
    charge["prm"].append("issue_formal_notice")
    charge["rol"] = "huissier"
    nouveau = base64.urlsafe_b64encode(
        json.dumps(charge, sort_keys=True, separators=(",", ":")).encode()
    ).decode().rstrip("=")

    with pytest.raises(JetonInvalide):
        lire_jeton(nouveau + "." + jeton.split(".")[1])


def test_un_jeton_expire_est_refuse() -> None:
    passe = int(time.time()) - 100_000
    jeton = creer_jeton("cpt-1", "a@b.tn", "org-a", "msme",
                        duree_secondes=60, maintenant=passe)
    with pytest.raises(JetonInvalide) as refus:
        lire_jeton(jeton)
    assert "expiré" in str(refus.value)
    # Le même jeton était valide à l'instant de son émission.
    assert lire_jeton(jeton, maintenant=passe + 10).role == "msme"


def test_un_jeton_signe_avec_une_autre_cle_est_refuse(monkeypatch) -> None:
    monkeypatch.setenv("MIZAN_SECRET", "la-cle-de-quelqu-un-d-autre")
    etranger = creer_jeton("cpt-1", "a@b.tn", "org-a", "huissier")
    monkeypatch.setenv("MIZAN_SECRET", "la-vraie-cle-de-mizan")
    with pytest.raises(JetonInvalide):
        lire_jeton(etranger)


@pytest.mark.parametrize("informe", ["", "sans-point", "a.b.c", "....", "   "])
def test_un_jeton_informe_est_refuse(informe: str) -> None:
    with pytest.raises(JetonInvalide):
        lire_jeton(informe)


def test_la_cle_de_developpement_est_signalee_comme_telle(monkeypatch) -> None:
    monkeypatch.delenv("MIZAN_SECRET", raising=False)
    assert jetons.signature_de_developpement() is True
    assert "NON-SECRETE" in jetons.CLE_DEVELOPPEMENT
    monkeypatch.setenv("MIZAN_SECRET", "une-vraie-cle")
    assert jetons.signature_de_developpement() is False


def test_le_jeton_ignore_les_privileges_qu_on_voudrait_lui_souffler() -> None:
    """`creer_jeton` relit la matrice : il n'accepte pas de liste fournie."""
    jeton = creer_jeton("cpt-1", "a@b.tn", "org-a", "msme")
    session = lire_jeton(jeton)
    assert "issue_formal_notice" not in session.permissions
    assert set(session.permissions) == set(roles.PERMISSIONS["msme"])


# ---------------------------------------------------------------------------
# Privilèges : qui peut quoi, et surtout qui ne peut pas
# ---------------------------------------------------------------------------

def test_un_msme_n_a_pas_le_privilege_de_signifier(reg: Registre) -> None:
    """CPCC art. 5 et 60 : seul l'huissier signifie. La matrice le dit aussi."""
    reg.inscrire("ahmed@menuiserie.tn", BON_MOT_DE_PASSE, "msme", "Menuiserie Ahmed")
    jeton, _ = reg.connexion("ahmed@menuiserie.tn", BON_MOT_DE_PASSE)
    session = lire_jeton(jeton)

    assert not session.peut("issue_formal_notice")
    # Mais il peut DEMANDER l'acte : générer n'est pas signifier.
    assert session.peut("request_notice")


def test_seul_le_huissier_porte_issue_formal_notice() -> None:
    porteurs = [r for r in roles.ROLES if roles.peut(r, "issue_formal_notice")]
    assert porteurs == ["huissier"]


def test_un_huissier_n_a_pas_manage_tenants(reg: Registre) -> None:
    reg.inscrire("adl@huissier-sfax.tn", BON_MOT_DE_PASSE, "huissier",
                 "Étude Ben Salah")
    jeton, _ = reg.connexion("adl@huissier-sfax.tn", BON_MOT_DE_PASSE)
    session = lire_jeton(jeton)

    assert not session.peut("manage_tenants")
    assert not session.peut("approve_dossier")
    assert session.peut("record_service")


def test_aucun_role_sauf_l_administrateur_ne_gere_les_organisations() -> None:
    porteurs = [r for r in roles.ROLES if roles.peut(r, "manage_tenants")]
    assert porteurs == ["platform_admin"]


def test_un_role_inconnu_ne_peut_rien(  ) -> None:
    """Le refus par défaut : une donnée abîmée n'ouvre aucune porte."""
    assert roles.peut("juge_supreme", "view_all") is False
    assert roles.peut("", "upload_evidence") is False
    with pytest.raises(RoleInconnu):
        roles.permissions_du_role("juge_supreme")


def test_les_privileges_ne_se_chevauchent_pas_entre_les_deux_signataires() -> None:
    """Signer le PV appartient au professionnel, pas au greffier ni à la PME."""
    porteurs = [r for r in roles.ROLES if roles.peut(r, "sign_settlement")]
    assert porteurs == ["accredited_pro"]
    porteurs = [r for r in roles.ROLES if roles.peut(r, "approve_dossier")]
    assert porteurs == ["court_clerk"]


# ---------------------------------------------------------------------------
# L'avocat : ce qui le distingue des cinq autres qualités
# ---------------------------------------------------------------------------

def test_l_avocat_existe_et_porte_ses_libelles_francais_et_arabe() -> None:
    """Un rôle sans libellé afficherait son identifiant technique à l'écran."""
    assert "avocat" in roles.ROLES
    assert roles.LIBELLES["avocat"] == "Avocat"
    assert roles.LIBELLES_AR["avocat"] == "محام"


def test_seul_l_avocat_represente_son_client_et_signe_les_ecritures() -> None:
    """CDPF art. 57 et 35 : la représentation et la signature sont à lui seul.

    Art. 57 : « تكون إنابة المحامي وجوبية إذا تجاوز مبلغ الأداء الموظف إجباريا
    أو المبلغ المطلوب استرجاعه خمسة وعشرين ألف دينار » — au-delà de 25 000
    dinars la représentation est obligatoire. Art. 35 : la requête et les
    mémoires en réponse sont signés par un avocat auprès de la cassation ou de
    l'appel. Si une autre qualité venait à porter ces deux clés, la plateforme
    promettrait une recevabilité que la loi refuse.
    """
    assert [r for r in roles.ROLES if roles.peut(r, "represent_client")] == ["avocat"]
    assert [r for r in roles.ROLES if roles.peut(r, "sign_pleading")] == ["avocat"]
    assert [r for r in roles.ROLES if roles.peut(r, "draft_pleading")] == ["avocat"]


def test_l_avocat_ne_signifie_pas_et_ne_concilie_pas() -> None:
    """Les deux confusions à écarter : l'huissier et le tiers neutre.

    L'avocat plaide pour une partie. Il n'a donc ni le monopole de la
    signification (CPCC art. 5 et 60), ni l'office du conciliateur — on ne
    concilie pas deux parties dont on défend l'une.
    """
    assert not roles.peut("avocat", "issue_formal_notice")
    assert not roles.peut("avocat", "record_service")
    assert not roles.peut("avocat", "conduct_ecma")
    assert not roles.peut("avocat", "sign_settlement")
    assert not roles.peut("avocat", "approve_dossier")
    assert not roles.peut("avocat", "manage_users")


def test_l_avocat_n_est_pas_une_copie_du_professionnel_accredite() -> None:
    """Deux listes identiques signaleraient qu'on a recopié au lieu de penser."""
    assert roles.PERMISSIONS["avocat"] != roles.PERMISSIONS["accredited_pro"]
    propres = set(roles.PERMISSIONS["avocat"]) - set(roles.PERMISSIONS["accredited_pro"])
    assert propres == {"represent_client", "draft_pleading", "sign_pleading"}


def test_un_avocat_inscrit_recoit_bien_ses_privileges_et_aucun_autre(
    reg: Registre,
) -> None:
    """Le parcours complet : inscription, connexion, jeton, privilèges."""
    reg.inscrire("cabinet@avocat-tunis.tn", BON_MOT_DE_PASSE, "avocat",
                 "Cabinet d'avocats de Tunis")
    jeton, compte = reg.connexion("cabinet@avocat-tunis.tn", BON_MOT_DE_PASSE)
    session = lire_jeton(jeton)

    assert compte.libelle_role == "Avocat"
    assert session.role == "avocat"
    assert session.peut("represent_client")
    assert session.peut("sign_pleading")
    assert not session.peut("issue_formal_notice")
    assert set(session.permissions) == set(roles.PERMISSIONS["avocat"])


def test_chaque_privilege_de_chaque_role_porte_un_libelle_francais() -> None:
    """Une clé sans traduction atteindrait l'écran en anglais technique.

    Le dictionnaire TypeScript est vérifié par le compilateur ; celui-ci ne
    l'est par rien, sauf par ce test. Un privilège nouveau oublié ici
    s'afficherait « represent_client » dans un message de refus adressé à un
    juriste.
    """
    for role in roles.ROLES:
        for permission in roles.PERMISSIONS[role]:
            libelle = roles.libelle_permission(permission)
            assert libelle != permission, (
                f"le privilège « {permission} » du rôle « {role} » n'a pas de "
                f"libellé français dans LIBELLES_PERMISSIONS"
            )


# ---------------------------------------------------------------------------
# Cloisonnement multi-organisations
# ---------------------------------------------------------------------------

def test_un_compte_de_l_organisation_a_ne_peut_pas_agir_pour_l_organisation_b(
    reg: Registre,
) -> None:
    """Les deux parties d'un litige peuvent être clientes de Mizan en même temps."""
    reg.inscrire("ahmed@menuiserie.tn", BON_MOT_DE_PASSE, "msme", "Menuiserie Ahmed")
    reg.inscrire("sonia@zitouna.tn", BON_MOT_DE_PASSE, "msme", "Société Zitouna")

    jeton_a, _ = reg.connexion("ahmed@menuiserie.tn", BON_MOT_DE_PASSE)
    session_a = lire_jeton(jeton_a)

    # Chez lui : autorisé.
    verifier_acces_organisation(session_a, "menuiserie-ahmed")
    # Chez l'autre : refusé, même avec le bon privilège métier.
    assert session_a.peut("view_own_case")
    with pytest.raises(AccesRefuse) as refus:
        verifier_acces_organisation(session_a, "societe-zitouna")
    # Le refus ne confirme pas que « Société Zitouna » est cliente de Mizan.
    assert "zitouna" not in str(refus.value).lower()


def test_la_liste_des_comptes_est_cloisonnee_par_organisation(reg: Registre) -> None:
    reg.inscrire("ahmed@menuiserie.tn", BON_MOT_DE_PASSE, "msme", "Menuiserie Ahmed")
    reg.inscrire("fatma@menuiserie.tn", BON_MOT_DE_PASSE, "msme", "Menuiserie Ahmed")
    reg.inscrire("sonia@zitouna.tn", BON_MOT_DE_PASSE, "msme", "Société Zitouna")

    chez_ahmed = reg.comptes_de_l_organisation("menuiserie-ahmed")
    assert {c.email for c in chez_ahmed} == {"ahmed@menuiserie.tn",
                                            "fatma@menuiserie.tn"}
    assert len(reg.comptes_de_l_organisation("societe-zitouna")) == 1
    assert reg.comptes_de_l_organisation("organisation-inexistante") == []


def test_deux_ecritures_du_meme_nom_rejoignent_la_meme_organisation(reg: Registre) -> None:
    """Deux collègues qui tapent le nom différemment doivent se retrouver ensemble."""
    a = reg.inscrire("ahmed@menuiserie.tn", BON_MOT_DE_PASSE, "msme",
                     "Menuiserie Ahmed")
    b = reg.inscrire("fatma@menuiserie.tn", BON_MOT_DE_PASSE, "msme",
                     "  menuiserie   ahmed  ")
    assert a.organisation == b.organisation


def test_un_meme_email_ne_peut_pas_exister_dans_deux_organisations(reg: Registre) -> None:
    """L'adresse est l'identifiant global : elle ne se dédouble pas par tenant."""
    reg.inscrire("ahmed@menuiserie.tn", BON_MOT_DE_PASSE, "msme", "Menuiserie Ahmed")
    with pytest.raises(InscriptionRefusee):
        reg.inscrire("ahmed@menuiserie.tn", BON_MOT_DE_PASSE, "msme",
                     "Société Zitouna")


# ---------------------------------------------------------------------------
# exige() : la porte des routes
# ---------------------------------------------------------------------------

def test_exige_laisse_passer_la_bonne_permission_et_refuse_la_mauvaise() -> None:
    from fastapi import HTTPException

    from packages.comptes.garde import exige

    session = lire_jeton(creer_jeton("cpt-1", "adl@h.tn", "etude-ben-salah",
                                     "huissier", nom_organisation="Étude Ben Salah"))

    autorise = exige("issue_formal_notice")
    assert autorise(session) is session

    refuse = exige("manage_tenants")
    with pytest.raises(HTTPException) as refus:
        refuse(session)
    assert refus.value.status_code == 403
    # Le message est écrit pour un juriste : le rôle et l'action, en français.
    assert "Huissier de justice" in refus.value.detail
    assert "d'administrer les organisations" in refus.value.detail


def test_verifier_jeton_refuse_un_entete_absent_ou_malforme() -> None:
    from fastapi import HTTPException

    from packages.comptes.garde import verifier_jeton

    for entete in (None, "", "Basic abc", "Bearer", "n-importe-quoi"):
        with pytest.raises(HTTPException) as refus:
            verifier_jeton(entete)
        assert refus.value.status_code == 401


def test_verifier_jeton_accepte_un_entete_bearer_valide() -> None:
    from packages.comptes.garde import verifier_jeton

    jeton = creer_jeton("cpt-1", "a@b.tn", "org-a", "court_clerk")
    session = verifier_jeton(f"Bearer {jeton}")
    assert session.role == "court_clerk"


def test_exige_organisation_refuse_une_organisation_etrangere() -> None:
    from fastapi import HTTPException

    from packages.comptes.garde import exige_organisation

    session = lire_jeton(creer_jeton("cpt-1", "a@b.tn", "org-a", "msme"))
    assert exige_organisation(session, "org-a") is session
    with pytest.raises(HTTPException) as refus:
        exige_organisation(session, "org-b")
    assert refus.value.status_code == 403


# ---------------------------------------------------------------------------
# La matrice serveur et la matrice navigateur ne doivent jamais diverger
# ---------------------------------------------------------------------------

def test_la_matrice_serveur_est_identique_a_celle_du_navigateur() -> None:
    """Relit `web/lib/auth.ts` et compare, rôle par rôle.

    Une divergence serait une faille silencieuse : l'écran masquerait un bouton
    que le serveur autorise encore, ou proposerait une action que le serveur
    refuse. Ce test échoue avant que quiconque ne s'en aperçoive en démonstration.
    """
    source = (RACINE / "web" / "lib" / "auth.ts").read_text(encoding="utf-8")
    bloc = source.split("export const permissions = {", 1)[1]
    bloc = bloc.split("} satisfies", 1)[0]

    depuis_le_navigateur: dict[str, list[str]] = {}
    role_courant: str | None = None
    for ligne in bloc.splitlines():
        nu = ligne.split("//", 1)[0].strip()
        debut = re.match(r"^(\w+)\s*:\s*\[", nu)
        if debut:
            role_courant = debut.group(1)
            depuis_le_navigateur[role_courant] = []
            nu = nu[debut.end():]
        if role_courant:
            depuis_le_navigateur[role_courant].extend(re.findall(r"'([^']+)'", nu))
        if nu.startswith("]"):
            role_courant = None

    assert set(depuis_le_navigateur) == set(roles.PERMISSIONS), (
        "les rôles du navigateur et du serveur ne sont plus les mêmes"
    )
    for role, privileges in depuis_le_navigateur.items():
        assert list(roles.PERMISSIONS[role]) == privileges, (
            f"le rôle « {role} » diverge entre web/lib/auth.ts et roles.py"
        )


def _libelles_du_navigateur(nom_de_la_table: str) -> dict[str, str]:
    """Relit une table de libellés dans `web/lib/auth.ts`.

    Même lecture naïve que pour la matrice : on isole le bloc entre l'ouverture
    de l'objet et son accolade fermante, puis on ramasse les paires. C'est
    suffisant parce que le fichier est écrit à la main, avec une paire par
    ligne, et c'est préférable à l'exécution d'un interpréteur TypeScript
    depuis la suite Python.
    """
    source = (RACINE / "web" / "lib" / "auth.ts").read_text(encoding="utf-8")
    bloc = source.split(f"export const {nom_de_la_table}: Record<Role, string> = {{", 1)[1]
    bloc = bloc.split("};", 1)[0]

    lus: dict[str, str] = {}
    for ligne in bloc.splitlines():
        paire = re.match(r"^\s*(\w+)\s*:\s*'([^']*)'\s*,\s*$", ligne)
        if paire:
            lus[paire.group(1)] = paire.group(2)
    return lus


def test_les_libelles_francais_sont_identiques_des_deux_cotes() -> None:
    """Un rôle nommé différemment ici et là donne deux produits, pas un.

    Le test de la matrice ci-dessus ne voit que les privilèges : on pouvait
    ajouter une qualité des deux côtés et n'écrire son nom français que d'un
    seul, auquel cas l'écran afficherait « avocat » — l'identifiant technique —
    là où le serveur dit « Avocat ». C'est exactement le jargon que la
    plateforme s'interdit de montrer à un juriste.
    """
    assert _libelles_du_navigateur("roleLabels") == roles.LIBELLES


def test_les_libelles_arabes_sont_identiques_des_deux_cotes() -> None:
    """Le nom officiel de la qualité est une donnée juridique, pas un ornement."""
    assert _libelles_du_navigateur("roleLabelsAr") == roles.LIBELLES_AR


def test_le_fichier_de_base_par_defaut_est_bien_hors_du_code_source() -> None:
    """Les données d'exploitation ne vivent pas dans `packages/`."""
    assert registre.BASE_PAR_DEFAUT.name == "comptes.db"
    assert registre.BASE_PAR_DEFAUT.parent.name == ".donnees"
