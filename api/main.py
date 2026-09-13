"""API HTTP de Mizan.

Ce que cette API expose, et surtout ce qu'elle refuse d'exposer
--------------------------------------------------------------
Le moteur juridique est déterministe : les délais de prescription, les seuils
et les articles cités sortent de `packages/legal/`, jamais d'un modèle de
langage. L'API est une couche de transport — elle sérialise une décision, elle
n'en prend aucune.

Le seul endpoint qui appelle un modèle est `/assistant/expliquer`, et il est
construit à l'envers de l'usage habituel : le moteur calcule d'abord, les
articles sont choisis d'abord, puis on demande au modèle de reformuler ce
paquet en français simple. Les citations lui sont FOURNIES ; il n'a pas à les
produire, et si jamais il en invente une, `_purger_articles` la retire avant
que la réponse ne quitte le serveur.

Si aucun modèle ne répond, l'endpoint retourne 200 avec une explication
dégradée rédigée à partir du moteur seul. Une PME ne doit pas voir une erreur
500 parce qu'un GPU est occupé : le droit, lui, est toujours disponible.
"""
from __future__ import annotations

import hashlib
import logging
import re
import tempfile
from datetime import date
from pathlib import Path

from api import amorce  # noqa: F401  — installe sys.path avant les imports métier

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from packages.legal import doc_gate, gate, invoice, retrieve
from packages.legal.legal_engine import DateImpossible, assess
from packages.models.client import ClientLLM, ModeleIndisponible

from api.documents import routeur as routeur_documents
from api.schemas import (
    Analyse,
    ArticleTrouve,
    DemandeAnalyse,
    DemandeExplication,
    EtatHebergement,
    Explication,
    PieceDeposee,
    Recherche,
    Sante,
)

logger = logging.getLogger("mizan.api")

VERSION = "1.0.0"
PRINCIPE = "L'IA propose. Le droit dispose."
AVERTISSEMENT_SOURCES = (
    "Chaque article cité a été relu dans le corpus indexé. Aucun modèle de "
    "langage n'énonce ici une règle de droit."
)
# Une PME n'a pas besoin d'un roman, et un modèle bavard finit toujours par
# broder du droit. La longueur est donc bornée à la source.
MAX_TOKENS_EXPLICATION = 420
TAILLE_MAX_PIECE = 20 * 1024 * 1024  # 20 Mo : au-delà, ce n'est plus une facture

app = FastAPI(
    title="Mizan — API juridique",
    version=VERSION,
    description=(
        "Résolution de litiges commerciaux pour les PME tunisiennes. "
        "Le moteur juridique est déterministe ; le modèle de langage ne sert "
        "qu'à reformuler."
    ),
)

# Le frontend Next.js tourne en local sur le port 3000.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Les deux livrables institutionnels du brief §4 : le projet de mise en
# demeure et le tableau greffier.
app.include_router(routeur_documents)

# Un seul client, construit au démarrage : `sonder()` interroge le réseau, on
# ne recrée pas l'objet à chaque requête.
_client = ClientLLM()


def client_llm() -> ClientLLM:
    """Indirection volontaire : les tests remplacent cette fonction."""
    return _client


# ---------------------------------------------------------------------------
# Outils internes
# ---------------------------------------------------------------------------

def _parse_date(valeur: str | None, champ: str) -> date | None:
    if valeur is None:
        return None
    try:
        return date.fromisoformat(valeur)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Le champ « {champ} » doit être une date au format AAAA-MM-JJ. "
                f"Reçu : « {valeur} »."
            ),
        )


def _analyser(montant: float, date_facture: str, activite: str,
              aujourdhui: str | None) -> Analyse:
    """Appelle le moteur et traduit ses refus en erreurs HTTP propres.

    Le moteur lève `DateImpossible` sur une facture datée de demain. C'est une
    donnée d'entrée invalide, pas une panne du serveur : 400, avec le motif du
    moteur mot pour mot — il est déjà rédigé pour un lecteur non juriste.
    """
    jour = _parse_date(aujourdhui, "aujourdhui")
    _parse_date(date_facture, "date_facture")
    try:
        a = assess(montant, date_facture, activite, today=jour)
    except DateImpossible as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    d = a.to_dict()
    return Analyse(
        montant_tnd=d["amount_tnd"],
        date_facture=d["invoice_date"],
        aujourdhui=d["today"],
        regime=d["regime"],
        regime_reason_fr=d["regime_reason_fr"],
        echeance=d["deadline"],
        jours_restants=d["days_left"],
        est_prescrit=d["is_expired"],
        urgence=d["urgency"],
        huissier_requis=d["needs_bailiff"],
        jours_francs=d["grace_days"],
        sources=d["sources"],
        etapes=d["steps"],
    )


# Un modèle qui cite le droit est un modèle qui invente le droit. On ne lui
# fait pas confiance sur ce point : on relit sa sortie.
_MOTIFS_ARTICLE = [
    re.compile(r"\b(?:art\.?|article[s]?)\s*(?:n[°o]\s*)?\d+\w*", re.I),
    re.compile(r"الفصل\s*\d+"),
    re.compile(r"\b(?:COC|CPCC?|C\.?O\.?C\.?)\s*(?:art\.?)?\s*\d+", re.I),
]
MENTION_PURGE = "[référence retirée : les articles sont affichés par le moteur]"


def _purger_articles(texte: str) -> tuple[str, bool]:
    """Retire toute référence d'article produite par le modèle.

    Le modèle reçoit pourtant les articles en contexte et pour consigne de ne
    pas les citer. Ce filtre est la ceinture après les bretelles : un modèle
    quantifié dérape, et une référence fausse affichée à une PME vaut pire que
    pas de référence du tout. Les vraies citations arrivent séparément, dans
    le champ `sources`.
    """
    purge = False
    for rx in _MOTIFS_ARTICLE:
        texte, n = rx.subn(MENTION_PURGE, texte)
        purge = purge or bool(n)
    return texte, purge


def _resume_pour_modele(a: Analyse) -> str:
    """Le paquet de faits — déjà calculés — que le modèle doit reformuler."""
    etat = (
        f"le délai est DÉPASSÉ depuis {abs(a.jours_restants)} jours"
        if a.est_prescrit
        else f"il reste {a.jours_restants} jours avant l'échéance du "
             f"{a.echeance}"
    )
    lignes = [
        f"Montant réclamé : {a.montant_tnd:.3f} DT",
        f"Date de la facture : {a.date_facture}",
        f"Date du jour : {a.aujourdhui}",
        f"Délai de prescription applicable : {a.regime}",
        f"Motif du régime retenu : {a.regime_reason_fr}",
        f"Situation : {etat} (niveau d'urgence : {a.urgence})",
        (
            "Sommation par huissier de justice obligatoire, avec "
            f"{a.jours_francs} jours francs laissés au débiteur."
            if a.huissier_requis
            else "Sommation par huissier non exigée à ce montant."
        ),
        "Étapes calculées par le moteur :",
    ]
    lignes += [f"  {e.order}. {e.title_fr} — {e.detail_fr}" for e in a.etapes]
    lignes.append(
        "Références déjà vérifiées et affichées séparément à l'utilisateur : "
        + ", ".join(s.short_fr for s in a.sources)
    )
    return "\n".join(lignes)


SYSTEME_EXPLICATION = (
    "Tu es l'assistant de Mizan, une plateforme tunisienne d'aide aux PME en "
    "litige commercial. Tu écris en français simple, à un artisan ou un petit "
    "commerçant qui n'est pas juriste.\n"
    "RÈGLES ABSOLUES :\n"
    "1. Tu ne cites JAMAIS un article de loi, ni son numéro, ni son code. "
    "Les références exactes sont affichées à côté de ton texte par le moteur "
    "juridique : tu n'as pas à les répéter ni à en produire.\n"
    "2. Tu n'inventes aucun chiffre, aucune date, aucun délai. Tu n'utilises "
    "que les valeurs données ci-dessous.\n"
    "3. Tu reformules, tu n'ajoutes rien. Si une information manque, tu dis "
    "qu'elle manque.\n"
    "4. Cinq phrases au maximum, ton posé, pas de formule commerciale."
)


def _explication_degradee(a: Analyse, motif: str) -> str:
    """Ce que l'utilisateur lit quand aucun modèle ne répond.

    Écrit à la main à partir des valeurs du moteur : c'est moins fluide qu'une
    reformulation, et c'est exactement aussi juste.
    """
    montant = f"{a.montant_tnd:,.3f}".replace(",", " ")
    if a.est_prescrit:
        situation = (
            f"Le délai pour agir est dépassé depuis {abs(a.jours_restants)} jours "
            f"(échéance : {a.echeance}). Une action reste possible mais le "
            f"débiteur peut opposer la prescription."
        )
    else:
        situation = (
            f"Il vous reste {a.jours_restants} jours pour agir, jusqu'au "
            f"{a.echeance}."
        )
    suite = (
        f"Votre créance dépasse le seuil légal : la sommation doit être "
        f"signifiée par un huissier de justice, qui laisse {a.jours_francs} "
        f"jours francs au débiteur pour payer. Passé ce délai, vous pouvez "
        f"demander une injonction de payer."
        if a.huissier_requis
        else "À ce montant, la sommation par huissier n'est pas exigée."
    )
    return (
        f"Vous réclamez {montant} DT au titre d'une facture du "
        f"{a.date_facture}. {situation} {a.regime_reason_fr} {suite}\n\n"
        f"(Reformulation automatique indisponible — {motif}. Le calcul "
        f"ci-dessus est celui du moteur juridique, il n'en dépend pas.)"
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/sante", response_model=Sante, summary="État du service")
def sante() -> Sante:
    """État du service : modèle, index, version.

    Le motif d'indisponibilité est retourné en clair. Un booléen seul oblige à
    aller lire les journaux au pire moment.
    """
    etats: list[EtatHebergement] = []
    motifs: list[str] = []
    disponible = False
    for h, ok, motif in client_llm().sonder():
        etats.append(EtatHebergement(
            nom=h.nom, base_url=h.base_url, modele=h.modele,
            disponible=ok, motif=motif,
        ))
        disponible = disponible or ok
        if not ok:
            motifs.append(f"{h.nom} — {motif}")

    if disponible:
        motif_global = "ok"
    elif etats:
        motif_global = " | ".join(motifs)
    else:
        motif_global = "aucun hébergement configuré"

    try:
        nb = len(retrieve._CACHE["docs"]) if retrieve._CACHE else len(
            _charger_index()
        )
        charge = True
    except Exception as exc:  # noqa: BLE001 — l'état doit répondre même cassé
        logger.warning("index illisible : %s", exc)
        nb, charge = 0, False

    return Sante(
        service="mizan-api",
        version=VERSION,
        moteur_juridique="deterministe",
        modele_disponible=disponible,
        motif_modele=motif_global,
        hebergements=etats,
        articles_indexes=nb,
        index_charge=charge,
        principe=PRINCIPE,
    )


def _charger_index() -> list:
    """Force le chargement du pickle et retourne les documents."""
    retrieve.search("تقادم", k=1)
    return retrieve._CACHE.get("docs", [])


@app.post("/dossiers/analyser", response_model=Analyse,
          summary="Évaluation déterministe d'un impayé")
def analyser(demande: DemandeAnalyse) -> Analyse:
    return _analyser(
        demande.montant_tnd, demande.date_facture,
        demande.activite, demande.aujourdhui,
    )


@app.post("/dossiers/deposer-piece", response_model=PieceDeposee,
          summary="Dépôt d'une pièce : empreinte, contrôle, extraction")
async def deposer_piece(fichier: UploadFile = File(...)) -> PieceDeposee:
    """Reçoit un PDF, l'empreinte, vérifie que c'est une facture, l'extrait.

    L'empreinte SHA-256 est calculée AVANT toute analyse : c'est elle qui
    permettra au greffier de contrôler que la pièce reçue est bien celle qui a
    été déposée.
    """
    contenu = await fichier.read()
    if not contenu:
        raise HTTPException(status_code=400, detail="Le fichier reçu est vide.")
    if len(contenu) > TAILLE_MAX_PIECE:
        raise HTTPException(
            status_code=413,
            detail=f"Fichier trop volumineux ({len(contenu)} octets) : "
                   f"la limite est de {TAILLE_MAX_PIECE // (1024 * 1024)} Mo.",
        )

    empreinte = hashlib.sha256(contenu).hexdigest()
    nom = fichier.filename or "piece.pdf"
    suffixe = Path(nom).suffix.lower() or ".pdf"

    with tempfile.NamedTemporaryFile(suffix=suffixe, delete=True) as tmp:
        tmp.write(contenu)
        tmp.flush()
        try:
            texte, methode = invoice.extract_text(tmp.name)
        except Exception as exc:  # noqa: BLE001 — un PDF cassé n'est pas un bug
            logger.warning("extraction impossible pour %s : %s", nom, exc)
            return PieceDeposee(
                acceptee=False, nom_fichier=nom, sha256=empreinte,
                taille_octets=len(contenu),
                motif_refus=(
                    "Le contenu du document n'a pas pu être lu. Déposez un PDF "
                    "ou une photo nette de la facture."
                ),
                avertissement=AVERTISSEMENT_SOURCES,
            )

        verdict = doc_gate.inspect(texte)
        if not verdict["is_invoice"]:
            motif = verdict["reason"] or verdict["detail"] or "document non reconnu"
            if verdict["detail"] and verdict["reason"]:
                motif = f"{verdict['reason']} ({verdict['detail']})"
            return PieceDeposee(
                acceptee=False, nom_fichier=nom, sha256=empreinte,
                taille_octets=len(contenu), methode_extraction=methode,
                motif_refus=(
                    f"Ce document n'est pas accepté comme facture : {motif}. "
                    "Aucun montant n'en a été extrait — Mizan refuse plutôt que "
                    "de deviner."
                ),
                indices_trouves=verdict["signals"],
                indices_manquants=verdict["missing"],
                avertissement=AVERTISSEMENT_SOURCES,
            )

        donnees = invoice.parse_invoice(tmp.name)

    return PieceDeposee(
        acceptee=True, nom_fichier=nom, sha256=empreinte,
        taille_octets=len(contenu), methode_extraction=donnees["method"],
        indices_trouves=verdict["signals"],
        indices_manquants=verdict["missing"],
        ligne_montant=verdict["anchored_line"],
        montant_tnd=donnees["amount_tnd"],
        date_facture=donnees["invoice_date"],
        dates_trouvees=donnees["all_dates"],
        numero_facture=donnees["invoice_no"],
        client=donnees["client"],
        avertissement=AVERTISSEMENT_SOURCES,
    )


@app.get("/corpus/rechercher", response_model=Recherche,
         summary="Recherche BM25 dans le corpus arabe")
def rechercher(
    q: str = Query(..., min_length=1, description="Requête, en arabe de préférence."),
    k: int = Query(5, ge=1, le=20),
    code_id: str | None = Query(None, description="Filtre : coc, procciv, commerce…"),
) -> Recherche:
    """Cherche dans le corpus et dit quand il ne répond pas.

    Le garde-fou d'abstention (`gate.py`) est appliqué : si les termes de la
    question ne figurent pas dans l'article trouvé, on retourne quand même les
    résultats mais `fonde` vaut faux et le message le dit. Afficher un article
    sans ce signal, c'est laisser croire que le corpus a répondu.
    """
    try:
        hits = retrieve.search(q, k=k, code_id=code_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="L'index du corpus est absent. Reconstruisez-le : "
                   "python -m packages.legal.retrieve build",
        )

    verdict = gate.evaluate(q, hits)
    resultats = [
        ArticleTrouve(
            id=h["id"], code_id=h["code_id"], code_fr=h["code_fr"],
            code_ar=h["code_ar"], article=h["article"],
            citation_ar=h["citation_ar"], text_ar=h["text_ar"],
            score=h["score"],
        )
        for h in hits
    ]
    return Recherche(
        requete=q,
        nombre=len(resultats),
        fonde=verdict["grounded"],
        motif_abstention=verdict["reason"],
        message=None if verdict["grounded"] else gate.ABSTAIN_MESSAGE,
        resultats=resultats,
    )


@app.post("/assistant/expliquer", response_model=Explication,
          summary="Reformulation en français simple, sans citation inventée")
def expliquer(demande: DemandeExplication) -> Explication:
    """Fait reformuler l'évaluation du moteur par le modèle.

    L'ordre compte : le moteur calcule, puis le modèle reformule. Jamais
    l'inverse. Si le modèle est absent, on retourne 200 avec une explication
    dégradée — le moteur juridique n'a besoin de personne.
    """
    # On recalcule TOUJOURS côté moteur. Une analyse envoyée par le client
    # pourrait avoir été modifiée ; le droit ne se négocie pas dans un corps
    # de requête.
    source = demande.analyse or {}
    montant = demande.montant_tnd if demande.montant_tnd is not None else (
        source.get("montant_tnd") or source.get("amount_tnd")
    )
    date_facture = demande.date_facture or (
        source.get("date_facture") or source.get("invoice_date")
    )
    activite = demande.activite or source.get("activite") or "menuiserie"
    aujourdhui = demande.aujourdhui or source.get("aujourdhui")

    if montant is None or date_facture is None:
        raise HTTPException(
            status_code=400,
            detail="Il faut un montant et une date de facture, soit "
                   "directement, soit dans le champ « analyse ».",
        )

    analyse = _analyser(float(montant), str(date_facture), activite, aujourdhui)

    invite = (
        "Explique la situation suivante à un chef de petite entreprise "
        "tunisienne, en français simple. Ne cite aucun article de loi.\n\n"
        + _resume_pour_modele(analyse)
    )
    if demande.question:
        invite += f"\n\nLa question posée par l'entreprise : {demande.question}"

    try:
        rep = client_llm().generer(
            invite, systeme=SYSTEME_EXPLICATION,
            max_tokens=MAX_TOKENS_EXPLICATION,
        )
    except ModeleIndisponible as exc:
        logger.info("mode dégradé : %s", exc)
        return Explication(
            texte=_explication_degradee(analyse, str(exc)),
            origine="aucune", duree_s=0.0,
            mode_degrade=True, motif_degradation=str(exc),
            analyse=analyse, sources=analyse.sources,
            avertissement=AVERTISSEMENT_SOURCES,
        )
    except Exception as exc:  # noqa: BLE001 — toute panne modèle est dégradable
        logger.warning("panne du modèle, mode dégradé : %s", exc)
        motif = f"{type(exc).__name__}: {exc}"
        return Explication(
            texte=_explication_degradee(analyse, motif),
            origine="aucune", duree_s=0.0,
            mode_degrade=True, motif_degradation=motif,
            analyse=analyse, sources=analyse.sources,
            avertissement=AVERTISSEMENT_SOURCES,
        )

    texte, purge = _purger_articles(rep.texte)
    if purge:
        logger.warning(
            "le modèle a produit une référence d'article : elle a été retirée"
        )
    return Explication(
        texte=texte, origine=rep.origine, duree_s=round(rep.duree_s, 2),
        mode_degrade=False, motif_degradation=None,
        analyse=analyse, sources=analyse.sources,
        avertissement=AVERTISSEMENT_SOURCES,
    )
