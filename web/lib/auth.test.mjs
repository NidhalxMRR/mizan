/**
 * Vérifie que la matrice de permissions dit bien ce que dit le droit.
 *
 * Ce ne sont pas des tests de confort : chacun correspond à une règle écrite
 * (CPC art. 5 et 60, brief Challenge B §4). Une régression ici, c'est une
 * plateforme qui usurpe un acte réservé.
 *
 *     node --test web/lib/auth.test.mjs
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';

// Le module est en TypeScript mais ne contient aucune annotation à
// l'exécution : on relit la matrice depuis la source pour ne pas dépendre
// d'une étape de compilation dans un test.
import { readFileSync } from 'node:fs';
const src = readFileSync(new URL('./auth.ts', import.meta.url), 'utf8');

function permsOf(role) {
  const m = src.match(new RegExp(`${role}:\\s*\\[([^\\]]*)\\]`, 's'));
  if (!m) throw new Error(`rôle introuvable : ${role}`);
  // Les commentaires français contiennent des apostrophes (« le projet d'acte »)
  // qu'une extraction naïve prend pour des délimiteurs de chaîne. On les retire
  // avant de lire la liste — sinon le test échoue sur son propre analyseur,
  // pas sur la matrice.
  const sansCommentaires = m[1].replace(/\/\/[^\n]*/g, '');
  return [...sansCommentaires.matchAll(/'([^']+)'/g)].map((x) => x[1]);
}
const can = (role, perm) => permsOf(role).includes(perm);

test('seul l’huissier peut signifier une mise en demeure (CPC art. 5 et 60)', () => {
  assert.ok(can('huissier', 'issue_formal_notice'));

  for (const role of ['platform_admin', 'msme', 'accredited_pro', 'court_clerk']) {
    assert.equal(
      can(role, 'issue_formal_notice'),
      false,
      `${role} ne doit pas pouvoir signifier : c’est un monopole légal`,
    );
  }
});

test('la PME demande le projet d’acte, elle ne le signifie pas', () => {
  assert.ok(can('msme', 'request_notice'));
  assert.equal(can('msme', 'issue_formal_notice'), false);
});

test('la PME dépose ses pièces (brief §4.1)', () => {
  assert.ok(can('msme', 'upload_evidence'));
});

test('le greffier dispose du module institutionnel (brief §4)', () => {
  for (const p of ['view_queue', 'review_evidence', 'approve_dossier', 'schedule_mediation']) {
    assert.ok(can('court_clerk', p), `le greffier doit pouvoir ${p}`);
  }
});

test('le greffier ne conduit pas la médiation : il la programme', () => {
  assert.ok(can('court_clerk', 'schedule_mediation'));
  assert.equal(can('court_clerk', 'conduct_ecma'), false);
  assert.equal(can('court_clerk', 'sign_settlement'), false);
});

test('seul le professionnel accrédité signe un PV de conciliation (brief §6)', () => {
  assert.ok(can('accredited_pro', 'sign_settlement'));
  for (const role of ['msme', 'court_clerk', 'huissier', 'platform_admin']) {
    assert.equal(can(role, 'sign_settlement'), false, `${role} ne signe pas un PV`);
  }
});

test('la PME accepte un accord mais ne le rédige pas', () => {
  assert.ok(can('msme', 'accept_settlement'));
  assert.equal(can('msme', 'draft_settlement'), false);
});

test('l’administrateur n’hérite d’aucun pouvoir juridique', () => {
  for (const p of ['issue_formal_notice', 'sign_settlement', 'conduct_ecma', 'approve_dossier']) {
    assert.equal(
      can('platform_admin', p),
      false,
      `exploiter la plateforme ne confère pas ${p}`,
    );
  }
});

test('aucun rôle ne cumule signification et signature d’accord', () => {
  for (const role of ['platform_admin', 'msme', 'accredited_pro', 'court_clerk', 'huissier']) {
    const cumul = can(role, 'issue_formal_notice') && can(role, 'sign_settlement');
    assert.equal(cumul, false, `${role} cumule deux monopoles distincts`);
  }
});
