"""Générateur et analyseur de la CLAUSE DE RÈGLEMENT DES LITIGES.

POURQUOI CE MODULE EXISTE
-------------------------
Sur la plateforme, la voie de résolution d'un litige — conciliation, médiation
ou arbitrage — est choisie AU MOMENT DE LA SIGNATURE, pas au moment du
conflit. Quand le différend survient, les parties n'ont plus à négocier
COMMENT se régler : c'est déjà convenu, et le contrat le dit. Ce module rédige
cette stipulation, en français et en arabe, et sait relire un contrat existant
pour dire si elle s'y trouve et ce qui lui manque.

CE QUE CE MODULE NE FAIT PAS
----------------------------
Il ne produit aucun effet de droit. Tout document sorti d'ici porte la mention
« PROJET — NON SIGNÉ », un champ ``valide_par`` à ``None`` et un champ
``porte_effet_juridique`` à ``False``. L'exécution et l'effet juridique
restent au professionnel accrédité qui valide. L'intelligence attachée au
contrat donne des AVIS ; elle ne signe pas.

D'OÙ VIENNENT LES ARTICLES
--------------------------
Aucune référence n'est écrite à la main. Chaque article cité est RETROUVÉ dans
le corpus au chargement du module par ``_ancrer()``, qui exige que l'article
existe ET que le fragment arabe attendu y figure réellement. Si le corpus
change, le module refuse de se charger plutôt que de citer un texte qu'il n'a
pas vu. La citation arabe reproduite dans la clause est celle du corpus, mot
pour mot, jamais une reformulation.

CE QUE LE CORPUS NE FONDE PAS
-----------------------------
La MÉDIATION n'a aucun fondement dans ce corpus : les seules occurrences de
« وساطة » relèvent du courtage commercial (art. 601 du code de commerce :
« عقد الوساطة هو توكيل تاجر... »), pas du règlement amiable des litiges.
Le module REFUSE donc de rédiger une clause de médiation. Voir
``lacunes_corpus()`` pour la liste complète et honnête des points que la
plateforme stipule sans pouvoir les adosser à un article.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable, Optional

# `packages.legal.gate` fait `from retrieve import tokenize` : il n'est
# importable que si packages/legal/ est sur le chemin. On l'y met sans
# toucher au fichier d'un autre module.
_LEGAL_DIR = Path(__file__).resolve().parents[1] / 'legal'
if str(_LEGAL_DIR) not in sys.path:
    sys.path.insert(0, str(_LEGAL_DIR))

from packages.legal import gate, retrieve  # noqa: E402

# ---------------------------------------------------------------------------
# Mentions verrouillées
# ---------------------------------------------------------------------------

# Comme dans notice.py : la mention est une constante, pas une chaîne recopiée.
# Elle doit être impossible à perdre par inadvertance, et un test la verrouille.
MENTION_PROJET = "PROJET — NON SIGNÉ"
MENTION_PROJET_AR = "مشروع — غير ممضى"

MENTION_PROJET_LONGUE = (
    "PROJET — NON SIGNÉ. La présente clause est un projet de stipulation "
    "rédigé par Mizan. Elle ne produit, en l'état, aucun effet de droit : "
    "elle n'engage les parties qu'une fois insérée dans un contrat signé par "
    "elles, et elle n'est proposée qu'à titre d'avis. Sa validation relève "
    "d'un professionnel accrédité, seul habilité à en apprécier la portée et "
    "à en assumer l'effet juridique."
)

AVERTISSEMENT_SOURCES = (
    "Les articles cités ci-dessus sont reproduits depuis le corpus des codes "
    "tunisiens indexé par Mizan. Aucun modèle de langage n'énonce ici une "
    "règle de droit."
)


# ---------------------------------------------------------------------------
# Erreurs : chacune correspond à un refus que le module doit savoir opposer
# ---------------------------------------------------------------------------

class ErreurClause(ValueError):
    """Base des refus opposés par ce module."""


class VoieInconnue(ErreurClause):
    """La voie demandée n'est pas l'une des trois voies de la plateforme."""


class VoieNonFondee(ErreurClause):
    """La voie existe en pratique mais aucun article du corpus ne la fonde.

    Le refus est la bonne réponse : rédiger une clause de médiation en citant
    un article de courtage commercial serait une référence inventée.
    """


class ParametreInvalide(ErreurClause):
    """Un paramètre rendrait la clause nulle ou inapplicable.

    Exemples : un nombre pair d'arbitres (art. 17 de la mjalla du tahkim
    impose de compléter le tribunal par un arbitre supplémentaire), un délai
    de saisine négatif (un délai qui a expiré avant de courir n'est pas un
    délai).
    """


class ContratIllisible(ErreurClause):
    """Le texte soumis à l'analyse n'est pas exploitable."""


# ---------------------------------------------------------------------------
# Ancrage sur le corpus : aucune citation n'est écrite à la main
# ---------------------------------------------------------------------------

_DOCS: Optional[list] = None


def _docs() -> list:
    """Charge le corpus une fois. La clé `article` y est un INT, pas une str."""
    global _DOCS
    if _DOCS is None:
        _DOCS = retrieve.load_docs()
    return _DOCS


@dataclass(frozen=True)
class Article:
    """Un article du corpus, reproduit tel quel.

    `reserve` n'est pas du droit : c'est l'honnêteté de la citation. Certains
    articles de la mjalla du tahkim figurent au chapitre de l'arbitrage
    INTERNATIONAL ; les citer pour un contrat interne sans le dire serait
    trompeur, alors la réserve est portée dans le document.
    """
    code_id: str
    code_fr: str
    code_ar: str
    article: int
    citation_ar: str
    texte_ar: str
    role_fr: str
    reserve: str = ''

    def to_dict(self) -> dict:
        return asdict(self)


def _ancrer(code_id: str, article: int, marqueur_ar: str, role_fr: str,
            reserve: str = '') -> Article:
    """Retrouve un article dans le corpus et prouve qu'il dit bien ceci.

    POURQUOI un marqueur. Le corpus est issu d'OCR : plusieurs entrées peuvent
    porter le même numéro d'article (la mjalla du tahkim compte six entrées
    « article 2 », dont des annexes de conventions bilatérales). Le numéro seul
    ne désigne donc rien. Le fragment arabe attendu lève l'ambiguïté ET vérifie
    que le texte cité est bien celui qu'on croit citer.

    Lève RuntimeError si zéro ou plusieurs articles correspondent : mieux vaut
    un module qui refuse de se charger qu'un module qui cite au hasard.
    """
    cible = retrieve.normalize(marqueur_ar)
    trouves = [d for d in _docs()
               if d['code_id'] == code_id
               and d['article'] == article          # INT, pas str
               and cible in retrieve.normalize(d['text_ar'])]
    if len(trouves) != 1:
        raise RuntimeError(
            f"Ancrage impossible : {code_id} art. {article} + marqueur "
            f"{marqueur_ar!r} → {len(trouves)} correspondance(s). Mizan ne "
            f"cite pas un article qu'elle n'a pas retrouvé dans le corpus."
        )
    d = trouves[0]
    return Article(
        code_id=d['code_id'], code_fr=d['code_fr'], code_ar=d['code_ar'],
        article=d['article'], citation_ar=d['citation_ar'],
        texte_ar=d['text_ar'], role_fr=role_fr, reserve=reserve,
    )


_RESERVE_INTERNATIONAL = (
    "Cet article figure au chapitre III de la mjalla du tahkim, consacré à "
    "l'arbitrage international. Il est cité ici comme référence de principe ; "
    "pour un arbitrage interne, sa transposition doit être validée par un "
    "professionnel."
)

# Les fondements de chaque voie, retrouvés dans le corpus au chargement.
# Si l'un d'eux disparaît du corpus, l'import échoue bruyamment.
FONDEMENTS: dict[str, list[Article]] = {
    'conciliation': [
        _ancrer('coc', 1458, 'الصلح عقد وضع لرفع النزاع وقطع الخصومة',
                "Définition de la transaction (الصلح) : contrat par lequel les "
                "parties terminent une contestation née ou préviennent une "
                "contestation à naître, par concessions réciproques."),
        _ancrer('coc', 1462, 'لا يجوز الصلح فيما يتعلق بالحقوق الخاصة بذات الإنسان',
                "Matières exclues : la transaction ne peut porter sur les "
                "droits attachés à la personne ni sur l'ordre public ; elle "
                "reste possible sur leurs conséquences pécuniaires."),
        _ancrer('coc', 1466, 'يكون الصلح إلا كتابة',
                "Forme : lorsque la transaction crée, transfère ou modifie des "
                "droits susceptibles d'hypothèque, elle doit être écrite et "
                "enregistrée pour être opposable aux tiers."),
        _ancrer('coc', 1467, 'يترتب على الصلح سقوط الحقوق والدعاوي',
                "Effet : la transaction éteint les droits et actions sur "
                "lesquels elle porte."),
        _ancrer('coc', 1475, 'الصلح لا يقبل التجزئة',
                "Indivisibilité : la nullité d'une partie de la transaction "
                "entraîne en principe celle du tout."),
        _ancrer('coc', 242, 'يقوم مقام القانون فيما بين المتعاقدين',
                "Force obligatoire : le contrat valablement formé tient lieu "
                "de loi aux parties — c'est ce qui rend la clause contraignante."),
        _ancrer('procciv', 45, 'يدعوهما للصلح',
                "Complément procédural : devant le juge cantonal, les parties "
                "sont invitées à la conciliation, et l'accord est constaté par "
                "jugement d'expédient."),
    ],
    'arbitrage': [
        _ancrer('arbitrage', 2, 'يفضوا بواسطة التحكيم',
                "Définition de la convention d'arbitrage : engagement des "
                "parties de soumettre à l'arbitrage tout ou partie des litiges "
                "nés d'un rapport de droit déterminé, sous forme de clause "
                "compromissoire ou de compromis."),
        _ancrer('arbitrage', 3, 'الشرط التحكيمي',
                "Clause compromissoire : stipulation par laquelle les parties "
                "soumettent à l'arbitrage les litiges à naître du contrat — "
                "c'est exactement l'objet de la présente clause."),
        _ancrer('arbitrage', 7, 'يجوز اشتراط شرط تحكيمي',
                "Arbitrabilité : les litiges relatifs aux obligations et "
                "échanges civils et commerciaux peuvent faire l'objet d'une "
                "clause compromissoire."),
        _ancrer('arbitrage', 17, 'شفعا فإن هيئة التحكيم',
                "Objet et composition : l'objet du litige et la désignation "
                "des arbitres doivent figurer au compromis à peine de nullité ; "
                "si les arbitres désignés sont en nombre PAIR, le tribunal est "
                "complété par un arbitre qui le préside."),
        _ancrer('arbitrage', 10, 'يجب أن يكون المحكم شخصا',
                "Qualités de l'arbitre : personne physique capable, "
                "indépendante et impartiale envers les parties."),
        _ancrer('arbitrage', 24, 'ستة أشهر',
                "Délai de la sentence : à défaut de délai convenu, le tribunal "
                "statue au plus vite et en tout état de cause dans les six "
                "mois, prorogeables."),
        _ancrer('arbitrage', 33, 'بإذن من رئيس المحكمة الابتدائية',
                "Exécution : la sentence s'exécute volontairement ou par "
                "exequatur du président du tribunal de première instance — "
                "l'effet exécutoire reste judiciaire, jamais contractuel."),
        _ancrer('arbitrage', 63, 'على قدم المساواة',
                "Égalité des parties : chacune doit disposer d'une pleine "
                "possibilité de faire valoir ses droits.",
                reserve=_RESERVE_INTERNATIONAL),
        _ancrer('arbitrage', 65, 'مكان التحكيم',
                "Siège : les parties fixent librement le lieu de l'arbitrage, "
                "en Tunisie ou hors de Tunisie.",
                reserve=_RESERVE_INTERNATIONAL),
    ],
}

VOIES = ('conciliation', 'mediation', 'arbitrage')

# La médiation : nommée par le métier, absente du corpus. Le texte du refus
# cite ce que le corpus contient réellement, pour que le refus soit vérifiable.
VOIES_NON_FONDEES: dict[str, str] = {
    'mediation': (
        "Aucun article du corpus indexé (4 087 articles, dont 79 de la mjalla "
        "du tahkim) n'organise la médiation comme mode de règlement des "
        "litiges. Les seules occurrences de « وساطة » visent le courtage "
        "commercial — art. 601 du code de commerce : « عقد الوساطة هو توكيل "
        "تاجر... » — qui est un contrat d'entremise, pas un mode de résolution "
        "des différends. Mizan s'abstient donc de rédiger une clause de "
        "médiation : la fonder sur ces articles serait une citation inventée. "
        "La médiation est régie en droit tunisien par des textes qui ne "
        "figurent pas dans ce corpus ; leur versement au corpus est un "
        "préalable, et la rédaction relève en attendant d'un professionnel "
        "accrédité."
    ),
}


def voies_disponibles() -> tuple[str, ...]:
    """Les voies que le corpus permet réellement de rédiger."""
    return tuple(v for v in VOIES if v in FONDEMENTS)


def lacunes_corpus() -> list[dict]:
    """Ce que la plateforme stipule sans qu'un article du corpus le fonde.

    POURQUOI cette fonction. Une clause bien rédigée porte des mentions —
    langue de la procédure, répartition des frais — que le corpus n'impose ni
    n'organise. Elles restent licites : l'art. 242 du COC fait du contrat la
    loi des parties. Mais les présenter comme fondées sur un texte serait
    faux. La liste est donc rendue avec le document, pas cachée.
    """
    coc242 = next(a for a in FONDEMENTS['conciliation']
                  if a.code_id == 'coc' and a.article == 242)
    return [
        {
            'objet': 'médiation',
            'constat': VOIES_NON_FONDEES['mediation'],
            'consequence': "Mizan refuse de générer cette clause.",
        },
        {
            'objet': 'langue de la procédure',
            'constat': (
                "Aucun article du corpus ne fixe la langue d'une conciliation "
                "ou d'un arbitrage interne. La recherche « لغة التحكيم » ne "
                "retourne aucun article."
            ),
            'consequence': (
                f"La mention est une stipulation purement contractuelle, "
                f"licite au titre de l'{coc242.citation_ar} (force obligatoire "
                f"du contrat), et non l'application d'une règle légale."
            ),
        },
        {
            'objet': 'répartition des frais',
            'constat': (
                "Aucun article du corpus n'organise la charge des frais et "
                "honoraires d'arbitrage : les recherches « مصاريف التحكيم » et "
                "« أتعاب المحكمين » ne retournent aucun article."
            ),
            'consequence': (
                "La répartition stipulée vaut comme convention entre les "
                "parties, sous réserve de l'appréciation du tribunal saisi."
            ),
        },
        {
            'objet': 'désignation d\'une institution d\'arbitrage',
            'constat': (
                "Le corpus connaît le « نظام تحكيم » (règlement d'arbitrage) "
                "aux art. 5 et 17, mais n'agrée ni ne nomme aucune institution."
            ),
            'consequence': (
                "Le nom de l'institution retenue est repris tel que les "
                "parties l'indiquent ; Mizan ne certifie pas son existence."
            ),
        },
    ]


# ---------------------------------------------------------------------------
# Paramètres de la clause
# ---------------------------------------------------------------------------

LANGUES_PROCEDURE = {'arabe', 'français', 'francais', 'anglais'}
_LANGUE_AR = {'arabe': 'العربية', 'français': 'الفرنسية',
              'francais': 'الفرنسية', 'anglais': 'الإنجليزية'}

REPARTITIONS_FRAIS = {
    'parts_egales': ("supportés par parts égales entre les parties",
                     "يتحملها الطرفان بالتساوي"),
    'partie_perdante': ("supportés par la partie qui succombe",
                        "يتحملها الطرف الخاسر"),
    'decision_tribunal': ("répartis par la décision qui met fin au litige",
                          "يقع توزيعها بمقتضى القرار الفاصل في النزاع"),
}

# Un délai de saisine se compte en jours ouvrables ou francs, jamais en
# décennies : au-delà, la clause est en réalité une renonciation déguisée.
DELAI_SAISINE_MAX_JOURS = 365
# Art. 24 : à défaut de convention, six mois. On borne les conventions
# excessives, qui priveraient la voie choisie de tout intérêt.
DELAI_PROCEDURE_MAX_MOIS = 24
NB_ARBITRES_MAX = 7


@dataclass
class ParametresClause:
    """Ce qu'une vraie clause de règlement doit porter pour être applicable.

    Une clause qui ne dit ni quand saisir, ni où, ni dans quelle langue, ni
    qui tranche, n'est pas une clause : c'est une intention. Chaque paramètre
    est donc obligatoire, et ``valider()`` refuse ceux qui rendraient la
    stipulation nulle.
    """
    delai_saisine_jours: int
    lieu: str
    langue: str
    repartition_frais: str = 'parts_egales'
    delai_procedure_mois: int = 6
    nombre_arbitres: Optional[int] = None
    institution: Optional[str] = None

    def valider(self, voie: str) -> 'ParametresClause':
        """Refuse tout paramètre qui rendrait la clause nulle ou absurde.

        POURQUOI chaque refus :

        - délai de saisine ≤ 0 : un délai qui expire avant de courir n'ouvre
          aucune voie ; il ferme le recours dès la signature.
        - nombre d'arbitres pair ou nul : l'art. 17 de la mjalla du tahkim
          traite le nombre pair comme une composition incomplète, à compléter
          par un arbitre président. Une clause qui stipule un nombre pair
          organise donc sa propre correction — autant la refuser.
        - nombre d'arbitres sur une conciliation : il n'y a pas d'arbitre dans
          une conciliation ; la mention trahit une confusion de voie.
        """
        v = _normaliser_voie(voie)

        if not isinstance(self.delai_saisine_jours, int) or isinstance(self.delai_saisine_jours, bool):
            raise ParametreInvalide(
                "Le délai de saisine doit être un nombre entier de jours.")
        if self.delai_saisine_jours <= 0:
            raise ParametreInvalide(
                f"Délai de saisine invalide ({self.delai_saisine_jours} jours) : "
                f"un délai nul ou négatif ferme la voie de recours au moment "
                f"même où la clause l'ouvre. Il doit être strictement positif.")
        if self.delai_saisine_jours > DELAI_SAISINE_MAX_JOURS:
            raise ParametreInvalide(
                f"Délai de saisine invalide ({self.delai_saisine_jours} jours) : "
                f"au-delà de {DELAI_SAISINE_MAX_JOURS} jours, la clause vide de "
                f"sens l'engagement de régler le litige par cette voie.")

        if not isinstance(self.delai_procedure_mois, int) or isinstance(self.delai_procedure_mois, bool):
            raise ParametreInvalide(
                "Le délai de la procédure doit être un nombre entier de mois.")
        if not 0 < self.delai_procedure_mois <= DELAI_PROCEDURE_MAX_MOIS:
            raise ParametreInvalide(
                f"Délai de procédure invalide ({self.delai_procedure_mois} mois) : "
                f"il doit être compris entre 1 et {DELAI_PROCEDURE_MAX_MOIS} mois.")

        if not isinstance(self.lieu, str) or not _nettoyer(self.lieu).strip():
            raise ParametreInvalide(
                "Le lieu de la procédure doit être indiqué : sans lieu, aucune "
                "partie ne sait où se rendre ni quel juge d'appui saisir.")

        langue = self.langue.strip().lower() if isinstance(self.langue, str) else None
        if langue not in LANGUES_PROCEDURE:
            raise ParametreInvalide(
                f"Langue de procédure inconnue : {self.langue!r}. Valeurs "
                f"admises : {sorted(LANGUES_PROCEDURE)}.")

        if self.repartition_frais not in REPARTITIONS_FRAIS:
            raise ParametreInvalide(
                f"Répartition des frais inconnue : {self.repartition_frais!r}. "
                f"Valeurs admises : {sorted(REPARTITIONS_FRAIS)}.")

        if v == 'arbitrage':
            n = self.nombre_arbitres
            if n is None:
                raise ParametreInvalide(
                    "Le nombre d'arbitres doit être stipulé : l'art. 17 de la "
                    "mjalla du tahkim exige que la composition du tribunal "
                    "résulte de la convention.")
            if not isinstance(n, int) or isinstance(n, bool):
                raise ParametreInvalide(
                    "Le nombre d'arbitres doit être un entier.")
            if n <= 0:
                raise ParametreInvalide(
                    f"Nombre d'arbitres invalide ({n}) : un tribunal arbitral "
                    f"sans arbitre ne peut rendre aucune sentence.")
            if n % 2 == 0:
                raise ParametreInvalide(
                    f"Nombre d'arbitres invalide ({n}) : le nombre doit être "
                    f"IMPAIR. L'art. 17 de la mjalla du tahkim prévoit qu'un "
                    f"tribunal composé en nombre pair soit complété par un "
                    f"arbitre qui le préside ; stipuler {n} arbitres revient à "
                    f"stipuler une composition que la loi devra corriger, et "
                    f"expose la sentence à contestation.")
            if n > NB_ARBITRES_MAX:
                raise ParametreInvalide(
                    f"Nombre d'arbitres invalide ({n}) : au-delà de "
                    f"{NB_ARBITRES_MAX}, le coût de l'arbitrage prive la clause "
                    f"de toute utilité pratique.")
        else:
            if self.nombre_arbitres is not None:
                raise ParametreInvalide(
                    f"Un nombre d'arbitres ({self.nombre_arbitres}) n'a aucun "
                    f"sens dans une clause de {v} : cette voie ne comporte pas "
                    f"de tribunal arbitral. Choisissez la voie « arbitrage » "
                    f"ou retirez ce paramètre.")
        return self

    def to_dict(self) -> dict:
        return asdict(self)


def _normaliser_voie(voie: Any) -> str:
    """Ramène 'Arbitrage ', 'MÉDIATION' … à une clé connue, ou refuse."""
    if not isinstance(voie, str):
        raise VoieInconnue(
            f"Voie de règlement inconnue : {voie!r}. Voies possibles : "
            f"{', '.join(VOIES)}.")
    # On N'assainit PAS la voie : contrairement au corps d'un contrat, c'est
    # une valeur d'énumération. « conciliation\x00 » n'est pas une faute de
    # copier-coller, c'est une valeur qui n'existe pas — et l'accepter
    # silencieusement masquerait un appelant qui construit mal sa requête.
    if _CTRL.search(voie):
        raise VoieInconnue(
            f"Voie de règlement inconnue : {voie!r} (caractères de contrôle). "
            f"Voies possibles : {', '.join(VOIES)}.")
    v = unicodedata.normalize('NFKD', voie.strip().lower())
    v = ''.join(c for c in v if not unicodedata.combining(c))
    if v not in VOIES:
        raise VoieInconnue(
            f"Voie de règlement inconnue : {voie!r}. Voies possibles : "
            f"{', '.join(VOIES)}.")
    return v


_CTRL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


def _nettoyer(texte: str) -> str:
    """Remplace les caractères de contrôle par une espace.

    Ce n'est PAS une reformulation : aucun mot n'est modifié. Un contrat
    collé depuis un PDF traîne souvent des \\x00 ou des \\x1b qui feraient
    échouer la recherche d'une clause bel et bien présente. Les extraits cités
    sont pris dans ce texte assaini, et le document le signale.
    """
    return _CTRL.sub(' ', texte)


# ---------------------------------------------------------------------------
# Le document produit
# ---------------------------------------------------------------------------

@dataclass
class ClauseReglement:
    """Le projet de clause : données, puis texte français et texte arabe.

    ``porte_effet_juridique`` est un champ, pas un calcul : il naît à False et
    seule ``valider_par_professionnel()`` peut le lever. Un test verrouille
    cette propriété sur toutes les clauses générées.
    """
    voie: str
    voie_ar: str
    mention_projet: str
    mention_projet_ar: str
    mention_projet_longue: str
    titre_fr: str
    titre_ar: str
    parametres: dict
    clause_fr: str
    clause_ar: str
    articles: list = field(default_factory=list)
    lacunes: list = field(default_factory=list)
    valide_par: Optional[dict] = None
    porte_effet_juridique: bool = False
    avertissement: str = AVERTISSEMENT_SOURCES
    texte: str = ''

    def to_dict(self) -> dict:
        return asdict(self)


def valider_par_professionnel(clause: ClauseReglement, professionnel: dict) -> ClauseReglement:
    """Attache la validation d'un professionnel accrédité — le seul acte qui
    puisse faire passer ``porte_effet_juridique`` à True.

    POURQUOI trois champs obligatoires. Une validation anonyme n'engage
    personne. Le nom, la qualité et le numéro d'accréditation sont ce qui
    permet, en cas de contestation, de dire QUI a validé et à quel titre.
    Mizan ne valide jamais elle-même : elle ne fait que porter la signature
    d'un humain accrédité.
    """
    manquants = [c for c in ('nom', 'qualite', 'numero_accreditation')
                 if not str((professionnel or {}).get(c, '')).strip()]
    if manquants:
        raise ParametreInvalide(
            f"Validation refusée : champs manquants {manquants}. Une clause ne "
            f"porte effet que si un professionnel accrédité, identifié et "
            f"identifiable, l'a validée.")
    clause.valide_par = dict(professionnel)
    clause.porte_effet_juridique = True
    clause.mention_projet = (
        f"VALIDÉ PAR {professionnel['nom']} — {professionnel['qualite']} "
        f"(accréditation {professionnel['numero_accreditation']})")
    clause.texte = _rendre_texte(clause)
    return clause


# ---------------------------------------------------------------------------
# Rédaction des trois voies
# ---------------------------------------------------------------------------

def _jours_ar(n: int) -> str:
    """Accord arabe du décompte de jours (تمييز العدد).

    Ce n'est pas de la cosmétique : « 3 يوما » est une faute qui décrédibilise
    un acte juridique aux yeux d'un lecteur arabophone. 3–10 → أيام (pluriel de
    petit nombre), 11 et au-delà → يوما (singulier accusatif).
    """
    if n == 1:
        return "يوم واحد"
    if n == 2:
        return "يومين"
    if 3 <= n <= 10:
        return f"{n} أيام"
    return f"{n} يوما"


def _mois_ar(n: int) -> str:
    """Accord arabe du décompte de mois, même règle que _jours_ar."""
    if n == 1:
        return "شهر واحد"
    if n == 2:
        return "شهرين"
    if 3 <= n <= 10:
        return f"{n} أشهر"
    return f"{n} شهرا"


def _corps_conciliation(p: ParametresClause) -> tuple[list[str], list[str]]:
    frais_fr, frais_ar = REPARTITIONS_FRAIS[p.repartition_frais]
    lieu = _nettoyer(p.lieu).strip()
    langue = p.langue.strip().lower()
    langue_ar = _LANGUE_AR[langue]
    inst_fr = (f" La conciliation est conduite sous l'égide de "
               f"{_nettoyer(p.institution).strip()}."
               if p.institution else "")
    inst_ar = (f" وتجري المصالحة تحت إشراف {_nettoyer(p.institution).strip()}."
               if p.institution else "")
    jours_ar = _jours_ar(p.delai_saisine_jours)
    mois_ar = _mois_ar(p.delai_procedure_mois)
    fr = [
        "Article — Règlement des litiges par CONCILIATION (الصلح)",
        f"1. Tout différend né de l'exécution ou de l'interprétation du présent "
        f"contrat sera soumis, préalablement à toute instance, à une tentative "
        f"de conciliation entre les parties, qui déclarent la choisir dès la "
        f"signature comme voie de règlement convenue.",
        f"2. La partie la plus diligente saisit l'autre par écrit dans un délai "
        f"de {p.delai_saisine_jours} jours à compter du jour où le différend "
        f"est survenu. La saisine énonce l'objet précis de la contestation.",
        f"3. La conciliation se tient à {lieu} et se déroule en langue "
        f"{langue}.{inst_fr}",
        f"4. Les parties disposent de {p.delai_procedure_mois} mois à compter "
        f"de la saisine pour aboutir. L'accord de conciliation est constaté par "
        f"écrit signé des parties ; il éteint les droits et actions sur "
        f"lesquels il porte, et sur ceux-là seulement.",
        f"5. La conciliation ne peut porter sur les droits attachés à la "
        f"personne ni sur ce qui relève de l'ordre public ; elle demeure "
        f"ouverte sur leurs conséquences pécuniaires.",
        f"6. Les frais de la conciliation sont {frais_fr}.",
        f"7. À défaut d'accord dans le délai convenu, la partie la plus "
        f"diligente recouvre la liberté de saisir la juridiction compétente.",
    ]
    ar = [
        "فصل — تسوية النزاعات بواسطة الصلح",
        f"1. كل نزاع ينشأ عن تنفيذ هذا العقد أو عن تأويله يعرض وجوبا، قبل رفع "
        f"أي دعوى، على محاولة صلح بين الطرفين، وقد اختار الطرفان هذه الطريقة "
        f"منذ الإمضاء كوسيلة متفق عليها لفض النزاع.",
        f"2. يقوم أحرص الطرفين بإعلام الطرف الآخر كتابة في أجل "
        f"{jours_ar} من تاريخ نشوء النزاع، مع بيان موضوع "
        f"الخلاف بدقة.",
        f"3. تجري المصالحة بـ{lieu} وتكون لغتها {langue_ar}.{inst_ar}",
        f"4. للطرفين أجل {mois_ar} من تاريخ الإعلام "
        f"للتوصل إلى اتفاق. ويحرر الصلح كتابة ويمضيه الطرفان، ويترتب عليه سقوط "
        f"الحقوق والدعاوى المتصالح فيها دون سواها.",
        f"5. لا يجوز الصلح فيما يتعلق بالحقوق الخاصة بذات الإنسان ولا بالحق "
        f"العام، ويبقى جائزا فيما يترتب على ذلك من حقوق مالية.",
        f"6. مصاريف المصالحة {frais_ar}.",
        f"7. وعند عدم التوصل إلى اتفاق في الأجل المتفق عليه، يستعيد كل طرف حقه "
        f"في اللجوء إلى المحكمة المختصة.",
    ]
    return fr, ar


def _corps_arbitrage(p: ParametresClause) -> tuple[list[str], list[str]]:
    frais_fr, frais_ar = REPARTITIONS_FRAIS[p.repartition_frais]
    lieu = _nettoyer(p.lieu).strip()
    langue = p.langue.strip().lower()
    langue_ar = _LANGUE_AR[langue]
    n = p.nombre_arbitres
    if n == 1:
        desig_fr = ("Le tribunal arbitral est composé d'un arbitre unique, "
                    "désigné d'un commun accord par les parties.")
        desig_ar = ("تتركب هيئة التحكيم من محكم فرد يعينه الطرفان باتفاق "
                    "بينهما.")
    else:
        desig_fr = (f"Le tribunal arbitral est composé de {n} arbitres. Chaque "
                    f"partie en désigne un ; les arbitres ainsi désignés "
                    f"choisissent celui qui préside. Le nombre est impair, afin "
                    f"que le tribunal soit régulièrement composé.")
        desig_ar = (f"تتركب هيئة التحكيم من {n} محكمين، يعين كل طرف محكما "
                    f"ويختار المحكمون المعينون رئيس الهيئة. وعدد المحكمين وتر "
                    f"حتى تكون الهيئة مكتملة التركيبة.")
    # « conformément au règlement de le Centre… » : l'élision est faite ici
    # parce qu'un nom d'institution arrive tel que les parties l'écrivent.
    _inst = _nettoyer(p.institution).strip() if p.institution else ''
    _de = "du " + _inst[3:] if _inst.lower().startswith('le ') else (
          "de l'" + _inst[2:] if _inst.lower().startswith("l'") else
          "de la " + _inst[3:] if _inst.lower().startswith('la ') else
          "des " + _inst[4:] if _inst.lower().startswith('les ') else
          "de " + _inst)
    inst_fr = (f" L'arbitrage est conduit conformément au règlement {_de}."
               if _inst else
               " L'arbitrage est ad hoc, conduit par le tribunal arbitral "
               "lui-même.")
    inst_ar = (f" ويجري التحكيم وفق نظام {_inst}."
               if _inst else
               " والتحكيم حر تتولى هيئة التحكيم تنظيمه بنفسها.")
    jours_ar = _jours_ar(p.delai_saisine_jours)
    mois_ar = _mois_ar(p.delai_procedure_mois)
    fr = [
        "Article — Règlement des litiges par ARBITRAGE (التحكيم) — clause compromissoire",
        f"1. Tout différend né de l'exécution ou de l'interprétation du présent "
        f"contrat, y compris sur sa validité, sera tranché définitivement par "
        f"voie d'arbitrage, à l'exclusion des juridictions étatiques pour le "
        f"fond. Les parties adoptent cette voie dès la signature.",
        f"2. La partie qui entend recourir à l'arbitrage le notifie à l'autre "
        f"par écrit dans un délai de {p.delai_saisine_jours} jours à compter du "
        f"jour où le différend est survenu. La notification énonce l'objet du "
        f"litige, qui est ainsi déterminé au sens de la loi.",
        f"3. {desig_fr}{inst_fr} Chaque arbitre doit être une personne physique "
        f"capable, indépendante et impartiale envers les parties, et révéler "
        f"toute circonstance de nature à faire douter de son impartialité.",
        f"4. Le siège de l'arbitrage est fixé à {lieu}. La procédure se déroule "
        f"en langue {langue}.",
        f"5. Le tribunal arbitral statue dans un délai de "
        f"{p.delai_procedure_mois} mois à compter de l'acceptation de sa "
        f"mission par le dernier arbitre, prorogeable dans les conditions de "
        f"la loi. Il traite les parties sur un pied d'égalité et met chacune en "
        f"mesure de faire valoir ses droits.",
        f"6. Les frais et honoraires de l'arbitrage sont {frais_fr}.",
        f"7. La sentence est exécutée volontairement. À défaut, son exécution "
        f"forcée suppose l'exequatur du président du tribunal de première "
        f"instance compétent : la clause ne confère par elle-même aucune force "
        f"exécutoire.",
    ]
    ar = [
        "فصل — تسوية النزاعات بواسطة التحكيم — شرط تحكيمي",
        f"1. كل نزاع ينشأ عن تنفيذ هذا العقد أو عن تأويله، بما في ذلك ما يتعلق "
        f"بصحته، يفصل فيه نهائيا عن طريق التحكيم دون المحاكم في الأصل. وقد "
        f"اعتمد الطرفان هذه الطريقة منذ الإمضاء.",
        f"2. على الطرف الذي يعتزم اللجوء إلى التحكيم أن يعلم الطرف الآخر كتابة "
        f"في أجل {jours_ar} من تاريخ نشوء النزاع، مع تعيين "
        f"موضوع النزاع في الإعلام.",
        f"3. {desig_ar}{inst_ar} ويجب أن يكون كل محكم شخصا طبيعيا رشيدا متمتعا "
        f"بكامل حقوقه المدنية وبالاستقلالية والحياد إزاء الطرفين، وأن يصرح بكل "
        f"ما من شأنه أن يثير الشك في حياده.",
        f"4. مقر التحكيم هو {lieu}، وتكون لغة الإجراءات {langue_ar}.",
        f"5. تبت هيئة التحكيم في أجل {mois_ar} من تاريخ "
        f"قبول آخر المحكمين لمهمته، قابل للتمديد وفق أحكام القانون. وتعامل "
        f"الأطراف على قدم المساواة وتمكن كل طرف من فرصة كاملة للدفاع عن حقوقه.",
        f"6. مصاريف التحكيم وأتعاب المحكمين {frais_ar}.",
        f"7. ينفذ حكم التحكيم تلقائيا، وعند التعذر يكون تنفيذه الجبري بإذن من "
        f"رئيس المحكمة الابتدائية المختصة، إذ لا يخول هذا الشرط بذاته أي قوة "
        f"تنفيذية.",
    ]
    return fr, ar


_REDACTEURS = {
    'conciliation': _corps_conciliation,
    'arbitrage': _corps_arbitrage,
}

_TITRES = {
    'conciliation': ("CLAUSE DE RÈGLEMENT DES LITIGES — CONCILIATION",
                     "شرط تسوية النزاعات — الصلح", "الصلح"),
    'arbitrage': ("CLAUSE DE RÈGLEMENT DES LITIGES — ARBITRAGE",
                  "شرط تسوية النزاعات — التحكيم", "التحكيم"),
}


def generer_clause(voie: str, parametres: ParametresClause) -> ClauseReglement:
    """Rédige le projet de clause, en français et en arabe, pour une voie.

    C'est la fonction que la plateforme appelle au moment de la signature :
    les parties choisissent leur voie, et la clause correspondante entre au
    contrat. Le document qui sort d'ici est un PROJET : il ne porte aucun
    effet juridique tant qu'un professionnel accrédité ne l'a pas validé.

    Lève :
      VoieInconnue      — voie qui n'est pas l'une des trois.
      VoieNonFondee     — voie réelle qu'aucun article du corpus ne fonde
                          (la médiation) : Mizan s'abstient plutôt qu'inventer.
      ParametreInvalide — paramètre rendant la clause nulle.
    """
    v = _normaliser_voie(voie)
    if v in VOIES_NON_FONDEES:
        raise VoieNonFondee(VOIES_NON_FONDEES[v])
    if v not in FONDEMENTS:  # pragma: no cover — filet si une voie est ajoutée
        raise VoieNonFondee(
            f"Aucun fondement n'a été retrouvé dans le corpus pour la voie « {v} ».")

    if not isinstance(parametres, ParametresClause):
        raise ParametreInvalide(
            "Les paramètres doivent être une instance de ParametresClause.")
    parametres.valider(v)

    fr, ar = _REDACTEURS[v](parametres)
    titre_fr, titre_ar, voie_ar = _TITRES[v]

    clause = ClauseReglement(
        voie=v,
        voie_ar=voie_ar,
        mention_projet=MENTION_PROJET,
        mention_projet_ar=MENTION_PROJET_AR,
        mention_projet_longue=MENTION_PROJET_LONGUE,
        titre_fr=titre_fr,
        titre_ar=titre_ar,
        parametres=parametres.to_dict(),
        clause_fr='\n'.join(fr),
        clause_ar='\n'.join(ar),
        articles=[a.to_dict() for a in FONDEMENTS[v]],
        lacunes=lacunes_corpus(),
        valide_par=None,               # aucune validation par défaut
        porte_effet_juridique=False,   # et donc aucun effet de droit
    )
    clause.texte = _rendre_texte(clause)
    return clause


def _rendre_texte(clause: ClauseReglement) -> str:
    """Le projet de clause en texte brut bilingue, prêt à lire ou à imprimer."""
    L: list[str] = []
    A = L.append
    A(f"{clause.mention_projet}{' ' * 8}{clause.mention_projet_ar}")
    A('=' * 72)
    A(clause.mention_projet_longue)
    A('')
    A(f'{clause.titre_fr}')
    A(f'{clause.titre_ar}')
    A('-' * 72)
    A('')
    A('— TEXTE FRANÇAIS —')
    A(clause.clause_fr)
    A('')
    A('— النص العربي —')
    A(clause.clause_ar)
    A('')
    A('FONDEMENT JURIDIQUE — السند القانوني')
    A('-' * 72)
    for a in clause.articles:
        A(f"  • Art. {a['article']} — {a['code_fr']} : {a['role_fr']}")
        A(f"    {a['citation_ar']}")
        if a['reserve']:
            A(f"    ⚠ {a['reserve']}")
    A('')
    A("CE QUE LE CORPUS NE FONDE PAS — ما لا يسنده النص")
    A('-' * 72)
    for lac in clause.lacunes:
        A(f"  • {lac['objet']} : {lac['constat']}")
        A(f"    → {lac['consequence']}")
    A('')
    A(f"Validé par : {clause.valide_par or '— aucun professionnel accrédité —'}")
    A(f"Porte effet juridique : {'OUI' if clause.porte_effet_juridique else 'NON'}")
    A('')
    A('-' * 72)
    A(clause.mention_projet_longue)
    A(clause.avertissement)
    return '\n'.join(L)


# ---------------------------------------------------------------------------
# Analyse d'un contrat existant
# ---------------------------------------------------------------------------

# Limite de garde : au-delà, on n'analyse pas un contrat, on analyse une
# archive. Le refus est explicite plutôt que silencieusement tronqué.
TAILLE_MAX_CONTRAT = 2_000_000

# Les frontières de mot latines (\b) ne fonctionnent pas en arabe : « محكم »
# (arbitre) est un sous-mot de « المحكمة » (le tribunal). Sans garde, un
# contrat arabophone qui renvoie au TRIBUNAL compétent serait lu comme
# stipulant un ARBITRAGE — l'inverse de ce qu'il dit. D'où les lookarounds.
_AR = r'\u0621-\u064A'

_MOTIFS_VOIE: dict[str, list[re.Pattern]] = {
    'arbitrage': [
        re.compile(r"\barbitr(?:age|al|ale|aux|ales|e|es)\b", re.I),
        re.compile(r"clause\s+compromissoire", re.I),
        re.compile(r"compromis\s+d['’]arbitrage", re.I),
        re.compile(rf"(?<![{_AR}])(?:ال)?تحكيم(?![{_AR}])"
                   rf"|(?<![{_AR}])(?:ال)?محكم(?:ين|ون|ا)?(?![{_AR}])"),
    ],
    'conciliation': [
        re.compile(r"\bconcili(?:ation|ateur|atrice)\b", re.I),
        re.compile(r"\btransaction(?:nel|nelle)?\b", re.I),
        re.compile(r"règlement\s+amiable|reglement\s+amiable", re.I),
        re.compile(rf"(?<![{_AR}])(?:ال)?(?:صلح|مصالحة|توفيق)(?![{_AR}])"),
    ],
    'mediation': [
        re.compile(r"\bm[ée]diat(?:ion|eur|rice)\b", re.I),
        re.compile(rf"(?<![{_AR}])(?:ال)?(?:وساطة|وسيط)(?![{_AR}])"),
    ],
}

# Ce que la clause doit dire pour être applicable, et comment on le repère.
# On ne juge pas le style : on vérifie qu'une information est présente.
_EXIGENCES: dict[str, list[tuple[str, str, re.Pattern]]] = {
    'arbitrage': [
        ('objet du litige',
         "L'art. 17 de la mjalla du tahkim impose de déterminer l'objet du "
         "litige, à peine de nullité de la convention.",
         re.compile(r"(diff[ée]rend|litige|contestation|نزاع|خلاف)", re.I)),
        ('désignation des arbitres',
         "L'art. 17 impose que les arbitres soient désignés, expressément ou "
         "par renvoi à un règlement, à peine de nullité.",
         re.compile(r"(d[ée]sign|nomm|arbitre\s+unique|pr[ée]sident|تعيين|محكم\s+فرد|رئيس)", re.I)),
        ('nombre impair d\'arbitres',
         "Un nombre pair conduit, en application de l'art. 17, à compléter le "
         "tribunal par un arbitre président.",
         re.compile(r"(arbitre\s+unique|un\s+seul\s+arbitre|trois\s+arbitres|"
                    r"cinq\s+arbitres|\b(?:1|3|5|7)\s+arbitres?\b|"
                    r"محكم\s+فرد|ثلاثة\s+محكمين|خمسة\s+محكمين)", re.I)),
        ('siège / lieu',
         "Le lieu détermine le juge d'appui et le juge de l'exequatur.",
         re.compile(r"(si[èe]ge|lieu\s+de\s+l['’]arbitrage|se\s+tient\s+[àa]|مقر|مكان)", re.I)),
        ('langue de la procédure',
         "Sans langue convenue, la procédure peut être conduite dans une langue "
         "qu'une partie ne maîtrise pas.",
         re.compile(r"(langue|en\s+langue|لغة|اللغة)", re.I)),
        ('délai',
         "Sans délai, l'art. 24 impose six mois ; le stipuler évite la "
         "discussion.",
         re.compile(r"(d[ée]lai|mois|jours|أجل|أشهر|يوما)", re.I)),
        ('répartition des frais',
         "Le corpus n'organise pas la charge des frais : seule la convention "
         "la règle.",
         re.compile(r"(frais|honoraires|d[ée]pens|مصاريف|أتعاب)", re.I)),
    ],
    'conciliation': [
        ('objet du litige',
         "L'art. 1469 du COC limite la transaction aux droits sur lesquels "
         "elle porte : il faut donc dire sur quoi elle porte.",
         re.compile(r"(diff[ée]rend|litige|contestation|نزاع|خلاف)", re.I)),
        ('forme écrite de l\'accord',
         "L'art. 1466 du COC impose l'écrit lorsque la transaction touche des "
         "droits susceptibles d'hypothèque.",
         re.compile(r"(par\s+[ée]crit|constat[ée]\s+par\s+[ée]crit|proc[èe]s-verbal|كتابة|محرر)", re.I)),
        ('délai de saisine',
         "Sans délai, la voie convenue peut être invoquée des années après le "
         "différend, ou jamais.",
         re.compile(r"(d[ée]lai|jours|mois|أجل|يوما|أشهر)", re.I)),
        ('lieu',
         "Le lieu évite une discussion préalable sur le lieu.",
         re.compile(r"(lieu|se\s+tient\s+[àa]|[àa]\s+Tunis|مقر|مكان)", re.I)),
        ('langue de la procédure',
         "Stipulation purement contractuelle, mais elle évite un litige sur le "
         "litige.",
         re.compile(r"(langue|لغة|اللغة)", re.I)),
        ('issue en cas d\'échec',
         "Sans clause de sortie, l'échec de la conciliation peut être opposé "
         "comme fin de non-recevoir à l'action.",
         re.compile(r"(à\s+d[ée]faut|en\s+cas\s+d['’][ée]chec|juridiction\s+comp[ée]tente|"
                    r"tribunal\s+comp[ée]tent|عند\s+التعذر|المحكمة\s+المختصة)", re.I)),
        ('répartition des frais',
         "Le corpus ne l'organise pas : seule la convention la règle.",
         re.compile(r"(frais|honoraires|مصاريف)", re.I)),
    ],
}

_NEGATIONS = [
    re.compile(r"\bne\s+(?:\w+\s+){0,3}?(?:aucun|aucune|pas|point|plus)\b", re.I),
    re.compile(r"\baucun(?:e)?\s+(?:clause|convention|stipulation|disposition|"
               r"proc[ée]dure|recours)\b", re.I),
    re.compile(r"\bsans\s+(?:clause|convention|stipulation|recours)\b", re.I),
    re.compile(r"\bn['’](?:est|a|ont|existe|y\s+a)\b", re.I),
    re.compile(r"\bexclu(?:t|ent|e|es|s)?\b", re.I),
    re.compile(r"\b(?:est|sont)\s+écart[ée]e?s?\b", re.I),
    re.compile(r"لا\s+يتضمن|لا\s+يحتوي|لا\s+يشتمل|لم\s+يتضمن|لا\s+وجود|"
               r"دون\s+شرط|بدون\s+شرط|لا\s+يخضع|غير\s+قابل"),
]

# Une phrase se termine par une ponctuation forte, ou par une rupture de
# paragraphe (ligne vide, ou retour à la ligne suivi d'un nouvel article).
# POURQUOI pas un simple « \n » : les contrats sont retournés à la ligne à
# 70 colonnes. Couper dessus citait « d'arbitrage » au lieu de la stipulation
# entière, et faisait conclure à l'ABSENCE de mentions pourtant présentes —
# c'est-à-dire un avis juridique faux. Le retour à la ligne simple est donc
# traité comme une espace, et l'extrait cité reste verbatim, sauts compris.
_FIN_PHRASE = re.compile(
    r"[.;!?\u060C\u061B\u06D4]+"            # ponctuation forte
    r"|\n[ \t]*\n"                          # ligne vide = fin de paragraphe
    r"|\n(?=[ \t]*(?:Article|ARTICLE|Art\.|الفصل|فصل)\b)"  # nouvel article
)
LONGUEUR_EXTRAIT_MAX = 600


@dataclass
class MentionVoie:
    """Une occurrence d'une voie dans le contrat, citée mot pour mot."""
    voie: str
    extrait: str
    extrait_tronque: bool
    debut: int
    fin: int
    dans_une_negation: bool
    motif_negation: str = ''
    # L'article entier qui porte l'occurrence : sert à vérifier les mentions
    # obligatoires. Il n'est pas rendu au client, qui lit `extrait`.
    bloc: str = field(default='', repr=False)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop('bloc', None)   # ce qui est CITÉ au client, c'est `extrait`
        return d


@dataclass
class AnalyseContrat:
    """L'AVIS rendu sur un contrat existant. Un avis, pas une décision.

    ``clause_detectee`` peut être None pour deux raisons opposées, et la
    distinction compte : soit le contrat ne parle pas de règlement des litiges,
    soit il en parle POUR LA NIER (« le présent contrat ne comporte aucune
    clause d'arbitrage »). Confondre les deux ferait dire à Mizan l'inverse du
    contrat.
    """
    contrat_vide: bool
    longueur: int
    caracteres_de_controle_retires: bool
    langues_detectees: list
    clause_detectee: Optional[str]
    mentions: list = field(default_factory=list)
    voies_ecartees: list = field(default_factory=list)
    manques: list = field(default_factory=list)
    opposable_en_l_etat: bool = False
    avis: str = ''
    porte_effet_juridique: bool = False
    valide_par: Optional[dict] = None
    avertissement: str = AVERTISSEMENT_SOURCES
    articles: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _langues(texte: str) -> list:
    """Quelles écritures le contrat emploie réellement.

    Un contrat uniquement en arabe et un contrat uniquement en français sont
    tous deux normaux ici ; ce qui ne l'est pas, c'est d'analyser l'un avec
    les motifs de l'autre sans le dire.
    """
    arabes = sum(1 for c in texte if '\u0600' <= c <= '\u06FF')
    latins = sum(1 for c in texte if c.isascii() and c.isalpha())
    out = []
    if arabes >= 5:
        out.append('arabe')
    if latins >= 5:
        out.append('latin')
    return out or ['indeterminee']


# Début d'un article : c'est l'unité de lecture d'un contrat. Les mentions
# d'une clause s'y répartissent sur plusieurs phrases (« … par voie
# d'arbitrage. Le tribunal est composé de trois arbitres. »), et c'est le
# BLOC entier qu'il faut lire pour dire ce qui manque.
_DEBUT_ARTICLE = re.compile(
    r"(?:^|\n)[ \t]*(?:Article|ARTICLE|Art\.|الفصل|فصل)\b")


def _bloc_autour(texte: str, debut: int, fin: int) -> str:
    """L'article complet qui porte l'occurrence.
    POURQUOI un bloc et pas la phrase. Vérifier les mentions obligatoires sur
    une seule phrase faisait conclure à l'absence du nombre d'arbitres quand
    il figurait à la phrase suivante du même article — un avis faux. On lit
    donc l'article entier, tout en continuant à CITER la phrase exacte.
    """
    gauche = 0
    for m in _DEBUT_ARTICLE.finditer(texte, 0, debut):
        gauche = m.start()
    m = _DEBUT_ARTICLE.search(texte, fin)
    droite = m.start() if m else len(texte)
    return texte[gauche:droite]


def _phrase_autour(texte: str, debut: int, fin: int) -> tuple[str, int, int]:
    """La phrase complète qui porte l'occurrence, avec ses bornes exactes.

    On cite la phrase, pas le mot : « arbitrage » isolé ne dit pas si la
    clause est stipulée ou niée. Les bornes sont des index dans le texte
    assaini, donc l'extrait est littéral.
    """
    gauche = 0
    for m in _FIN_PHRASE.finditer(texte, 0, debut):
        gauche = m.end()
    m = _FIN_PHRASE.search(texte, fin)
    droite = m.start() if m else len(texte)
    return texte[gauche:droite].strip(), gauche, droite


def analyser_contrat(texte: Any) -> AnalyseContrat:
    """Relit un contrat existant : y a-t-il une clause de règlement, laquelle,
    et que lui manque-t-il pour être opposable ?

    POURQUOI cette fonction. La plateforme reçoit aussi des contrats rédigés
    ailleurs. Avant de proposer d'en insérer une, il faut savoir si le contrat
    en porte déjà une — et surtout ne pas en inventer une qui n'y est pas.

    L'extrait rendu est TOUJOURS pris mot pour mot dans le contrat (seuls les
    caractères de contrôle ont été remplacés par des espaces) ; il n'est jamais
    reformulé. Le résultat est un AVIS : ``porte_effet_juridique`` y vaut
    False, comme partout ailleurs dans ce module.
    """
    if texte is None or not isinstance(texte, str):
        raise ContratIllisible(
            "Le contrat à analyser doit être fourni sous forme de texte.")
    if len(texte) > TAILLE_MAX_CONTRAT:
        raise ContratIllisible(
            f"Texte de {len(texte)} caractères : au-delà de "
            f"{TAILLE_MAX_CONTRAT}, Mizan refuse l'analyse plutôt que de la "
            f"tronquer en silence. Découpez le document.")

    propre = _nettoyer(texte)
    nettoye = propre != texte

    if not propre.strip():
        return AnalyseContrat(
            contrat_vide=True, longueur=len(texte),
            caracteres_de_controle_retires=nettoye,
            langues_detectees=_langues(propre), clause_detectee=None,
            avis="Le contrat soumis est vide : il n'y a rien à analyser.",
        )

    mentions: list[MentionVoie] = []
    for voie, motifs in _MOTIFS_VOIE.items():
        vus: set[tuple[int, int]] = set()
        for motif in motifs:
            for m in motif.finditer(propre):
                phrase, g, d = _phrase_autour(propre, m.start(), m.end())
                if (g, d) in vus or not phrase:
                    continue
                vus.add((g, d))
                negation, motif_neg = '', ''
                for neg in _NEGATIONS:
                    hit = neg.search(phrase)
                    if hit:
                        negation, motif_neg = 'oui', hit.group(0)
                        break
                tronque = len(phrase) > LONGUEUR_EXTRAIT_MAX
                mentions.append(MentionVoie(
                    voie=voie,
                    extrait=(phrase[:LONGUEUR_EXTRAIT_MAX] + ' […]') if tronque else phrase,
                    extrait_tronque=tronque,
                    debut=g, fin=d,
                    dans_une_negation=bool(negation),
                    motif_negation=motif_neg,
                    bloc=_bloc_autour(propre, m.start(), m.end()),
                ))

    mentions.sort(key=lambda x: x.debut)
    positives = [m for m in mentions if not m.dans_une_negation]
    negatives = [m for m in mentions if m.dans_une_negation]

    detectee = None
    for voie in ('arbitrage', 'conciliation', 'mediation'):
        if any(m.voie == voie for m in positives):
            detectee = voie
            break

    ecartees = sorted({m.voie for m in negatives}
                      - {m.voie for m in positives})

    manques: list[dict] = []
    articles: list[dict] = []
    if detectee in _EXIGENCES:
        # On vérifie les exigences dans la ou les phrases qui portent la
        # clause, pas dans tout le contrat : « trois » figurant dans un article
        # de prix ne prouve pas le nombre d'arbitres.
        # On lit les ARTICLES qui portent la clause, pas le contrat entier :
        # « trois » figurant dans un article de prix ne prouve pas le nombre
        # d'arbitres, mais « trois arbitres » deux phrases plus loin dans le
        # même article, si.
        vus_blocs: list[str] = []
        for m in positives:
            if m.voie == detectee and m.bloc not in vus_blocs:
                vus_blocs.append(m.bloc)
        zone = '\n'.join(vus_blocs)
        for nom, pourquoi, motif in _EXIGENCES[detectee]:
            if not motif.search(zone):
                manques.append({'element': nom, 'pourquoi': pourquoi})
        articles = [a.to_dict() for a in FONDEMENTS[detectee]]
    elif detectee == 'mediation':
        manques.append({
            'element': 'fondement légal dans le corpus',
            'pourquoi': VOIES_NON_FONDEES['mediation'],
        })

    if detectee is None and ecartees:
        avis = (f"Le contrat évoque {', '.join(ecartees)} uniquement pour "
                f"l'écarter : aucune voie de règlement n'y est convenue. "
                f"À défaut de clause, les litiges relèvent des juridictions "
                f"étatiques de droit commun.")
    elif detectee is None:
        avis = ("Aucune clause de règlement des litiges n'a été repérée dans "
                "ce contrat. En l'absence de voie convenue, tout différend "
                "relèvera des juridictions étatiques, et le mode de résolution "
                "devra être négocié au moment du conflit — c'est précisément ce "
                "qu'une clause insérée à la signature évite.")
    elif detectee == 'mediation':
        avis = ("Le contrat stipule une médiation. Le corpus indexé ne fonde "
                "pas cette voie : Mizan ne peut ni en apprécier la régularité "
                "ni en compléter les mentions. L'avis d'un professionnel "
                "accrédité est nécessaire.")
    elif manques:
        avis = (f"Le contrat comporte une clause de {detectee}. Elle est "
                f"incomplète : {len(manques)} mention(s) manquent pour qu'elle "
                f"soit pleinement opposable. Ces manques sont un avis, pas une "
                f"nullité constatée : seul un professionnel accrédité peut "
                f"conclure à l'inefficacité de la clause.")
    else:
        avis = (f"Le contrat comporte une clause de {detectee} qui porte toutes "
                f"les mentions attendues par Mizan. Cet avis ne vaut pas "
                f"validation : l'appréciation de son opposabilité relève d'un "
                f"professionnel accrédité.")

    return AnalyseContrat(
        contrat_vide=False,
        longueur=len(texte),
        caracteres_de_controle_retires=nettoye,
        langues_detectees=_langues(propre),
        clause_detectee=detectee,
        mentions=[m.to_dict() for m in mentions],
        voies_ecartees=ecartees,
        manques=manques,
        opposable_en_l_etat=False,     # jamais : ce module rend un avis
        avis=avis,
        porte_effet_juridique=False,
        valide_par=None,
        articles=articles,
    )


# ---------------------------------------------------------------------------
# Vérification de l'ancrage : utilisable en ligne de commande et par les tests
# ---------------------------------------------------------------------------

def verifier_ancrage() -> list[dict]:
    """Re-cherche chaque article cité dans le corpus par BM25 et passe la
    garde anti-hallucination de ``packages.legal.gate``.

    POURQUOI en plus de ``_ancrer()``. ``_ancrer()`` prouve que le texte existe
    à l'endroit annoncé. La garde prouve autre chose : que le sujet de la
    clause et le sujet de l'article se recouvrent réellement, avec les mêmes
    seuils (MIN_SCORE, MIN_MATCHED) que le reste de la plateforme.
    """
    out = []
    for voie, articles in FONDEMENTS.items():
        for a in articles:
            # On interroge le corpus avec le texte même de l'article : si le
            # ranker ne le retrouve pas, l'index et le corpus divergent.
            requete = ' '.join(a.texte_ar.split()[:12])
            hits = retrieve.search(requete, k=3)
            d = gate.evaluate(requete, hits)
            out.append({
                'voie': voie, 'code_id': a.code_id, 'article': a.article,
                'citation_ar': a.citation_ar, 'grounded': d['grounded'],
                'score': d['best_score'], 'matched': d['matched'],
                'retrouve_en_tete': bool(hits) and hits[0]['id'] == f"{a.code_id}-art{a.article}",
            })
    return out


if __name__ == '__main__':  # pragma: no cover
    p_conc = ParametresClause(delai_saisine_jours=15, lieu='Sfax',
                              langue='arabe', repartition_frais='parts_egales',
                              delai_procedure_mois=2)
    p_arb = ParametresClause(delai_saisine_jours=30, lieu='Tunis',
                             langue='arabe', repartition_frais='partie_perdante',
                             delai_procedure_mois=6, nombre_arbitres=3,
                             institution="le Centre de conciliation et d'arbitrage de Tunis")
    print(generer_clause('conciliation', p_conc).texte)
    print('\n' + '#' * 72 + '\n')
    print(generer_clause('arbitrage', p_arb).texte)
    print('\n' + '#' * 72 + '\n')
    try:
        generer_clause('mediation', p_conc)
    except VoieNonFondee as e:
        print('MÉDIATION — ABSTENTION :\n', e)
