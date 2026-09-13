"""Le dossier de réclamation : ce que le greffier reçoit réellement.

Le brief Challenge B, section 4.3, exige d'empaqueter les preuves *vérifiées*
dans un dossier numérique standardisé. Le mot qui compte est « vérifiées ».

Un greffier du Tribunal de Commerce ne manque pas de PDF. Il manque de temps
pour établir, pièce par pièce, si un dossier est recevable. Ce module produit
donc un manifeste : chaque pièce porte son empreinte SHA-256, sa provenance,
et le verdict de la porte d'entrée qui l'a acceptée ou refusée.

Rien n'est affirmé ici qui ne soit calculable. Un dossier incomplet est
déclaré incomplet — c'est la même règle que l'abstention en recherche.
"""
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from pathlib import Path

SCHEMA_VERSION = '1.0'

# Ce qu'un dossier d'impayé doit contenir pour être instruit sans aller-retour.
# Source : brief Challenge B §4.1 (contrats, bons de commande, factures, bons
# de livraison, emails) croisé avec CPC art. 59-60 (créance déterminée +
# mise en demeure préalable).
PIECES_ATTENDUES = {
    'facture': {
        'label': 'Facture',
        'obligatoire': True,
        'pourquoi': "CPC art. 59 : l'injonction de payer suppose une créance "
                    "déterminée d'origine contractuelle.",
    },
    'mise_en_demeure': {
        'label': 'Mise en demeure',
        'obligatoire': True,
        'pourquoi': "CPC art. 60 : au-delà de 150 DT, la mise en demeure "
                    "préalable par huissier est requise.",
    },
    'preuve_livraison': {
        'label': 'Bon de livraison ou preuve d\'exécution',
        'obligatoire': False,
        'pourquoi': "Établit que la prestation a été exécutée : c'est ce qui "
                    "distingue un impayé d'un litige sur la qualité.",
    },
    'contrat': {
        'label': 'Contrat ou bon de commande',
        'obligatoire': False,
        'pourquoi': "Fonde l'origine contractuelle de la créance.",
    },
    'echanges': {
        'label': 'Échanges (emails, courriers)',
        'obligatoire': False,
        'pourquoi': "Documentent les relances et la date de connaissance "
                    "du débiteur.",
    },
}


@dataclass
class Piece:
    """Une pièce du dossier, avec ce qui permet de la contrôler."""
    kind: str
    filename: str
    sha256: str
    n_bytes: int
    # Verdict de la porte d'entrée (app/doc_gate.py) au moment du dépôt.
    gate_ok: bool = True
    gate_reason: str = None
    source_method: str = 'upload'

    def to_dict(self):
        return asdict(self)


@dataclass
class Dossier:
    """Le dossier standardisé. Sérialisable, vérifiable, sans effet de bord."""
    reference: str
    created_at: str
    creancier: str
    debiteur: str
    montant_tnd: float
    invoice_date: str
    pieces: list = field(default_factory=list)
    articles: list = field(default_factory=list)
    prescription: dict = field(default_factory=dict)

    # --- contrôle de recevabilité -------------------------------------------
    def manquants(self):
        """Les pièces obligatoires absentes. Vide = dossier instruisable."""
        presents = {p.kind for p in self.pieces if p.gate_ok}
        return [k for k, v in PIECES_ATTENDUES.items()
                if v['obligatoire'] and k not in presents]

    def pieces_refusees(self):
        return [p for p in self.pieces if not p.gate_ok]

    @property
    def complet(self):
        return not self.manquants()

    @property
    def statut(self):
        if self.pieces_refusees():
            return 'pieces_refusees'
        return 'complet' if self.complet else 'incomplet'

    # --- sortie --------------------------------------------------------------
    def manifest(self):
        """Le manifeste JSON : ce qu'un greffier (ou une API) peut contrôler."""
        return {
            'schema_version': SCHEMA_VERSION,
            'reference': self.reference,
            'created_at': self.created_at,
            'statut': self.statut,
            'parties': {'creancier': self.creancier, 'debiteur': self.debiteur},
            'creance': {
                'montant_tnd': self.montant_tnd,
                'date_facture': self.invoice_date,
            },
            'prescription': self.prescription,
            'pieces': [p.to_dict() for p in self.pieces],
            'pieces_manquantes': [
                {'kind': k, **PIECES_ATTENDUES[k]} for k in self.manquants()
            ],
            'fondement_juridique': self.articles,
            'avertissement': (
                "Chaque article cité a été relu dans le corpus indexé. "
                "Aucun modèle de langage n'intervient dans la constitution "
                "de ce dossier."
            ),
        }


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def reference_for(montant, invoice_date, debiteur, when=None):
    """Référence stable et lisible : MZ-AAAAMMJJ-XXXX.

    Déterministe pour un même dossier — deux dépôts identiques ne créent pas
    deux références différentes, ce qui évite les doublons côté greffe.
    """
    when = when or date.today()
    seed = f'{montant}|{invoice_date}|{debiteur}'.encode('utf-8')
    suffix = hashlib.sha256(seed).hexdigest()[:4].upper()
    return f"MZ-{when.strftime('%Y%m%d')}-{suffix}"


def build_zip(dossier, files, out_path):
    """Écrit le dossier : manifeste + pièces + lisez-moi lisible par un humain.

    `files` : dict kind -> chemin du fichier réel.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = dossier.manifest()

    lignes = [
        f"DOSSIER DE RÉCLAMATION {dossier.reference}",
        f"Constitué le {dossier.created_at}",
        '',
        f"Créancier : {dossier.creancier}",
        f"Débiteur  : {dossier.debiteur}",
        f"Montant   : {dossier.montant_tnd:,.3f} DT".replace(',', ' '),
        f"Statut    : {dossier.statut}",
        '',
        'PIÈCES',
    ]
    for p in dossier.pieces:
        mark = 'OK ' if p.gate_ok else 'REFUSÉE'
        lignes.append(f"  [{mark}] {PIECES_ATTENDUES.get(p.kind, {}).get('label', p.kind)}"
                      f" — {p.filename}")
        lignes.append(f"          sha256 {p.sha256}")
        if not p.gate_ok:
            lignes.append(f"          motif : {p.gate_reason}")
    if dossier.manquants():
        lignes += ['', 'PIÈCES MANQUANTES']
        for k in dossier.manquants():
            lignes.append(f"  - {PIECES_ATTENDUES[k]['label']} : "
                          f"{PIECES_ATTENDUES[k]['pourquoi']}")
    lignes += ['', 'FONDEMENT JURIDIQUE']
    for a in dossier.articles:
        lignes.append(f"  - {a.get('short_fr', '')} : {a.get('label_fr', '')}")
        if a.get('citation_ar'):
            lignes.append(f"    {a['citation_ar']}")

    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('manifeste.json',
                   json.dumps(manifest, ensure_ascii=False, indent=2))
        z.writestr('LISEZ-MOI.txt', '\n'.join(lignes))
        for kind, src in files.items():
            src = Path(src)
            if src.exists():
                z.write(src, f'pieces/{kind}{src.suffix}')
    return out_path


# ---------------------------------------------------------------------------
# Calibration : `python app/dossier.py`
# La question n'est pas « le ZIP se crée » mais « un dossier incomplet est-il
# déclaré incomplet ».
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    d = Dossier(
        reference=reference_for(9520.0, '2026-05-12', 'SARL Untel'),
        created_at=datetime.now().isoformat(timespec='seconds'),
        creancier='Menuiserie Ahmed', debiteur='SARL Untel',
        montant_tnd=9520.0, invoice_date='2026-05-12',
    )
    print('référence     :', d.reference)
    print('statut vide   :', d.statut, '| manquants:', d.manquants())

    d.pieces.append(Piece('facture', 'facture_ahmed.pdf', 'a' * 64, 50000))
    print('avec facture  :', d.statut, '| manquants:', d.manquants())

    d.pieces.append(Piece('mise_en_demeure', 'mise_en_demeure.pdf', 'b' * 64, 50406))
    print('avec MED      :', d.statut, '| manquants:', d.manquants())

    d.pieces.append(Piece('contrat', 'joining_instructions.pdf', 'c' * 64, 248620,
                          gate_ok=False,
                          gate_reason="ce document est un programme d'événement"))
    print('avec intrus   :', d.statut,
          '| refusées:', [p.filename for p in d.pieces_refusees()])

    ok = (d.statut == 'pieces_refusees'
          and reference_for(9520.0, '2026-05-12', 'SARL Untel')
          == reference_for(9520.0, '2026-05-12', 'SARL Untel'))
    print('\nCALIBRATION', 'OK' if ok else 'ÉCHEC')
