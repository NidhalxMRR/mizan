"""Exécution réelle sur une facture, pour voir ce que le moteur produit.

    cd ~/mizan && source .venv/bin/activate
    python -m packages.risques.demo samples/facture_ahmed.pdf

Sans argument, prend la facture d'Ahmed. Ce script lit un vrai PDF, en
extrait le texte avec la chaîne d'ingestion existante, et imprime le rapport
tel qu'un juriste le lirait : chaque risque avec sa constatation, sa portée et
l'article arabe qui le fonde — puis ce que le moteur n'a PAS pu vérifier.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from packages.legal.invoice import parse_invoice  # noqa: E402
from packages.risques import fondements  # noqa: E402
from packages.risques.facture import analyser  # noqa: E402

BANDEAU = {'eleve': 'GRAVITÉ ÉLEVÉE', 'moyen': 'GRAVITÉ MOYENNE',
           'faible': 'GRAVITÉ FAIBLE'}


def main(chemin: str, aujourdhui: date | None = None) -> int:
    """Analyse le document désigné et imprime le rapport."""
    aujourdhui = aujourdhui or date.today()
    donnees = parse_invoice(chemin)
    texte = donnees['_full_text']

    print('=' * 78)
    print(f"DOCUMENT   {Path(chemin).name}")
    print(f"Lecture    {donnees['method']} — {donnees['n_chars']} caractères")
    print(f"Montant    {donnees['amount_tnd']} DT")
    print(f"Date       {donnees['invoice_date']}")
    print(f"Numéro     {donnees['invoice_no']}")
    print(f"Analyse au {aujourdhui.strftime('%d/%m/%Y')}")
    print('=' * 78)

    rapport = analyser(
        texte,
        montant=donnees['amount_tnd'],
        date_facture=donnees['invoice_date'],
        activite='menuiserie',
        aujourdhui=aujourdhui,
    )

    if not rapport.document_analyse:
        print(f"\nDOCUMENT REJETÉ : {rapport.motif_rejet_fr}")
        for abstention in rapport.abstentions:
            print(f"  · {abstention.sujet_fr} — {abstention.motif_fr}")
        return 0

    print(f"\n{len(rapport.risques)} RISQUE(S) FONDÉ(S) SUR LE CORPUS\n")
    for numero, risque in enumerate(rapport.risques, 1):
        print(f"[{numero}] {risque.intitule_fr}")
        print(f"    {BANDEAU[risque.gravite]}  ·  identifiant : {risque.identifiant}")
        print(f"    CONSTATATION  {risque.constatation_fr}")
        print(f"    PORTÉE        {risque.consequence_fr}")
        print(f"    FONDEMENT     {risque.fondement.citation_ar}")
        print(f"                  ({risque.fondement.code_fr}, art. "
              f"{risque.fondement.article})")
        print(f"    CITATION      {risque.fondement.extrait_ar}")
        if risque.fondement.reserve_fr:
            print(f"    RÉSERVE       {risque.fondement.reserve_fr}")
        print()

    print(f"{len(rapport.abstentions)} POINT(S) NON VÉRIFIÉ(S) — le moteur "
          f"s'abstient plutôt que d'affirmer\n")
    for abstention in rapport.abstentions:
        print(f"  · {abstention.sujet_fr}")
        print(f"    {abstention.motif_fr}\n")

    print('LACUNES CONNUES DU CORPUS\n')
    for lacune in fondements.LACUNES:
        print(f"  · {lacune.sujet_fr}")
        print(f"    {lacune.constat_fr}\n")

    return 0


if __name__ == '__main__':
    cible = sys.argv[1] if len(sys.argv) > 1 else str(
        RACINE / 'samples' / 'facture_ahmed.pdf')
    sys.exit(main(cible))
