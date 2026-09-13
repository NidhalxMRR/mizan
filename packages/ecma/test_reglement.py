"""Tests du moteur E-CMA.

Trois familles, et la première est la plus importante :

1. L'INVARIANT CONSTITUTIONNEL — `porte_effet_juridique` est False sur TOUTE
   entrée tant qu'aucun humain n'a validé. Vérifié par balayage sur l'ensemble
   des litiges du fichier, y compris les hostiles, et jusque dans le dict
   sérialisé.

2. LES ENTRÉES HOSTILES — montant négatif, montant nul, parties identiques,
   position vide, date absente, date illisible, texte arabe, créance
   prescrite. Écrites d'emblée, pas après coup : ce sont elles qui cassent un
   moteur en démonstration.

3. L'ANCRAGE — aucun article n'est cité qui n'existe pas dans le corpus, et
   chaque citation arabe est identique, caractère pour caractère, à celle du
   corpus. Un test tente explicitement de citer des articles inexistants ou
   ambigus et exige le refus.
"""
from __future__ import annotations

import json
import pathlib
from datetime import date

import pytest

from reglement import (
    VOIES,
    Litige,
    LitigeInvalide,
    MENTION_PROJET,
    MENTION_PROJET_AR,
    Partie,
    _ancrer,
    _charger_corpus,
    proposer_reglement,
    rediger_pv,
    verifier_ancrage_bm25,
)

AUJOURDHUI = date(2026, 9, 13)  # date figée : un test ne dépend pas du calendrier


# ---------------------------------------------------------------------------
# Fixtures : le dossier réel, puis toute la famille hostile.
# ---------------------------------------------------------------------------

def litige_ahmed() -> Litige:
    """Le dossier réel du hackathon : menuiserie, qualité contestée."""
    return Litige(
        montant_reclame=9520.0,
        nature="Travaux de menuiserie — fourniture et pose",
        demandeur=Partie(
            nom='Ahmed Ben Salah',
            role='demandeur',
            position="Les travaux ont été livrés et réceptionnés. La facture "
                     "reste impayée depuis plus de trois mois.",
        ),
        defendeur=Partie(
            nom='Société Dar El Ouns SARL',
            role='defendeur',
            position="La qualité des finitions n'est pas conforme au devis : "
                     "plusieurs ouvrants ferment mal.",
        ),
        date_facture='2026-05-12',
        numero_facture='F-2026-0143',
        lieu='Sfax',
    )


def _litiges_hostiles() -> list[tuple[str, Litige]]:
    """Tout ce qu'un utilisateur pressé ou malveillant peut saisir."""
    base = dict(nature='Travaux de menuiserie', date_facture='2026-05-12')
    return [
        ('position_vide', Litige(
            montant_reclame=9520.0,
            demandeur=Partie(nom='Ahmed'), defendeur=Partie(nom='Dar El Ouns'),
            **base)),
        ('date_absente', Litige(
            montant_reclame=9520.0, nature='Travaux de menuiserie',
            demandeur=Partie(nom='Ahmed', position='impayé'),
            defendeur=Partie(nom='Dar El Ouns', position='conteste'))),
        ('date_illisible', Litige(
            montant_reclame=9520.0, nature='Travaux de menuiserie',
            demandeur=Partie(nom='Ahmed', position='impayé'),
            defendeur=Partie(nom='Dar El Ouns', position='conteste'),
            date_facture='12/05/2026')),
        ('creance_prescrite', Litige(
            montant_reclame=9520.0, nature='Travaux de menuiserie',
            demandeur=Partie(nom='Ahmed', position='impayé'),
            defendeur=Partie(nom='Dar El Ouns', position='conteste'),
            date_facture='2024-01-05')),
        ('texte_arabe', Litige(
            montant_reclame=9520.0,
            nature='أشغال نجارة — تركيب وتزويد',
            demandeur=Partie(nom='أحمد بن صالح', position='الفاتورة لم تخلص'),
            defendeur=Partie(nom='شركة دار الأنس', position='جودة العمل غير مطابقة'),
            date_facture='2026-05-12')),
        ('montant_minuscule', Litige(
            montant_reclame=0.001, nature='Travaux de menuiserie',
            demandeur=Partie(nom='Ahmed', position='impayé'),
            defendeur=Partie(nom='Dar El Ouns', position='conteste'),
            date_facture='2026-05-12')),
        ('montant_enorme', Litige(
            montant_reclame=1_000_000_000.0, nature='Travaux de menuiserie',
            demandeur=Partie(nom='Ahmed', position='impayé'),
            defendeur=Partie(nom='Dar El Ouns', position='conteste'),
            date_facture='2026-05-12')),
        ('nature_inconnue', Litige(
            montant_reclame=9520.0, nature='litige de voisinage sur un arbre',
            demandeur=Partie(nom='Ahmed', position='gêne'),
            defendeur=Partie(nom='Dar El Ouns', position='pas ma faute'),
            date_facture='2026-05-12')),
        ('nature_vide', Litige(
            montant_reclame=9520.0, nature='',
            demandeur=Partie(nom='Ahmed', position='impayé'),
            defendeur=Partie(nom='Dar El Ouns', position='conteste'),
            date_facture='2026-05-12')),
        ('clause_arbitrage', Litige(
            montant_reclame=9520.0, nature='Travaux de menuiserie',
            demandeur=Partie(nom='Ahmed', position='impayé'),
            defendeur=Partie(nom='Dar El Ouns', position='conteste'),
            date_facture='2026-05-12', clause_arbitrage=True)),
        ('montant_reconnu_partiel', Litige(
            montant_reclame=9520.0, nature='Travaux de menuiserie',
            demandeur=Partie(nom='Ahmed', position='impayé'),
            defendeur=Partie(nom='Dar El Ouns', position='conteste',
                             montant_reconnu=7000.0),
            date_facture='2026-05-12')),
        ('reel_ahmed', litige_ahmed()),
    ]


TOUS_LES_LITIGES = _litiges_hostiles()
IDS = [n for n, _ in TOUS_LES_LITIGES]


# ---------------------------------------------------------------------------
# 1. L'INVARIANT : l'IA ne décide pas.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('nom,litige', TOUS_LES_LITIGES, ids=IDS)
def test_jamais_deffet_juridique_sans_validation_humaine(nom, litige):
    """L'INVARIANT DU PROJET, balayé sur toutes les entrées.

    Quelle que soit l'entrée — hostile, arabe, prescrite, silencieuse — un
    dossier fraîchement produit par l'agent ne porte AUCUN effet juridique.
    C'est le test que le jury doit pouvoir lire sans être développeur.
    """
    d = proposer_reglement(litige, aujourdhui=AUJOURDHUI)
    assert d.porte_effet_juridique is False
    assert d.est_projet is True
    assert d.validation.valide_par is None
    assert d.validation.numero_accreditation is None
    assert d.validation.valide_le is None
    assert d.validation.signature is None
    assert d.validation.signe is False
    assert d.avis.contraignant is False
    # Et jusque dans la sérialisation, car c'est elle que l'API renvoie.
    assert d.to_dict()['porte_effet_juridique'] is False
    assert d.to_dict()['est_projet'] is True


def test_porte_effet_juridique_nest_pas_ecrivable():
    """On ne peut pas forcer l'effet juridique : c'est une propriété calculée.

    Sans setter, l'affectation lève AttributeError. C'est la garantie
    structurelle : aucun appelant, aucune route d'API, aucun bug d'inattention
    ne peut faire passer un avis pour une décision.
    """
    d = proposer_reglement(litige_ahmed(), aujourdhui=AUJOURDHUI)
    with pytest.raises(AttributeError):
        d.porte_effet_juridique = True  # type: ignore[misc]
    assert d.porte_effet_juridique is False


def test_un_dict_trafique_ne_remonte_pas_en_effet_juridique():
    """Trafiquer le dict de sortie ne change rien à l'objet.

    `to_dict()` recalcule la propriété à chaque appel depuis l'état de la
    validation : elle n'est jamais relue d'un champ stocké.
    """
    d = proposer_reglement(litige_ahmed(), aujourdhui=AUJOURDHUI)
    sortie = d.to_dict()
    sortie['porte_effet_juridique'] = True
    assert d.to_dict()['porte_effet_juridique'] is False


def test_validation_partielle_ne_suffit_pas():
    """Renseigner un nom à la main, sans passer par valider(), ne suffit pas.

    La propriété exige la conjonction : signé, nommé, accrédité, daté.
    """
    d = proposer_reglement(litige_ahmed(), aujourdhui=AUJOURDHUI)
    d.validation.valide_par = 'Quelqu\'un'
    assert d.porte_effet_juridique is False
    d.validation.signe = True
    assert d.porte_effet_juridique is False  # ni accréditation ni date
    d.validation.numero_accreditation = 'X-1'
    assert d.porte_effet_juridique is False  # toujours pas de date


def test_validation_par_un_professionnel_accredite_porte_effet():
    """Le seul chemin qui produise un effet juridique : valider()."""
    d = proposer_reglement(litige_ahmed(), aujourdhui=AUJOURDHUI)
    assert d.porte_effet_juridique is False
    d.valider(nom='Me Leila Trabelsi', qualite='conciliateur',
              numero_accreditation='CONC-SFX-0417',
              observations='Abattement arrêté à 12 % au vu du constat.',
              le='2026-09-14')
    assert d.porte_effet_juridique is True
    assert d.est_projet is False
    assert d.validation.valide_par == 'Me Leila Trabelsi'
    assert d.to_dict()['porte_effet_juridique'] is True


@pytest.mark.parametrize('nom,qualite,numero', [
    ('', 'conciliateur', 'C-1'),                 # anonyme
    ('   ', 'conciliateur', 'C-1'),              # blancs
    ('Me X', 'juge', 'C-1'),                     # qualité non admise
    ('Me X', 'chatgpt', 'C-1'),                  # ni surtout celle-là
    ('Me X', 'conciliateur', ''),                # non imputable
    ('Me X', 'conciliateur', '   '),
])
def test_validation_refuse_ce_qui_nest_pas_imputable(nom, qualite, numero):
    """Une validation non imputable n'est qu'un second avis. On la refuse."""
    d = proposer_reglement(litige_ahmed(), aujourdhui=AUJOURDHUI)
    with pytest.raises(LitigeInvalide):
        d.valider(nom=nom, qualite=qualite, numero_accreditation=numero)
    assert d.porte_effet_juridique is False


# ---------------------------------------------------------------------------
# 2. ENTRÉES HOSTILES.
# ---------------------------------------------------------------------------

def test_montant_negatif_refuse():
    lit = litige_ahmed()
    lit.montant_reclame = -9520.0
    with pytest.raises(LitigeInvalide, match='négatif'):
        proposer_reglement(lit, aujourdhui=AUJOURDHUI)


def test_montant_zero_refuse():
    """Sur zéro, il n'y a pas de concession possible (COC art. 1458)."""
    lit = litige_ahmed()
    lit.montant_reclame = 0
    with pytest.raises(LitigeInvalide, match='nul'):
        proposer_reglement(lit, aujourdhui=AUJOURDHUI)


@pytest.mark.parametrize('mauvais', [None, 'beaucoup', [], {}, True, float('nan')])
def test_montant_non_numerique_refuse(mauvais):
    lit = litige_ahmed()
    lit.montant_reclame = mauvais
    with pytest.raises(LitigeInvalide):
        proposer_reglement(lit, aujourdhui=AUJOURDHUI)


@pytest.mark.parametrize('a,b', [
    ('Ahmed Ben Salah', 'Ahmed Ben Salah'),
    ('Ahmed Ben Salah', '  ahmed ben salah  '),   # casse et blancs
    ('أحمد بن صالح', 'أحمد بن صالح'),
])
def test_parties_identiques_refusees(a, b):
    """Le COC art. 1458 suppose deux transigeants distincts."""
    lit = Litige(montant_reclame=9520.0, nature='menuiserie',
                 demandeur=Partie(nom=a), defendeur=Partie(nom=b),
                 date_facture='2026-05-12')
    with pytest.raises(LitigeInvalide, match='même personne'):
        proposer_reglement(lit, aujourdhui=AUJOURDHUI)


@pytest.mark.parametrize('a,b', [('', 'X'), ('X', ''), ('  ', 'X')])
def test_partie_sans_nom_refusee(a, b):
    lit = Litige(montant_reclame=100.0, nature='menuiserie',
                 demandeur=Partie(nom=a), defendeur=Partie(nom=b))
    with pytest.raises(LitigeInvalide):
        proposer_reglement(lit, aujourdhui=AUJOURDHUI)


def test_position_vide_declenche_labstention_sur_le_quantum():
    """Silence du débiteur ≠ contestation. On ne propose alors AUCUNE remise.

    Proposer une remise au vu du silence du débiteur reviendrait à négocier
    contre le créancier qui nous a saisis.
    """
    lit = Litige(montant_reclame=9520.0, nature='Travaux de menuiserie',
                 demandeur=Partie(nom='Ahmed', position='impayé'),
                 defendeur=Partie(nom='Dar El Ouns'),  # muet
                 date_facture='2026-05-12')
    d = proposer_reglement(lit, aujourdhui=AUJOURDHUI)
    montant = next(t for t in d.avis.termes if t['cle'] == 'montant_transige')
    assert montant['valeur']['plancher'] == 9520.0
    assert montant['valeur']['plafond'] == 9520.0
    assert 'ABSTENTION' in montant['reserve']
    assert any('aucune position' in x for x in d.avis.abstentions)


def test_date_absente_nempeche_pas_lavis_mais_suspend_la_prescription():
    """Une PME sans facture n'est pas renvoyée : on dit ce qu'on ne sait pas."""
    lit = Litige(montant_reclame=9520.0, nature='Travaux de menuiserie',
                 demandeur=Partie(nom='Ahmed', position='impayé'),
                 defendeur=Partie(nom='Dar El Ouns', position='conteste'))
    d = proposer_reglement(lit, aujourdhui=AUJOURDHUI)
    assert d.avis.prescription['calculable'] is False
    assert 'date' in d.avis.prescription['motif'].lower()
    assert 'est_prescrite' not in d.avis.prescription
    assert any('Prescription non calculée' in x for x in d.avis.abstentions)
    assert d.porte_effet_juridique is False


def test_date_illisible_ne_devine_pas():
    lit = litige_ahmed()
    lit.date_facture = '12/05/2026'
    d = proposer_reglement(lit, aujourdhui=AUJOURDHUI)
    assert d.avis.prescription['calculable'] is False
    assert 'illisible' in d.avis.prescription['motif']


def test_date_illisible_ne_casse_pas_la_redaction_du_pv():
    """Régression : une date mal saisie faisait planter la rédaction du PV.

    Elle est déjà signalée dans le bloc prescription ; elle ne doit pas en
    plus empêcher le professionnel accrédité de lire le projet et de la
    corriger. Le moteur reproduit la saisie telle quelle.
    """
    lit = litige_ahmed()
    lit.date_facture = '12/05/2026'
    pv = rediger_pv(proposer_reglement(lit, aujourdhui=AUJOURDHUI))
    assert '12/05/2026' in pv['texte_fr']
    assert MENTION_PROJET in pv['texte_fr']


def test_creance_prescrite_est_signalee_mais_pas_bloquante():
    """La prescription ferme la contrainte, pas la conciliation.

    Contrairement à la mise en demeure (packages/legal/notice.py, qui REFUSE
    de rédiger sur une créance éteinte), transiger sur une créance prescrite
    reste licite : le débiteur peut vouloir solder la relation. Ce qui change,
    c'est le rapport de force — et le moteur doit le dire au créancier au lieu
    de le laisser négocier en croyant tenir un moyen de pression.
    """
    lit = litige_ahmed()
    lit.date_facture = '2024-01-05'
    d = proposer_reglement(lit, aujourdhui=AUJOURDHUI)
    assert d.avis.prescription['est_prescrite'] is True
    assert d.avis.prescription['jours_restants'] < 0
    motifs = ' '.join(d.avis.voie_recommandee['motifs'])
    assert 'PRESCRITE' in motifs
    assert 'interruption ne se présume pas' in motifs
    assert d.avis.voie_recommandee['voie_retenue'] == 'conciliation'
    assert d.porte_effet_juridique is False


def test_prescription_proche_est_signalee():
    lit = litige_ahmed()
    lit.date_facture = '2025-10-01'  # échéance 2026-10-01, soit 18 jours
    d = proposer_reglement(lit, aujourdhui=AUJOURDHUI)
    assert d.avis.prescription['urgence'] == 'critique'
    assert 'expire le' in ' '.join(d.avis.voie_recommandee['motifs'])


def test_entree_entierement_en_arabe():
    """Nom, nature et positions en arabe : rien ne casse, rien ne se perd."""
    lit = next(l for n, l in TOUS_LES_LITIGES if n == 'texte_arabe')
    d = proposer_reglement(lit, aujourdhui=AUJOURDHUI)
    pv = rediger_pv(d)
    assert 'أحمد بن صالح' in pv['texte_fr']
    assert 'أحمد بن صالح' in pv['texte_ar']
    assert 'شركة دار الأنس' in pv['texte_ar']
    assert d.porte_effet_juridique is False
    # La nature arabe « نجارة » doit déclencher le régime du louage d'ouvrage.
    assert any(t['cle'] == 'objet_du_differend' for t in d.avis.termes)


def test_nature_inconnue_provoque_une_abstention_explicite():
    """On n'applique pas par analogie un texte qui ne vise pas le cas."""
    lit = next(l for n, l in TOUS_LES_LITIGES if n == 'nature_inconnue')
    d = proposer_reglement(lit, aujourdhui=AUJOURDHUI)
    assert not any(t['cle'] == 'objet_du_differend' for t in d.avis.termes)
    assert any('aucun régime de fond' in x for x in d.avis.abstentions)


def test_montant_reconnu_par_le_defendeur_prime_sur_lestimation():
    """Un chiffre donné par une partie vaut mieux qu'une bande conventionnelle."""
    lit = next(l for n, l in TOUS_LES_LITIGES if n == 'montant_reconnu_partiel')
    d = proposer_reglement(lit, aujourdhui=AUJOURDHUI)
    t = next(t for t in d.avis.termes if t['cle'] == 'montant_transige')
    assert t['valeur']['plancher'] == 7000.0
    assert t['valeur']['plafond'] == 7000.0
    assert 'vient de la partie elle-même' in t['detail_fr']


@pytest.mark.parametrize('nom,litige', TOUS_LES_LITIGES, ids=IDS)
def test_le_quantum_nest_jamais_declare_fonde(nom, litige):
    """AUCUN article du corpus ne fixe de taux : le drapeau est un invariant."""
    d = proposer_reglement(litige, aujourdhui=AUJOURDHUI)
    for t in d.avis.termes:
        assert t['quantum_fonde'] is False, t['cle']


@pytest.mark.parametrize('nom,litige', TOUS_LES_LITIGES, ids=IDS)
def test_le_pv_porte_toujours_la_mention_projet(nom, litige):
    """La mention ne peut disparaître que par validation. Les deux langues."""
    d = proposer_reglement(litige, aujourdhui=AUJOURDHUI)
    pv = rediger_pv(d)
    assert pv['est_projet'] is True
    assert pv['porte_effet_juridique'] is False
    assert MENTION_PROJET in pv['texte_fr']
    assert MENTION_PROJET_AR in pv['texte_ar']
    assert 'AUCUN EFFET JURIDIQUE' in pv['texte_fr']
    assert 'لا يترتب على هذا المحضر أي أثر قانوني' in pv['texte_ar']
    # L'espace de validation est présent mais vide.
    assert '(NON VALIDÉ)' in pv['texte_fr']
    assert '(غير مصادق عليه)' in pv['texte_ar']


def test_la_mention_disparait_apres_validation():
    d = proposer_reglement(litige_ahmed(), aujourdhui=AUJOURDHUI)
    d.valider('Me Leila Trabelsi', 'conciliateur', 'CONC-SFX-0417', le='2026-09-14')
    pv = rediger_pv(d)
    assert MENTION_PROJET not in pv['texte_fr']
    assert MENTION_PROJET_AR not in pv['texte_ar']
    assert 'porte effet juridique' in pv['texte_fr']
    assert 'Me Leila Trabelsi' in pv['texte_fr']
    assert 'CONC-SFX-0417' in pv['texte_ar']


# ---------------------------------------------------------------------------
# 3. ANCRAGE : aucune citation composée.
# ---------------------------------------------------------------------------

def _corpus_brut() -> dict:
    """Relit les .jsonl à la main, sans passer par le module testé.

    Un test qui vérifierait les citations à l'aide des fonctions du module
    testé ne vérifierait rien : il comparerait le module à lui-même.
    """
    racine = pathlib.Path(__file__).resolve().parents[2] / 'corpus'
    out = {}
    for f in sorted(racine.glob('*.jsonl')):
        for ligne in f.open(encoding='utf-8'):
            doc = json.loads(ligne)
            out.setdefault((doc['code_id'], int(doc['article'])), []).append(doc)
    return out


def test_la_cle_article_du_corpus_est_bien_un_int():
    """Le piège documenté : un lookup par str renvoie silencieusement rien."""
    brut = _corpus_brut()
    assert ('coc', 1458) in brut
    assert ('coc', '1458') not in brut  # type: ignore[comparison-overlap]


@pytest.mark.parametrize('nom,litige', TOUS_LES_LITIGES, ids=IDS)
def test_chaque_article_cite_existe_et_est_cite_mot_pour_mot(nom, litige):
    """LE TEST ANTI-HALLUCINATION.

    Pour chaque article cité dans chaque avis : il existe dans le corpus, et
    sa `citation_ar` est identique caractère pour caractère à celle du corpus.
    Aucune citation n'est composée, reformulée ni traduite.
    """
    brut = _corpus_brut()
    d = proposer_reglement(litige, aujourdhui=AUJOURDHUI)
    sources = [s for t in d.avis.termes for s in t['sources']]
    sources += d.avis.voie_recommandee['sources']
    sources += [d.avis.prescription['source']] if d.avis.prescription.get('source') else []
    assert sources, 'un avis sans aucune source ne devrait pas être produit'
    for s in sources:
        cle = (s['code_id'], s['article'])
        assert cle in brut, f'article cité absent du corpus : {cle}'
        citations = {doc['citation_ar'] for doc in brut[cle]}
        assert s['citation_ar'] in citations, (
            f"citation non conforme au corpus pour {cle} : {s['citation_ar']!r}")
        textes = {doc['text_ar'].strip() for doc in brut[cle]}
        assert s['extrait_ar'] in textes, f'extrait non verbatim pour {cle}'


def test_ancrer_refuse_un_article_inexistant():
    """On ne cite pas le COC art. 99999. Il n'existe pas."""
    assert _ancrer('coc', 99999, 'x', 'x', 'x') is None
    assert _ancrer('coc', 0, 'x', 'x', 'x') is None
    assert _ancrer('inexistant', 1458, 'x', 'x', 'x') is None


def test_ancrer_refuse_un_numero_ambigu_du_code_arbitrage():
    """Le Code de l'Arbitrage a des numéros dupliqués : on refuse d'y piocher.

    Preuve dans le corpus : l'article 2 y figure six fois avec six textes
    différents (l'extraction a mêlé la loi de promulgation, la mjalla et les
    conventions annexées). Citer « Code de l'Arbitrage art. 2 » sans savoir
    lequel des six reviendrait à faire signer un texte tiré au sort.
    """
    brut = _corpus_brut()
    assert len(brut[('arbitrage', 2)]) > 1, 'le corpus a changé : revoir ce test'
    assert _ancrer('arbitrage', 2, 'x', 'x', 'x') is None


def test_ancrer_refuse_aussi_un_numero_ambigu_du_coc():
    """La duplication n'est pas propre à l'arbitrage : le COC 875 aussi.

    Le corpus porte deux entrées sous « coc / 875 » : le texte complet, et un
    fragment de trois mots recollé par l'extracteur. Sans levée d'ambiguïté,
    `_ancrer` doit refuser — c'est ce refus qui a été détecté par les tests
    avant d'être levé explicitement dans `_terme_objet_du_differend`, par un
    incipit que seul le bon texte porte.
    """
    brut = _corpus_brut()
    assert len(brut[('coc', 875)]) > 1, 'le corpus a changé : revoir ce test'
    assert _ancrer('coc', 875, 'x', 'x', 'x') is None            # ambigu
    s = _ancrer('coc', 875, 'x', 'x', 'x', incipit_attendu='حط الثمن')
    assert s is not None                                          # levé
    assert 'حط الثمن' in s.extrait_ar


def test_ancrer_refuse_un_incipit_attendu_absent():
    """Une levée d'ambiguïté qui ne se vérifie pas ne lève rien."""
    assert _ancrer('coc', 1458, 'x', 'x', 'x',
                   incipit_attendu='الكمبيالة') is None


def test_larticle_1458_est_bien_celui_du_corpus_et_non_la_formule_de_manuel():
    """Le COC tunisien ne dit PAS « terminer une contestation née ».

    La définition qu'on lit partout (« contrat par lequel les parties
    terminent une contestation née ou préviennent une contestation à naître »)
    est la formule française. Le texte tunisien indexé dit, mot pour mot :
    « الصلح عقد وضع لرفع النزاع وقطع الخصومة… ». Ce test verrouille le fait
    qu'on cite le corpus et non le manuel.
    """
    s = _ancrer('coc', 1458, 'x', 'x', 'x')
    assert s is not None
    assert s.citation_ar == 'الفصل 1458 من مجلة الالتزامات والعقود'
    assert 'الصلح عقد وضع لرفع النزاع وقطع الخصومة' in s.extrait_ar
    assert 'تنازل كل من المتصالحين عن شيء من مطالبه' in s.extrait_ar
    assert s.fiabilite == 'texte-natif'


def test_larticle_1467_fonde_bien_leffet_dextinction():
    """« الصلح بشيء من الدين كالإبراء في الباقي » : la remise du surplus."""
    s = _ancrer('coc', 1467, 'x', 'x', 'x')
    assert s is not None
    assert 'سقوط الحقوق والدعاوي' in s.extrait_ar
    assert 'كالإبراء في الباقي' in s.extrait_ar


def test_larticle_875_fonde_bien_la_reduction_du_prix():
    """« أن يطلب حط الثمن » : c'est ce qui rend la remise juridiquement cohérente."""
    s = _ancrer('coc', 875, 'x', 'x', 'x', incipit_attendu='حط الثمن')
    assert s is not None
    assert 'حط الثمن' in s.extrait_ar


def test_larticle_7_du_code_arbitrage_est_signale_comme_ocr():
    """Le seul article d'arbitrage cité, et il est marqué pour ce qu'il est."""
    s = _ancrer('arbitrage', 7, 'x', 'x', 'x')
    assert s is not None
    assert s.fiabilite == 'ocr-degrade'
    assert 'التحكيم' in s.extrait_ar


def test_le_corpus_ne_fonde_pas_la_mediation():
    """HONNÊTETÉ : « الوساطة » n'est au corpus que comme COURTAGE (commerce 601).

    Si un jour le corpus intègre une loi sur la médiation, ce test tombera —
    et c'est exactement ce qu'on veut : il garde la trace de ce qu'on a
    réellement vérifié, à la date où on l'a vérifié.
    """
    brut = _corpus_brut()
    porteurs = [doc for docs in brut.values() for doc in docs
                if 'الوساطة' in doc['text_ar']]
    assert len(porteurs) == 1
    assert porteurs[0]['code_id'] == 'commerce'
    assert porteurs[0]['article'] == 601
    assert VOIES['mediation'].fondee_dans_corpus is False
    assert 'courtage' in VOIES['mediation'].reserve


def test_le_corpus_ne_fonde_pas_lechelonnement():
    """HONNÊTETÉ : « التقسيط » et « نظرة الميسرة » : zéro occurrence."""
    brut = _corpus_brut()
    tout = [doc for docs in brut.values() for doc in docs]
    assert not [d for d in tout if 'التقسيط' in d['text_ar']]
    assert not [d for d in tout if 'نظرة الميسرة' in d['text_ar']]
    d = proposer_reglement(litige_ahmed(), aujourdhui=AUJOURDHUI)
    ech = next(t for t in d.avis.termes if t['cle'] == 'echeancier')
    assert ech['quantum_fonde'] is False
    assert 'ABSENTS' in ech['reserve']


def test_larticle_1466_nest_pas_presente_comme_une_exigence_generale_decrit():
    """Piège classique : citer 1466 pour dire « la transaction doit être écrite ».

    Faux. Le texte ne vise que les transactions portant sur des biens
    susceptibles d'hypothèque. Le module doit le dire.
    """
    d = proposer_reglement(litige_ahmed(), aujourdhui=AUJOURDHUI)
    forme = next(t for t in d.avis.termes if t['cle'] == 'forme_de_lacte')
    assert forme['valeur']['ecrit_exige_a_peine_de_nullite'] is False
    assert "n'impose donc pas ici" in forme['detail_fr']


def test_contre_epreuve_bm25_retrouve_les_articles_cites():
    """La seconde preuve : le corpus retrouve l'article par la recherche.

    L'ancrage direct prouve l'existence ; BM25 + la garde anti-hallucination
    du projet (packages/legal/gate.py) prouvent la pertinence.
    """
    s = _ancrer('coc', 1458, 'x', 'x', 'x')
    assert s is not None
    r = verifier_ancrage_bm25(
        'الصلح عقد وضع لرفع النزاع وقطع الخصومة تنازل المتصالحين', s)
    assert r['retrouve'] is True
    assert r['rang_de_larticle'] == 1
    assert r['gate_grounded'] is True


def test_le_mode_controle_produit_des_contre_epreuves():
    d = proposer_reglement(litige_ahmed(), aujourdhui=AUJOURDHUI,
                           controler_ancrage=True)
    controles = [c for t in d.avis.termes for c in t['controles']]
    assert controles, 'le mode contrôle doit produire des contre-épreuves'
    assert all(c['retrouve'] for c in controles), \
        [c for c in controles if not c['retrouve']]
    assert d.porte_effet_juridique is False


# ---------------------------------------------------------------------------
# Les trois voies.
# ---------------------------------------------------------------------------

def test_les_trois_voies_sont_decrites_et_distinguees():
    assert set(VOIES) == {'conciliation', 'mediation', 'arbitrage'}
    # La distinction de fond : seul l'arbitre tranche.
    assert 'TRANCHE' in VOIES['arbitrage'].role_du_tiers
    assert 'PROPOSE' in VOIES['conciliation'].role_du_tiers
    assert 'ne propose pas' in VOIES['mediation'].role_du_tiers
    for v in VOIES.values():
        assert v.nom_ar and v.effet_de_lissue and v.qui_valide


def test_larbitrage_nest_recommande_que_sil_est_ouvert():
    """Sans convention d'arbitrage, la voie est fermée : on ne la recommande pas."""
    sans = litige_ahmed()
    d1 = proposer_reglement(sans, aujourdhui=AUJOURDHUI)
    assert d1.avis.voie_recommandee['voie_retenue'] == 'conciliation'
    assert d1.avis.voie_recommandee['arbitrage_ouvert'] is False
    assert 'fermée' in ' '.join(d1.avis.voie_recommandee['motifs'])

    avec = litige_ahmed()
    avec.clause_arbitrage = True
    d2 = proposer_reglement(avec, aujourdhui=AUJOURDHUI)
    assert d2.avis.voie_recommandee['voie_retenue'] == 'arbitrage'
    assert d2.avis.voie_recommandee['arbitrage_ouvert'] is True
    # Et il reste cité sur le seul article d'arbitrage vérifié.
    arts = {(s['code_id'], s['article'])
            for s in d2.avis.voie_recommandee['sources']}
    assert ('arbitrage', 7) in arts


def test_toutes_les_voies_sont_exposees_pas_seulement_la_retenue():
    """Le justiciable doit voir les trois, pas seulement celle qu'on conseille."""
    d = proposer_reglement(litige_ahmed(), aujourdhui=AUJOURDHUI)
    assert set(d.avis.voie_recommandee['voies_examinees']) == set(VOIES)


# ---------------------------------------------------------------------------
# La référence de dossier.
# ---------------------------------------------------------------------------

def test_la_reference_est_stable_dans_le_meme_processus():
    """Le même litige doit porter le même numéro de dossier."""
    r1 = proposer_reglement(litige_ahmed(), aujourdhui=AUJOURDHUI).reference
    r2 = proposer_reglement(litige_ahmed(), aujourdhui=AUJOURDHUI).reference
    assert r1 == r2
    assert r1.startswith('ECMA-20260913-')


def test_la_reference_est_stable_entre_deux_processus_python():
    """RÉGRESSION, et elle ne se voit pas dans un seul processus.

    La référence était bâtie sur `hash()` d'une chaîne, randomisé à chaque
    démarrage de Python (PYTHONHASHSEED). Deux exécutions successives de la
    démo donnaient deux numéros différents pour le même dossier — un numéro de
    dossier qui change n'est pas un numéro de dossier. Ce test relance
    réellement un interpréteur pour le prouver.
    """
    import subprocess
    import sys as _sys

    code = (
        "import sys; sys.path.insert(0, %r);"
        "from datetime import date;"
        "from reglement import Litige, Partie, proposer_reglement;"
        "l = Litige(montant_reclame=9520.0, nature='menuiserie',"
        " demandeur=Partie(nom='Ahmed Ben Salah'),"
        " defendeur=Partie(nom='Dar El Ouns'), date_facture='2026-05-12');"
        "print(proposer_reglement(l, aujourdhui=date(2026, 9, 13)).reference)"
        % str(pathlib.Path(__file__).resolve().parent)
    )
    refs = set()
    for graine in ('0', '1', '42'):  # trois seeds de hachage différentes
        env = {'PYTHONHASHSEED': graine, 'PATH': '/usr/bin:/bin'}
        out = subprocess.run([_sys.executable, '-c', code], capture_output=True,
                             text=True, env=env, check=True)
        refs.add(out.stdout.strip())
    assert len(refs) == 1, f'référence instable entre processus : {refs}'


# ---------------------------------------------------------------------------
# Le dossier réel, de bout en bout.
# ---------------------------------------------------------------------------

def test_dossier_ahmed_bout_en_bout():
    d = proposer_reglement(litige_ahmed(), aujourdhui=AUJOURDHUI,
                           controler_ancrage=True)
    pv = rediger_pv(d)

    assert d.porte_effet_juridique is False
    assert d.avis.voie_recommandee['voie_retenue'] == 'conciliation'

    cles = {t['cle'] for t in d.avis.termes}
    assert cles == {'objet_du_differend', 'montant_transige', 'echeancier',
                    'forme_de_lacte'}

    montant = next(t for t in d.avis.termes if t['cle'] == 'montant_transige')
    assert montant['valeur']['reclame'] == 9520.0
    assert montant['valeur']['plancher'] == 7140.0   # -25 %
    assert montant['valeur']['plafond'] == 8568.0    # -10 %
    assert montant['principe_fonde'] is True
    assert montant['quantum_fonde'] is False

    # Prescription : facture du 12/05/2026, +365 j => 12/05/2027, 241 j restants.
    p = d.avis.prescription
    assert p['calculable'] is True
    assert p['echeance'] == '2027-05-12'
    assert p['jours_restants'] == 241
    assert p['est_prescrite'] is False

    arts = {(s['code_id'], s['article']) for s in pv['articles_cites']}
    assert {('coc', 1458), ('coc', 1467), ('coc', 875), ('coc', 242)} <= arts

    assert MENTION_PROJET in pv['texte_fr']
    assert MENTION_PROJET_AR in pv['texte_ar']
    assert 'الفصل 1458 من مجلة الالتزامات والعقود' in pv['texte_fr']
    assert 'الفصل 1458 من مجلة الالتزامات والعقود' in pv['texte_ar']
    assert '9\u00a0520,000' in pv['texte_fr']
