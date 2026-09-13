"""Fabrique les pièces d'essai déposées pendant la démonstration.

Le site accepte une facture au format PDF, en lit le montant, la date, le
numéro et le client, puis calcule le délai de prescription. Encore faut-il
avoir des pièces à lui donner, et surtout des pièces qui ne racontent pas
toutes la même histoire : une créance encore récupérable ne prouve rien si
l'on ne montre pas, à côté, une créance perdue et une pièce refusée.

Chaque facture ci-dessous existe pour une raison précise, écrite en tête de
sa fonction. Les montants suivent la règle tunisienne des trois décimales et
la taxe sur la valeur ajoutée est calculée à dix-neuf pour cent, non
arrondie à la main : c'est le programme qui la calcule, afin qu'aucun chiffre
affiché ne soit le fruit d'une saisie distraite.

Le rendu passe par ReportLab, sous licence BSD, déjà présent dans le projet.
Aucune police distante n'est employée : la salle peut être sans réseau.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

DOSSIER = Path(__file__).resolve().parent
LARGEUR, HAUTEUR = A4
MARGE = 50


def montant(valeur: float) -> str:
    """Trois décimales, séparateur de milliers : l'usage tunisien."""
    return f"{valeur:,.3f}"


@dataclass
class Ligne:
    designation: str
    quantite: int
    prix_unitaire: float

    @property
    def total(self) -> float:
        return self.quantite * self.prix_unitaire


@dataclass
class Facture:
    fichier: str
    raison: str
    vendeur: str
    adresse_vendeur: str
    matricule: str
    telephone: str
    numero: str
    date: str
    client: str
    adresse_client: str
    lignes: list[Ligne]
    mention_finale: str
    conditions: str = "Conditions de paiement : 30 jours fin de mois."
    taux_tva: float = 0.19
    devise: str = "DT"

    @property
    def total_ht(self) -> float:
        return sum(ligne.total for ligne in self.lignes)

    @property
    def tva(self) -> float:
        return round(self.total_ht * self.taux_tva, 3)

    @property
    def net_a_payer(self) -> float:
        return round(self.total_ht + self.tva, 3)


def ecrire(facture: Facture) -> Path:
    """Dessine la facture, dans la disposition que le lecteur sait lire."""
    chemin = DOSSIER / facture.fichier
    c = canvas.Canvas(str(chemin), pagesize=A4)
    y = HAUTEUR - MARGE

    c.setFont("Helvetica-Bold", 14)
    c.drawString(MARGE, y, facture.vendeur)
    y -= 16
    c.setFont("Helvetica", 9)
    for ligne in (facture.adresse_vendeur,
                  f"Matricule fiscal : {facture.matricule}",
                  f"Tél : {facture.telephone}"):
        c.drawString(MARGE, y, ligne)
        y -= 12

    y -= 14
    c.setFont("Helvetica-Bold", 12)
    c.drawString(MARGE, y, f"FACTURE N° {facture.numero}")
    y -= 16
    c.setFont("Helvetica", 10)
    for ligne in (f"Date : {facture.date}",
                  f"Client : {facture.client}",
                  f"Adresse : {facture.adresse_client}"):
        c.drawString(MARGE, y, ligne)
        y -= 13

    y -= 12
    c.setFont("Helvetica-Bold", 9)
    c.drawString(MARGE, y, "Désignation")
    c.drawRightString(LARGEUR - MARGE - 210, y, "Qté")
    c.drawRightString(LARGEUR - MARGE - 110, y, f"P.U. ({facture.devise})")
    c.drawRightString(LARGEUR - MARGE, y, f"Total ({facture.devise})")
    y -= 6
    c.line(MARGE, y, LARGEUR - MARGE, y)
    y -= 14

    c.setFont("Helvetica", 9)
    for ligne in facture.lignes:
        c.drawString(MARGE, y, ligne.designation)
        c.drawRightString(LARGEUR - MARGE - 210, y, str(ligne.quantite))
        c.drawRightString(LARGEUR - MARGE - 110, y, montant(ligne.prix_unitaire))
        c.drawRightString(LARGEUR - MARGE, y, montant(ligne.total))
        y -= 14

    y -= 4
    c.line(LARGEUR - MARGE - 260, y, LARGEUR - MARGE, y)
    y -= 16

    c.setFont("Helvetica", 10)
    c.drawString(LARGEUR - MARGE - 260, y, "TOTAL HT")
    c.drawRightString(LARGEUR - MARGE, y, montant(facture.total_ht))
    y -= 14
    c.drawString(LARGEUR - MARGE - 260, y,
                 f"TVA {int(facture.taux_tva * 100)}%")
    c.drawRightString(LARGEUR - MARGE, y, montant(facture.tva))
    y -= 16
    c.setFont("Helvetica-Bold", 11)
    c.drawString(LARGEUR - MARGE - 260, y, "NET A PAYER")
    c.drawRightString(LARGEUR - MARGE, y, montant(facture.net_a_payer))

    y -= 34
    c.setFont("Helvetica", 9)
    c.drawString(MARGE, y, facture.conditions)
    y -= 13
    c.drawString(MARGE, y, facture.mention_finale)

    c.save()
    return chemin


# --- Les pièces ------------------------------------------------------------

FACTURES: list[Facture] = [
    Facture(
        fichier="facture_encore_recuperable.pdf",
        raison=(
            "Le cas nominal. Une créance récente, encore dans le délai : le "
            "moteur doit annoncer un nombre de jours restants et une date "
            "d'échéance. C'est la pièce à déposer en premier."
        ),
        vendeur="MENUISERIE AHMED",
        adresse_vendeur="Route de Gabès km 3 — 3000 Sfax",
        matricule="1234567/A/M/000",
        telephone="74 400 112",
        numero="2026-058",
        date="03/03/2026",
        client="Société El Amen SARL",
        adresse_client="Avenue Habib Bourguiba, Sfax",
        lignes=[
            Ligne("Comptoir d'accueil en chêne massif", 1, 4200.000),
            Ligne("Étagères murales sur mesure", 6, 380.000),
            Ligne("Pose et livraison", 1, 900.000),
        ],
        mention_finale="Marchandise livrée et réceptionnée sans réserve.",
    ),
    Facture(
        fichier="facture_prescrite.pdf",
        raison=(
            "Le contre-exemple, et le plus utile des deux. Une créance de deux "
            "mille vingt : le délai est expiré depuis longtemps. Le moteur doit "
            "le dire franchement plutôt que de proposer une démarche qui ne "
            "mènerait nulle part. Montrer un refus vaut mieux que montrer dix "
            "réussites."
        ),
        vendeur="MENUISERIE AHMED",
        adresse_vendeur="Route de Gabès km 3 — 3000 Sfax",
        matricule="1234567/A/M/000",
        telephone="74 400 112",
        numero="2020-014",
        date="15/01/2020",
        client="Entreprise Ben Mahmoud",
        adresse_client="Rue de la République, Sfax",
        lignes=[
            Ligne("Mobilier de bureau complet", 1, 5400.000),
            Ligne("Cloisons vitrées", 4, 650.000),
        ],
        mention_finale="Marchandise livrée et réceptionnée sans réserve.",
    ),
    Facture(
        fichier="facture_sous_seuil.pdf",
        raison=(
            "Une créance de faible montant, sous le seuil de cent cinquante "
            "dinars au-delà duquel la sommation doit être signifiée par un "
            "huissier de justice. Le moteur doit alors indiquer qu'une lettre "
            "recommandée suffit : la démonstration prouve qu'il distingue les "
            "situations au lieu d'appliquer une règle unique."
        ),
        vendeur="MENUISERIE AHMED",
        adresse_vendeur="Route de Gabès km 3 — 3000 Sfax",
        matricule="1234567/A/M/000",
        telephone="74 400 112",
        numero="2026-061",
        date="20/04/2026",
        client="Café des Arts",
        adresse_client="Place des Martyrs, Sfax",
        lignes=[
            Ligne("Réparation de deux tabourets", 2, 45.000),
        ],
        mention_finale="Marchandise livrée et réceptionnée sans réserve.",
    ),
    Facture(
        fichier="facture_prestation_de_service.pdf",
        raison=(
            "Une prestation de service, et non une marchandise livrée. La "
            "distinction n'est pas décorative : elle change le délai "
            "applicable. Déposer cette pièce après la première montre que le "
            "moteur lit la nature de l'obligation et ne se contente pas du "
            "montant."
        ),
        vendeur="CABINET TECHNIQUE SFAX",
        adresse_vendeur="12 rue Mongi Slim — 3000 Sfax",
        matricule="7654321/B/N/000",
        telephone="74 220 887",
        numero="2026-007",
        date="10/02/2026",
        client="Société El Amen SARL",
        adresse_client="Avenue Habib Bourguiba, Sfax",
        lignes=[
            Ligne("Étude technique et plans d'exécution", 1, 3500.000),
            Ligne("Suivi de chantier — honoraires", 1, 2800.000),
        ],
        mention_finale="Prestation de service exécutée et acceptée.",
    ),
    Facture(
        fichier="facture_gros_montant.pdf",
        raison=(
            "Une créance qui dépasse vingt-cinq mille dinars, seuil au-delà "
            "duquel la représentation par avocat devient obligatoire selon "
            "l'article 57 du code des droits et procédures fiscaux. La pièce "
            "sert à montrer la qualité d'avocat récemment ajoutée, et pourquoi "
            "elle existe."
        ),
        vendeur="MENUISERIE AHMED",
        adresse_vendeur="Route de Gabès km 3 — 3000 Sfax",
        matricule="1234567/A/M/000",
        telephone="74 400 112",
        numero="2026-044",
        date="18/01/2026",
        client="Groupe Hôtelier Manar SA",
        adresse_client="Route touristique, Sousse",
        lignes=[
            Ligne("Agencement complet de quarante chambres", 40, 720.000),
            Ligne("Mobilier de réception", 1, 6800.000),
            Ligne("Transport et pose sur site", 1, 4200.000),
        ],
        mention_finale="Marchandise livrée et réceptionnée sans réserve.",
    ),
]


def fabriquer() -> list[Path]:
    return [ecrire(f) for f in FACTURES]


def verifier(chemins: list[Path], base: str) -> int:
    """Dépose chaque pièce sur le service et rapporte ce qu'il en a lu.

    Fabriquer un fichier ne prouve rien : tant qu'il n'est pas passé par la
    route qui le lit, on ignore si le montant sera reconnu. Cette fonction
    fait donc le trajet réel, celui de la démonstration.
    """
    echecs = 0
    for chemin in chemins:
        sortie = subprocess.run(
            ["curl", "-s", "-m", "90", "-X", "POST",
             f"{base}/dossiers/traiter-piece",
             "-F", f"fichier=@{chemin}"],
            capture_output=True, text=True).stdout
        try:
            import json
            lu = json.loads(sortie)
        except Exception:
            print(f"  ILLISIBLE {chemin.name} : {sortie[:120]}")
            echecs += 1
            continue

        faits = {}
        for etape in lu.get("etapes", []):
            for fait in (etape.get("detail") or {}).get("faits", []) or []:
                faits[fait["cle"]] = fait["valeur"]

        attendu = next(f for f in FACTURES if f.fichier == chemin.name)
        montant_lu = faits.get("montant_tnd")
        correct = (montant_lu is not None
                   and abs(float(montant_lu) - attendu.net_a_payer) < 0.01)
        if not correct:
            echecs += 1
        print(f"  [{'OK ' if correct else 'ECHEC'}] {chemin.name:38} "
              f"lu={montant_lu} attendu={attendu.net_a_payer} "
              f"date={faits.get('date_facture')} "
              f"n°={faits.get('numero_facture')}")
    return echecs


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8820"
    chemins = fabriquer()
    print(f"{len(chemins)} pièces écrites dans {DOSSIER}\n")
    echecs = verifier(chemins, base)
    print(f"\n{len(chemins) - echecs}/{len(chemins)} pièces relues par le "
          f"service, {echecs} échec(s)")
    sys.exit(1 if echecs else 0)
