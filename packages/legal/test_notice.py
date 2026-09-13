"""Ce qui doit rester vrai du projet de mise en demeure.

Ces tests ne vérifient pas que le code s'exécute : ils verrouillent trois
engagements juridiques. Chacun échoue si l'engagement disparaît du code,
et c'est leur seule raison d'exister.

1. Le document dit qu'il n'est PAS signifié. Mizan rédige un projet ; seul un
   huissier de justice signifie (CPCC art. 5 et 60).
2. Les articles cités sont ceux du moteur déterministe, avec leur citation
   arabe exacte. Aucun n'est reformulé, aucun n'est ajouté.
3. Aucune mise en demeure n'est rédigée sur une créance prescrite.
"""
from datetime import date

import pytest

from packages.legal import notice
from packages.legal.legal_engine import SOURCES, assess

# Le dossier d'Ahmed : menuisier à Sfax, 9 520,000 DT, facture du 12 mai 2026.
AUJOURDHUI = date(2026, 9, 13)
CREANCIER = {'name': 'Menuiserie Ahmed', 'address': 'Route de Gabès km 3 — 3000 Sfax',
             'tax_id': '1234567/A/M/000', 'city': 'Sfax'}
DEBITEUR = {'name': 'Société El Amen SARL', 'address': 'Avenue Habib Bourguiba, Sfax'}
FACTURE = {'invoice_no': '2026-041', 'invoice_date': '2026-05-12'}


def dossier_ahmed():
    return assess(9520.0, '2026-05-12', 'menuiserie', today=AUJOURDHUI)


def doc_ahmed():
    return notice.construire(dossier_ahmed(), CREANCIER, DEBITEUR, FACTURE)


# --- 1. La mention de projet ------------------------------------------------

def test_la_mention_projet_non_signifie_figure_dans_le_texte():
    """Le test qui échoue si quelqu'un retire la mention.

    Un document qui porte « MISE EN DEMEURE » en en-tête, un cachet
    d'huissier à remplir et un délai de paiement ressemble, pour une PME qui
    n'est pas juriste, à un acte qui produit ses effets. Il n'en produit
    aucun tant qu'il n'est pas signifié. La mention est donc une garantie de
    fond, pas une décoration.
    """
    texte = doc_ahmed().texte
    assert 'PROJET — NON SIGNIFIÉ' in texte, (
        "Le projet d'acte ne porte plus la mention « projet — non signifié ». "
        "Un document qui ne dit pas qu'il n'est pas signifié se lit comme un "
        "acte signifié."
    )


def test_la_mention_est_repetee_en_tete_et_en_pied():
    """Une seule occurrence se perd à la première copie partielle.

    La chaîne est écrite en dur, et non lue depuis `notice.MENTION_PROJET` :
    un test qui lit la constante qu'il contrôle ne détecte pas qu'on l'a vidée.
    """
    texte = doc_ahmed().texte
    n = texte.count('PROJET — NON SIGNIFIÉ')
    assert n >= 2, (
        f"La mention n'apparaît que {n} fois. Elle doit encadrer le "
        f"document, en tête ET en pied."
    )
    lignes = [ln for ln in texte.splitlines() if ln.strip()]
    assert 'PROJET — NON SIGNIFIÉ' in lignes[0], (
        f"La première ligne lue est « {lignes[0]} » et non la mention de projet."
    )
    assert notice.MENTION_PROJET == 'PROJET — NON SIGNIFIÉ', (
        "La constante a été modifiée : la mention doit rester celle-ci, mot "
        "pour mot, car c'est elle que cherchent les tests et les relecteurs."
    )


def test_le_document_nomme_lhuissier_comme_seul_habilite():
    """Dire « non signifié » ne suffit pas : il faut dire qui peut signifier."""
    texte = doc_ahmed().texte
    assert 'huissier de justice' in texte
    assert 'عدل منفذ' in texte, (
        "Le terme arabe consacré (عدل منفذ) doit figurer : c'est celui que le "
        "lecteur tunisien reconnaît."
    )


def test_le_document_ne_se_declare_jamais_signifie():
    doc = doc_ahmed()
    d = doc.to_dict()
    assert 'signifie' not in d or d.get('signifie') is False
    # Aucune formule ne doit affirmer la signification comme un fait accompli.
    for interdit in ('a été signifié', 'acte signifié', 'dûment signifié'):
        assert interdit not in doc.texte.lower(), (
            f"Le texte contient « {interdit} » : Mizan ne signifie pas."
        )


# --- 2. Les articles viennent du moteur -------------------------------------

def test_les_articles_sont_exactement_ceux_du_moteur():
    """Ni un de plus, ni un de moins, et dans le même ordre."""
    evaluation = dossier_ahmed()
    doc = notice.construire(evaluation, CREANCIER, DEBITEUR, FACTURE)
    attendus = [(s['code_id'], s['article']) for s in evaluation.sources]
    obtenus = [(a['code_id'], a['article']) for a in doc.articles]
    assert obtenus == attendus, (
        f"Le document cite {obtenus} alors que le moteur a retenu {attendus}. "
        "Le générateur ne choisit aucun article."
    )


def test_la_citation_arabe_est_reproduite_mot_pour_mot():
    """Une citation retouchée n'est plus une citation."""
    doc = doc_ahmed()
    for a in doc.articles:
        attendue = next(
            s['citation_ar'] for s in SOURCES.values()
            if s['code_id'] == a['code_id'] and s['article'] == a['article']
        )
        assert a['citation_ar'] == attendue, (
            f"Citation altérée pour {a['short_fr']} : « {a['citation_ar']} » "
            f"au lieu de « {attendue} »."
        )
        assert a['citation_ar'] in doc.texte, (
            f"La citation arabe de {a['short_fr']} n'apparaît pas dans le "
            f"texte livré."
        )


def test_la_prescription_dun_an_est_citee_pour_un_menuisier():
    """COC art. 403, et pas le délai général de quinze ans."""
    doc = doc_ahmed()
    courts = [a['short_fr'] for a in doc.articles]
    assert 'COC art. 403' in courts, courts
    assert 'COC art. 402' not in courts, (
        "Le délai général de quinze ans ne doit pas être cité : la créance "
        "porte sur le prix de marchandises livrées."
    )
    assert 'الفصل 403 من مجلة الالتزامات والعقود' in doc.texte


def test_lacte_au_dessus_du_seuil_cite_larticle_de_lhuissier():
    """9 520 DT > 150 DT : CPCC art. 60 doit être au fondement."""
    doc = doc_ahmed()
    assert doc.huissier_requis is True
    assert 'CPCC art. 60' in [a['short_fr'] for a in doc.articles]
    assert doc.delai_jours == 5
    assert doc.delai_est_legal is True


def test_sous_le_seuil_le_delai_est_annonce_comme_delai_dusage():
    """Un délai d'usage présenté comme légal serait une règle inventée."""
    petite = assess(120.0, '2026-08-01', 'menuiserie', today=AUJOURDHUI)
    doc = notice.construire(petite, CREANCIER, DEBITEUR, FACTURE)
    assert doc.huissier_requis is False
    assert doc.delai_est_legal is False
    assert "délai d'usage" in doc.texte, (
        "Sous le seuil, aucun texte ne fixe le délai : il doit être annoncé "
        "comme un usage, pas comme la loi."
    )


# --- 3. Le refus sur créance prescrite ---------------------------------------

def test_refus_de_generer_sur_une_creance_prescrite():
    """Le garde-fou absent de la version d'origine.

    Facture du 12 mai 2024, menuiserie : prescription d'un an, échue depuis
    longtemps au 13 septembre 2026. Mettre en demeure ici fait payer un
    huissier au créancier pour s'entendre opposer la prescription.
    """
    eteinte = assess(9520.0, '2024-05-12', 'menuiserie', today=AUJOURDHUI)
    assert eteinte.is_expired is True, "Le scénario de test doit être prescrit."

    with pytest.raises(notice.CreancePrescrite) as exc:
        notice.construire(eteinte, CREANCIER, DEBITEUR, FACTURE)

    motif = str(exc.value)
    assert 'prescrite' in motif.lower()
    # Le refus doit être exploitable : dire depuis quand, et quoi faire.
    assert str(abs(eteinte.days_left)) in motif, (
        "Le refus doit chiffrer le dépassement, pas seulement le constater."
    )
    assert 'interrompu' in motif.lower(), (
        "Le refus doit mentionner l'interruption possible du délai : c'est la "
        "seule porte de sortie légitime, et elle ne se présume pas."
    )


def test_le_pdf_refuse_aussi_sur_creance_prescrite():
    """Le garde-fou ne doit pas être contournable par l'autre porte."""
    eteinte = assess(9520.0, '2024-05-12', 'menuiserie', today=AUJOURDHUI)
    with pytest.raises(notice.CreancePrescrite):
        notice.build_notice(eteinte, CREANCIER, DEBITEUR, FACTURE,
                            out_path='/tmp/ne_doit_pas_exister.pdf')


def test_une_creance_au_bord_de_la_prescription_est_toujours_redigee():
    """Le refus s'arrête exactement à l'expiration, pas avant.

    Il reste un jour : c'est précisément le moment où la mise en demeure est
    la plus utile. Un garde-fou trop large priverait le créancier du seul
    recours qui lui reste.
    """
    limite = assess(9520.0, '2025-09-14', 'menuiserie', today=AUJOURDHUI)
    assert limite.is_expired is False
    assert limite.days_left == 1
    doc = notice.construire(limite, CREANCIER, DEBITEUR, FACTURE)
    assert notice.MENTION_PROJET in doc.texte


# --- Le contenu factuel ------------------------------------------------------

def test_le_document_porte_les_parties_le_montant_et_la_facture():
    texte = doc_ahmed().texte
    assert 'Menuiserie Ahmed' in texte
    assert 'Société El Amen SARL' in texte
    assert '2026-041' in texte
    assert '12 mai 2026' in texte, "La date doit être en français juridique."
    assert '9\u00a0520,000' in texte, (
        "Le montant doit être en format français avec espace insécable."
    )


def test_le_corps_est_en_francais_et_les_citations_en_arabe():
    """Bilingue veut dire : corps français, articles en arabe d'origine."""
    doc = doc_ahmed()
    for para in doc.corps:
        assert not any('\u0600' <= c <= '\u06FF' for c in para), (
            f"Le corps français contient de l'arabe : « {para[:60]}… »"
        )
    for ligne in doc.sommation_ar:
        assert any('\u0600' <= c <= '\u06FF' for c in ligne)
    for a in doc.articles:
        assert any('\u0600' <= c <= '\u06FF' for c in a['citation_ar'])


def test_le_texte_est_reproductible():
    """Deux appels identiques donnent le même acte, au caractère près."""
    assert doc_ahmed().texte == doc_ahmed().texte


def test_le_pdf_est_produit_et_non_vide(tmp_path):
    out = tmp_path / 'med.pdf'
    chemin = notice.build_notice(dossier_ahmed(), CREANCIER, DEBITEUR,
                                 FACTURE, out_path=out)
    assert chemin.exists()
    assert chemin.stat().st_size > 2000, "PDF suspectement vide."
    assert chemin.read_bytes()[:4] == b'%PDF'
