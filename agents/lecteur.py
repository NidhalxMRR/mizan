"""Agent 1 — LECTEUR DE PIÈCES.

Son unique métier : dire ce que le document CONTIENT, jamais ce qu'il VAUT.

Pourquoi cette séparation est structurelle et pas cosmétique
------------------------------------------------------------
Quand un seul composant lit le PDF et qualifie la créance en même temps, une
erreur de lecture devient une erreur de droit sans laisser de trace. Le
montant de 2 083,000 DT ramassé dans les joining instructions du hackathon
est passé en mise en demeure exécutoire parce que rien, dans la chaîne, ne
distinguait « j'ai lu ce nombre » de « ce nombre est une créance ».

Le lecteur ne produit donc que des FAITS, et chaque fait porte trois choses :
  - sa valeur,
  - la PAGE d'où il vient,
  - la LIGNE exacte qui le porte.

Un juriste peut rouvrir le PDF et vérifier chaque fait en quelques secondes.
C'est la définition opérationnelle de « traçable ».

L'empreinte SHA-256 scelle le document analysé : si la pièce change d'un
octet, l'empreinte change, et le dossier produit ne correspond plus. Sans
elle, « voici l'analyse de votre facture » ne désigne aucun fichier précis.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

from agents import amorce  # noqa: F401  (installe sys.path avant le métier)

from packages.legal import doc_gate, invoice

NOM = "lecteur"


@dataclass
class Fait:
    """Une donnée lue, et l'endroit exact où elle a été lue.

    `page` vaut None quand la ligne d'origine n'a pas pu être re-localisée
    dans une page précise (cas de l'OCR fusionné) : on préfère l'avouer
    plutôt que d'annoncer une page fausse.
    """

    cle: str
    valeur: object
    page: int | None
    ligne: str | None

    def to_dict(self):
        return asdict(self)


@dataclass
class Lecture:
    """Sortie de l'agent 1."""

    accepte: bool
    motif_refus: str | None
    chemin: str
    sha256: str
    n_pages: int
    methode: str          # 'text-layer' | 'ocr'
    faits: list = field(default_factory=list)
    indices_facture: list = field(default_factory=list)
    indices_manquants: list = field(default_factory=list)

    # -- accès confort pour les agents suivants ---------------------------
    def fait(self, cle):
        for f in self.faits:
            if f.cle == cle:
                return f
        return None

    def valeur(self, cle, defaut=None):
        f = self.fait(cle)
        return f.valeur if f is not None else defaut

    def to_dict(self):
        d = asdict(self)
        d["faits"] = [f.to_dict() if isinstance(f, Fait) else f for f in self.faits]
        return d


def empreinte(chemin) -> str:
    """SHA-256 du fichier, lu par blocs (une pièce jointe peut être lourde)."""
    h = hashlib.sha256()
    with open(chemin, "rb") as fh:
        for bloc in iter(lambda: fh.read(65536), b""):
            h.update(bloc)
    return h.hexdigest()


def _pages(chemin) -> list[str]:
    """Texte page par page. Liste vide si le PDF n'a pas de couche texte."""
    try:
        import pdfplumber

        with pdfplumber.open(str(chemin)) as pdf:
            return [(p.extract_text() or "") for p in pdf.pages]
    except Exception:
        return []


def _localiser(valeur, pages) -> tuple[int | None, str | None]:
    """Retrouve la page et la ligne qui portent une valeur.

    On cherche la forme telle qu'elle est IMPRIMÉE, pas la forme normalisée :
    une date stockée « 2026-05-12 » figure « 12/05/2026 » sur la facture. Sans
    ces variantes, tous les faits sortiraient avec page=None et la traçabilité
    serait décorative.
    """
    if valeur is None:
        return None, None

    formes = _formes(valeur)
    for num, texte in enumerate(pages, start=1):
        for ligne in texte.splitlines():
            plat = ligne.strip()
            if not plat:
                continue
            cible = plat.lower()
            for forme in formes:
                if forme and forme.lower() in cible:
                    return num, plat[:120]
    return None, None


def _formes(valeur) -> list[str]:
    """Les écritures plausibles d'une valeur dans un document réel."""
    s = str(valeur).strip()
    formes = [s]

    # Date ISO -> jj/mm/aaaa et jj-mm-aaaa
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        a, mo, j = m.groups()
        formes += [f"{j}/{mo}/{a}", f"{j}-{mo}-{a}", f"{j}.{mo}.{a}",
                   f"{int(j)}/{int(mo)}/{a}"]

    # Montant : 9520.0 -> « 9,520.000 », « 9 520,000 », « 9520.000 »
    if isinstance(valeur, float) or re.fullmatch(r"\d+(\.\d+)?", s):
        v = float(valeur)
        entier = int(v)
        formes += [
            f"{entier:,}".replace(",", " "),
            f"{entier:,}",
            f"{entier}",
            f"{v:,.3f}",
            f"{v:,.3f}".replace(",", " ").replace(".", ","),
            f"{v:.3f}",
        ]
    return formes


# Nature de la créance : ce que le vendeur dit avoir fourni. On reste
# DESCRIPTIF — « des marchandises ont été livrées » est un fait lisible sur
# la pièce. En tirer un délai de prescription est le métier de l'agent 2,
# pas celui-ci.
NATURE = [
    (re.compile(r"marchandise|livr[ée]|r[ée]ceptionn[ée]|بضاعة|تسليم", re.I),
     "livraison de marchandises"),
    (re.compile(r"prestation|service|honoraires|خدمة", re.I),
     "prestation de service"),
    (re.compile(r"travaux|chantier|pose|installation", re.I),
     "travaux ou pose"),
]

VENDEUR = re.compile(
    r"^\s*([A-ZÀ-Ý][A-ZÀ-Ý\s&'.-]{3,60})\s*$", re.M)


def lire(chemin) -> Lecture:
    """Lit une pièce et en extrait les faits. N'interprète rien juridiquement."""
    chemin = Path(chemin)
    if not chemin.exists():
        raise FileNotFoundError(f"pièce introuvable : {chemin}")

    sha = empreinte(chemin)
    pages = _pages(chemin)
    brut = invoice.parse_invoice(str(chemin))
    texte = brut.pop("_full_text", "") or ""

    # --- La porte d'entrée décide AVANT toute extraction de faits --------
    # Un document qui n'est pas une facture ne doit pas produire de « faits » :
    # ce sont eux qui deviendraient une créance en aval.
    verdict = doc_gate.inspect(texte)
    if not verdict["is_invoice"]:
        return Lecture(
            accepte=False,
            motif_refus=verdict["reason"] or verdict["detail"]
            or "ce document n'est pas reconnu comme une facture",
            chemin=str(chemin),
            sha256=sha,
            n_pages=len(pages),
            methode=brut.get("method", "inconnu"),
            faits=[],
            indices_facture=verdict.get("signals", []),
            indices_manquants=verdict.get("missing", []),
        )

    faits: list[Fait] = []

    def ajouter(cle, valeur):
        if valeur in (None, ""):
            return
        page, ligne = _localiser(valeur, pages)
        faits.append(Fait(cle=cle, valeur=valeur, page=page, ligne=ligne))

    ajouter("montant_tnd", brut.get("amount_tnd"))
    ajouter("date_facture", brut.get("invoice_date"))
    ajouter("numero_facture", brut.get("invoice_no"))
    ajouter("client", brut.get("client"))

    # Le vendeur : première ligne en capitales, convention des factures
    # tunisiennes (en-tête = raison sociale). Faute de quoi on n'invente pas.
    m = VENDEUR.search(texte)
    if m:
        ajouter("vendeur", m.group(1).strip())

    for rx, libelle in NATURE:
        if rx.search(texte):
            page, ligne = _localiser_motif(rx, pages)
            faits.append(Fait("nature_creance", libelle, page, ligne))
            break

    return Lecture(
        accepte=True,
        motif_refus=None,
        chemin=str(chemin),
        sha256=sha,
        n_pages=len(pages),
        methode=brut.get("method", "inconnu"),
        faits=faits,
        indices_facture=verdict.get("signals", []),
        indices_manquants=verdict.get("missing", []),
    )


def _localiser_motif(rx, pages) -> tuple[int | None, str | None]:
    for num, texte in enumerate(pages, start=1):
        for ligne in texte.splitlines():
            if rx.search(ligne):
                return num, ligne.strip()[:120]
    return None, None


if __name__ == "__main__":  # pragma: no cover
    import json
    import sys

    cible = sys.argv[1] if len(sys.argv) > 1 else "samples/facture_ahmed.pdf"
    r = lire(cible)
    print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2))
