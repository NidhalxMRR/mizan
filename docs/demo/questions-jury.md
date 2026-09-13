# Les 10 questions du jury — et ce qu'on répond honnêtement

Hack4Justice · 3 minutes de questions après la démonstration.

**Règle absolue pour ces trois minutes :** quand la réponse n'existe pas encore
dans le code, on le dit. Un jury HiiL a vu des dizaines d'équipes broder. Celle
qui dit « pas encore fait, voici ce qui l'est » gagne la crédibilité que les
autres dépensent.

Aucun chiffre de marché, de financement ou d'utilisateurs n'apparaît ici :
**nous n'en avons mesuré aucun.**

---

## 1. « En quoi êtes-vous différents de ChatGPT ? »

**La question qui tombera, et la plus facile à rater.** Ne comparez pas les
modèles. Comparez les architectures.

> « ChatGPT est un modèle de langage : il produit du texte plausible. Mizan est
> un moteur déterministe qui a un modèle de langage en bout de chaîne, et
> l'ordre change tout.
>
> Chez nous le calcul vient d'abord. Le régime de prescription, la date
> d'échéance, le seuil de l'huissier, les articles cités : tout ça sort de code
> écrit à la main à partir des textes tunisiens. Le modèle n'intervient qu'après,
> pour reformuler un résultat déjà arrêté, et **on lui interdit de citer un
> article** — l'API supprime toute référence qu'il tenterait de produire.
>
> Trois conséquences concrètes :
> 1. Même question, même réponse. Toujours. Un modèle de langage ne garantit pas ça.
> 2. Quand nous ne savons pas, nous le disons — vous l'avez vu à l'écran.
> 3. Si le modèle tombe, Mizan continue de répondre juste. Nous l'avons testé :
>    on perd la reformulation, jamais le droit.
>
> Et une différence qui n'est pas technique : ChatGPT n'a pas lu le Code des
> obligations et des contrats tunisien article par article. Nous en avons indexé
> 4 087, en arabe, dans leur texte officiel. »

---

## 2. « Qu'est-ce qui vous empêche d'halluciner un article ? »

**Répondez par des mécanismes, pas par une promesse.** Il y en a quatre, tous
dans le code.

> « Quatre verrous, et ils sont indépendants les uns des autres.
>
> **Premier — le modèle ne choisit pas les articles.** Les citations viennent du
> moteur déterministe, pas de lui. Il les reçoit déjà faites.
>
> **Deuxième — le garde-fou d'abstention.** Avant d'afficher un article comme une
> réponse, on vérifie que les mots de la question figurent réellement dans le
> texte trouvé. Pas un score de similarité : la présence effective des mots.
> Sinon on s'abstient, et on affiche pourquoi.
>
> Un détail qui explique le choix : sur notre corpus, la question absurde "de
> quelle couleur est le ciel" obtient un score de 8,75, tandis que "الكمبيالة" —
> la lettre de change, question parfaitement légitime — obtient 6,98. Un simple
> seuil aurait donc accepté l'absurde et rejeté le droit. Il fallait autre chose
> que le score.
>
> **Troisième — le filtre de sortie.** Si le modèle écrit malgré tout un numéro
> d'article, une expression régulière le retire du texte avant qu'il ne quitte le
> serveur, et le remplace par une mention explicite. Bretelles et ceinture.
>
> **Quatrième — le contrôle anti-hallucination de la chaîne d'agents.** L'agent
> qui cherche les articles produit une liste blanche ; l'agent qui rédige est
> ensuite recoupé contre cette liste. Toute citation hors liste est signalée
> comme violation.
>
> Ce que nous ne prétendons pas : que le modèle ne se trompe jamais. Nous
> prétendons qu'**il n'a pas la main sur ce qui est cité.** »

---

## 3. « Est-ce que vous pratiquez le droit sans licence ? »

**La question piège devant un jury de juristes. Ne la fuyez pas.**

> « Non, et l'architecture a été pensée pour ça.
>
> Mizan fait trois choses : elle informe sur un délai légal, elle cite le texte
> officiel applicable, et elle décrit une procédure. Ce sont des informations
> publiques. Elle ne plaide pas, ne représente personne, ne signe aucun acte.
>
> Le point le plus net est celui de la mise en demeure. Notre module la produit
> comme un **projet d'acte**, jamais comme un acte signifié — et le document le
> dit sur lui-même. En droit tunisien, seul un huissier de justice signifie, et
> c'est la signification qui fait courir les délais, pas la rédaction. Mizan
> rédige ; elle ne signifie pas.
>
> Le module refuse même de produire une mise en demeure sur une créance
> prescrite, parce que ce serait le pire conseil possible : faire payer un
> huissier à un créancier pour réveiller un débiteur qui n'a qu'à opposer la
> prescription.
>
> Ce que nous n'avons pas encore : un avertissement juridique validé par un
> avocat tunisien, et des conditions d'utilisation. C'est à faire, et ça se fait
> avec le barreau, pas contre lui. Notre position est que Mizan amène à
> l'huissier et à l'avocat des dossiers déjà qualifiés — pas qu'elle les
> remplace. »

---

## 4. « Où vont les données de mes clients ? »

> « Elles ne sortent pas de la machine. C'est vérifiable maintenant : coupez le
> wifi, tout ce que vous avez vu continue de fonctionner.
>
> Le corpus est local. Le moteur est local. Le modèle de langage tourne sur un
> GPU ici, dans cette salle, pas chez un fournisseur étranger. Ce n'est pas une
> optimisation : un dossier de litige contient des factures, des contrats, des
> noms de clients. Un greffe tunisien ne peut pas envoyer ça chez un tiers
> étranger — donc si nous voulons être adoptables par une institution, c'est la
> condition d'entrée, pas une option.
>
> Sur le stockage, nous avons écrit le schéma PostgreSQL avec de la Row Level
> Security : l'isolation entre organisations est imposée par la base elle-même,
> pas par le code applicatif. Une requête mal écrite ne peut pas faire fuiter les
> dossiers d'une autre entreprise, parce que la base refuse. Nous avons **51
> assertions** qui essaient de casser cette isolation et qui échouent — et le
> test refuse même de s'exécuter sous un rôle superutilisateur, parce qu'il ne
> prouverait rien.
>
> **Ce qui n'est pas fait, et je préfère le dire :** il n'y a pas encore
> d'authentification sur l'API. Le schéma de sécurité de la base existe et est
> prouvé ; la couche HTTP qui s'y branche n'est pas écrite. C'est la première
> chose à faire avant tout pilote réel. »

---

## 5. « Quel est votre modèle économique ? »

**Le piège ici est d'inventer des chiffres. Ne le faites pas.**

> « Je vais être direct : nous n'avons pas de chiffre à vous donner, parce que
> nous n'en avons mesuré aucun. Vous donner un TAM ce matin serait vous donner un
> nombre inventé, et vous le sauriez.
>
> Ce que nous pouvons défendre, c'est la structure de coût, parce qu'elle est
> mesurée. Le modèle tourne sur un GPU d'ordinateur portable — pas sur une carte
> de centre de données. Il n'y a aucun coût d'API par requête. Le coût marginal
> d'un dossier traité est donc proche de l'électricité. C'est ce qui rend
> économiquement possible de servir un menuisier qui réclame 9 520 dinars : à ce
> montant, une consultation classique mange la créance.
>
> Trois pistes que nous jugeons crédibles, dans cet ordre de plausibilité :
> l'abonnement pour les organisations professionnelles et les chambres de
> commerce, qui servent beaucoup de PME identiques ; la licence institutionnelle
> pour un ministère ou un greffe, où l'argument souverain fait le travail ; et
> l'orientation qualifiée vers huissiers et avocats, qui reçoivent un dossier
> déjà instruit.
>
> Laquelle est la bonne ? Nous ne le savons pas encore, et c'est précisément ce
> qu'un accompagnement d'incubation nous permettrait de trancher avec des
> utilisateurs réels plutôt qu'avec un tableur. »

---

## 6. « Votre corpus fait 4 087 articles. Est-il complet et à jour ? »

> « Non, et le compte exact vous dira où sont les trous. Code des obligations et
> des contrats : 1 496 articles. Droits et procédures fiscaux : 814. Sociétés
> commerciales : 664. Code de commerce : 546. Procédure civile et commerciale :
> 488. Arbitrage : 79.
>
> Ce sont six codes. Le droit tunisien en compte davantage : le droit du travail
> n'y est pas, les textes sectoriels non plus.
>
> Et il y a un défaut que je préfère annoncer plutôt que vous laisser le
> découvrir : **le code de l'arbitrage est mal océrisé.** Le texte extrait est
> par endroits corrompu — des caractères parasites, des numéros d'articles en
> double. Il est indexé, mais nous ne le considérons pas comme citable en l'état.
> Les cinq autres codes sont propres et ont été relus.
>
> Sur la mise à jour : nous n'avons pas de chaîne d'ingestion automatique du
> Journal Officiel. C'est un travail d'ingénierie connu, pas résolu ici. »

---

## 7. « Un délai de prescription mal calculé peut faire perdre un droit. Qui est responsable ? »

**Question de juriste. Elle mérite mieux qu'une clause de non-responsabilité.**

> « Vous posez la bonne question, et la réponse honnête est : aujourd'hui,
> l'utilisateur, et ce n'est pas satisfaisant.
>
> Ce que nous avons fait pour réduire le risque. Le calcul est déterministe et
> testé — 76 tests Python passent, dont ceux du moteur juridique. Chaque
> conclusion affiche l'article qui la fonde, en arabe, mot pour mot depuis le
> corpus : l'utilisateur, ou son conseil, peut vérifier sans nous croire sur
> parole. Et le moteur explique son raisonnement en français — pourquoi le délai
> d'un an plutôt que celui de quinze ans — au lieu de sortir un chiffre nu.
>
> Ce que nous n'avons pas. Pas de validation formelle par un avocat tunisien en
> exercice. Pas d'assurance de responsabilité professionnelle. Pas encore de
> mention claire, à l'écran, disant que le résultat ne remplace pas une
> consultation.
>
> Notre position : Mizan doit dire à Ahmed « votre délai court, allez voir un
> huissier maintenant » — pas « vous gagnerez ». La différence entre informer et
> conseiller, nous la prenons au sérieux, mais elle doit encore être écrite dans
> l'interface. »

---

## 8. « Ahmed, menuisier à Sfax, ne parle pas français et n'utilise pas d'ordinateur. Comment l'atteignez-vous ? »

> « C'est notre plus grande faiblesse, et elle n'est pas technique.
>
> L'interface actuelle est en français, sur navigateur de bureau. Les articles
> sont affichés en arabe — c'est délibéré, c'est la langue officielle des textes
> — mais l'interface elle-même, non. Un artisan de Sfax ne s'en servira pas tel
> quel.
>
> Ce que nous pensons, sans l'avoir validé : le vrai point d'entrée n'est pas
> Ahmed seul devant un écran. C'est le comptable qui tient ses factures, la
> chambre de commerce de Sfax, l'huissier de son quartier. Ce sont eux qui ont un
> ordinateur, et eux que les PME consultent déjà.
>
> Mais je ne vais pas vous vendre ça comme une certitude : nous n'avons pas
> interrogé d'artisans. C'est exactement le genre de question qu'un
> accompagnement terrain permettrait de trancher, et c'est la première chose
> que nous ferions. »

---

## 9. « Pourquoi un modèle de 7 milliards de paramètres et pas un grand modèle ? »

> « Parce que la souveraineté des données passe avant la fluidité du texte, et
> parce que le modèle ne fait pas le travail juridique.
>
> Un grand modèle propriétaire suppose d'envoyer les factures et les contrats de
> PME tunisiennes sur des serveurs étrangers. Pour un greffe, c'est rédhibitoire.
> Nous avons donc choisi ce qu'on peut faire tourner ici : qwen2.5 en 7
> milliards, quantifié, mesuré à 19–22 tokens par seconde sur un GPU
> d'ordinateur portable. Une reformulation complète prend environ 7 secondes.
>
> Et c'est acceptable parce que son travail est étroit : il reformule un résultat
> déjà calculé. Il ne raisonne pas sur le droit, il ne choisit pas les articles.
> Sur cette tâche-là, un grand modèle ne serait pas plus juste — il serait
> seulement plus élégant, et hors de la machine.
>
> L'architecture permet d'en changer : les hébergements sont une liste ordonnée
> avec bascule automatique. Si demain un modèle arabophone souverain est
> disponible, c'est une variable d'environnement. »

---

## 10. « Qu'est-ce qui existe vraiment, et qu'est-ce qui est une maquette ? »

**Si elle tombe, c'est une chance. Répondez précisément.**

> « Tout ce que vous avez vu tourne. Rien n'est une maquette cliquable.
>
> **Ce qui fonctionne :** le moteur juridique déterministe, avec ses tests. Une
> API de cinq points d'entrée. Trois écrans branchés dessus — l'analyse est
> calculée côté serveur, elle est dans le HTML, vous pouvez la vérifier au
> `curl`. Le corpus de 4 087 articles avec sa recherche et son garde-fou. Une
> chaîne de trois agents qui traite une facture PDF de bout en bout, avec
> contrôle anti-hallucination. Le schéma PostgreSQL avec son isolation prouvée
> par 51 assertions. En tout, 127 vérifications automatiques : 76 tests Python et
> 51 assertions de base de données.
>
> **Ce qui n'existe pas :** l'intégration e-Houwiya, la marketplace d'huissiers
> et d'avocats, le paiement, l'authentification sur l'API, la licence du projet.
>
> Nous avons une liste écrite de nos limites. Je préfère vous la donner plutôt
> que vous la laisser trouver. »

*(Tendez `limites-connues.md`, ou proposez-le. Le geste compte autant que le
document.)*

---

## Trois règles pour ces trois minutes

1. **Si vous ne savez pas, dites-le.** « Nous ne l'avons pas mesuré » est une
   réponse acceptable devant HiiL. Un chiffre inventé ne l'est pas, et un jury
   de juristes détecte le flou mieux que quiconque.
2. **Ramenez toujours à l'abstention.** C'est le seul argument que les autres
   équipes n'auront pas. Presque toutes les questions peuvent y revenir.
3. **Ne promettez rien au futur sans dire que c'est du futur.** Les mots
   « pas encore » sont vos alliés, pas votre faiblesse.
