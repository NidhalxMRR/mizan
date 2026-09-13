/**
 * Contrôle de mise en page réel, pas déclaratif.
 *
 * Ouvre chaque page dans Chromium à 479 px puis à 1280 px et mesure la boîte
 * de CHAQUE élément. On cherche deux défauts qui ne se voient pas en lisant
 * du CSS : un débordement horizontal, et un texte arabe dont la direction
 * n'aurait pas été appliquée par le navigateur.
 *
 * Usage : node scripts/verifier-mise-en-page.mjs
 */
import { spawn } from 'node:child_process';
import { setTimeout as dormir } from 'node:timers/promises';

const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:3000';
const PAGES = [
  ['/', 'accueil'],
  ['/dossier?montant=9520&date=2024-05-12&activite=menuiserie', 'dossier'],
  // Les deux écrans d'interruption : celui qui gagne du temps, et le piège.
  // Le second est le plus exposé au débordement — motif long, pastille
  // « n'a rien interrompu », citation arabe — donc le plus utile à mesurer.
  [
    '/dossier?montant=9520&date=2026-05-12&activite=menuiserie' +
      '&acte=sommation_huissier%3A2026-07-01%3ASommation%20de%20payer%20signifi%C3%A9e%20%C3%A0%20la%20soci%C3%A9t%C3%A9%20d%C3%A9bitrice',
    'dossier (interruption retenue)',
  ],
  [
    '/dossier?montant=9520&date=2020-01-15&activite=menuiserie' +
      '&acte=sommation_huissier%3A2026-01-01%3ASommation%20signifi%C3%A9e%20apr%C3%A8s%20l%27expiration%20du%20d%C3%A9lai',
    'dossier (acte sans effet)',
  ],
  ['/corpus?q=%D8%A7%D9%84%D8%AA%D9%82%D8%A7%D8%AF%D9%85', 'corpus (fondé)'],
  ['/corpus?q=recette+de+couscous+au+poisson', 'corpus (abstention)'],
];
const LARGEURS = [479, 1280];

const chrome = spawn('/usr/bin/chromium', [
  '--headless=new',
  '--remote-debugging-port=9222',
  '--no-sandbox',
  '--disable-gpu',
  '--hide-scrollbars',
  'about:blank',
]);
chrome.stderr.on('data', () => {});

async function attendreChrome() {
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch('http://127.0.0.1:9222/json/version');
      if (r.ok) return;
    } catch {}
    await dormir(250);
  }
  throw new Error("Chromium n'a pas ouvert son port de débogage.");
}

// --- Client CDP minimal : pas de dépendance à installer ---------------------
async function ouvrirSession() {
  const cible = await (await fetch('http://127.0.0.1:9222/json/new?about:blank', {
    method: 'PUT',
  })).json();
  const ws = new WebSocket(cible.webSocketDebuggerUrl);
  await new Promise((ok, ko) => {
    ws.onopen = ok;
    ws.onerror = () => ko(new Error('WebSocket CDP refusée'));
  });
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
  const envoyer = (method, params = {}) =>
    new Promise((ok, ko) => {
      const n = ++id;
      attentes.set(n, { ok, ko });
      ws.send(JSON.stringify({ id: n, method, params }));
    });
  return { envoyer, fermer: () => ws.close(), cibleId: cible.id };
}

const SONDE = `(() => {
  const de = document.documentElement;
  const large = de.clientWidth;
  const deborde = [];
  document.querySelectorAll('body *').forEach((el) => {
    const b = el.getBoundingClientRect();
    if (b.width > 0 && b.height > 0 && (b.right > large + 1 || b.left < -1)) {
      deborde.push(el.tagName + '.' + String(el.className || '').split(' ')[0] +
        ' [' + Math.round(b.left) + '→' + Math.round(b.right) + ']');
    }
  });
  // Direction RÉSOLUE par le navigateur, pas l'attribut écrit dans le HTML.
  const ar = [...document.querySelectorAll('[lang="ar"]')].map((el) => ({
    dir: getComputedStyle(el).direction,
    bidi: getComputedStyle(el).unicodeBidi,
  }));
  const fr = getComputedStyle(document.body).direction;
  return JSON.stringify({
    large,
    scroll: de.scrollWidth,
    defilementH: de.scrollWidth > large + 1,
    deborde: deborde.slice(0, 10),
    nbDeborde: deborde.length,
    nbArabe: ar.length,
    arabeNonRtl: ar.filter((a) => a.dir !== 'rtl').length,
    arabeNonIsole: ar.filter((a) => !a.bidi.includes('isolate')).length,
    corpsDir: fr,
  });
})()`;

await attendreChrome();
const { envoyer, fermer } = await ouvrirSession();
await envoyer('Page.enable');
await envoyer('Runtime.enable');

let echecs = 0;
for (const largeur of LARGEURS) {
  console.log(`\n╔══ LARGEUR ${largeur} px ${'═'.repeat(46 - String(largeur).length)}`);
  await envoyer('Emulation.setDeviceMetricsOverride', {
    width: largeur,
    height: 900,
    deviceScaleFactor: 1,
    mobile: largeur < 700,
  });
  for (const [chemin, nom] of PAGES) {
    await envoyer('Page.navigate', { url: BASE + chemin });
    await dormir(1400);
    const r = await envoyer('Runtime.evaluate', {
      expression: SONDE,
      returnByValue: true,
    });
    const d = JSON.parse(r.result.value);
    const okLargeur = !d.defilementH && d.nbDeborde === 0;
    const okArabe = d.nbArabe > 0 && d.arabeNonRtl === 0 && d.arabeNonIsole === 0;
    const okFr = d.corpsDir === 'ltr';
    if (!(okLargeur && okArabe && okFr)) echecs++;
    console.log(`║ ${nom}`);
    console.log(
      `║   largeur   ${okLargeur ? 'OK' : 'ÉCHEC'} — contenu ${d.scroll}px dans ${d.large}px` +
        (d.nbDeborde ? `, ${d.nbDeborde} débordement(s)` : ', aucun débordement'),
    );
    if (d.nbDeborde) d.deborde.forEach((e) => console.log(`║       ↳ ${e}`));
    console.log(
      `║   arabe     ${okArabe ? 'OK' : 'ÉCHEC'} — ${d.nbArabe} bloc(s) lang="ar", ` +
        `${d.arabeNonRtl} non-RTL, ${d.arabeNonIsole} non isolé(s)`,
    );
    console.log(`║   français  ${okFr ? 'OK' : 'ÉCHEC'} — body direction: ${d.corpsDir}`);
  }
}

fermer();
chrome.kill();
console.log(
  echecs === 0
    ? '\n✓ Mise en page conforme à 479 px et à 1280 px, arabe en RTL isolé partout.'
    : `\n✗ ${echecs} contrôle(s) en échec.`,
);
process.exit(echecs === 0 ? 0 : 1);
