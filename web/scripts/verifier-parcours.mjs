/**
 * Contrôle du parcours interactif, dans un vrai navigateur.
 *
 * Le rendu serveur se prouve au `curl`. Ce qui suit ne le peut pas : il faut
 * cliquer. Ce script pilote Chromium et vérifie que les trois interactions de
 * la démonstration produisent bien un nouvel appel à l'API :
 *
 *   1. changer le montant recalcule le dossier (et fait disparaître l'encart
 *      huissier sous le seuil de 150 DT) ;
 *   2. la requête hors corpus fait apparaître l'abstention ;
 *   3. une requête arabe fondée affiche des articles, sans abstention.
 *
 * Il a déjà attrapé un défaut qui ne se voyait pas autrement : React n'était
 * pas hydraté en développement, faute d'`allowedDevOrigins`, et aucun bouton
 * ne répondait alors que toutes les pages rendaient un HTML correct.
 *
 * Usage : node scripts/verifier-parcours.mjs
 */
import { spawn } from 'node:child_process';
import { setTimeout as dormir } from 'node:timers/promises';

const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:3000';
const PORT_CDP = 9226;

const chrome = spawn('/usr/bin/chromium', [
  '--headless=new',
  `--remote-debugging-port=${PORT_CDP}`,
  '--no-sandbox',
  '--disable-gpu',
  'about:blank',
]);
chrome.stderr.on('data', () => {});
for (let i = 0; i < 60; i++) {
  try {
    if ((await fetch(`http://127.0.0.1:${PORT_CDP}/json/version`)).ok) break;
  } catch {}
  await dormir(250);
}

const cible = await (
  await fetch(`http://127.0.0.1:${PORT_CDP}/json/new?about:blank`, { method: 'PUT' })
).json();
const ws = new WebSocket(cible.webSocketDebuggerUrl);
await new Promise((ok) => (ws.onopen = ok));
let id = 0;
const att = new Map();
const exceptions = [];
ws.onmessage = (e) => {
  const m = JSON.parse(e.data);
  if (m.method === 'Runtime.exceptionThrown') {
    exceptions.push(
      (m.params.exceptionDetails.exception?.description ??
        m.params.exceptionDetails.text ??
        '').slice(0, 200),
    );
  }
  if (m.id && att.has(m.id)) {
    const { ok, ko } = att.get(m.id);
    att.delete(m.id);
    m.error ? ko(new Error(JSON.stringify(m.error))) : ok(m.result);
  }
};
const cdp = (method, params = {}) =>
  new Promise((ok, ko) => {
    const n = ++id;
    att.set(n, { ok, ko });
    ws.send(JSON.stringify({ id: n, method, params }));
  });
const ev = async (expr) =>
  (await cdp('Runtime.evaluate', {
    expression: expr,
    returnByValue: true,
    awaitPromise: true,
  })).result.value;

await cdp('Runtime.enable');
await cdp('Page.enable');

const resultats = [];
const verifier = (nom, obtenu, attendu) => {
  const ok = obtenu === attendu;
  resultats.push(ok);
  console.log(
    `  ${ok ? 'OK   ' : 'ÉCHEC'} | ${nom.padEnd(42)} | ${JSON.stringify(obtenu)}`,
  );
};

// --- 1. Le formulaire du dossier -------------------------------------------
console.log('\n=== Formulaire du dossier : 9520 DT → 120 DT ===');
await cdp('Page.navigate', { url: `${BASE}/dossier` });
await dormir(3000);
verifier('hydratation : bouton actif', await ev(`!document.querySelector('.formulaire button').disabled`), true);
verifier('encart huissier avant (9520 DT)', await ev(`!!document.querySelector('.encart-huissier')`), true);

// React contrôle les champs : sans le setter natif, l'état ne suit pas.
await ev(`(() => {
  const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  const m = document.getElementById('montant');
  s.call(m, '120'); m.dispatchEvent(new Event('input', { bubbles: true }));
  const d = document.getElementById('date');
  s.call(d, '2026-09-01'); d.dispatchEvent(new Event('input', { bubbles: true }));
  return 'ok';
})()`);
await dormir(300);
await ev(`document.querySelector('.formulaire button[type=submit]').click(); 'ok'`);
await dormir(4000);

verifier('URL mise à jour', await ev(`location.search`), '?montant=120&date=2026-09-01&activite=menuiserie');
verifier('montant recalculé par l’API', await ev(`[...document.querySelectorAll('.fait')].find(f => f.textContent.includes('Montant'))?.querySelector('.fait-valeur')?.textContent`), '120,000 DT');
verifier('encart huissier retiré (<150 DT)', await ev(`!!document.querySelector('.encart-huissier')`), false);

// --- 2. L'abstention --------------------------------------------------------
console.log('\n=== Corpus : requête hors corpus → abstention ===');
await cdp('Page.navigate', { url: `${BASE}/corpus` });
await dormir(3000);
verifier('aucune abstention au départ', await ev(`!!document.querySelector('.bloc-abstention')`), false);
await ev(`[...document.querySelectorAll('.exemple')].find(x => x.textContent.includes('couscous')).click(); 'ok'`);
await dormir(4000);
verifier('bloc d’abstention affiché', await ev(`!!document.querySelector('.bloc-abstention')`), true);
verifier(
  'la phrase du projet est affichée',
  await ev(`(document.querySelector('.abstention-message')?.textContent ?? '').includes("préfère se taire plutôt que d'inventer une référence")`),
  true,
);

// --- 3. Une requête fondée --------------------------------------------------
console.log('\n=== Corpus : requête arabe fondée → articles ===');
await ev(`[...document.querySelectorAll('.exemple')].find(x => x.textContent.includes('prescription')).click(); 'ok'`);
await dormir(4000);
verifier('abstention levée', await ev(`!!document.querySelector('.bloc-abstention')`), false);
verifier('5 articles affichés', await ev(`document.querySelectorAll('.article').length`), 5);
verifier(
  'citation arabe présente',
  await ev(`/^الفصل \\d+/.test(document.querySelector('.article .citation-ref')?.textContent ?? '')`),
  true,
);

console.log(`\nExceptions JavaScript : ${exceptions.length}`);
exceptions.forEach((e) => console.log('  ' + e));

ws.close();
chrome.kill();
const echecs = resultats.filter((r) => !r).length + exceptions.length;
console.log(
  echecs === 0
    ? '\n✓ Parcours interactif conforme : chaque clic déclenche un appel réel à l’API.'
    : `\n✗ ${echecs} contrôle(s) en échec.`,
);
process.exit(echecs === 0 ? 0 : 1);
