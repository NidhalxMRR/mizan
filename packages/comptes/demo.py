"""
Démonstration en ligne de commande : les six qualités, de l'inscription au refus.

    ./.venv/bin/python -m packages.comptes.demo

Inscrit les six qualités, connecte chacune, puis montre ce que chacune peut et ne
peut pas faire. La dernière section met en scène le cloisonnement : deux
entreprises en litige, chacune cliente de Mizan, et l'impossibilité pour l'une
de lire le dossier de l'autre.

Rien n'est simulé : les comptes sont réellement créés, les mots de passe
réellement scellés, les jetons réellement signés et vérifiés.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from packages.comptes import roles
from packages.comptes.garde import exige
from packages.comptes.jetons import JetonInvalide, lire_jeton
from packages.comptes.registre import (
    AccesRefuse,
    InscriptionRefusee,
    Registre,
    verifier_acces_organisation,
)

# Le scénario du brief : le litige d'Ahmed, menuisier à Sfax.
ACTEURS = [
    ("admin@mizan.tn", "platform_admin", "Mizan"),
    ("ahmed@menuiserie-sfax.tn", "msme", "Menuiserie Ahmed"),
    ("maitre@barreau-sfax.tn", "avocat", "Cabinet Maître Trabelsi"),
    ("wassila@mediation.tn", "accredited_pro", "Cabinet Wassila Médiation"),
    ("greffe@tribunal-sfax.tn", "court_clerk", "Tribunal de Commerce de Sfax"),
    ("adl@bensalah.tn", "huissier", "Étude Ben Salah"),
]

MOT_DE_PASSE = "Hack4Justice2026!"


def _titre(texte: str) -> None:
    print()
    print(texte)
    print("=" * len(texte))


def principal() -> None:
    """Déroule la démonstration de bout en bout."""
    # Un fichier temporaire : la démonstration ne pollue pas la base réelle,
    # mais elle écrit bien sur un disque, pas dans un dictionnaire.
    dossier = Path(tempfile.mkdtemp(prefix="mizan-demo-"))
    with Registre(dossier / "comptes.db") as reg:
        _inscriptions(reg)
        sessions = _connexions(reg)
        _privileges(sessions)
        _la_porte(sessions)
        _cloisonnement(reg)
        _refus(reg)
        _le_disque(reg)


def _inscriptions(reg: Registre) -> None:
    _titre("1. INSCRIPTION — LE RÔLE APPORTE SES PRIVILÈGES")
    print("Aucun privilège n'est attribué à la main : le rôle choisi les porte.")
    print()
    for email, role, organisation in ACTEURS:
        compte = reg.inscrire(email, MOT_DE_PASSE, role, organisation)
        print(f"  {compte.libelle_role:<25} {email}")
        print(f"  {'':<25} organisation : {compte.organisation}")
        print(f"  {'':<25} privilèges reçus d'office : "
              f"{len(compte.permissions)}")
        for p in compte.permissions:
            print(f"  {'':<27}· {roles.libelle_permission(p)}")
        print()


def _connexions(reg: Registre) -> dict[str, object]:
    _titre("2. CONNEXION — UN JETON SIGNÉ PAR ACTEUR")
    sessions = {}
    for email, role, _ in ACTEURS:
        jeton, compte = reg.connexion(email, MOT_DE_PASSE)
        session = lire_jeton(jeton)
        sessions[role] = session
        print(f"  {compte.libelle_role:<25} jeton {jeton[:28]}… "
              f"({len(jeton)} caractères)")
        print(f"  {'':<25} vérifié : rôle {session.role}, "
              f"organisation {session.organisation}, "
              f"{len(session.permissions)} privilèges")
    return sessions


def _privileges(sessions: dict) -> None:
    _titre("3. QUI PEUT QUOI — LA MATRICE À L'ŒUVRE")
    epreuves = [
        ("issue_formal_notice", "signifier une mise en demeure"),
        ("approve_dossier", "déclarer un dossier recevable"),
        ("sign_settlement", "signer le procès-verbal de conciliation"),
        # L'épreuve qui sépare l'avocat du médiateur : l'un représente une
        # partie, l'autre est le tiers neutre des deux. Sans cette ligne, la
        # colonne « Avocat » ne se distinguerait pas à l'œil de sa voisine.
        ("represent_client", "représenter son client en justice"),
        ("sign_pleading", "signer la requête et les mémoires"),
        ("manage_tenants", "administrer les organisations"),
        ("upload_evidence", "déposer des pièces"),
    ]
    largeur = max(len(l) for _, l in epreuves)
    entete = " " * (largeur + 4) + "".join(
        f"{roles.LIBELLES[r][:11]:<13}" for _, r, _ in ACTEURS
    )
    print(entete)
    for permission, libelle in epreuves:
        ligne = f"  {libelle:<{largeur}}  "
        for _, role, _ in ACTEURS:
            ligne += f"{'OUI' if sessions[role].peut(permission) else 'non':<13}"
        print(ligne)
    print()
    print("  Lecture : seul l'huissier signifie (CPCC art. 5 et 60). La PME")
    print("  peut DEMANDER l'acte, jamais le signifier. Générer n'est pas")
    print("  signifier, et la matrice le dit aussi côté serveur.")
    print()
    print("  Seul l'avocat représente et signe les écritures (CDPF art. 35,")
    print("  57 et 19) : le médiateur accrédité est un tiers neutre, il ne")
    print("  représente personne, et l'huissier signifie sans plaider.")


def _la_porte(sessions: dict) -> None:
    _titre("4. exige() — LA PORTE POSÉE SUR LES ROUTES")
    from fastapi import HTTPException

    porte = exige("issue_formal_notice")

    session = sessions["huissier"]
    porte(session)
    print("  L'huissier demande à signifier     → autorisé")

    session = sessions["msme"]
    try:
        porte(session)
        print("  L'entreprise demande à signifier   → AUTORISÉ (anomalie !)")
    except HTTPException as refus:
        print(f"  L'entreprise demande à signifier   → refusé ({refus.status_code})")
        print(f"     « {refus.detail} »")

    try:
        exige("manage_tenants")(sessions["huissier"])
    except HTTPException as refus:
        print(f"  L'huissier veut administrer        → refusé ({refus.status_code})")
        print(f"     « {refus.detail} »")


def _cloisonnement(reg: Registre) -> None:
    _titre("5. CLOISONNEMENT — DEUX ENTREPRISES, DEUX MONDES")
    reg.inscrire("sonia@zitouna.tn", MOT_DE_PASSE, "msme", "Société Zitouna")
    print("  Les deux parties du litige sont clientes de Mizan :")
    print("    · Menuiserie Ahmed (le créancier)")
    print("    · Société Zitouna  (le débiteur)")
    print()

    jeton, _ = reg.connexion("ahmed@menuiserie-sfax.tn", MOT_DE_PASSE)
    ahmed = lire_jeton(jeton)

    verifier_acces_organisation(ahmed, "menuiserie-ahmed")
    print("  Ahmed consulte son propre dossier   → autorisé")
    try:
        verifier_acces_organisation(ahmed, "societe-zitouna")
        print("  Ahmed consulte le dossier adverse   → AUTORISÉ (anomalie !)")
    except AccesRefuse as refus:
        print("  Ahmed consulte le dossier adverse   → refusé")
        print(f"     « {refus} »")
    print()
    print(f"  Comptes visibles par Ahmed : "
          f"{len(reg.comptes_de_l_organisation(ahmed.organisation))} "
          f"(ceux de son organisation)")
    print("  Le refus ne confirme même pas que « Société Zitouna » est cliente :")
    print("  le dire apprendrait à Ahmed que son adversaire est sur Mizan.")


def _refus(reg: Registre) -> None:
    _titre("6. CE QUE MIZAN REFUSE, ET COMMENT ELLE LE DIT")
    essais = [
        ("Rôle inventé dans le formulaire",
         lambda: reg.inscrire("x@y.tn", MOT_DE_PASSE, "juge_supreme", "Org X")),
        ("Adresse déjà inscrite",
         lambda: reg.inscrire("ahmed@menuiserie-sfax.tn", MOT_DE_PASSE, "msme",
                              "Menuiserie Ahmed")),
        ("Mot de passe de 4 caractères",
         lambda: reg.inscrire("z@y.tn", "1234", "msme", "Org Z")),
        ("Organisation laissée vide",
         lambda: reg.inscrire("w@y.tn", MOT_DE_PASSE, "msme", "  ")),
    ]
    for libelle, essai in essais:
        try:
            essai()
            print(f"  {libelle:<34} → ACCEPTÉ (anomalie !)")
        except InscriptionRefusee as refus:
            print(f"  {libelle:<34} → refusé")
            print(f"     « {refus} »")

    print()
    jeton, _ = reg.connexion("adl@bensalah.tn", MOT_DE_PASSE)
    altere = jeton[:-1] + ("A" if jeton[-1] != "A" else "B")
    try:
        lire_jeton(altere)
        print("  Jeton modifié d'un caractère       → ACCEPTÉ (anomalie !)")
    except JetonInvalide as refus:
        print("  Jeton modifié d'un caractère       → refusé")
        print(f"     « {refus} »")

    import time
    from packages.comptes.jetons import creer_jeton
    vieux = creer_jeton("cpt-x", "a@b.tn", "org-a", "msme",
                        duree_secondes=60,
                        maintenant=int(time.time()) - 100_000)
    try:
        lire_jeton(vieux)
        print("  Jeton expiré depuis hier           → ACCEPTÉ (anomalie !)")
    except JetonInvalide as refus:
        print("  Jeton expiré depuis hier           → refusé")
        print(f"     « {refus} »")


def _le_disque(reg: Registre) -> None:
    _titre("7. LE DISQUE — CE QUI EST RÉELLEMENT ÉCRIT")
    import sqlite3

    chemin = Path(str(reg.chemin))
    cx = sqlite3.connect(str(chemin))
    ligne = cx.execute(
        "SELECT email, role, organisation, empreinte FROM comptes "
        "WHERE email = ?", ("ahmed@menuiserie-sfax.tn",)
    ).fetchone()
    cx.close()

    print(f"  Fichier : {chemin.name} ({chemin.stat().st_size} octets)")
    print(f"  email        : {ligne[0]}")
    print(f"  role         : {ligne[1]}")
    print(f"  organisation : {ligne[2]}")
    print(f"  empreinte    : {ligne[3][:58]}…")
    print()

    octets = chemin.read_bytes()
    present = MOT_DE_PASSE.encode("utf-8") in octets
    print(f"  Le mot de passe « {MOT_DE_PASSE} » figure-t-il dans le fichier ?")
    print(f"    → {'OUI — ANOMALIE GRAVE' if present else 'NON'}")
    print(f"  L'adresse d'Ahmed y figure-t-elle (contre-épreuve) ?")
    print(f"    → {'OUI' if b'ahmed@menuiserie-sfax.tn' in octets else 'NON'}")
    print()
    print("  Deux comptes, même mot de passe, empreintes différentes :")
    cx = sqlite3.connect(str(chemin))
    deux = [l[0] for l in cx.execute(
        "SELECT empreinte FROM comptes WHERE email IN (?, ?)",
        ("ahmed@menuiserie-sfax.tn", "sonia@zitouna.tn"))]
    cx.close()
    print(f"    Ahmed : …{deux[0][-24:]}")
    print(f"    Sonia : …{deux[1][-24:]}")
    print(f"    → {'différentes' if deux[0] != deux[1] else 'IDENTIQUES (anomalie !)'}"
          " — le sel aléatoire fonctionne")


if __name__ == "__main__":
    principal()
