"""Les routes de l'agent conversationnel.

CE FICHIER NE FAIT QUE TRANSPORTER. Aucune décision juridique, aucun contrôle
de droits n'est écrit ici : tout est dans `packages/agent`. Si une règle
d'accès devait être ajoutée dans ce fichier, ce serait le signe qu'elle manque
dans le moteur — et une règle qui ne vit que dans la couche HTTP est une règle
qu'aucun test métier ne protège.

Le rôle de ces routes tient en une phrase : prendre la session vérifiée de
l'appelant, en tirer une `Identite`, et la donner à l'agent. L'organisation et
le rôle ne sont JAMAIS lus dans le corps de la requête. Le navigateur ne dit
pas qui il est ; le jeton le prouve.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from packages.agent.cerveau import Agent
from packages.agent.identite import Identite, IdentiteInvalide
from packages.agent.outils import outils_autorises

logger = logging.getLogger(__name__)

routeur = APIRouter(prefix="/api/agent", tags=["agent"])


class DemandeAgent(BaseModel):
    """Ce que le navigateur envoie. Remarquez ce qui n'y figure PAS.

    Ni organisation, ni rôle, ni identifiant de compte. Si ces champs
    existaient, il faudrait les ignorer ; ne pas les déclarer est plus sûr que
    les ignorer, parce qu'on ne peut pas oublier d'ignorer un champ qui n'a
    jamais été lu.
    """

    message: str = Field(..., max_length=4000)


def _identite_de_lappelant(requete: Request) -> Identite:
    """Tire l'identité de la session vérifiée, déposée par le garde d'accès.

    Deux sources possibles, dans l'ordre : `request.state.session`, posé par la
    dépendance d'authentification du projet, ou l'en-tête de session. Aucune
    troisième. Un appel sans session vérifiée est refusé — l'agent n'a pas de
    mode anonyme, parce qu'un agent qui agit au nom de personne agirait au nom
    de n'importe qui.
    """
    session = getattr(requete.state, "session", None)
    if session is None:
        raise HTTPException(
            status_code=401,
            detail=(
                "Vous devez être connecté pour utiliser l'agent : il travaille "
                "au nom de votre entreprise, avec vos droits."
            ),
        )
    try:
        return Identite.depuis_session(session)
    except IdentiteInvalide as exc:
        logger.warning("session inexploitable pour l'agent : %s", exc)
        raise HTTPException(
            status_code=403,
            detail=(
                "Votre session ne permet pas d'identifier l'organisation pour "
                "laquelle vous agissez. Reconnectez-vous."
            ),
        ) from exc


@routeur.post("/message")
def envoyer_un_message(demande: DemandeAgent,
                       identite: Identite = Depends(_identite_de_lappelant)) -> dict:
    """Le point d'entrée de la conversation.

    Rend toujours 200 quand la session est valide, y compris sur un refus de
    droits ou une abstention. Ce choix est délibéré : un refus fondé en droit
    n'est pas une erreur de transport, et le renvoyer en 403 le ferait afficher
    par le navigateur comme une panne au lieu d'une réponse juridique. Le champ
    `refuse` porte l'information ; le texte porte le motif.
    """
    agent = Agent(identite)
    reponse = agent.repondre(demande.message)
    return reponse.to_dict()


@routeur.get("/capacites")
def lister_les_capacites(identite: Identite = Depends(_identite_de_lappelant)) -> dict:
    """Ce que CET utilisateur peut demander à l'agent.

    Sert à l'interface, pour proposer des suggestions qui ne se heurteront pas
    à un refus. Ne liste que les outils ouverts à son rôle : la liste elle-même
    est cloisonnée, sans quoi elle renseignerait chacun sur les pouvoirs des
    autres.
    """
    return {
        "organisation": identite.organisation_affichee,
        "role": identite.libelle_role,
        "capacites": [
            {"nom": o.nom, "description": o.description}
            for o in outils_autorises(identite)
        ],
    }
