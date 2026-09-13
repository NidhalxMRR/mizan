"""L'agent conversationnel de Mizan.

Ce paquet n'est pas un « chatbot ». Un chatbot répond ; cet agent AGIT — il
appelle les fonctions de la plateforme au nom de la personne connectée, sous
son identité, avec ses droits et à l'intérieur de son organisation.

Trois idées structurent tout ce dossier, et elles tiennent en trois phrases.

1. Le modèle de langage ne dit jamais le droit. Il sert à deux choses, et à
   rien d'autre : comprendre ce que veut l'utilisateur pour choisir l'outil à
   appeler, puis remettre en français courant un résultat DÉJÀ calculé par le
   moteur déterministe. Entre les deux, il n'a pas voix au chapitre. Aucun
   chiffre, aucune date, aucun article cité ne sort de lui.

2. Un outil qu'un rôle n'a pas le droit d'appeler est refusé, et le refus
   explique la règle de droit qui le commande — pas un code d'erreur.

3. L'organisation de l'appelant n'est jamais un paramètre. Elle vient du jeton
   de session, jamais de la demande, et surtout jamais du modèle. Un agent qui
   travaille pour une entreprise ne peut pas être convaincu de travailler pour
   une autre, parce qu'on ne lui a pas laissé la possibilité de le dire.
"""

from packages.agent.identite import Identite, Refus
from packages.agent.cerveau import Agent, ReponseAgent

__all__ = ["Agent", "Identite", "Refus", "ReponseAgent"]
