"""Le filet déterministe : relire le message quand le modèle a oublié un chiffre.

POURQUOI CE FICHIER EXISTE
--------------------------
L'agent fonctionne en trois temps : le modèle choisit l'outil, le moteur
calcule, le modèle reformule. Le premier temps a un défaut mesuré en conditions
réelles, sur le vrai modèle, et pas en théorie :

    « Ma créance de 9520 DT du 12/05/2026 est-elle encore récupérable ? »
        → le modèle remplit montant, date et activité. Réponse complète.

    « Calcule la prescription : montant 9520, date de facture 2026-05-12 »
        → le modèle appelle le BON outil, et n'y met AUCUN paramètre.
          L'agent répond « il me manque le montant ». Le montant est
          pourtant écrit en toutes lettres dans la phrase.

Le même renseignement, la même demande, deux formulations : l'une passe,
l'autre non. Pour une PME qui montre la plateforme à son comptable, ce n'est
pas un défaut d'ergonomie, c'est une panne.

Ce module est la réponse : une relecture du message en Python pur, sans
modèle, sans réseau, sans dépendance. Le modèle propose, le code vérifie.

LES DEUX RÈGLES QUI COMMANDENT TOUT LE RESTE
--------------------------------------------
1. NE JAMAIS ÉCRASER. Si le modèle a rempli un paramètre, ce paramètre est
   conservé tel quel. Ce filet COMPLÈTE ce qui manque, il ne corrige pas ce
   qui est déjà là. La seule exception, étroitement bornée, est la remise en
   forme d'une valeur que l'outil rejetterait de toute façon (« 9 520,000 DT »
   en texte, une date écrite 12/05/2026 alors que l'outil attend l'ISO) : là,
   on ne remplace pas une bonne valeur par une autre, on rend utilisable une
   valeur qui allait être refusée.

2. NE JAMAIS INVENTER. Dans le doute, ce module ne pose RIEN et l'agent
   redemande, exactement comme aujourd'hui. Une question de plus coûte dix
   secondes à l'utilisateur ; un montant deviné coûte un procès. C'est
   pourquoi deux montants concurrents dans une même phrase produisent une
   abstention, et non un choix.

CE QUE CE MODULE NE FAIT PAS
----------------------------
Il ne qualifie rien juridiquement. Il lit « je suis menuisier » et écrit
« menuiserie » ; c'est un travail de vocabulaire, pas de droit. C'est le
moteur — et lui seul — qui décide si la menuiserie relève du délai d'un an.
Quand le mot lu n'est pas dans la liste que le moteur sait qualifier, on le
transmet quand même : le moteur dira lui-même qu'il ne le qualifie pas, ce qui
vaut infiniment mieux que de laisser s'appliquer en silence l'activité par
défaut.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ce que le moteur sait réellement qualifier
# ---------------------------------------------------------------------------
# On ne recopie pas la liste des activités : on la LIT dans le moteur. Une
# liste recopiée diverge le jour où quelqu'un ajoute « ferronnerie » au moteur
# sans savoir que ce fichier existe. L'import est protégé parce que ce module
# doit rester lisible et testable même si le paquet juridique n'est pas
# chargeable — il ne fait, lui, que de la lecture de texte.
try:  # pragma: no cover - le chemin d'échec ne se produit pas en production
    from packages.legal.legal_engine import KNOWN_ACTIVITIES as _CONNUES_DU_MOTEUR
except Exception:  # noqa: BLE001
    _CONNUES_DU_MOTEUR = set()

ACTIVITES_DU_MOTEUR: frozenset[str] = frozenset(_CONNUES_DU_MOTEUR)


def _champs_declares(outil: str) -> frozenset[str]:
    """Les paramètres que CET outil déclare accepter.

    On interroge le catalogue plutôt que de tenir une table en double. C'est
    ce qui empêche le filet de poser `activite` sur `analyser_risques_facture`,
    qui ne la déclare pas : le paramètre serait écarté plus loin, et on aurait
    cru compléter quelque chose. Catalogue introuvable ou outil inconnu : on ne
    complète rien, ce qui est le comportement d'aujourd'hui.
    """
    try:
        from packages.agent.outils import CATALOGUE
    except Exception:  # noqa: BLE001  pragma: no cover
        return frozenset()
    fiche = CATALOGUE.get(str(outil))
    if fiche is None:
        return frozenset()
    return frozenset(fiche.parametres)


# ---------------------------------------------------------------------------
# Outillage de texte
# ---------------------------------------------------------------------------

def aplatir(texte: str) -> str:
    """Minuscules, sans accents, et SURTOUT de la même longueur que l'original.

    La longueur identique n'est pas un détail : on repère les nombres sur le
    texte d'origine (pour ne pas abîmer « د.ت » ni les majuscules de « DT »)
    puis on lit leur contexte sur cette version aplatie, aux mêmes positions.
    Une normalisation qui raccourcit la chaîne décalerait tous les index et
    ferait lire le contexte du mot d'à côté.
    """
    sortie = []
    for caractere in texte:
        decompose = unicodedata.normalize("NFD", caractere)
        base = "".join(c for c in decompose if not unicodedata.combining(c))
        sortie.append(base[0].lower() if base else caractere.lower())
    return "".join(sortie)


def lire_nombre(brut: str) -> float | None:
    """« 9 520,000 », « 9.520,000 », « 9520,5 », « 9520 » : une seule somme.

    Une PME tunisienne écrit son montant de quatre façons dans la même
    semaine, parfois dans la même phrase. Refuser l'une d'elles, c'est refuser
    un utilisateur sur quatre.

    Le cas réellement ambigu est « 9.520 » : séparateur de milliers à la
    tunisienne, ou 9 dinars 520 millimes ? On tranche pour les millimes, parce
    que c'est l'écriture des factures (trois décimales) et parce que c'est
    déjà la convention d'affichage de la plateforme. Le choix est arbitraire,
    il est documenté, et il est le même partout.
    """
    if brut is None:
        return None
    texte = str(brut).replace("\u00a0", "").replace("\u202f", "").replace(" ", "")
    texte = texte.strip().rstrip(".,")
    if not texte:
        return None
    signe = 1.0
    if texte.startswith("-"):
        signe, texte = -1.0, texte[1:]
    elif texte.startswith("+"):
        texte = texte[1:]
    if not texte or not texte[0].isdigit():
        return None
    if "," in texte and "." in texte:
        # La dernière ponctuation rencontrée est la décimale ; l'autre groupe
        # les milliers. « 9.520,000 » et « 9,520.00 » se lisent tous les deux.
        if texte.rindex(".") > texte.rindex(","):
            texte = texte.replace(",", "")
        else:
            texte = texte.replace(".", "").replace(",", ".")
    elif "," in texte:
        entier, _, frac = texte.rpartition(",")
        texte = f"{entier}.{frac}" if entier and len(frac) in (1, 2, 3) else texte.replace(",", "")
    try:
        return signe * float(texte)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Les dates
# ---------------------------------------------------------------------------

MOIS_FRANCAIS: dict[str, int] = {
    "janvier": 1, "janv": 1, "jan": 1,
    "fevrier": 2, "fevr": 2, "fev": 2,
    "mars": 3,
    "avril": 4, "avr": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7, "juil": 7, "jui": 7,
    "aout": 8,
    "septembre": 9, "sept": 9, "sep": 9,
    "octobre": 10, "oct": 10,
    "novembre": 11, "nov": 11,
    "decembre": 12, "dec": 12,
}

# Le nom de mois le plus long d'abord : sans cela « juillet » serait lu
# « juil » et il resterait « let » dans la phrase.
_ALTERNATIVE_MOIS = "|".join(sorted(MOIS_FRANCAIS, key=len, reverse=True))

_DATE_ISO = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
# Jour/mois/année, à la tunisienne. Ce motif ne connaît QUE cet ordre : voir
# `_construire_date` pour la raison, qui n'est pas un détail de localisation.
_DATE_CHIFFRES = re.compile(r"\b(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{4})\b")
_DATE_LETTRES = re.compile(
    rf"\b(\d{{1,2}})\s*(?:er)?\s+({_ALTERNATIVE_MOIS})\.?\s*(\d{{4}})?\b"
)
# Reconnu pour ne pas être confondu avec autre chose, mais jamais posé : une
# année à deux chiffres se lit 1926 ou 2026 selon l'humeur du lecteur.
_DATE_ANNEE_COURTE = re.compile(r"\b\d{1,2}\s*[/.\-]\s*\d{1,2}\s*[/.\-]\s*\d{2}\b")

# Les mots qui, juste avant une date, désignent LA date de la facture. Ils ne
# servent qu'à départager plusieurs dates ; une date seule n'a pas besoin
# d'être qualifiée pour être retenue.
_QUALIFIANTS_DATE = (
    "facture", "facturee", "facture du", "datee", "date", "emise", "etablie",
    "creance", "impaye", "dette", "livraison", "livree", "bon de",
)

ANNEE_MINIMALE = 1906  # entrée en vigueur du COC ; le moteur refuse en deçà


def _construire_date(annee: int, mois: int, jour: int) -> str | None:
    """Rend l'ISO si la date existe au calendrier, sinon rien.

    Le 30 février et le 31 novembre sont les deux pièges classiques : ils sont
    syntaxiquement irréprochables et n'existent pas. `date()` lève, on avale,
    on ne pose rien. Planter ici reviendrait à rendre une erreur technique
    anglaise à un chef d'entreprise qui a simplement mal tapé.
    """
    try:
        return date(annee, mois, jour).isoformat()
    except ValueError:
        return None


@dataclass
class _Candidat:
    """Une valeur repérée, avec l'endroit et le contexte où on l'a trouvée."""

    valeur: Any
    debut: int
    fin: int
    qualifie: bool = False
    ecarte: str = ""


def _dates_candidates(message: str, plat: str, aujourdhui: date) -> tuple[list[_Candidat], list[tuple[int, int]], list[str]]:
    """Toutes les dates lisibles, leurs emplacements, et ce qu'on a écarté.

    Les emplacements sont rendus même pour les dates ILLISIBLES (31/11/2026) :
    ils servent de zone interdite au repérage des montants. Sans cela,
    « 12/05/2026 » livrerait trois nombres — 12, 5 et 2026 — dont l'un a la
    taille d'une créance.
    """
    candidats: list[_Candidat] = []
    zones: list[tuple[int, int]] = []
    traces: list[str] = []

    def enregistrer(iso: str | None, debut: int, fin: int, brut: str) -> None:
        zones.append((debut, fin))
        if iso is None:
            traces.append(f"« {brut} » n'existe pas au calendrier : aucune date posée.")
            return
        annee = int(iso[:4])
        if annee < ANNEE_MINIMALE or annee > aujourdhui.year + 1:
            # Une facture de 1850 ou de 2190 est une faute de frappe. La poser
            # donnerait un calcul de prescription parfaitement exact sur une
            # donnée parfaitement fausse — le pire des deux mondes.
            traces.append(
                f"« {brut} » est hors des bornes plausibles ({ANNEE_MINIMALE}"
                f"–{aujourdhui.year + 1}) : aucune date posée."
            )
            return
        avant = plat[max(0, debut - 45):debut]
        candidats.append(_Candidat(
            valeur=iso, debut=debut, fin=fin,
            qualifie=any(mot in avant for mot in _QUALIFIANTS_DATE),
        ))

    for trouve in _DATE_ISO.finditer(message):
        annee, mois, jour = (int(g) for g in trouve.groups())
        enregistrer(_construire_date(annee, mois, jour), *trouve.span(), trouve.group(0))

    for trouve in _DATE_CHIFFRES.finditer(message):
        if any(d < trouve.end() and trouve.start() < f for d, f in zones):
            continue
        # JOUR EN PREMIER, TOUJOURS. En Tunisie « 12/05/2026 » est le 12 mai,
        # jamais le 5 décembre, et « 05/12/2026 » est le 5 décembre. Lire ces
        # dates à l'américaine décalerait la prescription de plusieurs mois
        # sans qu'aucune erreur ne soit visible à l'écran. Quand le premier
        # nombre dépasse 12, il n'y a pas d'ambiguïté ; quand c'est le second,
        # la date est simplement impossible dans cet ordre et rien n'est posé.
        jour, mois, annee = (int(g) for g in trouve.groups())
        enregistrer(_construire_date(annee, mois, jour), *trouve.span(), trouve.group(0))

    for trouve in _DATE_LETTRES.finditer(plat):
        if any(d < trouve.end() and trouve.start() < f for d, f in zones):
            continue
        jour = int(trouve.group(1))
        mois = MOIS_FRANCAIS[trouve.group(2)]
        annee_brute = trouve.group(3)
        if annee_brute is None:
            # « le 12 mai » : la forme est reconnue — ses chiffres ne seront
            # donc pas pris pour un montant — mais rien n'est posé. Deviner
            # l'année, c'est choisir entre une créance prescrite et une
            # créance vivante à la place de l'utilisateur.
            zones.append(trouve.span())
            traces.append(
                f"« {message[trouve.start():trouve.end()].strip()} » ne porte pas "
                "d'année : aucune date posée, l'agent la demandera."
            )
            continue
        enregistrer(_construire_date(int(annee_brute), mois, jour),
                    *trouve.span(), trouve.group(0))

    for trouve in _DATE_ANNEE_COURTE.finditer(message):
        if any(d < trouve.end() and trouve.start() < f for d, f in zones):
            continue
        zones.append(trouve.span())
        traces.append(
            f"« {trouve.group(0)} » porte une année à deux chiffres, qui se lit "
            "aussi bien 1926 que 2026 : aucune date posée."
        )

    return candidats, zones, traces


def _choisir_date(candidats: list[_Candidat]) -> tuple[str | None, list[str]]:
    """Une seule date, ou aucune. Jamais un tirage au sort.

    Règle : une seule date distincte, on la prend. Plusieurs, on ne garde que
    celles qu'un mot désigne comme la date de la facture ; s'il en reste
    exactement une, on la prend ; sinon on s'abstient.
    """
    traces: list[str] = []
    distinctes = {c.valeur for c in candidats}
    if not distinctes:
        return None, traces
    if len(distinctes) == 1:
        return next(iter(distinctes)), traces
    qualifiees = {c.valeur for c in candidats if c.qualifie}
    if len(qualifiees) == 1:
        retenue = next(iter(qualifiees))
        traces.append(
            f"Plusieurs dates dans le message ; celle désignée comme date de "
            f"facture ({retenue}) a été retenue."
        )
        return retenue, traces
    traces.append(
        "Plusieurs dates concurrentes et aucune n'est désignée comme la date "
        "de la facture : aucune date posée."
    )
    return None, traces


# ---------------------------------------------------------------------------
# Les montants
# ---------------------------------------------------------------------------

_UNITES = r"(?:dinars?|dt|tnd|د\.?\s?ت)"
_CHIFFRES = r"\d[\d\u00a0\u202f .,]*\d|\d"

# Premier motif : le nombre porte son unité. C'est le cas sûr.
_MONTANT_AVEC_UNITE = re.compile(rf"({_CHIFFRES})\s*{_UNITES}\b", re.IGNORECASE)

# Second motif : le nombre est annoncé par un mot qui dit que c'est de
# l'argent. « montant 9520 » n'a pas d'unité et reste parfaitement clair.
_ANNONCES = (
    r"montants?", r"sommes?", r"creances?", r"factures?\s+de", r"impayes?\s+de",
    r"dettes?\s+de", r"valeur", r"total", r"reclame", r"reclamant", r"doit",
    r"me\s+doit", r"nous\s+doit", r"principal", r"encours",
)
_MONTANT_ANNONCE = re.compile(
    rf"(?:{'|'.join(_ANNONCES)})\s*(?:de\s+|d'un\s+montant\s+de\s+|:\s*|=\s*)?({_CHIFFRES})"
)

# Ce qui ressemble à un montant et n'en est pas. Un numéro d'article est le
# faux ami le plus dangereux du projet : « article 403 » et « COC 1458 » sont
# des nombres de la bonne taille, cités en permanence, et les prendre pour une
# créance produirait une analyse de prescription sur un numéro d'article.
_ZONES_INTERDITES = (
    re.compile(r"\b(?:articles?|art\.?|coc|cpcc?|fascicule|alinea|paragraphe|"
               r"chapitre|titre|livre)\s*\.?\s*n?°?\s*\d+[\w\-/]*"),
    re.compile(r"الفصل\s*\d+"),
    re.compile(r"\b(?:n°|no\.?|numero|reference|ref\.?)\s*:?\s*[\w\-/]*\d[\w\-/]*"),
    re.compile(r"\d+(?:[.,]\d+)?\s*%"),
    re.compile(r"\b(?:tel|telephone|gsm|matricule|rib|cin|registre)\b\s*:?\s*[\d\s./\-]{4,}"),
)

# Les mots qui, autour d'un nombre, disent que ce nombre est une PART de la
# créance et non la créance. « 9520 dinars dont 1520 de TVA » : la somme
# réclamée est 9520, et 1520 est dedans.
#
# LA PROXIMITÉ EST CAPITALE, et un premier essai l'a appris à ses dépens : en
# cherchant « de tva » dans une fenêtre de vingt-six caractères après le
# nombre, on trouvait la TVA de l'AUTRE nombre, et « 9520 dinars dont 1520 de
# TVA » écartait les deux — donc n'extrayait rien du cas le plus courant. Un
# marqueur ne compte que s'il touche le nombre : juste devant, ou juste après
# son unité.
_MARQUEURS_AVANT = (
    "dont", "y compris", "incluant", "inclus", "tva", "taxe", "timbre",
    "acompte", "avance", "arrhes", "remise", "rabais", "escompte", "penalite",
    "penalites", "interet", "interets", "frais", "retenue", "majoration",
    "commission",
)
_MARQUEURS_APRES = (
    "tva", "taxe", "timbre", "acompte", "avance", "arrhes", "remise", "rabais",
    "escompte", "penalite", "penalites", "interet", "interets", "frais",
    "retenue", "majoration", "commission",
)
# Les mots de liaison qu'on saute pour aller du nombre à son marqueur :
# « dont 1520 DE TVA », « 300 D'intérêts », « dont 1520 » tout court.
_LIAISONS = ("de", "d", "du", "des", "en", "pour", "a", "au", "la", "le", "les",
             "l", "est", "etait", "sont", "s")

MONTANT_MAXIMAL = 1_000_000_000.0  # un milliard de dinars : au-delà, c'est une saisie


def _mots_colles_avant(amont: str, combien: int = 3) -> list[str]:
    """Les derniers mots qui précèdent immédiatement le nombre, dans l'ordre."""
    return re.findall(r"[a-z']+", amont)[-combien:]


def _marqueur_colle_avant(amont: str) -> bool:
    """« dont 1520 », « 300 » précédé de « frais de » : ce nombre est une part.

    On remonte au plus trois mots, en sautant les liaisons. Au-delà, on serait
    en train de lire la phrase d'à côté — et c'est précisément l'erreur qui
    faisait écarter les DEUX montants de « 9520 dinars dont 1520 de TVA ».
    """
    mots = _mots_colles_avant(amont)
    for mot in reversed(mots):
        mot = mot.strip("'")
        if mot in _MARQUEURS_AVANT:
            return True
        if mot not in _LIAISONS:
            return False
    return False


def _marqueur_colle_apres(aval: str) -> bool:
    """« 1520 de TVA », « 300 d'intérêts » : le mot qui suit qualifie le nombre.

    On saute l'unité monétaire éventuelle et une liaison, pas davantage.
    """
    reste = re.sub(rf"^\s*{_UNITES}\b", "", aval, flags=re.IGNORECASE)
    mots = re.findall(r"[a-z']+", reste)[:2]
    for mot in mots:
        mot = mot.strip("'")
        if mot in _MARQUEURS_APRES:
            return True
        if mot not in _LIAISONS:
            return False
    return False


def _montants_candidats(message: str, plat: str,
                        zones_dates: list[tuple[int, int]]) -> tuple[list[_Candidat], list[str]]:
    """Les nombres du message qui peuvent être la somme réclamée."""
    traces: list[str] = []
    interdits: list[tuple[int, int]] = list(zones_dates)
    for motif in _ZONES_INTERDITES:
        interdits.extend(t.span() for t in motif.finditer(plat))

    def interdit(debut: int, fin: int) -> bool:
        return any(d < fin and debut < f for d, f in interdits)

    candidats: list[_Candidat] = []
    vus: set[tuple[int, int]] = set()

    def examiner(brut: str, debut: int, fin: int, avec_unite: bool) -> None:
        if (debut, fin) in vus or interdit(debut, fin):
            return
        vus.add((debut, fin))
        valeur = lire_nombre(brut)
        if valeur is None:
            return
        # Le signe moins précède le nombre et ne fait partie d'aucun des deux
        # motifs : sans cette relecture, « une créance de -50 dinars » serait
        # lue comme une créance de 50 dinars — l'erreur exactement inverse de
        # celle qu'on veut éviter, et silencieuse.
        amont = plat[:debut].rstrip()
        if amont.endswith("-"):
            valeur = -valeur
        if valeur <= 0:
            # Le moteur refuserait de toute façon, mais il le refuserait au
            # nom du droit (« une créance nulle n'ouvre aucun droit »). Ici on
            # s'abstient simplement de poser : l'utilisateur sera invité à
            # donner un montant, ce qui est plus juste que de lui opposer une
            # règle sur une valeur qu'il n'a jamais voulu saisir.
            traces.append(f"« {brut.strip()} » n'est pas un montant recevable "
                          "(nul ou négatif) : rien n'a été posé.")
            return
        if valeur > MONTANT_MAXIMAL:
            traces.append(f"« {brut.strip()} » dépasse le milliard de dinars : "
                          "traité comme une faute de saisie, rien n'a été posé.")
            return
        entier = brut.strip().replace(" ", "").replace("\u00a0", "")
        if not avec_unite and entier.isdigit() and len(entier) == 4 and 1900 <= valeur <= 2100:
            # « 2026 » seul n'est pas une créance de 2026 dinars. Avec son
            # unité (« 2026 dinars ») il l'est, et le premier motif l'aura pris.
            traces.append(f"« {entier} » a été lu comme une année, pas comme un "
                          "montant : rien n'a été posé pour ce nombre.")
            return
        avant = plat[max(0, debut - 28):debut]
        apres = plat[fin:fin + 40]
        ecarte = ""
        if _marqueur_colle_avant(avant):
            ecarte = "part annoncée de la créance (mot qui précède le nombre)"
        elif _marqueur_colle_apres(apres):
            ecarte = "part annoncée de la créance (mot qui suit le nombre)"
        candidats.append(_Candidat(valeur=round(valeur, 3), debut=debut, fin=fin,
                                   qualifie=avec_unite, ecarte=ecarte))

    for trouve in _MONTANT_AVEC_UNITE.finditer(message):
        examiner(trouve.group(1), *trouve.span(1), True)
    for trouve in _MONTANT_ANNONCE.finditer(plat):
        examiner(message[trouve.start(1):trouve.end(1)], *trouve.span(1), False)

    return candidats, traces


def _choisir_montant(candidats: list[_Candidat]) -> tuple[float | None, list[str]]:
    """LA règle en cas de montants multiples, écrite ici une fois pour toutes.

    1. Les nombres présentés comme une PART de la créance — « dont 1520 de
       TVA », « 300 de frais » — sont écartés. Ils sont dans la somme, ils ne
       sont pas la somme.
    2. S'il reste une seule valeur distincte, c'est elle.
    3. S'il en reste plusieurs, ON NE POSE RIEN. Pas la plus grande, pas la
       première : rien. Choisir entre deux créances possibles, c'est décider à
       la place du créancier de ce qu'il réclame. L'agent redemande, et la
       question qu'il pose est bien meilleure qu'une réponse tirée au sort.
    """
    traces: list[str] = []
    if not candidats:
        return None, traces
    retenus = [c for c in candidats if not c.ecarte]
    ecartes = [c for c in candidats if c.ecarte]
    if ecartes and retenus:
        traces.append(
            "Montant(s) écarté(s) comme composante de la créance : "
            + ", ".join(f"{c.valeur:g}" for c in ecartes) + "."
        )
    if not retenus:
        traces.append("Tous les nombres repérés étaient des composantes "
                      "(TVA, frais…) : aucun montant posé.")
        return None, traces
    valeurs = {c.valeur for c in retenus}
    if len(valeurs) == 1:
        return next(iter(valeurs)), traces
    traces.append(
        "Plusieurs montants concurrents ("
        + ", ".join(f"{v:g}" for v in sorted(valeurs))
        + ") : aucun montant posé, l'agent demandera lequel est réclamé."
    )
    return None, traces


# ---------------------------------------------------------------------------
# L'activité
# ---------------------------------------------------------------------------
# Du vocabulaire, et rien que du vocabulaire : « je suis menuisier » désigne
# l'activité « menuiserie ». Aucune de ces lignes ne dit qu'une activité relève
# du délai d'un an ou de quinze : cette qualification appartient au moteur.
#
# Les termes trop généraux sont volontairement exigeants. « conseil » apparaît
# dans « je demande conseil » et « formation » dans « la formation du
# contrat » : les reconnaître à ces endroits ferait basculer le régime de
# prescription sur un mot de la langue courante.
_LEXIQUE_ACTIVITES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("menuiserie", ("menuiserie", "menuisier", "menuisiere")),
    ("menuiserie_alu", ("menuiserie alu", "menuiserie aluminium", "menuiserie en aluminium")),
    ("ebenisterie", ("ebenisterie", "ebeniste")),
    ("plomberie", ("plomberie", "plombier")),
    ("mobilier", ("mobilier", "ameublement", "fabricant de meubles")),
    ("textile", ("textile", "tissage", "filature", "tisserand")),
    ("confection", ("confection", "couturier", "couturiere", "atelier de couture")),
    ("imprimerie", ("imprimerie", "imprimeur")),
    ("boulangerie", ("boulangerie", "boulanger")),
    ("metallurgie", ("metallurgie", "metallurgiste", "metallurgique")),
    ("plasturgie", ("plasturgie",)),
    ("ceramique", ("ceramique", "ceramiste")),
    ("agroalimentaire", ("agroalimentaire", "agro-alimentaire", "agro alimentaire")),
    ("papeterie", ("papeterie", "papetier")),
    ("quincaillerie", ("quincaillerie", "quincaillier")),
    ("artisanat", ("artisanat", "artisan", "artisanale")),
    ("fabrication", ("fabrication", "fabricant")),
    ("industrie", ("industrie", "industriel")),
    ("commerce", ("commerce", "commercant", "negociant")),
    ("agriculture", ("agriculture", "agriculteur", "agricole")),
    ("atelier", ("atelier",)),
    ("transport", ("transport", "transporteur", "transitaire")),
    ("nettoyage", ("nettoyage", "societe de nettoyage")),
    ("gardiennage", ("gardiennage",)),
    ("maintenance", ("maintenance",)),
    ("informatique", ("informatique",)),
    ("comptabilite", ("comptabilite", "comptable", "expert-comptable")),
    ("publicite", ("publicite", "publicitaire", "agence de communication")),
    ("ingenierie", ("ingenierie", "bureau d'etudes", "bureau d'etude")),
    ("architecture", ("architecture", "architecte")),
    ("traduction", ("traduction", "traducteur")),
    ("conseil", ("consultant", "cabinet de conseil", "societe de conseil",
                 "activite de conseil", "conseil en")),
    ("formation", ("formateur", "centre de formation", "organisme de formation",
                   "societe de formation")),
    ("securite", ("societe de securite", "agent de securite", "societe de gardiennage")),
)

# Les termes qui désignent un cadre d'exercice plutôt qu'un métier. « atelier
# de confection » en nomme deux : l'atelier est le lieu, la confection est le
# métier. Sans cette distinction, la phrase la plus naturelle d'un artisan
# tunisien produirait une abstention pour « plusieurs activités » alors qu'elle
# n'en nomme qu'une. Quand un métier précis est nommé, le cadre s'efface.
_TERMES_GENERIQUES = frozenset({
    "atelier", "artisanat", "fabrication", "industrie", "commerce",
})

# Les termes longs d'abord : « menuiserie aluminium » doit l'emporter sur
# « menuiserie », sinon la variante ne serait jamais atteinte.
_TERMES_ACTIVITE: tuple[tuple[str, str], ...] = tuple(sorted(
    ((terme, canonique) for canonique, termes in _LEXIQUE_ACTIVITES for terme in termes),
    key=lambda paire: len(paire[0]), reverse=True,
))


def _activite_candidate(plat: str) -> tuple[str | None, list[str]]:
    """L'activité nommée dans le message, si elle l'est sans ambiguïté."""
    traces: list[str] = []
    trouvees: list[str] = []
    couvert: list[tuple[int, int]] = []
    for terme, canonique in _TERMES_ACTIVITE:
        for trouve in re.finditer(rf"(?<![a-z0-9]){re.escape(terme)}(?![a-z])", plat):
            if any(d < trouve.end() and trouve.start() < f for d, f in couvert):
                continue
            couvert.append(trouve.span())
            if canonique not in trouvees:
                trouvees.append(canonique)
    if not trouvees:
        return None, traces
    # Le cadre d'exercice s'efface devant le métier : « atelier de confection »
    # est une confection, pas deux activités concurrentes.
    precises = [a for a in trouvees if a not in _TERMES_GENERIQUES]
    if precises:
        trouvees = precises
    if len(trouvees) > 1:
        traces.append(
            "Plusieurs activités nommées (" + ", ".join(trouvees)
            + ") : aucune activité posée, le régime de prescription en dépend "
            "trop directement pour être deviné."
        )
        return None, traces
    activite = trouvees[0]
    if activite not in ACTIVITES_DU_MOTEUR:
        # On la transmet quand même, et c'est volontaire. Sans elle, l'outil
        # applique son activité par défaut — la menuiserie — et annoncerait à
        # un plombier une prescription d'un an qu'aucun texte ne fonde. Avec
        # elle, le moteur dit lui-même qu'il ne sait pas qualifier « plomberie »
        # et le signale à l'écran. Un doute affiché vaut mieux qu'une certitude
        # fausse.
        traces.append(
            f"L'activité « {activite} » a été lue dans le message mais n'est pas "
            "qualifiée par le moteur : elle est transmise telle quelle, le moteur "
            "annoncera lui-même que le régime n'est pas confirmé."
        )
    return activite, traces


# ---------------------------------------------------------------------------
# Le résultat de la relecture
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Extraction:
    """Ce que la relecture du message a permis d'établir, et rien de plus.

    Un champ à None ne veut pas dire « absent du message » : il veut dire
    « pas assez sûr pour être posé ». Les deux cas sont indiscernables pour
    l'appelant, et c'est exactement ce qu'on veut — dans les deux cas, l'agent
    doit demander.

    `traces` est destiné aux journaux et à la démonstration : il dit POURQUOI
    on s'est abstenu. C'est ce qui permet de défendre une abstention devant un
    jury au lieu de la subir.
    """

    montant: float | None = None
    date_facture: str | None = None
    activite: str | None = None
    traces: tuple[str, ...] = field(default_factory=tuple)

    def __bool__(self) -> bool:
        return any((self.montant is not None, self.date_facture is not None,
                    self.activite is not None))

    def to_dict(self) -> dict[str, Any]:
        return {
            "montant": self.montant,
            "date_facture": self.date_facture,
            "activite": self.activite,
            "traces": list(self.traces),
        }


def extraire(message: str, aujourdhui: date | None = None) -> Extraction:
    """Relit le message et en tire ce qui est certain. Ne lève jamais.

    « Ne lève jamais » est une exigence, pas une politesse : ce filet est
    appelé sur le chemin nominal de l'agent. S'il se mettait à lever sur une
    phrase biscornue, il transformerait une réponse imparfaite en panne.
    """
    texte = (message or "").strip()
    if not texte:
        return Extraction()
    reference = aujourdhui or date.today()
    try:
        plat = aplatir(texte)
        candidats_dates, zones_dates, traces = _dates_candidates(texte, plat, reference)
        date_retenue, t = _choisir_date(candidats_dates)
        traces += t
        candidats_montants, t = _montants_candidats(texte, plat, zones_dates)
        traces += t
        montant, t = _choisir_montant(candidats_montants)
        traces += t
        activite, t = _activite_candidate(plat)
        traces += t
        return Extraction(montant=montant, date_facture=date_retenue,
                          activite=activite, traces=tuple(traces))
    except Exception as exc:  # noqa: BLE001 — un filet qui tombe n'est pas un filet
        logger.warning("relecture déterministe interrompue : %s", exc)
        return Extraction()


# ---------------------------------------------------------------------------
# La remise en forme d'une valeur que le modèle a bien vue mais mal écrite
# ---------------------------------------------------------------------------

def _renseigne(valeur: Any) -> bool:
    """Le modèle a-t-il mis quelque chose dans ce paramètre ?

    `0` et `0.0` comptent comme renseignés : ils sont faux, l'outil les
    refusera avec un message clair, et ce refus appartient au moteur. Les
    remplacer en silence par une valeur lue dans le texte serait précisément
    l'écrasement qu'on s'interdit.
    """
    if valeur is None:
        return False
    if isinstance(valeur, str):
        return bool(valeur.strip())
    return True


def _montant_utilisable(valeur: Any) -> bool:
    """L'outil saura-t-il lire ce montant tel quel ?"""
    if isinstance(valeur, bool):
        return False
    if isinstance(valeur, (int, float)):
        return True
    try:
        float(str(valeur).strip())
        return True
    except (TypeError, ValueError):
        return False


def _date_utilisable(valeur: Any) -> bool:
    """L'outil saura-t-il lire cette date telle quelle ? Il n'accepte que l'ISO."""
    try:
        date.fromisoformat(str(valeur).strip())
        return True
    except (TypeError, ValueError):
        return False


def remettre_en_forme(cle: str, valeur: Any, aujourdhui: date | None = None) -> Any:
    """Rend une valeur du modèle utilisable, ou la laisse telle quelle.

    Ce n'est PAS un écrasement, et la distinction est la raison d'être de cette
    fonction : on n'intervient que sur une valeur que l'outil allait rejeter.
    Le modèle qui rend `montant: "9 520,000 DT"` a parfaitement lu la phrase —
    il l'a seulement recopiée au lieu de la convertir. Refuser cette réponse
    pour un espace insécable serait un comble.
    """
    if cle == "montant":
        if _montant_utilisable(valeur):
            return valeur
        sans_unite = re.sub(_UNITES, "", str(valeur), flags=re.IGNORECASE)
        lu = lire_nombre(sans_unite)
        return lu if lu is not None and 0 < lu <= MONTANT_MAXIMAL else valeur
    if cle == "date_facture":
        if _date_utilisable(valeur):
            return valeur
        relecture = extraire(str(valeur), aujourdhui=aujourdhui)
        return relecture.date_facture or valeur
    return valeur


# ---------------------------------------------------------------------------
# Le filet proprement dit
# ---------------------------------------------------------------------------

CHAMPS_DU_FILET = ("montant", "date_facture", "activite")


def completer(message: str, outil: str, parametres: dict[str, Any] | None,
              aujourdhui: date | None = None) -> dict[str, Any]:
    """Complète les paramètres oubliés par le modèle, sans jamais en changer un.

    C'est le point d'entrée que l'agent appelle, et le seul. Il rend TOUJOURS
    un dictionnaire neuf : personne ne doit pouvoir se demander si l'appelant a
    été modifié par surprise.

    L'ordre de préséance, du plus fort au plus faible :
      1. ce que le modèle a rempli et que l'outil sait lire — intouchable ;
      2. ce que le modèle a rempli mais mal écrit — remis en forme ;
      3. ce que le modèle a oublié et que le texte donne sans ambiguïté — posé ;
      4. le reste — laissé vide, l'agent demandera.
    """
    params = dict(parametres or {})
    champs = _champs_declares(outil) & set(CHAMPS_DU_FILET)
    if not champs:
        return params

    manquants = [c for c in CHAMPS_DU_FILET if c in champs and not _renseigne(params.get(c))]

    for cle in champs:
        if _renseigne(params.get(cle)):
            avant = params[cle]
            apres = remettre_en_forme(cle, avant, aujourdhui)
            if apres != avant:
                logger.info("filet déterministe : %s remis en forme (%r → %r)",
                            cle, avant, apres)
                params[cle] = apres

    if not manquants:
        return params

    relecture = extraire(message, aujourdhui=aujourdhui)
    for cle in manquants:
        valeur = getattr(relecture, cle)
        if valeur is None:
            continue
        params[cle] = valeur
        logger.info("filet déterministe : %s complété depuis le message (%r)",
                    cle, valeur)
    for trace in relecture.traces:
        logger.info("filet déterministe : %s", trace)
    return params


# ---------------------------------------------------------------------------
# Le cas où le modèle s'est trompé d'outil faute d'avoir lu les chiffres
# ---------------------------------------------------------------------------

def corriger_outil(message: str, outil: str, parametres: dict[str, Any] | None,
                   aujourdhui: date | None = None) -> str:
    """Corrige le seul mauvais aiguillage que la relecture permet d'établir.

    Mesuré sur le vrai modèle :

        « J'ai une facture impayée de 9520 dinars datée du 12 mai 2026, je suis
          menuisier. Qu'est-ce que je risque ? »
            → le mot « risque » l'emporte, le modèle appelle l'analyse de
              risques d'un DOCUMENT, et l'agent réclame un PDF que l'utilisateur
              n'a jamais eu l'intention de déposer.

    Le renseignement est pourtant complet : une somme, une date, une activité.
    Quand l'analyse documentaire est demandée SANS document et que le message
    contient de quoi calculer la prescription, la demande porte sur la créance,
    pas sur la pièce. On corrige — et seulement dans ce sens, jamais l'inverse :
    dès qu'un document est fourni, c'est bien la pièce qu'il faut analyser.
    """
    if outil != "analyser_risques_facture":
        return outil
    params = dict(parametres or {})
    if _renseigne(params.get("chemin")) or _renseigne(params.get("texte")):
        return outil
    montant = params.get("montant")
    jour = params.get("date_facture")
    if not (_renseigne(montant) and _renseigne(jour)):
        relecture = extraire(message, aujourdhui=aujourdhui)
        montant = montant if _renseigne(montant) else relecture.montant
        jour = jour if _renseigne(jour) else relecture.date_facture
    if _renseigne(montant) and _renseigne(jour):
        logger.info("filet déterministe : analyse documentaire sans document, "
                    "mais créance complète dans le message — aiguillé vers "
                    "l'analyse d'impayé")
        return "analyser_impaye"
    return outil
