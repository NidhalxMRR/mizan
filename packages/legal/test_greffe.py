"""Ce que le tableau greffier montre — et surtout ce qu'il ne montre pas.

Le greffier du tribunal de commerce instruit la RECEVABILITÉ. Il contrôle
qu'une pièce obligatoire est présente, que son empreinte correspond au
fichier reçu, que la créance n'est pas prescrite. Rien dans ce métier
n'exige de lire le contenu des pièces, de connaître l'adresse personnelle du
gérant ou de voir ce que le créancier a écrit à l'assistant.

La projection est une liste blanche. Ces tests le vérifient de la seule façon
qui prouve quelque chose : en déposant un manifeste FARCI de champs
sensibles, puis en exigeant qu'aucun ne ressorte.
"""
import json

import pytest

from packages.legal import greffe


@pytest.fixture(autouse=True)
def file_isolee(tmp_path, monkeypatch):
    """Chaque test part d'une file vide, sur disque, hors de la vraie file."""
    monkeypatch.setenv('MIZAN_GREFFE_DIR', str(tmp_path / 'greffe'))
    yield


# Un manifeste réaliste, volontairement bavard : il porte tout ce qu'un
# dossier créancier peut contenir, y compris ce qui ne regarde pas le greffe.
MANIFESTE_BAVARD = {
    'schema_version': '1.0',
    'reference': 'MZ-20260913-A1B2',
    'created_at': '2026-09-13',
    'statut': 'complet',
    'parties': {
        'creancier': 'Menuiserie Ahmed',
        'debiteur': 'Société El Amen SARL',
        # Ce qui suit ne sert à aucun contrôle de recevabilité.
        'creancier_adresse': 'Route de Gabès km 3 — 3000 Sfax',
        'creancier_telephone': '+216 98 123 456',
        'creancier_email': 'ahmed@menuiserie-sfax.tn',
        'creancier_matricule_fiscal': '1234567/A/M/000',
        'creancier_rib': 'TN59 1000 6035 0000 1234 5678',
        'debiteur_telephone': '+216 71 000 000',
    },
    'creance': {'montant_tnd': 9520.0, 'date_facture': '2026-05-12'},
    'prescription': {
        'regime': 'goods_1y', 'deadline': '2027-05-12', 'days_left': 241,
        'is_expired': False, 'regime_reason_fr': 'Marchandises livrées.',
        # Champ interne qui n'a rien à faire au greffe.
        'note_interne': 'client fragile, relancer doucement',
    },
    'pieces': [
        {
            'kind': 'facture', 'filename': 'facture_2026_041.pdf',
            'sha256': 'a' * 64, 'n_bytes': 50000, 'gate_ok': True,
            'gate_reason': None, 'source_method': 'upload',
            # Le contenu extrait : c'est exactement ce qui ne doit pas sortir.
            'texte_extrait': 'FACTURE N° 2026-041 — Menuiserie Ahmed — '
                             'RIB TN59 1000 6035 0000 1234 5678',
            'client_extrait': 'Société El Amen SARL',
            'chemin_disque': '/home/nidhal/mizan/data/uploads/facture.pdf',
        },
        {
            'kind': 'mise_en_demeure', 'filename': 'mise_en_demeure.pdf',
            'sha256': 'b' * 64, 'n_bytes': 50406, 'gate_ok': True,
            'texte_extrait': 'Vous restez redevable de 9 520,000 DT…',
        },
    ],
    'pieces_manquantes': [],
    'fondement_juridique': [
        {'code_id': 'coc', 'article': 403,
         'citation_ar': 'الفصل 403 من مجلة الالتزامات والعقود',
         'label_fr': "Prescription d'un an — prix des marchandises livrées",
         'short_fr': 'COC art. 403'},
    ],
    # Le canal privé entre la PME et l'assistant : hors du dossier.
    'conversation_assistant': [
        {'role': 'user', 'contenu': "Je crois que j'ai perdu le bon de livraison"},
    ],
    'notes_privees_creancier': 'Ne pas ébruiter, on travaille encore avec eux.',
    'avertissement': 'Chaque article cité a été relu dans le corpus indexé.',
}

MANIFESTE_INCOMPLET = {
    'reference': 'MZ-20260913-C3D4',
    'statut': 'incomplet',
    'parties': {'creancier': 'Imprimerie Carthage Print',
                'debiteur': 'Agence Média Plus'},
    'creance': {'montant_tnd': 14200.0, 'date_facture': '2025-11-08'},
    'prescription': {'regime': 'goods_1y', 'deadline': '2026-11-08',
                     'days_left': 56, 'is_expired': False,
                     'regime_reason_fr': 'Marchandises livrées.'},
    'pieces': [{'kind': 'mise_en_demeure', 'filename': 'med.pdf',
                'sha256': 'c' * 64, 'n_bytes': 40000, 'gate_ok': True}],
    'pieces_manquantes': [
        {'kind': 'facture', 'label': 'Facture', 'obligatoire': True,
         'pourquoi': "CPC art. 59 : l'injonction de payer suppose une créance "
                     "déterminée d'origine contractuelle."},
    ],
    'fondement_juridique': [],
}

MANIFESTE_PRESCRIT = {
    'reference': 'MZ-20260913-E5F6',
    'statut': 'complet',
    'parties': {'creancier': 'Atelier Bouzid', 'debiteur': 'Confections SA'},
    'creance': {'montant_tnd': 3150.0, 'date_facture': '2024-01-10'},
    'prescription': {'regime': 'goods_1y', 'deadline': '2025-01-09',
                     'days_left': -612, 'is_expired': True,
                     'regime_reason_fr': 'Marchandises livrées.'},
    'pieces': [{'kind': 'facture', 'filename': 'f.pdf', 'sha256': 'd' * 64,
                'n_bytes': 1000, 'gate_ok': True},
               {'kind': 'mise_en_demeure', 'filename': 'm.pdf',
                'sha256': 'e' * 64, 'n_bytes': 1000, 'gate_ok': True}],
    'pieces_manquantes': [],
    'fondement_juridique': [],
}


# --- Ce que le greffier n'a PAS le droit de voir -----------------------------

# Chaque entrée est une valeur réellement présente dans MANIFESTE_BAVARD.
# Chercher la VALEUR et non le nom du champ est le seul contrôle honnête :
# renommer un champ ne doit pas suffire à faire passer le test.
VALEURS_INTERDITES = [
    ('téléphone du créancier', '+216 98 123 456'),
    ('courriel du créancier', 'ahmed@menuiserie-sfax.tn'),
    ('RIB du créancier', 'TN59 1000 6035 0000 1234 5678'),
    ('matricule fiscal', '1234567/A/M/000'),
    ('adresse postale du créancier', 'Route de Gabès km 3'),
    ('téléphone du débiteur', '+216 71 000 000'),
    ('contenu extrait de la facture', 'FACTURE N° 2026-041'),
    ('contenu extrait de la mise en demeure', 'Vous restez redevable'),
    ('chemin du fichier sur le disque', '/home/nidhal/mizan/data/uploads'),
    ('conversation avec l\'assistant', "j'ai perdu le bon de livraison"),
    ('notes privées du créancier', 'Ne pas ébruiter'),
    ('note interne sur le débiteur', 'client fragile'),
]


def test_le_tableau_greffier_nexpose_aucune_donnee_interdite():
    """Le test qui compte : on dépose tout, on vérifie que rien ne fuit."""
    greffe.deposer(MANIFESTE_BAVARD)
    rendu = json.dumps(greffe.tableau(), ensure_ascii=False)
    fuites = [nom for nom, valeur in VALEURS_INTERDITES if valeur in rendu]
    assert not fuites, (
        "Le tableau greffier expose des données hors de son périmètre : "
        + ', '.join(fuites)
    )


def test_la_projection_est_une_liste_blanche_pas_une_liste_noire():
    """Un champ inconnu ajouté demain ne doit pas sortir tout seul.

    C'est la différence entre les deux approches : une liste noire laisse
    passer tout ce qu'on n'a pas prévu, et on ne prévoit jamais tout.
    """
    manifeste = dict(MANIFESTE_BAVARD)
    manifeste['reference'] = 'MZ-20260913-NEUF'
    manifeste['champ_invente_demain'] = 'SECRET-INATTENDU-42'
    manifeste['parties'] = {**manifeste['parties'],
                            'creancier_cin': 'CIN-09876543'}
    greffe.deposer(manifeste)
    rendu = json.dumps(greffe.tableau(), ensure_ascii=False)
    assert 'SECRET-INATTENDU-42' not in rendu
    assert 'CIN-09876543' not in rendu


def test_les_pieces_ne_montrent_que_ce_qui_se_controle():
    greffe.deposer(MANIFESTE_BAVARD)
    dossier = greffe.tableau()['dossiers'][0]
    facture = next(p for p in dossier['pieces'] if p['kind'] == 'facture')
    autorises = set(greffe.CHAMPS_PIECE) | {'format'}
    assert set(facture) <= autorises, (
        f"Champs non autorisés sur une pièce : {set(facture) - autorises}"
    )
    # L'empreinte reste : c'est elle qui permet le contrôle d'intégrité.
    assert facture['sha256'] == 'a' * 64
    assert facture['format'] == 'pdf'


# --- Ce que le greffier DOIT voir --------------------------------------------

def test_les_parties_sont_nommees_le_montant_et_la_date_sont_la():
    """Restreindre n'est pas mutiler : le contrôle doit rester possible."""
    greffe.deposer(MANIFESTE_BAVARD)
    d = greffe.tableau()['dossiers'][0]
    assert d['parties'] == {'creancier': 'Menuiserie Ahmed',
                            'debiteur': 'Société El Amen SARL'}
    assert d['creance']['montant_tnd'] == 9520.0
    assert d['creance']['date_facture'] == '2026-05-12'
    assert d['prescription']['deadline'] == '2027-05-12'
    assert d['prescription']['days_left'] == 241


def test_un_dossier_incomplet_nomme_la_piece_qui_manque_et_pourquoi():
    greffe.deposer(MANIFESTE_INCOMPLET)
    d = greffe.tableau()['dossiers'][0]
    assert d['instruisable'] is False
    assert d['etat'] == 'incomplet'
    manquante = d['pieces_manquantes'][0]
    assert manquante['label'] == 'Facture'
    assert 'art. 59' in manquante['pourquoi']


def test_le_controle_des_pieces_manquantes_est_bloquant():
    """Un contrôle affiché sans dire qu'il bloque n'oriente aucune décision."""
    greffe.deposer(MANIFESTE_INCOMPLET)
    d = greffe.tableau()['dossiers'][0]
    c = next(x for x in d['controles_a_effectuer']
             if x['controle'] == 'pieces_obligatoires')
    assert c['bloquant'] is True
    assert 'Facture' in c['libelle']


def test_une_creance_prescrite_leve_un_controle_bloquant_chiffre():
    greffe.deposer(MANIFESTE_PRESCRIT)
    d = greffe.tableau()['dossiers'][0]
    c = next(x for x in d['controles_a_effectuer']
             if x['controle'] == 'prescription')
    assert c['bloquant'] is True
    assert '612' in c['libelle'], c['libelle']
    assert '2025-01-09' in c['libelle']


def test_un_dossier_incomplet_ne_peut_pas_etre_declare_recevable():
    """Le bouton absent vaut mieux que le refus après coup."""
    greffe.deposer(MANIFESTE_INCOMPLET)
    d = greffe.tableau()['dossiers'][0]
    etats = {a['etat'] for a in d['actions_possibles']}
    assert 'recevable' not in etats, (
        "Le greffe propose de déclarer recevable un dossier dont il sait "
        "qu'une pièce obligatoire manque."
    )
    assert etats == {'incomplet'}


def test_un_dossier_complet_ouvre_les_trois_orientations():
    greffe.deposer(MANIFESTE_BAVARD)
    d = greffe.tableau()['dossiers'][0]
    etats = {a['etat'] for a in d['actions_possibles']}
    assert etats == {'recevable', 'mediation', 'injonction'}


def test_le_fondement_juridique_conserve_la_citation_arabe():
    """Le greffier doit pouvoir vérifier l'article, donc le lire."""
    greffe.deposer(MANIFESTE_BAVARD)
    d = greffe.tableau()['dossiers'][0]
    a = d['fondement_juridique'][0]
    assert a['citation_ar'] == 'الفصل 403 من مجلة الالتزامات والعقود'
    assert a['short_fr'] == 'COC art. 403'


# --- L'ordre de la file ------------------------------------------------------

def test_les_instruisables_passent_avant_les_dossiers_bloques():
    greffe.deposer(MANIFESTE_INCOMPLET)
    greffe.deposer(MANIFESTE_BAVARD)
    dossiers = greffe.tableau()['dossiers']
    instruisables = [d['instruisable'] for d in dossiers]
    assert instruisables == sorted(instruisables, reverse=True), instruisables


def test_le_tri_suit_lecheance_pas_la_date_de_depot():
    """Le dossier le plus urgent d'abord, même déposé en dernier."""
    lointain = {**MANIFESTE_BAVARD, 'reference': 'MZ-LOINTAIN'}
    proche = {**MANIFESTE_BAVARD, 'reference': 'MZ-PROCHE',
              'prescription': {**MANIFESTE_BAVARD['prescription'],
                               'days_left': 12}}
    greffe.deposer(lointain)   # déposé en premier, échéance lointaine
    greffe.deposer(proche)     # déposé ensuite, échéance proche
    refs = [d['reference'] for d in greffe.tableau()['dossiers']]
    assert refs[0] == 'MZ-PROCHE', refs


def test_une_creance_prescrite_remonte_en_tete():
    """Une mauvaise nouvelle s'annonce vite, elle ne se classe pas."""
    greffe.deposer(MANIFESTE_BAVARD)
    greffe.deposer(MANIFESTE_PRESCRIT)
    d = greffe.tableau()['dossiers'][0]
    assert d['prescription']['is_expired'] is True


# --- Le cycle de vie, repris de h4j ------------------------------------------

def test_un_depot_incomplet_est_renvoye_sans_examen():
    rec = greffe.deposer(MANIFESTE_INCOMPLET)
    assert rec['etat'] == 'incomplet'


def test_completer_un_dossier_le_sort_de_la_file_des_renvois():
    """Le comportement de h4j, conservé et verrouillé.

    Sans lui, le créancier ajoute la pièce et le greffe continue d'afficher
    « incomplet » : le dossier reste bloqué pour une raison qui n'existe plus.
    """
    rec = greffe.deposer(MANIFESTE_INCOMPLET)
    assert rec['etat'] == 'incomplet'
    complete = {**MANIFESTE_INCOMPLET, 'pieces_manquantes': []}
    rec = greffe.deposer(complete)
    assert rec['etat'] == 'recu'
    assert any(e['action'] == 'piece_ajoutee' for e in rec['journal'])


def test_le_depot_est_idempotent_sur_la_reference():
    greffe.deposer(MANIFESTE_BAVARD)
    greffe.deposer(MANIFESTE_BAVARD)
    assert len(greffe.tableau()['dossiers']) == 1


def test_un_changement_detat_est_journalise_et_visible():
    greffe.deposer(MANIFESTE_BAVARD)
    greffe.changer_etat('MZ-20260913-A1B2', 'recevable',
                        note='pièces contrôlées')
    d = greffe.tableau()['dossiers'][0]
    assert d['etat'] == 'recevable'
    assert d['etat_libelle'] == 'Examiné — recevable'
    dernier = d['journal'][-1]
    assert dernier['action'] == 'changement_etat'
    assert dernier['par'] == 'greffier'
    assert dernier['note'] == 'pièces contrôlées'


def test_un_etat_inconnu_est_refuse():
    greffe.deposer(MANIFESTE_BAVARD)
    with pytest.raises(ValueError):
        greffe.changer_etat('MZ-20260913-A1B2', 'classe_sans_suite')


def test_la_charge_est_chiffree():
    greffe.deposer(MANIFESTE_BAVARD)
    greffe.deposer(MANIFESTE_INCOMPLET)
    greffe.deposer(MANIFESTE_PRESCRIT)
    charge = greffe.tableau()['charge']
    assert charge['total'] == 3
    assert charge['instruisables'] == 2
    assert charge['renvoyes'] == 1
    assert charge['prescrits'] == 1


def test_le_chiffre_du_brief_est_marque_comme_hypothese():
    """Un gain de temps non mesuré ne se présente pas comme une mesure."""
    stats = greffe.tableau()['statistiques']
    assert stats['minutes_par_dossier'] == 65
    assert 'hypothèse' in stats['statut_chiffre']
