#!/usr/bin/env bash
# Preuve d'isolation multi-tenant, rejouable autant de fois qu'on veut.
#
# Le test SQL lui-même n'est pas idempotent : il amorce la plateforme, et
# l'amorçage refuse — à raison — d'être rejoué. Relancer le fichier sur une
# base déjà initialisée produisait donc une erreur qui ressemblait à un échec
# d'isolation alors que c'était une garde de sécurité qui faisait son travail.
#
# Ce script repart d'une base neuve à chaque exécution. C'est la seule façon
# d'obtenir un résultat qu'on puisse montrer deux fois de suite devant un jury
# sans avoir à expliquer une erreur rouge.
#
#   ./db/prouver-isolation.sh
#
set -euo pipefail

HOTE="${PGHOST:-/tmp}"
PORT="${PGPORT:-54329}"
BASE="mizan_isolation"
RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Preuve d'isolation multi-tenant — base repartie de zéro ==="
echo

psql -h "$HOTE" -p "$PORT" -d postgres -q -tAc \
  "DROP DATABASE IF EXISTS $BASE;" >/dev/null
psql -h "$HOTE" -p "$PORT" -d postgres -q -tAc \
  "CREATE DATABASE $BASE;" >/dev/null
psql -h "$HOTE" -p "$PORT" -d "$BASE" -q -v ON_ERROR_STOP=1 \
  -f "$RACINE/db/schema.sql" >/dev/null

# PGOPTIONS impose le rôle applicatif AVANT toute requête : sous un
# superutilisateur PostgreSQL contourne la RLS et le test ne prouverait rien.
# Le fichier SQL refuse d'ailleurs de s'exécuter dans ce cas — c'est voulu.
sortie="$(PGOPTIONS='-c role=mizan_app' psql -h "$HOTE" -p "$PORT" -d "$BASE" \
  -v ON_ERROR_STOP=1 -f "$RACINE/db/test_isolation.sql" 2>&1)"

echo "$sortie" | grep -E '^\-\-\-|\[OK\]|\[ÉCHEC\]|\[ECHEC\]' || true
echo

reussis="$(echo "$sortie" | grep -c '\[OK\]' || true)"
echecs="$(echo "$sortie" | grep -cE '\[ÉCHEC\]|\[ECHEC\]' || true)"
erreurs="$(echo "$sortie" | grep -c '^psql.*ERROR' || true)"

echo "====================================================================="
echo "  contrôles réussis : $reussis"
echo "  échecs            : $echecs"
echo "  erreurs SQL       : $erreurs"
echo "====================================================================="

if [ "$echecs" -ne 0 ] || [ "$erreurs" -ne 0 ]; then
  echo
  echo "ISOLATION NON PROUVÉE — sortie complète :"
  echo "$sortie"
  exit 1
fi

echo "  ISOLATION PROUVÉE sur une base neuve."
