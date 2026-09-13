# Mizan — scénario de démonstration (3 minutes)

Hack4Justice · Challenge B · jury non technique (juristes, institutionnels HiiL).
Format : **3 minutes de démo + 3 minutes de questions.**

Tout ce qui est écrit ici a été exécuté et vérifié le 13/09/2026. Les URL sont
exactes, copiables, et rendues côté serveur : ce qui s'affiche est dans le HTML,
pas injecté après coup.

---

## Avant d'entrer dans la salle

```bash
cd ~/mizan && ./docs/demo/preparer-demo.sh
```

Le script ne lance rien, il vérifie et dit quoi faire. **Ne commencez pas tant
qu'il n'affiche pas au minimum `PRÊT` ou `PRÊT (mode dégradé)`.**

Ouvrez **trois onglets dans cet ordre**, et laissez-les chargés — chaque page
est déjà rendue, vous ne perdrez pas une seconde devant le jury :

| Onglet | URL | Ce qu'il montre |
|---|---|---|
| 1 | `http://127.0.0.1:3000/` | L'état réel du service + le principe |
| 2 | `http://127.0.0.1:3000/dossier?montant=9520&date=2026-05-12&activite=menuiserie` | Le cas Ahmed, déjà calculé |
| 3 | `http://127.0.0.1:3000/corpus?q=recette%20de%20couscous%20au%20poisson` | L'abstention |

> **Pourquoi l'onglet 2 porte des paramètres dans l'URL.** La page `/dossier`
> sans paramètres part sur une facture du **2025-11-03** (51 jours restants,
> urgence `critical`) — ce n'est pas le cas d'Ahmed. L'URL ci-dessus est la
> seule qui produit les **241 jours** du récit. Vérifié au `curl`.

---

## Minutage

| Temps | Séquence | Onglet |
|---|---|---|
| 0:00 – 0:35 | Le problème d'Ahmed | 1 |
| 0:35 – 1:30 | Le moteur répond, article par article | 2 |
| 1:30 – 2:25 | **Ce que Mizan refuse de dire** | 3 |
| 2:25 – 3:00 | Souveraineté, et la phrase de fin | 1 ou 3 |

---

## 0:00 – 0:35 · Le problème d'Ahmed

**Onglet 1 — `http://127.0.0.1:3000/`**

Ne lisez pas l'écran. Regardez le jury.

> « Ahmed est menuisier à Sfax. Il a livré des meubles, facture 2026-041,
> 9 520 dinars, datée du 12 mai 2026. Il n'a jamais été payé.
>
> Ahmed ne sait pas qu'en droit tunisien, le prix des marchandises livrées se
> prescrit par **un an** — et pas par quinze. S'il attend, il ne perd pas une
> facture : il perd son droit d'agir. Il n'ira pas voir un avocat pour
> 9 520 dinars, parce que la consultation coûte une part de ce qu'il réclame.
>
> Nous avons construit Mizan pour ce moment-là. »

Pointez la bannière d'état du service — elle est lue à l'instant, en direct :

> « Ce chiffre d'articles indexés n'est pas écrit en dur dans la page. Il est
> compté par l'index au moment où vous le regardez. »

*(Repli si l'API est éteinte : la page affiche un bloc de panne explicite au
lieu d'un faux chiffre. Dites-le — c'est une démonstration d'honnêteté.)*

---

## 0:35 – 1:30 · Le moteur répond

**Onglet 2 — `/dossier?montant=9520&date=2026-05-12&activite=menuiserie`**

La page est déjà calculée. Faites défiler lentement, de haut en bas.

> « Trois informations, c'est tout ce qu'on demande : un montant, une date, une
> activité. »

**Montrez le compte à rebours :**

> « **241 jours.** Pas "environ un an", pas "prochainement". La date d'échéance
> est le 12 mai 2027. »

**Montrez le bloc "pourquoi ce délai" :**

> « Et voici pourquoi — c'est la partie qui compte : *"Meubles fabriqués puis
> livrés au client : la créance porte sur le prix de marchandises livrées, non
> sur une simple prestation de service. C'est le délai d'un an qui s'applique,
> et non celui de quinze ans."*
>
> Ce raisonnement n'a pas été écrit par une intelligence artificielle. Il sort
> d'un moteur déterministe. Même question, même réponse, à chaque fois. »

**Montrez l'encart huissier puis les articles en arabe :**

> « La créance dépasse 150 dinars : la sommation doit passer par un huissier de
> justice, qui laisse 5 jours francs au débiteur.
>
> Et chaque affirmation porte son article, cité **en arabe, mot pour mot depuis
> le corpus** : COC article 403 pour la prescription, CPCC article 60 pour
> l'huissier. »

**Si et seulement s'il vous reste du temps** — le bouton « Demander la
reformulation », mesuré à **7 secondes** :

> « Là, et seulement là, un modèle de langage intervient. Il reçoit le résultat
> déjà calculé et le réécrit en français simple. Il n'a pas le droit de citer un
> article — et s'il en invente un, l'API le retire avant l'affichage. »

> ⚠️ **N'appuyez sur ce bouton que si le chronomètre est sous 2:00.** En cas de
> doute, sautez-le : il n'est pas nécessaire au récit.

---

## 1:30 – 2:25 · Ce que Mizan refuse de dire — **le cœur de la démo**

**Onglet 3 — `/corpus?q=recette de couscous au poisson`**

C'est la séquence à ne pas manquer. Ralentissez.

> « Maintenant je vais faire quelque chose d'un peu étrange : je vais poser à
> une plateforme juridique une question qui n'est pas juridique. »

Montrez le bloc gris **ABSTENTION MOTIVÉE — GARDE-FOU DÉCLENCHÉ** :

> « *"Aucun article du corpus ne répond à cette question avec une confiance
> suffisante. Mizan préfère se taire plutôt que d'inventer une référence."*
>
> Zéro article retenu. Et remarquez la couleur : **c'est gris, pas rouge.**
> Ce n'est pas une panne. C'est une décision du système. »

Laissez un temps, puis le point qui vaut le prix :

> « Posez cette question à un assistant grand public : il vous répondra. Posez-lui
> une question de droit tunisien à laquelle il ne sait pas répondre — il vous
> répondra quand même, avec un numéro d'article plausible et faux.
>
> Une référence fausse dans un dossier déposé au tribunal, ce n'est pas une
> imprécision. C'est une pièce qui décrédibilise un justiciable devant un juge.
>
> Notre garde-fou ne regarde pas un score de pertinence. Il vérifie que les
> **mots de la question figurent réellement dans le texte trouvé**. Sinon, il se
> tait. »

**Enchaînez immédiatement — la contre-preuve.** Cliquez l'essai rapide
**`عدل منفذ`** (huissier) *ou* tapez-le :

> « Et pour qu'il soit clair que ce n'est pas un système qui dit toujours non —
> une vraie question de droit : "عدل منفذ", l'huissier de justice. »

L'écran bascule sur **LE CORPUS RÉPOND** / *Garde-fou passé : termes retrouvés
dans le texte*, avec les articles en arabe.

> « Il répond quand il peut. Il se tait quand il ne peut pas. C'est tout le
> projet. »

> ⚠️ **Les essais rapides sûrs pour la démo : `التقادم`, `عدل منفذ`, `الصلح`.**
> Les trois passent le garde-fou — vérifié.
> **N'utilisez PAS le bouton `الفاتورة`** : il déclenche une abstention
> (« aucun article trouvé »), ce qui brouille la contre-démonstration au
> pire moment.

---

## 2:25 – 3:00 · Souveraineté et clôture

Restez sur l'écran où vous êtes. Ne changez plus d'onglet.

> « Un dernier point, et il est institutionnel.
>
> Tout ce que vous venez de voir a tourné **sur cette machine**. Pas de wifi, pas
> d'API étrangère. Le corpus est local. Le moteur est local. Même le modèle de
> langage tourne sur un GPU ici, dans cette salle.
>
> Ce n'est pas un choix technique, c'est la condition d'adoption : un dossier de
> litige contient des factures, des contrats, des noms de clients. Un greffe
> tunisien ne peut pas envoyer ça chez un tiers étranger.
>
> Et si ce modèle tombe — il peut tomber — la plateforme continue. Le calcul du
> délai, les articles, les étapes : rien de tout ça ne dépend d'une IA. On perd
> la reformulation. On ne perd jamais le droit. »

**La phrase de fin, nette, et on s'arrête :**

> « **L'IA propose. Le droit dispose.** »

---

## Plan de repli — le modèle local est tombé

Le tunnel SSH vers le GPU peut tomber le jour J. **Ce cas a été testé pour de
bon** (hébergement pointé vers un port mort) : l'API répond **HTTP 200**, pas
une erreur, avec l'analyse juridique complète et le motif exact de la panne.

**Ce que vous faites :** rien de spécial. **Ne cachez pas la panne — utilisez-la.**

1. La bannière d'accueil affichera le modèle indisponible avec son motif.
2. Le bloc de reformulation affichera *« Modèle indisponible — texte produit par
   le moteur seul »*, suivi du texte complet et juste.
3. Dites exactement ceci :

> « Vous tombez bien. Le modèle vient de tomber — et regardez ce que la
> plateforme affiche : le délai, l'échéance, les articles, les étapes. Tout est
> là. Elle vous dit même précisément pourquoi le modèle manque, au lieu de
> faire semblant. C'est exactement ce que je vous décrivais : l'IA n'est pas le
> produit. Le moteur juridique l'est. »

C'est un meilleur argument que la démo nominale. **Ne paniquez pas : encaissez.**

### Autres reculs

| Panne | Ce qui reste | Ce que vous dites |
|---|---|---|
| Next.js tombé (port 3000) | L'API en direct : `curl http://127.0.0.1:8820/dossiers/analyser` | « Je vous montre la donnée brute, c'est la même » |
| API tombée (port 8820) | Les 3 diagrammes dans `~/mizan/docs/diagrams/*.html` (statiques, s'ouvrent sans serveur) | Racontez l'architecture au tableau |
| Tout est tombé | `scenario.md` + les diagrammes | Le récit d'Ahmed tient sans écran |

---

## Ce qu'il ne faut **pas** faire

- **Ne lancez pas `python -m agents.chaine` en direct.** La chaîne complète prend
  **31 secondes** (mesuré), dont 30,8 s pour le seul rédacteur. C'est un tiers de
  votre temps de parole. Elle est faite pour être racontée, pas exécutée.
- **Ne cliquez pas « Demander la reformulation » après 2:00.**
- **Ne dites pas « 136 tests ».** Le compte vérifié est **127** : 76 tests
  Python (`pytest`, tous verts) + 51 assertions d'isolation PostgreSQL. Un
  chiffre juste et vérifiable vaut mieux qu'un chiffre rond.
- **N'annoncez pas de chiffre de marché.** Vous n'en avez aucun de mesuré.
- **Ne promettez pas e-Houwiya, la marketplace ou le paiement** : voir
  `limites-connues.md`, à annoncer vous-même avant qu'on ne vous les demande.

---

## Chiffres exacts à connaître par cœur

| Donnée | Valeur vérifiée |
|---|---|
| Facture Ahmed | 2026-041 · 9 520,000 DT · 12/05/2026 |
| Régime | `goods_1y` — prix des marchandises livrées |
| Échéance | 2027-05-12 · **241 jours restants** |
| Articles | COC art. 403 · CPCC art. 60 · COC art. 277 · COC art. 278 · CPCC art. 59 |
| Huissier | requis · **5 jours francs** |
| Corpus | **4 087 articles** — COC 1496 · Fiscal 814 · Sociétés 664 · Commerce 546 · CPCC 488 · Arbitrage 79 |
| Modèle | qwen2.5:7b-instruct-q4_K_M, local, 19–22 tok/s |
| Reformulation | **7,3 s** mesuré via l'API |
| Moteur seul | **< 6 ms** |
| Recherche corpus | **< 16 ms** |
| Tests | 76 pytest + 51 assertions RLS = **127** |
