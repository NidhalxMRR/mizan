# Mizan — ميزان

Plateforme de résolution de litiges commerciaux pour les PME tunisiennes.

**Hack4Justice 2026 — AI Edition** · HiiL × ESPRIT · Challenge B, *Digital
Dispute Resolution & Pre-Litigation*.

---

## Le principe

> **L'IA propose. Le droit dispose.**

Aucun modèle de langage ne calcule un délai de prescription et n'énonce un
article de loi. Le moteur juridique est déterministe : il relit chaque article
dans le corpus avant de l'afficher, et **s'abstient** quand il ne trouve pas —
au lieu d'inventer une référence plausible.

Le modèle de langage sert à reformuler et à rédiger. Débranchez-le : la
plateforme continue de fonctionner.

## Chaque acte à son acteur

Le droit tunisien réserve certains actes à certaines personnes. La plateforme
ne les usurpe pas — elle prépare le travail de celui qui a qualité pour agir.

| Acteur | Ce que lui seul peut faire | Base |
|---|---|---|
| **عدل منفذ** (huissier) | signifier une mise en demeure | CPC art. 5 et 60 |
| **Professionnel accrédité** | signer un PV de conciliation | COC art. 1458 |
| **Greffier** | instruire et programmer une médiation | brief §4 |
| **Entreprise** | déposer ses pièces, accepter un accord | — |

Cette séparation n'est pas une convention de nommage : elle est **vérifiée par
des tests** (`web/lib/auth.test.mjs`). Aucun rôle ne peut signifier un acte à
la place de l'huissier, et personne ne cumule deux monopoles.

La plateforme **génère** un projet d'acte conforme — parties identifiées,
montant calculé, articles cités et relus. La **signification** reste à
l'huissier. Le brief §4 demande de *generate* la mise en demeure ; générer
n'est pas signifier.

## Souveraineté des données

Un dossier de litige contient des factures, des contrats, des noms de clients.
Un greffe tunisien ne peut pas envoyer cela chez un tiers étranger.

Le modèle tourne **en local** (RTX 4050, via Ollama). Un hébergement distant
existe en **secours** uniquement : si le GPU sature pendant une démonstration,
la bascule est automatique et invisible. Les deux exposent la même API
compatible OpenAI — basculer revient à changer une URL.

Retirez la variable `MIZAN_LLM_MODAL` : la plateforme fonctionne sans aucune
connexion sortante. La bascule est couverte par 9 tests
(`packages/models/test_client.py`).

## État du dépôt

| Composant | État |
|---|---|
| Rôles et permissions | **9 tests verts** |
| Client LLM local + secours | **9 tests verts** |
| Identité visuelle | tokens posés, clair et sombre |
| Diagramme d'architecture | validé 9/9, relu visuellement |
| Moteur juridique | repris de `~/h4j` — 94 tests verts |
| Schéma PostgreSQL multi-tenant | en cours |

## Corpus

4 087 articles de droit tunisien, en arabe :
COC (1 496) · Fiscal (814) · Sociétés (664) · Commerce (546) · CPC (488) ·
Arbitrage (79).

Recherche hybride : BM25 sur le chemin critique, embeddings **bge-m3** en
complément (MIT, arabe natif, contexte 8192).

## Structure

```
web/          interface Next.js 16 — App Router, RTL/LTR
  lib/auth.ts       rôles, permissions, et ce que chacun ne peut pas faire
packages/
  models/           accès au modèle : local d'abord, secours ensuite
db/           schéma PostgreSQL multi-tenant (isolation par RLS)
docs/diagrams/      architecture, parcours, cycle de vie — validés
```

## Lancer les tests

```bash
node --test web/lib/auth.test.mjs                      # séparation des rôles
./.venv/bin/python -m pytest packages/models -q        # bascule du modèle
```

## Licence

À définir avant publication.
