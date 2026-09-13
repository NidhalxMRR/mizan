"""
La ligne qui justifie le montant doit porter le montant réclamé.

Défaut observé le 13/09/2026 sur la facture de démonstration : le dépôt de
pièce renvoyait

    ligne_montant : « TOTAL HT 8,000.000 »
    montant_tnd   : 9520.0

Les deux chiffres sont exacts — 8 000 HT + 1 520 de TVA font 9 520 — et
chaque module respectait son propre contrat : `doc_gate` retournait la
PREMIÈRE ligne de total, `invoice` retenait le PLUS GRAND montant. Mais
affichés côte à côte, ils donnent à lire une pièce qui se contredit.

Une pièce qui semble se contredire ne se discute plus : elle se rejette.
Le défaut n'était donc pas cosmétique.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import doc_gate


# La structure exacte de la facture d'Ahmed, telle que pdfplumber la rend.
FACTURE_AHMED = """FACTURE N° 2026-041
Menuiserie Ahmed Ben Salah - Sfax
MF : 1234567/A/M/000
Client : Société El Amen SARL
Date : 12/05/2026

Désignation Qté P.U. (DT) Total (DT)
Porte intérieure chêne 4 1,200.000 4,800.000
Fenêtre double vitrage 2 1,600.000 3,200.000

TOTAL HT 8,000.000
TVA 19% 1,520.000
NET A PAYER 9,520.000
"""


def test_la_ligne_portait_le_montant_hors_taxe_avant_correction():
    """Sans le montant, on retombe sur la première ligne de total : le HT."""
    ok, ligne = doc_gate._anchored_amount(FACTURE_AHMED)
    assert ok
    assert "TOTAL HT" in ligne, (
        "c'est le comportement d'origine, conservé comme comportement par "
        "défaut quand l'appelant ne sait pas encore quel montant est réclamé"
    )


def test_la_ligne_porte_le_montant_reclame_quand_on_le_connait():
    """Avec le montant, c'est la ligne du NET A PAYER qui est retenue."""
    ok, ligne = doc_gate._anchored_amount(FACTURE_AHMED, montant=9520.0)
    assert ok
    assert "NET A PAYER" in ligne
    assert "9,520.000" in ligne
    assert "TOTAL HT" not in ligne


def test_inspect_expose_la_bonne_ligne():
    """Le verdict complet, pas seulement la fonction interne."""
    v = doc_gate.inspect(FACTURE_AHMED, montant=9520.0)
    assert v["is_invoice"] is True
    assert "NET A PAYER" in v["anchored_line"]


def test_les_deux_montants_sont_coherents_entre_eux():
    """On n'a pas corrigé l'affichage en cassant l'arithmétique."""
    ok, ligne_ht = doc_gate._anchored_amount(FACTURE_AHMED, montant=8000.0)
    assert "TOTAL HT" in ligne_ht
    # 8 000 HT + 19 % de TVA = 9 520 : la facture est juste, c'est bien
    # l'affichage qui induisait en erreur.
    assert abs(8000.0 * 1.19 - 9520.0) < 0.01


def test_un_montant_absent_des_lignes_de_total_ne_ment_pas():
    """Si le montant ne figure sur aucune ligne de total, on ne l'invente pas."""
    ok, ligne = doc_gate._anchored_amount(FACTURE_AHMED, montant=42.0)
    assert ok
    # On retombe sur la première ligne de total, jamais sur une ligne
    # fabriquée pour faire coïncider l'affichage.
    assert "TOTAL HT" in ligne
    assert "42" not in ligne


def test_une_facture_sans_ligne_de_total_reste_refusee():
    """La correction ne doit pas affaiblir le contrôle d'entrée."""
    ok, ligne = doc_gate._anchored_amount(
        "Reçu de caisse\nMerci de votre visite\n34848\n", montant=34848.0
    )
    assert ok is False
    assert ligne is None


def test_les_formats_de_nombre_tunisiens_sont_reconnus():
    """« 9 520,000 » et « 9,520.000 » désignent la même somme."""
    variante = FACTURE_AHMED.replace("9,520.000", "9 520,000")
    ok, ligne = doc_gate._anchored_amount(variante, montant=9520.0)
    assert ok
    assert "NET A PAYER" in ligne
