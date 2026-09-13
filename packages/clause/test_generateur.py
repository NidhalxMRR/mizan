"""Ce qui doit rester vrai de la clause de règlement des litiges.

Ces tests ne vérifient pas que le code s'exécute : ils verrouillent des
engagements, et chacun échoue si l'engagement disparaît du code.

1. Aucune clause ne porte effet juridique sans validation humaine accréditée.
2. Aucun article n'est cité qui ne soit retrouvé dans le corpus, avec sa
   citation arabe exacte.
3. La médiation, que le corpus ne fonde pas, est REFUSÉE — pas improvisée.
4. Les paramètres qui rendraient la clause nulle (arbitres en nombre pair,
   délai négatif) sont refusés, avec un motif lisible.
5. L'analyse d'un contrat cite le contrat mot pour mot et ne confond jamais
   une clause stipulée avec une clause niée.
"""
import re

import pytest

from packages.clause import generateur as g
from packages.clause.generateur import (
    AnalyseContrat, ClauseReglement, ContratIllisible, ParametreInvalide,
    ParametresClause, VoieInconnue, VoieNonFondee, analyser_contrat,
    generer_clause, lacunes_corpus, valider_par_professionnel,
    verifier_ancrage, voies_disponibles,
)


# --------------------------------------------------------------------------
# Jeux de paramètres
# --------------------------------------------------------------------------

def p_conciliation(**kw) -> ParametresClause:
    base = dict(delai_saisine_jours=15, lieu='Sfax', langue='arabe',
                repartition_frais='parts_egales', delai_procedure_mois=2)
    base.update(kw)
    return ParametresClause(**base)


def p_arbitrage(**kw) -> ParametresClause:
    base = dict(delai_saisine_jours=30, lieu='Tunis', langue='arabe',
                repartition_frais='partie_perdante', delai_procedure_mois=6,
                nombre_arbitres=3,
                institution="le Centre de conciliation et d'arbitrage de Tunis")
    base.update(kw)
    return ParametresClause(**base)


# --------------------------------------------------------------------------
# 1. L'effet juridique : jamais sans un humain accrédité
# --------------------------------------------------------------------------

@pytest.mark.parametrize('voie,params', [
    ('conciliation', p_conciliation()),
    ('arbitrage', p_arbitrage()),
    ('arbitrage', p_arbitrage(nombre_arbitres=1, institution=None)),
    ('arbitrage', p_arbitrage(nombre_arbitres=5, delai_saisine_jours=7)),
    ('conciliation', p_conciliation(repartition_frais='decision_tribunal')),
    ('CONCILIATION ', p_conciliation()),
    ('Arbitrage', p_arbitrage()),
])
def test_aucune_clause_ne_porte_effet_juridique_sans_validation(voie, params):
    """L'engagement central : Mizan donne un avis, elle ne signe pas."""
    c = generer_clause(voie, params)
    assert c.porte_effet_juridique is False
    assert c.valide_par is None
    assert g.MENTION_PROJET in c.texte
    assert 'Porte effet juridique : NON' in c.texte


def test_mention_projet_presente_dans_les_deux_langues():
    c = generer_clause('arbitrage', p_arbitrage())
    assert c.mention_projet == 'PROJET — NON SIGNÉ'
    assert c.mention_projet_ar == 'مشروع — غير ممضى'
    assert c.mention_projet_ar in c.texte


def test_seule_la_validation_accreditee_leve_l_effet_juridique():
    c = generer_clause('conciliation', p_conciliation())
    assert c.porte_effet_juridique is False
    valider_par_professionnel(c, {
        'nom': 'Me Salma Ben Ammar', 'qualite': 'avocate au barreau de Tunis',
        'numero_accreditation': 'BT-2019-0442'})
    assert c.porte_effet_juridique is True
    assert c.valide_par['numero_accreditation'] == 'BT-2019-0442'
    assert 'VALIDÉ PAR' in c.texte


@pytest.mark.parametrize('pro', [
    {}, None,
    {'nom': 'X'},
    {'nom': 'X', 'qualite': 'avocat'},
    {'nom': '  ', 'qualite': 'avocat', 'numero_accreditation': 'A-1'},
    {'nom': 'X', 'qualite': 'avocat', 'numero_accreditation': ''},
])
def test_validation_anonyme_ou_incomplete_refusee(pro):
    """Une validation qui n'identifie personne n'engage personne."""
    c = generer_clause('conciliation', p_conciliation())
    with pytest.raises(ParametreInvalide):
        valider_par_professionnel(c, pro)
    assert c.porte_effet_juridique is False
    assert c.valide_par is None


def test_analyse_ne_porte_jamais_effet_juridique():
    a = analyser_contrat("Article 12 — Tout litige sera tranché par arbitrage.")
    assert a.porte_effet_juridique is False
    assert a.opposable_en_l_etat is False
    assert a.valide_par is None


# --------------------------------------------------------------------------
# 2. Les citations : retrouvées dans le corpus, jamais inventées
# --------------------------------------------------------------------------

def test_chaque_article_cite_existe_dans_le_corpus_avec_son_texte():
    """Le numéro seul ne prouve rien : on revérifie le texte arabe aussi."""
    docs = g._docs()
    for voie, articles in g.FONDEMENTS.items():
        for a in articles:
            jumeaux = [d for d in docs
                       if d['code_id'] == a.code_id
                       and d['article'] == a.article       # INT, pas str
                       and d['text_ar'] == a.texte_ar]
            assert jumeaux, f"{voie}: {a.code_id} art.{a.article} introuvable"
            assert jumeaux[0]['citation_ar'] == a.citation_ar


def test_coc_1458_fonde_bien_la_conciliation():
    """Le fondement annoncé par le métier, vérifié dans le corpus."""
    art = next(a for a in g.FONDEMENTS['conciliation']
               if a.code_id == 'coc' and a.article == 1458)
    assert 'الصلح عقد وضع لرفع النزاع وقطع الخصومة' in art.texte_ar
    assert art.citation_ar == 'الفصل 1458 من مجلة الالتزامات والعقود'
    c = generer_clause('conciliation', p_conciliation())
    assert art.citation_ar in c.texte


def test_l_arbitrage_cite_la_mjalla_du_tahkim():
    c = generer_clause('arbitrage', p_arbitrage())
    cites = {(a['code_id'], a['article']) for a in c.articles}
    assert ('arbitrage', 2) in cites   # convention d'arbitrage
    assert ('arbitrage', 3) in cites   # clause compromissoire
    assert ('arbitrage', 17) in cites  # objet + nombre pair
    assert 'الفصل 17 من مجلة التحكيم' in c.texte


def test_l_ancrage_passe_la_garde_anti_hallucination():
    """Même garde (MIN_SCORE, MIN_MATCHED) que le reste de la plateforme."""
    rapport = verifier_ancrage()
    assert rapport
    non_fondes = [r for r in rapport if not r['grounded']]
    assert not non_fondes, f"articles non ancrés : {non_fondes}"


def test_les_citations_arabes_ne_sont_pas_reformulees():
    """Aucune citation ne doit avoir été retouchée après extraction."""
    docs = {(d['code_id'], d['article'], d['text_ar']): d for d in g._docs()}
    for articles in g.FONDEMENTS.values():
        for a in articles:
            assert (a.code_id, a.article, a.texte_ar) in docs


def test_les_reserves_sont_portees_au_document():
    """Citer un article d'arbitrage international sans le dire serait trompeur."""
    c = generer_clause('arbitrage', p_arbitrage())
    reserves = [a for a in c.articles if a['reserve']]
    assert reserves
    assert 'arbitrage international' in c.texte


# --------------------------------------------------------------------------
# 3. La médiation : abstention, pas improvisation
# --------------------------------------------------------------------------

@pytest.mark.parametrize('voie', ['mediation', 'médiation', 'MÉDIATION',
                                  ' Mediation ', 'Médiation'])
def test_la_mediation_est_refusee_faute_de_fondement(voie):
    with pytest.raises(VoieNonFondee) as e:
        generer_clause(voie, p_conciliation())
    msg = str(e.value)
    assert 'وساطة' in msg          # le refus cite ce que le corpus contient
    assert '601' in msg            # l'article de courtage, nommément


def test_la_mediation_n_est_pas_dans_les_voies_disponibles():
    assert 'mediation' not in voies_disponibles()
    assert set(voies_disponibles()) == {'conciliation', 'arbitrage'}


def test_les_lacunes_du_corpus_sont_rendues_avec_le_document():
    """Le client doit lire ce que le corpus NE fonde pas, pas le deviner."""
    c = generer_clause('arbitrage', p_arbitrage())
    objets = {l['objet'] for l in c.lacunes}
    assert 'médiation' in objets
    assert 'langue de la procédure' in objets
    assert 'répartition des frais' in objets
    assert 'CE QUE LE CORPUS NE FONDE PAS' in c.texte
    assert lacunes_corpus() == c.lacunes


@pytest.mark.parametrize('voie', [
    'transaction', 'expertise', '', '   ', 'arbitrag', 'التحكيم',
    None, 42, 3.14, [], {}, ['arbitrage'], b'arbitrage',
    'arbitrage; DROP TABLE', 'conciliation\x00', '../../etc/passwd',
])
def test_voie_inconnue_refusee(voie):
    with pytest.raises(VoieInconnue):
        generer_clause(voie, p_conciliation())


# --------------------------------------------------------------------------
# 4. Les paramètres : ce qui rendrait la clause nulle est refusé
# --------------------------------------------------------------------------

@pytest.mark.parametrize('n', [2, 4, 6, 8, 100])
def test_nombre_pair_d_arbitres_refuse(n):
    """Art. 17 : un tribunal en nombre pair doit être complété — donc refusé."""
    with pytest.raises(ParametreInvalide) as e:
        generer_clause('arbitrage', p_arbitrage(nombre_arbitres=n))
    assert 'IMPAIR' in str(e.value)
    assert '17' in str(e.value)


@pytest.mark.parametrize('n', [0, -1, -3])
def test_nombre_nul_ou_negatif_d_arbitres_refuse(n):
    with pytest.raises(ParametreInvalide):
        generer_clause('arbitrage', p_arbitrage(nombre_arbitres=n))


@pytest.mark.parametrize('n', [1, 3, 5, 7])
def test_nombre_impair_d_arbitres_accepte(n):
    c = generer_clause('arbitrage', p_arbitrage(nombre_arbitres=n))
    assert c.parametres['nombre_arbitres'] == n


def test_nombre_d_arbitres_excessif_refuse():
    with pytest.raises(ParametreInvalide):
        generer_clause('arbitrage', p_arbitrage(nombre_arbitres=99))


def test_nombre_d_arbitres_manquant_en_arbitrage_refuse():
    with pytest.raises(ParametreInvalide):
        generer_clause('arbitrage', p_arbitrage(nombre_arbitres=None))


def test_nombre_d_arbitres_sur_une_conciliation_refuse():
    """Il n'y a pas d'arbitre dans une conciliation : c'est une confusion."""
    with pytest.raises(ParametreInvalide) as e:
        generer_clause('conciliation', p_conciliation(nombre_arbitres=3))
    assert 'conciliation' in str(e.value)


@pytest.mark.parametrize('d', [0, -1, -30, -10_000])
def test_delai_de_saisine_negatif_ou_nul_refuse(d):
    with pytest.raises(ParametreInvalide) as e:
        generer_clause('conciliation', p_conciliation(delai_saisine_jours=d))
    assert 'strictement positif' in str(e.value)
    with pytest.raises(ParametreInvalide):
        generer_clause('arbitrage', p_arbitrage(delai_saisine_jours=d))


@pytest.mark.parametrize('d', [366, 10_000, 999_999])
def test_delai_de_saisine_excessif_refuse(d):
    with pytest.raises(ParametreInvalide):
        generer_clause('conciliation', p_conciliation(delai_saisine_jours=d))


@pytest.mark.parametrize('d', ['30', 30.5, True, None, [30]])
def test_delai_non_entier_refuse(d):
    with pytest.raises(ParametreInvalide):
        generer_clause('conciliation', p_conciliation(delai_saisine_jours=d))


@pytest.mark.parametrize('m', [0, -6, 25, 1000])
def test_delai_de_procedure_hors_bornes_refuse(m):
    with pytest.raises(ParametreInvalide):
        generer_clause('arbitrage', p_arbitrage(delai_procedure_mois=m))


@pytest.mark.parametrize('lieu', ['', '   ', '\x00\x01', '\n\t', None, 42])
def test_lieu_manquant_refuse(lieu):
    with pytest.raises(ParametreInvalide):
        generer_clause('conciliation', p_conciliation(lieu=lieu))


@pytest.mark.parametrize('langue', ['klingon', '', None, 'ar', 42, 'العربية'])
def test_langue_de_procedure_inconnue_refusee(langue):
    with pytest.raises(ParametreInvalide):
        generer_clause('conciliation', p_conciliation(langue=langue))


@pytest.mark.parametrize('rep', ['gratuit', '', None, 'moitie'])
def test_repartition_des_frais_inconnue_refusee(rep):
    with pytest.raises(ParametreInvalide):
        generer_clause('conciliation', p_conciliation(repartition_frais=rep))


def test_parametres_qui_ne_sont_pas_des_parametres_refuses():
    for mauvais in [None, {}, 'Sfax', 42, ['Sfax']]:
        with pytest.raises(ParametreInvalide):
            generer_clause('conciliation', mauvais)


# --------------------------------------------------------------------------
# 5. Le contenu bilingue des trois voies
# --------------------------------------------------------------------------

def test_les_deux_voies_fondees_sont_bilingues():
    for voie, params in [('conciliation', p_conciliation()),
                         ('arbitrage', p_arbitrage())]:
        c = generer_clause(voie, params)
        assert isinstance(c, ClauseReglement)
        # du français
        assert re.search(r"[a-zàâçéèêëîïôûùüÿœ]{20}", c.clause_fr.lower()
                         .replace(' ', 'x')) or len(c.clause_fr) > 200
        # de l'arabe, en quantité
        arabes = sum(1 for ch in c.clause_ar if '\u0600' <= ch <= '\u06FF')
        assert arabes > 200, f"{voie}: texte arabe trop court ({arabes})"
        # aucun placeholder oublié
        assert '{' not in c.clause_fr and '{' not in c.clause_ar
        assert 'None' not in c.clause_fr


def test_les_parametres_figurent_reellement_dans_les_deux_textes():
    c = generer_clause('arbitrage', p_arbitrage(
        delai_saisine_jours=21, lieu='Sousse', nombre_arbitres=3,
        delai_procedure_mois=4, langue='français'))
    assert '21' in c.clause_fr and '21' in c.clause_ar
    assert 'Sousse' in c.clause_fr and 'Sousse' in c.clause_ar
    assert '3 arbitres' in c.clause_fr and '3 محكمين' in c.clause_ar
    assert '4 mois' in c.clause_fr and '4 أشهر' in c.clause_ar
    assert 'français' in c.clause_fr and 'الفرنسية' in c.clause_ar


def test_l_arbitrage_rappelle_que_l_exequatur_reste_judiciaire():
    """La clause ne doit pas laisser croire qu'elle vaut titre exécutoire."""
    c = generer_clause('arbitrage', p_arbitrage())
    assert 'exequatur' in c.clause_fr
    assert 'aucune force exécutoire' in c.clause_fr
    assert 'بإذن من رئيس المحكمة الابتدائية' in c.clause_ar


def test_la_conciliation_rappelle_les_matieres_exclues():
    c = generer_clause('conciliation', p_conciliation())
    assert 'ordre public' in c.clause_fr
    assert 'لا يجوز الصلح' in c.clause_ar


def test_arbitre_unique_redige_au_singulier():
    c = generer_clause('arbitrage', p_arbitrage(nombre_arbitres=1))
    assert 'arbitre unique' in c.clause_fr
    assert 'محكم فرد' in c.clause_ar


def test_sans_institution_l_arbitrage_est_ad_hoc():
    c = generer_clause('arbitrage', p_arbitrage(institution=None))
    assert 'ad hoc' in c.clause_fr
    assert 'التحكيم حر' in c.clause_ar


def test_accord_arabe_du_decompte_de_jours():
    """« 3 يوما » est une faute ; un acte juridique ne doit pas la porter."""
    assert '3 أيام' in generer_clause(
        'conciliation', p_conciliation(delai_saisine_jours=3)).clause_ar
    assert '15 يوما' in generer_clause(
        'conciliation', p_conciliation(delai_saisine_jours=15)).clause_ar


def test_caracteres_de_controle_dans_le_lieu_sont_neutralises():
    c = generer_clause('arbitrage', p_arbitrage(lieu='Tunis\x00\x07'))
    assert '\x00' not in c.texte and '\x07' not in c.texte
    assert 'Tunis' in c.clause_fr


def test_le_document_est_serialisable():
    """L'API doit pouvoir rendre la clause en JSON sans traitement spécial."""
    import json
    c = generer_clause('arbitrage', p_arbitrage())
    d = c.to_dict()
    assert d['porte_effet_juridique'] is False and d['valide_par'] is None
    json.dumps(d, ensure_ascii=False)


# --------------------------------------------------------------------------
# 6. L'analyse d'un contrat existant
# --------------------------------------------------------------------------

CONTRAT_ARBITRAGE = """CONTRAT DE FOURNITURE
Article 1 — Objet. Le fournisseur livre 200 châssis en aluminium.
Article 2 — Prix. Le prix est de 48 000 dinars, payable à trente jours.
Article 14 — Règlement des litiges. Tout différend né de l'exécution ou
de l'interprétation du présent contrat sera tranché définitivement par voie
d'arbitrage. Le tribunal arbitral est composé de trois arbitres, chaque partie
en désignant un. Le siège de l'arbitrage est fixé à Tunis.
Article 15 — Loi applicable. Le contrat est régi par le droit tunisien.
"""

CONTRAT_SANS_CLAUSE = """CONTRAT DE PRESTATION
Article 1 — Objet. Le prestataire assure la maintenance du parc informatique.
Article 2 — Durée. Douze mois renouvelables.
Article 3 — Prix. 900 dinars par mois, payables le 5 de chaque mois.
"""

CONTRAT_NEGATION = """CONTRAT DE VENTE
Article 9 — Le présent contrat ne comporte aucune clause d'arbitrage. Les
parties conviennent expressément que la médiation est exclue.
Article 10 — Tout litige relève du tribunal de première instance de Sfax.
"""

CONTRAT_ARABE = """عقد بيع
الفصل 8 — كل نزاع ينشأ عن هذا العقد يعرض على محاولة صلح بين الطرفين في أجل
ثلاثين يوما، وتجري المصالحة بمدينة صفاقس وتكون لغتها العربية، ويحرر الاتفاق
كتابة. ومصاريف المصالحة يتحملها الطرفان بالتساوي. وعند التعذر تكون المحكمة
المختصة هي محكمة صفاقس.
"""


def test_contrat_avec_clause_d_arbitrage_detectee():
    a = analyser_contrat(CONTRAT_ARBITRAGE)
    assert isinstance(a, AnalyseContrat)
    assert a.clause_detectee == 'arbitrage'
    assert a.contrat_vide is False
    assert 'arbitrage' in a.avis


def test_l_extrait_est_cite_mot_pour_mot_jamais_paraphrase():
    """Le point non négociable : on cite le contrat, on ne le raconte pas."""
    a = analyser_contrat(CONTRAT_ARABIGE := CONTRAT_ARBITRAGE)
    assert a.mentions
    for m in a.mentions:
        if m['extrait_tronque']:
            continue
        assert m['extrait'] in CONTRAT_ARABIGE, m['extrait']
        # les bornes rendues désignent bien cet extrait
        assert CONTRAT_ARABIGE[m['debut']:m['fin']].strip() == m['extrait']


def test_l_extrait_cite_la_stipulation_entiere_pas_un_fragment():
    """Régression : les contrats sont retournés à la ligne à 70 colonnes.

    En coupant sur le simple saut de ligne, l'analyse citait « d'arbitrage »
    au lieu de la stipulation complète, puis concluait que l'objet du litige et
    la désignation des arbitres MANQUAIENT alors qu'ils figuraient noir sur
    blanc. Un avis juridique faux est pire que pas d'avis.
    """
    a = analyser_contrat(CONTRAT_ARBITRAGE)
    arb = [m for m in a.mentions if m['voie'] == 'arbitrage']
    assert arb
    principal = max(arb, key=lambda m: len(m['extrait']))
    assert len(principal['extrait']) > 60, principal['extrait']
    assert principal['extrait'] in CONTRAT_ARBITRAGE
    manquants = {m['element'] for m in a.manques}
    # ces deux-là SONT dans le contrat : les signaler manquants serait faux
    assert 'objet du litige' not in manquants
    assert 'désignation des arbitres' not in manquants
    assert "nombre impair d'arbitres" not in manquants


def test_les_manques_de_la_clause_sont_signales():
    a = analyser_contrat(CONTRAT_ARBITRAGE)
    manquants = {m['element'] for m in a.manques}
    # le contrat ne dit ni la langue, ni le délai, ni les frais
    assert 'langue de la procédure' in manquants
    assert 'répartition des frais' in manquants
    # chaque manque explique POURQUOI il compte
    assert all(m['pourquoi'] for m in a.manques)


def test_clause_citee_dans_une_negation_n_est_pas_une_clause():
    """« ne comporte aucune clause d'arbitrage » ne stipule pas un arbitrage."""
    a = analyser_contrat(CONTRAT_NEGATION)
    assert a.clause_detectee is None
    assert 'arbitrage' in a.voies_ecartees
    assert any(m['dans_une_negation'] for m in a.mentions)
    assert 'écarter' in a.avis


def test_contrat_sans_aucune_clause():
    a = analyser_contrat(CONTRAT_SANS_CLAUSE)
    assert a.clause_detectee is None
    assert a.mentions == []
    assert a.voies_ecartees == []
    assert 'Aucune clause' in a.avis


def test_contrat_uniquement_en_arabe():
    a = analyser_contrat(CONTRAT_ARABE)
    assert a.clause_detectee == 'conciliation'
    assert a.langues_detectees == ['arabe']
    assert a.mentions and a.mentions[0]['extrait'] in CONTRAT_ARABE


def test_le_tribunal_arabe_n_est_pas_lu_comme_un_arbitrage():
    """Régression : « المحكمة » (le tribunal) contient « محكم » (arbitre).

    Sans garde de frontière de mot arabe, un contrat qui renvoie au TRIBUNAL
    compétent était lu comme stipulant un ARBITRAGE — soit exactement l'inverse
    de ce que le contrat dit. C'est la faute la plus grave que ce module puisse
    commettre, donc elle est verrouillée.
    """
    a = analyser_contrat(
        "الفصل 12 — كل نزاع يعرض على المحكمة الابتدائية بتونس، وهي المحكمة "
        "المختصة دون سواها.")
    assert a.clause_detectee is None
    assert not any(m['voie'] == 'arbitrage' for m in a.mentions)


def test_contrat_uniquement_en_francais():
    a = analyser_contrat(CONTRAT_ARBITRAGE)
    assert 'latin' in a.langues_detectees
    assert 'arabe' not in a.langues_detectees


@pytest.mark.parametrize('vide', ['', '   ', '\n\n\t', '\x00\x00\x00', '\r\n'])
def test_contrat_vide_refuse_poliment(vide):
    a = analyser_contrat(vide)
    assert a.contrat_vide is True
    assert a.clause_detectee is None
    assert 'vide' in a.avis


@pytest.mark.parametrize('mauvais', [None, 42, [], {}, b'contrat', 3.14])
def test_contrat_non_textuel_refuse(mauvais):
    with pytest.raises(ContratIllisible):
        analyser_contrat(mauvais)


def test_contrat_tres_long_est_analyse_sans_exploser():
    remplissage = "Article de remplissage sans portée juridique. " * 20_000
    a = analyser_contrat(remplissage + CONTRAT_ARBITRAGE)
    assert a.clause_detectee == 'arbitrage'
    for m in a.mentions:
        assert len(m['extrait']) <= g.LONGUEUR_EXTRAIT_MAX + 4


def test_contrat_demesure_refuse_plutot_que_tronque():
    with pytest.raises(ContratIllisible):
        analyser_contrat('x' * (g.TAILLE_MAX_CONTRAT + 1))


def test_caracteres_de_controle_n_empechent_pas_la_detection():
    """Un contrat collé depuis un PDF traîne des \\x00 : la clause reste là."""
    sale = CONTRAT_ARBITRAGE.replace(' ', '\x00 ', 30)
    a = analyser_contrat(sale)
    assert a.caracteres_de_controle_retires is True
    assert a.clause_detectee == 'arbitrage'
    for m in a.mentions:
        assert '\x00' not in m['extrait']


def test_une_mediation_stipulee_est_signalee_sans_etre_appreciee():
    a = analyser_contrat(
        "Article 7 — Tout différend sera soumis à une médiation préalable.")
    assert a.clause_detectee == 'mediation'
    assert any('fondement' in m['element'] for m in a.manques)
    assert 'professionnel accrédité' in a.avis
    assert a.articles == []      # aucun article cité : aucun ne le fonde


def test_l_arbitrage_prime_sur_la_conciliation_quand_les_deux_figurent():
    """Une clause échelonnée existe ; l'arbitrage est la voie qui tranche."""
    a = analyser_contrat(
        "Article 11 — Les parties tenteront une conciliation. À défaut, le "
        "litige sera tranché par arbitrage à Tunis en langue arabe, par trois "
        "arbitres, dans un délai de six mois, les frais étant partagés.")
    assert a.clause_detectee == 'arbitrage'
    voies = {m['voie'] for m in a.mentions}
    assert {'arbitrage', 'conciliation'} <= voies


def test_analyse_serialisable():
    import json
    a = analyser_contrat(CONTRAT_ARBITRAGE)
    json.dumps(a.to_dict(), ensure_ascii=False)
