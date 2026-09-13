"""
Tests de la place de marché : notation vérifiée, conflit d'intérêts, abstention.

L'ordre de ce fichier est volontaire. On teste d'abord ce qui doit ÉCHOUER —
notes hors bornes, notes sans dossier clôturé, professionnel en conflit
d'intérêts, annuaire vide — parce que ce sont ces refus qu'un juriste du jury
viendra vérifier. Le cas nominal vient ensuite.

    ./.venv/bin/python -m pytest packages/marketplace/ -q
"""

from __future__ import annotations

import pytest

from packages.marketplace.annuaire import (
    Annuaire,
    Dossier,
    Litige,
    NotationRefusee,
    ProfilInvalide,
    Professionnel,
)
from packages.marketplace.exemples import annuaire_demo, litige_ahmed


# --------------------------------------------------------------------------
# Profils : ce qui n'entre pas à l'annuaire
# --------------------------------------------------------------------------


def test_professionnel_sans_accreditation_est_refuse() -> None:
    """Un praticien sans numéro d'ordre ne peut pas être mis en relation."""
    with pytest.raises(ProfilInvalide) as erreur:
        Professionnel.creer(
            identifiant="pro-x",
            nom="Me Untel",
            qualite="avocat",
            numero_accreditation="   ",
            expertises=["commercial"],
            langues=["francais"],
            gouvernorat="Tunis",
        )
    assert "accréditation" in str(erreur.value)


def test_qualite_inconnue_est_refusee() -> None:
    """« huissier » n'est pas une qualité opératrice du règlement amiable."""
    with pytest.raises(ProfilInvalide, match="Qualité inconnue"):
        Professionnel.creer(
            identifiant="pro-y",
            nom="Untel",
            qualite="huissier",
            numero_accreditation="X-1",
            expertises=["commercial"],
            langues=["francais"],
            gouvernorat="Tunis",
        )


def test_gouvernorat_inexistant_est_refuse() -> None:
    """Marseille n'est pas un gouvernorat tunisien."""
    with pytest.raises(ProfilInvalide, match="Ressort géographique inconnu"):
        Professionnel.creer(
            identifiant="pro-z",
            nom="Untel",
            qualite="avocat",
            numero_accreditation="X-2",
            expertises=["commercial"],
            langues=["francais"],
            gouvernorat="Marseille",
        )


def test_nom_en_arabe_est_accepte_et_preserve() -> None:
    """La normalisation ne doit pas mutiler un nom écrit en caractères arabes."""
    pro = Professionnel.creer(
        identifiant="pro-ar",
        nom="محمد الطرابلسي",
        qualite="conciliateur",
        numero_accreditation="ACC-AR-1 (fictif)",
        expertises=["conciliation"],
        langues=["arabe"],
        gouvernorat="Nabeul",
    )
    assert pro.nom == "محمد الطرابلسي"
    assert pro.gouvernorat == "nabeul"


def test_gouvernorat_accentue_est_normalise() -> None:
    """« Béja » et « beja » désignent le même ressort."""
    pro = Professionnel.creer(
        identifiant="pro-b",
        nom="Untel",
        qualite="avocat",
        numero_accreditation="X-3",
        expertises=["commercial"],
        langues=["francais"],
        gouvernorat="Béja",
    )
    assert pro.gouvernorat == "beja"


# --------------------------------------------------------------------------
# Notation : une note sans dossier clôturé est une note qui ment
# --------------------------------------------------------------------------


@pytest.fixture()
def annuaire() -> Annuaire:
    """Annuaire de démonstration, profils et notes vérifiées inclus."""
    return annuaire_demo()


@pytest.mark.parametrize("etoiles", [0, 6, -1, 42])
def test_note_hors_bornes_est_refusee(annuaire: Annuaire, etoiles: int) -> None:
    """Seules les notes de 1 à 5 étoiles existent."""
    with pytest.raises(NotationRefusee, match="hors de la fourchette"):
        annuaire.noter("pro-001", "ste-medina", "dos-101", etoiles)


def test_note_sur_dossier_non_cloture_est_refusee(annuaire: Annuaire) -> None:
    """
    Le point central du module : tant que la résolution n'est pas terminée,
    la note est refusée. C'est ce refus qui rend la notation crédible.
    """
    with pytest.raises(NotationRefusee) as erreur:
        annuaire.noter("pro-003", "ste-aurore", "dos-110", 5)
    message = str(erreur.value)
    assert "n'est pas clôturé" in message
    assert "dos-110" in message

    # Et la note n'a évidemment pas été comptabilisée.
    moyenne, nombre = annuaire.note_moyenne("pro-003")
    assert (moyenne, nombre) == (3.0, 1)


def test_note_sur_dossier_inexistant_est_refusee(annuaire: Annuaire) -> None:
    """Une note achetée, sans dossier derrière, n'entre pas."""
    with pytest.raises(NotationRefusee, match="une note qui ment"):
        annuaire.noter("pro-001", "client-fantome", "dos-999", 5)


def test_note_par_un_tiers_non_partie_est_refusee(annuaire: Annuaire) -> None:
    """Seules les parties au dossier peuvent noter."""
    with pytest.raises(NotationRefusee, match="n'était pas partie"):
        annuaire.noter("pro-001", "concurrent-jaloux", "dos-101", 1)


def test_note_visant_un_autre_professionnel_est_refusee(annuaire: Annuaire) -> None:
    """On ne note pas un praticien qui n'a pas conduit le dossier."""
    with pytest.raises(NotationRefusee, match="n'a pas été conduit"):
        annuaire.noter("pro-004", "ste-medina", "dos-101", 5)


def test_double_note_sur_le_meme_dossier_est_refusee(annuaire: Annuaire) -> None:
    """Une partie ne peut pas gonfler une moyenne en notant deux fois."""
    with pytest.raises(NotationRefusee, match="a déjà noté"):
        annuaire.noter("pro-001", "ste-medina", "dos-101", 5)


def test_note_devient_possible_apres_cloture() -> None:
    """La clôture du dossier ouvre le droit de noter, et pas avant."""
    annuaire = annuaire_demo()
    with pytest.raises(NotationRefusee):
        annuaire.noter("pro-003", "ste-aurore", "dos-110", 4)
    annuaire.cloturer("dos-110")
    avis = annuaire.noter("pro-003", "ste-aurore", "dos-110", 4)
    assert avis.etoiles == 4
    assert annuaire.note_moyenne("pro-003") == (3.5, 2)


def test_professionnel_sans_avis_na_pas_de_note(annuaire: Annuaire) -> None:
    """Pas encore noté n'est pas la même chose que mal noté."""
    assert annuaire.note_moyenne("pro-007") == (None, 0)


# --------------------------------------------------------------------------
# Conflit d'intérêts : le point que le jury vérifiera
# --------------------------------------------------------------------------


def test_conflit_interets_detecte(annuaire: Annuaire) -> None:
    """pro-002 a travaillé pour la société Zitouna dans le dossier dos-109."""
    conflit = annuaire.conflit_interets("pro-002", "ste-zitouna")
    assert conflit is not None
    assert conflit.dossier == "dos-109"


def test_professionnel_en_conflit_nest_jamais_recommande(annuaire: Annuaire) -> None:
    """
    Karim Trabelsi coche tout — Sfax, conciliateur, recouvrement, bien noté —
    et doit pourtant être écarté, parce qu'il est déjà intervenu pour la partie
    adverse d'Ahmed.
    """
    recommandation = annuaire.recommander(litige_ahmed(), limite=5)
    identifiants = [p.professionnel.identifiant for p in recommandation.propositions]
    assert "pro-002" not in identifiants
    assert any(
        "déjà intervenu pour la partie adverse" in motif and "Karim Trabelsi" in motif
        for motif in recommandation.ecartes
    )


def test_sans_conflit_le_meme_professionnel_est_recommande() -> None:
    """
    Contre-épreuve : face à une autre partie adverse, Karim Trabelsi revient
    dans la liste. L'exclusion tient au conflit, pas au profil.
    """
    annuaire = annuaire_demo()
    litige = Litige.creer(
        nature=["recouvrement", "commercial"],
        montant_dt=9520.0,
        gouvernorat="Sfax",
        langue="francais",
        voie="conciliation",
        demandeur="menuiserie-ahmed",
        partie_adverse="ste-inconnue-au-bataillon",
    )
    identifiants = [
        p.professionnel.identifiant
        for p in annuaire.recommander(litige, limite=5).propositions
    ]
    assert "pro-002" in identifiants


def test_conflit_vaut_aussi_pour_un_dossier_en_cours() -> None:
    """Un dossier non clôturé crée un conflit tout aussi réel."""
    annuaire = annuaire_demo()
    annuaire.enregistrer_dossier(
        Dossier.creer("dos-200", ["ste-zitouna", "autre"], "pro-001", cloture=False)
    )
    assert annuaire.conflit_interets("pro-001", "ste-zitouna") is not None
    identifiants = [
        p.professionnel.identifiant
        for p in annuaire.recommander(litige_ahmed(), limite=5).propositions
    ]
    assert "pro-001" not in identifiants


# --------------------------------------------------------------------------
# Recommandation : abstention explicite, jamais de liste vide silencieuse
# --------------------------------------------------------------------------


def test_annuaire_vide_sabstient_explicitement() -> None:
    """Zéro professionnel inscrit : on le dit, on ne rend pas une liste vide."""
    recommandation = Annuaire().recommander(litige_ahmed())
    assert recommandation.abstention is True
    assert recommandation.propositions == ()
    assert "Aucun professionnel accrédité ne correspond" in recommandation.message
    assert bool(recommandation) is False


def test_aucun_professionnel_correspondant_sabstient(annuaire: Annuaire) -> None:
    """Expertise inexistante : abstention motivée, avec les raisons d'écartement."""
    litige = Litige.creer(
        nature=["droit-spatial"],
        montant_dt=1000.0,
        gouvernorat="Sfax",
        langue="francais",
        voie="conciliation",
        partie_adverse="ste-zitouna",
    )
    recommandation = annuaire.recommander(litige)
    assert recommandation.abstention is True
    assert "Aucun professionnel accrédité ne correspond" in recommandation.message
    assert recommandation.ecartes  # les motifs sont rendus, pas avalés
    assert recommandation.texte() == recommandation.message


def test_voie_inconnue_sabstient(annuaire: Annuaire) -> None:
    """Une voie de règlement qui n'existe pas ne produit pas de proposition."""
    litige = Litige.creer(
        nature=["recouvrement"],
        montant_dt=5000.0,
        gouvernorat="Sfax",
        langue="francais",
        voie="duel-au-sabre",
    )
    recommandation = annuaire.recommander(litige)
    assert recommandation.abstention is True
    assert any("inconnue de la plateforme" in motif for motif in recommandation.ecartes)


def test_litige_sans_gouvernorat_recommande_quand_meme(annuaire: Annuaire) -> None:
    """
    Une saisine incomplète reste traitable : on cherche sans critère de
    proximité, et on l'écrit dans les motifs.
    """
    litige = Litige.creer(
        nature=["recouvrement", "commercial"],
        montant_dt=9520.0,
        gouvernorat=None,
        langue="francais",
        voie="conciliation",
        partie_adverse="ste-zitouna",
    )
    recommandation = annuaire.recommander(litige)
    assert recommandation.abstention is False
    assert recommandation.propositions
    assert any(
        "proximité géographique n'a pas pu être prise en compte" in motif
        for motif in recommandation.propositions[0].motifs
    )


def test_gouvernorat_illisible_est_traite_comme_absent(annuaire: Annuaire) -> None:
    """Un gouvernorat fantaisiste n'invente pas une proximité fausse."""
    litige = Litige.creer(
        nature=["recouvrement"],
        montant_dt=9520.0,
        gouvernorat="Atlantide",
        langue="francais",
        voie="conciliation",
    )
    assert litige.gouvernorat is None


def test_langue_arabe_filtre_les_francophones_seuls(annuaire: Annuaire) -> None:
    """Nizar Chaabane ne travaille qu'en français : écarté sur un litige en arabe."""
    litige = Litige.creer(
        nature=["bail"],
        montant_dt=3000.0,
        gouvernorat="Nabeul",
        langue="arabe",
        voie="mediation",
    )
    recommandation = annuaire.recommander(litige)
    identifiants = [p.professionnel.identifiant for p in recommandation.propositions]
    assert "pro-007" not in identifiants
    assert any("ne travaille pas en arabe" in motif for motif in recommandation.ecartes)


def test_seuil_de_montant_ecarte_larbitre(annuaire: Annuaire) -> None:
    """Me Fatma Jelassi n'accepte pas les dossiers sous 20 000 DT."""
    litige = Litige.creer(
        nature=["commercial"],
        montant_dt=5000.0,
        gouvernorat="Tunis",
        langue="francais",
        voie="arbitrage",
    )
    recommandation = annuaire.recommander(litige)
    identifiants = [p.professionnel.identifiant for p in recommandation.propositions]
    assert "pro-006" not in identifiants
    assert any("inférieurs à 20000 DT" in motif for motif in recommandation.ecartes)


def test_professionnel_suspendu_nest_pas_propose() -> None:
    """Un profil inactif reste en base mais disparaît des propositions."""
    annuaire = Annuaire()
    annuaire.inscrire(
        Professionnel.creer(
            identifiant="pro-susp",
            nom="Me Suspendu",
            qualite="avocat",
            numero_accreditation="X-9",
            expertises=["recouvrement"],
            langues=["francais"],
            gouvernorat="Sfax",
            actif=False,
        )
    )
    recommandation = annuaire.recommander(litige_ahmed())
    assert recommandation.abstention is True
    assert any("profil suspendu" in motif for motif in recommandation.ecartes)


def test_montant_negatif_est_refuse() -> None:
    """Un litige à montant négatif n'est pas un litige."""
    with pytest.raises(ValueError, match="négatif"):
        Litige.creer(
            nature=["recouvrement"],
            montant_dt=-1.0,
            gouvernorat="Sfax",
            langue="francais",
            voie="conciliation",
        )


# --------------------------------------------------------------------------
# Cas nominal : le litige d'Ahmed
# --------------------------------------------------------------------------


def test_cas_ahmed_rend_une_liste_ordonnee_et_motivee(annuaire: Annuaire) -> None:
    """
    Ahmed, menuisier à Sfax, 9 520 DT de factures impayées, conciliation en
    français : le moteur doit proposer PLUSIEURS professionnels, chacun motivé.
    """
    recommandation = annuaire.recommander(litige_ahmed(), limite=3)

    assert recommandation.abstention is False
    assert len(recommandation.propositions) >= 2, "une liste, pas un choix unique"

    # Ordre décroissant de pertinence.
    scores = [p.score for p in recommandation.propositions]
    assert scores == sorted(scores, reverse=True)

    # Chaque proposition est expliquée en français.
    for proposition in recommandation.propositions:
        assert proposition.motifs
        assert "Expertise en" in proposition.explication()

    # Me Sonia Ben Amor : Sfax, recouvrement, 4,5/5 sur deux dossiers clôturés.
    tete = recommandation.propositions[0]
    assert tete.professionnel.identifiant == "pro-001"
    assert tete.note_moyenne == 4.5
    assert tete.nombre_avis == 2
    assert "Sfax" in tete.explication()

    # Le rappel de la règle du projet figure dans le texte rendu aux parties.
    assert "le choix appartient aux parties" in recommandation.texte()


def test_la_recommandation_nimpose_jamais_un_seul_nom(annuaire: Annuaire) -> None:
    """
    Même en demandant une seule proposition, l'API reste une liste : aucune
    fonction ne renvoie un professionnel désigné d'office.
    """
    recommandation = annuaire.recommander(litige_ahmed(), limite=1)
    assert isinstance(recommandation.propositions, tuple)
    assert not hasattr(recommandation, "choix")
    assert not hasattr(recommandation, "designation")


def test_synonyme_impaye_ramene_au_recouvrement() -> None:
    """Les parties écrivent « impayé », l'annuaire comprend « recouvrement »."""
    litige = Litige.creer(
        nature="impaye",
        montant_dt=9520.0,
        gouvernorat="Sfax",
        langue="francais",
        voie="conciliation",
    )
    assert "recouvrement" in litige.domaines()


def test_les_motifs_sont_ecrits_dans_un_francais_correct(annuaire: Annuaire) -> None:
    """
    Ce texte est lu par un juriste : « qualité de avocat » discrédite une
    phrase par ailleurs juste. L'élision est donc testée.
    """
    recommandation = annuaire.recommander(litige_ahmed(), limite=3)
    textes = [p.explication() for p in recommandation.propositions]
    assert any("Qualité d'avocat" in texte for texte in textes)
    assert not any("Qualité de avocat" in texte for texte in textes)
    assert any("Qualité de conciliateur" in texte for texte in textes)
