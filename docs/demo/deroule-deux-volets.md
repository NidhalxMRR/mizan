# Déroulé de la démonstration — deux volets, trois minutes

Ce document se lit debout, avant de monter. Il ne contient pas ce que le
produit sait faire : il contient ce que l'on montre, dans quel ordre, et ce
que l'on répond quand on est coupé.

**Les deux moitiés se raccordent d'elles-mêmes** : le même Ahmed, la même
facture de 9 520 dinars, le même client qui ne paie pas. Le premier volet
regarde la créance du côté de celui qui réclame ; le second va jusqu'au
client qui doit payer, et lui laisse répondre.

---

## Avant de monter — trois gestes, deux minutes

1. **Se connecter** sur le premier volet, hors de vue du jury.
   `http://161.97.134.3:3000/connexion` — `direction@atelier-medina.tn`
   / `Mizan2026`. On monte déjà identifié : personne ne regarde quelqu'un
   taper un mot de passe.

2. **Ouvrir le second volet dans un autre onglet** :
   `http://161.97.134.3:8830/deposer`. Le laisser chargé.

3. **Vérifier les trois services** — si l'un ne répond pas, on le sait
   maintenant et non sur scène :
   ```
   curl -s -o /dev/null -w "%{http_code}\n" -m 12 http://161.97.134.3:3000/
   curl -s -o /dev/null -w "%{http_code}\n" -m 12 http://161.97.134.3:8820/sante
   curl -s -o /dev/null -w "%{http_code}\n" -m 12 http://161.97.134.3:8830/health
   ```
   Trois fois `200`. Le second volet se relance seul toutes les deux minutes
   s'il tombe.

---

## Minute 1 — la question qu'un artisan pose vraiment (0:00 → 1:00)

**Écran : le premier volet, déjà connecté.**

> « Ahmed est menuisier à Sfax. Une société lui doit neuf mille cinq cent
> vingt dinars depuis le douze mai. Il ne demande pas un cours de droit. Il
> demande une seule chose : est-ce que je peux encore récupérer mon argent ? »

**Geste** — ouvrir « Poser une question juridique », taper :

> *Ma créance de 9520 DT du 12/05/2026 est-elle encore récupérable ?
> activité menuiserie*

**Pendant que le moteur travaille** (une vingtaine de secondes — ne pas se
taire, c'est le moment de placer la phrase suivante) :

> « Le modèle ne répond pas de mémoire. Il ne répond que sur quatre mille
> quatre-vingt-sept articles du droit tunisien, et il affiche l'article qui
> fonde chaque phrase. Quand il ne trouve pas, il le dit — il ne comble
> pas. »

**Résultat attendu à l'écran** : deux cent quarante et un jours,
prescription le douze mai 2027, articles cités dont le COC 403 et le
CPCC 60.

---

## Minute 2 — ce que le produit REFUSE de faire (1:00 → 2:00)

C'est le moment qui compte devant un jury de juristes. Un outil qui accepte
tout ne vaut rien ; celui qui refuse pour un motif nommé vaut quelque chose.

**Geste** — demander : *« Signifie ma mise en demeure »*

**Résultat attendu** : le refus, motivé par l'article 5 du code de procédure
civile — la signification appartient à l'huissier de justice (عدل منفذ).

> « L'intelligence artificielle conseille. Les professionnels habilités
> décident. Ce n'est pas une limite technique que nous aurions contournée si
> nous avions eu le temps : c'est la loi, et le produit l'applique. »

**Geste** — ouvrir « Mon espace », montrer les six qualités : entreprise,
avocat, professionnel accrédité, huissier, greffier, administrateur. Chacune
voit ce qu'elle a le droit de faire, et voit aussi ce qui lui est fermé,
avec le motif.

> « Un avocat représente et signe les écritures, parce que l'article 57 du
> code des droits et procédures fiscaux rend sa présence obligatoire au-delà
> de vingt-cinq mille dinars. Il ne signifie pas : ce n'est pas son
> monopole. »

---

## Minute 3 — l'autre partie (2:00 → 3:00)

**Geste** — cliquer « Le recouvrement » dans la barre de gauche, ou passer à
l'onglet du second volet.

> « Jusqu'ici nous avons regardé la créance du côté d'Ahmed. Mais un litige
> a deux côtés, et une justice qui n'écoute qu'un seul camp n'est pas une
> justice. »

**Geste** — déposer `facture_ahmed.pdf` sur `/deposer`. Le montant, la date
et le numéro sont lus seuls.

**Puis** — montrer l'écran de réponse du client : il voit la réclamation,
et il peut accepter, refuser, ou contre-proposer.

> « Le client n'a pas de compte à créer et rien à payer. Il reçoit un lien,
> il répond. C'est à cet endroit qu'un litige se règle sans procès — et
> c'est précisément ce que demande le challenge : résoudre avant le
> tribunal. »

**Dernière phrase, à dire lentement :**

> « Nous ne remplaçons ni l'avocat, ni l'huissier, ni le juge. Nous faisons
> en sorte qu'une petite entreprise sache où elle en est, et que l'autre
> partie puisse répondre. »

---

## Les questions qui viendront, et la réponse courte

**« L'écran cite cinq articles mais le calcul n'en utilise que deux. »**
Vrai. Deux articles fondent le calcul — le COC 403 pour le délai, le
CPCC 60 pour l'interruption. Les trois autres sont le contexte que le
moteur a jugé pertinent et qu'il affiche par transparence, plutôt que de
les cacher.

**« Et si le modèle se trompe ? »**
Le calcul de prescription n'est pas fait par le modèle. Il est fait par un
code déterministe, testé — huit cent cinquante-sept tests. Le modèle
explique, il ne calcule pas.

**« Le corpus est-il à jour ? »**
Quatre mille quatre-vingt-sept articles, comptés en direct par le service,
visibles sur `/corpus`. Ce sont des textes officiels, pas des résumés.

**« Pourquoi deux applications ? »**
Parce que ce sont deux moments différents du même litige, et parce que le
jour d'une démonstration, deux applications qui tombent séparément valent
mieux qu'une seule qui tombe entièrement.

**« C'est en HTTP, pas en HTTPS. »**
Oui. C'est une démonstration servie depuis un serveur de développement. Le
chiffrement est une ligne de configuration, pas une question d'architecture.

---

## Si quelque chose tombe sur scène

- **Le moteur ne répond pas** → passer directement à `/dossier` avec les
  paramètres : le calcul de prescription ne dépend d'aucun modèle. Vérifié :
  la route `/dossiers/analyser` rend `jours_restants = 241` sans qu'aucun
  modèle n'intervienne.
  `http://161.97.134.3:3000/dossier?montant=9520&date=2026-05-12&activite=menuiserie`
- **Le second volet ne répond pas** → il se relance seul dans les deux
  minutes ; en attendant, rester sur le premier et décrire l'écran de
  réponse plutôt que de le montrer.
- **Rien ne répond** → `/corpus` est une page statique : quatre mille
  articles, et l'on parle du reste.

### Sur le modèle : deux hébergements, un seul allumé

Le service interroge d'abord un modèle installé sur la machine de Nidhal,
puis bascule sur le déploiement Modal de Zied. **Le premier est actuellement
éteint** (connexion refusée) — c'est normal, le portable n'est pas allumé.
Le second répond.

Si l'on demande d'où vient la réponse, le service le dit lui-même sur
`/sante` : champ `hebergements`, avec pour chacun s'il est joignable et
pourquoi. Ne pas prétendre que les deux tournent : dire qu'il y en a deux,
que l'un prend le relais de l'autre, et que c'est celui de Zied qui répond
aujourd'hui.

---

## Les adresses, en un bloc

```
Premier volet   http://161.97.134.3:3000
Second volet    http://161.97.134.3:8830
Le dossier      http://161.97.134.3:3000/dossier?montant=9520&date=2026-05-12&activite=menuiserie
Le corpus       http://161.97.134.3:3000/corpus
Dépôt (Zied)    http://161.97.134.3:8830/deposer
```

Comptes de démonstration, tous avec le même mot de passe `Mizan2026` :

| Adresse | Qualité |
|---|---|
| `direction@atelier-medina.tn` | Entreprise |
| `cabinet@avocat-tunis.tn` | Avocat |
| `mediateur@cabinet-benali.tn` | Professionnel accrédité |
| `etude@hj-tunis.tn` | Huissier de justice |
| `greffe@tc-tunis.tn` | Greffier |
| `exploitation@mizan.tn` | Administrateur |
