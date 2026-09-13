"""Ce qui doit rester vrai du scellement, même sous attaque.

Ces tests ne vérifient pas que le code s'exécute. Ils verrouillent les
engagements sur lesquels repose la valeur probante d'un document scellé :

1. Un document altéré, même d'UN SEUL caractère, est détecté.
2. Un sceau ne peut pas être rejoué d'un document sur un autre.
3. Une signature tronquée ou bricolée ne passe pas.
4. La clé d'une autre partie ne permet pas d'usurper une identité.
5. e-Houwiya ne signe RIEN tant que le raccordement n'existe pas.
6. Les réserves juridiques figurent dans TOUT rapport, y compris favorable.

Chacun échoue si l'engagement disparaît du code, et c'est sa seule raison
d'exister. Les entrées hostiles sont testées d'emblée : arabe, documents
très longs, chaînes vides, octets bricolés.
"""
from datetime import datetime, timedelta, timezone

import pytest

from packages.identite import attribution as attr
from packages.identite.signature import (
    LONGUEUR_SIGNATURE_ED25519,
    VERSION_SCELLE,
    DocumentVide,
    ErreurIdentite,
    FournisseurEHouwiya,
    FournisseurIdentite,
    FournisseurIndisponible,
    FournisseurLocal,
    RegistreDeCles,
    Scelle,
    ScelleInvalide,
    empreinte,
    sceller,
    verifier,
)

# --- Décor : deux parties à un litige --------------------------------------
DOCUMENT = (
    "MISE EN DEMEURE — PROJET, NON SIGNIFIÉ\n"
    "Menuiserie Ahmed met en demeure la Société El Amen SARL de lui payer "
    "la somme de 9 520,000 DT au titre de la facture n° 2026-041."
)

DOCUMENT_ARABE = (
    "إنذار — مشروع، غير مبلّغ\n"
    "تنذر نجارة أحمد شركة الأمان ش.م.م بدفع مبلغ 9520,000 د.ت."
)


@pytest.fixture
def ahmed() -> FournisseurLocal:
    return FournisseurLocal("Menuiserie Ahmed")


@pytest.fixture
def el_amen() -> FournisseurLocal:
    return FournisseurLocal("Société El Amen SARL")


@pytest.fixture
def registre(ahmed: FournisseurLocal) -> RegistreDeCles:
    r = RegistreDeCles()
    r.enregistrer_fournisseur(ahmed)
    return r


# --- 1. L'altération d'un seul caractère ------------------------------------

def test_un_seul_caractere_altere_fait_echouer_la_verification(ahmed):
    """Le test central : 9 520 devient 9 530, et la vérification le dit.

    C'est la raison d'être de toute la couche. Si un chiffre du montant peut
    être changé sans que le sceau s'en aperçoive, la plateforme ne prouve
    rien et ne doit pas être livrée.
    """
    s = sceller(DOCUMENT, ahmed)
    altere = DOCUMENT.replace("9 520,000", "9 530,000")
    assert altere != DOCUMENT, "Le test doit réellement modifier le document."

    resultat = verifier(s, altere, cle_publique_reference=ahmed.cle_publique_hex)

    assert resultat.valide is False
    assert resultat.document_intact is False
    assert resultat.attribution_etablie is False
    assert "modifié" in resultat.motif or "ne correspond pas" in resultat.motif


def test_un_espace_ajoute_en_fin_de_document_est_detecte(ahmed):
    """Un caractère invisible reste une altération.

    Les altérations utiles à un fraudeur ne sont pas toujours visibles :
    une espace insécable substituée à une espace ordinaire peut changer un
    montant à l'impression.
    """
    s = sceller(DOCUMENT, ahmed)
    resultat = verifier(s, DOCUMENT + " ")
    assert resultat.document_intact is False


def test_une_espace_insecable_substituee_est_detectee(ahmed):
    """L'empreinte porte sur les octets, pas sur l'apparence."""
    s = sceller(DOCUMENT, ahmed)
    altere = DOCUMENT.replace("9 520,000", "9\u00a0520,000")
    assert altere != DOCUMENT
    assert verifier(s, altere).document_intact is False


def test_le_document_intact_est_reconnu(ahmed, registre):
    """Le contrôle négatif : sans lui, un code qui refuse tout passerait.

    Un vérificateur qui répond « invalide » à tout détecte parfaitement les
    altérations et ne vaut rien. Ce test tient l'autre bout.
    """
    s = sceller(DOCUMENT, ahmed)
    resultat = registre.verifier_scelle(s, DOCUMENT)
    assert resultat.valide is True
    assert resultat.document_intact is True
    assert resultat.signature_valide is True
    assert resultat.attribution_etablie is True


# --- 2. Le rejeu d'un sceau sur un autre document ---------------------------

def test_un_scelle_valide_ne_peut_pas_etre_rejoue_sur_un_autre_document(ahmed):
    """Un sceau authentique collé sur un autre texte ne le valide pas.

    L'attaque est évidente et c'est la plus probable : on prend le sceau
    d'une facture de 500 DT que le débiteur a bien reçue, et on le recolle
    sur une facture de 50 000 DT.
    """
    s = sceller(DOCUMENT, ahmed)
    autre = DOCUMENT.replace("9 520,000", "95 200,000")

    resultat = verifier(s, autre, cle_publique_reference=ahmed.cle_publique_hex)

    assert resultat.valide is False
    assert resultat.document_intact is False
    # La signature, elle, reste authentique : elle porte sur l'ancienne
    # empreinte. C'est bien l'intégrité qui doit trancher.
    assert resultat.signature_valide is True


def test_deux_documents_differents_ont_des_empreintes_differentes():
    assert empreinte(DOCUMENT) != empreinte(DOCUMENT + "x")


# --- 3. Signatures tronquées, bricolées, illisibles -------------------------

def test_une_signature_tronquee_est_rejetee_avec_un_motif_clair(ahmed):
    """Une signature coupée en deux ne prouve pas la moitié de quelque chose.

    Le message doit être intelligible dans un rapport : « tronquée », pas
    une exception de bas niveau.
    """
    s = sceller(DOCUMENT, ahmed)
    tronque = Scelle(**{**s.to_dict(), "signature": s.signature[: len(s.signature) // 2]})

    resultat = verifier(tronque, DOCUMENT)

    assert resultat.valide is False
    assert resultat.signature_valide is False
    assert any("tronquée" in a for a in resultat.anomalies)


def test_une_signature_non_hexadecimale_est_rejetee(ahmed):
    s = sceller(DOCUMENT, ahmed)
    casse = Scelle(**{**s.to_dict(), "signature": "ceci n'est pas de l'hexa"})
    resultat = verifier(casse, DOCUMENT)
    assert resultat.valide is False
    assert any("hexadécimale" in a for a in resultat.anomalies)


def test_une_signature_de_bonne_longueur_mais_fausse_est_rejetee(ahmed):
    """Bonne longueur, mauvais contenu : le contrôle de forme ne suffit pas."""
    s = sceller(DOCUMENT, ahmed)
    faux = "00" * LONGUEUR_SIGNATURE_ED25519
    casse = Scelle(**{**s.to_dict(), "signature": faux})
    resultat = verifier(casse, DOCUMENT)
    assert resultat.valide is False
    assert resultat.signature_valide is False


def test_modifier_le_signataire_declare_invalide_la_signature(ahmed):
    """On ne réécrit pas le nom du signataire sur un sceau existant.

    Si seule l'empreinte du document était signée, ce champ serait librement
    réécrivable : n'importe qui pourrait s'attribuer le document d'un autre.
    """
    s = sceller(DOCUMENT, ahmed)
    usurpe = Scelle(**{**s.to_dict(), "identifiant_signataire": "Quelqu'un d'autre"})
    resultat = verifier(usurpe, DOCUMENT)
    assert resultat.signature_valide is False
    assert resultat.valide is False


def test_modifier_l_horodatage_invalide_la_signature(ahmed):
    """Antidater un sceau doit casser la signature, sinon la date ne vaut rien."""
    s = sceller(DOCUMENT, ahmed)
    antidate = Scelle(**{
        **s.to_dict(),
        "horodatage": (datetime.now(timezone.utc) - timedelta(days=365)).isoformat(),
    })
    assert verifier(antidate, DOCUMENT).signature_valide is False


def test_modifier_le_contexte_invalide_la_signature(ahmed):
    """Le numéro de dossier est signé lui aussi : on ne le déplace pas."""
    s = sceller(DOCUMENT, ahmed, contexte={"dossier": "2026-041"})
    bricole = Scelle(**{**s.to_dict(), "contexte": {"dossier": "2026-999"}})
    assert verifier(bricole, DOCUMENT).signature_valide is False


# --- 4. La clé d'une autre partie -------------------------------------------

def test_la_cle_publique_d_une_autre_partie_ne_valide_pas_le_scelle(ahmed, el_amen):
    """Vérifier avec la clé du débiteur un sceau apposé par le créancier."""
    s = sceller(DOCUMENT, ahmed)
    resultat = verifier(
        s, DOCUMENT, cle_publique_reference=el_amen.cle_publique_hex
    )
    assert resultat.attribution_etablie is False
    assert any("autre clé" in a for a in resultat.anomalies)


def test_un_tiers_ne_peut_pas_usurper_l_identite_d_une_partie_enregistree(
    ahmed, registre
):
    """L'attaque complète : re-signer un faux avec sa propre paire de clés.

    Le faussaire modifie le document, le scelle avec SA clé, et met le nom
    d'Ahmed dans le champ signataire. Sans registre, le sceau paraîtrait
    cohérent : c'est précisément ce que le registre empêche.
    """
    faussaire = FournisseurLocal("Menuiserie Ahmed")  # même nom, autre clé
    faux_document = DOCUMENT.replace("9 520,000", "95 200,000")
    faux_scelle = sceller(faux_document, faussaire)

    # Contrôle de la mise en scène : le faux est cohérent avec lui-même.
    naif = verifier(faux_scelle, faux_document)
    assert naif.document_intact is True
    assert naif.signature_valide is True
    assert naif.attribution_etablie is False, (
        "Sans clé de référence, aucune attribution ne doit être établie."
    )

    # Le registre, lui, connaît la vraie clé d'Ahmed et démasque le faux.
    verdict = registre.verifier_scelle(faux_scelle, faux_document)
    assert verdict.attribution_etablie is False
    assert any("autre clé" in a for a in verdict.anomalies)


def test_sans_cle_de_reference_l_attribution_n_est_jamais_etablie(ahmed):
    """La réserve doit être explicite, pas implicite.

    Vérifier une signature avec la clé jointe au document ne prouve rien :
    le résultat doit le dire, sinon un rapport affirmera plus que de raison.
    """
    s = sceller(DOCUMENT, ahmed)
    resultat = verifier(s, DOCUMENT)
    assert resultat.valide is True
    assert resultat.attribution_etablie is False
    assert any("PAS qui l'a signé" in a for a in resultat.anomalies)


def test_un_signataire_inconnu_du_registre_n_est_pas_confirme(el_amen, registre):
    s = sceller(DOCUMENT, el_amen)
    resultat = registre.verifier_scelle(s, DOCUMENT)
    assert resultat.attribution_etablie is False
    assert any("registre des clés" in a for a in resultat.anomalies)


def test_le_registre_refuse_de_remplacer_une_cle_silencieusement(ahmed, registre):
    """Changer la clé d'une partie sans le dire invalide le passé."""
    autre = FournisseurLocal("Menuiserie Ahmed")
    with pytest.raises(ErreurIdentite, match="déjà enregistrée"):
        registre.enregistrer_fournisseur(autre)


def test_le_registre_accepte_le_reenregistrement_de_la_meme_cle(ahmed, registre):
    """Idempotent : réenregistrer la même clé n'est pas un conflit."""
    registre.enregistrer_fournisseur(ahmed)
    assert registre.connait("Menuiserie Ahmed")


def test_le_registre_refuse_une_cle_publique_invalide(registre):
    with pytest.raises(ErreurIdentite, match="invalide"):
        registre.enregistrer("Quelqu'un", "pas une clé")


# --- 5. Entrées hostiles ----------------------------------------------------

def test_sceller_un_document_vide_est_refuse(ahmed):
    """Un sceau sur rien est un sceau que n'importe qui peut rejouer."""
    with pytest.raises(DocumentVide):
        sceller("", ahmed)


def test_sceller_des_octets_vides_est_refuse(ahmed):
    with pytest.raises(DocumentVide):
        sceller(b"", ahmed)


def test_un_document_vide_presente_a_la_verification_ne_valide_rien(ahmed):
    s = sceller(DOCUMENT, ahmed)
    resultat = verifier(s, "")
    assert resultat.valide is False
    assert "vide" in resultat.motif


def test_un_document_en_arabe_se_scelle_et_se_verifie(ahmed, registre):
    """Le corpus est bilingue : l'arabe n'est pas un cas exotique ici."""
    s = sceller(DOCUMENT_ARABE, ahmed)
    assert registre.verifier_scelle(s, DOCUMENT_ARABE).valide is True


def test_un_caractere_arabe_altere_est_detecte(ahmed):
    """Un chiffre changé dans un montant en arabe compte autant qu'en latin."""
    s = sceller(DOCUMENT_ARABE, ahmed)
    altere = DOCUMENT_ARABE.replace("9520", "9530")
    assert altere != DOCUMENT_ARABE
    assert verifier(s, altere).document_intact is False


def test_un_document_tres_long_se_scelle_et_detecte_une_alteration(ahmed, registre):
    """Un dossier complet peut peser plusieurs mégaoctets.

    Et l'altération doit être détectée où qu'elle se trouve — ici au milieu,
    l'endroit le plus facile à oublier dans une implémentation naïve.
    """
    long_doc = ("Article premier. " * 100_000) + "FIN"
    assert len(long_doc) > 1_000_000
    s = sceller(long_doc, ahmed)
    assert registre.verifier_scelle(s, long_doc).valide is True

    milieu = len(long_doc) // 2
    altere = long_doc[:milieu] + "X" + long_doc[milieu + 1:]
    assert len(altere) == len(long_doc)
    assert verifier(s, altere).document_intact is False


def test_un_identifiant_vide_est_refuse():
    """Un sceau anonyme n'attribue rien : autant ne pas le produire."""
    with pytest.raises(ErreurIdentite):
        FournisseurLocal("")
    with pytest.raises(ErreurIdentite):
        FournisseurLocal("   ")


def test_un_horodatage_sans_fuseau_est_refuse(ahmed):
    """Une heure sans fuseau ne veut rien dire dans un dossier transfrontalier."""
    with pytest.raises(ErreurIdentite, match="fuseau"):
        sceller(DOCUMENT, ahmed, horodatage=datetime(2026, 9, 13, 9, 0))


def test_un_contexte_non_serialisable_est_refuse_a_la_source(ahmed):
    """Mieux vaut échouer en scellant qu'obtenir un sceau invérifiable."""
    with pytest.raises(ErreurIdentite, match="sérialisable"):
        sceller(DOCUMENT, ahmed, contexte={"objet": object()})


def test_un_scelle_incomplet_est_rejete():
    with pytest.raises(ScelleInvalide, match="incomplet"):
        Scelle.from_dict({"version": VERSION_SCELLE})


def test_un_scelle_illisible_est_rejete():
    with pytest.raises(ScelleInvalide, match="illisible"):
        Scelle.from_json("{ ceci n'est pas du JSON")


def test_un_scelle_d_une_autre_version_n_est_pas_verifie(ahmed):
    """Un format inconnu obéit peut-être à d'autres règles : on ne devine pas."""
    s = sceller(DOCUMENT, ahmed)
    ancien = Scelle(**{**s.to_dict(), "version": "mizan-scelle-0"})
    resultat = verifier(ancien, DOCUMENT)
    assert resultat.valide is False
    assert "Format de sceau inconnu" in resultat.motif


def test_sceller_un_type_absurde_est_refuse(ahmed):
    with pytest.raises(ScelleInvalide):
        sceller(12345, ahmed)  # type: ignore[arg-type]


# --- 6. e-Houwiya : NON IMPLÉMENTÉ, et ça doit le rester tant que --------

def test_ehouwiya_refuse_de_signer_et_dit_pourquoi():
    """Le test qui échoue si quelqu'un simule une intégration d'État.

    Produire un sceau « e-Houwiya » sans raccordement à TunTrust/ANCE serait
    un faux. L'exception est la fonctionnalité, pas un manque.
    """
    fournisseur = FournisseurEHouwiya("12345678")
    with pytest.raises(FournisseurIndisponible) as exc:
        fournisseur.signer(b"peu importe")
    message = str(exc.value)
    assert "TunTrust" in message
    assert "UNKNOWN" in message


def test_ehouwiya_refuse_de_donner_une_identite_ou_une_cle():
    f = FournisseurEHouwiya()
    with pytest.raises(FournisseurIndisponible):
        _ = f.identifiant
    with pytest.raises(FournisseurIndisponible):
        _ = f.cle_publique_hex


def test_sceller_avec_ehouwiya_echoue_avant_de_produire_quoi_que_ce_soit():
    """Aucun sceau partiel, aucun fichier, aucune trace : rien."""
    with pytest.raises(FournisseurIndisponible):
        sceller(DOCUMENT, FournisseurEHouwiya())


def test_ehouwiya_reste_une_erreur_notimplemented():
    """Le code appelant existant qui attrape NotImplementedError fonctionne."""
    assert issubclass(FournisseurIndisponible, NotImplementedError)


# --- 7. Le contrat d'interface ---------------------------------------------

def test_le_fournisseur_local_respecte_l_interface(ahmed):
    """L'abstraction doit tenir, sinon changer de fournisseur casse tout."""
    assert isinstance(ahmed, FournisseurIdentite)


def test_une_identite_locale_se_recharge_depuis_son_pem(ahmed, registre):
    """Une clé qui ne survit pas au redémarrage ne sert à rien en production."""
    pem = ahmed.exporter_cle_privee_pem(b"mot-de-passe-de-test")
    rechargee = FournisseurLocal.depuis_pem(
        "Menuiserie Ahmed", pem, b"mot-de-passe-de-test"
    )
    assert rechargee.cle_publique_hex == ahmed.cle_publique_hex
    s = sceller(DOCUMENT, rechargee)
    assert registre.verifier_scelle(s, DOCUMENT).attribution_etablie is True


def test_une_cle_privee_illisible_est_refusee():
    with pytest.raises(ErreurIdentite, match="illisible"):
        FournisseurLocal.depuis_pem("X", b"pas une cle PEM du tout")


def test_le_scelle_survit_a_un_aller_retour_json(ahmed, registre):
    """Le sceau transite par une base ou un fichier : il doit y survivre."""
    s = sceller(DOCUMENT_ARABE, ahmed, contexte={"dossier": "2026-041"})
    relu = Scelle.from_json(s.to_json())
    assert relu == s
    assert registre.verifier_scelle(relu, DOCUMENT_ARABE).valide is True


def test_le_json_du_scelle_garde_l_arabe_lisible(ahmed):
    """Un sceau illisible en base complique inutilement toute expertise."""
    s = sceller(DOCUMENT, ahmed, contexte={"objet": "إنذار"})
    assert "إنذار" in s.to_json()


def test_un_scelle_est_immuable(ahmed):
    """Un sceau modifiable en mémoire n'est pas un sceau."""
    s = sceller(DOCUMENT, ahmed)
    with pytest.raises(Exception):
        s.empreinte_document = "autre chose"  # type: ignore[misc]


# --- 8. Le rapport d'attribution : ce qu'il dit au juge ---------------------

def test_le_rapport_repond_aux_trois_questions(ahmed, registre):
    s = sceller(DOCUMENT, ahmed, horodatage=datetime(2026, 9, 13, 9, 41,
                                                     tzinfo=timezone.utc))
    rapport = attr.attribuer(s, DOCUMENT, registre=registre)

    assert rapport.signataire_declare == "Menuiserie Ahmed"
    assert rapport.signataire_confirme is True
    assert rapport.document_modifie is False
    assert "13 septembre 2026" in rapport.date_scellement
    assert "09h41" in rapport.date_scellement


def test_le_rapport_est_en_francais_et_sans_jargon(ahmed, registre):
    """Un rapport que seul un cryptographe comprend ne se plaide pas."""
    s = sceller(DOCUMENT, ahmed)
    texte = attr.attribuer(s, DOCUMENT, registre=registre).en_texte()
    assert "QUI a scellé ce document ?" in texte
    assert "QUAND ?" in texte
    assert "Le document a-t-il été modifié depuis ?" in texte
    for jargon in ("Ed25519", "SHA-256", "hexadéc", "nonce"):
        assert jargon not in texte, (
            f"Le rapport destiné au juge contient le terme technique « {jargon} »."
        )


def test_le_rapport_annonce_clairement_une_alteration(ahmed, registre):
    """Le cas qui compte : le rapport doit être sans ambiguïté."""
    s = sceller(DOCUMENT, ahmed)
    altere = DOCUMENT.replace("9 520,000", "9 530,000")
    rapport = attr.attribuer(s, altere, registre=registre)

    assert rapport.document_modifie is True
    assert rapport.signataire_confirme is False
    assert "N'EST PAS celui qui a été scellé" in rapport.conclusion
    assert "OUI — le document présenté n'est pas celui" in rapport.en_texte()


def test_le_rapport_distingue_identite_inconnue_et_document_altere(el_amen):
    """Deux situations très différentes, qui n'ont pas les mêmes suites.

    « Je ne sais pas qui a signé » n'est pas « le document a été falsifié ».
    Confondre les deux, c'est accuser à tort ou rassurer à tort.
    """
    s = sceller(DOCUMENT, el_amen)
    rapport = attr.attribuer(s, DOCUMENT)  # sans registre
    assert rapport.document_modifie is False
    assert rapport.signataire_confirme is False
    assert "n'est pas confirmée" in rapport.conclusion


def test_les_reserves_juridiques_figurent_dans_tout_rapport(ahmed, registre):
    """Y compris — surtout — dans un rapport favorable.

    Un rapport qui conclut à la validité sans dire que l'horodatage n'est pas
    qualifié et que la signature n'est pas qualifiée affirme plus que ce que
    la technique établit. Il serait détruit à la première contestation.
    """
    s = sceller(DOCUMENT, ahmed)
    rapport = attr.attribuer(s, DOCUMENT, registre=registre)
    assert rapport.signataire_confirme is True  # rapport favorable

    texte = rapport.en_texte()
    reserves = texte.split("CE QUE CE RAPPORT N'ÉTABLIT PAS")[1]
    assert "n'est pas un horodatage qualifié" in reserves
    assert "signature électronique qualifiée" in reserves
    assert "Sceller n'est pas signifier" in reserves
    assert "huissier" in reserves
    assert len(rapport.reserves) == len(attr.RESERVES_PERMANENTES)


def test_le_rapport_signale_une_signature_tronquee_en_clair(ahmed, registre):
    s = sceller(DOCUMENT, ahmed)
    tronque = Scelle(**{**s.to_dict(), "signature": s.signature[:20]})
    rapport = attr.attribuer(tronque, DOCUMENT, registre=registre)
    assert "n'établit rien" in rapport.conclusion


def test_le_rapport_accepte_un_scelle_relu_depuis_un_dictionnaire(ahmed, registre):
    """Le sceau vient d'une base de données, pas d'un objet en mémoire."""
    s = sceller(DOCUMENT, ahmed)
    rapport = attr.attribuer(s.to_dict(), DOCUMENT, registre=registre)
    assert rapport.signataire_confirme is True


def test_un_horodatage_illisible_n_est_pas_remplace_par_une_date_inventee(ahmed):
    """Un rapport ne corrige pas silencieusement ce qu'il constate."""
    s = sceller(DOCUMENT, ahmed)
    casse = Scelle(**{**s.to_dict(), "horodatage": "pas une date"})
    rapport = attr.attribuer(casse, DOCUMENT)
    assert "illisible" in rapport.date_scellement
