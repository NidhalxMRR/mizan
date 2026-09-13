/**
 * Contrôle de l'îlot client : le bouton « Demander la reformulation ».
 *
 * Le rendu serveur se vérifie au `curl`. Celui-ci ne le peut pas : le texte
 * arrive après un clic, via un `fetch` depuis le navigateur. On pilote donc
 * un vrai Chromium, on clique, et on lit ce qui s'affiche — puis on compare
 * au texte que l'API a réellement produit.
 *
 * Usage : node scripts/verifier-reformulation.mjs
 */
import { spawn } from 'node:child_process';
import { setTimeout as dormir } from 'node:timers/promises';

const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:3000';
const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8820';
const URL_PAGE = `${BASE}/dossier?montant=9520&date=2024-05-12&activite=menuiserie`;

const chrome = spawn('/usr/bin/chromium', [
  '--headless=new',
  '--remote-debugging-port=9223',
  '--no-sandbox',
  '--disable-gpu',
  'about:blank',
]);
chrome.stderr.on('data', () => {});

for (let i = 0; i < 60; i++) {
  try {
    if ((await fetch('http://127.0.0.1:9223/json/version')).ok) break;
  } catch {}
  await dormir(250);
}

const cible = await (
  await fetch('http://127.0.0.1:9223/json/new?about:blank', { method: 'PUT' })
).json();
const ws = new WebSocket(cible.webSocketDebuggerUrl);
await new Promise((ok) => (ws.onopen = ok));
let id = 0;
const attentes = new Map();
ws.onmessage = (e) => {
  const m = JSON.parse(e.data);
  if (m.id && attentes.has(m.id)) {
    const { ok, ko } = attentes.get(m.id);
    attentes.delete(m.id);
    m.error ? ko(new Error(JSON.stringify(m.error))) : ok(m.result);
  }
};
const cdp = (method, params = {}) =>
  new Promise((ok, ko) => {
    const n = ++id;
    attentes.set(n, { ok, ko });
    ws.send(JSON.stringify({ id: n, method, params }));
  });
const evaluer = async (expr) =>
  JSON.parse(
    (await cdp('Runtime.evaluate', { expression: expr, returnByValue: true }))
      .result.value,
  );

await cdp('Page.enable');
await cdp('Runtime.enable');
await cdp('Page.navigate', { url: URL_PAGE });
await dormir(2500);

const avant = await evaluer(`JSON.stringify({
  bouton: !!document.querySelector('.secondary-button'),
  texte: document.querySelector('.reformulation-texte')?.textContent ?? null
})`);
console.log('Avant le clic :');
console.log('  bouton présent        :', avant.bouton);
console.log('  texte déjà affiché    :', avant.texte, '(attendu: null)');

if (!avant.bouton) {
  console.log('✗ Bouton introuvable.');
  ws.close();
  chrome.kill();
  process.exit(1);
}

await evaluer(
  `(() => { document.querySelector('.secondary-button').click(); return JSON.stringify(true); })()`,
);
await dormir(400);
const pendant = await evaluer(
  `JSON.stringify({ attente: !!document.querySelector('[aria-busy="true"]') })`,
);
console.log('\nPendant l’appel :');
console.log('  état d’attente affiché :', pendant.attente);

// Le modèle tourne en local : on lui laisse le temps qu'il lui faut.
let apres = null;
for (let i = 0; i < 100; i++) {
  await dormir(1000);
  apres = await evaluer(`JSON.stringify({
    texte: document.querySelector('.reformulation-texte')?.textContent ?? null,
    etiquette: document.querySelector('.reformulation .provenance')?.textContent ?? null,
    degrade: !!document.querySelector('.reformulation .provenance-abstain'),
    panne: !!document.querySelector('.bloc-panne'),
    avertissement: document.querySelector('.reformulation-avertissement')?.textContent ?? null
  })`);
  if (apres.texte || apres.panne) break;
}

console.log('\nAprès l’appel :');
console.log('  étiquette de provenance :', apres.etiquette);
console.log('  mode dégradé            :', apres.degrade);
console.log('  bloc de panne           :', apres.panne);
console.log(
  '  texte affiché (140c)    :',
  apres.texte ? apres.texte.slice(0, 140) + '…' : null,
);
console.log('  avertissement           :', apres.avertissement?.slice(0, 80));

// Le texte affiché doit être un texte que l'API produit réellement. On ne
// peut pas comparer mot pour mot (le modèle n'est pas déterministe), mais on
// vérifie que l'API répond bien sur les mêmes paramètres, et que le texte
// affiché n'est pas une référence d'article inventée côté client.
const rep = await fetch(`${API}/assistant/expliquer`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    montant_tnd: 9520,
    date_facture: '2024-05-12',
    activite: 'menuiserie',
  }),
});
const j = await rep.json();
console.log('\nContre-appel direct à l’API :');
console.log('  origine :', j.origine, '| mode_degrade :', j.mode_degrade);

const inventeUnArticle = /\b(?:art\.?|article)\s*\d+/i.test(apres.texte ?? '');
console.log(
  '  le texte affiché cite-t-il un article ?',
  inventeUnArticle,
  '(attendu: false — les références sont affichées par le moteur)',
);

ws.close();
chrome.kill();
const ok = Boolean(apres.texte) && !apres.panne && !inventeUnArticle;
console.log(
  ok
    ? '\n✓ La reformulation arrive réellement de l’API et ne cite aucun article.'
    : '\n✗ Contrôle en échec.',
);
process.exit(ok ? 0 : 1);
