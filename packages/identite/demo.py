"""Démonstration réelle : sceller une vraie mise en demeure, l'altérer, le voir.

Exécution :
    cd ~/mizan && source .venv/bin/activate && python -m packages.identite.demo

Le document n'est pas inventé pour la démonstration : il est produit par
`packages/legal/notice.py` à partir du moteur juridique déterministe, sur le
dossier d'Ahmed (menuisier à Sfax, 9 520,000 DT, facture du 12 mai 2026).
"""
from datetime import date

from packages.identite import (
    FournisseurEHouwiya,
    FournisseurIndisponible,
    FournisseurLocal,
    RegistreDeCles,
    sceller,
)
from packages.identite.attribution import attribuer
from packages.legal import notice
from packages.legal.legal_engine import assess

AUJOURDHUI = date(2026, 9, 13)
CREANCIER = {"name": "Menuiserie Ahmed", "address": "Route de Gabès km 3 — 3000 Sfax",
             "tax_id": "1234567/A/M/000", "city": "Sfax"}
DEBITEUR = {"name": "Société El Amen SARL", "address": "Avenue Habib Bourguiba, Sfax"}
FACTURE = {"invoice_no": "2026-041", "invoice_date": "2026-05-12"}


def main() -> None:
    # 1. Une VRAIE mise en demeure, produite par le module légal.
    dossier = assess(9520.0, "2026-05-12", "menuiserie", today=AUJOURDHUI)
    doc = notice.construire(dossier, CREANCIER, DEBITEUR, FACTURE)
    texte = doc.texte

    print("=" * 72)
    print("1. DOCUMENT RÉEL produit par packages/legal/notice.py")
    print("=" * 72)
    print(f"Longueur : {len(texte)} caractères")
    print("Extrait :")
    for ligne in texte.splitlines()[:6]:
        print(f"    {ligne}")
    print("    [...]")

    # 2. Le créancier scelle son document.
    ahmed = FournisseurLocal("Menuiserie Ahmed")
    registre = RegistreDeCles()
    registre.enregistrer_fournisseur(ahmed)

    scelle = sceller(
        texte, ahmed,
        contexte={"dossier": "2026-041", "objet": "Mise en demeure — projet"},
    )
    print()
    print("=" * 72)
    print("2. SCELLEMENT")
    print("=" * 72)
    print(scelle.to_json())

    # 3. Vérification du document authentique.
    print()
    print("=" * 72)
    print("3. VÉRIFICATION DU DOCUMENT AUTHENTIQUE")
    print("=" * 72)
    print(attribuer(scelle, texte, registre=registre).en_texte())

    # 4. Altération d'UN SEUL caractère, dans le montant réclamé : le pire cas
    #    pour le créancier, et le plus plausible dans un litige.
    montant = doc.montant_fr  # tel qu'il est réellement écrit dans le texte
    chiffres = [i for i, c in enumerate(montant) if c.isdigit()]
    i_rel = chiffres[1]  # le deuxième chiffre : « 9 5xx » -> « 9 8xx »
    montant_faux = (
        montant[:i_rel]
        + ("8" if montant[i_rel] != "8" else "7")
        + montant[i_rel + 1:]
    )
    if montant in texte:
        altere = texte.replace(montant, montant_faux, 1)
    else:  # repli : le montant n'apparaît pas tel quel, on altère un chiffre
        i = next(i for i, c in enumerate(texte) if c.isdigit())
        altere = texte[:i] + ("8" if texte[i] != "8" else "7") + texte[i + 1:]

    differences = [
        (i, a, b) for i, (a, b) in enumerate(zip(texte, altere)) if a != b
    ]
    print()
    print("=" * 72)
    print("4. ALTÉRATION")
    print("=" * 72)
    print(f"Caractères modifiés : {len(differences)}")
    for i, avant, apres in differences:
        print(f"    position {i} : « {avant} » devient « {apres} »")
    print(f"Longueur avant : {len(texte)} / après : {len(altere)}")

    print()
    print("=" * 72)
    print("5. LA VÉRIFICATION DÉTECTE L'ALTÉRATION")
    print("=" * 72)
    rapport = attribuer(scelle, altere, registre=registre)
    print(rapport.en_texte())

    # 6. e-Houwiya : non implémenté, et on le dit.
    print()
    print("=" * 72)
    print("6. e-HOUWIYA — NON IMPLÉMENTÉ")
    print("=" * 72)
    try:
        sceller(texte, FournisseurEHouwiya("12345678"))
    except FournisseurIndisponible as exc:
        print(exc)

    assert rapport.document_modifie is True, "L'altération DOIT être détectée."
    print()
    print("Démonstration terminée : altération détectée, e-Houwiya refusé.")


if __name__ == "__main__":
    main()
