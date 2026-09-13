"""Le greffe : ce qu'un officier public reçoit, et ce qu'il en fait.

Repris du dépôt h4j (app/greffe.py). Le cycle de vie, le tri par échéance et
la journalisation sont conservés tels quels — ils marchaient, et les raisons
écrites dans les commentaires d'origine tiennent toujours.

Ce qui a été ajouté ici : la VUE GREFFIER.

La version h4j exposait `lister()`, c'est-à-dire le manifeste complet du
dossier, à qui appelait l'endpoint. C'était acceptable dans un prototype à un
seul écran ; ça ne l'est plus dès que le greffe devient un poste distinct du
poste créancier. Un greffier instruit la RECEVABILITÉ : il contrôle qu'une
pièce obligatoire est présente, que son empreinte correspond, que la créance
n'est pas prescrite. Il n'a pas à connaître le contenu extrait des pièces, ni
les coordonnées personnelles des parties, ni ce que le créancier a pu écrire
à l'assistant.

La projection est donc une LISTE BLANCHE, pas une liste noire. Un champ
nouveau ajouté un jour au manifeste n'apparaîtra pas au greffe tant que
personne n'aura décidé qu'il doit y apparaître. L'inverse — retirer les
champs connus comme sensibles — laisse fuir tout ce qu'on n'a pas prévu.

Persistance volontairement en JSON sur disque : la VPS est partagée, un
serveur de base de données de plus serait une dépendance de démo. Le format
est le manifeste du dossier, tel quel — ce que le greffe lit est exactement
ce que le créancier a déposé.
"""
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

# packages/legal/greffe.py -> packages/legal -> packages -> racine du dépôt.
ROOT = Path(__file__).resolve().parents[2]

_LOCK = threading.Lock()

# Le cycle de vie d'un dossier côté greffe. Volontairement court : chaque
# état correspond à une action réelle d'un officier public, pas à un statut
# décoratif.
ETATS = {
    'recu': "Reçu — en attente d'examen",
    'recevable': 'Examiné — recevable',
    'incomplet': 'Renvoyé au demandeur — pièces manquantes',
    'mediation': 'Orienté vers la médiation',
    'injonction': "Transmis pour injonction de payer",
}


def greffe_dir():
    """Le répertoire de la file. Surchargeable pour les tests.

    Résolu à l'appel et non à l'import : un test qui fixe MIZAN_GREFFE_DIR ne
    doit pas dépendre de l'ordre des imports pour être isolé de la vraie file.
    """
    d = Path(os.environ.get('MIZAN_GREFFE_DIR') or (ROOT / 'data' / 'greffe'))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(reference):
    safe = ''.join(c for c in reference if c.isalnum() or c in '-_')
    return greffe_dir() / f'{safe}.json'


def deposer(manifest):
    """Enregistre un dossier au greffe. Idempotent sur la référence."""
    ref = manifest['reference']
    with _LOCK:
        p = _path(ref)
        if p.exists():
            existing = json.loads(p.read_text(encoding='utf-8'))
            existing['manifest'] = manifest
            existing['updated_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')

            # Un dossier complété après coup doit ressortir de la file des
            # renvois. Sans cela, le créancier ajoute la pièce manquante et le
            # greffe continue d'afficher « incomplet » — le dossier reste
            # bloqué pour une raison qui n'existe plus.
            manque = bool(manifest.get('pieces_manquantes'))
            if existing.get('etat') in ('recu', 'incomplet'):
                nouvel_etat = 'incomplet' if manque else 'recu'
                if nouvel_etat != existing['etat']:
                    existing['etat'] = nouvel_etat
                    existing.setdefault('journal', []).append({
                        'at': existing['updated_at'],
                        'action': 'piece_ajoutee' if not manque else 'piece_retiree',
                        'etat': nouvel_etat,
                        'par': 'demandeur',
                    })

            p.write_text(json.dumps(existing, ensure_ascii=False, indent=2),
                         encoding='utf-8')
            return existing

        # Un dossier dont les pièces obligatoires manquent n'entre pas dans la
        # file d'examen : il est renvoyé immédiatement. C'est la version greffe
        # de l'abstention — ne pas faire semblant d'instruire.
        etat = 'incomplet' if manifest.get('pieces_manquantes') else 'recu'
        maintenant = datetime.now(timezone.utc).isoformat(timespec='seconds')
        rec = {
            'reference': ref,
            'etat': etat,
            'deposited_at': maintenant,
            'updated_at': maintenant,
            'journal': [{
                'at': maintenant,
                'action': 'depot',
                'etat': etat,
                'par': 'demandeur',
            }],
            'manifest': manifest,
        }
        p.write_text(json.dumps(rec, ensure_ascii=False, indent=2),
                     encoding='utf-8')
        return rec


def lister():
    """La file, triée : l'instruisable d'abord, puis le plus urgent.

    Le tri par date de dépôt était le réflexe administratif — mais il fait
    traiter en premier le dossier arrivé en premier, pas celui qui va se
    prescrire. Sur la file de test, un dossier à 242 jours passait après un
    dossier à 5 408 jours au seul motif qu'il avait été déposé plus tôt.

    Ce qui ordonne la journée d'un greffier, c'est l'échéance. Le dépôt ne
    sert plus que de départage à égalité.

    Attention : cette fonction rend le dossier COMPLET, manifeste inclus.
    C'est l'usage interne. Ce qui sort par l'API passe par `tableau()`.
    """
    out = []
    for f in greffe_dir().glob('*.json'):
        try:
            out.append(json.loads(f.read_text(encoding='utf-8')))
        except Exception:
            continue

    def clef(r):
        m = r.get('manifest', {})
        pret = 0 if not m.get('pieces_manquantes') else 1
        presc = m.get('prescription') or {}
        # Une créance déjà prescrite remonte en tête du groupe : c'est une
        # mauvaise nouvelle à annoncer vite, pas un dossier à classer.
        jours = -1 if presc.get('is_expired') else presc.get('days_left')
        if jours is None:
            jours = 10 ** 6
        return (pret, jours, r.get('deposited_at', ''))

    return sorted(out, key=clef)


def lire(reference):
    p = _path(reference)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding='utf-8'))


def changer_etat(reference, etat, par='greffier', note=None):
    """Transition d'état, journalisée. Refuse un état inconnu."""
    if etat not in ETATS:
        raise ValueError(f'état inconnu : {etat}')
    with _LOCK:
        rec = lire(reference)
        if not rec:
            return None
        rec['etat'] = etat
        rec['updated_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        entry = {
            'at': rec['updated_at'],
            'action': 'changement_etat',
            'etat': etat,
            'par': par,
        }
        if note:
            entry['note'] = note
        rec.setdefault('journal', []).append(entry)
        _path(reference).write_text(
            json.dumps(rec, ensure_ascii=False, indent=2), encoding='utf-8')
        return rec


# ---------------------------------------------------------------------------
# La vue greffier : la liste blanche
# ---------------------------------------------------------------------------

# Ce qu'un greffier contrôle sur une pièce : son type, son nom, son empreinte,
# sa taille, et le verdict de la porte d'entrée. Pas son contenu. L'empreinte
# suffit à établir que la pièce reçue est celle qui a été déposée — c'est
# exactement le contrôle que le greffe doit pouvoir faire, et il n'exige pas
# de lire le document.
CHAMPS_PIECE = ('kind', 'label', 'sha256', 'n_bytes', 'gate_ok', 'gate_reason')

# Ce qu'un greffier contrôle sur la prescription. `motif_fr` explique le
# régime retenu ; il vient du moteur déterministe, pas d'une saisie.
CHAMPS_PRESCRIPTION = ('regime', 'deadline', 'days_left', 'is_expired',
                       'regime_reason_fr')

# Les parties sont nommées — elles figurent sur l'acte. Leurs coordonnées,
# elles, ne servent à aucun contrôle de recevabilité : le greffe n'a pas à
# détenir l'adresse, le téléphone ou le matricule fiscal du créancier pour
# décider si un dossier est instruisable.
CHAMPS_PARTIE = ('creancier', 'debiteur')

# Ce que le greffier doit CONTRÔLER, nommé explicitement. Un tableau qui
# affiche un état sans dire quel contrôle il appelle laisse le greffier
# deviner sa propre tâche.
CONTROLES = {
    'pieces_obligatoires': "Vérifier que la facture et la mise en demeure "
                           "figurent au dossier (CPCC art. 59 et 60).",
    'empreintes': "Contrôler que l'empreinte SHA-256 de chaque pièce "
                  "correspond au fichier reçu.",
    'prescription': "Vérifier que la créance n'est pas prescrite avant "
                    "d'ouvrir l'instruction.",
    'qualite_des_parties': "Vérifier la qualité et l'identité des parties sur "
                           "les pièces produites.",
    'orientation': "Décider de l'orientation : médiation ou injonction de "
                   "payer.",
}


def _projeter_piece(p):
    out = {k: p[k] for k in CHAMPS_PIECE if k in p}
    # `filename` est utile au greffier pour retrouver la pièce, mais il peut
    # porter un nom parlant (« releve_bancaire_ahmed.pdf »). On garde
    # l'extension, qui dit le format, et rien de plus.
    nom = p.get('filename')
    if nom:
        out['format'] = Path(nom).suffix.lstrip('.').lower() or 'inconnu'
    return out


def vue_greffier(rec):
    """Projette un dossier sur ce qu'un greffier a le droit de voir.

    Liste blanche stricte : tout champ non nommé ici ne sort pas, même s'il
    existe dans le manifeste. C'est la seule façon de garantir qu'un champ
    ajouté demain côté créancier ne se retrouve pas sur l'écran du greffe.
    """
    m = rec.get('manifest', {}) or {}
    parties = m.get('parties', {}) or {}
    presc = m.get('prescription', {}) or {}
    manquantes = m.get('pieces_manquantes', []) or []

    return {
        'reference': rec.get('reference'),
        'etat': rec.get('etat'),
        'etat_libelle': ETATS.get(rec.get('etat'), rec.get('etat')),
        'depose_le': rec.get('deposited_at'),
        'mis_a_jour_le': rec.get('updated_at'),
        'statut_depot': m.get('statut'),
        'parties': {k: parties.get(k) for k in CHAMPS_PARTIE
                    if parties.get(k) is not None},
        'creance': {
            'montant_tnd': (m.get('creance') or {}).get('montant_tnd'),
            'date_facture': (m.get('creance') or {}).get('date_facture'),
        },
        'prescription': {k: presc[k] for k in CHAMPS_PRESCRIPTION
                         if k in presc},
        'pieces': [_projeter_piece(p) for p in (m.get('pieces') or [])],
        'pieces_manquantes': [
            {'kind': x.get('kind'), 'label': x.get('label'),
             'pourquoi': x.get('pourquoi')}
            for x in manquantes
        ],
        'instruisable': not manquantes,
        'fondement_juridique': [
            {k: a.get(k) for k in
             ('code_id', 'article', 'citation_ar', 'label_fr', 'short_fr')}
            for a in (m.get('fondement_juridique') or [])
        ],
        'controles_a_effectuer': _controles_pour(m, manquantes, presc),
        'journal': [
            {k: e.get(k) for k in ('at', 'action', 'etat', 'par', 'note')
             if e.get(k) is not None}
            for e in (rec.get('journal') or [])
        ],
        'actions_possibles': _actions_pour(rec.get('etat'), manquantes),
    }


def _controles_pour(manifest, manquantes, prescription):
    """Ce que CE dossier appelle comme contrôle, pas la liste générique."""
    out = []
    if manquantes:
        noms = ', '.join(x.get('label') or x.get('kind') or '?'
                         for x in manquantes)
        out.append({
            'controle': 'pieces_obligatoires',
            'libelle': f"Pièce(s) obligatoire(s) absente(s) : {noms}. "
                       f"Renvoyer au demandeur avant tout examen.",
            'bloquant': True,
        })
    else:
        out.append({'controle': 'pieces_obligatoires',
                    'libelle': CONTROLES['pieces_obligatoires'],
                    'bloquant': False})
    if manifest.get('pieces'):
        out.append({'controle': 'empreintes',
                    'libelle': CONTROLES['empreintes'], 'bloquant': False})
    if prescription.get('is_expired'):
        out.append({
            'controle': 'prescription',
            'libelle': f"Créance prescrite depuis "
                       f"{abs(prescription.get('days_left', 0))} jours "
                       f"(échéance : {prescription.get('deadline')}). "
                       f"Ne pas ouvrir l'instruction sans l'avoir signalé.",
            'bloquant': True,
        })
    elif prescription.get('days_left') is not None:
        out.append({
            'controle': 'prescription',
            'libelle': f"{prescription['days_left']} jours avant prescription "
                       f"(échéance : {prescription.get('deadline')}).",
            'bloquant': False,
        })
    out.append({'controle': 'qualite_des_parties',
                'libelle': CONTROLES['qualite_des_parties'], 'bloquant': False})
    if not manquantes:
        out.append({'controle': 'orientation',
                    'libelle': CONTROLES['orientation'], 'bloquant': False})
    return out


def _actions_pour(etat, manquantes):
    """Les transitions ouvertes depuis l'état courant.

    Un dossier incomplet ne peut pas être déclaré recevable : proposer le
    bouton reviendrait à inviter le greffier à instruire un dossier que le
    système sait incomplet.
    """
    if manquantes:
        return [{'etat': 'incomplet', 'libelle': ETATS['incomplet']}]
    ouvertes = [e for e in ('recevable', 'mediation', 'injonction')
                if e != etat]
    return [{'etat': e, 'libelle': ETATS[e]} for e in ouvertes]


def tableau():
    """Le tableau greffier complet : la file projetée + la charge chiffrée."""
    dossiers = [vue_greffier(r) for r in lister()]
    return {
        'dossiers': dossiers,
        'etats': ETATS,
        'controles': CONTROLES,
        'charge': {
            'total': len(dossiers),
            'instruisables': sum(1 for d in dossiers if d['instruisable']),
            'renvoyes': sum(1 for d in dossiers if d['etat'] == 'incomplet'),
            'prescrits': sum(1 for d in dossiers
                             if d['prescription'].get('is_expired')),
        },
        'statistiques': statistiques(),
        'avertissement': (
            "Cette vue est restreinte aux éléments nécessaires au contrôle de "
            "recevabilité. Le contenu des pièces et les coordonnées des "
            "parties ne sont pas exposés au greffe."
        ),
    }


def statistiques():
    """Ce que la slide « The Agency Benefit » doit pouvoir citer.

    Les minutes économisées ne sont PAS une estimation marketing : ce sont les
    étapes manuelles que le dossier structuré supprime, chacune nommée.
    Tant qu'un officier public n'a pas validé ces durées, elles sont
    présentées comme une hypothèse à valider — jamais comme un fait mesuré.
    """
    dossiers = lister()
    complets = [d for d in dossiers
                if not d.get('manifest', {}).get('pieces_manquantes')]
    renvoyes = [d for d in dossiers if d.get('etat') == 'incomplet']

    # Étapes supprimées par un dépôt structuré, par dossier.
    ETAPES_SUPPRIMEES = [
        ('Réception et enregistrement du dossier papier', 12),
        ('Vérification pièce par pièce de la complétude', 15),
        ('Ressaisie des parties et du montant', 8),
        ('Recherche des textes applicables', 20),
        ('Classement physique et archivage', 10),
    ]
    return {
        'dossiers': len(dossiers),
        'instruisables': len(complets),
        'renvoyes_avant_examen': len(renvoyes),
        'etapes_supprimees': [
            {'etape': e, 'minutes': m} for e, m in ETAPES_SUPPRIMEES
        ],
        'minutes_par_dossier': sum(m for _, m in ETAPES_SUPPRIMEES),
        'statut_chiffre': 'hypothèse à valider par un officier public',
    }


if __name__ == '__main__':
    print(json.dumps(statistiques(), ensure_ascii=False, indent=2))
    print('\ndossiers au greffe :', len(lister()))
