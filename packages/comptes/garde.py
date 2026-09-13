"""La porte : `exige(privilège)`, à poser sur toute route qui agit.

Une route protégée s'écrit ainsi, et pas autrement :

    @routeur.post("/greffe/dossiers/{reference}/recevable")
    def declarer_recevable(
        reference: str,
        session: Session = Depends(exige("approve_dossier")),
    ):
        ...

Le contrôle est donc DÉCLARÉ dans la signature de la route, pas enfoui dans un
`if` au milieu du corps. La différence n'est pas esthétique : une route sans
dépendance se repère d'un coup d'œil, alors qu'un `if` oublié dix lignes plus
bas ne se voit pas. C'est une propriété qu'on peut relire route par route.

Ce module est le SEUL du paquet à importer FastAPI. Toute la logique — rôles,
empreintes, jetons, registre — reste du Python ordinaire, testable sans serveur
et réutilisable depuis un script en ligne de commande.
"""
from __future__ import annotations

from typing import Callable

from fastapi import Depends, Header, HTTPException

from packages.comptes.jetons import JetonInvalide, Session, lire_jeton
from packages.comptes.roles import libelle_permission, libelle_role


def _elider(verbe: str) -> str:
    """« de administrer » ne se dit pas : on élide devant une voyelle.

    Le détail paraît mince, mais ces messages seront lus par des juristes. Une
    faute d'élision dans un refus d'accès signale un logiciel bâclé, et sur une
    plateforme judiciaire ce soupçon coûte plus cher que la faute elle-même.
    """
    return f"d'{verbe}" if verbe[:1].lower() in "aeéèêiouy" else f"de {verbe}"


def _jeton_de_l_entete(autorisation: str | None) -> str:
    """Extrait le jeton de l'en-tête HTTP `Authorization: Bearer ...`."""
    if not autorisation:
        raise HTTPException(
            status_code=401,
            detail="Vous n'êtes pas connecté. Merci de vous identifier pour "
                   "accéder à cette page.",
        )
    morceaux = autorisation.split(None, 1)
    if len(morceaux) != 2 or morceaux[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Votre session n'est pas reconnue. Merci de vous reconnecter.",
        )
    return morceaux[1].strip()


def verifier_jeton(
    authorization: str | None = Header(default=None),
) -> Session:
    """Dépendance FastAPI : exige une session valide, sans privilège précis.

    À utiliser sur les routes qui demandent seulement d'être connecté. Pour
    tout ce qui AGIT — approuver, signifier, signer — passer par `exige`.
    """
    try:
        return lire_jeton(_jeton_de_l_entete(authorization))
    except JetonInvalide as exc:
        # 401 et non 403 : ce n'est pas un droit qui manque, c'est l'identité
        # qui n'est pas établie. Le client doit renvoyer vers la connexion, pas
        # afficher « accès interdit » à quelqu'un dont la session a simplement
        # expiré.
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def exige(permission: str) -> Callable[..., Session]:
    """Fabrique une dépendance qui refuse si le rôle ne porte pas ce privilège.

    Le refus est un 403 et non un 404 : le dossier existe, c'est bien le droit
    d'agir qui manque. Un greffier à qui l'on répondrait « introuvable » sur un
    dossier qu'il voit à l'écran chercherait une panne là où il y a une règle.
    """

    def dependance(session: Session = Depends(verifier_jeton)) -> Session:
        if not session.peut(permission):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Votre compte est enregistré comme « {libelle_role(session.role)} ». "
                    f"Ce rôle ne permet pas {_elider(libelle_permission(permission))} "
                    "sur Mizan."
                ),
            )
        return session

    # Nommer la dépendance d'après le privilège rend les traces d'erreur et la
    # documentation OpenAPI lisibles : on y voit « exige_issue_formal_notice »
    # plutôt que cinq fois « dependance ».
    dependance.__name__ = f"exige_{permission}"
    dependance.__doc__ = (
        f"Exige le privilège « {libelle_permission(permission)} »."
    )
    return dependance


def exige_organisation(session: Session, organisation: str) -> Session:
    """Refuse (403) si la session agit au nom d'une autre organisation.

    N'est pas une dépendance parce que l'organisation visée ne se connaît
    qu'une fois le dossier chargé : la route l'appelle donc juste après sa
    lecture, avant de renvoyer quoi que ce soit.
    """
    if not session.meme_organisation(organisation):
        raise HTTPException(
            status_code=403,
            detail="Ce dossier appartient à une autre organisation. Votre "
                   "compte n'a accès qu'aux dossiers de votre entreprise.",
        )
    return session
