// Golden-path click-through: the exact 3 minutes the jury will see.
// Fails loudly if any step does not land, so the dry-run catches it, not the jury.
const { chromium } = require('playwright');

const BASE = process.env.BASE || 'http://127.0.0.1:8811';
const INVOICE = process.env.INVOICE || '/home/nidhal/h4j/samples/facture_ahmed.pdf';
const SHOTS = '/tmp/shots';

(async () => {
  const fs = require('fs');
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch({ args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1280, height: 1400 } });
  const errors = [];
  page.on('pageerror', e => errors.push('JS: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });

  const step = async (n, label, fn) => {
    process.stdout.write(`\n[${n}] ${label}\n`);
    await fn();
    await page.screenshot({ path: `${SHOTS}/${n}.png`, fullPage: true });
  };

  await step('01', 'Accueil', async () => {
    await page.goto(BASE, { waitUntil: 'networkidle' });
    const doors = await page.locator('.door').count();
    if (doors !== 3) throw new Error(`attendu 3 portes, trouve ${doors}`);
    const foot = await page.locator('#foot').textContent();
    if (!/\d/.test(foot)) throw new Error('footer sans compteur corpus');
    console.log('    3 portes OK |', foot.trim());
  });

  await step('02', 'Ouvrir "Recuperer un impaye"', async () => {
    await page.locator('.door[data-door="c"]').click();
    await page.waitForSelector('#p-c.on', { timeout: 5000 });
    console.log('    panneau C ouvert');
  });

  await step('03', 'Upload de la facture', async () => {
    await page.setInputFiles('#file', INVOICE);
    await page.waitForFunction(
      () => document.querySelector('#amount').value !== '', { timeout: 30000 });
    const amount = await page.inputValue('#amount');
    const dt = await page.inputValue('#idate');
    const no = await page.inputValue('#ino');
    if (!amount || !dt) throw new Error('extraction incomplete');
    console.log(`    extrait: ${amount} DT | ${dt} | facture ${no}`);
  });

  await step('04', 'Verifier mes droits', async () => {
    await page.locator('#btn-assess').click();
    await page.waitForSelector('.verdict', { timeout: 20000 });
    const days = (await page.locator('.days').textContent()).trim();
    const steps = await page.locator('.steps li').count();
    const cites = await page.locator('.cite').count();
    if (steps < 3) throw new Error(`attendu >=3 etapes, trouve ${steps}`);
    if (cites < 5) throw new Error(`attendu >=5 citations, trouve ${cites}`);
    console.log(`    verdict: ${days.replace(/\s+/g, ' ')}`);
    console.log(`    ${steps} etapes | ${cites} citations cliquables`);
  });

  await step('05', 'Deplier une citation (article reel)', async () => {
    await page.locator('.cite').first().click();
    await page.waitForSelector('.art.on', { timeout: 5000 });
    const txt = (await page.locator('.art.on').first().textContent()).trim();
    if (txt.length < 60) throw new Error('article vide: ' + txt);
    if (!/[\u0600-\u06FF]/.test(txt)) throw new Error('pas de texte arabe');
    console.log('    article affiche:', txt.slice(0, 90).replace(/\s+/g, ' '), '...');
  });

  await step('06', 'Generer la mise en demeure', async () => {
    await page.locator('#btn-pdf').click();
    await page.waitForSelector('#pdfout a', { timeout: 30000 });
    const href = await page.locator('#pdfout a').getAttribute('href');
    const res = await page.request.get(BASE + href);
    if (res.status() !== 200) throw new Error('PDF HTTP ' + res.status());
    const buf = await res.body();
    if (buf.length < 10000) throw new Error('PDF trop petit: ' + buf.length);
    if (buf.slice(0, 4).toString() !== '%PDF') throw new Error('pas un PDF');
    fs.writeFileSync('/tmp/shots/mise_en_demeure.pdf', buf);
    console.log(`    PDF ${href} — ${buf.length} octets, signature %PDF OK`);
  });

  await step('07', 'Porte B: recherche dans la loi', async () => {
    await page.locator('.door[data-door="b"]').click();
    await page.waitForSelector('#p-b.on');
    await page.fill('#q-b', 'الأمر بالدفع');
    await page.locator('[data-search="b"]').click();
    await page.waitForSelector('#out-b .hit', { timeout: 20000 });
    const hits = await page.locator('#out-b .hit').count();
    if (hits === 0) throw new Error('aucun resultat');
    console.log(`    ${hits} articles trouves`);
  });

  if (errors.length) {
    console.log('\nERREURS JS DETECTEES:');
    errors.forEach(e => console.log('  -', e));
  } else {
    console.log('\nAucune erreur JS.');
  }
  console.log('\nCHEMIN DORE: OK — captures dans ' + SHOTS);
  await browser.close();
  process.exit(errors.length ? 1 : 0);
})().catch(e => { console.error('\nECHEC:', e.message); process.exit(1); });
