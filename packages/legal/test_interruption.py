"""Tests de l'interruption de la prescription (COC art. 396 à 398).

Run: ./.venv/bin/python -m pytest packages/legal/test_interruption.py -q
"""
from datetime import date
import sys
import pathlib

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from interruption import (  # noqa: E402
    ActeImpossible,
    ActeInterruptif,
    appliquer,
    citations_corpus,
)
from legal_engine import assess  # noqa: E402

TODAY = date(2026, 9, 13)          # jour de la démo, figé pour le déterminisme
AHMED = dict(amount_tnd=9520, invoice_date='2026-05-12', activity='menuiserie')


def _articles(a):
    return {s['article'] for s in a.sources}


# --- 1. Sans acte : rien ne bouge -------------------------------------------

def test_sans_acte_le_resultat_est_identique_a_avant():
    """Le contrat d'origine ne bouge pas d'un jour."""
    a = assess(**AHMED, today=TODAY)
    assert a.days_left == 241
    assert a.deadline == '2027-05-12'
    assert a.interruption is None
    assert not a.is_expired


def test_actes_vide_equivaut_a_aucun_acte():
    sans = assess(**AHMED, today=TODAY)
    vide = assess(**AHMED, today=TODAY, actes=[])
    assert vide.days_left == sans.days_left
    assert vide.deadline == sans.deadline
    assert vide.interruption is None
    assert [s['article'] for s in vide.sources] == \
           [s['article'] for s in sans.sources]


# --- 2. Sommation d'huissier au milieu du délai -----------------------------

def test_sommation_au_milieu_du_delai_prolonge_la_creance():
    """Facture 12/05/2026, sommation 01/09/2026, on se place au 13/09/2026."""
    sans = assess(**AHMED, today=TODAY)
    avec = assess(
        **AHMED, today=TODAY,
        actes=[ActeInterruptif('sommation_huissier', '2026-09-01',
                               "Sommation par huissier de justice")],
    )
    # COC 398 : le délai repart en entier depuis l'acte, pas depuis la facture.
    assert avec.deadline == '2027-09-01'
    assert avec.days_left > sans.days_left
    assert avec.days_left == 353          # 01/09/2026 + 365 - 13/09/2026
    assert avec.interruption['interrompu'] is True
    assert avec.interruption['date_depart_effective'] == '2026-09-01'
    assert avec.interruption['jours_gagnes'] == 112
    # Les deux articles qui fondent l'interruption doivent être cités.
    assert 396 in _articles(avec)
    assert 398 in _articles(avec)


def test_les_citations_arabes_viennent_du_corpus():
    avec = assess(
        **AHMED, today=TODAY,
        actes=[{'type': 'sommation_huissier', 'date': '2026-09-01'}],
    )
    attendues = citations_corpus()
    for s in avec.sources:
        assert s['citation_ar'].startswith('الفصل')
        if s['article'] in attendues:
            assert s['citation_ar'] == attendues[s['article']]


# --- 3. Reconnaissance de dette (COC 397) -----------------------------------

def test_paiement_partiel_cite_larticle_397():
    avec = assess(
        **AHMED, today=TODAY,
        actes=[ActeInterruptif('paiement_partiel', '2026-08-20',
                               "Acompte de 2 000 DT, reçu du 20/08/2026")],
    )
    assert 397 in _articles(avec)
    assert 398 in _articles(avec)
    assert 396 not in _articles(avec)      # c'est un acte du débiteur, pas du créancier
    assert avec.deadline == '2027-08-20'
    assert avec.interruption['interruptions'][0]['article_cause'] == 397


def test_reconnaissance_et_arrete_de_compte_relevent_aussi_de_397():
    for t in ('reconnaissance_dette', 'arrete_compte'):
        a = assess(**AHMED, today=TODAY,
                   actes=[ActeInterruptif(t, '2026-07-01')])
        assert 397 in _articles(a), t


# --- 4. LE PIÈGE : un acte après l'expiration n'interrompt rien -------------

def test_acte_posterieur_a_expiration_ne_ressuscite_pas_la_creance():
    """Facture 15/01/2020 : prescrite depuis le 14/01/2021. Sommation 2026."""
    sans = assess(9520, '2020-01-15', 'menuiserie', today=TODAY)
    assert sans.is_expired

    avec = assess(
        9520, '2020-01-15', 'menuiserie', today=TODAY,
        actes=[ActeInterruptif('sommation_huissier', '2026-01-01',
                               "Sommation tardive")],
    )
    assert avec.is_expired, "une créance éteinte ne se ranime pas"
    assert avec.urgency == 'expired'
    assert avec.days_left == sans.days_left
    assert avec.deadline == sans.deadline
    assert avec.interruption['interrompu'] is False
    assert avec.interruption['jours_gagnes'] == 0
    assert len(avec.interruption['actes_sans_effet']) == 1
    motif = avec.interruption['actes_sans_effet'][0]['motif_fr']
    assert 'APRÈS' in motif and 'prescription' in motif


def test_acte_le_jour_meme_de_lecheance_interrompt_encore():
    """Limite exacte : au dernier jour du délai, il reste un délai à couper."""
    a = assess(9520, '2025-09-13', 'menuiserie', today=TODAY,
               actes=[ActeInterruptif('sommation_huissier', '2026-09-13')])
    assert a.interruption['interrompu'] is True
    assert a.deadline == '2027-09-13'


# --- 5. Acte antérieur à la facture : refusé --------------------------------

def test_acte_anterieur_a_la_facture_est_refuse():
    with pytest.raises(ActeImpossible) as exc:
        assess(**AHMED, today=TODAY,
               actes=[ActeInterruptif('sommation_huissier', '2026-01-10')])
    msg = str(exc.value)
    assert 'AVANT la facture' in msg
    assert '10/01/2026' in msg and '12/05/2026' in msg
    assert "n'était pas encore née" in msg


# --- 6. Plusieurs actes : c'est le dernier valide qui compte ----------------

def test_plusieurs_actes_successifs_le_dernier_valide_fixe_le_depart():
    a = assess(
        **AHMED, today=TODAY,
        actes=[
            ActeInterruptif('sommation_huissier', '2026-06-01'),
            ActeInterruptif('paiement_partiel', '2026-07-15'),
            ActeInterruptif('demande_justice', '2026-09-10'),
        ],
    )
    assert len(a.interruption['interruptions']) == 3
    assert a.interruption['date_depart_effective'] == '2026-09-10'
    assert a.deadline == '2027-09-10'
    assert a.days_left == 362
    # Les trois articles fondateurs sont présents, sans doublon.
    arts = [s['article'] for s in a.sources]
    assert 396 in arts and 397 in arts and 398 in arts
    assert len(arts) == len(set(arts)), "aucune source ne doit être dupliquée"


def test_ordre_de_saisie_indifferent():
    """Des actes donnés en désordre donnent le même résultat."""
    ordonne = assess(**AHMED, today=TODAY, actes=[
        ActeInterruptif('sommation_huissier', '2026-06-01'),
        ActeInterruptif('demande_justice', '2026-09-10'),
    ])
    desordre = assess(**AHMED, today=TODAY, actes=[
        ActeInterruptif('demande_justice', '2026-09-10'),
        ActeInterruptif('sommation_huissier', '2026-06-01'),
    ])
    assert ordonne.deadline == desordre.deadline
    assert ordonne.days_left == desordre.days_left


def test_acte_valide_puis_acte_tardif_sur_creance_deja_relancee():
    """Un acte valide prolonge ; un acte encore postérieur reste dans le délai."""
    a = assess(9520, '2025-06-01', 'menuiserie', today=TODAY, actes=[
        ActeInterruptif('sommation_huissier', '2026-05-01'),   # dans le délai
        ActeInterruptif('paiement_partiel', '2026-09-01'),     # dans le NOUVEAU délai
    ])
    assert len(a.interruption['interruptions']) == 2
    assert a.interruption['actes_sans_effet'] == []
    assert a.deadline == '2027-09-01'


# --- 7. Acte daté du futur : refusé -----------------------------------------

def test_acte_date_du_futur_est_refuse():
    with pytest.raises(ActeImpossible) as exc:
        assess(**AHMED, today=TODAY,
               actes=[ActeInterruptif('sommation_huissier', '2026-11-15')])
    msg = str(exc.value)
    assert 'après aujourd' in msg
    assert '15/11/2026' in msg
    assert "n'a pas encore eu lieu" in msg


# --- 8. Garde-fous de saisie ------------------------------------------------

def test_type_dacte_inconnu_est_refuse():
    with pytest.raises(ActeImpossible) as exc:
        ActeInterruptif('coup_de_telephone', '2026-07-01')
    assert "Type d'acte inconnu" in str(exc.value)


def test_date_illisible_est_refusee():
    with pytest.raises(ActeImpossible):
        ActeInterruptif('sommation_huissier', '12/05/2026')


def test_acte_sous_forme_de_dict_est_accepte():
    """L'API transmet des dicts, pas des dataclasses."""
    a = assess(**AHMED, today=TODAY,
               actes=[{'type': 'arrete_compte', 'date': '2026-08-01',
                       'description': 'Compte arrêté et signé'}])
    assert a.interruption['interrompu'] is True
    assert a.interruption['interruptions'][0]['description'] == \
        'Compte arrêté et signé'


def test_dict_sans_date_est_refuse():
    with pytest.raises(ActeImpossible) as exc:
        assess(**AHMED, today=TODAY, actes=[{'type': 'arrete_compte'}])
    assert 'date' in str(exc.value)


# --- 9. Le régime de quinze ans repart lui aussi à zéro ---------------------

def test_interruption_sous_le_regime_general_de_quinze_ans():
    a = assess(9520, '2026-05-12', 'conseil', today=TODAY,
               actes=[ActeInterruptif('reconnaissance_dette', '2026-09-01')])
    assert a.regime == 'general_15y'
    assert a.deadline == '2041-09-01'      # quinze ans depuis l'acte
    assert 397 in _articles(a)


# --- 10. La fonction appliquer() prise isolément ----------------------------

def test_appliquer_retourne_le_depart_et_les_articles():
    res = appliquer('2026-05-12',
                    [ActeInterruptif('sommation_huissier', '2026-09-01')],
                    regime_jours=365, today=TODAY)
    assert res.date_depart_effective == '2026-09-01'
    assert res.echeance_initiale == '2027-05-12'
    assert res.echeance_effective == '2027-09-01'
    assert res.jours_gagnes == 112
    assert {s['article'] for s in res.sources} >= {396, 398}
    assert 'repart à zéro' in res.resume_fr


# --- 11. L'endpoint POST /dossiers/analyser ---------------------------------

def _client():
    from fastapi.testclient import TestClient
    racine = pathlib.Path(__file__).resolve().parents[2]
    if str(racine) not in sys.path:
        sys.path.insert(0, str(racine))
    from api.main import app
    return TestClient(app)


def test_endpoint_sans_actes_ne_change_rien():
    r = _client().post('/dossiers/analyser', json={
        'montant_tnd': 9520, 'date_facture': '2026-05-12',
        'activite': 'menuiserie', 'aujourdhui': '2026-09-13',
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['jours_restants'] == 241
    assert d['interruption'] is None


def test_endpoint_avec_sommation_expose_linterruption():
    r = _client().post('/dossiers/analyser', json={
        'montant_tnd': 9520, 'date_facture': '2026-05-12',
        'activite': 'menuiserie', 'aujourdhui': '2026-09-13',
        'actes_interruptifs': [
            {'type': 'sommation_huissier', 'date': '2026-09-01',
             'description': 'Sommation signifiée par huissier'},
        ],
    })
    assert r.status_code == 200, r.text
    d = r.json()
    inter = d['interruption']
    assert inter['interrompu'] is True
    assert inter['interruptions'][0]['type'] == 'sommation_huissier'
    assert inter['interruptions'][0]['date'] == '2026-09-01'
    assert inter['jours_gagnes'] == 112
    assert d['jours_restants'] == 353
    assert {a['article'] for a in inter['interruptions'][0]['articles']} == {396, 398}


def test_endpoint_acte_tardif_renvoie_200_et_creance_prescrite():
    """Le piège, vu depuis l'API : pas une erreur, un refus motivé."""
    r = _client().post('/dossiers/analyser', json={
        'montant_tnd': 9520, 'date_facture': '2020-01-15',
        'activite': 'menuiserie', 'aujourdhui': '2026-09-13',
        'actes_interruptifs': [
            {'type': 'sommation_huissier', 'date': '2026-01-01'},
        ],
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['est_prescrit'] is True
    assert d['interruption']['interrompu'] is False
    assert d['interruption']['jours_gagnes'] == 0
    assert len(d['interruption']['actes_sans_effet']) == 1


def test_endpoint_acte_anterieur_a_la_facture_renvoie_400():
    r = _client().post('/dossiers/analyser', json={
        'montant_tnd': 9520, 'date_facture': '2026-05-12',
        'activite': 'menuiserie', 'aujourdhui': '2026-09-13',
        'actes_interruptifs': [
            {'type': 'sommation_huissier', 'date': '2026-01-10'},
        ],
    })
    assert r.status_code == 400, r.text
    assert 'AVANT la facture' in r.json()['detail']


def test_endpoint_type_dacte_inconnu_renvoie_422():
    """Le schéma rejette en amont un type que le corpus ne fonde pas."""
    r = _client().post('/dossiers/analyser', json={
        'montant_tnd': 9520, 'date_facture': '2026-05-12',
        'aujourdhui': '2026-09-13',
        'actes_interruptifs': [
            {'type': 'coup_de_telephone', 'date': '2026-07-01'},
        ],
    })
    assert r.status_code == 422, r.text

