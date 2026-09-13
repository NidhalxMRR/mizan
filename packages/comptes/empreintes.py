"""Scellement des mots de passe.

Un mot de passe n'est jamais écrit tel quel : on n'en conserve qu'une empreinte
dont on ne sait pas revenir en arrière. Si la base de Mizan fuitait — et une
plateforme qui héberge des litiges commerciaux est une cible — l'attaquant
n'emporterait que des empreintes.

Trois décisions, et leurs raisons.

`scrypt` plutôt que SHA-256 seul : un condensé simple se calcule des milliards
de fois par seconde sur une carte graphique, donc un dictionnaire de mots de
passe courants s'y épuise en quelques minutes. `scrypt` a été conçu pour être
lent ET gourmand en mémoire, ce qui retire justement à l'attaquant l'avantage
du matériel spécialisé. Il est dans la bibliothèque standard de Python : aucune
dépendance à installer, ce qui compte quand la machine de démonstration est
saturée.

Un sel aléatoire par compte : sans sel, deux personnes ayant choisi le même mot
de passe auraient la même empreinte, et il suffirait d'en casser une pour les
avoir toutes. Le sel est tiré de `secrets`, donc d'une source cryptographique,
et non de `random` qui est prévisible.

`compare_digest` plutôt que `==` : l'égalité de Python s'arrête au premier
octet qui diffère, et le temps qu'elle met à répondre trahit donc le nombre
d'octets déjà devinés. La comparaison à temps constant ne dit rien de tel.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

# Longueur minimale exigée. Huit caractères ne font pas un bon mot de passe,
# mais en refuser moins écarte déjà les mots de passe qu'on devine en les
# lisant. Le seuil est nommé plutôt qu'écrit en dur dans le test : le jour où
# on le relève, il n'y a qu'un endroit à changer.
LONGUEUR_MINIMALE = 8

# Paramètres de coût. `n` est le facteur de travail, `r` la taille des blocs,
# `p` le parallélisme. n = 2^14 tient environ un dixième de seconde et seize
# mégaoctets par calcul : assez pour décourager une attaque par dictionnaire,
# assez peu pour qu'une connexion reste instantanée à l'usage.
COUT_N = 1 << 14
COUT_R = 8
COUT_P = 1
MEMOIRE_MAX = 64 * 1024 * 1024
TAILLE_SEL = 16
TAILLE_EMPREINTE = 32

# Les paramètres sont inscrits DANS l'empreinte, pas seulement dans ce fichier.
# Le jour où l'on relèvera le coût, les comptes déjà créés devront continuer à
# se connecter avec l'ancien : leur empreinte porte ce qu'il faut pour les
# recalculer.
ALGORITHME = "scrypt"


class MotDePasseInvalide(ValueError):
    """Le mot de passe proposé ne peut pas être accepté en l'état."""


class EmpreinteIllisible(ValueError):
    """L'empreinte stockée n'a pas la forme attendue : la base est abîmée."""


def _encoder(donnees: bytes) -> str:
    return base64.urlsafe_b64encode(donnees).decode("ascii").rstrip("=")


def _decoder(texte: str) -> bytes:
    rembourrage = "=" * (-len(texte) % 4)
    return base64.urlsafe_b64decode(texte + rembourrage)


def valider_mot_de_passe(mot_de_passe: str) -> str:
    """Refuse un mot de passe vide ou trop court, avec un message lisible.

    Le contrôle est fait ici et pas dans le formulaire, parce qu'un contrôle
    qui ne vit qu'au navigateur ne contrôle rien : il suffit d'appeler la route
    directement pour le contourner.
    """
    if not isinstance(mot_de_passe, str) or not mot_de_passe.strip():
        raise MotDePasseInvalide(
            "Le mot de passe est vide. Merci d'en choisir un avant de créer "
            "le compte."
        )
    if len(mot_de_passe) < LONGUEUR_MINIMALE:
        raise MotDePasseInvalide(
            f"Le mot de passe est trop court : il doit compter au moins "
            f"{LONGUEUR_MINIMALE} caractères."
        )
    return mot_de_passe


def sceller(mot_de_passe: str) -> str:
    """Transforme un mot de passe en empreinte salée, prête à être stockée.

    Le format retenu tient sur une seule colonne de texte et se relit sans
    table annexe :

        scrypt$16384$8$1$<sel>$<empreinte>

    Tout y est sauf le mot de passe lui-même, qui ne quitte jamais la mémoire
    de ce processus.
    """
    valider_mot_de_passe(mot_de_passe)
    sel = secrets.token_bytes(TAILLE_SEL)
    empreinte = hashlib.scrypt(
        mot_de_passe.encode("utf-8"),
        salt=sel,
        n=COUT_N, r=COUT_R, p=COUT_P,
        maxmem=MEMOIRE_MAX,
        dklen=TAILLE_EMPREINTE,
    )
    return "$".join((
        ALGORITHME, str(COUT_N), str(COUT_R), str(COUT_P),
        _encoder(sel), _encoder(empreinte),
    ))


def correspond(mot_de_passe: str, scelle: str) -> bool:
    """Vrai si le mot de passe proposé redonne bien l'empreinte stockée.

    Aucune exception n'est levée sur un mot de passe vide ou une empreinte
    malformée : la réponse est simplement « non ». Une fonction de vérification
    qui distinguerait « mot de passe faux » de « compte abîmé » renseignerait
    un attaquant sur l'état de la base.
    """
    if not isinstance(mot_de_passe, str) or not isinstance(scelle, str):
        return False
    try:
        algo, n, r, p, sel_txt, attendu_txt = scelle.split("$")
        if algo != ALGORITHME:
            return False
        candidat = hashlib.scrypt(
            mot_de_passe.encode("utf-8"),
            salt=_decoder(sel_txt),
            n=int(n), r=int(r), p=int(p),
            maxmem=MEMOIRE_MAX,
            dklen=TAILLE_EMPREINTE,
        )
    except (ValueError, TypeError, MemoryError):
        return False
    return hmac.compare_digest(candidat, _decoder(attendu_txt))


def relire_parametres(scelle: str) -> dict[str, int | str]:
    """Extrait les paramètres de coût d'une empreinte, sans la vérifier.

    Sert au contrôle d'exploitation : savoir si des comptes traînent encore sur
    un coût obsolète se lit dans la base, sans demander leur mot de passe aux
    intéressés.
    """
    try:
        algo, n, r, p, sel_txt, _ = scelle.split("$")
        return {
            "algorithme": algo, "n": int(n), "r": int(r), "p": int(p),
            "octets_de_sel": len(_decoder(sel_txt)),
        }
    except (ValueError, TypeError) as exc:
        raise EmpreinteIllisible(
            "L'empreinte enregistrée pour ce compte est illisible."
        ) from exc
