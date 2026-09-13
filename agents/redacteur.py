"""Agent 3 — RÉDACTEUR.

Il explique à une PME, en français simple, ce que disent les faits et le
droit rapportés par les agents 1 et 2. Il ne cherche rien lui-même.

La règle absolue : aucune citation hors liste blanche
-----------------------------------------------------
L'agent 3 est le seul maillon qui parle à un modèle de langage, donc le seul
qui puisse inventer un article. Lui demander gentiment de ne citer que la
liste fournie ne suffit pas — une consigne n'est pas une garantie.

Le contrôle est donc STRUCTUREL et appliqué APRÈS génération :

  1. On extrait par expression régulière tout numéro d'article présent dans
     le texte produit (« article 403 », « art. 59 », « COC 403 », « الفصل 60 »).
  2. Tout numéro absent de la liste blanche de l'agent 2 est une violation.
  3. À la première violation, LE TEXTE DU MODÈLE EST JETÉ EN ENTIER et la
     version déterministe prend sa place.

On ne corrige pas, on ne masque pas le numéro fautif : un texte qui cite un
article inexistant est un texte dont on ne peut plus rien garantir, y compris
les phrases qui l'entourent. Le remplacer intégralement est la seule réponse
qui laisse une propriété vérifiable.

`verification['viole']` et `articles_hors_liste` exposent ce verdict : la
chaîne reste honnête sur ce qui s'est passé, et le test peut l'exiger.

Sans modèle, l'application reste utilisable
--------------------------------------------
La version déterministe n'est pas un mode dégradé honteux : elle dit le même
droit, avec les mêmes citations, dans une prose fixe. On perd la
reformulation, jamais le fond. C'est ce qui permet de démontrer Mizan sur une
machine hors-ligne.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, asdict, replace

from agents import amorce  # noqa: F401

from packages.models.client import ClientLLM, ModeleIndisponible

NOM = "redacteur"

# Le client LLM vise 20 s, calibré pour une réponse courte. Une explication
# juridique de 280 mots, précédée d'une invite qui contient le texte arabe de
# huit articles, ne tient pas dans ce budget : mesuré à 21,6 tok/s sur le
# qwen2.5:7b local, la seule génération demande une trentaine de secondes.
# Avec 20 s, le modèle est TOUJOURS coupé et la chaîne retombe en déterministe
# sans que rien ne soit cassé — on ne verrait jamais le modèle travailler.
# Le délai est donc relevé ici, côté appelant, sans toucher au client partagé.
DELAI_REDACTION_S = float(os.getenv("MIZAN_REDACTION_DELAI", "90"))


def _client_redaction() -> ClientLLM:
    """Un client identique à celui par défaut, mais patient."""
    base = ClientLLM()
    base.hebergements = [
        replace(h, delai_s=max(h.delai_s, DELAI_REDACTION_S))
        for h in base.hebergements
    ]
    return base

# --- Détection des citations d'articles -------------------------------------
# Couvre les formes françaises et arabes. Le but n'est pas d'être élégant mais
# de n'en laisser passer AUCUNE : une regex trop étroite rendrait la garantie
# creuse.
MOTIFS_ARTICLE = [
    re.compile(r"(?:articles?|art\.?)\s*(?:n[°o]\s*)?(\d{1,4})", re.I),
    re.compile(r"\b(?:COC|CPCC|CPC|C\.O\.C\.?)\s*(?:art\.?|article)?\s*(\d{1,4})", re.I),
    re.compile(r"الفصل\s*(\d{1,4})"),
    # « 403 du code des obligations » : le numéro précède la référence au code.
    re.compile(r"\b(\d{1,4})\s*(?:du|de la)\s+(?:code|mjalla|majalla)", re.I),
]


def numeros_cites(texte: str) -> set:
    """Tous les numéros d'articles apparaissant dans un texte.

    C'est la fonction que le test utilise pour prouver la propriété, donc
    elle est publique et volontairement simple à relire.
    """
    trouves = set()
    for rx in MOTIFS_ARTICLE:
        for m in rx.finditer(texte or ""):
            trouves.add(m.group(1).lstrip("0") or m.group(1))
    return trouves


# --- Détection du CODE attribué à un article --------------------------------
# Un numéro juste dans le mauvais code reste une erreur de droit. Le modèle a
# écrit « Code des Obligations et des Contrats, article 60 » alors que le 60
# est au Code de procédure civile : le numéro figurait bien dans la liste
# blanche, donc le contrôle par numéro seul laissait passer la faute. Vu par
# un magistrat, cette phrase décrédibilise tout le reste.
_NOMS_DE_CODE = [
    ("coc", re.compile(
        r"code\s+des\s+obligations|COC\b|مجلة\s+الالتزامات", re.I)),
    ("procciv", re.compile(
        r"code\s+de\s+proc[ée]dure\s+civile|CPCC?\b|مجلة\s+المرافعات", re.I)),
    ("commerce", re.compile(
        r"code\s+de\s+commerce|مجلة\s+التجارة", re.I)),
    ("fiscal", re.compile(
        r"code\s+des\s+droits|fiscal|مجلة\s+الحقوق", re.I)),
]

# Un code nommé puis, dans les 60 caractères qui suivent, un numéro d'article.
_CODE_PUIS_ARTICLE = re.compile(
    r"(?P<code>code\s+[^,.;()]{3,60}|COC|CPCC?)"
    r"[^0-9]{0,40}?"
    r"(?:articles?|art\.?)\s*(?:n[°o]\s*)?(?P<num>\d{1,4})",
    re.I,
)


def _code_nomme(fragment: str) -> str | None:
    """Quel code ce fragment de texte désigne-t-il ?"""
    for code_id, rx in _NOMS_DE_CODE:
        if rx.search(fragment or ""):
            return code_id
    return None


def attributions_citees(texte: str) -> set:
    """Les couples (code_id, numéro) que le texte attribue explicitement.

    On ne retient que les citations où le modèle a NOMMÉ un code : un numéro
    seul n'affirme rien sur son origine et reste couvert par `numeros_cites`.
    """
    couples = set()
    for m in _CODE_PUIS_ARTICLE.finditer(texte or ""):
        code_id = _code_nomme(m.group("code"))
        if code_id:
            couples.add((code_id, m.group("num").lstrip("0") or m.group("num")))
    return couples



@dataclass
class Redaction:
    """Sortie de l'agent 3."""

    texte: str
    origine: str                  # 'local' | 'modal' | 'deterministe'
    verification: dict = field(default_factory=dict)
    articles_cites: list = field(default_factory=list)
    articles_hors_liste: list = field(default_factory=list)
    motif_repli: str | None = None
    duree_modele_s: float | None = None

    def to_dict(self):
        return asdict(self)


def _liste_blanche(articles) -> dict:
    """cle -> article, pour les articles que l'agent 2 a validés."""
    return {str(a.article): a for a in articles}


def _bloc_droit(articles) -> str:
    """Le droit disponible, tel qu'il sera montré au modèle."""
    lignes = []
    for a in articles:
        extrait = " ".join(a.text_ar.split())[:220]
        lignes.append(
            f"- {a.code_fr}, article {a.article} "
            f"(citation officielle : {a.citation_ar})\n"
            f"  Pourquoi il s'applique : {a.motif_fr}\n"
            f"  Texte arabe (extrait) : {extrait}"
        )
    return "\n".join(lignes)


SYSTEME = (
    "Tu es le rédacteur de Mizan, une plateforme tunisienne d'aide aux PME "
    "en litige commercial. Tu écris en français simple, pour un artisan qui "
    "n'a pas d'avocat. Pas de jargon, pas de formules latines.\n"
    "\n"
    "RÈGLE ABSOLUE : tu ne cites QUE les articles de la liste qui t'est "
    "fournie, en reprenant leur numéro exact. Tu n'inventes aucun autre "
    "numéro d'article, aucune autre référence, même si tu crois en connaître. "
    "Si un point te manque, tu l'écris en français sans citer d'article.\n"
    "\n"
    "Tu n'annonces jamais une issue judiciaire certaine. Tu expliques les "
    "délais, les étapes, et ce que la personne doit faire maintenant."
)


def _invite(faits, evaluation, articles) -> str:
    montant = faits.get("montant_tnd")
    return f"""Voici un dossier réel à expliquer à son titulaire.

FAITS ÉTABLIS PAR LA LECTURE DE LA FACTURE
- Créancier : {faits.get('vendeur', 'non précisé')}
- Débiteur : {faits.get('client', 'non précisé')}
- Montant réclamé : {montant} DT
- Date de la facture : {faits.get('date_facture', 'non précisée')}
- Nature de la créance : {faits.get('nature_creance', 'non précisée')}

CALCULS DU MOTEUR JURIDIQUE (déterministes, à reprendre tels quels)
- Régime de prescription retenu : {evaluation.get('regime')}
- Motif : {evaluation.get('regime_reason_fr')}
- Date limite pour agir : {evaluation.get('deadline')}
- Jours restants : {evaluation.get('days_left')}
- Mise en demeure par huissier nécessaire : {'oui' if evaluation.get('needs_bailiff') else 'non'}
- Délai laissé au débiteur après sommation : {evaluation.get('grace_days')} jours

ARTICLES DE LOI DISPONIBLES — LA SEULE LISTE QUE TU PEUX CITER
{_bloc_droit(articles)}

Rédige une explication de 200 à 280 mots, en français simple, structurée ainsi :
1. Où en est votre créance (montant, délai restant, urgence)
2. Pourquoi ce délai s'applique à votre cas
3. Ce que vous devez faire maintenant, dans l'ordre

Ne cite aucun numéro d'article absent de la liste ci-dessus."""


def _deterministe(faits, evaluation, articles) -> str:
    """La même explication, sans modèle. Prose fixe, droit identique."""
    montant = faits.get("montant_tnd")
    jours = evaluation.get("days_left")
    echeance = evaluation.get("deadline")
    urgence = evaluation.get("urgency")
    vendeur = faits.get("vendeur") or "Votre entreprise"
    client = faits.get("client") or "votre client"

    par_numero = {str(a.article): a for a in articles}

    def cite(num, defaut=""):
        """Ne cite un article que s'il est dans la liste blanche."""
        a = par_numero.get(str(num))
        return f"{a.code_fr}, article {a.article}" if a else defaut

    if urgence == "expired":
        entete = (
            f"Attention : le délai pour réclamer cette somme en justice est "
            f"dépassé depuis {abs(jours)} jours."
        )
    elif urgence == "critical":
        entete = (
            f"C'est urgent : il vous reste {jours} jours pour agir, "
            f"jusqu'au {echeance}."
        )
    elif urgence == "warning":
        entete = (
            f"Il vous reste {jours} jours pour agir, jusqu'au {echeance}. "
            f"Ne laissez pas filer ce délai."
        )
    else:
        entete = (
            f"Vous avez encore {jours} jours pour agir, jusqu'au {echeance}."
        )

    presc = cite(403) or cite(402)
    morceaux = [
        f"OÙ EN EST VOTRE CRÉANCE",
        f"{vendeur} réclame {montant} DT à {client}, au titre d'une facture "
        f"du {faits.get('date_facture', 'date non précisée')}. {entete}",
        "",
        "POURQUOI CE DÉLAI S'APPLIQUE",
        evaluation.get("regime_reason_fr", ""),
    ]
    if presc:
        morceaux.append(f"Fondement : {presc}.")

    morceaux += ["", "CE QUE VOUS DEVEZ FAIRE MAINTENANT"]
    n = 0
    for etape in evaluation.get("steps", []):
        num = str(etape.get("article"))
        if num not in par_numero:
            # Une étape dont l'article n'a pas été confirmé par l'agent 2
            # n'est pas présentée comme fondée en droit.
            continue
        n += 1
        a = par_numero[num]
        morceaux.append(
            f"{n}. {etape.get('title_fr')} — {etape.get('detail_fr')} "
            f"({a.code_fr}, article {a.article})"
        )

    if n == 0:
        morceaux.append(
            "Aucune étape n'a pu être adossée à un article vérifié du corpus. "
            "Rapprochez-vous d'un avocat ou d'un huissier de justice."
        )

    morceaux += [
        "",
        "Ce document vous informe ; il ne remplace pas l'avis d'un avocat.",
    ]
    return "\n".join(m for m in morceaux if m is not None)


def rediger(faits: dict, recherche, evaluation: dict,
            client: ClientLLM | None = None,
            utiliser_modele: bool = True) -> Redaction:
    """Rédige l'explication, puis VÉRIFIE qu'elle ne cite rien d'interdit."""
    articles = recherche.articles if hasattr(recherche, "articles") else recherche
    autorises = set(_liste_blanche(articles).keys())

    # --- Cas d'abstention : l'agent 2 n'a rien fondé ---------------------
    if not articles:
        motif = getattr(recherche, "motif_abstention", None) or (
            "Aucun article du corpus ne fonde une réponse sur ce dossier."
        )
        return Redaction(
            texte=(
                "Mizan ne peut pas répondre sur ce dossier.\n\n"
                f"{motif}\n\n"
                "Aucune référence n'est produite : la plateforme préfère se "
                "taire plutôt qu'inventer un article de loi."
            ),
            origine="deterministe",
            verification={
                "viole": False,
                "autorises": sorted(autorises),
                "cites": [],
                "controle": "abstention — aucun article à citer",
            },
        )

    texte_repli = _deterministe(faits, evaluation, articles)
    duree = None
    motif_repli = None
    origine = "deterministe"
    texte = texte_repli

    if utiliser_modele:
        cl = client or _client_redaction()
        try:
            rep = cl.generer(
                _invite(faits, evaluation, articles),
                systeme=SYSTEME,
                max_tokens=700,
            )
            duree = rep.duree_s
            candidat = (rep.texte or "").strip()

            # --- LE CONTRÔLE QUI COMPTE ------------------------------------
            cites = numeros_cites(candidat)
            hors = sorted(cites - autorises, key=lambda x: int(x))

            # Deuxième garde : le bon numéro dans le mauvais code. Observé en
            # conditions réelles — « Code des Obligations et des Contrats,
            # article 60 » alors que le 60 appartient au Code de procédure
            # civile. Le numéro étant autorisé, le premier contrôle laissait
            # passer une affirmation juridiquement fausse.
            attributions_valides = {
                (
                    a.get("code_id") if isinstance(a, dict) else a.code_id,
                    str(a.get("article") if isinstance(a, dict) else a.article),
                )
                for a in articles
            }
            mal_attribues = sorted(
                attributions_citees(candidat) - attributions_valides
            )

            if not candidat:
                motif_repli = "le modèle a renvoyé un texte vide"
            elif hors:
                # On jette TOUT le texte, pas seulement la phrase fautive.
                motif_repli = (
                    "le modèle a cité un ou plusieurs articles absents de la "
                    f"liste vérifiée ({', '.join(hors)}) : sa rédaction est "
                    "écartée en entier au profit de la version déterministe"
                )
            elif mal_attribues:
                motif_repli = (
                    "le modèle a rattaché un article au mauvais code ("
                    + ", ".join(f"{c} art. {n}" for c, n in mal_attribues)
                    + ") : le numéro existe mais l'attribution est fausse, "
                    "la rédaction est écartée en entier"
                )
            else:
                texte, origine = candidat, rep.origine


        except ModeleIndisponible as exc:
            motif_repli = f"aucun modèle disponible ({exc})"

    cites_final = sorted(numeros_cites(texte), key=lambda x: int(x))
    hors_final = [c for c in cites_final if c not in autorises]

    return Redaction(
        texte=texte,
        origine=origine,
        verification={
            "viole": bool(hors_final),
            "autorises": sorted(autorises, key=lambda x: int(x)),
            "cites": cites_final,
            "controle": "extraction par motif des numéros d'articles du texte produit",
        },
        articles_cites=cites_final,
        articles_hors_liste=hors_final,
        motif_repli=motif_repli,
        duree_modele_s=duree,
    )
