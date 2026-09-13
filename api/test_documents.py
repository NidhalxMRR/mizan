"""Les deux endpoints du brief §4, vus depuis le réseau.

Ce qui est vérifié ici n'est pas « l'endpoint répond 200 » mais « ce qui sort
du serveur tient juridiquement ». Trois engagements :

- le document livré porte la mention « projet — non signifié » ;
- ses articles sont ceux du moteur, avec leur citation arabe exacte ;
- une créance prescrite est refusée, avec un motif exploitable.

Et pour le greffe : la réponse HTTP ne contient rien qu'un greffier n'ait à
connaître pour instruire la recevabilité.
"""
import json

import pytest
from fastapi.testclient import TestClient

from api.main import app
from packages.legal import greffe
from packages.legal.legal_engine import SOURCES

client = TestClient(app)

# Le dossier d'Ahmed, tel qu'il sera montré en démonstration.
AHMED = {
    'montant_tnd': 9520.0,
    'date_facture': '2026-05-12',
    'activite': 'menuiserie',
    'creancier_nom': 'Menuiserie Ahmed',
    'debiteur_nom': 'Société El Amen SARL',
    'creancier_ville': 'Sfax',
    'numero_facture': '2026-041',
    'aujourdhui': '2026-09-13',
}


@pytest.fixture
def file_greffe(tmp_path, monkeypatch):
    monkeypatch.setenv('MIZAN_GREFFE_DIR', str(tmp_path / 'greffe'))
    return tmp_path


# ---------------------------------------------------------------------------
# POST /documents/mise-en-demeure
# ---------------------------------------------------------------------------

def test_lendpoint_rend_le_projet_dacte_avec_sa_mention():
    r = client.post('/documents/mise-en-demeure', json=AHMED)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['mention_projet'] == 'PROJET — NON SIGNIFIÉ'
    assert 'PROJET — NON SIGNIFIÉ' in d['texte'], (
        "La mention figure dans un champ mais pas dans le texte livré : un "
        "copier-coller du texte perdrait l'avertissement."
    )
    assert d['signifie'] is False


def test_la_reponse_dit_que_seul_un_huissier_signifie():
    d = client.post('/documents/mise-en-demeure', json=AHMED).json()
    assert 'huissier de justice' in d['mention_projet_longue']
    assert 'عدل منفذ' in d['mention_projet_longue']


def test_les_articles_livres_portent_leur_citation_arabe_exacte():
    d = client.post('/documents/mise-en-demeure', json=AHMED).json()
    assert d['articles'], "Aucun article cité."
    for a in d['articles']:
        attendue = next(
            s['citation_ar'] for s in SOURCES.values()
            if s['code_id'] == a['code_id'] and s['article'] == a['article']
        )
        assert a['citation_ar'] == attendue, (
            f"{a['short_fr']} : citation altérée en transit."
        )
    courts = [a['short_fr'] for a in d['articles']]
    assert 'COC art. 403' in courts, courts
    assert 'CPCC art. 60' in courts, courts
    assert d['origine'] == 'moteur_deterministe'


def test_refus_409_sur_une_creance_prescrite():
    """On ne met pas en demeure sur une créance éteinte."""
    prescrit = {**AHMED, 'date_facture': '2024-05-12'}
    r = client.post('/documents/mise-en-demeure', json=prescrit)
    assert r.status_code == 409, r.text
    motif = r.json()['detail']
    assert 'prescrite' in motif.lower()
    assert 'interrompu' in motif.lower(), (
        "Le refus doit indiquer la seule porte de sortie légitime."
    )


def test_refus_400_sur_une_facture_datee_de_demain():
    """Le refus du moteur remonte en 400, pas en 500."""
    futur = {**AHMED, 'date_facture': '2026-12-31'}
    r = client.post('/documents/mise-en-demeure', json=futur)
    assert r.status_code == 400, r.text
    assert 'après' in r.json()['detail']


def test_refus_sur_un_montant_nul():
    r = client.post('/documents/mise-en-demeure', json={**AHMED, 'montant_tnd': 0})
    assert r.status_code == 422, r.text


def test_refus_sur_une_date_illisible():
    r = client.post('/documents/mise-en-demeure',
                    json={**AHMED, 'date_facture': '12/05/2026'})
    assert r.status_code == 400, r.text


def test_le_document_contient_les_parties_et_le_montant():
    d = client.post('/documents/mise-en-demeure', json=AHMED).json()
    assert 'Menuiserie Ahmed' in d['texte']
    assert 'Société El Amen SARL' in d['texte']
    assert d['montant_fr'] == '9\u00a0520,000'
    assert d['huissier_requis'] is True
    assert d['delai_jours'] == 5
    assert d['delai_est_legal'] is True
    assert d['date_limite'] == '2026-09-18'


def test_le_texte_ne_contient_aucune_formule_de_signification_accomplie():
    d = client.post('/documents/mise-en-demeure', json=AHMED).json()
    bas = d['texte'].lower()
    for interdit in ('a été signifié', 'acte signifié', 'dûment signifié'):
        assert interdit not in bas, interdit


def test_le_champ_mention_est_obligatoire_dans_le_schema():
    """Le contrat OpenAPI lui-même interdit un document sans mention."""
    schema = client.get('/openapi.json').json()
    modele = schema['components']['schemas']['MiseEnDemeureRendue']
    assert 'mention_projet' in modele['required'], (
        "La mention n'est plus obligatoire dans le schéma : un document sans "
        "elle pourrait être sérialisé."
    )
    assert 'texte' in modele['required']


# ---------------------------------------------------------------------------
# GET /greffe/dossiers
# ---------------------------------------------------------------------------

MANIFESTE = {
    'reference': 'MZ-API-0001',
    'statut': 'complet',
    'parties': {
        'creancier': 'Menuiserie Ahmed',
        'debiteur': 'Société El Amen SARL',
        'creancier_telephone': '+216 98 123 456',
        'creancier_rib': 'TN59 1000 6035 0000 1234 5678',
    },
    'creance': {'montant_tnd': 9520.0, 'date_facture': '2026-05-12'},
    'prescription': {'regime': 'goods_1y', 'deadline': '2027-05-12',
                     'days_left': 241, 'is_expired': False,
                     'regime_reason_fr': 'Marchandises livrées.'},
    'pieces': [
        {'kind': 'facture', 'filename': 'f.pdf', 'sha256': 'a' * 64,
         'n_bytes': 5000, 'gate_ok': True,
         'texte_extrait': 'FACTURE N° 2026-041 montant 9520'},
        {'kind': 'mise_en_demeure', 'filename': 'm.pdf', 'sha256': 'b' * 64,
         'n_bytes': 5000, 'gate_ok': True},
    ],
    'pieces_manquantes': [],
    'fondement_juridique': [
        {'code_id': 'coc', 'article': 403,
         'citation_ar': 'الفصل 403 من مجلة الالتزامات والعقود',
         'label_fr': "Prescription d'un an", 'short_fr': 'COC art. 403'},
    ],
    'notes_privees_creancier': 'Ne pas ébruiter.',
}

MANIFESTE_BLOQUE = {
    'reference': 'MZ-API-0002',
    'statut': 'incomplet',
    'parties': {'creancier': 'Imprimerie Carthage', 'debiteur': 'Média Plus'},
    'creance': {'montant_tnd': 14200.0, 'date_facture': '2025-11-08'},
    'prescription': {'regime': 'goods_1y', 'deadline': '2026-11-08',
                     'days_left': 56, 'is_expired': False,
                     'regime_reason_fr': 'Marchandises livrées.'},
    'pieces': [],
    'pieces_manquantes': [{'kind': 'facture', 'label': 'Facture',
                           'obligatoire': True,
                           'pourquoi': 'CPC art. 59 : créance déterminée.'}],
    'fondement_juridique': [],
}


def test_le_tableau_greffier_rend_la_file_et_sa_charge(file_greffe):
    greffe.deposer(MANIFESTE)
    greffe.deposer(MANIFESTE_BLOQUE)
    r = client.get('/greffe/dossiers')
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['charge']['total'] == 2
    assert d['charge']['instruisables'] == 1
    assert d['charge']['renvoyes'] == 1
    refs = [x['reference'] for x in d['dossiers']]
    assert refs == ['MZ-API-0001', 'MZ-API-0002'], (
        f"L'instruisable doit passer en tête : {refs}"
    )


def test_lendpoint_greffe_nexpose_pas_ce_qui_ne_le_regarde_pas(file_greffe):
    greffe.deposer(MANIFESTE)
    corps = json.dumps(client.get('/greffe/dossiers').json(), ensure_ascii=False)
    for valeur in ('+216 98 123 456', 'TN59 1000 6035 0000 1234 5678',
                   'FACTURE N° 2026-041', 'Ne pas ébruiter'):
        assert valeur not in corps, (
            f"L'API du greffe expose « {valeur} », hors du périmètre du "
            f"contrôle de recevabilité."
        )


def test_le_greffier_voit_ce_quil_doit_controler(file_greffe):
    greffe.deposer(MANIFESTE_BLOQUE)
    d = client.get('/greffe/dossiers').json()['dossiers'][0]
    bloquants = [c for c in d['controles_a_effectuer'] if c['bloquant']]
    assert bloquants, "Un dossier sans facture n'appelle aucun contrôle bloquant ?"
    assert 'Facture' in bloquants[0]['libelle']
    assert d['instruisable'] is False
    assert d['pieces_manquantes'][0]['label'] == 'Facture'


def test_les_empreintes_restent_visibles_pour_le_controle(file_greffe):
    """Restreindre la vue ne doit pas retirer l'outil de contrôle."""
    greffe.deposer(MANIFESTE)
    d = client.get('/greffe/dossiers').json()['dossiers'][0]
    assert {p['sha256'] for p in d['pieces']} == {'a' * 64, 'b' * 64}
    assert all(p['format'] == 'pdf' for p in d['pieces'])


def test_le_filtre_par_etat_fonctionne(file_greffe):
    greffe.deposer(MANIFESTE)
    greffe.deposer(MANIFESTE_BLOQUE)
    d = client.get('/greffe/dossiers', params={'etat': 'incomplet'}).json()
    assert [x['reference'] for x in d['dossiers']] == ['MZ-API-0002']
    assert d['charge']['total'] == 1


def test_un_etat_inconnu_est_refuse_en_400(file_greffe):
    r = client.get('/greffe/dossiers', params={'etat': 'classe_sans_suite'})
    assert r.status_code == 400
    assert 'classe_sans_suite' in r.json()['detail']


def test_la_file_vide_repond_200_et_le_dit(file_greffe):
    """Une file vide n'est pas une panne."""
    r = client.get('/greffe/dossiers')
    assert r.status_code == 200
    d = r.json()
    assert d['dossiers'] == []
    assert d['charge']['total'] == 0
    assert d['etats']  # le vocabulaire reste disponible pour l'écran


def test_le_tableau_porte_son_avertissement_de_perimetre(file_greffe):
    d = client.get('/greffe/dossiers').json()
    assert 'recevabilité' in d['avertissement']


# ---------------------------------------------------------------------------
# Les endpoints existants ne bougent pas
# ---------------------------------------------------------------------------

def test_les_endpoints_existants_repondent_toujours():
    """Brancher un routeur ne doit rien casser d'autre."""
    r = client.post('/dossiers/analyser', json={
        'montant_tnd': 9520.0, 'date_facture': '2026-05-12',
        'activite': 'menuiserie', 'aujourdhui': '2026-09-13'})
    assert r.status_code == 200
    assert r.json()['jours_restants'] == 241
