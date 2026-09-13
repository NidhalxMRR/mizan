"""Catalogue des fondements : un risque, un article, un marqueur qui le prouve.

Chaque entrée de ce fichier a été VÉRIFIÉE dans le corpus avant d'être
écrite, par recherche du marqueur arabe dans le texte de l'article. Le
marqueur n'est pas décoratif : c'est lui qui, à l'exécution, décide si le
risque peut être produit ou s'il faut s'abstenir (voir `ancrage.ancrer`).
Supprimer un article du corpus fait donc disparaître le risque correspondant
au lieu de produire une citation morte.

CE QUE LE CORPUS NE CONTIENT PAS
--------------------------------
Le périmètre demandé couvrait six risques. Le corpus n'en fonde que quatre
familles, et ce constat est le résultat de la vérification, pas un aveu
d'inachèvement. Sur 4087 articles, SIX seulement contiennent le mot « facture »
(فاتورة) : COC 441, fiscal 18, 22, 48, 96, et societes 20.

Deux risques sont donc IMPOSSIBLES à fonder ici, et le module le dit au lieu
de citer approximativement (voir `LACUNES`) :

  * L'OBLIGATION DE DATER UNE FACTURE. Aucune occurrence de « تاريخ الفاتورة »
    ni d'aucune formulation voisine dans les 4087 articles. L'obligation
    existe en droit tunisien, mais elle vit dans le Code de la TVA et dans le
    décret sur la facturation, qui ne sont pas indexés ici. Produire un risque
    « date manquante » adossé à un article de procédure civile serait une
    erreur de droit présentée comme une vérification.

  * LE TAUX DE TVA DE 19 %. Zéro occurrence de « 19 % », « 19 بالمائة » ou de
    toute autre écriture du taux. Un contrôle d'incohérence TVA/HT suppose un
    taux légal de référence ; ce taux ne figure nulle part dans le corpus. Le
    module calcule néanmoins l'écart arithmétique et le PRÉSENTE comme un
    simple constat de calcul, sans le qualifier de manquement légal — un
    chiffre qui ne colle pas est un fait ; dire quelle règle il viole demande
    un texte qu'on n'a pas.

Ce qui reste est fondé, et solidement.
"""
from __future__ import annotations

from typing import NamedTuple


class Fondement(NamedTuple):
    """Un article invoqué, avec la preuve textuelle qui le désigne.

    `marqueur_ar` est le passage arabe littéral qui porte la règle. Il sert à
    deux choses : désigner la bonne entrée quand plusieurs partagent le même
    numéro d'article, et prouver que l'article dit bien ce qu'on lui fait dire.
    """

    cle: str
    code_id: str
    article: int
    marqueur_ar: str
    portee_fr: str


# --- Prescription -----------------------------------------------------------
# Vérifié : COC 403 porte « ثلاثمائة وخمسة وستين يوما » et vise expressément
# « ما يطلبه الباعة وأرباب المصانع من ثمن ما سلموه من البضائع » — le prix des
# marchandises livrées par les vendeurs et les propriétaires d'atelier. C'est
# exactement la situation d'un menuisier impayé.
PRESCRIPTION_UN_AN = Fondement(
    cle='prescription_un_an',
    code_id='coc',
    article=403,
    marqueur_ar='ثلاثمائة وخمسة وستين يوما',
    portee_fr="Prescription d'un an du prix des marchandises livrées par les "
              "vendeurs et les propriétaires d'atelier.",
)

# Vérifié : COC 402 porte « خمس عشرة سنة ».
PRESCRIPTION_GENERALE = Fondement(
    cle='prescription_generale',
    code_id='coc',
    article=402,
    marqueur_ar='خمس عشرة سنة',
    portee_fr='Prescription générale de quinze ans des actions personnelles.',
)

# Vérifié : COC 396 énumère les causes d'interruption (« ينقطع »).
INTERRUPTION = Fondement(
    cle='interruption',
    code_id='coc',
    article=396,
    marqueur_ar='ينقطع',
    portee_fr="Causes d'interruption de la prescription.",
)

# --- Seuil de 150 DT --------------------------------------------------------
# Vérifié : CPCC 60 porte « مائة وخمسين دينارا » et impose, au-delà, la
# sommation par huissier avec un délai de cinq jours francs.
SEUIL_HUISSIER = Fondement(
    cle='seuil_huissier',
    code_id='procciv',
    article=60,
    marqueur_ar='مائة وخمسين دينارا',
    portee_fr="Au-delà de 150 dinars, le créancier doit faire sommer le "
              "débiteur par huissier de justice et lui laisser cinq jours "
              "francs avant l'injonction de payer.",
)

# --- Preuve -----------------------------------------------------------------
# Vérifié : COC 420 — « إثبات الالتزام على القائم به ». Trois mots, et c'est
# la règle qui décide de l'issue : le créancier qui réclame supporte la
# charge de prouver ce qu'il avance.
CHARGE_PREUVE = Fondement(
    cle='charge_preuve',
    code_id='coc',
    article=420,
    marqueur_ar='إثبات الالتزام على القائم به',
    portee_fr="La preuve de l'obligation incombe à celui qui l'invoque.",
)

# Vérifié : COC 441 cite « والفاتورات المقبولة » parmi les preuves écrites.
# Le mot « المقبولة » (acceptées) fait tout le risque : une facture n'est une
# preuve écrite que si le débiteur l'a acceptée. Une facture émise seule, sans
# bon de livraison signé ni accusé de réception, ne remplit pas la condition
# posée par le texte lui-même.
FACTURE_ACCEPTEE = Fondement(
    cle='facture_acceptee',
    code_id='coc',
    article=441,
    marqueur_ar='والفاتورات المقبولة',
    portee_fr="La preuve écrite résulte notamment des factures ACCEPTÉES : "
              "l'acceptation par le débiteur est une condition du texte, non "
              "une formalité.",
)

# --- Mentions obligatoires --------------------------------------------------
# Vérifié : l'entrée fiscal/22 qui porte « غير مرقمة » sanctionne l'usage de
# factures non numérotées ou numérotées en série irrégulière. C'est le seul
# fondement du corpus pour le défaut de numéro.
NUMEROTATION = Fondement(
    cle='numerotation',
    code_id='fiscal',
    article=22,
    marqueur_ar='غير مرقمة',
    portee_fr="L'usage de factures non numérotées, ou numérotées en série "
              "irrégulière ou interrompue, est sanctionné par une amende de "
              "50 à 1000 dinars par facture.",
)

# Vérifié : l'entrée fiscal/18 qui porte « معرّفهم الجبائي » impose de faire
# figurer l'identifiant fiscal sur tous les documents d'activité, et prévoit
# que les documents qui ne le portent pas ne peuvent pas être retenus. Cette
# entrée déclenche une réserve de qualification (voir ancrage._reserve) : son
# texte se réclame du Code de la TVA alors que le corpus la range ailleurs.
IDENTIFIANT_FISCAL = Fondement(
    cle='identifiant_fiscal',
    code_id='fiscal',
    article=18,
    marqueur_ar='معرّفهم الجبائي',
    portee_fr="L'identifiant fiscal doit figurer sur tous les documents "
              "relatifs à l'activité ; ceux qui ne le portent pas ne peuvent "
              "pas être retenus.",
)

TOUS: tuple[Fondement, ...] = (
    PRESCRIPTION_UN_AN, PRESCRIPTION_GENERALE, INTERRUPTION,
    SEUIL_HUISSIER, CHARGE_PREUVE, FACTURE_ACCEPTEE,
    NUMEROTATION, IDENTIFIANT_FISCAL,
)


class Lacune(NamedTuple):
    """Un risque que le corpus ne permet pas de fonder, et pourquoi."""

    sujet_fr: str
    constat_fr: str


# Ces lacunes sont renvoyées dans le rapport. Un rapport qui liste ce qu'il
# n'a PAS pu vérifier vaut mieux qu'un rapport qui a l'air complet.
LACUNES: tuple[Lacune, ...] = (
    Lacune(
        sujet_fr="Obligation de dater la facture",
        constat_fr="Aucun des 4087 articles indexés n'énonce l'obligation de "
                   "porter une date sur une facture. L'obligation existe en "
                   "droit tunisien, mais son siège (Code de la TVA, textes "
                   "sur la facturation) n'est pas dans ce corpus. Mizan "
                   "signale l'absence de date comme un fait, sans la "
                   "qualifier de manquement légal.",
    ),
    Lacune(
        sujet_fr="Taux légal de TVA",
        constat_fr="Le taux de 19 % ne figure dans aucun article indexé. "
                   "L'écart entre la TVA portée sur la facture et le montant "
                   "hors taxe est donc présenté comme un constat de calcul, "
                   "et non comme la violation d'un taux légal.",
    ),
)
