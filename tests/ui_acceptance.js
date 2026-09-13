/*
 * Mizan — UI acceptance run.
 *
 * The lesson from Assurance bug #261: a dead backend produced a confident,
 * well-formatted refusal and the demo looked healthy while nothing worked.
 * So this file never asserts on status codes. It asserts on what a juror
 * would actually read on the screen, and it fails loudly on a console error.
 */
const { chromium } = require('playwright');

const BASE = process.env.BASE || 'http://127.0.0.1:8811';
const results = [];
let failed = 0;

function check(name, cond, detail) {
  results.push({ name, ok: !!cond, detail: detail === undefined ? '' : String(detail) });
  if (!cond) failed++;
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });

  const consoleErrors = [];
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });
  page.on('pageerror', e => consoleErrors.push('pageerror: ' + e.message));

  await page.goto(BASE, { waitUntil: 'networkidle' });

  // --- the shell actually painted, with the design system applied ---
  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  check('design.css applied (body not default white)', bg !== 'rgba(0, 0, 0, 0)' && bg !== '', bg);

  const verified = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue('--verified').trim());
  check('token --verified present', verified.length > 0, verified);

  // --- the corpus count is fetched live, not hardcoded in the markup ---
  await page.waitForFunction(() => {
    const el = document.querySelector('#corpusN');
    return el && el.textContent.trim() !== '—' && el.textContent.trim() !== '';
  }, { timeout: 10000 }).catch(() => {});
  const corpus = (await page.textContent('#corpusN')).trim();
  check('corpus count rendered from /health', /\d/.test(corpus) && corpus !== '0', corpus);

  // --- upload prefills BOTH amount and date (the bug Nidhal reported) ---
  await page.setInputFiles('#file', 'samples/facture_ahmed.pdf');
  await page.waitForFunction(() => document.querySelector('#amount').value !== '', { timeout: 15000 });
  const amount = await page.inputValue('#amount');
  const idate = await page.inputValue('#idate');
  const ino = await page.inputValue('#ino');
  check('amount prefilled', amount === '9520', amount);
  check('DATE prefilled (regression: was empty)', idate === '2026-05-12', idate);
  check('invoice number prefilled', ino === '2026-041', ino);

  // --- the verdict renders the real number, in French ---
  await page.click('#go');
  await page.waitForSelector('.clock', { timeout: 15000 });
  const clockNum = (await page.textContent('.dial .num b')).trim();
  check('clock shows 242 days', clockNum === '242', clockNum);

  const head = (await page.textContent('.clock-body h3')).trim();
  // Le titre ne répète plus le chiffre : l'anneau porte "242", le titre porte
  // le VERDICT en langue humaine, la puce mono porte la preuve. Trois rôles,
  // pas trois fois la même donnée.
  check('verdict headline is human French', /encore dans le délai/.test(head) && !/242/.test(head), head);

  const reason = (await page.textContent('.clock-body p:not(.deriv)')).trim();
  check('regime reason shown (not just a code)', reason.length > 40 && !/goods_1y/.test(reason), reason.slice(0, 70));

  // --- the arc actually animated (signature element is alive) ---
  await page.waitForTimeout(1200);
  const off = await page.evaluate(() => {
    const r = document.querySelector('.dial .run');
    return r ? parseFloat(getComputedStyle(r).strokeDashoffset) : -1;
  });
  const circ = 2 * Math.PI * 58;
  check('prescription arc animated away from empty', off > 1 && off < circ - 1, off.toFixed(1) + ' / ' + circ.toFixed(1));

  // --- provenance is visible, and it is the corpus talking ---
  const badges = await page.$$eval('#cites .badge', els => els.map(e => e.textContent.trim()));
  check('every citation carries a provenance badge', badges.length >= 5, badges.join(','));
  check('citations are verified', badges.filter(b => /vérifié/.test(b)).length >= 5, badges.length);

  // --- the Arabic text of the decisive article is on screen ---
  await page.click('#cites details:first-child summary');
  await page.waitForTimeout(300);
  const ar = (await page.textContent('#cites details:first-child .ar')).trim();
  check('Arabic article text rendered', /الفصل 403/.test(ar), ar.slice(0, 40));
  const dir = await page.evaluate(() =>
    getComputedStyle(document.querySelector('#cites .ar')).direction);
  check('Arabic renders right-to-left', dir === 'rtl', dir);

  // --- the steps, with their own citations ---
  const steps = await page.$$eval('ol.steps li h4', e => e.map(x => x.textContent.trim()));
  check('3 procedural steps', steps.length === 3, steps.join(' | '));

  // --- ABSTENTION: the thing that separates Mizan from a chatbot ---
  await page.fill('#q', 'ما هو لون السماء');
  await page.click('#qgo');
  await page.waitForSelector('.abstain', { timeout: 15000 });
  const abstainTitle = (await page.textContent('.abstain b')).trim();
  check('refusal is stated plainly', /ne trouve pas de texte de loi/.test(abstainTitle), abstainTitle);
  const why = (await page.textContent('.abstain .why')).trim();
  check('refusal shows its measured reason (not empty)', /meilleur score 8\.75/.test(why) && why.length > 40, why.slice(0, 90));

  // --- and it still answers a real legal question ---
  await page.fill('#q', 'الأمر بالدفع');
  await page.click('#qgo');
  await page.waitForSelector('#qout details', { timeout: 15000 });
  const nres = await page.$$eval('#qout details', e => e.length);
  check('real legal question returns articles', nres >= 3, nres);

  // --- the OCR caveat is a state a juror can actually SEE, not just footer prose ---
  await page.fill('#q', 'الكمبيالة');
  await page.click('#qgo');
  await page.waitForSelector('#qout details', { timeout: 15000 });
  const ocrBadges = await page.$$eval('#qout .badge.ocr', e => e.map(x => x.textContent.trim()));
  check('OCR provenance is reachable in the demo', ocrBadges.length >= 1, ocrBadges.join(','));

  // --- the trust strip is above the fold, not 12px grey at the bottom ---
  const trustTop = await page.evaluate(() => {
    const t = document.querySelector('.trust');
    return t ? t.getBoundingClientRect().top : 99999;
  });
  check('trust argument sits above the fold', trustTop < 900, trustTop);

  // --- the derivation is printed, so nobody has to trust the arc ---
  const deriv = (await page.textContent('.clock-body .deriv')).trim();
  check('prescription derivation shown', /12\/05\/2026 \+ 1 an/.test(deriv) && /= 242 jours/.test(deriv), deriv);

  // <input type=date> s'affiche selon la locale du navigateur : en anglais US
  // le 12 mai devient "05/12/2026". La date pivot ne doit pas pouvoir se lire
  // à l'envers devant un jury tunisien.
  const echo = (await page.textContent('#dateEcho')).trim();
  check('invoice date spelled out, locale-proof', /^12 mai 2026$/.test(echo), echo);

  // --- THE BUG NIDHAL FOUND: a non-invoice must never become a claim ---
  // He dropped the hackathon's own joining instructions and Mizan produced an
  // enforceable mise en demeure for 2 083,000 DT against invoice n° 34848.
  // None of it existed. This asserts the door now refuses.
  await page.setInputFiles('#file', 'samples/not_an_invoice_joining_instructions.pdf');
  await page.waitForSelector('.reject', { timeout: 30000 });
  const rejTitle = (await page.textContent('.reject b')).trim();
  check('non-invoice is refused at the door', /n'est pas une facture/.test(rejTitle), rejTitle);
  const rejWhy = (await page.textContent('.reject p')).trim();
  check('refusal states why', rejWhy.length > 15, rejWhy.slice(0, 70));
  const aVal = await page.inputValue('#amount');
  const dVal = await page.inputValue('#idate');
  check('NO amount invented from a non-invoice', aVal === '', JSON.stringify(aVal));
  check('NO date invented from a non-invoice', dVal === '', JSON.stringify(dVal));
  const goOff = await page.evaluate(() => document.querySelector('#go').disabled);
  check('cannot generate a claim from it', goOff === true, goOff);

  // --- and a real invoice still passes, right after ---
  await page.setInputFiles('#file', 'samples/facture_ahmed.pdf');
  await page.waitForFunction(() => document.querySelector('#amount').value !== '', { timeout: 20000 });
  const backAmount = await page.inputValue('#amount');
  check('real invoice still accepted after a refusal', backAmount === '9520', backAmount);

  // --- the deliverable ---
  await page.click('#mkNotice');
  await page.waitForSelector('#noticeOut a', { timeout: 20000 });
  const href = await page.getAttribute('#noticeOut a', 'href');
  check('mise en demeure produced a PDF link', /^\/download\/[\w-]+\.pdf$/.test(href), href);
  const pdf = await page.request.get(BASE + href);
  const buf = await pdf.body();
  check('PDF downloads and is non-trivial', buf.length > 20000, buf.length + ' bytes');

  // --- narrow viewport: his browser is ~479px ---
  await page.setViewportSize({ width: 479, height: 900 });
  await page.waitForTimeout(400);
  const overflow = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth);
  check('no horizontal overflow at 479px', overflow <= 1, overflow + 'px');
  await page.screenshot({ path: 'docs/ui-479.png', fullPage: true });

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.waitForTimeout(400);
  await page.screenshot({ path: 'docs/ui-1280.png', fullPage: true });

  check('no console errors', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' | '));

  await browser.close();

  for (const r of results) console.log((r.ok ? 'PASS  ' : 'FAIL  ') + r.name + (r.detail ? '   [' + r.detail + ']' : ''));
  console.log('\n' + (results.length - failed) + '/' + results.length + ' checks passed');
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error('RUN ERROR', e); process.exit(2); });
