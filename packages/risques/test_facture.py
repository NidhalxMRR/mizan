"""Tests du moteur de risques : d'abord les entrées hostiles, ensuite le cas nominal.

Pourquoi cet ordre
------------------
Le cas nominal ne prouve rien d'intéressant : il passe par construction. Ce
qui décide de la valeur de ce module, c'est son comportement sur les documents
qu'on ne lui a pas préparés — une page blanche, un montant négatif, une date
dans le futur, un contrat déguisé en facture. Un moteur juridique qui produit
une analyse confiante sur une page vide est plus dangereux qu'un moteur qui ne
produit rien.

La classe la plus importante de ce fichier est `TestAbstention` : elle vérifie
qu'aucun risque ne sort quand le corpus ne le fonde pas.

Lancer : cd ~/mizan && source .venv/bin/activate && pytest packages/risques/ -q
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from packages.risques import ancrage, fondements
from packages.risques.facture import (
    ELEVE,
    Abstention,
    RapportRisques,
    analyser,
)

RACINE = Path(__file__).resolve().parents[2]

# Jour de la démonstration, figé : un test dont le résultat dépend de la date
# d'exécution finit par échouer tout seul un matin de démonstration.
AUJOURDHUI = date(2026, 9, 13)

FACTURE_AHMED = """MENUISERIE AHMED
Route de Gabès km 3 — 3000 Sfax
Matricule fiscal : 1234567/A/M/000
Tél : 74 400 XXX
FACTURE N° 2026-041
Date : 12/05/2026
Client : Société El Amen SARL
Adresse : Avenue Habib Bourguiba, Sfax
Désignation Qté P.U. (DT) Total (DT)
Table de réunion en chêne massif 2 1,800.000 3,600.000
Chaises assorties 12 250.000 3,000.000
Pose et livraison 1 1,400.000 1,400.000
TOTAL HT 8,000.000
TVA 19% 1,520.000
NET A PAYER 9,520.000
Conditions de paiement : 30 jours fin de mois.
Marchandise livrée et réceptionnée sans réserve."""


def _sans_mentions() -> str:
    """La facture d'Ahmed privée de son numéro et de son matricule fiscal."""
    lignes = [l for l in FACTURE_AHMED.splitlines()
              if not l.startswith('Matricule fiscal')
              and not l.startswith('FACTURE N°')]
    return '\n'.join(lignes)


# ===========================================================================
# ENTRÉES HOSTILES — écrites d'abord, parce que c'est là que ça casse.
# ===========================================================================
class TestEntreesHostiles:
    """Chaque test ici correspond à un document qu'un utilisateur déposera."""

    def test_facture_vide_ne_produit_aucun_risque(self):
        """Une chaîne vide ne doit produire aucune analyse, et le dire."""
        rapport = analyser('', montant=9520.0, date_facture='2026-05-12',
                           aujourdhui=AUJOURDHUI)
        assert rapport.risques == []
        assert rapport.document_analyse is False
        assert rapport.abstentions
        assert rapport.gravite_maximale is None

    def test_texte_blanc_seul_est_traite_comme_vide(self):
        """Espaces et sauts de ligne ne sont pas du texte exploitable."""
        rapport = analyser('   \n\n\t  \n', montant=100.0,
                           date_facture='2026-05-12', aujourdhui=AUJOURDHUI)
        assert rapport.document_analyse is False
        assert rapport.risques == []

    def test_pdf_scanne_sans_couche_texte(self):
        """Un scan sans OCR renvoie une chaîne vide : on refuse, on n'invente pas.

        Le motif renvoyé doit orienter vers l'OCR, sinon l'utilisateur croit
        que sa facture est mauvaise alors que c'est la lecture qui a échoué.
        """
        rapport = analyser('', montant=None, date_facture=None,
                           aujourdhui=AUJOURDHUI)
        assert rapport.document_analyse is False
        motif = rapport.abstentions[0].motif_fr.lower()
        assert 'caractères' in motif or 'scanné' in motif

    def test_document_qui_nest_pas_une_facture_est_rejete(self):
        """Un contrat ne doit pas être analysé comme une facture."""
        contrat = ("CONTRAT DE BAIL COMMERCIAL\n"
                   "Entre les soussignés, il a été convenu ce qui suit.\n"
                   "Loyer mensuel : 1,200.000 DT")
        rapport = analyser(contrat, montant=1200.0, date_facture='2026-05-12',
                           aujourdhui=AUJOURDHUI)
        assert rapport.document_analyse is False
        assert rapport.risques == []
        assert rapport.motif_rejet_fr

    def test_mise_en_demeure_produite_par_mizan_est_rejetee(self):
        """Le moteur ne doit pas boucler sur son propre document de sortie."""
        acte = ("MISE EN DEMEURE\n"
                "Facture n° 2026-041 — Total : 9,520.000 DT\n"
                "Matricule fiscal : 1234567/A/M/000")
        rapport = analyser(acte, montant=9520.0, date_facture='2026-05-12',
                           aujourdhui=AUJOURDHUI)
        assert rapport.document_analyse is False

    def test_montant_negatif_ne_produit_pas_de_prescription(self):
        """Une créance négative n'existe pas : le moteur juridique la refuse.

        `legal_engine.assess` lève DateImpossible sur un montant non positif.
        Le moteur de risques doit convertir ce refus en abstention motivée, et
        surtout ne pas laisser passer un risque de prescription calculé sur
        une créance qui n'a pas de sens.
        """
        rapport = analyser(FACTURE_AHMED, montant=-500.0,
                           date_facture='2026-05-12', aujourdhui=AUJOURDHUI)
        identifiants = {r.identifiant for r in rapport.risques}
        assert 'prescription_acquise' not in identifiants
        assert 'prescription_proche' not in identifiants
        sujets = {a.sujet_fr for a in rapport.abstentions}
        assert 'Prescription' in sujets

    def test_montant_zero_ne_produit_pas_de_risque_de_seuil(self):
        """Zéro dinar n'ouvre aucun droit : pas de risque chiffré."""
        rapport = analyser(FACTURE_AHMED, montant=0.0,
                           date_facture='2026-05-12', aujourdhui=AUJOURDHUI)
        identifiants = {r.identifiant for r in rapport.risques}
        assert 'sommation_huissier_obligatoire' not in identifiants
        assert 'sommation_huissier_non_exigee' not in identifiants

    def test_date_future_est_refusee_avec_un_motif_lisible(self):
        """Une créance ne peut pas se prescrire avant d'exister.

        Le motif doit être compréhensible par un juriste, pas une trace
        technique : c'est lui qui s'affichera à l'écran.
        """
        rapport = analyser(FACTURE_AHMED, montant=9520.0,
                           date_facture='2027-12-31', aujourdhui=AUJOURDHUI)
        abstention = next(a for a in rapport.abstentions
                          if a.sujet_fr == 'Prescription')
        assert '31/12/2027' in abstention.motif_fr
        assert len(abstention.motif_fr) > 60

    def test_date_absente_abstient_au_lieu_de_supposer(self):
        """Sans date, le point de départ du délai est inconnu."""
        rapport = analyser(FACTURE_AHMED, montant=9520.0, date_facture=None,
                           aujourdhui=AUJOURDHUI)
        identifiants = {r.identifiant for r in rapport.risques}
        assert 'prescription_acquise' not in identifiants
        assert 'prescription_proche' not in identifiants
        abstention = next(a for a in rapport.abstentions
                          if a.sujet_fr == 'Prescription')
        assert 'date' in abstention.motif_fr.lower()

    def test_date_malformee_ne_leve_pas_dexception(self):
        """Une date illisible produit une abstention, pas une pile d'appels."""
        rapport = analyser(FACTURE_AHMED, montant=9520.0,
                           date_facture='pas-une-date', aujourdhui=AUJOURDHUI)
        assert isinstance(rapport, RapportRisques)
        assert any(a.sujet_fr == 'Prescription' for a in rapport.abstentions)

    def test_date_anterieure_au_coc_est_refusee(self):
        """1899 est une faute de saisie, pas une créance centenaire."""
        rapport = analyser(FACTURE_AHMED, montant=9520.0,
                           date_facture='1899-01-01', aujourdhui=AUJOURDHUI)
        assert any(a.sujet_fr == 'Prescription' for a in rapport.abstentions)

    def test_tva_a_zero_ne_declenche_pas_de_faux_ecart(self):
        """« TVA 0% » sur une facture exonérée est régulier, pas suspect."""
        exonere = FACTURE_AHMED.replace('TVA 19% 1,520.000', 'TVA 0% 0.000')
        exonere = exonere.replace('NET A PAYER 9,520.000',
                                  'NET A PAYER 8,000.000')
        rapport = analyser(exonere, montant=8000.0, date_facture='2026-05-12',
                           aujourdhui=AUJOURDHUI)
        assert not any(a.sujet_fr == 'Cohérence de la TVA'
                       for a in rapport.abstentions)

    def test_tva_incoherente_est_signalee_sans_etre_qualifiee(self):
        """L'écart est un constat de calcul ; aucun taux légal n'est dans le corpus.

        C'est le cœur de l'honnêteté du module : il voit l'anomalie, il la
        montre, et il refuse de dire quelle règle fiscale elle enfreint parce
        qu'il n'a pas le texte pour l'affirmer.
        """
        faux = FACTURE_AHMED.replace('TVA 19% 1,520.000', 'TVA 19% 400.000')
        rapport = analyser(faux, montant=9520.0, date_facture='2026-05-12',
                           aujourdhui=AUJOURDHUI)
        abstention = next(a for a in rapport.abstentions
                          if a.sujet_fr == 'Cohérence de la TVA')
        assert '1520' in abstention.motif_fr.replace('.', '').replace(' ', '')
        # Aucun risque fondé ne doit prétendre qualifier cet écart.
        assert not any('tva' in r.identifiant for r in rapport.risques)

    def test_caracteres_arabes_melanges_au_francais(self):
        """Une facture bilingue ne doit ni planter ni perdre ses risques."""
        bilingue = FACTURE_AHMED + (
            "\nالمعرف الجبائي : 1234567/A/M/000\n"
            "فاتورة عدد 2026-041\n"
            "المبلغ الجملي : 9,520.000 د.ت\n"
        )
        rapport = analyser(bilingue, montant=9520.0,
                           date_facture='2026-05-12', aujourdhui=AUJOURDHUI)
        assert isinstance(rapport, RapportRisques)
        assert rapport.document_analyse is True

    def test_montant_non_ancre_dans_le_document(self):
        """Un montant qu'aucune ligne ne porte ne fonde aucun risque chiffré.

        C'est la protection contre l'incident fondateur : 2 083,000 DT
        réclamés au titre d'une « facture » qui était le programme du
        hackathon. Ici le document est bien une facture, mais le montant
        transmis (99 999) ne figure sur aucune de ses lignes de total.
        """
        rapport = analyser(FACTURE_AHMED, montant=99999.0,
                           date_facture='2026-05-12', aujourdhui=AUJOURDHUI)
        abstention = next(a for a in rapport.abstentions
                          if a.sujet_fr == 'Ancrage du montant réclamé')
        assert '99 999' in abstention.motif_fr

    def test_montant_ancre_ne_declenche_pas_labstention(self):
        """Le contrôle d'ancrage ne doit pas crier au loup sur une facture saine."""
        rapport = analyser(FACTURE_AHMED, montant=9520.0,
                           date_facture='2026-05-12', aujourdhui=AUJOURDHUI)
        assert not any(a.sujet_fr == 'Ancrage du montant réclamé'
                       for a in rapport.abstentions)

    def test_aucune_entree_ne_leve_dexception(self):
        """Balayage : aucun de ces documents ne doit faire tomber le moteur."""
        hostiles = [
            ('', None, None),
            ('   ', 0.0, ''),
            ('facture', -1.0, '2026-05-12'),
            ('\x00\x01 facture total 10 DT MF', 10.0, '2026-05-12'),
            ('فاتورة المبلغ الجملي 500 د.ت المعرف الجبائي', 500.0, '2026-05-12'),
            (FACTURE_AHMED, 1e12, '2026-05-12'),
            (FACTURE_AHMED * 40, 9520.0, '2026-05-12'),
        ]
        for texte, montant, date_facture in hostiles:
            rapport = analyser(texte, montant=montant,
                               date_facture=date_facture or None,
                               aujourdhui=AUJOURDHUI)
            assert isinstance(rapport, RapportRisques)


# ===========================================================================
# ABSTENTION — le test qui justifie tout le reste.
# ===========================================================================
class TestAbstention:
    """L'abstention est une fonctionnalité : elle doit être testée comme telle."""

    def test_aucun_risque_sans_article_dans_le_corpus(self, monkeypatch):
        """Corpus vide : zéro risque produit, et des abstentions motivées.

        On vide le corpus sous les pieds du moteur. S'il continue à produire
        des risques, c'est qu'il cite des articles qu'il n'a pas ouverts —
        exactement la faute que ce module existe pour empêcher.
        """
        monkeypatch.setattr(ancrage, '_DOCUMENTS', [])
        rapport = analyser(_sans_mentions(), montant=9520.0,
                           date_facture='2026-05-12', aujourdhui=AUJOURDHUI)
        assert rapport.risques == [], (
            "des risques ont été produits alors que le corpus est vide : "
            "ils citent donc des articles inexistants"
        )
        assert rapport.abstentions
        assert rapport.gravite_maximale is None

    def test_abstention_nomme_le_sujet_non_verifie(self, monkeypatch):
        """Se taire ne suffit pas : il faut dire sur quoi on se tait."""
        monkeypatch.setattr(ancrage, '_DOCUMENTS', [])
        rapport = analyser(FACTURE_AHMED, montant=9520.0,
                           date_facture='2026-05-12', aujourdhui=AUJOURDHUI)
        sujets = {a.sujet_fr for a in rapport.abstentions}
        assert 'Prescription' in sujets
        assert 'Seuil de 150 dinars' in sujets

    def test_ancrer_refuse_un_article_inexistant(self):
        """Un numéro d'article absent du corpus renvoie None."""
        assert ancrage.ancrer('coc', 999999, 'نص لا وجود له') is None

    def test_ancrer_refuse_un_marqueur_absent_de_larticle(self):
        """L'article existe, mais il ne dit pas ce qu'on lui fait dire.

        C'est la seconde barrière : sans elle, on citerait le bon numéro
        d'article pour la mauvaise règle.
        """
        assert ancrage.ancrer('coc', 403, 'حكم لا يوجد في هذا الفصل') is None

    def test_ancrer_refuse_un_marqueur_vide(self):
        """Un marqueur vide matcherait tout : il doit être refusé."""
        assert ancrage.ancrer('coc', 403, '') is None


# ===========================================================================
# FONDEMENTS — chaque article cité existe réellement.
# ===========================================================================
class TestFondements:
    """Le catalogue ne doit contenir aucune référence morte."""

    @pytest.mark.parametrize('fondement', fondements.TOUS,
                             ids=[f.cle for f in fondements.TOUS])
    def test_chaque_fondement_est_dans_le_corpus(self, fondement):
        """Chaque article du catalogue est retrouvé, marqueur compris."""
        article = ancrage.ancrer(fondement.code_id, fondement.article,
                                 fondement.marqueur_ar)
        assert article is not None, (
            f"{fondement.cle} cite {fondement.code_id} art. "
            f"{fondement.article} : introuvable dans le corpus"
        )
        assert article.citation_ar
        assert fondement.marqueur_ar in article.extrait_ar

    def test_coc_403_vise_bien_le_prix_des_marchandises_livrees(self):
        """Le délai d'un an ne vaut pas pour n'importe quelle créance."""
        article = ancrage.ancrer('coc', 403, 'ثلاثمائة وخمسة وستين يوما')
        assert article is not None
        assert 'الباعة' in article.extrait_ar or 'البضائع' in article.extrait_ar

    def test_cpcc_60_porte_bien_le_seuil_de_150_dinars(self):
        """Le seuil cité doit être celui du texte, pas un chiffre de mémoire."""
        article = ancrage.ancrer('procciv', 60, 'مائة وخمسين دينارا')
        assert article is not None
        assert article.code_id == 'procciv'
        assert article.article == 60

    def test_coc_441_exige_une_facture_acceptee(self):
        """Le mot « acceptées » est ce qui fait tout le risque de preuve."""
        article = ancrage.ancrer('coc', 441, 'والفاتورات المقبولة')
        assert article is not None
        assert 'المقبولة' in article.extrait_ar

    def test_lidentifiant_fiscal_porte_une_reserve_de_qualification(self):
        """L'entrée fiscal/18 se réclame d'un autre code que son étiquette.

        On ne masque pas cette divergence : la citation reste utilisable mais
        le juriste doit savoir qu'elle est à vérifier avant d'aller au greffe.
        """
        article = ancrage.ancrer('fiscal', 18, 'معرّفهم الجبائي')
        assert article is not None
        assert article.reserve_fr is not None
        assert 'vérifier' in article.reserve_fr

    def test_le_numero_darticle_seul_ne_suffit_pas_a_designer_un_texte(self):
        """Le corpus porte huit entrées sous « fiscal, article 18 ».

        C'est la raison d'être du marqueur. Si ce test échoue un jour parce
        que le corpus a été dédoublonné, le marqueur reste utile mais son
        urgence tombe.
        """
        entrees = [d for d in ancrage.charger()
                   if d['code_id'] == 'fiscal' and d['article'] == 18]
        assert len(entrees) > 1

    def test_la_cle_article_est_un_entier(self):
        """Comparer 403 à « 403 » ne renverrait jamais rien."""
        for document in ancrage.charger()[:200]:
            assert isinstance(document['article'], int)

    def test_les_lacunes_sont_declarees(self):
        """Le module doit dire ce qu'il ne peut PAS vérifier."""
        sujets = {lacune.sujet_fr for lacune in fondements.LACUNES}
        assert any('date' in s.lower() for s in sujets)
        assert any('tva' in s.lower() for s in sujets)


# ===========================================================================
# CAS NOMINAL — la facture d'Ahmed, celle de la démonstration.
# ===========================================================================
class TestFactureAhmed:
    """9 520 DT, 12/05/2026, menuiserie. Le dossier montré au client."""

    @pytest.fixture
    def rapport(self) -> RapportRisques:
        return analyser(FACTURE_AHMED, montant=9520.0,
                        date_facture='2026-05-12', aujourdhui=AUJOURDHUI)

    def test_le_document_est_analyse(self, rapport):
        assert rapport.document_analyse is True

    def test_le_seuil_de_150_dinars_est_franchi(self, rapport):
        """9 520 DT impose la sommation par huissier."""
        risque = next(r for r in rapport.risques
                      if r.identifiant == 'sommation_huissier_obligatoire')
        assert risque.fondement.code_id == 'procciv'
        assert risque.fondement.article == 60
        assert '150' in risque.constatation_fr

    def test_le_montant_est_lisible_et_la_phrase_intacte(self, rapport):
        """Le séparateur de milliers ne doit pas manger la ponctuation.
        Un premier jet formatait « 9,520.000 » puis remplaçait toutes les
        virgules de la phrase : la constatation devenait « 9 520.000 DT
        supérieur au seuil », sans la virgule qui sépare les propositions.
        Le chiffre était juste et la phrase fautive — le genre de détail sur
        lequel un lecteur perd confiance dans tout le reste.
        """
        risque = next(r for r in rapport.risques
                      if r.identifiant == 'sommation_huissier_obligatoire')
        assert '9 520.000 DT' in risque.constatation_fr
        assert 'DT, supérieur' in risque.constatation_fr

    def test_la_facture_reguliere_ne_declenche_pas_les_mentions(self, rapport):
        """Numéro et matricule sont présents : aucun risque de mention."""
        identifiants = {r.identifiant for r in rapport.risques}
        assert 'numero_absent' not in identifiants
        assert 'identifiant_fiscal_absent' not in identifiants

    def test_la_livraison_mentionnee_ecarte_le_risque_de_preuve(self, rapport):
        """« Marchandise livrée et réceptionnée sans réserve » fait la preuve."""
        identifiants = {r.identifiant for r in rapport.risques}
        assert 'preuve_livraison_absente' not in identifiants

    def test_chaque_risque_porte_un_article_cite_en_arabe(self, rapport):
        """La règle du projet : pas de risque sans citation vérifiée."""
        assert rapport.risques
        for risque in rapport.risques:
            assert risque.fondement is not None
            assert risque.fondement.citation_ar.startswith('الفصل')
            assert risque.fondement.extrait_ar
            assert risque.constatation_fr
            assert risque.gravite in {'eleve', 'moyen', 'faible'}

    def test_les_risques_sont_tries_du_plus_grave_au_moins_grave(self, rapport):
        rangs = [{'eleve': 0, 'moyen': 1, 'faible': 2}[r.gravite]
                 for r in rapport.risques]
        assert rangs == sorted(rangs)

    def test_le_rapport_est_serialisable(self, rapport):
        """L'API devra le rendre en JSON sans traitement particulier."""
        import json
        donnees = rapport.to_dict()
        json.dumps(donnees, ensure_ascii=False)
        assert 'risques' in donnees and 'abstentions' in donnees


class TestFacturePrescrite:
    """Le cas où le créancier a trop attendu."""

    def test_prescription_acquise_est_le_risque_le_plus_grave(self):
        """Facture de 2024 pour un menuisier : le délai d'un an est passé."""
        vieille = FACTURE_AHMED.replace('Date : 12/05/2026', 'Date : 10/01/2024')
        rapport = analyser(vieille, montant=9520.0,
                           date_facture='2024-01-10', aujourdhui=AUJOURDHUI)
        risque = next(r for r in rapport.risques
                      if r.identifiant == 'prescription_acquise')
        assert risque.gravite == ELEVE
        assert risque.fondement.article == 403
        assert rapport.risques[0].gravite == ELEVE
        # Le conseil doit orienter vers l'interruption, seule porte de sortie.
        assert '396' in risque.consequence_fr

    def test_prescription_proche_est_signalee_avant_lecheance(self):
        """À 30 jours de l'échéance, l'alerte doit partir."""
        # Délai d'un an depuis le 01/10/2025 : échéance au 01/10/2026.
        rapport = analyser(FACTURE_AHMED, montant=9520.0,
                           date_facture='2025-10-01', aujourdhui=AUJOURDHUI)
        risque = next(r for r in rapport.risques
                      if r.identifiant == 'prescription_proche')
        assert risque.gravite == ELEVE
        assert '01/10/2026' in risque.constatation_fr

    def test_prescription_lointaine_ne_produit_aucun_risque(self):
        """Une facture récente ne doit pas alarmer inutilement."""
        rapport = analyser(FACTURE_AHMED, montant=9520.0,
                           date_facture='2026-09-01', aujourdhui=AUJOURDHUI)
        identifiants = {r.identifiant for r in rapport.risques}
        assert 'prescription_proche' not in identifiants
        assert 'prescription_acquise' not in identifiants


class TestFactureIrreguliere:
    """Une facture à laquelle il manque ce que le corpus impose."""

    @pytest.fixture
    def rapport(self) -> RapportRisques:
        texte = _sans_mentions().replace(
            'Marchandise livrée et réceptionnée sans réserve.', '')
        return analyser(texte, montant=9520.0, date_facture='2026-05-12',
                        aujourdhui=AUJOURDHUI)

    def test_numero_manquant_est_fonde_sur_le_corpus(self, rapport):
        risque = next(r for r in rapport.risques
                      if r.identifiant == 'numero_absent')
        assert risque.fondement.code_id == 'fiscal'
        assert 'غير مرقمة' in risque.fondement.extrait_ar

    def test_identifiant_fiscal_manquant_est_fonde(self, rapport):
        risque = next(r for r in rapport.risques
                      if r.identifiant == 'identifiant_fiscal_absent')
        assert risque.fondement.article == 18

    def test_absence_de_livraison_est_un_risque_eleve(self, rapport):
        """Sans preuve de réception, la facture ne prouve pas la créance."""
        risque = next(r for r in rapport.risques
                      if r.identifiant == 'preuve_livraison_absente')
        assert risque.gravite == ELEVE
        assert risque.fondement.article == 441
        # La charge de la preuve (COC 420) doit être citée dans le conseil.
        assert '420' in risque.consequence_fr

    def test_la_gravite_maximale_remonte_correctement(self, rapport):
        assert rapport.gravite_maximale == ELEVE
