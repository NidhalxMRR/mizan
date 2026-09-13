"""
Données FICTIVES de démonstration pour la place de marché MIZAN.

AVERTISSEMENT — AUCUNE DE CES PERSONNES N'EXISTE.
Les noms, les numéros d'inscription à l'ordre, les numéros d'accréditation et
les historiques de dossiers de ce fichier sont entièrement INVENTÉS pour la
démonstration du hackathon Hack4Justice. Ils ne désignent aucun avocat,
conciliateur, médiateur ou arbitre réel, et ne doivent jamais être présentés
comme un annuaire officiel. Les gouvernorats, eux, sont réels : c'est le seul
élément authentique de ce jeu de données.

En production, l'annuaire sera alimenté par les listes de l'Ordre national des
avocats de Tunisie et par les registres d'accréditation des médiateurs et
arbitres. Ce fichier n'est qu'un jeu d'essai.
"""

from __future__ import annotations

from packages.marketplace.annuaire import Annuaire, Dossier, Litige, Professionnel

__all__ = ["PROFESSIONNELS_FICTIFS", "annuaire_demo", "litige_ahmed"]


#: Huit professionnels fictifs, couvrant les quatre qualités, les deux langues
#: et plusieurs gouvernorats. Les seuils de montant reflètent des pratiques
#: plausibles (un arbitre ne se saisit pas d'un dossier à 300 DT).
PROFESSIONNELS_FICTIFS: tuple[Professionnel, ...] = (
    Professionnel.creer(
        identifiant="pro-001",
        nom="Me Sonia Ben Amor",
        qualite="avocat",
        numero_accreditation="ONAT-SFX-4412 (fictif)",
        expertises=["recouvrement", "commercial", "conciliation"],
        langues=["francais", "arabe"],
        gouvernorat="Sfax",
    ),
    Professionnel.creer(
        identifiant="pro-002",
        nom="Karim Trabelsi",
        qualite="conciliateur",
        numero_accreditation="ACC-CONC-2021-118 (fictif)",
        expertises=["conciliation", "commercial", "recouvrement"],
        langues=["francais", "arabe"],
        gouvernorat="Sfax",
    ),
    Professionnel.creer(
        identifiant="pro-003",
        nom="Me Hédi Ben Salah",
        qualite="avocat",
        numero_accreditation="ONAT-TUN-2290 (fictif)",
        expertises=["commercial", "recouvrement", "bail"],
        langues=["francais", "arabe"],
        gouvernorat="Tunis",
    ),
    Professionnel.creer(
        identifiant="pro-004",
        nom="Leïla Gharbi",
        qualite="mediateur",
        numero_accreditation="ACC-MED-2019-073 (fictif)",
        expertises=["mediation", "travail", "commercial"],
        langues=["francais", "arabe"],
        gouvernorat="Sousse",
    ),
    Professionnel.creer(
        identifiant="pro-005",
        nom="محمد الطرابلسي",  # Mohamed Trabelsi — profil en caractères arabes
        qualite="conciliateur",
        numero_accreditation="ACC-CONC-2020-045 (fictif)",
        expertises=["conciliation", "bail", "recouvrement"],
        langues=["arabe"],
        gouvernorat="Nabeul",
    ),
    Professionnel.creer(
        identifiant="pro-006",
        nom="Me Fatma Jelassi",
        qualite="arbitre",
        numero_accreditation="ACC-ARB-2018-012 (fictif)",
        expertises=["arbitrage", "construction", "commercial"],
        langues=["francais", "arabe"],
        gouvernorat="Tunis",
        montant_minimum_dt=20000.0,
    ),
    Professionnel.creer(
        identifiant="pro-007",
        nom="Nizar Chaabane",
        qualite="mediateur",
        numero_accreditation="ACC-MED-2022-201 (fictif)",
        expertises=["mediation", "construction", "bail"],
        langues=["francais"],
        gouvernorat="Nabeul",
    ),
    Professionnel.creer(
        identifiant="pro-008",
        nom="Me Amira Khelifi",
        qualite="avocat",
        numero_accreditation="ONAT-SFX-5107 (fictif)",
        expertises=["travail", "conciliation"],
        langues=["francais", "arabe"],
        gouvernorat="Sfax",
    ),
    Professionnel.creer(
        identifiant="pro-009",
        nom="Slim Ouerghi",
        qualite="conciliateur",
        numero_accreditation="ACC-CONC-2017-009 (fictif)",
        expertises=["conciliation", "recouvrement", "commercial"],
        langues=["francais", "arabe"],
        gouvernorat="Sousse",
    ),
)


def annuaire_demo() -> Annuaire:
    """
    Construit l'annuaire de démonstration : profils, dossiers passés et notes
    vérifiées.

    Tous les avis enregistrés ici passent par `Annuaire.noter`, donc par la
    vérification de clôture : le jeu de démonstration ne contourne pas la règle
    qu'il est censé illustrer.
    """
    annuaire = Annuaire()
    for pro in PROFESSIONNELS_FICTIFS:
        annuaire.inscrire(pro)

    # Dossiers passés, tous clôturés : ils fondent les notes affichées.
    historique = [
        Dossier.creer("dos-101", ["ste-medina", "atelier-bouzid"], "pro-001", cloture=True),
        Dossier.creer("dos-102", ["ste-olivia", "transport-gabes"], "pro-001", cloture=True),
        Dossier.creer("dos-103", ["ste-karama", "menuiserie-nord"], "pro-002", cloture=True),
        Dossier.creer("dos-104", ["ste-nour", "ste-delta"], "pro-003", cloture=True),
        Dossier.creer("dos-105", ["ste-sahel", "usine-msaken"], "pro-004", cloture=True),
        Dossier.creer("dos-106", ["ste-cap", "residence-hammamet"], "pro-005", cloture=True),
        Dossier.creer("dos-107", ["ste-batim", "promoteur-lac"], "pro-006", cloture=True),
        Dossier.creer("dos-108", ["ste-riadh", "ste-jasmin"], "pro-009", cloture=True),
        # Ce dossier est le piège du conflit d'intérêts : pro-002 a défendu
        # Société Zitouna, qui est la partie adverse d'Ahmed.
        Dossier.creer("dos-109", ["ste-zitouna", "fournisseur-kerkennah"], "pro-002", cloture=True),
        # Dossier volontairement NON clôturé : sert à démontrer le refus de note.
        Dossier.creer("dos-110", ["ste-aurore", "ste-phenix"], "pro-003", cloture=False),
    ]
    for dossier in historique:
        annuaire.enregistrer_dossier(dossier)

    notes = [
        ("pro-001", "ste-medina", "dos-101", 5, "Dossier mené vite, accord signé."),
        ("pro-001", "ste-olivia", "dos-102", 4, "Bonne écoute, délais respectés."),
        ("pro-002", "ste-karama", "dos-103", 4, "Conciliation aboutie en deux séances."),
        ("pro-003", "ste-nour", "dos-104", 3, "Compétent mais peu disponible."),
        ("pro-004", "ste-sahel", "dos-105", 5, "Médiation exemplaire."),
        ("pro-005", "ste-cap", "dos-106", 4, "Très clair en arabe."),
        ("pro-006", "ste-batim", "dos-107", 5, "Sentence motivée et rapide."),
        ("pro-009", "ste-riadh", "dos-108", 3, "Accord partiel seulement."),
    ]
    for professionnel, auteur, dossier, etoiles, commentaire in notes:
        annuaire.noter(professionnel, auteur, dossier, etoiles, commentaire)

    return annuaire


def litige_ahmed() -> Litige:
    """
    Le cas de démonstration : Ahmed, menuisier à Sfax, réclame 9 520 DT à la
    société Zitouna au titre de factures impayées, et souhaite une conciliation
    conduite en français.
    """
    return Litige.creer(
        nature=["recouvrement", "commercial", "impaye"],
        montant_dt=9520.0,
        gouvernorat="Sfax",
        langue="francais",
        voie="conciliation",
        demandeur="menuiserie-ahmed",
        partie_adverse="ste-zitouna",
    )
