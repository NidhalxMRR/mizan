#!/usr/bin/env bash
#
# Mizan — vérification d'avant-démonstration.
#
# Ce script ne DÉMARRE rien, ne MODIFIE rien, n'EFFACE rien. Il regarde l'état
# de la machine et dit, en clair, ce qui manque et quelle commande le répare.
#
# Le choix est délibéré : un script qui relance des services tout seul, trois
# minutes avant de passer devant un jury, est un script qui peut casser ce qui
# marchait encore. On diagnostique ; l'opérateur décide.
#
# Code de sortie : 0 si la démonstration est jouable (même en mode dégradé),
#                  1 si un élément indispensable manque.

set -uo pipefail

API="${MIZAN_API:-http://127.0.0.1:8820}"
WEB="${MIZAN_WEB:-http://127.0.0.1:3000}"
LLM="${MIZAN_LLM:-http://127.0.0.1:11434}"
RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

ARTICLES_ATTENDUS=4087

if [ -t 1 ]; then
  G=$'\033[32m'; R=$'\033[31m'; J=$'\033[33m'; B=$'\033[1m'; Z=$'\033[0m'
else
  G=''; R=''; J=''; B=''; Z=''
fi

bloquants=0
avertissements=0
declare -a A_FAIRE=()

ok()    { printf '  %s[ OK ]%s %s\n'    "$G" "$Z" "$1"; }
manque(){ printf '  %s[MANQUE]%s %s\n'  "$R" "$Z" "$1"; bloquants=$((bloquants+1)); }
attn()  { printf '  %s[ ATT ]%s %s\n'   "$J" "$Z" "$1"; avertissements=$((avertissements+1)); }
titre() { printf '\n%s%s%s\n' "$B" "$1" "$Z"; }
faire() { A_FAIRE+=("$1"); }

# jq n'est pas garanti sur la machine : on lit le JSON avec le Python du venv,
# qui lui est garanti puisque l'API tourne avec.
PY="$RACINE/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3 || true)"

champ() { # champ <fichier-json> <clé>
  [ -x "$PY" ] || { echo ""; return; }
  "$PY" -c "
import json,sys
try:
    d=json.load(open('$1'))
    v=d.get('$2','')
    print('' if v is None else v)
except Exception:
    print('')
" 2>/dev/null
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

printf '%s\n' "====================================================================="
printf '%s MIZAN — vérification d'\''avant-démonstration%s\n' "$B" "$Z"
printf ' %s\n' "$(date '+%A %d %B %Y — %H:%M:%S')"
printf '%s\n' "====================================================================="

# --------------------------------------------------------------------------
titre "1. L'API juridique  ($API)"
# --------------------------------------------------------------------------
if curl -sf -m 8 "$API/sante" -o "$TMP/sante.json" 2>/dev/null; then
  ok "l'API répond sur $API/sante"

  version="$(champ "$TMP/sante.json" version)"
  [ -n "$version" ] && ok "version $version — moteur $(champ "$TMP/sante.json" moteur_juridique)"

  # -- le corpus -----------------------------------------------------------
  charge="$(champ "$TMP/sante.json" index_charge)"
  nb="$(champ "$TMP/sante.json" articles_indexes)"
  if [ "$charge" = "True" ] && [ "$nb" = "$ARTICLES_ATTENDUS" ]; then
    ok "corpus chargé : $nb articles indexés (compte attendu)"
  elif [ "$charge" = "True" ]; then
    attn "corpus chargé mais $nb articles au lieu de $ARTICLES_ATTENDUS"
    faire "Le corpus ne contient pas le compte attendu. Reconstruire l'index :
      cd $RACINE && ./.venv/bin/python -m packages.legal.retrieve build
    Puis NE PAS annoncer « 4 087 articles » au jury : annoncer le chiffre affiché."
  else
    manque "index du corpus NON chargé — la recherche et l'abstention ne marcheront pas"
    faire "Reconstruire l'index du corpus :
      cd $RACINE && ./.venv/bin/python -m packages.legal.retrieve build"
  fi
else
  manque "l'API ne répond pas sur $API"
  faire "Démarrer l'API (dans un terminal à laisser ouvert) :
      cd $RACINE && ./.venv/bin/python -m uvicorn api.main:app --port 8820"
fi

# --------------------------------------------------------------------------
titre "2. Le cas de démonstration — Ahmed, menuisier à Sfax"
# --------------------------------------------------------------------------
if curl -sf -m 10 -X POST "$API/dossiers/analyser" \
     -H 'Content-Type: application/json' \
     -d '{"montant_tnd":9520.0,"date_facture":"2026-05-12","activite":"menuiserie"}' \
     -o "$TMP/ahmed.json" 2>/dev/null; then

  regime="$(champ "$TMP/ahmed.json" regime)"
  jours="$(champ "$TMP/ahmed.json" jours_restants)"
  echeance="$(champ "$TMP/ahmed.json" echeance)"
  huissier="$(champ "$TMP/ahmed.json" huissier_requis)"

  [ "$regime" = "goods_1y" ] \
    && ok "régime retenu : goods_1y (prix des marchandises livrées)" \
    || attn "régime « $regime » au lieu de goods_1y"

  [ "$huissier" = "True" ] \
    && ok "huissier requis, 5 jours francs — conforme au récit" \
    || attn "huissier_requis = $huissier (attendu : True)"

  if [ "$jours" = "241" ]; then
    ok "241 jours restants, échéance $echeance — le chiffre du scénario"
  else
    attn "le moteur annonce $jours jours, le scénario dit 241"
    faire "Le compte à rebours dépend de la date du jour. Le scénario a été écrit
    le 13/09/2026 (241 jours). ANNONCEZ « $jours jours » au jury, pas 241 —
    c'est le chiffre que l'écran affichera."
  fi
else
  manque "l'analyse du cas Ahmed a échoué — la séquence principale ne passera pas"
fi

# --------------------------------------------------------------------------
titre "3. L'abstention — le cœur de la démonstration"
# --------------------------------------------------------------------------
if curl -sf -m 10 -G "$API/corpus/rechercher" \
     --data-urlencode "q=recette de couscous au poisson" \
     -o "$TMP/abst.json" 2>/dev/null; then
  fonde="$(champ "$TMP/abst.json" fonde)"
  motif="$(champ "$TMP/abst.json" motif_abstention)"
  if [ "$fonde" = "False" ]; then
    ok "la question hors corpus déclenche bien l'abstention (« $motif »)"
  else
    manque "PAS d'abstention sur « recette de couscous » — la démo perd son argument"
    faire "Le garde-fou ne se déclenche plus. Vérifier packages/legal/gate.py :
      cd $RACINE && ./.venv/bin/python -m packages.legal.gate"
  fi
else
  manque "la recherche dans le corpus ne répond pas"
fi

# La contre-preuve : un système qui dit toujours non ne prouve rien.
if curl -sf -m 10 -G "$API/corpus/rechercher" \
     --data-urlencode "q=عدل منفذ" -o "$TMP/huis.json" 2>/dev/null; then
  [ "$(champ "$TMP/huis.json" fonde)" = "True" ] \
    && ok "contre-preuve « عدل منفذ » (huissier) : le corpus RÉPOND" \
    || attn "« عدل منفذ » s'abstient — utiliser plutôt التقادم ou الصلح comme contre-preuve"
fi

# --------------------------------------------------------------------------
titre "4. L'interface  ($WEB)"
# --------------------------------------------------------------------------
URL_DOSSIER="$WEB/dossier?montant=9520&date=2026-05-12&activite=menuiserie"
URL_CORPUS="$WEB/corpus?q=recette%20de%20couscous%20au%20poisson"

if curl -sf -m 15 "$WEB/" -o "$TMP/home.html" 2>/dev/null; then
  ok "page d'accueil servie"

  if curl -sf -m 20 "$URL_DOSSIER" -o "$TMP/dossier.html" 2>/dev/null; then
    if grep -q "241" "$TMP/dossier.html" 2>/dev/null; then
      ok "écran /dossier : les 241 jours sont dans le HTML rendu"
    else
      attn "écran /dossier servi, mais « 241 » absent du HTML (date du jour ?)"
    fi
  else
    manque "l'écran /dossier ne répond pas"
  fi

  if curl -sf -m 20 "$URL_CORPUS" -o "$TMP/corpus.html" 2>/dev/null; then
    if grep -q "ABSTENTION MOTIVÉE" "$TMP/corpus.html" 2>/dev/null; then
      ok "écran /corpus : le bloc d'abstention s'affiche réellement"
    else
      manque "écran /corpus servi SANS bloc d'abstention — vérifier l'API"
    fi
  else
    manque "l'écran /corpus ne répond pas"
  fi
else
  manque "l'interface ne répond pas sur $WEB"
  faire "Démarrer l'interface (dans un terminal à laisser ouvert) :
      cd $RACINE/web && npm run dev"
fi

# --------------------------------------------------------------------------
titre "5. Le modèle de langage  ($LLM)  — FACULTATIF"
# --------------------------------------------------------------------------
dispo="$(champ "$TMP/sante.json" modele_disponible)"
motif_m="$(champ "$TMP/sante.json" motif_modele)"

if [ "$dispo" = "True" ]; then
  ok "modèle joignable — motif : $motif_m"
  if curl -sf -m 10 "$LLM/api/tags" -o "$TMP/tags.json" 2>/dev/null; then
    ok "le tunnel vers le GPU répond sur $LLM"
  fi
  printf '     %s→ le bouton « Demander la reformulation » est utilisable (~7 s mesuré).%s\n' "$J" "$Z"
else
  attn "modèle INDISPONIBLE — motif : ${motif_m:-inconnu}"
  faire "Le modèle local ne répond pas. Rétablir le tunnel SSH vers le GPU, ou
    JOUER EN MODE DÉGRADÉ — c'est prévu et c'est testé : l'API renvoie 200 avec
    l'analyse juridique complète et affiche le motif exact de la panne.
    Voir « Plan de repli » dans docs/demo/scenario.md. NE PAS cliquer sur
    « Demander la reformulation » sans avoir lu ce passage."
fi

# --------------------------------------------------------------------------
titre "6. Les replis hors ligne"
# --------------------------------------------------------------------------
for d in architecture parcours-pme cycle-dossier; do
  f="$RACINE/docs/diagrams/$d.html"
  [ -f "$f" ] \
    && ok "diagramme $d.html présent (s'ouvre sans serveur)" \
    || attn "diagramme $d.html absent"
done
[ -f "$RACINE/samples/facture_ahmed.pdf" ] \
  && ok "facture de démonstration présente (samples/facture_ahmed.pdf)" \
  || attn "samples/facture_ahmed.pdf absent"

# --------------------------------------------------------------------------
printf '\n%s\n' "====================================================================="
if [ "$bloquants" -gt 0 ]; then
  printf '%s NON PRÊT — %d élément(s) indispensable(s) manquant(s)%s\n' "$R" "$bloquants" "$Z"
elif [ "$dispo" != "True" ]; then
  printf '%s PRÊT (mode dégradé) — le modèle manque, le droit est intact%s\n' "$J" "$Z"
else
  printf '%s PRÊT — tout répond%s\n' "$G" "$Z"
fi
[ "$avertissements" -gt 0 ] && printf ' %d avertissement(s).\n' "$avertissements"
printf '%s\n' "====================================================================="

if [ ${#A_FAIRE[@]} -gt 0 ]; then
  printf '\n%sÀ FAIRE%s\n' "$B" "$Z"
  i=1
  for t in "${A_FAIRE[@]}"; do
    printf '\n %d. %s\n' "$i" "$t"
    i=$((i+1))
  done
fi

printf '\n%sLES TROIS ONGLETS À OUVRIR, DANS CET ORDRE%s\n' "$B" "$Z"
printf '  1. %s/\n' "$WEB"
printf '  2. %s\n' "$URL_DOSSIER"
printf '  3. %s\n' "$URL_CORPUS"
printf '\n  Scénario complet : docs/demo/scenario.md\n'
printf '  Questions du jury : docs/demo/questions-jury.md\n'
printf '  Limites à annoncer: docs/demo/limites-connues.md\n\n'

[ "$bloquants" -gt 0 ] && exit 1
exit 0
