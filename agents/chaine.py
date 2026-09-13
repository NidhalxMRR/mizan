"""ORCHESTRATEUR — enchaîne lecteur → chercheur → rédacteur.

Ce que la chaîne garantit, et pourquoi elle est dans cet ordre
--------------------------------------------------------------
Chaque agent ne reçoit que la sortie du précédent. Ce n'est pas un choix de
style : c'est ce qui rend la garantie d'anti-hallucination démontrable.

  lecteur    → des FAITS, avec page et empreinte SHA-256
  chercheur  → du DROIT, récupéré du corpus et vérifié article par article
  rédacteur  → de la PROSE, dont chaque citation est contrôlée contre le droit
               rapporté par le chercheur

Le rédacteur n'a aucun accès au corpus. Il ne peut donc pas « aller chercher »
un article de plus : tout ce qu'il peut citer lui a été remis par l'agent 2,
et ce qu'il cite quand même est détecté et écarté.

Le moteur déterministe (`legal_engine`) est branché entre le 2 et le 3 : il
calcule les délais. Aucun nombre affiché à l'utilisateur ne vient du modèle.

Usage :
    ./.venv/bin/python -m agents.chaine samples/facture_ahmed.pdf
    ./.venv/bin/python -m agents.chaine samples/facture_ahmed.pdf --sans-modele
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict

from agents import amorce  # noqa: F401

from agents import chercheur, lecteur, redacteur
from packages.legal.legal_engine import DateImpossible, assess

VERSION_CHAINE = "1.0"


@dataclass
class Etape:
    """Une exécution d'agent, chronométrée."""

    agent: str
    ok: bool
    duree_s: float
    resume: str
    detail: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


@dataclass
class Resultat:
    """Le dossier traité de bout en bout, entièrement traçable."""

    ok: bool
    arret: str | None
    piece: str
    sha256: str | None
    etapes: list = field(default_factory=list)
    faits: dict = field(default_factory=dict)
    articles: list = field(default_factory=list)
    evaluation: dict = field(default_factory=dict)
    explication: str = ""
    origine_texte: str = ""
    verification: dict = field(default_factory=dict)
    duree_totale_s: float = 0.0

    def to_dict(self):
        d = asdict(self)
        d["version_chaine"] = VERSION_CHAINE
        d["etapes"] = [e.to_dict() if isinstance(e, Etape) else e
                       for e in self.etapes]
        return d


def _activite(faits: dict) -> str:
    """Déduit l'activité pour le moteur, à partir de la nature lue.

    Le moteur distingue marchandises et services. On ne lui transmet une
    activité « marchandises » que si la pièce le dit ; sinon on laisse le
    moteur appliquer son propre régime par défaut, qui est explicite sur son
    incertitude.
    """
    nature = (faits.get("nature_creance") or "").lower()
    if "marchandise" in nature:
        return "menuiserie"
    if "prestation" in nature or "service" in nature:
        return "conseil"
    return "inconnu"


def traiter(chemin, utiliser_modele: bool = True, aujourdhui=None) -> Resultat:
    """Traite un dossier de litige de bout en bout."""
    depart = time.monotonic()
    etapes: list[Etape] = []

    # ---------------------------------------------------------------- 1/3
    t = time.monotonic()
    lecture = lecteur.lire(chemin)
    d1 = time.monotonic() - t

    if not lecture.accepte:
        etapes.append(Etape(
            agent=lecteur.NOM, ok=False, duree_s=round(d1, 3),
            resume=f"pièce refusée : {lecture.motif_refus}",
            detail={"sha256": lecture.sha256, "pages": lecture.n_pages},
        ))
        return Resultat(
            ok=False,
            arret="lecteur — la pièce n'est pas une facture",
            piece=str(chemin),
            sha256=lecture.sha256,
            etapes=etapes,
            explication=(
                "Mizan n'a pas traité ce document.\n\n"
                f"Motif : {lecture.motif_refus}.\n\n"
                "Aucun montant, aucune date et aucun article de loi n'ont été "
                "produits : analyser une pièce qui n'est pas une facture "
                "reviendrait à fabriquer une créance."
            ),
            origine_texte="deterministe",
            duree_totale_s=round(time.monotonic() - depart, 3),
        )

    faits = {f.cle: f.valeur for f in lecture.faits}
    etapes.append(Etape(
        agent=lecteur.NOM, ok=True, duree_s=round(d1, 3),
        resume=f"{len(lecture.faits)} faits extraits de {lecture.n_pages} page(s) "
               f"({lecture.methode})",
        detail={
            "sha256": lecture.sha256,
            "faits": [f.to_dict() for f in lecture.faits],
        },
    ))

    # ---------------------------------------------------------------- 2/3
    t = time.monotonic()
    recherche = chercheur.chercher(faits)
    d2 = time.monotonic() - t

    if not recherche.fonde:
        etapes.append(Etape(
            agent=chercheur.NOM, ok=False, duree_s=round(d2, 3),
            resume="abstention : aucun article fondé dans le corpus",
            detail={"abstentions": recherche.abstentions},
        ))
        red = redacteur.rediger(faits, recherche, {}, utiliser_modele=False)
        return Resultat(
            ok=False,
            arret="chercheur — abstention",
            piece=str(chemin),
            sha256=lecture.sha256,
            etapes=etapes,
            faits=faits,
            explication=red.texte,
            origine_texte=red.origine,
            verification=red.verification,
            duree_totale_s=round(time.monotonic() - depart, 3),
        )

    etapes.append(Etape(
        agent=chercheur.NOM, ok=True, duree_s=round(d2, 3),
        resume=f"{len(recherche.articles)} articles vérifiés dans le corpus, "
               f"{len(recherche.abstentions)} abstention(s)",
        detail={
            "articles": [a.cle for a in recherche.articles],
            "questions": len(recherche.questions),
        },
    ))

    # ------------------------------------- moteur déterministe (délais)
    t = time.monotonic()
    try:
        evaluation = assess(
            amount_tnd=faits.get("montant_tnd"),
            invoice_date=faits.get("date_facture"),
            activity=_activite(faits),
            today=aujourdhui,
        ).to_dict()
        d_moteur = time.monotonic() - t
        etapes.append(Etape(
            agent="moteur_juridique", ok=True, duree_s=round(d_moteur, 3),
            resume=f"régime {evaluation['regime']}, "
                   f"{evaluation['days_left']} jours restants "
                   f"(urgence : {evaluation['urgency']})",
            detail={"deadline": evaluation["deadline"]},
        ))
    except (DateImpossible, TypeError, ValueError) as exc:
        d_moteur = time.monotonic() - t
        etapes.append(Etape(
            agent="moteur_juridique", ok=False, duree_s=round(d_moteur, 3),
            resume=f"calcul impossible : {exc}", detail={},
        ))
        return Resultat(
            ok=False,
            arret=f"moteur juridique — {exc}",
            piece=str(chemin),
            sha256=lecture.sha256,
            etapes=etapes,
            faits=faits,
            articles=[a.to_dict() for a in recherche.articles],
            explication=(
                "Mizan ne peut pas calculer votre délai.\n\n"
                f"{exc}\n\n"
                "Aucune échéance n'est affichée : une date fausse produirait "
                "un délai faux, et c'est l'erreur la plus coûteuse."
            ),
            origine_texte="deterministe",
            duree_totale_s=round(time.monotonic() - depart, 3),
        )

    # Les articles du moteur sont RELUS dans le corpus avant d'être citables.
    confirmes = chercheur.ancrer(evaluation.get("sources", []))
    connus = {a.cle for a in recherche.articles}
    for a in confirmes:
        if a.cle not in connus:
            recherche.articles.append(a)
            connus.add(a.cle)

    # ---------------------------------------------------------------- 3/3
    t = time.monotonic()
    red = redacteur.rediger(faits, recherche, evaluation,
                            utiliser_modele=utiliser_modele)
    d3 = time.monotonic() - t

    resume = f"{len(red.texte.split())} mots, origine « {red.origine} »"
    if red.motif_repli:
        resume += f" — repli : {red.motif_repli}"
    etapes.append(Etape(
        agent=redacteur.NOM, ok=not red.verification.get("viole", False),
        duree_s=round(d3, 3), resume=resume,
        detail={
            "verification": red.verification,
            "duree_modele_s": (round(red.duree_modele_s, 2)
                               if red.duree_modele_s else None),
        },
    ))

    return Resultat(
        ok=True,
        arret=None,
        piece=str(chemin),
        sha256=lecture.sha256,
        etapes=etapes,
        faits=faits,
        articles=[a.to_dict() for a in recherche.articles],
        evaluation=evaluation,
        explication=red.texte,
        origine_texte=red.origine,
        verification=red.verification,
        duree_totale_s=round(time.monotonic() - depart, 3),
    )


# --- Affichage console -------------------------------------------------------

def afficher(r: Resultat):
    print("=" * 72)
    print(f"MIZAN — chaîne d'agents v{VERSION_CHAINE}")
    print(f"Pièce    : {r.piece}")
    print(f"SHA-256  : {r.sha256}")
    print("=" * 72)

    print("\nJOURNAL DES AGENTS")
    for i, e in enumerate(r.etapes, start=1):
        marque = "OK  " if e.ok else "STOP"
        print(f"  {i}. [{marque}] {e.agent:<18} {e.duree_s:>7.3f}s  {e.resume}")
    print(f"  {'':>27}{r.duree_totale_s:>7.3f}s  TOTAL")

    if r.faits:
        print("\nFAITS ÉTABLIS (agent 1 — avec page d'origine)")
        for e in r.etapes:
            for f in e.detail.get("faits", []):
                page = f"p.{f['page']}" if f["page"] else "page ?"
                print(f"  - {f['cle']:<16} {str(f['valeur']):<28} [{page}] "
                      f"« {(f['ligne'] or '')[:46]} »")

    if r.articles:
        print("\nARTICLES VÉRIFIÉS DANS LE CORPUS (agent 2)")
        for a in r.articles:
            print(f"  - {a['code_fr']}, art. {a['article']}  —  {a['citation_ar']}")

    if r.evaluation:
        ev = r.evaluation
        print("\nMOTEUR JURIDIQUE (déterministe)")
        print(f"  Régime          : {ev['regime']}")
        print(f"  Échéance        : {ev['deadline']}  "
              f"({ev['days_left']} jours — {ev['urgency']})")
        print(f"  Huissier requis : {'oui' if ev['needs_bailiff'] else 'non'}")

    print("\nEXPLICATION POUR LA PME (agent 3)")
    print(f"  [origine : {r.origine_texte}]")
    for ligne in r.explication.splitlines():
        print(f"  {ligne}")

    v = r.verification or {}
    if v:
        print("\nCONTRÔLE ANTI-HALLUCINATION")
        print(f"  Articles autorisés par l'agent 2 : {', '.join(v.get('autorises', [])) or '—'}")
        print(f"  Articles cités dans le texte     : {', '.join(v.get('cites', [])) or '—'}")
        print(f"  Violation                        : "
              f"{'OUI' if v.get('viole') else 'non'}")

    print()
    print("=" * 72)
    print("RÉSULTAT :", "dossier traité" if r.ok else f"arrêt — {r.arret}")
    print("=" * 72)


def main(argv=None):
    import sys

    argv = list(argv if argv is not None else sys.argv[1:])
    sans_modele = "--sans-modele" in argv
    en_json = "--json" in argv
    argv = [a for a in argv if not a.startswith("--")]

    if not argv:
        print("usage : python -m agents.chaine <facture.pdf> "
              "[--sans-modele] [--json]")
        return 2

    r = traiter(argv[0], utiliser_modele=not sans_modele)

    if en_json:
        print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2))
    else:
        afficher(r)

    # Le code de sortie distingue un refus motivé (2) d'une violation (1).
    if r.verification.get("viole"):
        return 1
    return 0 if r.ok else 2


if __name__ == "__main__":
    import sys

    sys.exit(main())
