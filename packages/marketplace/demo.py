"""
Démonstration en ligne de commande : le litige d'Ahmed.

    ./.venv/bin/python -m packages.marketplace.demo

Affiche les professionnels proposés, la raison de chaque proposition, les
professionnels écartés et leur motif — dont le conflit d'intérêts.
"""

from __future__ import annotations

from packages.marketplace.annuaire import Annuaire, Litige, NotationRefusee
from packages.marketplace.exemples import annuaire_demo, litige_ahmed


def _titre(texte: str) -> None:
    print()
    print(texte)
    print("=" * len(texte))


def principal() -> None:
    """Déroule le cas de démonstration de bout en bout."""
    annuaire: Annuaire = annuaire_demo()
    litige: Litige = litige_ahmed()

    _titre("LITIGE")
    print("Demandeur      : Ahmed, menuisier à Sfax (menuiserie-ahmed)")
    print("Partie adverse : Société Zitouna (ste-zitouna)")
    print(f"Nature         : {', '.join(sorted(litige.nature))}")
    print(f"Montant        : {litige.montant_dt:,.0f} DT".replace(",", " "))
    print(f"Gouvernorat    : {(litige.gouvernorat or 'non précisé').title()}")
    print(f"Langue         : {litige.langue}")
    print(f"Voie choisie   : {litige.voie}")

    recommandation = annuaire.recommander(litige, limite=3)

    _titre("PROFESSIONNELS PROPOSÉS")
    print(recommandation.texte())

    _titre("PROFESSIONNELS ÉCARTÉS, ET POURQUOI")
    for motif in recommandation.ecartes:
        print(f"- {motif}")

    _titre("NOTATION VÉRIFIÉE : LE REFUS EN ACTION")
    try:
        annuaire.noter("pro-003", "ste-aurore", "dos-110", 5)
    except NotationRefusee as refus:
        print(f"- Note de 5 étoiles sur un dossier en cours → {refus}")
    try:
        annuaire.noter("pro-001", "ste-medina", "dos-101", 6)
    except NotationRefusee as refus:
        print(f"- Note de 6 étoiles → {refus}")
    try:
        annuaire.noter("pro-001", "client-fantome", "dos-999", 5)
    except NotationRefusee as refus:
        print(f"- Note sans dossier → {refus}")

    _titre("ANNUAIRE VIDE : L'ABSTENTION EST ÉCRITE")
    print(Annuaire().recommander(litige).texte())


if __name__ == "__main__":
    principal()
