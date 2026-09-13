"""Tests du moteur d'analyse de risques des contrats.

Run: cd ~/mizan && source .venv/bin/activate && pytest packages/contrats/ -q

CE QUE CES TESTS CHERCHENT À CASSER
-----------------------------------
Pas « est-ce que ça trouve la clause pénale ». Un détecteur par mots-clés
trouve toujours le mot qu'on lui a appris. Ce qui casse un outil juridique en
démonstration, c'est l'inverse : ce qu'il affirme à tort.

Les tests sont donc écrits d'abord contre les entrées HOSTILES — contrat vide,
document qui n'est pas un contrat, clause citée dans une négation, texte
gigantesque, caractères de contrôle — et ensuite seulement sur les deux
contrats d'exemple.

Deux tests valent plus que tous les autres :
  - test_abstention_*   : le moteur se tait quand il n'a rien à dire.
  - test_aucune_citation_inventee : chaque article cité EXISTE dans le corpus,
    avec exactement la citation arabe rendue.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

RACINE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from analyse import (  # noqa: E402
    CATALOGUE,
    LIMITE_CARACTERES,
    MESSAGE_ABSTENTION,
    analyser,
    analyser_pdf,
    detecter_langues,
    est_un_contrat,
    normaliser,
    rendre,
)
from fondements import LACUNES, charger, fondement  # noqa: E402

EXEMPLES = pathlib.Path(__file__).resolve().parent / 'exemples'
CONTRAT_FR = EXEMPLES / 'contrat_fr_fourniture.txt'
CONTRAT_AR = EXEMPLES / 'contrat_ar_entreprise.txt'


def _lire(chemin: pathlib.Path) -> str:
    return chemin.read_text(encoding='utf-8')


def _identifiants(rapport) -> set:
    return {c.identifiant for c in rapport.clauses}


# ===========================================================================
# 1. ENTRÉES HOSTILES — écrites avant les cas heureux, exprès.
# ===========================================================================

def test_abstention_texte_vide():
    """Un document vide ne produit RIEN, et le dit."""
    r = analyser('')
    assert r.analyse is False
    assert r.clauses == []
    assert 'vide' in r.motif_abstention
    assert 'ABSTENTION' in rendre(r)


@pytest.mark.parametrize('blanc', ['   ', '\n\n\n', '\t\t', '\x00\x0b\x1f'])
def test_abstention_texte_blanc_ou_controle(blanc):
    """Espaces, sauts de ligne et caractères de contrôle ne font pas un contrat."""
    r = analyser(blanc)
    assert r.analyse is False
    assert r.clauses == []


def test_abstention_document_qui_nest_pas_un_contrat():
    """Un CV n'est pas un contrat : aucune clause ne doit en sortir.

    C'est la faute que doc_gate.py a corrigée pour les factures (Mizan avait
    produit une mise en demeure à partir du programme du hackathon). La
    version contrat de cette faute serait d'« analyser les risques » d'un CV.
    """
    cv = (
        "CURRICULUM VITAE\n"
        "Ahmed Ben Salah — Ingenieur en genie civil\n"
        "Experience : 8 ans, societe de travaux publics, Tunis.\n"
        "Formation : ENIT, 2016. Langues : arabe, francais, anglais.\n"
        "Competences : penalites de retard, arbitrage, gestion de contrats.\n"
    )
    r = analyser(cv)
    assert r.analyse is False, "un CV ne doit jamais produire de clauses"
    assert r.clauses == []
    assert MESSAGE_ABSTENTION in rendre(r)


def test_abstention_texte_hors_sujet():
    """Une recette de cuisine ne porte aucun risque contractuel."""
    r = analyser("Recette du couscous : semoule, pois chiches, agneau. "
                 "Cuire a la vapeur pendant une heure.")
    assert r.analyse is False
    assert r.clauses == []


def test_abstention_mots_cles_sans_contrat():
    """Le piège : les mots-clés présents, mais aucun contrat autour.

    Un article de presse qui parle de clauses pénales et d'arbitrage contient
    tout le vocabulaire du moteur. S'il suffisait des mots-clés, l'outil
    « analyserait » un journal.
    """
    presse = (
        "Selon nos informations, les penalites de retard et la clause penale "
        "font debat chez les juristes tunisiens. L'arbitrage progresse."
    )
    r = analyser(presse)
    assert r.analyse is False
    assert r.clauses == []


def test_negation_clause_penale_non_signalee():
    """« ne contient aucune clause pénale » ne doit PAS déclencher d'alerte.

    Alerter ici, c'est alerter sur le contraire exact de ce que dit le
    contrat : le client renoncerait à une signature qui ne portait pas ce
    risque.
    """
    texte = (
        "CONTRAT DE PRESTATION\n"
        "Entre les soussignes, il a ete convenu ce qui suit.\n"
        "Article 1 : Le prestataire s'engage a livrer le rapport.\n"
        "Article 2 : Le present contrat ne contient aucune clause penale.\n"
    )
    r = analyser(texte)
    assert r.analyse is True
    assert 'clause_penale' not in _identifiants(r)
    assert any(n['identifiant'] == 'clause_penale' for n in r.niees)


@pytest.mark.parametrize('phrase,identifiant', [
    ("Le present contrat ne comporte aucune clause compromissoire.",
     'arbitrage'),
    ("Aucune clause resolutoire n'est prevue aux presentes.",
     'clause_resolutoire'),
    ("Les parties excluent toute clause de reserve de propriete.",
     'reserve_propriete'),
    ("Aucune penalite de retard n'est applicable au present marche.",
     'penalite_retard'),
])
def test_negations_francaises(phrase, identifiant):
    """Chaque tournure négative française neutralise sa clause."""
    texte = ("CONTRAT CADRE\nEntre les soussignes, il a ete convenu.\n"
             "Article 1 : " + phrase + "\n")
    r = analyser(texte)
    assert r.analyse is True
    assert identifiant not in _identifiants(r), (
        f"« {phrase} » a été lue comme une clause présente")


def test_negation_arabe():
    """La négation arabe « لا يتضمن هذا العقد أي شرط تحكيم » neutralise aussi."""
    texte = (
        "عقد بيع\n"
        "اتفق الطرفان على ما يلي :\n"
        "الفصل 1 : لا يتضمن هذا العقد أي شرط تحكيم، وتبقى المحاكم التونسية "
        "هي المختصة.\n"
    )
    r = analyser(texte)
    assert r.analyse is True
    assert 'arbitrage' not in _identifiants(r)


def test_negation_ne_fait_pas_taire_une_clause_reelle():
    """Une négation ailleurs dans le contrat ne doit pas masquer la vraie clause.

    Le risque symétrique du test précédent : un filtre de négation trop large
    ferait taire des clauses réellement stipulées.
    """
    texte = (
        "CONTRAT DE FOURNITURE\n"
        "Entre les soussignes, il a ete convenu ce qui suit.\n"
        "Article 1 : Le present contrat ne contient aucune clause penale.\n"
        "Article 2 : Tout litige sera tranche par voie d'arbitrage a Tunis.\n"
    )
    r = analyser(texte)
    assert 'clause_penale' not in _identifiants(r)
    assert 'arbitrage' in _identifiants(r), (
        "la clause d'arbitrage réelle a été masquée par une négation voisine")


@pytest.mark.parametrize('phrase,identifiant', [
    # Une négation qui porte sur AUTRE CHOSE, dans une phrase antérieure, ne
    # doit pas neutraliser la stipulation qui suit. Le filtre de négation a
    # été élargi pour attraper « Aucune pénalité de retard n'est applicable » ;
    # ces cas vérifient qu'il ne mord pas au-delà de sa phrase.
    ("Aucun retard ne sera tolere. Le contrat sera resilie de plein droit "
     "sans mise en demeure.", 'clause_resolutoire'),
    ("Nul ne peut ceder le contrat. Tout litige sera tranche par voie "
     "d'arbitrage.", 'arbitrage'),
    ("Le client renonce a se prevaloir de la prescription.",
     'renonciation_prescription'),
])
def test_negation_ne_franchit_pas_la_phrase(phrase, identifiant):
    """La négation d'une phrase ne neutralise pas la phrase suivante."""
    texte = ("CONTRAT\nEntre les soussignes, il a ete convenu.\n"
             "Article 1 : " + phrase + "\n")
    r = analyser(texte)
    assert identifiant in _identifiants(r), (
        f"clause réelle masquée à tort dans : {phrase}")


def test_caracteres_de_controle_ne_cassent_pas_l_analyse():
    """Un PDF mal extrait charrie \\x00 et \\x0b : la clause doit sortir quand même."""
    texte = (
        "CONTRAT\x00 DE VENTE\n"
        "Entre les\x0b soussignes, il a ete convenu.\n"
        "Article 1 :\x1f Le contrat sera resilie de plein droit, sans "
        "sommation ni mise en demeure.\n"
    )
    r = analyser(texte)
    assert r.analyse is True
    assert 'clause_resolutoire' in _identifiants(r)
    for c in r.clauses:
        assert '\x00' not in c.extrait
        assert '\x0b' not in c.extrait


def test_texte_tres_long_ne_bloque_pas():
    """Un contrat énorme est analysé, borné, et le rapport reste cohérent."""
    base = _lire(CONTRAT_FR)
    gros = base + ("\nArticle de remplissage sans portee juridique.\n" * 20000)
    r = analyser(gros)
    assert r.analyse is True
    assert r.n_caracteres <= LIMITE_CARACTERES
    assert 'clause_resolutoire' in _identifiants(r)


def test_contrat_uniquement_arabe():
    """Un contrat sans un mot de français doit être analysé normalement."""
    texte = (
        "عقد كراء محل تجاري\n"
        "اتفق الطرفان على ما يلي :\n"
        "الفصل 1 : يلتزم المكتري بخلاص معين الكراء شهريا.\n"
        "الفصل 2 : في صورة التأخير تطبق خطية تأخير بنسبة 2 % عن كل شهر.\n"
        "الفصل 3 : ينفسخ العقد بمجرد عدم الخلاص دون حاجة إلى إنذار.\n"
    )
    r = analyser(texte)
    assert r.analyse is True
    assert r.langues == ['ar']
    assert {'penalite_retard', 'clause_resolutoire'} <= _identifiants(r)


def test_contrat_uniquement_francais():
    """Symétrique : un contrat sans un mot d'arabe."""
    r = analyser(_lire(CONTRAT_FR))
    assert r.analyse is True
    assert r.langues == ['fr']


def test_pdf_inexistant_ne_leve_pas():
    """Un chemin invalide produit une abstention, pas une exception."""
    r = analyser_pdf('/tmp/ce-fichier-nexiste-pas-mizan.pdf')
    assert r.analyse is False
    assert 'introuvable' in r.motif_abstention


def test_normalisation_conserve_la_longueur():
    """Invariant CRITIQUE : les positions rendues doivent rester valides.

    Les extraits sont prélevés sur le texte BRUT, aux positions trouvées sur
    le texte NORMALISÉ. Si la normalisation décalait d'un seul caractère, les
    extraits cités seraient tronqués ou décalés — et une citation décalée est
    une citation fausse.
    """
    for echantillon in [
        _lire(CONTRAT_FR),
        _lire(CONTRAT_AR),
        "مسؤولية هيئة التحكيم الشرط الجزائي",
        "Pénalité de retard — clause résolutoire\x00",
        "٠١٢٣٤٥٦٧٨٩",
    ]:
        assert len(normaliser(echantillon)) == len(echantillon)


# ===========================================================================
# 2. ANCRAGE DANS LE CORPUS — le cœur de la promesse.
# ===========================================================================

def test_corpus_charge():
    """Le corpus est bien là, avec le volume réellement observé.

    ATTENTION AU CHIFFRE. Le corpus compte 4087 LIGNES jsonl, mais seulement
    2825 couples (code, article) DISTINCTS : l'OCR de l'Imprimerie Officielle
    a produit des doublons (un même article réparti sur deux pages revient
    deux fois). fondements.charger() indexe par couple et garde la première
    occurrence, d'où 2825 et non 4087. Un test calé sur 4087 échouerait en
    accusant à tort le chargement.
    """
    index = charger()
    assert len(index) == 2825, (
        f"le corpus a changé de volume : {len(index)} articles distincts "
        "au lieu de 2825 — vérifier corpus/*.jsonl avant de corriger ce test")
    # Les six codes annoncés sont tous représentés.
    codes = {f.code_id for f in index.values()}
    assert codes == {'coc', 'fiscal', 'societes', 'commerce', 'procciv',
                     'arbitrage'}


def test_cle_article_est_un_int():
    """Le corpus stocke `article` en INT : le moteur doit s'y conformer.

    Chercher ('coc', '386') au lieu de ('coc', 386) renvoie None en silence,
    ce qui désactiverait la règle sans le moindre message d'erreur.
    """
    assert fondement('coc', 386) is not None
    assert fondement('coc', '386') is not None, (
        "fondement() doit tolérer une str et la convertir en int")


def test_tous_les_fondements_du_catalogue_existent():
    """Chaque (code, article) déclaré est réellement dans le corpus."""
    manquants = []
    for regle in CATALOGUE:
        for code_id, article in regle.fondements:
            if fondement(code_id, article) is None:
                manquants.append(f"{regle.identifiant}: {code_id} {article}")
    assert not manquants, f"articles introuvables dans le corpus : {manquants}"


def test_aucune_citation_inventee():
    """LE test anti-hallucination.

    Toute citation arabe rendue par le moteur doit être IDENTIQUE, caractère
    pour caractère, à celle portée par le corpus. Aucune n'est écrite à la
    main dans le code : elles sont toutes relues. Ce test vérifie que ce
    contrat n'a pas été rompu.
    """
    index = charger()
    for chemin in (CONTRAT_FR, CONTRAT_AR):
        r = analyser(_lire(chemin))
        assert r.clauses, f"aucune clause détectée dans {chemin.name}"
        for clause in r.clauses:
            assert clause.fondements, (
                f"{clause.identifiant} rendu sans aucun fondement")
            for f in clause.fondements:
                ref = index.get((f.code_id, f.article))
                assert ref is not None, (
                    f"article cité hors corpus : {f.code_id} {f.article}")
                assert f.citation_ar == ref.citation_ar
                assert f.extrait_ar and f.extrait_ar in ref.texte_ar


def test_extraits_sont_verbatim():
    """L'extrait rendu doit se retrouver mot pour mot dans le contrat.

    Le juriste doit pouvoir citer l'extrait à l'audience. Une paraphrase, même
    fidèle, n'est pas citable : on vérifie donc que chaque mot de l'extrait
    figure bien dans le texte source, dans cet ordre.
    """
    for chemin in (CONTRAT_FR, CONTRAT_AR):
        source = _lire(chemin)
        aplati = ' '.join(source.split())
        for clause in analyser(source).clauses:
            extrait = clause.extrait.rstrip('…').strip()
            assert extrait in aplati, (
                f"extrait absent du contrat {chemin.name} : {extrait!r}")


def test_position_et_ligne_sont_exploitables():
    """Position et numéro de ligne doivent pointer dans le document."""
    source = _lire(CONTRAT_FR)
    n_lignes = source.count('\n') + 1
    for clause in analyser(source).clauses:
        assert 0 <= clause.position < len(source)
        assert 1 <= clause.ligne <= n_lignes


def test_la_renonciation_a_la_prescription_est_fondee_sur_coc_386():
    """COC art. 386 est le SEUL article où le corpus tranche une nullité.

    « لا يسوغ ترك حق التمسك بمرور الزمان قبل حصوله » : la renonciation
    anticipée est interdite, la renonciation postérieure est licite. Le
    moteur doit citer cet article, et son texte doit bien dire cela.
    """
    r = analyser(_lire(CONTRAT_FR))
    clause = next(c for c in r.clauses
                  if c.identifiant == 'renonciation_prescription')
    articles = {(f.code_id, f.article) for f in clause.fondements}
    assert ('coc', 386) in articles
    texte = fondement('coc', 386).texte_ar
    assert 'مرور الزمان' in texte and 'قبل حصوله' in texte


def test_l_arbitrage_est_fonde_sur_le_code_de_l_arbitrage():
    """La clause compromissoire doit citer la mejella du même nom."""
    r = analyser(_lire(CONTRAT_AR))
    clause = next(c for c in r.clauses if c.identifiant == 'arbitrage')
    codes = {f.code_id for f in clause.fondements}
    assert 'arbitrage' in codes
    for f in clause.fondements:
        if f.code_id == 'arbitrage':
            assert 'التحكيم' in f.citation_ar


# ===========================================================================
# 3. LES CONTRATS D'EXEMPLE — cas heureux, en dernier.
# ===========================================================================

def test_contrat_fr_detections_attendues():
    """Le contrat français d'exemple : les huit clauses stipulées ressortent."""
    r = analyser(_lire(CONTRAT_FR))
    assert r.analyse is True
    attendues = {
        'clause_penale', 'attribution_juridiction', 'penalite_retard',
        'clause_resolutoire', 'limitation_responsabilite',
        'reserve_propriete', 'renonciation_prescription',
        'clause_potestative',
    }
    assert attendues <= _identifiants(r), (
        f"clauses manquées : {attendues - _identifiants(r)}")
    # L'article 11 nie expressément l'arbitrage : il ne doit PAS être signalé.
    assert 'arbitrage' not in _identifiants(r)
    assert any(n['identifiant'] == 'arbitrage' for n in r.niees)


def test_contrat_ar_detections_attendues():
    """Le contrat arabe/bilingue : les clauses arabes ressortent."""
    r = analyser(_lire(CONTRAT_AR))
    assert r.analyse is True
    assert 'ar' in r.langues
    attendues = {
        'clause_penale', 'arbitrage', 'penalite_retard',
        'clause_resolutoire', 'limitation_responsabilite',
        'renonciation_prescription', 'reserve_propriete',
        'clause_potestative',
    }
    assert attendues <= _identifiants(r), (
        f"clauses manquées : {attendues - _identifiants(r)}")


def test_contrat_bilingue_detecte_les_deux_langues():
    """Le contrat arabe double ses stipulations sensibles en français."""
    r = analyser(_lire(CONTRAT_AR))
    assert set(r.langues) == {'fr', 'ar'}


def test_gravites_ordonnees():
    """Le rapport présente le critique en premier : c'est ce qu'on lit."""
    r = analyser(_lire(CONTRAT_FR))
    niveaux = [c.gravite for c in r.clauses]
    ordre = {'critique': 0, 'eleve': 1, 'moyen': 2}
    assert niveaux == sorted(niveaux, key=lambda g: ordre[g])


def test_pas_de_doublon_sur_la_meme_stipulation():
    """Deux mots-clés dans la même phrase ne font qu'une clause.

    L'article 4 du contrat français dit « à titre de clause pénale, une
    indemnité forfaitaire » : deux motifs, une seule stipulation. En lister
    deux fait douter le juriste de toute la liste.
    """
    r = analyser(_lire(CONTRAT_FR))
    penales = [c for c in r.clauses if c.identifiant == 'clause_penale']
    assert len(penales) == 1, f"{len(penales)} doublons de clause pénale"


def test_chaque_clause_a_une_explication_en_une_phrase():
    """Le signataire doit lire ce qu'il risque, pas une note de doctrine."""
    for chemin in (CONTRAT_FR, CONTRAT_AR):
        for c in analyser(_lire(chemin)).clauses:
            assert c.explication_fr.strip()
            assert c.explication_fr.count('.') <= 2


def test_rendu_texte_contient_les_citations():
    """Le rendu lisible porte bien l'extrait ET la citation arabe."""
    sortie = rendre(analyser(_lire(CONTRAT_FR)))
    assert 'EXTRAIT DU CONTRAT' in sortie
    assert 'FONDEMENT' in sortie
    assert 'الفصل' in sortie
    assert 'CE QUE LE CORPUS NE FONDE PAS' in sortie


def test_serialisation_json():
    """Le rapport doit passer en JSON pour l'API, sans perte."""
    import json
    d = analyser(_lire(CONTRAT_AR)).to_dict()
    texte = json.dumps(d, ensure_ascii=False)
    relu = json.loads(texte)
    assert relu['analyse'] is True
    assert relu['clauses'][0]['fondements'][0]['citation_ar']


# ===========================================================================
# 4. HONNÊTETÉ — ce que le corpus ne fonde pas est DIT.
# ===========================================================================

def test_les_lacunes_sont_declarees():
    """Le rapport porte toujours la liste de ce que le corpus ne fonde pas."""
    r = analyser(_lire(CONTRAT_FR))
    assert r.lacunes
    for cle in ('clause_penale', 'clause_abusive', 'reserve_propriete',
                'limitation_responsabilite'):
        assert cle in r.lacunes
        assert len(r.lacunes[cle]) > 50


def test_clause_abusive_nest_pas_rendue():
    """Le corpus n'a AUCUN texte de droit de la consommation.

    Aucune règle du catalogue ne doit donc porter l'identifiant
    'clause_abusive' : la qualification serait invérifiable, et le client
    casserait la démo en demandant l'article.
    """
    assert 'clause_abusive' not in {r.identifiant for r in CATALOGUE}
    assert 'clause_abusive' in LACUNES
    index = charger()
    assert not [d for d in index.values() if 'المستهلك' in d.texte_ar], (
        "le corpus contient finalement un texte consommation : "
        "la lacune déclarée est à revoir")


def test_les_reserves_sont_portees_par_les_clauses_concernees():
    """Une clause dont le fondement est partiel le dit dans son rendu."""
    r = analyser(_lire(CONTRAT_FR))
    for identifiant in ('clause_penale', 'reserve_propriete',
                        'limitation_responsabilite',
                        'attribution_juridiction'):
        clause = next(c for c in r.clauses if c.identifiant == identifiant)
        assert clause.reserve_fr.strip(), (
            f"{identifiant} devrait porter une réserve explicite")


def test_regle_sans_fondement_est_desactivee(monkeypatch):
    """Si le corpus perd un article, la règle disparaît — elle n'invente pas.

    On simule la disparition de tous les articles : le moteur doit rendre zéro
    clause plutôt que des clauses sans citation.
    """
    import analyse as module
    monkeypatch.setattr(module, 'fondement', lambda code, art: None)
    r = module.analyser(_lire(CONTRAT_FR))
    assert r.analyse is True
    assert r.clauses == [], (
        "des clauses ont été rendues alors qu'aucun article n'est disponible")


def test_est_un_contrat_sur_les_exemples():
    """La porte d'entrée laisse passer les deux contrats d'exemple."""
    for chemin in (CONTRAT_FR, CONTRAT_AR):
        ok, motif, marqueurs = est_un_contrat(_lire(chemin))
        assert ok is True, f"{chemin.name} refusé : {motif}"
        assert len(marqueurs) >= 2


def test_detecter_langues_sur_texte_vide():
    """Aucune langue n'est devinée sur un texte vide."""
    assert detecter_langues('') == []
    assert detecter_langues('   \n\t') == []
