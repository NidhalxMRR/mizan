# API Mizan

API HTTP qui expose le moteur juridique déterministe de `packages/legal/`.

## Lancer

```bash
cd ~/mizan
./.venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 8820
```

Documentation interactive : http://127.0.0.1:8820/docs

## Tester

```bash
cd ~/mizan
./.venv/bin/python -m pytest api/ -q
```

## Endpoints

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET`  | `/sante` | Modèle disponible (avec le **motif** en clair), articles indexés, version |
| `POST` | `/dossiers/analyser` | Évaluation complète : régime, échéance, jours restants, urgence, étapes, sources |
| `POST` | `/dossiers/deposer-piece` | Upload PDF → SHA-256, contrôle `doc_gate`, extraction montant et date |
| `GET`  | `/corpus/rechercher?q=…` | BM25 arabe + garde-fou d'abstention (`fonde`) |
| `POST` | `/assistant/expliquer` | Reformulation du calcul en français simple |

## Ce que l'API garantit

**Aucun article de loi ne sort d'un modèle de langage.** Les citations
proviennent du moteur (`legal_engine.SOURCES`) ou du corpus indexé. Le modèle
reçoit les références en contexte avec consigne de ne pas les répéter ; par
sécurité, `_purger_articles` relit sa sortie et retire toute référence qu'il
aurait quand même produite. Les vraies citations arrivent séparément, dans le
champ `sources`.

**Une entrée juridiquement impossible est refusée, pas arrondie.** Une facture
datée de demain donne un `400` avec le motif rédigé par le moteur, jamais un
`500` ni une échéance calculée sur un fait qui n'a pas eu lieu.

**Le client n'est pas cru sur parole.** `/assistant/expliquer` recalcule
toujours l'analyse côté moteur, même si une analyse complète lui est envoyée.

**Le modèle est optionnel.** S'il ne répond pas, `/assistant/expliquer`
retourne `200` avec `mode_degrade: true` et une explication rédigée à partir
des seules valeurs du moteur. Le droit ne dépend pas d'un GPU.

## Configuration

Aucun secret dans le code. Les variables lues par `packages/models/client.py` :

| Variable | Défaut |
|---|---|
| `MIZAN_LLM_LOCAL` | `http://127.0.0.1:11434/v1` |
| `MIZAN_LLM_LOCAL_MODELE` | `qwen2.5:7b-instruct-q4_K_M` |
| `MIZAN_LLM_MODAL` | *(vide — Modal désactivé)* |

CORS ouvert pour `http://localhost:3000` (frontend Next.js).
