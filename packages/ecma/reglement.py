"""E-CMA — le moteur de règlement amiable en ligne (conciliation, médiation,
arbitrage électroniques).

LE PRINCIPE, ET POURQUOI IL EST DANS LES TYPES ET PAS DANS UN COMMENTAIRE
------------------------------------------------------------------------
« L'IA propose. Le droit dispose. »

Un agent logiciel n'a pas la personnalité juridique. Il ne peut ni concilier,
ni médier, ni arbitrer : ce sont des OFFICES, exercés par une personne
accréditée qui engage sa responsabilité. Ce que Mizan produit ici est donc un
AVIS — un projet de termes, motivé et sourcé — et rien d'autre.

Pour que cela ne soit pas une simple promesse en bas de page, la structure de
données le rend vrai :

  * `AvisAgent`        — ce que la machine propose. Non contraignant.
  * `EspaceValidation` — ce que le professionnel accrédité signe. VIDE tant
                         qu'il n'a pas signé : `valide_par is None`.
  * `DossierECMA.porte_effet_juridique` — une PROPRIÉTÉ CALCULÉE, jamais un
                         champ. Il n'existe aucun chemin de code par lequel un
                         appelant puisse l'écrire à True. Il vaut True si et
                         seulement si un professionnel identifié a signé.

C'est le point que le jury doit pouvoir vérifier en lisant les types, sans
nous croire sur parole : `porte_effet_juridique = True` est INÉCRIVABLE.

LE FONDEMENT LÉGAL, VÉRIFIÉ DANS LE CORPUS
------------------------------------------
Tout ce que ce module affirme en droit est ancré sur un article réellement
présent dans les 4087 articles indexés, cité en arabe mot pour mot depuis le
champ `citation_ar` du corpus. Aucune citation n'est composée ici : voir
`_ancrer()`, qui va relire l'article dans le corpus et REFUSE de citer ce
qu'il n'y trouve pas.

La transaction (الصلح) est définie au COC art. 1458. ATTENTION — le texte du
corpus n'est pas la formule française usuelle « contrat par lequel les parties
terminent une contestation née ou préviennent une contestation à naître » :
le COC tunisien dit, mot pour mot,
« الصلح عقد وضع لرفع النزاع وقطع الخصومة ويكون ذلك بتنازل كل من المتصالحين
عن شيء من مطالبه أو بتسليم شيء من المـال أو الحـق ».
Soit : un contrat destiné à LEVER le litige et à COUPER COURT à l'instance,
par une concession réciproque. La concession réciproque est donc de l'essence
même de la transaction en droit tunisien — ce qui fonde directement le fait de
proposer un montant transigé inférieur au montant réclamé. Le module cite le
texte du corpus, pas la formule de manuel.

CE QUE LE CORPUS NE FONDE PAS, ET QUE CE MODULE REFUSE D'INVENTER
-----------------------------------------------------------------
1. LA MÉDIATION CIVILE ET COMMERCIALE. Recherche exhaustive du corpus :
   « الوساطة » n'apparaît qu'une fois, au Code de commerce art. 601, et y
   désigne le COURTAGE (un mandat commercial), pas la médiation-mode de
   règlement des différends. « الوسيط » n'apparaît que comme intermédiaire
   boursier ou commissaire aux comptes. Aucun des 4087 articles n'organise la
   médiation. Le module décrit donc la médiation comme voie praticable, mais
   la marque `fondee_dans_corpus=False` et ne la recommande jamais sur le
   seul fondement du corpus.

2. LE QUANTUM DE LA REMISE. Aucun article ne fixe de taux d'abattement
   transactionnel. Le PRINCIPE de la concession est fondé (COC 1458) ; son
   MONTANT ne l'est pas. Chaque terme porte donc deux drapeaux distincts,
   `principe_fonde` et `quantum_fonde`, et le second est toujours False.

3. L'ÉCHÉANCIER. « التقسيط » (paiement échelonné) et « نظرة الميسرة » (délai
   de grâce) : zéro occurrence dans le corpus. Le juge tunisien dispose bien
   d'un pouvoir de délai, mais aucun article indexé ici ne le porte. Un
   échéancier n'est donc proposé QUE comme stipulation contractuelle, fondée
   sur la force obligatoire du contrat (COC art. 242), et jamais comme un
   droit du débiteur.

4. LE CODE DE L'ARBITRAGE EST DÉGRADÉ. Ses 79 articles proviennent d'un OCR
   (`source_method: "ocr"`) de qualité inégale, et les numéros d'article y
   sont DUPLIQUÉS : l'article 2 apparaît six fois avec six textes différents,
   l'article 4 quatre fois, etc. — l'extraction a confondu les articles de la
   loi de promulgation, ceux de la mjalla et ceux des conventions annexées.
   Conséquence pratique : ce module ne cite l'arbitrage que par des articles
   dont il a vérifié la LISIBILITÉ et l'UNICITÉ, et il le signale à
   l'utilisateur. On ne fait pas signer une clause compromissoire sur un texte
   qu'on ne sait pas relire.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys
import unicodedata
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from typing import Any, Optional

# `retrieve` et `gate` vivent dans packages/legal et s'importent par nom court
# (gate.py fait `from retrieve import tokenize`). On met donc ce répertoire sur
# le chemin AVANT de les importer, plutôt que de dupliquer leur code ici : la
# garde anti-hallucination doit rester unique dans le projet.
_RACINE = pathlib.Path(__file__).resolve().parents[2]
_LEGAL = _RACINE / 'packages' / 'legal'
if str(_LEGAL) not in sys.path:
    sys.path.insert(0, str(_LEGAL))

import gate  # noqa: E402
from retrieve import search  # noqa: E402

CORPUS_DIR = _RACINE / 'corpus'


# ---------------------------------------------------------------------------
# La mention de projet. Une constante, pas une chaîne recopiée : même rigueur
# que packages/legal/notice.py, pour la même raison — elle doit être
# impossible à perdre par inadvertance, et un test la verrouille.
# ---------------------------------------------------------------------------

MENTION_PROJET = "PROJET — NON SIGNÉ"
MENTION_PROJET_AR = "مشروع — غير ممضى"

MENTION_PROJET_LONGUE = (
    "PROJET — NON SIGNÉ. Ce procès-verbal est un projet rédigé par Mizan à "
    "partir des pièces du dossier. Il n'a été validé par aucun professionnel "
    "accrédité, n'est signé par aucune partie, et ne produit en l'état AUCUN "
    "effet de droit. Une transaction (الصلح) ne se forme que par l'accord des "
    "parties (COC art. 1458) ; sa force entre elles lui vient de leur "
    "consentement (COC art. 242), jamais de sa rédaction par un logiciel."
)

MENTION_PROJET_LONGUE_AR = (
    "مشروع — غير ممضى. هذا المحضر مشروع حرّرته منظومة ميزان اعتمادا على "
    "أوراق الملف. لم يصادق عليه أي مهني معتمد، ولم يمضه أي من الطرفين، "
    "ولا يترتب عليه في حالته الراهنة أي أثر قانوني. الصلح لا ينعقد إلا "
    "بتراضي الطرفين طبق الفصل 1458 من مجلة الالتزامات والعقود."
)

AVERTISSEMENT_IA = (
    "Cet avis a été préparé par un agent logiciel. Un agent logiciel ne "
    "concilie pas, ne médie pas et n'arbitre pas : ces offices supposent une "
    "personne accréditée qui engage sa responsabilité. L'avis ci-dessous est "
    "une PROPOSITION de termes, motivée et sourcée. Elle ne lie personne. "
    "Seule la validation d'un professionnel accrédité, suivie de la signature "
    "des parties, fait naître la transaction."
)

AVERTISSEMENT_SOURCES = (
    "Les articles cités sont reproduits mot pour mot depuis le corpus des "
    "codes tunisiens indexé par Mizan. Aucun modèle de langage n'énonce ici "
    "une règle de droit ni ne compose une référence."
)

# Délai conventionnel laissé aux parties pour se prononcer sur un projet de
# termes. Il n'est fixé par AUCUN texte du corpus : c'est un délai d'usage, et
# il est nommé comme tel partout où il apparaît, sans quoi il se lirait comme
# un délai légal qu'aucun article ne fonde.
DELAI_REPONSE_USAGE_JOURS = 15

# Bande d'abattement transactionnel proposée par défaut lorsque le débiteur
# conteste la qualité de l'ouvrage sans chiffrer sa contestation. CE N'EST PAS
# UNE RÈGLE DE DROIT : aucun article du corpus ne fixe de taux. C'est un point
# de départ de négociation, explicitement présenté comme tel, et que le
# professionnel accrédité est libre d'écarter.
BANDE_ABATTEMENT_QUALITE = (0.10, 0.25)

NBSP = '\u00a0'
MOIS_FR = ['', 'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
           'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre']


# ---------------------------------------------------------------------------
# Erreurs. On lève quand l'entrée décrit une situation qui n'est pas un litige,
# pas quand elle décrit un litige difficile.
# ---------------------------------------------------------------------------

class LitigeInvalide(ValueError):
    """L'objet soumis n'est pas un litige transigeable.

    Réservé aux cas où il n'y a RIEN à régler : pas de créance (montant nul ou
    négatif), ou une seule et même personne des deux côtés. Une créance
    prescrite, une position vide ou une date manquante ne tombent pas ici :
    ce sont des litiges difficiles, et un moteur de règlement amiable doit
    savoir les traiter en s'abstenant, pas en refusant de s'ouvrir.
    """


# ---------------------------------------------------------------------------
# Ancrage dans le corpus : la seule porte par laquelle un article peut entrer.
# ---------------------------------------------------------------------------

_DIAC = re.compile(r'[\u064B-\u0652\u0640]')
_INCIPIT = re.compile(r'الفصل\s*(\d+)')
_CACHE_CORPUS: dict[tuple[str, int], list[dict]] = {}


def _charger_corpus() -> dict[tuple[str, int], list[dict]]:
    """Indexe le corpus par (code_id, numéro d'article).

    PIÈGE DU CORPUS, et il coûte cher si on l'ignore : la clé `article` est un
    INT, pas une str. Un lookup avec '1458' renvoie silencieusement rien, et
    le moteur croit de bonne foi que l'article n'existe pas — donc s'abstient
    alors que le droit le fonde. La conversion est faite ici, une fois.

    La valeur est une LISTE et non un dict unique : dans le Code de
    l'Arbitrage, plusieurs entrées portent le même numéro (voir le préambule
    du module). Écraser silencieusement les doublons reviendrait à citer un
    texte au hasard sous un numéro d'article.
    """
    if _CACHE_CORPUS:
        return _CACHE_CORPUS
    for fichier in sorted(CORPUS_DIR.glob('*.jsonl')):
        with fichier.open(encoding='utf-8') as fh:
            for ligne in fh:
                doc = json.loads(ligne)
                cle = (doc['code_id'], int(doc['article']))
                _CACHE_CORPUS.setdefault(cle, []).append(doc)
    return _CACHE_CORPUS


def _normaliser(texte: str) -> str:
    """Normalisation arabe minimale, pour comparer des textes, pas les citer."""
    texte = unicodedata.normalize('NFKC', texte)
    return _DIAC.sub('', texte).replace('\u200f', '').strip()


@dataclass(frozen=True)
class SourceLegale:
    """Un article du corpus, relu à la source et cité tel quel.

    Immuable à dessein (`frozen=True`) : une citation qu'un appelant pourrait
    modifier après coup n'est plus une citation. `extrait_ar` est un extrait
    VERBATIM du corpus ; il n'est ni reformulé, ni traduit, ni complété.
    `commentaire_fr` est notre lecture — elle est nommée comme telle et se
    lit à côté du texte, jamais à sa place.
    """
    code_id: str
    article: int
    citation_ar: str
    code_fr: str
    extrait_ar: str
    label_fr: str
    short_fr: str
    commentaire_fr: str
    fiabilite: str  # 'texte-natif' | 'ocr-degrade'

    def to_dict(self) -> dict:
        return asdict(self)


def _ancrer(code_id: str, article: int, label_fr: str, short_fr: str,
            commentaire_fr: str, incipit_attendu: str | None = None
            ) -> Optional[SourceLegale]:
    """Relit l'article DANS le corpus et le rend citable — ou rend None.

    C'est la seule fonction du module qui a le droit de produire une citation.
    Elle refuse, plutôt que de deviner, dans quatre cas :

      1. Le couple (code, numéro) n'existe pas dans le corpus.
      2. Le numéro est ambigu (plusieurs textes différents sous le même
         numéro, cas du Code de l'Arbitrage) et aucune levée d'ambiguïté n'a
         été fournie par `incipit_attendu`.
      3. L'article ne commence pas par « الفصل <n> » : l'extraction a dérapé,
         on ne sait plus quel texte on tient.
      4. `incipit_attendu` est fourni et ne se retrouve pas dans le texte.

    Le retour None n'est pas une panne : c'est l'abstention, et l'appelant la
    traite comme un résultat légitime.
    """
    candidats = _charger_corpus().get((code_id, int(article)), [])
    if not candidats:
        return None

    # Ne garder que les entrées dont l'incipit confirme le numéro : c'est le
    # seul contrôle qui distingue un article correctement extrait d'un
    # fragment recollé sous un mauvais numéro.
    coherents = []
    for doc in candidats:
        m = _INCIPIT.search(doc['text_ar'][:60])
        if m and int(m.group(1)) == int(article):
            coherents.append(doc)
    if not coherents:
        return None

    if incipit_attendu:
        attendu = _normaliser(incipit_attendu)
        coherents = [d for d in coherents if attendu in _normaliser(d['text_ar'])]
        if not coherents:
            return None

    if len(coherents) > 1:
        # Ambiguïté non levée : plusieurs textes portent ce numéro. On ne
        # choisit pas à pile ou face le texte qu'on va faire signer.
        return None

    doc = coherents[0]
    ocr = doc.get('source_method') == 'ocr' or doc.get('source', '').startswith('ocr')
    return SourceLegale(
        code_id=doc['code_id'],
        article=int(doc['article']),
        citation_ar=doc['citation_ar'],
        code_fr=doc['code_fr'],
        extrait_ar=doc['text_ar'].strip(),
        label_fr=label_fr,
        short_fr=short_fr,
        commentaire_fr=commentaire_fr,
        fiabilite='ocr-degrade' if ocr else 'texte-natif',
    )


def verifier_ancrage_bm25(requete_ar: str, source: SourceLegale) -> dict:
    """Contre-épreuve : le corpus retrouve-t-il cet article par la recherche ?

    L'ancrage direct (`_ancrer`) prouve que l'article existe et qu'on le cite
    correctement. Il ne prouve pas qu'il est PERTINENT pour la question posée.
    Cette fonction rejoue donc la recherche BM25 du projet
    (packages/legal/retrieve.py) et lui applique la garde anti-hallucination
    (packages/legal/gate.py, MIN_SCORE=3.0, MIN_MATCHED=2), puis vérifie que
    l'article ancré figure bien dans les résultats.

    Deux preuves indépendantes valent mieux qu'une : l'une dit « ce texte est
    bien celui-là », l'autre dit « et il répond bien à cette question-là ».
    """
    hits = search(requete_ar, k=8)
    verdict = gate.evaluate(requete_ar, hits)
    rang = None
    for i, h in enumerate(hits):
        if h['code_id'] == source.code_id and int(h['article']) == source.article:
            rang = i + 1
            break
    return {
        'requete_ar': requete_ar,
        'gate_grounded': verdict['grounded'],
        'gate_motif': verdict['reason'],
        'meilleur_score': verdict['best_score'],
        'rang_de_larticle': rang,
        'retrouve': rang is not None,
    }


# ---------------------------------------------------------------------------
# Les trois voies. Ce qui les distingue est juridique, pas cosmétique.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Voie:
    """Une voie de règlement amiable, et ce qui la distingue en droit.

    `fondee_dans_corpus` est le champ qui compte : il dit si les 4087 articles
    indexés organisent réellement cette voie, ou si nous la décrivons d'après
    la pratique. Une interface qui ne ferait pas cette différence laisserait
    croire que la médiation civile est régie par un texte tunisien indexé ici.
    Elle ne l'est pas.
    """
    cle: str
    nom_fr: str
    nom_ar: str
    role_du_tiers: str
    effet_de_lissue: str
    qui_valide: str
    fondee_dans_corpus: bool
    reserve: str = ''

    def to_dict(self) -> dict:
        return asdict(self)


VOIES: dict[str, Voie] = {
    'conciliation': Voie(
        cle='conciliation',
        nom_fr='Conciliation',
        nom_ar='الصلح',
        role_du_tiers=(
            "Le conciliateur PROPOSE une solution. Il ne tranche pas et ne "
            "s'impose pas : il rapproche les positions et rédige les termes "
            "sur lesquels les parties se rejoignent."
        ),
        effet_de_lissue=(
            "L'accord obtenu est une transaction (الصلح). Il éteint les "
            "droits et actions sur lesquels il porte (COC art. 1467) et "
            "s'impose aux parties comme leur propre loi (COC art. 242). Il "
            "n'a pas, par lui-même, la force d'un jugement."
        ),
        qui_valide="Le conciliateur accrédité, puis les deux parties qui signent.",
        fondee_dans_corpus=True,
    ),
    'mediation': Voie(
        cle='mediation',
        nom_fr='Médiation',
        nom_ar='الوساطة',
        role_du_tiers=(
            "Le médiateur ne propose pas de solution : il conduit le dialogue "
            "pour que les parties trouvent elles-mêmes la leur. La solution "
            "leur appartient de bout en bout."
        ),
        effet_de_lissue=(
            "Si les parties s'entendent, l'accord se coule dans une "
            "transaction et prend alors les effets de l'article 1467 du COC. "
            "L'effet vient de la transaction, pas de la médiation."
        ),
        qui_valide="Le médiateur accrédité, puis les deux parties qui signent.",
        fondee_dans_corpus=False,
        reserve=(
            "AUCUN des 4087 articles indexés n'organise la médiation civile "
            "ou commerciale. Le terme « الوساطة » n'apparaît qu'une fois au "
            "corpus, au Code de commerce art. 601, où il désigne le courtage "
            "— un mandat commercial sans rapport avec le règlement des "
            "différends. Mizan décrit donc cette voie d'après la pratique, et "
            "ne la recommande pas sur le fondement du corpus. Faites vérifier "
            "le régime applicable par un professionnel."
        ),
    ),
    'arbitrage': Voie(
        cle='arbitrage',
        nom_fr='Arbitrage',
        nom_ar='التحكيم',
        role_du_tiers=(
            "L'arbitre TRANCHE. C'est la différence de nature avec les deux "
            "autres voies : il ne propose pas, il juge. Les parties lui ont "
            "confié ce pouvoir par une convention d'arbitrage."
        ),
        effet_de_lissue=(
            "La sentence arbitrale tranche le litige et s'impose aux parties. "
            "Elle suppose une convention d'arbitrage préalable ; à défaut, "
            "cette voie est fermée."
        ),
        qui_valide="Le tribunal arbitral, par une sentence motivée.",
        fondee_dans_corpus=True,
        reserve=(
            "Le Code de l'Arbitrage est présent au corpus (79 articles) mais "
            "son extraction est un OCR dégradé, et plusieurs numéros y sont "
            "dupliqués (l'article 2 apparaît six fois avec six textes "
            "distincts). Mizan ne cite ici que des articles dont elle a "
            "vérifié la lisibilité et l'unicité, et refuse de citer les "
            "autres. Ne faites pas signer de clause compromissoire sur la "
            "seule foi de ce corpus."
        ),
    ),
}


# ---------------------------------------------------------------------------
# Entrée : le litige.
# ---------------------------------------------------------------------------

@dataclass
class Partie:
    """Une partie au litige, et ce qu'elle soutient.

    `position` est laissée en texte libre et dans la langue de la partie —
    français, arabe ou mélange des deux. Le moteur ne prétend pas la
    comprendre : il la reproduit et, lorsqu'elle est vide, il le dit au lieu
    de combler le silence.
    """
    nom: str
    role: str = ''          # 'demandeur' | 'defendeur', à titre indicatif
    position: str = ''
    montant_reconnu: Optional[float] = None  # ce que la partie admet devoir

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Litige:
    """Le litige tel que les parties le soumettent.

    `date_facture` est optionnelle : une PME qui ne retrouve pas sa facture ne
    doit pas être bloquée à la porte. Son absence a une conséquence, et une
    seule — la prescription ne peut pas être calculée, et le moteur le dit.
    """
    montant_reclame: float
    nature: str
    demandeur: Partie
    defendeur: Partie
    date_facture: Optional[str] = None
    numero_facture: Optional[str] = None
    devise: str = 'DT'
    clause_arbitrage: bool = False
    lieu: str = 'Sfax'

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _valider(litige: Litige) -> None:
    """Refuse ce qui n'est pas un litige. Rien de plus.

    POURQUOI SI PEU DE REFUS. Un moteur de règlement amiable qui refuse les
    dossiers difficiles ne sert à rien : les dossiers difficiles sont
    précisément ceux qu'on cherche à régler à l'amiable. On ne refuse donc que
    l'impossible logique — une créance qui n'existe pas, ou un litige d'une
    personne contre elle-même (COC art. 1458 suppose deux « متصالحين », deux
    transigeants, donc deux personnes distinctes en contestation).
    """
    montant = litige.montant_reclame
    if montant is None or not isinstance(montant, (int, float)) or isinstance(montant, bool):
        raise LitigeInvalide(
            "Le montant réclamé doit être un nombre. Sans créance chiffrée, "
            "il n'y a pas de quantum sur lequel transiger."
        )
    if montant != montant:  # NaN
        raise LitigeInvalide("Le montant réclamé n'est pas un nombre exploitable.")
    if montant < 0:
        raise LitigeInvalide(
            f"Montant réclamé négatif ({montant}). Une créance négative n'est "
            f"pas une créance : si c'est le défendeur qui est créancier, "
            f"inversez les parties au lieu d'inverser le signe."
        )
    if montant == 0:
        raise LitigeInvalide(
            "Montant réclamé nul. Il n'y a rien à transiger : la transaction "
            "suppose, aux termes du COC art. 1458, une concession de chacun "
            "sur quelque chose. Sur zéro, il n'y a pas de concession possible."
        )

    d_nom = (litige.demandeur.nom or '').strip()
    f_nom = (litige.defendeur.nom or '').strip()
    if not d_nom or not f_nom:
        raise LitigeInvalide(
            "Les deux parties doivent être nommées : on ne rédige pas un "
            "procès-verbal de transaction au profit d'une personne inconnue."
        )
    if _normaliser(d_nom).casefold() == _normaliser(f_nom).casefold():
        raise LitigeInvalide(
            f"Demandeur et défendeur désignent la même personne ({d_nom!r}). "
            f"Il n'y a pas de contestation à lever : le COC art. 1458 suppose "
            f"deux transigeants distincts, chacun renonçant à quelque chose "
            f"vis-à-vis de l'autre."
        )


# ---------------------------------------------------------------------------
# Prescription. Reprise du régime déjà établi dans packages/legal.
# ---------------------------------------------------------------------------

PRESCRIPTION_JOURS = 365


def _prescription(litige: Litige, aujourdhui: date) -> dict:
    """Situe la créance dans le temps, ou dit qu'elle ne peut pas l'être.

    COC art. 403 : l'action des vendeurs et des propriétaires d'ateliers
    (أرباب المصانع) pour le prix de ce qu'ils ont livré se prescrit par 365
    jours. Un menuisier qui a livré un ouvrage tombe sous ce texte.

    POURQUOI CE CALCUL FIGURE DANS UN MOTEUR DE RÈGLEMENT AMIABLE. Parce que
    la prescription change complètement le rapport de force, et donc les
    termes raisonnables : une créance à trois semaines de l'extinction ne se
    négocie pas comme une créance à onze mois. Le taire serait un mauvais
    conseil déguisé en neutralité.
    """
    src = _ancrer(
        'coc', 403,
        "Prescription annale — prix des marchandises et ouvrages livrés",
        'COC art. 403',
        "Fixe à 365 jours l'extinction de l'action des vendeurs et des "
        "propriétaires d'ateliers pour le prix de ce qu'ils ont livré.",
    )
    if not litige.date_facture:
        return {
            'calculable': False,
            'motif': (
                "Aucune date de facture n'a été fournie : le point de départ "
                "du délai est inconnu, la prescription ne peut donc pas être "
                "calculée. Mizan ne la suppose pas. Fournissez la date de "
                "livraison ou de facturation, ou faites-la établir par le "
                "professionnel accrédité."
            ),
            'source': src.to_dict() if src else None,
        }
    try:
        depart = date.fromisoformat(litige.date_facture)
    except (TypeError, ValueError):
        return {
            'calculable': False,
            'motif': (
                f"Date de facture illisible ({litige.date_facture!r}) : "
                f"format attendu AAAA-MM-JJ. La prescription n'est pas "
                f"calculée plutôt que d'être devinée."
            ),
            'source': src.to_dict() if src else None,
        }
    echeance = depart + timedelta(days=PRESCRIPTION_JOURS)
    restants = (echeance - aujourdhui).days
    return {
        'calculable': True,
        'motif': None,
        'depart': depart.isoformat(),
        'echeance': echeance.isoformat(),
        'jours_restants': restants,
        'est_prescrite': restants < 0,
        'urgence': 'critique' if 0 <= restants <= 60 else ('passee' if restants < 0 else 'normale'),
        'source': src.to_dict() if src else None,
    }


# ---------------------------------------------------------------------------
# Les termes proposés.
# ---------------------------------------------------------------------------

@dataclass
class TermeReglement:
    """Un terme de règlement proposé, et l'état exact de son fondement.

    LES DEUX DRAPEAUX, ET POURQUOI ILS SONT SÉPARÉS. Un terme peut être fondé
    dans son PRINCIPE sans l'être dans son QUANTUM. Que la transaction suppose
    une concession réciproque est écrit au COC art. 1458 ; que cette
    concession soit de 15 % plutôt que de 22 % n'est écrit nulle part. Fondre
    les deux dans un seul booléen « sourcé » reviendrait à faire endosser au
    COC un chiffre qu'il ne contient pas — c'est exactement la forme
    d'hallucination la plus difficile à repérer, parce qu'elle s'accompagne
    d'une citation authentique.
    """
    cle: str
    intitule_fr: str
    intitule_ar: str
    detail_fr: str
    principe_fonde: bool
    quantum_fonde: bool
    sources: list = field(default_factory=list)     # list[dict]
    controles: list = field(default_factory=list)   # contre-épreuves BM25
    reserve: str = ''
    valeur: Any = None

    def to_dict(self) -> dict:
        return asdict(self)


def _fmt_montant(v: float) -> str:
    """9520.0 -> '9 520,000' : format monétaire français, espaces insécables."""
    return f'{v:,.3f}'.replace(',', NBSP).replace('.', ',')


def _fmt_date_fr(iso: str | date) -> str:
    """Date en français juridique, ou la valeur brute si elle est illisible.

    NE LÈVE PAS. Une date mal saisie par l'utilisateur (« 12/05/2026 ») a déjà
    été signalée dans le bloc prescription ; elle ne doit pas, en plus, faire
    échouer la rédaction du procès-verbal. Le moteur reproduit alors la saisie
    telle quelle : le professionnel accrédité la verra et la corrigera.
    """
    if isinstance(iso, date):
        return f'{iso.day} {MOIS_FR[iso.month]} {iso.year}'
    try:
        d = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return str(iso)
    return f'{d.day} {MOIS_FR[d.month]} {d.year}'


def _position_exploitable(p: Partie) -> bool:
    """Une position vide n'est pas une position contraire : c'est un silence.

    Distinguer les deux est la condition pour ne pas inventer un désaccord —
    ni, à l'inverse, un accord.
    """
    return bool((p.position or '').strip()) or p.montant_reconnu is not None


def _terme_montant(litige: Litige, controler: bool) -> TermeReglement:
    """Le montant transigé : principe fondé, quantum non fondé. Toujours.

    COC art. 1458 fonde la concession réciproque comme essence de la
    transaction. COC art. 1467 en tire la conséquence décisive et rarement
    comprise des PME : « والصلح بشيء من الدين كالإبراء في الباقي » — transiger
    sur une partie de la dette VAUT REMISE DU RESTE. Une fois signée, la
    transaction éteint le surplus ; on ne revient pas réclamer la différence.
    C'est pour cela que ce terme, plus que tout autre, doit passer devant un
    professionnel avant signature.
    """
    sources, controles = [], []

    s1458 = _ancrer(
        'coc', 1458,
        "Définition de la transaction (الصلح) — concession réciproque",
        'COC art. 1458',
        "La transaction est un contrat destiné à lever le litige et à couper "
        "court à l'instance, par la renonciation de chacun des transigeants à "
        "une partie de ses prétentions, ou par la remise d'un bien ou d'un "
        "droit. La concession réciproque n'est pas une facilité de "
        "négociation : elle est de l'essence même du contrat.",
    )
    s1467 = _ancrer(
        'coc', 1467,
        "Effets de la transaction — extinction des droits et actions",
        'COC art. 1467',
        "La transaction éteint les droits et les actions sur lesquels elle "
        "porte ; transiger sur une partie de la dette vaut remise du surplus. "
        "Le créancier qui signe renonce définitivement à la différence.",
    )
    for s in (s1458, s1467):
        if s:
            sources.append(s.to_dict())

    if controler and s1458:
        controles.append(verifier_ancrage_bm25(
            'الصلح عقد وضع لرفع النزاع وقطع الخصومة تنازل المتصالحين', s1458))
    if controler and s1467:
        controles.append(verifier_ancrage_bm25(
            'يترتب على الصلح سقوط الحقوق والدعاوي الإبراء في الباقي', s1467))

    principe = s1458 is not None

    # Le quantum. S'il est chiffré par les parties, il vient d'elles ; sinon
    # c'est une bande conventionnelle, et elle est annoncée comme telle.
    reconnu = litige.defendeur.montant_reconnu
    montant = float(litige.montant_reclame)

    if reconnu is not None and 0 <= reconnu <= montant:
        bas = haut = float(reconnu)
        origine = (
            f"Le défendeur reconnaît devoir {_fmt_montant(bas)} "
            f"{litige.devise}. Ce chiffre vient de la partie elle-même, non "
            f"d'une estimation de Mizan."
        )
        reserve = (
            "Le montant reconnu par le défendeur est un point de départ, pas "
            "un accord : le demandeur n'y a pas consenti."
        )
    elif not _position_exploitable(litige.defendeur):
        bas = haut = montant
        origine = (
            "Le défendeur n'a exprimé aucune position et n'a chiffré aucune "
            "contestation. Mizan ne propose donc AUCUN abattement : proposer "
            "une remise à un créancier au vu du silence de son débiteur "
            "reviendrait à négocier contre lui."
        )
        reserve = (
            "ABSTENTION SUR LE QUANTUM. Le dossier ne contient pas la "
            "position du défendeur. Recueillez-la avant toute proposition "
            "chiffrée."
        )
    else:
        p_bas, p_haut = BANDE_ABATTEMENT_QUALITE
        bas = round(montant * (1 - p_haut), 3)
        haut = round(montant * (1 - p_bas), 3)
        origine = (
            f"Le défendeur conteste sans chiffrer. La bande proposée "
            f"({int(p_bas * 100)} % à {int(p_haut * 100)} % d'abattement) est "
            f"un point de départ de négociation issu de la pratique, PAS "
            f"d'un texte."
        )
        reserve = (
            "QUANTUM NON FONDÉ EN DROIT. Aucun article du corpus ne fixe de "
            "taux d'abattement transactionnel. La bande ci-dessus n'engage "
            "pas Mizan et n'a aucune autorité : il appartient au "
            "professionnel accrédité de l'arrêter au vu des pièces, et le cas "
            "échéant d'une expertise contradictoire."
        )

    detail = (
        f"Montant réclamé : {_fmt_montant(montant)} {litige.devise}. "
        f"Fourchette de règlement proposée : de {_fmt_montant(bas)} à "
        f"{_fmt_montant(haut)} {litige.devise}. {origine} "
        f"ATTENTION — aux termes du COC art. 1467, transiger sur une partie "
        f"de la dette vaut remise du surplus : le solde non transigé sera "
        f"définitivement éteint par la signature."
    ) if principe else (
        "Le fondement de la transaction n'a pas pu être ancré dans le "
        "corpus : aucun montant transigé n'est proposé."
    )

    return TermeReglement(
        cle='montant_transige',
        intitule_fr='Montant transigé',
        intitule_ar='مبلغ الصلح',
        detail_fr=detail,
        principe_fonde=principe,
        quantum_fonde=False,  # invariant : aucun texte ne fixe de quantum
        sources=sources,
        controles=controles,
        reserve=reserve,
        valeur={'plancher': bas, 'plafond': haut, 'reclame': montant,
                'devise': litige.devise} if principe else None,
    )


def _terme_echeancier(litige: Litige, aujourdhui: date, controler: bool) -> TermeReglement:
    """L'échéancier : une stipulation, jamais un droit du débiteur.

    RECHERCHE FAITE, RÉSULTAT NÉGATIF : « التقسيط » (paiement échelonné) et
    « نظرة الميسرة » (délai de grâce) n'apparaissent nulle part dans les 4087
    articles indexés. Aucun texte du corpus n'ouvre au débiteur un droit à
    l'échelonnement, et Mizan n'en invente pas.

    Ce qui est fondé, c'est autre chose, et c'est suffisant : le COC art. 242
    donne aux conventions régulièrement formées force de loi entre les
    parties. Un échéancier vaut donc parce que les parties l'ont voulu — pas
    parce qu'un article l'accorde. La nuance est tout sauf académique : elle
    dit au débiteur qu'il ne peut pas l'exiger, et au créancier qu'il pourra
    l'opposer une fois signé.
    """
    sources, controles = [], []
    s242 = _ancrer(
        'coc', 242,
        "Force obligatoire du contrat",
        'COC art. 242',
        "Ce qui est régulièrement formé tient lieu de loi entre les parties "
        "et ne peut être défait que de leur consentement mutuel ou dans les "
        "cas prévus par la loi. C'est ce texte — et non un droit à "
        "l'échelonnement — qui donnera sa force à l'échéancier une fois "
        "signé.",
    )
    s1471 = _ancrer(
        'coc', 1471,
        "Inexécution de la transaction — exécution forcée ou résolution",
        'COC art. 1471',
        "Si l'une des parties n'exécute pas ce à quoi elle s'est engagée dans "
        "la transaction, l'autre peut en demander l'exécution si elle est "
        "encore possible, sinon la résolution, avec dommages-intérêts dans "
        "les deux cas. C'est la sanction de l'échéancier non tenu.",
    )
    for s in (s242, s1471):
        if s:
            sources.append(s.to_dict())
    if controler and s1471:
        controles.append(verifier_ancrage_bm25(
            'إذا لم يوف أحد الطرفين بما التزم به في الصلح طلب الفسخ تعويض', s1471))

    montant = float(litige.montant_reclame)
    # Le découpage est conventionnel et présenté comme tel. Il est indexé sur
    # le montant parce que c'est la pratique, pas parce qu'un texte l'ordonne.
    if montant <= 1000:
        n = 1
    elif montant <= 5000:
        n = 3
    elif montant <= 20000:
        n = 4
    else:
        n = 6

    premier = aujourdhui + timedelta(days=30)
    echeances = []
    for i in range(n):
        d = date(
            premier.year + (premier.month - 1 + i) // 12,
            (premier.month - 1 + i) % 12 + 1,
            min(premier.day, 28),  # 28 : aucune échéance ne saute un mois court
        )
        echeances.append(d.isoformat())

    return TermeReglement(
        cle='echeancier',
        intitule_fr='Échéancier de paiement',
        intitule_ar='رزنامة الخلاص',
        detail_fr=(
            f"Règlement proposé en {n} échéance(s) mensuelle(s) égale(s), la "
            f"première trente jours après la signature, soit à compter du "
            f"{_fmt_date_fr(echeances[0])}. Le montant de chaque échéance se "
            f"déduira du montant transigé, une fois celui-ci arrêté par le "
            f"professionnel accrédité. Cet échéancier n'est pas un droit du "
            f"débiteur : c'est une stipulation, qui ne vaudra que si le "
            f"créancier y consent — et qui, une fois signée, tiendra lieu de "
            f"loi entre les parties (COC art. 242)."
        ),
        principe_fonde=s242 is not None,
        quantum_fonde=False,
        sources=sources,
        controles=controles,
        reserve=(
            "NOMBRE ET DATES NON FONDÉS EN DROIT. Les termes « التقسيط » "
            "(échelonnement) et « نظرة الميسرة » (délai de grâce) sont "
            "ABSENTS des 4087 articles indexés : aucun texte du corpus "
            "n'ouvre au débiteur un droit à l'échelonnement, ni n'en fixe la "
            "durée. Le découpage ci-dessus est une proposition de pratique."
        ),
        valeur={'nombre_echeances': n, 'dates': echeances},
    )


def _terme_forme(litige: Litige, controler: bool) -> TermeReglement:
    """La forme de l'acte — et une nuance que beaucoup de modèles ratent.

    Le COC art. 1466 n'impose PAS l'écrit à toute transaction. Il l'impose
    lorsque la transaction crée, transfère ou modifie des droits sur des biens
    susceptibles d'hypothèque, et subordonne alors l'opposabilité aux tiers à
    l'enregistrement. Écrire « la transaction doit être écrite (COC 1466) »
    serait une citation authentique au service d'une affirmation fausse.

    Pour une créance de travaux réglée en argent, l'écrit reste donc
    vivement recommandé — mais comme preuve, pas comme condition de validité.
    """
    sources, controles = [], []
    s1466 = _ancrer(
        'coc', 1466,
        "Forme écrite et enregistrement — transactions portant sur des biens "
        "susceptibles d'hypothèque",
        'COC art. 1466',
        "Lorsque la transaction crée, transfère ou modifie des droits sur des "
        "choses susceptibles d'hypothèque, elle doit être passée par écrit, "
        "et n'est opposable aux tiers qu'une fois enregistrée dans les formes "
        "prévues pour la vente. HORS CE CAS — donc pour une créance de "
        "travaux réglée en argent — le texte n'impose pas l'écrit à peine de "
        "nullité.",
    )
    if s1466:
        sources.append(s1466.to_dict())
    if controler and s1466:
        controles.append(verifier_ancrage_bm25('الصلح كتابة تسجيل الرهن العقاري', s1466))

    return TermeReglement(
        cle='forme_de_lacte',
        intitule_fr="Forme de l'acte",
        intitule_ar='شكل العقد',
        detail_fr=(
            "Le présent litige porte sur le paiement d'une somme d'argent au "
            "titre de travaux, et non sur des droits relatifs à un bien "
            "susceptible d'hypothèque. Le COC art. 1466 n'impose donc pas ici "
            "l'écrit à peine de nullité. L'écrit reste néanmoins "
            "indispensable en pratique : c'est lui qui prouvera l'étendue de "
            "la renonciation le jour où l'une des parties la contestera. "
            "Signature des deux parties et du professionnel accrédité, un "
            "exemplaire original pour chacun."
        ),
        principe_fonde=s1466 is not None,
        quantum_fonde=False,
        sources=sources,
        controles=controles,
        reserve=(
            "Ne pas lire le COC art. 1466 comme une exigence générale "
            "d'écrit : il ne vise que les transactions portant sur des biens "
            "susceptibles d'hypothèque."
        ),
        valeur={'ecrit_exige_a_peine_de_nullite': False,
                'enregistrement_requis_pour_opposabilite_aux_tiers': False},
    )


def _terme_objet_du_differend(litige: Litige, controler: bool) -> Optional[TermeReglement]:
    """Le droit de fond propre à la nature du litige — ou rien.

    Seul le louage d'ouvrage est ancré ici, parce que c'est le seul régime que
    le corpus permet de citer avec certitude pour ce type de dossier. Pour
    toute autre nature, la fonction rend None : le moteur préfère n'avoir rien
    à dire sur le fond plutôt que d'appliquer par analogie un texte qui ne
    vise pas le cas.
    """
    nature = _normaliser(litige.nature or '').casefold()
    mots_ouvrage = ('menuiserie', 'travaux', 'ouvrage', 'chantier', 'artisan',
                    'fabrication', 'pose', 'installation', 'صنع', 'نجارة')
    if not any(m in nature for m in mots_ouvrage):
        return None

    sources, controles = [], []
    s875 = _ancrer(
        'coc', 875,
        "Défaut ou insuffisance de l'ouvrage — options du maître d'ouvrage",
        'COC art. 875',
        "Si l'ouvrage est défectueux ou incomplet, le maître d'ouvrage peut "
        "refuser de le recevoir ou le rendre dans la semaine de sa réception, "
        "afin que l'entrepreneur le reprenne dans un délai raisonnable. Passé "
        "ce délai sans exécution, il a le choix entre TROIS options : faire "
        "réparer aux frais de l'entrepreneur, demander la RÉDUCTION DU PRIX "
        "(حط الثمن), ou demander la résolution — avec dommages-intérêts s'il "
        "y a lieu.",
        # LEVÉE D'AMBIGUÏTÉ, ET ELLE EST NÉCESSAIRE : le corpus contient DEUX
        # entrées sous « coc / 875 ». La seconde est un fragment de trois mots
        # (« الفصل 875 فإنه يتنزل عليه ») recollé par l'extracteur. Sans cet
        # incipit, `_ancrer` refuse — à juste titre — de choisir entre les
        # deux, et le moteur perd l'article qui fonde toute la réduction de
        # prix. On désigne donc le bon texte par une locution qu'il est seul à
        # porter, au lieu de prendre le premier venu.
        incipit_attendu='حط الثمن',
    )
    s874 = _ancrer(
        'coc', 874,
        "Garantie de l'entrepreneur pour les vices de son ouvrage",
        'COC art. 874',
        "L'entrepreneur répond des vices et insuffisances de son travail.",
    )
    for s in (s874, s875):
        if s:
            sources.append(s.to_dict())
    if controler and s875:
        controles.append(verifier_ancrage_bm25(
            'إذا كان في المصنوع عيب أو نقص حط الثمن فسخ الاتفاق', s875))

    if not sources:
        return None

    return TermeReglement(
        cle='objet_du_differend',
        intitule_fr="Fondement de la contestation de qualité",
        intitule_ar='أساس النزاع في جودة المصنوع',
        detail_fr=(
            "Le litige relève du louage d'ouvrage. La contestation de qualité "
            "n'est donc pas un simple argument de négociation : le COC "
            "art. 875 ouvre au maître d'ouvrage, si le défaut est établi et "
            "si les délais du texte ont été respectés, un droit à la "
            "RÉDUCTION DU PRIX. C'est ce texte qui rend ici une transaction à "
            "montant réduit juridiquement cohérente, et non un simple partage "
            "du différend en deux. Le professionnel accrédité vérifiera que "
            "les conditions du texte sont réunies — notamment le délai d'une "
            "semaine après réception — avant d'en tirer un abattement."
        ),
        principe_fonde=True,
        quantum_fonde=False,
        sources=sources,
        controles=controles,
        reserve=(
            "Le COC art. 875 fonde le PRINCIPE d'une réduction du prix. Il ne "
            "fixe pas son montant, qui suppose l'appréciation du défaut — "
            "au besoin par expertise contradictoire."
        ),
        valeur={'regime': 'louage_ouvrage', 'reduction_du_prix_ouverte': True},
    )


# ---------------------------------------------------------------------------
# Choix de la voie.
# ---------------------------------------------------------------------------

def _recommander_voie(litige: Litige, prescription: dict, controler: bool) -> dict:
    """Dit laquelle des trois voies est adaptée, et pourquoi — ou s'abstient.

    L'arbitrage n'est pas une option qu'on choisit à la volée : il suppose une
    convention d'arbitrage. Le Code de l'Arbitrage art. 7 la prévoit pour un
    litige déjà né comme par clause compromissoire, en matière d'obligations
    et d'échanges civils et commerciaux. Sans cette convention, la voie est
    fermée, et il serait trompeur de la « recommander ».
    """
    sources, controles = [], []
    motifs: list[str] = []

    s_arb = _ancrer(
        'arbitrage', 7,
        "Champ de la convention d'arbitrage",
        "Code de l'Arbitrage art. 7",
        "L'arbitrage peut être convenu pour un litige déterminé déjà né, "
        "comme être stipulé par clause compromissoire pour les litiges à "
        "naître en matière d'obligations et d'échanges civils et commerciaux, "
        "ainsi qu'entre associés à propos de la société.",
    )
    if controler and s_arb:
        controles.append(verifier_ancrage_bm25('الاتفاق على التحكيم نزاع معين شرط تحكيمي', s_arb))

    if litige.clause_arbitrage and s_arb:
        retenue = 'arbitrage'
        sources.append(s_arb.to_dict())
        motifs.append(
            "Les parties sont liées par une convention d'arbitrage. "
            "L'arbitrage est donc ouvert (Code de l'Arbitrage art. 7). Il "
            "reste la voie la plus lourde : l'arbitre tranchera, et sa "
            "sentence s'imposera, là où une conciliation laisserait aux "
            "parties la maîtrise de l'issue."
        )
    else:
        retenue = 'conciliation'
        if not litige.clause_arbitrage:
            motifs.append(
                "Aucune convention d'arbitrage n'est invoquée : la voie "
                "arbitrale est fermée, elle suppose l'accord préalable des "
                "parties pour confier le litige à un arbitre."
            )
        motifs.append(
            "Le différend porte sur le quantum d'une créance et sur la "
            "qualité d'un ouvrage — un désaccord chiffrable, où un tiers peut "
            "utilement PROPOSER un terrain d'entente. C'est la définition "
            "même de l'office du conciliateur. L'accord prendra la forme "
            "d'une transaction au sens du COC art. 1458."
        )

    if prescription.get('calculable') and prescription.get('est_prescrite'):
        motifs.append(
            f"ALERTE — la créance paraît PRESCRITE depuis "
            f"{abs(prescription['jours_restants'])} jours (échéance au "
            f"{_fmt_date_fr(prescription['echeance'])}, COC art. 403). Cela "
            f"n'interdit pas de transiger : le débiteur peut vouloir solder "
            f"la relation. Mais il n'y est plus contraint, et il peut opposer "
            f"la prescription à toute action. La conciliation devient alors "
            f"la seule voie utile — et le créancier doit savoir qu'il négocie "
            f"sans le rapport de force qu'il croit avoir. Si le délai a été "
            f"interrompu (reconnaissance de dette, paiement partiel, acte "
            f"d'huissier), faites-le établir : l'interruption ne se présume "
            f"pas."
        )
    elif prescription.get('calculable') and prescription.get('urgence') == 'critique':
        motifs.append(
            f"Le délai de prescription expire le "
            f"{_fmt_date_fr(prescription['echeance'])}, dans "
            f"{prescription['jours_restants']} jours. Une conciliation menée "
            f"sans interrompre le délai peut faire perdre la créance pendant "
            f"la discussion : ce point doit être traité AVANT d'ouvrir la "
            f"négociation."
        )

    return {
        'voie_retenue': retenue,
        'voie': VOIES[retenue].to_dict(),
        'motifs': motifs,
        'sources': sources,
        'controles': controles,
        'voies_examinees': {c: VOIES[c].to_dict() for c in VOIES},
        'arbitrage_ouvert': bool(litige.clause_arbitrage and s_arb),
        'mediation_fondee_dans_corpus': VOIES['mediation'].fondee_dans_corpus,
    }


# ---------------------------------------------------------------------------
# L'avis, l'espace de validation, le dossier.
# ---------------------------------------------------------------------------

@dataclass
class AvisAgent:
    """CE QUE LA MACHINE PROPOSE. Non contraignant, et le type le dit.

    Aucun champ de cette classe ne parle d'effet juridique, de décision ou de
    signature : elle n'a pas le vocabulaire pour. Un avis qui pourrait se
    déclarer exécutoire serait un avis mal typé.
    """
    emis_par: str
    emis_le: str
    nature_de_lacte: str
    contraignant: bool
    avertissement: str
    litige: dict
    voie_recommandee: dict
    termes: list = field(default_factory=list)
    prescription: dict = field(default_factory=dict)
    abstentions: list = field(default_factory=list)
    avertissement_sources: str = AVERTISSEMENT_SOURCES

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EspaceValidation:
    """L'ESPACE DU PROFESSIONNEL ACCRÉDITÉ. Vide tant qu'il n'a pas signé.

    Ce n'est pas une métaphore : à la construction, tous les champs
    d'identification valent None et `signe` vaut False. Le seul moyen de les
    renseigner est `valider()`, qui exige un nom, une qualité et un numéro
    d'accréditation. Un espace de validation à moitié rempli n'existe pas.
    """
    qualites_admises: tuple = ('conciliateur', 'mediateur', 'arbitre')
    valide_par: Optional[str] = None
    qualite: Optional[str] = None
    numero_accreditation: Optional[str] = None
    valide_le: Optional[str] = None
    signature: Optional[str] = None
    observations: Optional[str] = None
    termes_retenus: Optional[list] = None
    signe: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DossierECMA:
    """Le dossier E-CMA : un avis d'un côté, un espace de validation de l'autre.

    LE POINT QUE LE JURY DOIT POUVOIR VÉRIFIER DANS LA STRUCTURE.
    `porte_effet_juridique` n'est PAS un champ. C'est une propriété calculée,
    sans setter, dérivée exclusivement de l'état de `validation`. Il n'existe
    aucune signature d'appel — constructeur, `to_dict()`, désérialisation —
    par laquelle un appelant pourrait la porter à True sans passer par
    `valider()`, c'est-à-dire sans qu'un professionnel identifié ait signé.

    La sortie du modèle ne porte jamais l'effet juridique. La validation
    humaine le porte. Ici, c'est une propriété du type, pas une consigne.
    """
    reference: str
    avis: AvisAgent
    validation: EspaceValidation
    mention_projet: str = MENTION_PROJET
    mention_projet_ar: str = MENTION_PROJET_AR

    @property
    def porte_effet_juridique(self) -> bool:
        """True si et seulement si un professionnel accrédité a signé.

        Lecture seule, par construction. Toute la promesse « l'IA propose, le
        droit dispose » tient dans cette propriété : tant qu'elle est fausse,
        le dossier n'est qu'un projet, quelle que soit la qualité de l'avis.
        """
        v = self.validation
        return bool(
            v.signe
            and v.valide_par
            and v.numero_accreditation
            and v.valide_le
        )

    @property
    def est_projet(self) -> bool:
        return not self.porte_effet_juridique

    def valider(self, nom: str, qualite: str, numero_accreditation: str,
                observations: str = '', termes_retenus: Optional[list] = None,
                le: Optional[str] = None) -> 'DossierECMA':
        """Le seul chemin par lequel un dossier acquiert un effet juridique.

        Exige les trois éléments qui font qu'une validation est imputable à
        quelqu'un : un nom, une qualité admise, un numéro d'accréditation
        vérifiable. Sans imputabilité, une « validation » n'est qu'un
        deuxième avis — et c'est précisément ce que ce module existe pour
        empêcher.
        """
        nom = (nom or '').strip()
        qualite = (qualite or '').strip().casefold()
        numero = (numero_accreditation or '').strip()
        if not nom:
            raise LitigeInvalide("La validation doit être nominative.")
        if qualite not in self.validation.qualites_admises:
            raise LitigeInvalide(
                f"Qualité {qualite!r} non admise. Seuls un conciliateur, un "
                f"médiateur ou un arbitre peuvent valider un dossier E-CMA."
            )
        if not numero:
            raise LitigeInvalide(
                "Un numéro d'accréditation est exigé : une validation qui "
                "n'est imputable à personne ne vaut pas mieux que l'avis "
                "qu'elle est censée contrôler."
            )
        self.validation.valide_par = nom
        self.validation.qualite = qualite
        self.validation.numero_accreditation = numero
        self.validation.valide_le = (le or date.today().isoformat())
        self.validation.signature = f'{nom} — {qualite} n° {numero}'
        self.validation.observations = observations or None
        self.validation.termes_retenus = termes_retenus
        self.validation.signe = True
        return self

    def to_dict(self) -> dict:
        """Sérialise le dossier — propriété calculée comprise.

        `porte_effet_juridique` figure dans le dict parce que l'API et l'UI en
        ont besoin, mais il y est RECALCULÉ à chaque appel depuis l'état de la
        validation. Il n'est jamais relu d'un champ stocké : un dict trafiqué
        ne peut donc pas remonter en objet porteur d'effet.
        """
        return {
            'reference': self.reference,
            'mention_projet': self.mention_projet,
            'mention_projet_ar': self.mention_projet_ar,
            'porte_effet_juridique': self.porte_effet_juridique,
            'est_projet': self.est_projet,
            'avis': self.avis.to_dict(),
            'validation': self.validation.to_dict(),
        }


# ---------------------------------------------------------------------------
# L'API du module.
# ---------------------------------------------------------------------------

def proposer_reglement(litige: Litige, aujourdhui: Optional[date] = None,
                       controler_ancrage: bool = False) -> DossierECMA:
    """Produit un AVIS de règlement amiable. Ne décide rien.

    Rend toujours un `DossierECMA` dont `porte_effet_juridique` vaut False :
    c'est l'invariant du module, et il est vérifié par un test dédié sur
    l'ensemble des entrées, y compris hostiles.

    `controler_ancrage=True` rejoue en plus, pour chaque article cité, la
    recherche BM25 du projet et la garde anti-hallucination
    (packages/legal/gate.py). C'est la contre-épreuve : plus lent, mais c'est
    elle qu'on montre quand on nous demande de prouver qu'aucune citation
    n'est composée.

    Lève `LitigeInvalide` quand l'objet soumis n'est pas un litige — et
    seulement dans ce cas.
    """
    _valider(litige)
    aujourdhui = aujourdhui or date.today()

    prescription = _prescription(litige, aujourdhui)
    recommandation = _recommander_voie(litige, prescription, controler_ancrage)

    termes: list[TermeReglement] = []
    fond = _terme_objet_du_differend(litige, controler_ancrage)
    if fond:
        termes.append(fond)
    termes.append(_terme_montant(litige, controler_ancrage))
    termes.append(_terme_echeancier(litige, aujourdhui, controler_ancrage))
    termes.append(_terme_forme(litige, controler_ancrage))

    # Abstentions : on les énumère au lieu de les taire. Une abstention
    # explicite est une information ; une abstention silencieuse est un trou.
    abstentions: list[str] = []
    if fond is None:
        abstentions.append(
            f"Nature du litige ({litige.nature!r}) : aucun régime de fond n'a "
            f"pu être ancré dans le corpus pour ce type de différend. Mizan "
            f"ne transpose pas par analogie un texte qui ne vise pas le cas. "
            f"Le professionnel accrédité qualifiera le contrat."
        )
    if not _position_exploitable(litige.defendeur):
        abstentions.append(
            "Le défendeur n'a exprimé aucune position : aucun abattement "
            "n'est proposé. Négocier une remise au vu du silence du débiteur "
            "serait négocier contre le créancier."
        )
    if not _position_exploitable(litige.demandeur):
        abstentions.append(
            "Le demandeur n'a pas exposé sa position : les termes ci-dessous "
            "ne reposent que sur les pièces comptables."
        )
    if not prescription.get('calculable'):
        abstentions.append(f"Prescription non calculée — {prescription['motif']}")
    abstentions.append(
        "Quantum de la remise : AUCUN article du corpus ne fixe de taux "
        "d'abattement transactionnel. Toute fourchette proposée relève de la "
        "pratique et doit être arrêtée par le professionnel accrédité."
    )
    abstentions.append(
        "Échelonnement : « التقسيط » et « نظرة الميسرة » sont absents des "
        "4087 articles indexés. Aucun droit du débiteur à l'échelonnement "
        "n'est fondé par le corpus."
    )
    if not VOIES['mediation'].fondee_dans_corpus:
        abstentions.append(
            "Médiation civile et commerciale : aucun des 4087 articles "
            "indexés ne l'organise. Mizan la décrit d'après la pratique et ne "
            "la recommande pas sur le fondement du corpus."
        )

    # La référence doit être STABLE : le même litige, soumis deux fois, doit
    # porter le même numéro de dossier, sinon on ne peut ni le retrouver ni en
    # parler. `hash()` sur une chaîne est randomisé à chaque processus Python
    # (PYTHONHASHSEED) — il donnait deux références différentes pour le même
    # dossier d'un appel à l'autre. On prend donc une empreinte déterministe.
    empreinte = hashlib.sha256(
        f"{litige.demandeur.nom}|{litige.defendeur.nom}|"
        f"{litige.montant_reclame}|{litige.date_facture}".encode('utf-8')
    ).hexdigest()[:6].upper()
    ref = f"ECMA-{aujourdhui.isoformat().replace('-', '')}-{empreinte}"

    avis = AvisAgent(
        emis_par='Mizan — agent logiciel (E-CMA)',
        emis_le=aujourdhui.isoformat(),
        nature_de_lacte="Avis de règlement amiable — PROPOSITION NON CONTRAIGNANTE",
        contraignant=False,
        avertissement=AVERTISSEMENT_IA,
        litige=litige.to_dict(),
        voie_recommandee=recommandation,
        termes=[t.to_dict() for t in termes],
        prescription=prescription,
        abstentions=abstentions,
    )

    return DossierECMA(reference=ref, avis=avis, validation=EspaceValidation())


# ---------------------------------------------------------------------------
# Le procès-verbal de transaction, bilingue.
# ---------------------------------------------------------------------------

def rediger_pv(dossier: DossierECMA) -> dict:
    """Rédige le projet de procès-verbal de transaction, en français et en arabe.

    La mention « PROJET — NON SIGNÉ » / « مشروع — غير ممضى » est portée en
    tête, en pied, et dans le champ `mention` des deux versions, et elle
    disparaît si et seulement si `dossier.porte_effet_juridique` est vrai —
    c'est-à-dire si et seulement si un professionnel accrédité a signé. Comme
    cette propriété n'est pas écrivable, la mention ne peut pas être retirée
    autrement qu'en validant. Même rigueur que packages/legal/notice.py, où
    la mention de non-signification obéit à la même règle.

    Rend un dict à deux versions plutôt qu'une chaîne unique : mélanger du
    français et de l'arabe dans un même flux de texte produit un rendu bidi
    illisible, et un PV illisible ne se fait pas signer.
    """
    projet = dossier.est_projet
    avis = dossier.avis
    lit = avis.litige
    dem, deff = lit['demandeur'], lit['defendeur']
    montant = float(lit['montant_reclame'])
    devise = lit['devise']

    terme_montant = next((t for t in avis.termes if t['cle'] == 'montant_transige'), None)
    terme_ech = next((t for t in avis.termes if t['cle'] == 'echeancier'), None)

    # --- articles cités, dédoublonnés, dans l'ordre d'apparition -----------
    vus, articles = set(), []
    for t in avis.termes:
        for s in t['sources']:
            cle = (s['code_id'], s['article'])
            if cle not in vus:
                vus.add(cle)
                articles.append(s)
    for s in avis.voie_recommandee.get('sources', []):
        cle = (s['code_id'], s['article'])
        if cle not in vus:
            vus.add(cle)
            articles.append(s)

    # ----------------------------- FRANÇAIS -------------------------------
    F: list[str] = []
    a = F.append
    if projet:
        a(MENTION_PROJET)
        a('=' * 72)
        a(MENTION_PROJET_LONGUE)
        a('')
    a('PROCÈS-VERBAL DE TRANSACTION')
    a(f"Règlement amiable en ligne (E-CMA) — voie : "
      f"{avis.voie_recommandee['voie']['nom_fr']}")
    a(f"Référence du dossier : {dossier.reference}")
    a('-' * 72)
    a('')
    a('ENTRE LES SOUSSIGNÉS')
    a(f"  Demandeur  : {dem['nom']}")
    if dem.get('position'):
        a(f"    Position : {dem['position']}")
    a(f"  Défendeur  : {deff['nom']}")
    if deff.get('position'):
        a(f"    Position : {deff['position']}")
    else:
        a("    Position : NON EXPRIMÉE — à recueillir avant signature.")
    a('')
    a('OBJET DU DIFFÉREND')
    ligne = (f"  Créance réclamée : {_fmt_montant(montant)} {devise}, au titre "
             f"de : {lit['nature']}.")
    if lit.get('numero_facture'):
        ligne += f" Facture n° {lit['numero_facture']}."
    if lit.get('date_facture'):
        ligne += f" Datée du {_fmt_date_fr(lit['date_facture'])}."
    a(ligne)
    a('')
    a('TERMES PROPOSÉS')
    for t in avis.termes:
        a(f"  • {t['intitule_fr']} — {t['intitule_ar']}")
        a(f"    {t['detail_fr']}")
        if t['reserve']:
            a(f"    RÉSERVE : {t['reserve']}")
        a(f"    Fondement : "
          f"{'principe fondé' if t['principe_fonde'] else 'PRINCIPE NON FONDÉ'}, "
          f"{'quantum fondé' if t['quantum_fonde'] else 'quantum NON fondé par un texte'}.")
        a('')
    a('CE QUE LE CORPUS NE FONDE PAS')
    for x in avis.abstentions:
        a(f"  – {x}")
    a('')
    a('FONDEMENT JURIDIQUE — السند القانوني')
    a('-' * 72)
    for s in articles:
        marque = '  [OCR DÉGRADÉ — à vérifier sur le texte officiel]' if s['fiabilite'] == 'ocr-degrade' else ''
        a(f"  • {s['short_fr']} — {s['label_fr']}{marque}")
        a(f"    {s['citation_ar']}")
        a(f"    {s['commentaire_fr']}")
        a('')
    a(AVERTISSEMENT_SOURCES)
    a('')
    a('VALIDATION DU PROFESSIONNEL ACCRÉDITÉ')
    a('-' * 72)
    if dossier.porte_effet_juridique:
        v = dossier.validation
        a(f"  Validé par      : {v.valide_par}")
        a(f"  Qualité         : {v.qualite}")
        a(f"  Accréditation   : n° {v.numero_accreditation}")
        a(f"  Date            : {_fmt_date_fr(v.valide_le or avis.emis_le)}")
        if v.observations:
            a(f"  Observations    : {v.observations}")
        a('  Ce procès-verbal est validé et porte effet juridique.')
    else:
        a("  Validé par      : ____________________________  (NON VALIDÉ)")
        a("  Qualité         : conciliateur / médiateur / arbitre")
        a("  Accréditation   : n° __________________________")
        a("  Date            : ____ / ____ / ________")
        a("  Signature       : ____________________________")
        a('')
        a("  EN L'ÉTAT, CE DOCUMENT NE PORTE AUCUN EFFET JURIDIQUE.")
        a("  L'avis ci-dessus a été préparé par un agent logiciel. Il ne lie")
        a("  personne tant qu'un professionnel accrédité ne l'a pas validé et")
        a("  que les parties ne l'ont pas signé.")
    a('')
    a('SIGNATURES DES PARTIES')
    a(f"  {dem['nom']} : ____________________    "
      f"{deff['nom']} : ____________________")
    a(f"  Fait à {lit['lieu']}, le {_fmt_date_fr(avis.emis_le)}")
    if projet:
        a('')
        a('-' * 72)
        a(MENTION_PROJET)
        a(MENTION_PROJET_LONGUE)
    texte_fr = '\n'.join(F)

    # ------------------------------ ARABE ---------------------------------
    # Rédaction arabe propre, non traduite mot à mot du français : un PV se
    # lit dans sa langue. Les CITATIONS d'articles restent celles du corpus,
    # reproduites sans retouche.
    A: list[str] = []
    b = A.append
    if projet:
        b(MENTION_PROJET_AR)
        b('=' * 72)
        b(MENTION_PROJET_LONGUE_AR)
        b('')
    b('محضر صلح')
    b(f"تسوية ودية عن بعد (E-CMA) — الطريقة المعتمدة: "
      f"{avis.voie_recommandee['voie']['nom_ar']}")
    b(f"مرجع الملف: {dossier.reference}")
    b('-' * 72)
    b('')
    b('بين الممضيين أسفله')
    b(f"  الطالب: {dem['nom']}")
    b(f"  المطلوب: {deff['nom']}")
    b('')
    b('موضوع النزاع')
    b(f"  المبلغ المطلوب: {_fmt_montant(montant)} {devise}، بعنوان: {lit['nature']}.")
    if lit.get('date_facture'):
        b(f"  الفاتورة المؤرخة في: {lit['date_facture']}")
    b('')
    b('الشروط المقترحة')
    for t in avis.termes:
        b(f"  • {t['intitule_ar']} ({t['intitule_fr']})")
    if terme_montant and terme_montant.get('valeur'):
        v = terme_montant['valeur']
        b(f"  يُقترح حصر مبلغ الصلح بين {_fmt_montant(v['plancher'])} و"
          f"{_fmt_montant(v['plafond'])} {v['devise']}.")
        b("  تنبيه: طبق الفصل 1467 من مجلة الالتزامات والعقود، الصلح بشيء من "
          "الدين كالإبراء في الباقي.")
    if terme_ech and terme_ech.get('valeur'):
        b(f"  عدد الأقساط المقترحة: {terme_ech['valeur']['nombre_echeances']}، "
          f"وهو اقتراح تعاقدي لا يستند إلى نص قانوني ولا يُعدّ حقا للمدين.")
    b('')
    b('السند القانوني')
    b('-' * 72)
    for s in articles:
        suffixe = '  [نص ممسوح ضوئيا — يُراجع على النص الرسمي]' if s['fiabilite'] == 'ocr-degrade' else ''
        b(f"  • {s['citation_ar']}{suffixe}")
    b('')
    b('مصادقة المهني المعتمد')
    b('-' * 72)
    if dossier.porte_effet_juridique:
        v = dossier.validation
        b(f"  صادق عليه: {v.valide_par} — {v.qualite} — عدد الاعتماد: {v.numero_accreditation}")
        b(f"  بتاريخ: {v.valide_le}")
        b('  هذا المحضر مصادق عليه ويترتب عليه أثر قانوني.')
    else:
        b("  صادق عليه: ____________________________  (غير مصادق عليه)")
        b("  الصفة: موفّق / وسيط / محكّم")
        b("  عدد الاعتماد: __________________________")
        b("  التاريخ: ____ / ____ / ________")
        b("  الإمضاء: ____________________________")
        b('')
        b("  في حالته الراهنة، لا يترتب على هذا المحضر أي أثر قانوني.")
        b("  الرأي الوارد أعلاه أعدّته منظومة آلية ولا يُلزم أحدا ما لم "
          "يصادق عليه مهني معتمد ويمضه الطرفان.")
    b('')
    b('إمضاء الطرفين')
    b(f"  {dem['nom']}: ____________________    {deff['nom']}: ____________________")
    if projet:
        b('')
        b('-' * 72)
        b(MENTION_PROJET_AR)
        b(MENTION_PROJET_LONGUE_AR)
    texte_ar = '\n'.join(A)

    return {
        'reference': dossier.reference,
        'est_projet': projet,
        'porte_effet_juridique': dossier.porte_effet_juridique,
        'mention': MENTION_PROJET if projet else '',
        'mention_ar': MENTION_PROJET_AR if projet else '',
        'titre_fr': 'PROCÈS-VERBAL DE TRANSACTION',
        'titre_ar': 'محضر صلح',
        'texte_fr': texte_fr,
        'texte_ar': texte_ar,
        'articles_cites': articles,
    }


__all__ = [
    'Litige', 'Partie', 'DossierECMA', 'AvisAgent', 'EspaceValidation',
    'TermeReglement', 'SourceLegale', 'Voie', 'VOIES', 'LitigeInvalide',
    'proposer_reglement', 'rediger_pv', 'verifier_ancrage_bm25',
    'MENTION_PROJET', 'MENTION_PROJET_AR',
]
