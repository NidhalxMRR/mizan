"""Parcours réel dans un vrai navigateur, aux deux largeurs.

Ce test ne vérifie pas que le serveur répond : il ouvre un navigateur, tape au
clavier dans les champs, clique sur les boutons, et relit ce qui s'affiche à
l'écran. C'est la seule façon de distinguer une interface qui calcule d'une
page qui récite des valeurs écrites à l'avance.

Les montants et les dates utilisés ici ne figurent NULLE PART dans le dépôt :
ni dans les exemples de la page, ni dans les tests, ni dans le scénario de
démonstration. Si l'écran affiche un résultat juste pour ces valeurs-là, c'est
qu'il a calculé.

    python -m docs.demo.parcours_reel
"""

from __future__ import annotations

import re
import sys
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:3000"

# Les deux largeurs qui comptent : le téléphone réel, et l'écran du jury.
LARGEURS = [("telephone", 479, 900), ("projecteur", 1280, 900)]

# Valeurs inédites, calculées à l'exécution pour qu'elles ne puissent pas
# avoir été écrites en dur : une facture d'il y a exactement 100 jours.
AUJOURDHUI = date.today()
DATE_FACTURE = AUJOURDHUI - timedelta(days=100)
MONTANT = "3187.450"          # ni 9520 ni aucun montant du dépôt
# Le moteur ne qualifie que les activités qu'il sait rattacher à un régime :
# sur « plomberie » ou « ébénisterie » il REFUSE de trancher et affiche le
# délai général de quinze ans en le signalant comme non confirmé — c'est le
# comportement voulu, pas un défaut. Pour prouver que l'écran CALCULE, on lui
# donne donc une activité qualifiée, et l'inédit porte sur le montant et la
# date, qui ne figurent nulle part dans le dépôt.
ACTIVITE = "menuiserie"
ATTENDU_ECHEANCE = DATE_FACTURE + timedelta(days=365)
ATTENDU_JOURS = (ATTENDU_ECHEANCE - AUJOURDHUI).days


class Echec(Exception):
    pass


def verifier(condition: bool, libelle: str, detail: str = "") -> bool:
    if condition:
        print(f"    [OK]   {libelle}" + (f" — {detail}" if detail else ""))
        return True
    print(f"    [ÉCHEC] {libelle}" + (f" — {detail}" if detail else ""))
    return False


def parcours(page, nom: str) -> list[bool]:
    resultats: list[bool] = []

    page.goto(f"{BASE}/dossier", wait_until="networkidle")

    # --- 1. L'écran de départ ne doit PAS déjà afficher un résultat -------
    corps_initial = page.inner_text("body")
    resultats.append(verifier(
        MONTANT not in corps_initial,
        "avant saisie, le montant inédit n'est pas déjà à l'écran",
    ))

    # --- 2. Saisie au clavier, comme un utilisateur ------------------------
    # fill() vide puis type() caractère par caractère : sur un champ contrôlé
    # par React, vider d'abord fait perdre la valeur au state. On remplace
    # donc le contenu en une fois, ce que fait aussi un utilisateur qui
    # sélectionne tout avant de retaper.
    page.locator("#montant").fill(MONTANT)
    page.locator("#date").fill(DATE_FACTURE.isoformat())
    page.locator("#activite").fill(ACTIVITE)

    # --- 3. La relecture de date doit suivre la frappe ---------------------
    aide = page.inner_text("body")
    mois_fr = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
               "août", "septembre", "octobre", "novembre", "décembre"]
    attendu_lisible = f"{DATE_FACTURE.day} {mois_fr[DATE_FACTURE.month - 1]} {DATE_FACTURE.year}"
    resultats.append(verifier(
        attendu_lisible in aide,
        "la date tapée est relue en toutes lettres",
        attendu_lisible,
    ))

    # --- 4. Clic réel sur Analyser ----------------------------------------
    # La page est rendue côté serveur : le bouton pousse les valeurs dans
    # l'URL, et c'est le serveur qui recalcule. Il faut donc attendre que
    # l'URL porte la saisie, sinon on relit l'écran d'avant.
    page.get_by_role("button", name=re.compile("Analyser", re.I)).click()
    page.wait_for_url(re.compile(r"montant=" + re.escape(MONTANT)), timeout=15000)
    page.wait_for_load_state("networkidle")

    corps = page.inner_text("body")

    # --- 5. Le résultat doit correspondre au CALCUL, pas à un exemple ------
    jj = f"{ATTENDU_ECHEANCE.day:02d}/{ATTENDU_ECHEANCE.month:02d}/{ATTENDU_ECHEANCE.year}"
    resultats.append(verifier(
        jj in corps,
        "l'échéance calculée s'affiche",
        f"attendu {jj} (facture + 1 an)",
    ))
    resultats.append(verifier(
        str(ATTENDU_JOURS) in corps,
        "le nombre de jours restants s'affiche",
        f"attendu {ATTENDU_JOURS} jours",
    ))
    # Le montant d'Ahmed figure dans les deux cartes d'exemples en haut de
    # page : le trouver dans le corps entier ne prouverait rien. Ce qui
    # compte, c'est que le RÉSULTAT porte la valeur saisie.
    # L'écran met en forme le montant à la française : séparateur de milliers
    # en espace insécable fine (U+202F) et virgule décimale. On normalise donc
    # avant de comparer, plutôt que de chercher la chaîne brute.
    corps_normalise = corps.replace("\u202f", "").replace("\u00a0", "").replace(" ", "")
    montant_attendu = MONTANT.replace(".", ",")
    resultats.append(verifier(
        montant_attendu in corps_normalise,
        "le résultat reprend le montant saisi",
        f"{montant_attendu} DT",
    ))

    # --- 6. Le bouton de dépôt doit être en français ----------------------
    resultats.append(verifier(
        "Choisir un fichier" in corps and "Choose File" not in corps,
        "le bouton de dépôt est en français",
    ))

    # --- 7. Un acte interruptif change le résultat ------------------------
    avant = corps
    date_acte = AUJOURDHUI - timedelta(days=10)
    page.locator("#acte-type").select_option("sommation_huissier")
    page.locator("#acte-date").fill(date_acte.isoformat())
    page.get_by_role("button", name=re.compile("Ajouter l|acte", re.I)).first.click()
    page.wait_for_url(re.compile(r"acte="), timeout=15000)
    page.wait_for_load_state("networkidle")
    apres = page.inner_text("body")

    nouvelle_echeance = date_acte + timedelta(days=365)
    jj2 = f"{nouvelle_echeance.day:02d}/{nouvelle_echeance.month:02d}/{nouvelle_echeance.year}"
    resultats.append(verifier(
        apres != avant,
        "déclarer un acte modifie l'écran",
    ))
    resultats.append(verifier(
        jj2 in apres,
        "le délai repart de l'acte, pas de la facture",
        f"attendu {jj2}",
    ))

    # --- 8. Une recherche sans réponse doit s'abstenir --------------------
    page.goto(f"{BASE}/corpus?q=comment%20faire%20pousser%20des%20tomates",
              wait_until="networkidle")
    corpus = page.inner_text("body")
    resultats.append(verifier(
        ("aucun" in corpus.lower() or "abstient" in corpus.lower()
         or "ne répond" in corpus.lower() or "rien" in corpus.lower()),
        "sur une question hors du droit, l'écran s'abstient",
    ))

    page.screenshot(path=f"/tmp/parcours_{nom}.png", full_page=False)
    return resultats


def main() -> int:
    print("=" * 72)
    print("PARCOURS RÉEL — clavier et souris dans un vrai navigateur")
    print("=" * 72)
    print(f"  montant inédit : {MONTANT} DT")
    print(f"  facture du     : {DATE_FACTURE.isoformat()} (il y a 100 jours)")
    print(f"  activité       : {ACTIVITE}")
    print(f"  attendu        : échéance {ATTENDU_ECHEANCE.isoformat()}, "
          f"{ATTENDU_JOURS} jours restants")
    print()

    tous: list[bool] = []
    with sync_playwright() as p:
        navigateur = p.chromium.launch()
        for nom, largeur, hauteur in LARGEURS:
            print(f"--- {nom} ({largeur} px) " + "-" * (48 - len(nom)))
            contexte = navigateur.new_context(
                viewport={"width": largeur, "height": hauteur},
                locale="fr-FR",
            )
            page = contexte.new_page()
            try:
                tous += parcours(page, nom)
            except Exception as exc:  # noqa: BLE001
                print(f"    [ÉCHEC] exception : {type(exc).__name__}: {exc}")
                tous.append(False)
            contexte.close()
            print()
        navigateur.close()

    reussis = sum(1 for r in tous if r)
    echecs = len(tous) - reussis
    print("=" * 72)
    print(f"  contrôles réussis : {reussis}")
    print(f"  échecs            : {echecs}")
    print("=" * 72)
    if echecs:
        print("  PARCOURS NON VALIDÉ")
        return 1
    print("  PARCOURS VALIDÉ aux deux largeurs, sur des valeurs inédites.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
