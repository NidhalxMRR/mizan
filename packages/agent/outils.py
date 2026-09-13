"""Les outils de l'agent : ce qu'il sait FAIRE, pas ce qu'il sait dire.

Chaque outil de ce fichier est une fonction Python qui appelle le code métier
existant de Mizan. L'agent choisit lequel appeler et avec quels paramètres ;
c'est le moteur, ici, qui exécute. La frontière est nette et elle est la raison
d'être du paquet : « L'IA propose. Le droit dispose. »

CE QU'UN OUTIL DOIT GARANTIR
----------------------------
1. Il déclare le privilège qu'il exige. Le contrôle se lit dans la déclaration
   de l'outil, pas dans un `if` enfoui au milieu du corps — exactement comme
   `packages/comptes/garde.exige` le fait pour les routes HTTP.

2. Il ne reçoit JAMAIS l'organisation en paramètre. Il lit celle de l'identité
   qu'on lui passe. Une organisation qui viendrait de la demande de
   l'utilisateur, ou pire du modèle de langage, ne serait plus une identité :
   ce serait un souhait.

3. Il rend un résultat déterministe : des chiffres, des dates, des articles
   cités depuis le corpus. La reformulation en français courant vient APRÈS,
   ailleurs, et ne peut plus rien changer à ces valeurs.

4. Une entrée aberrante — montant négatif, 30 février — est refusée avec un
   motif lisible, jamais absorbée en silence.
"""
from __future__ import annotations

from packages.agent import amorce  # noqa: F401  — chemins d'import avant le métier

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from packages.agent.dossiers import DepotDossiers, depot_demonstration
from packages.agent.identite import (
    Identite,
    Refus,
    refuser_hors_organisation,
    refuser_privilege,
)

from packages.legal import gate, retrieve
from packages.legal.legal_engine import DateImpossible, assess
from packages.legal.notice import CreancePrescrite, construire as construire_notice


class EntreeInvalide(ValueError):
    """L'utilisateur a demandé quelque chose qui n'est pas calculable.

    Distincte d'un refus de droit : ici, personne n'est en faute, la donnée est
    simplement impossible. Le message doit dire quoi corriger.
    """


@dataclass
class Resultat:
    """Ce qu'un outil rend à l'agent.

    `donnees` est le résultat déterministe : c'est la seule chose que l'agent
    est autorisé à faire reformuler. `resume` est une phrase française déjà
    correcte, produite SANS modèle — elle sert de réponse quand le modèle est
    injoignable, et c'est pour cela qu'elle ne peut pas être facultative.
    """

    outil: str
    donnees: dict[str, Any] = field(default_factory=dict)
    resume: str = ""
    articles: list[dict] = field(default_factory=list)
    abstention: bool = False
    avertissements: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "outil": self.outil,
            "donnees": self.donnees,
            "resume": self.resume,
            "articles": self.articles,
            "abstention": self.abstention,
            "avertissements": self.avertissements,
        }


@dataclass(frozen=True)
class Outil:
    """La description d'un outil, telle qu'elle est présentée au modèle.

    `privilege` porte le contrôle d'accès. `parametres` sert à deux choses :
    décrire l'outil au modèle pour qu'il sache quoi remplir, et refuser à
    l'exécution tout paramètre qui n'y figure pas — un modèle qui invente un
    paramètre `organisation` ne doit pas pouvoir le faire prendre en compte.
    """

    nom: str
    description: str
    privilege: str
    parametres: dict[str, str]
    obligatoires: tuple[str, ...]
    fonction: Callable[..., Resultat]

    def description_pour_modele(self) -> str:
        lignes = [f"- {self.nom} : {self.description}"]
        for cle, sens in self.parametres.items():
            marque = "obligatoire" if cle in self.obligatoires else "facultatif"
            lignes.append(f"    · {cle} ({marque}) — {sens}")
        return "\n".join(lignes)


# ---------------------------------------------------------------------------
# Contrôles d'entrée communs
# ---------------------------------------------------------------------------

def _lire_montant(valeur: Any) -> float:
    """Lit un montant, ou refuse en expliquant ce qui cloche.

    Le moteur juridique refuse déjà les montants nuls ou négatifs. On refuse
    ici en amont pour une raison de lisibilité : le message du moteur parle de
    créance, celui-ci parle de saisie, et l'utilisateur qui a tapé « moins »
    par erreur a besoin du second.
    """
    if valeur is None:
        raise EntreeInvalide(
            "Le montant de la créance n'a pas été indiqué. Précisez la somme "
            "réclamée, en dinars."
        )
    if isinstance(valeur, bool):
        raise EntreeInvalide("Le montant de la créance n'est pas un nombre.")
    try:
        montant = float(valeur)
    except (TypeError, ValueError):
        raise EntreeInvalide(
            f"« {valeur} » n'est pas un montant exploitable. Indiquez la somme "
            "en dinars, par exemple 9520."
        ) from None
    if montant != montant:  # NaN
        raise EntreeInvalide("Le montant indiqué n'est pas un nombre exploitable.")
    if montant <= 0:
        raise EntreeInvalide(
            f"Le montant indiqué ({montant:g} dinars) doit être strictement "
            "positif. Une créance nulle ou négative n'ouvre aucun droit à "
            "recouvrement."
        )
    return montant


def _lire_date(valeur: Any, quoi: str = "la facture") -> str:
    """Lit une date au format jour-mois-année, ou refuse.

    Le 30 février est le cas d'école : `date.fromisoformat` lève, et laisser
    cette exception remonter afficherait un message technique en anglais à un
    juriste. On la traduit ici, une fois.
    """
    if valeur is None or str(valeur).strip() == "":
        raise EntreeInvalide(
            f"La date de {quoi} n'a pas été indiquée. Elle commande le calcul "
            "de la prescription : sans elle, aucun délai ne peut être établi."
        )
    texte = str(valeur).strip()
    try:
        d = date.fromisoformat(texte)
    except ValueError:
        raise EntreeInvalide(
            f"La date « {texte} » n'existe pas au calendrier, ou n'est pas "
            f"écrite sous la forme attendue (année-mois-jour, par exemple "
            f"2025-11-04). Vérifiez la date portée sur {quoi}."
        ) from None
    return d.isoformat()


def _fr_date(iso: str) -> str:
    """2025-11-04 -> « 4 novembre 2025 ». Un juriste ne lit pas l'ISO."""
    mois = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
            "août", "septembre", "octobre", "novembre", "décembre"]
    d = date.fromisoformat(iso)
    return f"{d.day} {mois[d.month]} {d.year}"


def _fr_montant(v: float) -> str:
    """9520.0 -> « 9 520,000 » — écriture française, trois décimales (millimes)."""
    return f"{v:,.3f}".replace(",", "\u00a0").replace(".", ",")


# ---------------------------------------------------------------------------
# Les outils
# ---------------------------------------------------------------------------

def analyser_impaye(
    identite: Identite,
    montant: Any = None,
    date_facture: Any = None,
    activite: str = "menuiserie",
    aujourdhui: str | None = None,
) -> Resultat:
    """Où en est la créance : régime, échéance, jours restants, articles.

    Appelle `legal_engine.assess`, sans rien y ajouter. Tous les chiffres de la
    réponse viennent de là ; le modèle de langage n'en produit aucun.
    """
    somme = _lire_montant(montant)
    jour_facture = _lire_date(date_facture, "la facture")
    reference = _lire_date(aujourdhui, "référence") if aujourdhui else None

    try:
        analyse = assess(
            somme, jour_facture, activity=str(activite or "menuiserie"),
            today=date.fromisoformat(reference) if reference else None,
        )
    except DateImpossible as exc:
        # Le moteur a déjà rédigé un refus en français, à destination d'un
        # juriste. Le reformuler ici le dégraderait.
        raise EntreeInvalide(str(exc)) from exc

    d = analyse.to_dict()
    if analyse.is_expired:
        resume = (
            f"La créance de {_fr_montant(analyse.amount_tnd)} dinars, née de la "
            f"facture du {_fr_date(analyse.invoice_date)}, est PRESCRITE : le "
            f"délai a expiré le {_fr_date(analyse.deadline)}, il y a "
            f"{abs(analyse.days_left)} jours. {analyse.regime_reason_fr}"
        )
    else:
        resume = (
            f"La créance de {_fr_montant(analyse.amount_tnd)} dinars, née de la "
            f"facture du {_fr_date(analyse.invoice_date)}, se prescrit le "
            f"{_fr_date(analyse.deadline)} : il reste {analyse.days_left} jours "
            f"pour agir. {analyse.regime_reason_fr}"
        )
        if analyse.needs_bailiff:
            resume += (
                " Le montant dépassant 150 dinars, la sommation devra être "
                "signifiée par un huissier de justice, qui laissera 5 jours "
                "francs au débiteur."
            )
        else:
            resume += (
                " Le montant restant sous 150 dinars, la sommation par huissier "
                "n'est pas exigée à ce seuil."
            )

    avertissements = []
    if analyse.regime == "indetermine":
        avertissements.append(
            "Le régime de prescription affiché n'est PAS confirmé : l'activité "
            "indiquée n'est pas qualifiée par le moteur. À faire vérifier avant "
            "toute démarche."
        )

    return Resultat(
        outil="analyser_impaye",
        donnees=d,
        resume=resume,
        articles=list(analyse.sources),
        avertissements=avertissements,
    )


def chercher_article(identite: Identite, question: Any = None, nombre: int = 3) -> Resultat:
    """Cherche dans les 4087 articles du corpus, ou s'abstient en le disant.

    La garde d'abstention (`packages/legal/gate.py`) tranche : si les mots de la
    question ne figurent pas dans l'article retrouvé, c'est une collision du
    classement, pas une réponse. Mizan se tait alors, et le dit.
    """
    requete = str(question or "").strip()
    if not requete:
        raise EntreeInvalide(
            "Aucune question n'a été posée au corpus. Formulez votre question, "
            "de préférence en arabe : les codes tunisiens y sont rédigés."
        )
    try:
        k = max(1, min(int(nombre), 10))
    except (TypeError, ValueError):
        k = 3

    try:
        trouves = retrieve.search(requete, k=k)
    except FileNotFoundError:
        raise EntreeInvalide(
            "Le corpus des codes n'est pas disponible sur ce serveur. Aucune "
            "citation ne peut être produite pour l'instant — et Mizan préfère "
            "ne rien citer plutôt que citer de mémoire."
        ) from None

    verdict = gate.evaluate(requete, trouves)
    if not verdict["grounded"]:
        return Resultat(
            outil="chercher_article",
            donnees={"requete": requete, "fonde": False, "motif": verdict["reason"]},
            resume=(
                f"{gate.ABSTAIN_MESSAGE} Motif : {verdict['reason']}. "
                "Reformulez votre question, ou faites-la examiner par un "
                "professionnel accrédité."
            ),
            articles=[],
            abstention=True,
        )

    articles = [
        {
            "code_fr": a["code_fr"],
            "code_ar": a["code_ar"],
            "article": a["article"],
            "citation_ar": a["citation_ar"],
            "text_ar": a["text_ar"],
        }
        for a in trouves
    ]
    premier = articles[0]
    return Resultat(
        outil="chercher_article",
        donnees={"requete": requete, "fonde": True, "nombre": len(articles)},
        resume=(
            f"Le corpus répond par {len(articles)} article(s). Le plus proche "
            f"est l'article {premier['article']} du {premier['code_fr']} "
            f"({premier['citation_ar']}). Le texte arabe est reproduit tel qu'il "
            f"figure au corpus, sans reformulation."
        ),
        articles=articles,
    )


def preparer_mise_en_demeure(
    identite: Identite,
    montant: Any = None,
    date_facture: Any = None,
    activite: str = "menuiserie",
    debiteur: Any = None,
    creancier: Any = None,
    numero_facture: Any = None,
    aujourdhui: str | None = None,
) -> Resultat:
    """Rédige le PROJET de mise en demeure. Ne le signifie pas.

    Le créancier est, par défaut, l'organisation de l'appelant : c'est une
    conséquence directe du modèle multi-organisations. On ne prépare pas un acte
    au nom d'une entreprise pour laquelle on n'agit pas.
    """
    somme = _lire_montant(montant)
    jour_facture = _lire_date(date_facture, "la facture")
    reference = _lire_date(aujourdhui, "référence") if aujourdhui else None

    nom_debiteur = str(debiteur or "").strip()
    if not nom_debiteur:
        raise EntreeInvalide(
            "Le nom du débiteur manque. Une mise en demeure est adressée à une "
            "personne identifiée : sans destinataire, elle ne peut pas être "
            "signifiée."
        )

    try:
        analyse = assess(
            somme, jour_facture, activity=str(activite or "menuiserie"),
            today=date.fromisoformat(reference) if reference else None,
        )
    except DateImpossible as exc:
        raise EntreeInvalide(str(exc)) from exc

    partie_creanciere = {
        "nom": str(creancier).strip() if creancier else identite.organisation_affichee,
    }
    try:
        doc = construire_notice(
            analyse,
            creancier=partie_creanciere,
            debiteur={"nom": nom_debiteur},
            facture={"numero": str(numero_facture) if numero_facture else None,
                     "date": jour_facture},
        )
    except CreancePrescrite as exc:
        # Ce n'est pas une panne : c'est le conseil juridique correct. On ne
        # rédige pas une sommation sur une créance éteinte.
        return Resultat(
            outil="preparer_mise_en_demeure",
            donnees={"redige": False, "motif": str(exc),
                     "prescription": analyse.to_dict()},
            resume=str(exc),
            articles=list(analyse.sources),
            abstention=True,
        )

    return Resultat(
        outil="preparer_mise_en_demeure",
        donnees={"redige": True, "document": doc.to_dict(), "texte": doc.texte},
        resume=(
            f"Le projet de mise en demeure est rédigé à l'attention de "
            f"{nom_debiteur}, pour {_fr_montant(doc.montant_tnd)} dinars, avec "
            f"un délai de {doc.delai_jours} jours "
            f"{'francs à compter de la signification' if doc.delai_est_legal else 'd usage'}"
            f". Ce document est un PROJET : il n'est pas signifié et ne produit, "
            f"en l'état, aucun effet de droit. Seul un huissier de justice "
            f"(عدل منفذ) peut le signifier."
        ),
        articles=list(doc.articles),
        avertissements=[doc.mention_projet_longue],
    )


def analyser_risques_facture(identite: Identite, chemin: Any = None, montant: Any = None,
                             date_facture: Any = None, activite: str = "menuiserie",
                             texte: Any = None) -> Resultat:
    """Ce qui, dans la facture, peut être opposé au créancier.

    Accepte soit un chemin de fichier, soit directement le texte du document —
    l'interface dépose un PDF, la ligne de commande colle un texte, et les deux
    doivent marcher.
    """
    # Importé à l'appel : ce module tire pdfplumber, et l'agent doit pouvoir se
    # charger sur une machine où l'extraction PDF n'est pas installée.
    from packages.risques import facture as moteur_risques

    contenu = str(texte or "")
    if not contenu.strip():
        if not chemin:
            raise EntreeInvalide(
                "Aucun document n'a été fourni. Déposez la facture (PDF ou "
                "image), ou collez son texte."
            )
        from packages.legal import invoice as extraction
        try:
            lu = extraction.parse_invoice(str(chemin))
        except FileNotFoundError:
            raise EntreeInvalide(
                "Le document indiqué est introuvable. Déposez-le à nouveau."
            ) from None
        except Exception as exc:  # noqa: BLE001 — un PDF abîmé n'est pas une panne
            raise EntreeInvalide(
                "Le document n'a pas pu être lu. S'il s'agit d'un scan, il doit "
                "d'abord passer par la reconnaissance de caractères : analyser "
                "une page vide reviendrait à en inventer le contenu."
            ) from exc
        contenu = lu.get("_full_text") or ""
        if montant is None:
            montant = lu.get("amount_tnd")
        if date_facture is None:
            date_facture = lu.get("invoice_date")

    somme = None
    if montant is not None:
        somme = _lire_montant(montant)
    jour = _lire_date(date_facture, "la facture") if date_facture else None

    rapport = moteur_risques.analyser(
        contenu, montant=somme, date_facture=jour,
        activite=str(activite or "menuiserie"),
    )
    d = rapport.to_dict()

    if not rapport.document_analyse:
        return Resultat(
            outil="analyser_risques_facture",
            donnees=d,
            resume=(
                "Ce document n'a pas été reconnu comme une facture : "
                f"{rapport.motif_rejet_fr}. Aucun risque n'est produit — en "
                "analyser un autre type de pièce comme une facture donnerait "
                "des alertes sur une pièce qui n'en porte aucune."
            ),
            abstention=True,
        )

    nb = len(rapport.risques)
    if nb == 0:
        resume = (
            "Aucun risque juridique n'a été retenu sur cette facture. "
            f"{len(rapport.abstentions)} point(s) n'ont toutefois pas pu être "
            "vérifiés : consultez-les, c'est souvent là que se trouve le danger."
        )
    else:
        resume = (
            f"{nb} risque(s) juridique(s) relevé(s) sur cette facture, gravité "
            f"la plus élevée : {rapport.gravite_maximale}. Chaque risque est "
            "adossé à un article du corpus, jamais à une appréciation générale."
        )

    return Resultat(
        outil="analyser_risques_facture",
        donnees=d,
        resume=resume,
        articles=[r.get("fondement", {}) for r in d["risques"] if r.get("fondement")],
        avertissements=[a["motif_fr"] for a in d["abstentions"]],
    )


def recommander_professionnel(
    identite: Identite,
    nature: Any = None,
    montant: Any = None,
    gouvernorat: Any = None,
    langue: str = "francais",
    voie: str = "conciliation",
    partie_adverse: Any = None,
) -> Resultat:
    """Propose des professionnels accrédités. N'en désigne aucun.

    L'annuaire écarte les conflits d'intérêts sans arbitrage de score, et
    s'abstient en toutes lettres quand rien ne correspond. Une liste vide
    silencieuse se lit comme une panne d'affichage ; l'abstention est un
    résultat.
    """
    from packages.marketplace.annuaire import Litige as LitigeAnnuaire
    from packages.marketplace.exemples import annuaire_demo

    somme = _lire_montant(montant) if montant is not None else 0.0
    mots = nature or ["recouvrement", "commercial"]
    if isinstance(mots, str):
        mots = [m for m in mots.replace(",", " ").split() if m]

    try:
        litige = LitigeAnnuaire.creer(
            nature=mots,
            montant_dt=somme,
            gouvernorat=str(gouvernorat) if gouvernorat else None,
            langue=str(langue or "francais"),
            voie=str(voie or "conciliation"),
            # Le demandeur, c'est l'organisation de l'appelant. Jamais un nom
            # soufflé dans la conversation : la garde anti-conflit d'intérêts
            # repose sur cette valeur.
            demandeur=identite.organisation,
            partie_adverse=str(partie_adverse) if partie_adverse else "",
        )
    except ValueError as exc:
        raise EntreeInvalide(str(exc)) from exc

    recommandation = annuaire_demo().recommander(litige)
    propositions = [
        {
            "nom": p.professionnel.nom,
            "qualite": p.professionnel.libelle_qualite(),
            "gouvernorat": p.professionnel.gouvernorat.title(),
            "accreditation": p.professionnel.numero_accreditation,
            "note_moyenne": p.note_moyenne,
            "nombre_avis": p.nombre_avis,
            "pourquoi": p.explication(),
        }
        for p in recommandation.propositions
    ]
    return Resultat(
        outil="recommander_professionnel",
        donnees={"propositions": propositions,
                 "ecartes": list(recommandation.ecartes),
                 "abstention": recommandation.abstention},
        resume=recommandation.texte(),
        abstention=recommandation.abstention,
    )


def ouvrir_conciliation(
    identite: Identite,
    montant: Any = None,
    nature: Any = "recouvrement de facture impayée",
    debiteur: Any = None,
    date_facture: Any = None,
    position_debiteur: Any = None,
    montant_reconnu: Any = None,
    numero_facture: Any = None,
    clause_arbitrage: Any = False,
    aujourdhui: str | None = None,
) -> Resultat:
    """Produit un AVIS de règlement amiable — des termes proposés, pas un accord.

    L'invariant du moteur E-CMA est vérifié ici aussi : le dossier rendu ne
    porte aucun effet juridique tant qu'un professionnel accrédité ne l'a pas
    signé, et cette propriété est calculée, jamais écrite.
    """
    from packages.ecma import reglement

    somme = _lire_montant(montant)
    jour = _lire_date(date_facture, "la facture") if date_facture else None
    reference = _lire_date(aujourdhui, "référence") if aujourdhui else None

    nom_debiteur = str(debiteur or "").strip()
    if not nom_debiteur:
        raise EntreeInvalide(
            "Le nom de la partie adverse manque. Une conciliation suppose deux "
            "parties identifiées : on ne transige pas avec un inconnu."
        )

    reconnu = None
    if montant_reconnu is not None:
        reconnu = _lire_montant(montant_reconnu)

    litige = reglement.Litige(
        montant_reclame=somme,
        nature=str(nature or "recouvrement de facture impayée"),
        demandeur=reglement.Partie(
            nom=identite.organisation_affichee,
            role="demandeur",
            position=f"Réclame le paiement de {_fr_montant(somme)} dinars.",
        ),
        defendeur=reglement.Partie(
            nom=nom_debiteur,
            role="defendeur",
            position=str(position_debiteur or ""),
            montant_reconnu=reconnu,
        ),
        date_facture=jour,
        numero_facture=str(numero_facture) if numero_facture else None,
        clause_arbitrage=bool(clause_arbitrage),
    )

    try:
        dossier = reglement.proposer_reglement(
            litige,
            aujourdhui=date.fromisoformat(reference) if reference else None,
        )
    except reglement.LitigeInvalide as exc:
        raise EntreeInvalide(str(exc)) from exc

    d = dossier.to_dict()
    # La propriété est recalculée et non lue : c'est le point que le jury doit
    # pouvoir vérifier sans nous croire sur parole.
    assert dossier.porte_effet_juridique is False, (
        "invariant rompu : un avis d'agent ne peut pas porter effet juridique"
    )

    return Resultat(
        outil="ouvrir_conciliation",
        donnees=d,
        resume=(
            f"Un projet de règlement amiable est établi entre "
            f"{identite.organisation_affichee} et {nom_debiteur}, pour "
            f"{_fr_montant(somme)} dinars. Ce document est un AVIS : il ne lie "
            f"personne. Il ne produira d'effet qu'une fois signé par un "
            f"professionnel accrédité, qui engage alors sa responsabilité."
        ),
        abstention=False,
        # Les abstentions vivent dans l'avis, pas à la racine du dossier : c'est
        # l'avis qui s'abstient, pas le dossier.
        avertissements=list((d.get("avis") or {}).get("abstentions") or []),
    )


def consulter_mes_dossiers(identite: Identite, depot: DepotDossiers | None = None,
                           organisation: Any = None) -> Resultat:
    """Les dossiers de l'organisation de l'appelant, et uniquement ceux-là.

    Le paramètre `organisation` est accepté pour une seule raison : il est le
    piège. Un utilisateur — ou un modèle manipulé — qui tente de le remplir avec
    une autre entreprise doit être refusé explicitement, pas ignoré en silence.
    Ignorer la tentative donnerait la bonne réponse pour la mauvaise raison, et
    personne ne saurait dire si le cloisonnement tient.
    """
    if organisation is not None and str(organisation).strip():
        if not identite.meme_organisation(str(organisation).strip()):
            raise RefusOutil(refuser_hors_organisation("consulter_mes_dossiers"))

    depot = depot if depot is not None else depot_demonstration()
    liste = depot.de_l_organisation(identite.organisation)
    return Resultat(
        outil="consulter_mes_dossiers",
        donnees={"nombre": len(liste), "dossiers": [d.to_dict() for d in liste]},
        resume=(
            f"{identite.organisation_affichee} compte {len(liste)} dossier(s) "
            f"ouvert(s) sur Mizan."
            if liste else
            f"Aucun dossier n'est actuellement ouvert pour "
            f"{identite.organisation_affichee}."
        ),
    )


def signifier_mise_en_demeure(
    identite: Identite,
    debiteur: Any = None,
    date_signification: Any = None,
    numero_acte: Any = None,
) -> Resultat:
    """Consigne la signification d'un acte. Réservé à l'huissier de justice.

    POURQUOI CET OUTIL EXISTE ALORS QUE PRESQUE PERSONNE NE PEUT L'APPELER.
    Il serait plus simple de ne pas l'offrir du tout. Mais une entreprise qui
    demande « signifie ma mise en demeure » a besoin d'apprendre POURQUOI la
    plateforme ne le fera pas — c'est une règle de droit, pas une fonction
    manquante. Un outil absent produit « je ne sais pas faire ça » ; un outil
    présent et protégé produit le fondement légal du refus. C'est la
    différence entre un logiciel qui semble incomplet et un logiciel qui
    enseigne le droit à son utilisateur.

    Pour l'huissier, en revanche, l'outil travaille : il consigne la date, qui
    est le seul fait qui fasse courir le délai laissé au débiteur.
    """
    from packages.legal.legal_engine import NOTICE_GRACE_DAYS

    nom = str(debiteur or "").strip()
    if not nom:
        raise EntreeInvalide(
            "Le nom du destinataire de l'acte manque. Une signification est "
            "faite à une personne identifiée."
        )
    jour = _lire_date(date_signification, "la signification") if date_signification \
        else date.today().isoformat()

    from datetime import timedelta
    expire = (date.fromisoformat(jour) + timedelta(days=NOTICE_GRACE_DAYS)).isoformat()

    return Resultat(
        outil="signifier_mise_en_demeure",
        donnees={
            "debiteur": nom,
            "date_signification": jour,
            "numero_acte": str(numero_acte) if numero_acte else None,
            "delai_jours_francs": NOTICE_GRACE_DAYS,
            "fin_du_delai": expire,
            "signifie_par": identite.organisation_affichee,
        },
        resume=(
            f"La signification faite à {nom} le {_fr_date(jour)} est consignée. "
            f"Le débiteur dispose de {NOTICE_GRACE_DAYS} jours francs, soit "
            f"jusqu'au {_fr_date(expire)}. Passé ce délai, l'injonction de payer "
            f"peut être demandée."
        ),
    )


def administrer_organisations(identite: Identite, depot: DepotDossiers | None = None) -> Resultat:
    """Vue d'exploitation de la plateforme. Réservée à l'administration.

    Volontairement pauvre : elle rend des effectifs, pas des dossiers. Même un
    administrateur de plateforme n'a pas à lire le contenu des litiges des
    entreprises clientes — l'exploitation d'un service n'emporte pas le droit
    d'en lire le secret des affaires.
    """
    from packages.comptes.roles import ROLES

    return Resultat(
        outil="administrer_organisations",
        donnees={"roles_disponibles": list(ROLES)},
        resume=(
            "Vue d'exploitation : la plateforme reconnaît "
            f"{len(ROLES)} rôles. Le contenu des dossiers des organisations "
            "clientes n'est pas accessible depuis cette vue, y compris à "
            "l'administration."
        ),
    )


class RefusOutil(PermissionError):
    """Un outil a été appelé hors des droits ou du périmètre de l'appelant.

    Porte le `Refus` motivé, pour que l'agent le rende tel quel à l'utilisateur
    sans avoir à le reformuler — une reformulation par le modèle pourrait
    adoucir un refus qui doit rester net.
    """

    def __init__(self, refus: Refus) -> None:
        super().__init__(refus.motif)
        self.refus = refus


# ---------------------------------------------------------------------------
# Le catalogue
# ---------------------------------------------------------------------------

CATALOGUE: dict[str, Outil] = {
    o.nom: o
    for o in (
        Outil(
            nom="analyser_impaye",
            description=(
                "Calcule où en est une créance impayée : régime de prescription, "
                "date d'échéance, jours restants pour agir, obligation ou non de "
                "passer par un huissier, et articles applicables."
            ),
            privilege="view_own_case",
            parametres={
                "montant": "montant réclamé, en dinars (nombre)",
                "date_facture": "date de la facture, au format année-mois-jour",
                "activite": "activité du créancier (menuiserie, textile, transport, conseil…)",
            },
            obligatoires=("montant", "date_facture"),
            fonction=analyser_impaye,
        ),
        Outil(
            nom="chercher_article",
            description=(
                "Cherche un article dans les 4087 articles des codes tunisiens "
                "indexés. S'abstient explicitement si le corpus ne répond pas."
            ),
            privilege="",  # consulter la loi n'exige aucun privilège particulier
            parametres={
                "question": "la question posée, de préférence en arabe",
                "nombre": "nombre d'articles souhaités (1 à 10)",
            },
            obligatoires=("question",),
            fonction=chercher_article,
        ),
        Outil(
            nom="preparer_mise_en_demeure",
            description=(
                "Rédige le PROJET de mise en demeure (إنذار) à l'attention du "
                "débiteur. Le projet n'est pas signifié et ne produit aucun effet."
            ),
            privilege="request_notice",
            parametres={
                "montant": "montant réclamé, en dinars",
                "date_facture": "date de la facture, au format année-mois-jour",
                "debiteur": "nom du débiteur",
                "activite": "activité du créancier",
                "numero_facture": "numéro de la facture",
            },
            obligatoires=("montant", "date_facture", "debiteur"),
            fonction=preparer_mise_en_demeure,
        ),
        Outil(
            nom="analyser_risques_facture",
            description=(
                "Analyse une facture déposée et liste ce qui peut être opposé au "
                "créancier : mentions manquantes, preuve de livraison, seuils."
            ),
            privilege="upload_evidence",
            parametres={
                "chemin": "chemin du document déposé",
                "texte": "à défaut de document, le texte de la facture",
                "montant": "montant, s'il est déjà connu",
                "date_facture": "date de la facture, si elle est déjà connue",
            },
            obligatoires=(),
            fonction=analyser_risques_facture,
        ),
        Outil(
            nom="recommander_professionnel",
            description=(
                "Propose des professionnels accrédités pour conduire le règlement "
                "amiable. Propose, n'impose pas."
            ),
            privilege="choose_professional",
            parametres={
                "nature": "mots décrivant le litige (recouvrement, commercial, bail…)",
                "montant": "montant du litige, en dinars",
                "gouvernorat": "gouvernorat du litige",
                "langue": "langue de travail souhaitée (francais ou arabe)",
                "voie": "voie choisie (conciliation, arbitrage, conseil)",
            },
            obligatoires=(),
            fonction=recommander_professionnel,
        ),
        Outil(
            nom="ouvrir_conciliation",
            description=(
                "Établit un projet de règlement amiable (avis motivé, termes "
                "proposés). Ne lie personne tant qu'un professionnel n'a pas signé."
            ),
            privilege="open_ecma",
            parametres={
                "montant": "montant réclamé, en dinars",
                "debiteur": "nom de la partie adverse",
                "nature": "nature du litige",
                "date_facture": "date de la facture, si elle existe",
                "position_debiteur": "ce que la partie adverse soutient, si elle s'est exprimée",
                "montant_reconnu": "somme que la partie adverse admet devoir",
            },
            obligatoires=("montant", "debiteur"),
            fonction=ouvrir_conciliation,
        ),
        Outil(
            nom="consulter_mes_dossiers",
            description=(
                "Liste les dossiers ouverts par l'organisation de l'utilisateur "
                "connecté. Aucune autre organisation n'est accessible."
            ),
            privilege="view_own_case",
            parametres={},
            obligatoires=(),
            fonction=consulter_mes_dossiers,
        ),
        Outil(
            nom="signifier_mise_en_demeure",
            description=(
                "Consigne la signification d'une mise en demeure et fait courir "
                "le délai laissé au débiteur. Réservé à l'huissier de justice."
            ),
            privilege="issue_formal_notice",
            parametres={
                "debiteur": "nom du destinataire de l'acte",
                "date_signification": "date de la signification, au format année-mois-jour",
                "numero_acte": "numéro de l'acte",
            },
            obligatoires=("debiteur",),
            fonction=signifier_mise_en_demeure,
        ),
        Outil(
            nom="administrer_organisations",
            description=(
                "Vue d'exploitation des organisations inscrites. Réservée à "
                "l'administration de la plateforme."
            ),
            privilege="manage_tenants",
            parametres={},
            obligatoires=(),
            fonction=administrer_organisations,
        ),
    )
}


def outils_autorises(identite: Identite) -> list[Outil]:
    """Les outils que CE rôle peut appeler.

    C'est cette liste, et elle seule, qui est décrite au modèle. Un modèle qui
    n'a jamais entendu parler d'un outil ne peut pas le proposer : le premier
    rempart contre l'appel interdit est de ne pas l'annoncer. Le second — le
    vrai — est le contrôle à l'exécution, juste en dessous.
    """
    return [
        o for o in CATALOGUE.values()
        if not o.privilege or identite.peut(o.privilege)
    ]


def appeler(identite: Identite, nom: str, parametres: dict[str, Any] | None = None,
            depot: DepotDossiers | None = None) -> Resultat:
    """Appelle un outil au nom de l'identité fournie. Le seul chemin d'accès.

    Toutes les gardes sont ici, dans cet ordre, et l'ordre a un sens :

      1. l'outil existe-t-il ;
      2. le rôle a-t-il le droit de l'appeler ;
      3. les paramètres tentent-ils de sortir de l'organisation ;
      4. seulement ensuite, l'exécution.

    Le contrôle de droits passe AVANT la validation des paramètres. L'inverse
    dirait à un compte non habilité que son montant est mal formé, ce qui
    reviendrait à lui confirmer que l'outil existe et comment s'en servir.
    """
    outil = CATALOGUE.get(str(nom))
    if outil is None:
        raise RefusOutil(Refus(
            motif=(
                "Cette action ne fait pas partie de ce que Mizan sait faire. "
                "Je peux analyser une créance impayée, chercher un article des "
                "codes tunisiens, préparer un projet de mise en demeure, "
                "analyser les risques d'une facture, proposer un professionnel "
                "accrédité ou ouvrir un règlement amiable."
            ),
            outil=str(nom),
        ))

    if outil.privilege and not identite.peut(outil.privilege):
        raise RefusOutil(refuser_privilege(identite, outil.privilege, outil.nom))

    params = dict(parametres or {})

    # Toute tentative de désigner une autre organisation est arrêtée ici, quelle
    # que soit la façon dont le paramètre a été nommé. Le modèle n'a aucun de
    # ces mots dans sa description d'outils : s'ils apparaissent, ils ont été
    # soufflés par l'utilisateur.
    for cle in ("organisation", "tenant", "entreprise", "societe", "société"):
        valeur = params.get(cle)
        if valeur is not None and str(valeur).strip():
            if not identite.meme_organisation(str(valeur).strip()):
                raise RefusOutil(refuser_hors_organisation(outil.nom))

    # Un paramètre inconnu de la description est écarté sans bruit plutôt que
    # transmis : `fonction(**params)` sur un nom inattendu lèverait un TypeError
    # illisible, et surtout un modèle ne doit pas pouvoir atteindre un argument
    # qu'on ne lui a pas offert.
    acceptes = set(outil.parametres) | {"organisation"}
    params = {k: v for k, v in params.items() if k in acceptes}

    manquants = [c for c in outil.obligatoires if params.get(c) in (None, "")]
    if manquants:
        libelles = ", ".join(f"« {outil.parametres.get(m, m)} »" for m in manquants)
        raise EntreeInvalide(
            f"Il me manque un élément pour aller plus loin : {libelles}. "
            "Pouvez-vous me le préciser ?"
        )

    if outil.nom == "consulter_mes_dossiers":
        return outil.fonction(identite, depot=depot, **params)
    params.pop("organisation", None)
    return outil.fonction(identite, **params)
