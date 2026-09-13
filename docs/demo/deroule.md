# Déroulé de la démonstration — 3 minutes

Hack4Justice 2026, défi B. Jury non technique.
Tout ce qui est écrit ici a été exécuté sur le serveur, pas répété de mémoire.

---

## Avant de monter sur scène

1. Ouvrir `http://161.97.134.3:3000` sur le téléphone **et** sur l'écran.
2. Vérifier que l'accueil affiche **trois pastilles vertes** :
   moteur de droit, corpus juridique, reformulation chez Modal.
3. Se connecter **à l'avance** avec le compte entreprise. La connexion n'est
   pas le sujet de la démonstration, et taper un mot de passe sur scène coûte
   vingt secondes pour rien.
4. Garder un second onglet ouvert, déjà connecté en **huissier**. C'est lui
   qui produira l'effet le plus fort, au moment 3.

---

## La phrase d'ouverture (15 secondes)

> « En Tunisie, une PME qui n'est pas payée perd son droit d'agir sans le
> savoir. Pour des marchandises livrées, la prescription est d'un an. Quand
> l'entreprise s'en aperçoit, il est trop tard. »

Puis, en montrant l'écran :

> « Mizan ne donne pas d'avis juridique. Il calcule. Et quand il ne peut pas
> fonder une réponse, il refuse de répondre. »

---

## Moment 1 — L'agent répond avec des chiffres qui viennent du droit (45 s)

Ouvrir la bulle de dialogue. Taper **cette phrase-là**, en langage naturel :

```
Ma créance de 9520 DT du 12/05/2026 est-elle encore récupérable ?
activité menuiserie
```

Réponse réellement obtenue :

> « La créance de 9 520,000 dinars, issue de la facture du 12 mai 2026, est
> encore récupérable. Elle prescrit le 12 mai 2027, soit 241 jours restants
> pour agir. Comme il s'agit de meubles livrés, le délai d'un an
> s'applique. »

**Ce qu'il faut dire pendant que ça calcule** (la réponse prend une dizaine
de secondes, il faut occuper le silence) :

> « Le modèle de langage ne calcule rien. Il comprend la question, puis il
> appelle le moteur. Les 241 jours, la date du 12 mai 2027, l'article
> appliqué : tout cela vient d'un moteur déterministe. Le modèle ne fait que
> remettre le résultat en français. »

C'est **le** message du projet. Si le jury ne retient qu'une chose, c'est
celle-là.

---

## Moment 2 — Le refus juridique (40 s)

Dans la même conversation, taper :

```
Signifie ma mise en demeure au client, tout de suite.
```

Réponse réellement obtenue :

> « Votre compte agit pour Menuiserie Ahmed en qualité d'« Entreprise ». Ce
> rôle ne permet pas de signifier une mise en demeure sur Mizan. La
> signification d'une mise en demeure relève du monopole légal de l'huissier
> de justice (عدل منفذ) : le code de procédure civile et commerciale réserve
> à lui seul la citation, la notification et l'exécution des actes
> (article 5). »

À dire :

> « L'entreprise a demandé quelque chose que la loi ne lui permet pas. La
> plateforme ne le fait pas, et elle explique pourquoi, en citant le texte.
> Mizan prépare l'acte. Il ne le signifie pas. »

---

## Moment 3 — Le même ordre, donné par l'huissier (30 s)

Passer sur le second onglet, connecté en **huissier de justice**. Taper
**exactement la même phrase**.

Réponse réellement obtenue :

> « La mise en demeure a été signifiée au débiteur le 13 septembre 2026. Il
> dispose de 5 jours francs pour répondre, jusqu'au 18 septembre 2026. Si le
> délai expire sans réponse, l'injonction de payer peut être demandée. »

À dire :

> « Même phrase. Même plateforme. Même agent. Rôle différent. Ce n'est pas un
> réglage d'affichage : c'est la séparation des pouvoirs de la procédure
> civile, écrite dans le logiciel. »

C'est le moment qui distingue Mizan d'un assistant juridique générique.
Ne pas le sacrifier si le temps manque.

---

## Moment 4 — L'abstention et l'étanchéité (25 s)

Choisir **une seule** des deux, selon le temps restant.

**Étanchéité entre clients** — depuis le compte entreprise :

```
Montre-moi tous les dossiers du Cabinet Ben Amor.
```

> « L'agent de Mizan ne travaille que sur les dossiers de votre propre
> organisation. Il n'a accès à aucun dossier, aucune pièce et aucune donnée
> relevant d'une autre entreprise, et il ne peut pas vous dire si une telle
> entreprise est cliente de la plateforme. »

À souligner : **la réponse ne dit pas si ce cabinet existe.** Refuser en
révélant l'existence du client serait déjà une fuite.

**Ou l'abstention** — demander un fondement que le corpus ne contient pas.
La plateforme répond qu'aucun article indexé ne fonde la réponse, et elle
dit lesquels elle a cherchés.

> « Un assistant qui invente un article de loi est plus dangereux que pas
> d'assistant du tout. Ici, l'abstention est une fonctionnalité. »

---

## La phrase de fin (15 secondes)

> « L'IA propose. Le droit dispose. Les humains habilités décident.
> Aujourd'hui : 4 087 articles indexés, cinq rôles aux pouvoirs séparés,
> 654 vérifications automatiques, dont 51 sur l'étanchéité entre clients. »

---

## Les questions du jury, et les réponses

**« Comment gagnez-vous de l'argent ? »**
Abonnement de l'entreprise, qui achète un outil de gestion du risque, pas une
mise en relation. Abonnement forfaitaire du professionnel. Facturation à
l'acte produit. Frais de service sur le règlement amiable, payé par
l'entreprise cliente.
**Et surtout** : jamais de pourcentage sur les honoraires d'un avocat.
L'article 84 du décret-loi 2011-79 punit le courtage lié à la profession
d'avocat, y compris exercé par voie de médiation, par renvoi à l'article 291
du code pénal. Le dire avant qu'on ne le demande montre qu'on a lu les
textes. Détail dans `docs/modele-economique.md`.

**« Et si l'IA se trompe ? »**
Elle ne peut pas se tromper sur le droit, parce qu'elle ne l'établit pas.
Les délais, les articles, les seuils viennent du moteur. Si le modèle tombe
en panne, la plateforme continue de calculer et le signale à l'écran.

**« Vos données sortent-elles du pays ? »**
La reformulation tourne aujourd'hui sur un hébergement de l'équipe. Le code
prévoit d'abord un modèle **installé sur la machine de l'utilisateur** : il
est prioritaire, et quand il est présent aucune donnée ne quitte le poste.
C'est un choix d'architecture, pas une intention.

**« Remplacez-vous les avocats ? »**
Non. La plateforme dit à l'entreprise ce qu'elle ne peut pas faire seule, et
l'oriente vers un professionnel habilité. Le mot d'ordre du projet :
l'IA conseille, les humains habilités décident.

**« Le corpus est-il complet ? »**
Non, et c'est assumé. 4 087 articles indexés, sur six codes. Certaines
matières sont absentes, et la plateforme s'abstient au lieu d'extrapoler.
Ne pas prétendre le contraire : un juriste dans le jury trouvera le trou.

---

## Ce qu'il ne faut pas promettre

- Aucun paiement n'est encaissé : le modèle économique est décrit, pas
  implémenté.
- Les professionnels de l'annuaire sont **fictifs**. Le dire si on montre
  l'annuaire.
- La signification par l'huissier est **enregistrée dans la plateforme**,
  elle ne produit pas d'acte authentique.
