# packages/contrats — analyse de risques d'un contrat commercial tunisien

Lit le texte d'un contrat (français, arabe, ou bilingue) et signale les clauses
qui engagent lourdement le signataire. **Chaque clause rendue est fondée sur un
article réellement présent dans le corpus**, avec sa citation arabe exacte.

## Utilisation

```bash
cd ~/mizan && source .venv/bin/activate
python packages/contrats/analyse.py packages/contrats/exemples/contrat_fr_fourniture.txt
python packages/contrats/analyse.py packages/contrats/exemples/contrat_ar_entreprise.txt
```

```python
from packages.contrats import analyser, analyser_pdf, rendre

rapport = analyser(texte_du_contrat)      # ou analyser_pdf('contrat.pdf')
if not rapport.analyse:
    print(rapport.motif_abstention)        # le moteur s'est abstenu
for clause in rapport.clauses:
    clause.extrait                         # VERBATIM du contrat
    clause.fondements[0].citation_ar       # « الفصل 274 من مجلة الالتزامات والعقود »
rapport.to_dict()                          # sérialisable JSON pour l'API
```

## Les trois règles du moteur

1. **Aucune paraphrase.** `clause.extrait` est le texte du contrat, caractère
   pour caractère, avec sa ligne et sa position. Le juriste peut le citer.
2. **Aucune clause sans article.** Les articles sont *relus dans le corpus* à
   chaque exécution (`fondements.py`), jamais écrits à la main. Si un article
   disparaît du corpus, la règle se désactive au lieu de citer un fantôme
   (test : `test_regle_sans_fondement_est_desactivee`).
3. **Le droit dit ce qu'il dit.** Ce que le corpus ne fonde pas est déclaré
   dans `rapport.lacunes` et affiché en fin de rapport.

## Ce que le corpus FONDE (9 clauses détectées)

| Clause | Gravité | Articles du corpus |
|---|---|---|
| Clause résolutoire de plein droit | critique | COC 274, 680, 273 |
| Clause compromissoire (arbitrage) | critique | Arbitrage 7, 5, 52 |
| Renonciation anticipée à la prescription | critique | COC 386, 402 |
| Clause pénale / indemnité forfaitaire | élevé | COC 277, 278 |
| Clause limitative de responsabilité | élevé | Commerce 643, Sociétés 118, COC 642 |
| Clause attributive de juridiction | élevé | CPCC 3, 30 |
| Clause laissée à la seule volonté d'une partie | élevé | COC 121, 119 |
| Délai de paiement et pénalités de retard | moyen | COC 269, 278, 1100 |
| Réserve de propriété | moyen | COC 583, 601 |

Les 23 articles sont vérifiés présents dans le corpus par
`test_tous_les_fondements_du_catalogue_existent`.

## Ce que le corpus NE FONDE PAS — à dire au client

C'est la partie qu'il faut lire avant la démo. Ces limites sont **dans le
code** (`fondements.LACUNES`) et **dans chaque rapport**, pas seulement ici.

- **Clause abusive entre commerçant et non-commerçant — PAS DE RÈGLE.**
  Le corpus ne contient aucun texte de droit de la consommation (la loi
  92-117 n'y est pas ; zéro article contenant `المستهلك`). La qualification
  « clause abusive » serait invérifiable : **aucune règle ne la produit.**
  Le moteur détecte à la place la clause *potestative* (COC 121), qui est
  le seul angle que le corpus fonde réellement.

- **Réduction judiciaire de la clause pénale — NON FONDÉE.** Aucun article du
  corpus ne nomme la clause pénale ni ne permet au juge d'en réduire le
  montant. Seul est fondé le principe que l'évaluation du préjudice relève du
  tribunal (COC 278 : « موكولة لحكمة المجلس »). Le rapport le dit en réserve.

- **Réserve de propriété — RÉGIME ABSENT.** Aucun article ne la régit comme
  telle, ni son opposabilité en procédure collective. Seule est citée la règle
  à laquelle elle *déroge* : le transfert de propriété par le seul consentement
  (COC 583).

- **Limitation de responsabilité — FONDEMENTS SPÉCIAUX SEULEMENT.** Les trois
  articles disponibles sont sectoriels (transport, action sociale, garantie
  d'éviction). Le corpus ne porte **aucune règle générale** annulant
  l'exonération du dol ou de la faute lourde. Hors de ces terrains, le moteur
  signale sans conclure à la nullité.

- **Clause attributive de juridiction — VALIDITÉ NON TRANCHÉE.** CPCC 3 prive
  d'effet toute convention contraire à la compétence *d'attribution*, mais ne
  dit pas que toute clause de compétence *territoriale* est nulle. Le moteur
  signale et cite, sans trancher.

La seule clause où le corpus tranche une **nullité** est la renonciation
anticipée à la prescription : COC 386, « لا يسوغ ترك حق التمسك بمرور الزمان
قبل حصوله ».

## Abstention

Le moteur refuse d'analyser un document qui ne se présente pas comme un contrat
(moins de 2 marqueurs sur 8). Un CV mentionnant « pénalités de retard,
arbitrage » produit une abstention, pas une liste de clauses — c'est la version
contrat de la faute que `doc_gate.py` a corrigée pour les factures.

La négation est filtrée en français et en arabe : « le présent contrat ne
contient aucune clause pénale » n'alerte pas, la clause part dans
`rapport.niees`. Le filtre ne franchit pas la fin de phrase, pour ne pas
masquer une clause réelle voisine.

## Bilinguisme

Les contrats tunisiens doublent souvent leurs stipulations sensibles. Les
motifs couvrent les deux langues, et la normalisation arabe (diacritiques,
tatweel, variantes d'alif/hamza, chiffres indo-arabes) **conserve la longueur
du texte** — invariant testé, sans lequel les positions des extraits seraient
décalées et les citations fausses.

## Tests

```
cd ~/mizan && source .venv/bin/activate && pytest packages/contrats/ -q
46 passed
```

Écrits d'abord contre les entrées hostiles : vide, blancs, caractères de
contrôle, CV, article de presse, recette de cuisine, négations FR/AR, contrat
400 000 caractères, PDF inexistant, corpus vidé.

## Note

PyMuPDF (AGPL) n'est pas utilisé. L'extraction PDF passe par pypdf (BSD) avec
pdfplumber (MIT) en secours.
