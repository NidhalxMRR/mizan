# Ce que Mizan ne fait pas

Liste tenue honnêtement, vérifiée dans le code le 13/09/2026.

**À quoi elle sert.** Un jury qui découvre tout seul une limite que vous n'avez
pas annoncée cesse d'écouter le reste — il se demande ce que vous cachez encore.
Un jury à qui vous annoncez vos limites vous croit sur ce qui marche.

Annoncez-en deux ou trois pendant les questions, spontanément. Gardez ce
document sous la main pour le tendre si on vous le demande.

---

## Les cinq à annoncer vous-même

### 1. e-Houwiya n'est pas intégrée

L'identité numérique tunisienne n'est branchée nulle part. Il n'y a aucun appel
vers e-Houwiya dans le code.

Le schéma de base de données prévoit des utilisateurs, des rôles et des
organisations, mais l'identité n'est pas fédérée. **Conséquence directe :
aujourd'hui, rien ne prouve qu'un utilisateur est bien celui qu'il prétend
être.** Pour une plateforme destinée à toucher un greffe, c'est un prérequis,
pas une amélioration.

### 2. Il n'y a pas d'authentification sur l'API

Les cinq points d'entrée de l'API sont ouverts. Aucune vérification de jeton,
aucune clé, aucune session — vérifié : aucun mécanisme d'authentification n'est
présent dans `api/main.py`.

C'est la limite la plus importante de la liste, et il faut la formuler
précisément, parce qu'elle est facile à mal comprendre :

> Le schéma PostgreSQL a une Row Level Security réelle, et son isolation est
> prouvée par 51 assertions qui essaient de la casser. Ce travail est fait.
> Ce qui manque, c'est la couche HTTP qui relie un utilisateur authentifié à un
> contexte de base de données. **La serrure existe et elle tient. La porte n'est
> pas encore posée dessus.**

Aucun déploiement réel n'est envisageable avant que ce soit écrit.

### 3. La marketplace n'existe pas

Aucune mise en relation avec un huissier ou un avocat. Pas d'annuaire, pas de
prise de rendez-vous, pas de paiement, pas de suivi d'exécution.

Mizan dit à Ahmed qu'il doit passer par un huissier de justice et pourquoi. Elle
ne lui en trouve pas un. C'est souvent la première question posée après une
démonstration — mieux vaut prendre les devants.

### 4. Le code de l'arbitrage n'est pas citable

79 articles du Code de l'arbitrage sont indexés, mais **leur texte est corrompu
par l'OCR**. Vérifié en lisant directement l'index : caractères parasites au
milieu des mots (`أحكا؟ © جلة`), fragments de notes de bas de page mêlés au
corps du texte, et plusieurs numéros d'articles en double.

Ils apparaissent donc dans les résultats de recherche, mais **nous ne les
considérons pas comme citables** dans un acte. Les cinq autres codes — COC,
fiscal, sociétés, commerce, procédure civile — sont propres.

Si on vous demande pourquoi les avoir laissés : parce que les retirer
silencieusement serait pire. Ils sont là, leur défaut est documenté.

### 5. Le projet n'a pas de licence

Aucun fichier `LICENSE` à la racine. Le dépôt est donc, juridiquement, « tous
droits réservés » par défaut.

Ce n'est pas un oubli d'ingénierie, c'est une décision à prendre : une
plateforme qui vise l'adoption par une institution publique doit choisir
explicitement entre ouverture et propriété. Ce n'est pas tranché.

---

## Les autres limites, par ordre d'importance

### Produit

- **L'interface est en français uniquement.** Les articles sont affichés en
  arabe — c'est la langue des textes officiels — mais l'interface elle-même ne
  l'est pas. Un artisan arabophone ne s'en sert pas tel quel.
- **Aucune interface mobile.** L'application est faite pour un écran de bureau.
- **Aucun test avec un utilisateur réel.** Aucune PME, aucun artisan, aucun
  huissier n'a essayé Mizan. Le parcours d'Ahmed est plausible, pas validé.
- **Aucun compte, aucune persistance côté utilisateur.** On ne peut pas
  retrouver un dossier analysé hier : le schéma de base existe, l'application
  ne s'y branche pas encore.
- **Le dépôt de pièce accepte une facture et la refuse si ce n'en est pas une**,
  mais ne gère ni bon de livraison, ni contrat, ni relevé bancaire.

### Droit

- **Aucune validation par un avocat tunisien en exercice.** Le moteur a été
  écrit à partir des textes, et testé, mais aucun professionnel du droit ne l'a
  relu et validé.
- **Aucun avertissement juridique à l'écran.** Rien ne dit explicitement à
  l'utilisateur que le résultat ne remplace pas une consultation. À écrire.
- **Pas de conditions d'utilisation, pas de politique de données.**
- **Six codes seulement.** Le droit du travail est absent, les textes
  sectoriels aussi.
- **Aucune chaîne de mise à jour du corpus.** Une modification au Journal
  Officiel ne se propage pas. La mise à jour est manuelle.
- **Le moteur ne connaît pas les causes d'interruption ou de suspension de la
  prescription.** Une reconnaissance de dette ou une action en justice remet le
  délai à zéro ; Mizan ne le prend pas en compte. Le compte à rebours est donc
  un plancher prudent, pas une vérité complète. **C'est la limite la plus
  sérieuse du moteur juridique** — si un juriste la soulève, reconnaissez-la
  franchement, elle est réelle.

### Technique

- **Aucun chiffrement au repos** prévu pour les pièces déposées.
- **Aucune journalisation d'audit** des consultations.
- **Aucun déploiement.** Tout tourne en local sur une machine de développement.
  Il n'y a pas d'environnement de production, pas de sauvegarde, pas de
  supervision.
- **Le modèle dépend d'un tunnel SSH vers un GPU personnel.** Ce n'est pas une
  infrastructure, c'est un montage de hackathon. Le mode dégradé est testé et
  fonctionne, mais il ne remplace pas un hébergement.
- **Les tests d'acceptation JavaScript (`tests/*.js`) visent le port 8811**,
  qui n'est plus celui de l'API (8820). Ils ne sont donc pas à jour et ne sont
  pas comptés dans les 127 vérifications annoncées.
- **Le test d'isolation PostgreSQL n'est pas rejouable** sur une base déjà
  amorcée : il refuse de s'exécuter deux fois. C'est volontaire — il refuse
  aussi de tourner sous un superutilisateur, parce qu'il ne prouverait rien —
  mais il faut une base neuve pour le relancer.

---

## Ce qui est réellement prouvé

Pour équilibrer, et parce que c'est vérifiable maintenant :

| Élément | Preuve |
|---|---|
| Moteur juridique déterministe | 76 tests Python, tous verts |
| Isolation multi-tenant | 51 assertions RLS sur base neuve, toutes passées |
| Abstention hors corpus | testée au `curl` et à l'écran : `fonde=false`, 0 article retenu |
| Le corpus répond quand il le peut | `التقادم`, `عدل منفذ`, `الصلح` passent le garde-fou |
| Fonctionnement sans modèle | testé avec un hébergement mort : HTTP 200, analyse complète, motif affiché |
| Analyse rendue côté serveur | présente dans le HTML, vérifiable au `curl` |
| Chaîne de trois agents | exécutée de bout en bout sur `samples/facture_ahmed.pdf` en 31 s, 0 violation d'articles |
| Corpus | 4 087 articles comptés dans l'index |

**Total annoncé : 127 vérifications automatiques** (76 pytest + 51 RLS).
Ne dites pas 136 — le compte vérifié est 127.
