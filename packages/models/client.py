"""
Accès au modèle de langage — local d'abord, Modal en secours.

Pourquoi cet ordre. Un dossier de litige contient des factures, des contrats,
des noms de clients. Un greffe tunisien ne peut pas envoyer ça chez un tiers
étranger : le modèle local n'est pas une optimisation, c'est la condition pour
que la plateforme soit adoptable par une institution.

Modal reste branché pour une seule raison : si le GPU sature pendant la
démonstration, la bascule doit être invisible. Les deux hébergements exposent
la même API compatible OpenAI, donc basculer revient à changer une URL.

Et si les deux tombent, l'application continue de fonctionner : le moteur
juridique est déterministe. Aucun délai de prescription, aucun article de loi
ne dépend d'un modèle de langage. On perd la reformulation, jamais le droit.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Literal

import httpx

logger = logging.getLogger(__name__)

Origine = Literal["local", "modal", "aucune"]


class ModeleIndisponible(RuntimeError):
    """Aucun hébergement n'a répondu. L'appelant doit se passer du modèle."""


@dataclass(frozen=True)
class Hebergement:
    nom: Origine
    base_url: str
    modele: str
    delai_s: float

    def __str__(self) -> str:  # pragma: no cover - confort de journalisation
        return f"{self.nom} ({self.base_url})"


@dataclass(frozen=True)
class Reponse:
    texte: str
    origine: Origine
    duree_s: float


def _depuis_env() -> list[Hebergement]:
    """
    Construit la liste d'hébergements, dans l'ordre de préférence.

    Le local passe en premier. Modal n'est ajouté que si son URL est fournie,
    ce qui permet de démontrer le fonctionnement hors-ligne en retirant une
    seule variable d'environnement.
    """
    liste: list[Hebergement] = []

    url_locale = os.getenv("MIZAN_LLM_LOCAL", "http://127.0.0.1:11434/v1")
    if url_locale:
        liste.append(
            Hebergement(
                nom="local",
                base_url=url_locale.rstrip("/"),
                modele=os.getenv("MIZAN_LLM_LOCAL_MODELE", "qwen2.5:7b-instruct-q4_K_M"),
                # Court : si le GPU local ne répond pas vite, on bascule au lieu
                # de faire attendre le jury.
                delai_s=float(os.getenv("MIZAN_LLM_LOCAL_DELAI", "20")),
            )
        )

    url_modal = os.getenv("MIZAN_LLM_MODAL", "").rstrip("/")
    if url_modal:
        liste.append(
            Hebergement(
                nom="modal",
                base_url=url_modal,
                modele=os.getenv("MIZAN_LLM_MODAL_MODELE", "qwen"),
                # Plus long : Modal démarre ses conteneurs à froid.
                delai_s=float(os.getenv("MIZAN_LLM_MODAL_DELAI", "120")),
            )
        )

    return liste


def _nettoyer(texte: str) -> str:
    """
    Retire le raisonnement interne des modèles Qwen3.

    Ils émettent leur délibération entre <think> et </think>. Mesuré sur le
    déploiement de Zied, ce bloc contient des hésitations du genre
    « Wait, but I should make sure » — exactement ce qu'on ne montre jamais à
    une PME qui attend une réponse sur son litige.
    """
    while "<think>" in texte and "</think>" in texte:
        debut = texte.index("<think>")
        fin = texte.index("</think>") + len("</think>")
        texte = texte[:debut] + texte[fin:]
    return texte.strip()


class ClientLLM:
    """
    Un client, plusieurs hébergements, une bascule automatique.

    L'appelant ne sait pas quel hébergement a répondu — il le lit dans
    `Reponse.origine` s'il veut l'afficher, ce que fait l'interface pour
    rester honnête sur la provenance.
    """

    def __init__(self, hebergements: list[Hebergement] | None = None) -> None:
        self.hebergements = hebergements if hebergements is not None else _depuis_env()

    # -- diagnostic ---------------------------------------------------------

    def sonder(self) -> list[tuple[Hebergement, bool, str]]:
        """
        Interroge chaque hébergement et retourne son état.

        Retourne le motif d'échec en clair plutôt qu'un simple booléen : un
        `except Exception: return False` masque la cause et fait perdre du
        temps au moment où on en a le moins.
        """
        resultats: list[tuple[Hebergement, bool, str]] = []
        for h in self.hebergements:
            try:
                r = httpx.get(f"{h.base_url}/models", timeout=min(h.delai_s, 15.0))
                ok = r.status_code == 200
                resultats.append((h, ok, "ok" if ok else f"HTTP {r.status_code}"))
            except Exception as exc:  # noqa: BLE001 - on veut le motif exact
                resultats.append((h, False, f"{type(exc).__name__}: {exc}"))
        return resultats

    def disponible(self) -> bool:
        return any(ok for _, ok, _ in self.sonder())

    # -- génération ---------------------------------------------------------

    def generer(
        self,
        invite: str,
        *,
        systeme: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.3,
    ) -> Reponse:
        """
        Essaie chaque hébergement dans l'ordre et retourne la première réponse.

        Lève ModeleIndisponible si aucun ne répond, avec le motif de chacun.
        """
        messages = []
        if systeme:
            messages.append({"role": "system", "content": systeme})
        messages.append({"role": "user", "content": invite})

        echecs: list[str] = []

        for h in self.hebergements:
            debut = time.monotonic()
            try:
                r = httpx.post(
                    f"{h.base_url}/chat/completions",
                    json={
                        "model": h.modele,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    },
                    timeout=h.delai_s,
                )
                r.raise_for_status()
                brut = r.json()["choices"][0]["message"]["content"]
                duree = time.monotonic() - debut
                logger.info("réponse obtenue de %s en %.1f s", h, duree)
                return Reponse(texte=_nettoyer(brut), origine=h.nom, duree_s=duree)

            except Exception as exc:  # noqa: BLE001 - on essaie le suivant
                motif = f"{h.nom}: {type(exc).__name__}: {exc}"
                logger.warning("bascule — %s", motif)
                echecs.append(motif)

        raise ModeleIndisponible(
            "aucun hébergement n'a répondu — " + " | ".join(echecs)
            if echecs
            else "aucun hébergement configuré"
        )


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    c = ClientLLM()

    print("Hébergements configurés, par ordre de préférence :")
    for h, ok, motif in c.sonder():
        print(f"  {'✓' if ok else '✗'} {h.nom:6s} {h.base_url}")
        if not ok:
            print(f"       {motif}")

    try:
        rep = c.generer(
            "En une phrase : à quoi sert la conciliation en droit commercial ?",
            systeme="Tu réponds en français, brièvement, sans citer d'article de loi.",
            max_tokens=120,
        )
        print(f"\n[{rep.origine}, {rep.duree_s:.1f} s] {rep.texte}")
    except ModeleIndisponible as exc:
        print(f"\nAucun modèle : {exc}")
        print("L'application reste utilisable : le moteur juridique est déterministe.")
