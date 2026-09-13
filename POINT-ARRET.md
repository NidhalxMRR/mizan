# Point d'arrêt du code — 13/09/2026, 01h45

Repris après les diagrammes. Rien de ce qui suit n'est perdu.

## Ce qui est écrit et vérifié

### `~/mizan/web/` — Next.js 16.3.5
- Projet créé (TypeScript, Tailwind 4, App Router, pas de src/)
- `npm install` terminé
- **`app/globals.css` écrit** : identité Pharmalink complète
  (`--teal` #2f8d82, `--gold` #c28c3a, `--navy` #203c48, clair + sombre)
  + trois ajouts propres à Mizan :
  - `.legal-ar` — RTL isolé dans une page LTR (`unicode-bidi: isolate`)
  - `.citation` — filet teal, traitement visuel distinct d'un paragraphe ordinaire
  - `.provenance-{verified,declared,abstain}` — les trois états de provenance
- ⚠️ Next.js 16 a des ruptures d'API : lire `node_modules/next/dist/docs/`
  avant d'écrire des routes (déjà vérifié : v16.3.5, même version que Pharmalink)

### `~/mizan/packages/models/client.py` — client LLM
- **Testé contre le vrai Modal de Zied**, HTTP 200 confirmé
- `ClientLLM` : une interface, deux hébergements (Modal ↔ RTX 4050)
- Retire `<think>…</think>` (Qwen3 émet son raisonnement ; il contient
  les hésitations qu'on ne doit jamais afficher)
- `ModeleIndisponible` distincte d'une erreur de traitement : l'app reste
  utilisable sans modèle, le moteur juridique étant déterministe
- **Bug en cours, non résolu** : `disponible()` renvoyait faux alors que
  `httpx.get` sur la même URL avec les mêmes en-têtes renvoie 200.
  Le `except Exception: return False` masque la cause — instrumenter
  avant de corriger. C'est le prochain geste côté code.

### `~/mizan/.venv`
- httpx installé

## Mesuré, à ne pas re-mesurer

| Fait | Valeur |
|---|---|
| Modal de Zied | `https://ziedbouzekri06--llm-qwen-serve.modal.run/v1` |
| Modèle | Qwen3-8B via vLLM, `max_model_len` 24000, id `qwen` |
| Latence | 7,3 s / 150 tokens, conteneur chaud |
| Endpoint | **public, sans authentification** — à signaler |
| Embeddings | **BAAI/bge-m3** (MIT, 37,7 M dl, arabe natif, 8192 tokens) |
| Écarté | Solon = français uniquement (Zied avait raison) |

## Corrections du brief à intégrer au code

1. **La mise en demeure revient** — brief §4 l'exige littéralement.
   On **génère** le projet d'acte ; la signification reste au عدل منفذ
   (CPC art. 5 et 60). Générer ≠ signifier.
2. **Le tableau greffier revient** — brief §4 nomme le *Commercial Court
   Clerk* en premier. C'était l'exécution qui pêchait, pas l'acteur.
   Donne accès au Prix d'Adoption Institutionnelle.
3. **Slide « The Agency Benefit »** — 45 s obligatoires, chiffrées.

## Prochains gestes, dans l'ordre

1. Finir les diagrammes (architecture bloquée sur `pos` explicite :
   `row`/`col` exige `layout.mode: grid`, sinon coordonnées libres)
2. Reprendre le bug `disponible()` avec instrumentation
3. Coquille Next.js : barre latérale + routes des piliers
4. FastAPI : reprendre le moteur de `~/h4j` (il marche, 94 tests verts)

## Contrainte horaire

Timer jusqu'à **13h00**. Point d'étape à **9h30**.
