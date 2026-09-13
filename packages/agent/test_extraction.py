"""Ce que le filet déterministe doit tenir, et ce qu'il doit refuser de tenir.

Ces tests sont écrits dans les deux sens, et le second compte autant que le
premier. Un extracteur qui trouve toujours quelque chose n'est pas fiable : il
est complaisant. On éprouve donc ici, à parts égales :

  — qu'il extrait ce qui est écrit sans ambiguïté (« 9520 DT du 12/05/2026 ») ;
  — qu'il NE POSE RIEN quand il n'est pas sûr (deux créances, une date
    impossible, un numéro d'article, une année seule) ;
  — qu'il n'écrase JAMAIS ce que le modèle a correctement rempli.

Aucun de ces tests ne touche au réseau ni au modèle : le filet est en Python
pur, et c'est précisément ce qui en fait un filet.
"""
from __future__ import annotations

from datetime import date

import pytest

from packages.agent import extraction
from packages.agent.extraction import (
    Extraction,
    completer,
    corriger_outil,
    extraire,
    lire_nombre,
    remettre_en_forme,
)

# Toutes les dates du dossier de démonstration sont lues par rapport à ce jour.
# On le fige : un test qui dépend de la date du jour passe en septembre et
# échoue en juin, et personne ne comprend pourquoi.
AUJOURDHUI = date(2026, 9, 13)


def lire(message: str) -> Extraction:
    return extraire(message, aujourdhui=AUJOURDHUI)


# ---------------------------------------------------------------------------
# Les trois messages réels, ceux qui ont motivé tout ce fichier
# ---------------------------------------------------------------------------

MESSAGE_QUI_MARCHAIT = (
    "Ma créance de 9520 DT du 12/05/2026 est-elle encore récupérable ? "
    "activité menuiserie"
)
MESSAGE_QUI_ECHOUAIT = (
    "Calcule la prescription : montant 9520, date de facture 2026-05-12, "
    "activité menuiserie"
)
MESSAGE_MAL_AIGUILLE = (
    "J'ai une facture impayée de 9520 dinars datée du 12 mai 2026, je suis "
    "menuisier. Qu'est-ce que je risque ?"
)


@pytest.mark.parametrize("message", [
    MESSAGE_QUI_MARCHAIT, MESSAGE_QUI_ECHOUAIT, MESSAGE_MAL_AIGUILLE,
])
def test_les_trois_messages_reels_donnent_la_meme_creance(message):
    """Trois formulations, une seule créance. C'est tout l'enjeu.

    Avant ce filet, le deuxième message renvoyait « il me manque le montant »
    alors qu'il le contenait. Les trois doivent maintenant produire exactement
    les mêmes chiffres, sinon la plateforme répond selon la façon de demander
    et non selon ce qui est demandé.
    """
    lu = lire(message)
    assert lu.montant == 9520.0
    assert lu.date_facture == "2026-05-12"
    assert lu.activite == "menuiserie"


def test_le_message_qui_echouait_remplit_desormais_les_parametres():
    """Le modèle rend l'outil sans aucun paramètre : le filet les pose."""
    params = completer(MESSAGE_QUI_ECHOUAIT, "analyser_impaye", {},
                       aujourdhui=AUJOURDHUI)
    assert params == {"montant": 9520.0, "date_facture": "2026-05-12",
                      "activite": "menuiserie"}


# ---------------------------------------------------------------------------
# Les montants : toutes les écritures d'une PME tunisienne
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message, attendu", [
    ("9520 DT", 9520.0),
    ("9520 dinars", 9520.0),
    ("9520 dinar", 9520.0),
    ("9 520,000 DT", 9520.0),
    ("9520,5 dinars", 9520.5),
    ("montant 9520", 9520.0),
    ("montant : 9520", 9520.0),
    ("montant de 9520 dinars", 9520.0),
    ("9520TND", 9520.0),
    ("9.520,000", None),          # sans unité ni annonce : rien ne dit que c'est un montant
    ("créance de 9.520,000 dinars", 9520.0),
    ("la somme de 1 250,500 DT", 1250.5),
    ("il me doit 4300 dinars", 4300.0),
    ("facture de 150 DT", 150.0),
    ("9520 د.ت", 9520.0),
])
def test_les_ecritures_de_montant(message, attendu):
    assert lire(message).montant == attendu


def test_les_decimales_sont_conservees():
    """Les millimes ne sont pas un détail : 0,500 DT, c'est un demi-dinar."""
    assert lire("créance de 9520,750 dinars").montant == 9520.75


# ---------------------------------------------------------------------------
# Les montants : ce qui n'en est pas
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message", [
    "que dit l'article 403 du COC ?",
    "COC 1458",
    "l'article 60 du CPCC",
    "art. 403",
    "الفصل 403",
])
def test_un_numero_darticle_nest_pas_un_montant(message):
    """Le faux ami le plus dangereux du projet.

    « article 403 » a la taille d'une créance, revient dans presque toutes les
    questions juridiques, et le prendre pour un montant produirait un calcul de
    prescription sur un numéro d'article — avec la même assurance qu'un vrai.
    """
    assert lire(message).montant is None


@pytest.mark.parametrize("message", [
    "facture de 2026",
    "en 2026",
    "l'année 2025",
])
def test_une_annee_seule_nest_pas_un_montant(message):
    assert lire(message).montant is None


def test_une_annee_avec_son_unite_est_bien_un_montant():
    """« 2026 dinars » est une créance de 2026 dinars. L'unité lève le doute."""
    assert lire("créance de 2026 dinars").montant == 2026.0


@pytest.mark.parametrize("message", [
    "une créance de -50 dinars",
    "montant -9520",
    "créance de 0 dinars",
    "montant 0",
])
def test_un_montant_nul_ou_negatif_nest_pas_pose(message):
    """On ne pose rien, et l'agent demandera.

    Le moteur refuserait de toute façon, mais au nom du droit (« une créance
    nulle n'ouvre aucun droit »). Opposer une règle de droit à quelqu'un qui a
    tapé un moins par erreur, c'est répondre à côté.
    """
    assert lire(message).montant is None


def test_un_montant_aberrant_est_ecarte():
    assert lire("créance de 99999999999999 dinars").montant is None


@pytest.mark.parametrize("message", [
    "mon numéro de téléphone est 71 123 456",
    "facture n° 2024/0912",
    "une pénalité de 5%",
])
def test_les_nombres_qui_ne_sont_pas_de_largent(message):
    assert lire(message).montant is None


def test_un_montant_en_toutes_lettres_est_hors_perimetre():
    """« neuf mille dinars » n'est pas traité, et c'est assumé.

    Écrire un lecteur de nombres en toutes lettres français (avec « quatre-
    vingt-dix », « mille » sans « un », les accords) est un chantier à part
    entière pour un gain proche de zéro : aucune facture tunisienne ne porte
    son montant en lettres seules. Le comportement attendu est donc
    l'abstention — l'agent demandera le chiffre.
    """
    assert lire("je réclame neuf mille dinars").montant is None


# ---------------------------------------------------------------------------
# Les montants multiples : LA règle, et sa démonstration
# ---------------------------------------------------------------------------

def test_deux_montants_dont_lun_est_la_tva():
    """« 9520 dinars dont 1520 de TVA » → 9520.

    RÈGLE : un nombre annoncé comme une composante de la créance — TVA, frais,
    acompte, remise, pénalités — est écarté. Il est DANS la somme, il n'est pas
    la somme. C'est la seule situation où plusieurs nombres coexistent sans
    ambiguïté réelle, et c'est la plus fréquente sur une facture.
    """
    lu = lire("ma facture de 9520 dinars dont 1520 de TVA, du 12/05/2026")
    assert lu.montant == 9520.0
    assert lu.date_facture == "2026-05-12"


@pytest.mark.parametrize("message, attendu", [
    ("facture de 9520 dinars, dont 300 de frais et 1520 de TVA", 9520.0),
    ("montant 9520, dont acompte 2000", 9520.0),
    ("créance de 9520 DT y compris 1520 de taxe", 9520.0),
    ("9520 dinars avec 320 dinars de pénalités", 9520.0),
])
def test_les_composantes_sont_ecartees(message, attendu):
    assert lire(message).montant == attendu


def test_deux_creances_concurrentes_ne_donnent_aucun_montant():
    """RÈGLE, second volet : deux vraies créances → on ne choisit pas.

    Ni la plus grande, ni la première, ni la dernière : RIEN. Choisir
    reviendrait à décider à la place du créancier de ce qu'il réclame, et
    l'erreur ne serait visible nulle part à l'écran — le chiffre affiché aurait
    exactement l'air d'un chiffre juste. Une question de plus coûte dix
    secondes ; un mauvais montant coûte un procès.
    """
    lu = lire("j'ai une facture de 9520 dinars et une autre de 3000 dinars")
    assert lu.montant is None
    assert any("concurrent" in t for t in lu.traces)


def test_le_meme_montant_repete_reste_extractible():
    """« 9520 dinars… ces 9520 DT » : une seule créance, écrite deux fois."""
    assert lire("ma créance de 9520 dinars ; ces 9520 DT sont dus depuis mai").montant == 9520.0


# ---------------------------------------------------------------------------
# Les dates : l'ordre tunisien, et rien d'autre
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message, attendu", [
    ("facture du 12/05/2026", "2026-05-12"),
    ("facture du 2026-05-12", "2026-05-12"),
    ("facture du 12 mai 2026", "2026-05-12"),
    ("facture du 12-05-2026", "2026-05-12"),
    ("facture du 12.05.2026", "2026-05-12"),
    ("facture du 1er mai 2026", "2026-05-01"),
    ("facture du 3 août 2026", "2026-08-03"),
    ("facture du 31 décembre 2025", "2025-12-31"),
    ("facture du 09/02/2026", "2026-02-09"),
])
def test_les_ecritures_de_date(message, attendu):
    assert lire(message).date_facture == attendu


def test_le_jour_vient_toujours_avant_le_mois():
    """« 05/12/2026 » est le 5 décembre, jamais le 12 mai.

    C'est la convention tunisienne, et l'enjeu n'est pas cosmétique : lue à
    l'américaine, cette date décale l'échéance de prescription de sept mois.
    Rien à l'écran ne signalerait l'erreur — le calcul serait parfaitement
    exact sur une date parfaitement fausse.
    """
    assert lire("facture du 05/12/2026").date_facture == "2026-12-05"
    assert lire("facture du 12/05/2026").date_facture == "2026-05-12"


@pytest.mark.parametrize("message", [
    "facture du 30/02/2026",
    "facture du 31/11/2026",
    "facture du 31 février 2026",
    "facture du 2026-02-30",
    "facture du 32/01/2026",
])
def test_une_date_impossible_ne_pose_rien_et_ne_plante_pas(message):
    """Le 30 février est syntaxiquement irréprochable et n'existe pas."""
    lu = lire(message)
    assert lu.date_facture is None
    assert any("calendrier" in t for t in lu.traces)


def test_une_date_a_lamericaine_impossible_reste_une_abstention():
    """« 13/25/2026 » : ni jour/mois ni mois/jour. On ne pose rien."""
    assert lire("facture du 13/25/2026").date_facture is None


@pytest.mark.parametrize("message", [
    "facture du 12/05/1850",
    "facture du 12 mai 1850",
    "facture du 12/05/2190",
])
def test_une_date_aberrante_est_ecartee(message):
    """1850 ou 2190 : une faute de frappe, pas une créance.

    La poser produirait un calcul de prescription impeccable sur une donnée
    fausse — et sur 1850, une créance « prescrite depuis un siècle » affichée
    avec le plus grand sérieux.
    """
    lu = lire(message)
    assert lu.date_facture is None
    assert any("plausibles" in t for t in lu.traces)


def test_une_date_sans_annee_ne_pose_rien():
    """« le 12 mai » : reconnu pour ne pas être pris pour un nombre, jamais posé.

    Deviner l'année, c'est choisir pour l'utilisateur entre une créance vivante
    et une créance prescrite. Sur une prescription d'un an, se tromper d'année
    retourne complètement la réponse.
    """
    lu = lire("ma facture du 12 mai, 9520 dinars")
    assert lu.date_facture is None
    assert lu.montant == 9520.0          # le montant, lui, reste extractible
    assert any("année" in t for t in lu.traces)


def test_une_annee_a_deux_chiffres_ne_pose_rien():
    """« 12/05/26 » se lit 1926 aussi bien que 2026."""
    lu = lire("facture du 12/05/26")
    assert lu.date_facture is None


def test_les_chiffres_dune_date_ne_sont_pas_pris_pour_un_montant():
    """« 12/05/2026 » contient 2026, qui a la taille d'une créance."""
    lu = lire("ma facture du 12/05/2026")
    assert lu.montant is None
    assert lu.date_facture == "2026-05-12"


def test_deux_dates_dont_une_seule_est_celle_de_la_facture():
    lu = lire("relance envoyée le 01/09/2026, facture du 12/05/2026")
    assert lu.date_facture == "2026-05-12"


def test_deux_dates_indiscernables_ne_posent_rien():
    lu = lire("entre le 01/09/2026 et le 12/05/2026")
    assert lu.date_facture is None
    assert any("concurrentes" in t for t in lu.traces)


def test_la_meme_date_ecrite_deux_fois_reste_extractible():
    assert lire("facture du 12/05/2026, soit le 12 mai 2026").date_facture == "2026-05-12"


# ---------------------------------------------------------------------------
# L'activité : du vocabulaire, jamais du droit
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message, attendu", [
    ("activité menuiserie", "menuiserie"),
    ("je suis menuisier", "menuiserie"),
    ("menuisier à Sfax", "menuiserie"),
    ("je fais de l'ébénisterie", "ebenisterie"),
    ("je suis ébéniste", "ebenisterie"),
    ("je suis plombier", "plomberie"),
    ("mon activité est la plomberie", "plomberie"),
    ("je suis boulanger", "boulangerie"),
    ("atelier de confection", "confection"),
    ("je suis transporteur", "transport"),
    ("société de nettoyage", "nettoyage"),
    ("je suis imprimeur", "imprimerie"),
    ("je suis artisan", "artisanat"),
    ("activité textile", "textile"),
    ("je suis agriculteur", "agriculture"),
])
def test_le_vocabulaire_des_activites(message, attendu):
    assert lire(message).activite == attendu


def test_les_activites_reconnues_sont_celles_du_moteur():
    """On ne recopie pas la liste du moteur, on la lit.

    Une liste recopiée diverge le jour où quelqu'un ajoute une activité au
    moteur sans savoir que ce fichier existe. Ce test vérifie qu'on lit bien la
    vraie, et qu'elle n'est pas vide.
    """
    from packages.legal.legal_engine import KNOWN_ACTIVITIES

    assert extraction.ACTIVITES_DU_MOTEUR == frozenset(KNOWN_ACTIVITIES)
    assert "menuiserie" in extraction.ACTIVITES_DU_MOTEUR
    assert len(extraction.ACTIVITES_DU_MOTEUR) > 10


def test_une_activite_inconnue_du_moteur_est_transmise_avec_sa_reserve():
    """« plomberie » n'est pas qualifiée par le moteur, et c'est très bien.

    Ne PAS la transmettre laisserait s'appliquer l'activité par défaut de
    l'outil — la menuiserie — et annoncerait à un plombier une prescription
    d'un an qu'aucun texte ne fonde. La transmettre fait dire au moteur
    lui-même que le régime n'est pas confirmé. Un doute affiché vaut mieux
    qu'une certitude fausse.
    """
    lu = lire("je suis plombier, facture de 9520 DT du 12/05/2026")
    assert lu.activite == "plomberie"
    assert lu.activite not in extraction.ACTIVITES_DU_MOTEUR
    assert any("n'est pas qualifiée" in t for t in lu.traces)


def test_deux_activites_nommees_ne_posent_rien():
    """Le régime de prescription en dépend trop directement pour être deviné."""
    lu = lire("je fais de la menuiserie et du transport")
    assert lu.activite is None
    assert any("Plusieurs activités" in t for t in lu.traces)


@pytest.mark.parametrize("message", [
    "je vous demande conseil sur ma créance",
    "la formation du contrat pose problème",
    "quel est le délai de prescription ?",
])
def test_les_mots_de_la_langue_courante_ne_sont_pas_des_activites(message):
    """« conseil » et « formation » sont des activités ET des mots ordinaires.

    Les reconnaître au milieu d'une phrase ferait basculer le régime de
    prescription sur un mot que l'utilisateur n'a jamais employé comme métier.
    """
    assert lire(message).activite is None


def test_la_variante_la_plus_longue_lemporte():
    assert lire("je fais de la menuiserie aluminium").activite == "menuiserie_alu"


# ---------------------------------------------------------------------------
# Le message qui ne contient rien : le comportement d'avant, conservé
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message", [
    "",
    "   ",
    "bonjour",
    "est-ce que ma créance est encore récupérable ?",
    "que dois-je faire ?",
])
def test_un_message_sans_rien_dextractible_ne_pose_rien(message):
    lu = lire(message)
    assert lu.montant is None
    assert lu.date_facture is None
    assert lu.activite is None
    assert not lu


def test_les_parametres_restent_vides_et_lagent_redemandera():
    """Sans rien d'extractible, `completer` rend exactement ce qu'on lui donne."""
    assert completer("bonjour", "analyser_impaye", {}, aujourdhui=AUJOURDHUI) == {}


def test_le_filet_ne_leve_jamais():
    """Un filet qui tombe n'est pas un filet.

    Il est appelé sur le chemin nominal : s'il levait sur une phrase biscornue,
    il transformerait une réponse imparfaite en panne du service.
    """
    for tordu in ("///", "9520////2026", "\x00\x01", "€" * 300, "12/05/", "--", None,
                  "0" * 400, "e" * 5000, "1/1/1/1/1/1"):
        assert isinstance(extraire(tordu, aujourdhui=AUJOURDHUI), Extraction)


# ---------------------------------------------------------------------------
# LA règle absolue : ne jamais écraser ce que le modèle a rempli
# ---------------------------------------------------------------------------

def test_le_filet_nécrase_pas_un_montant_deja_rempli():
    """Le modèle a dit 7000, le texte dit 9520 : on garde 7000.

    Contre-intuitif, et pourtant non négociable. Le modèle a pu lire un
    échange plus riche que la seule dernière phrase. Si l'on se met à corriger
    ses valeurs, ce filet cesse d'être un filet pour devenir un deuxième avis —
    et deux avis qui se contredisent en silence, c'est pire qu'un seul.
    """
    params = completer("ma créance de 9520 dinars", "analyser_impaye",
                       {"montant": 7000}, aujourdhui=AUJOURDHUI)
    assert params["montant"] == 7000


def test_le_filet_nécrase_pas_une_date_deja_remplie():
    params = completer("facture du 12/05/2026", "analyser_impaye",
                       {"date_facture": "2025-01-04"}, aujourdhui=AUJOURDHUI)
    assert params["date_facture"] == "2025-01-04"


def test_le_filet_nécrase_pas_une_activite_deja_remplie():
    params = completer("je suis menuisier", "analyser_impaye",
                       {"activite": "transport"}, aujourdhui=AUJOURDHUI)
    assert params["activite"] == "transport"


def test_le_filet_ne_complete_que_ce_qui_manque():
    """Un paramètre rempli, deux oubliés : on ne pose que les deux."""
    params = completer(MESSAGE_QUI_MARCHAIT, "analyser_impaye",
                       {"montant": 7000}, aujourdhui=AUJOURDHUI)
    assert params == {"montant": 7000, "date_facture": "2026-05-12",
                      "activite": "menuiserie"}


def test_un_zero_explicite_du_modele_nest_pas_remplace():
    """0 est renseigné, donc intouchable.

    L'outil le refusera avec un message clair, et ce refus lui appartient. Le
    remplacer en douce par une valeur lue dans le texte serait exactement
    l'écrasement qu'on s'interdit.
    """
    params = completer("ma créance de 9520 dinars", "analyser_impaye",
                       {"montant": 0}, aujourdhui=AUJOURDHUI)
    assert params["montant"] == 0


def test_completer_ne_modifie_pas_le_dictionnaire_recu():
    """Aucune modification par surprise chez l'appelant."""
    origine = {"montant": 7000}
    completer(MESSAGE_QUI_MARCHAIT, "analyser_impaye", origine, aujourdhui=AUJOURDHUI)
    assert origine == {"montant": 7000}


def test_completer_accepte_de_ne_rien_recevoir():
    assert completer(MESSAGE_QUI_MARCHAIT, "analyser_impaye", None,
                     aujourdhui=AUJOURDHUI)["montant"] == 9520.0


# ---------------------------------------------------------------------------
# Le filet ne pose que sur les outils qui déclarent le paramètre
# ---------------------------------------------------------------------------

def test_le_filet_ne_pose_rien_sur_un_outil_inconnu():
    assert completer(MESSAGE_QUI_MARCHAIT, "outil_invente", {},
                     aujourdhui=AUJOURDHUI) == {}


def test_le_filet_ne_pose_rien_sur_un_outil_sans_ces_parametres():
    """`consulter_mes_dossiers` ne déclare ni montant ni date."""
    assert completer(MESSAGE_QUI_MARCHAIT, "consulter_mes_dossiers", {},
                     aujourdhui=AUJOURDHUI) == {}


def test_le_filet_ne_pose_pas_dactivite_sur_un_outil_qui_ne_la_declare_pas():
    """`analyser_risques_facture` déclare montant et date, pas activité.

    On interroge le catalogue au lieu de tenir une table en double : poser un
    paramètre non déclaré le ferait écarter plus loin, et on aurait cru
    compléter quelque chose.
    """
    params = completer(MESSAGE_MAL_AIGUILLE, "analyser_risques_facture",
                       {"chemin": "/tmp/f.pdf"}, aujourdhui=AUJOURDHUI)
    assert "activite" not in params
    assert params["montant"] == 9520.0


def test_le_filet_complete_la_mise_en_demeure_sans_inventer_le_debiteur():
    """Le nom du débiteur ne s'extrait pas, et ne doit surtout pas s'inventer."""
    params = completer(
        "prépare une mise en demeure pour ma facture de 9520 DT du 12/05/2026",
        "preparer_mise_en_demeure", {}, aujourdhui=AUJOURDHUI,
    )
    assert params["montant"] == 9520.0
    assert params["date_facture"] == "2026-05-12"
    assert "debiteur" not in params


# ---------------------------------------------------------------------------
# La remise en forme : rendre lisible, pas remplacer
# ---------------------------------------------------------------------------

def test_un_montant_recopie_avec_son_unite_est_remis_en_forme():
    """Le modèle rend « 9 520,000 DT ». Il a bien lu ; il n'a pas converti.

    Ce n'est PAS un écrasement : l'outil allait refuser cette valeur. Rejeter
    la réponse d'un modèle qui a tout compris, pour un espace insécable, serait
    un comble.
    """
    params = completer("peu importe", "analyser_impaye",
                       {"montant": "9 520,000 DT"}, aujourdhui=AUJOURDHUI)
    assert params["montant"] == 9520.0


def test_une_date_rendue_a_la_francaise_est_remise_en_forme():
    params = completer("peu importe", "analyser_impaye",
                       {"date_facture": "12/05/2026"}, aujourdhui=AUJOURDHUI)
    assert params["date_facture"] == "2026-05-12"


def test_une_date_en_toutes_lettres_du_modele_est_remise_en_forme():
    params = completer("peu importe", "analyser_impaye",
                       {"date_facture": "12 mai 2026"}, aujourdhui=AUJOURDHUI)
    assert params["date_facture"] == "2026-05-12"


def test_une_valeur_deja_lisible_nest_pas_touchee():
    assert remettre_en_forme("montant", 9520.0) == 9520.0
    assert remettre_en_forme("date_facture", "2026-05-12") == "2026-05-12"


def test_une_valeur_illisible_est_laissee_telle_quelle():
    """Le message d'erreur de l'outil est meilleur que le nôtre : on le laisse."""
    assert remettre_en_forme("montant", "beaucoup") == "beaucoup"
    assert remettre_en_forme("date_facture", "la semaine derniere") == "la semaine derniere"


def test_un_champ_hors_perimetre_nest_jamais_touche():
    assert remettre_en_forme("debiteur", "Société X") == "Société X"


# ---------------------------------------------------------------------------
# Le mauvais aiguillage : l'analyse de risques réclamée sans document
# ---------------------------------------------------------------------------

def test_une_analyse_de_risques_sans_document_devient_une_analyse_dimpaye():
    """« Qu'est-ce que je risque ? » sur une créance décrite, pas sur un PDF.

    Mesuré sur le vrai modèle : le mot « risque » l'emportait, l'agent
    réclamait un document que l'utilisateur n'avait jamais eu l'intention de
    déposer, alors que la somme, la date et le métier étaient dans la phrase.
    """
    assert corriger_outil(MESSAGE_MAL_AIGUILLE, "analyser_risques_facture", {},
                          aujourdhui=AUJOURDHUI) == "analyser_impaye"


def test_un_document_fourni_reste_une_analyse_de_risques():
    """La correction ne va que dans un sens. Un PDF déposé s'analyse."""
    assert corriger_outil(MESSAGE_MAL_AIGUILLE, "analyser_risques_facture",
                          {"chemin": "/tmp/facture.pdf"},
                          aujourdhui=AUJOURDHUI) == "analyser_risques_facture"
    assert corriger_outil(MESSAGE_MAL_AIGUILLE, "analyser_risques_facture",
                          {"texte": "FACTURE N°12"},
                          aujourdhui=AUJOURDHUI) == "analyser_risques_facture"


def test_sans_creance_complete_lanalyse_de_risques_reste_elle_meme():
    """Rien à calculer : on laisse l'outil réclamer son document."""
    assert corriger_outil("analyse les risques de ma facture",
                          "analyser_risques_facture", {},
                          aujourdhui=AUJOURDHUI) == "analyser_risques_facture"


def test_les_autres_outils_ne_sont_jamais_reaiguilles():
    for nom in ("analyser_impaye", "chercher_article", "preparer_mise_en_demeure",
                "ouvrir_conciliation", "consulter_mes_dossiers"):
        assert corriger_outil(MESSAGE_MAL_AIGUILLE, nom, {},
                              aujourdhui=AUJOURDHUI) == nom


# ---------------------------------------------------------------------------
# La lecture des nombres, isolément
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("brut, attendu", [
    ("9520", 9520.0),
    ("9 520,000", 9520.0),
    ("9\u00a0520,000", 9520.0),
    ("9.520,000", 9520.0),
    ("9,520.00", 9520.0),
    ("9520,5", 9520.5),
    ("9520.5", 9520.5),
    ("0", 0.0),
    ("", None),
    ("abc", None),
    (None, None),
])
def test_lire_nombre(brut, attendu):
    assert lire_nombre(brut) == attendu


def test_le_point_a_trois_decimales_se_lit_en_millimes():
    """« 9.520 » : neuf dinars cinq cent vingt millimes, pas neuf mille.

    Choix arbitraire, documenté, et surtout UNIFORME : c'est l'écriture des
    factures tunisiennes (trois décimales) et déjà la convention d'affichage de
    la plateforme. Ce qui compte n'est pas d'avoir raison dans l'absolu, c'est
    de faire toujours pareil.
    """
    assert lire_nombre("9.520") == 9.52


# ---------------------------------------------------------------------------
# Bout en bout : le filet dans l'agent, sans modèle
# ---------------------------------------------------------------------------

def _identite_pme():
    """Une PME réellement habilitée, avec les permissions de son rôle.

    On lit la matrice des rôles au lieu d'écrire une liste : une identité sans
    permission se heurterait au contrôle de droits avant d'atteindre le filet,
    et le test passerait à côté de ce qu'il prétend vérifier.
    """
    from packages.agent.identite import Identite
    from packages.comptes.roles import PERMISSIONS

    return Identite(
        organisation="org-ahmed",
        role="msme",
        permissions=tuple(PERMISSIONS["msme"]),
        nom_organisation="Menuiserie Ahmed",
        email="ahmed@exemple.tn",
        compte_id="cpt-ahmed",
    )


def test_lagent_calcule_desormais_sur_le_message_qui_echouait():
    """Le bout du bout : un modèle qui rend l'outil sans paramètres.

    On simule exactement le défaut mesuré — bon outil, paramètres vides — et on
    vérifie que l'agent produit le calcul au lieu de redemander le montant.
    """
    from packages.agent.cerveau import Agent

    class ModeleQuiOublieTout:
        """Le vrai défaut, reproduit à l'identique et sans réseau."""

        def generer(self, invite, *, systeme=None, max_tokens=512, temperature=0.3):
            class R:
                texte = '{"outil": "analyser_impaye", "parametres": {}}'
                modele = "test"

            if "JSON" in (systeme or ""):
                return R()
            raise RuntimeError("reformulation indisponible dans ce test")

    agent = Agent(_identite_pme(), client=ModeleQuiOublieTout())
    reponse = agent.repondre(MESSAGE_QUI_ECHOUAIT)

    assert reponse.outil_appele == "analyser_impaye"
    assert not reponse.abstention
    assert "manque" not in reponse.texte.lower()
    assert reponse.resultat["amount_tnd"] == 9520.0
    assert reponse.resultat["invoice_date"] == "2026-05-12"
    assert reponse.resultat["regime"] == "goods_1y"


def test_lagent_redemande_toujours_quand_le_message_ne_dit_rien():
    """Le comportement d'avant est conservé là où il était le bon."""
    from packages.agent.cerveau import Agent

    class ModeleQuiOublieTout:
        def generer(self, invite, *, systeme=None, max_tokens=512, temperature=0.3):
            class R:
                texte = '{"outil": "analyser_impaye", "parametres": {}}'
                modele = "test"

            return R()

    agent = Agent(_identite_pme(), client=ModeleQuiOublieTout())
    reponse = agent.repondre("est-ce que ma créance est encore récupérable ?")

    assert reponse.abstention
    assert "manque" in reponse.texte.lower()
