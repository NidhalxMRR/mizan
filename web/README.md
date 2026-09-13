# Mizan — interface web

Interface Next.js du parcours PME. Elle ne contient aucune donnée juridique :
chaque chiffre, chaque article et chaque date affichés proviennent d'un appel
à l'API FastAPI. Quand l'API ne répond pas, l'écran le dit et n'affiche rien
d'autre — il n'existe volontairement aucun jeu de données de repli.

## Démarrer

L'API doit tourner d'abord :

```bash
cd ~/mizan && .venv/bin/uvicorn api.main:app --port 8820
```

Puis l'interface :

```bash
cd ~/mizan/web
npm run dev     # http://localhost:3000
```

L'URL de l'API est configurable par `NEXT_PUBLIC_API_URL`
(défaut : `http://127.0.0.1:8820`, voir `.env.local`).

## Les trois écrans

| Route      | Ce qu'il démontre                                                                |
| ---------- | -------------------------------------------------------------------------------- |
| `/`        | Le principe, et l'état réel du service lu sur `/sante` (nombre d'articles indexés, disponibilité du modèle, hébergements sondés) |
| `/dossier` | Le parcours PME : `/dossiers/analyser` calcule le régime de prescription, le compte à rebours, les étapes et les articles. L'encart huissier n'apparaît que si `huissier_requis` est vrai. La reformulation par le modèle est un second appel, facultatif et étiqueté |
| `/corpus`  | La recherche dans le corpus, et surtout l'**abstention** : quand `fonde=false`, le message de l'API est mis en valeur avant tout résultat |

`/dossier` et `/corpus` lisent leurs paramètres dans l'URL et rendent **côté
serveur**. Conséquence utile : le résultat est dans le HTML, donc vérifiable
au `curl`, et une URL de démonstration se partage.

## Vérifier que rien n'est simulé

```bash
npm run build                             # doit passer sans erreur
node --test lib/auth.test.mjs             # 9 tests sur la matrice de rôles
node scripts/verifier-mise-en-page.mjs    # Chromium : 479 px et 1280 px, RTL
node scripts/verifier-parcours.mjs        # Chromium : chaque clic appelle l'API
node scripts/verifier-reformulation.mjs   # Chromium : le LLM répond vraiment
```

Les trois derniers pilotent un vrai navigateur. Ils ont déjà attrapé un défaut
que la lecture du code ne montrait pas : sans `allowedDevOrigins` dans
`next.config.ts`, React n'était pas hydraté en développement et aucun bouton
ne répondait, alors que toutes les pages rendaient un HTML parfaitement
correct.

La preuve la plus directe reste celle-ci :

```bash
curl -s 'http://127.0.0.1:3000/dossier?montant=9520&date=2024-05-12&activite=menuiserie' \
  | grep -o 'الفصل 403 من مجلة الالتزامات والعقود'
```

L'article sort du corpus indexé, pas du code de l'interface.

## Choix qui ne sont pas négociables

- **Aucune police distante, aucun CDN.** La salle de démonstration peut être
  sans wifi. Les familles utilisées existent déjà sur la machine.
- **Aucune donnée codée en dur.** Le compteur d'articles vient de `/sante` ;
  chercher `4087` dans `app/` ne renvoie qu'un commentaire.
- **`cache: 'no-store'` sur tous les appels.** Un chiffre juridique périmé
  affiché avec aplomb est exactement ce que ce projet refuse.
- **L'abstention est grise, pas rouge** (`--abstain`). Ne pas savoir n'est pas
  une panne, c'est une décision du système.
- **L'arabe est isolé** (`unicode-bidi: isolate`), y compris pour les incises
  au milieu d'une phrase française : sans cela, la ponctuation française part
  à l'envers.
