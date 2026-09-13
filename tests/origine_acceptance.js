/* Le calcul dit-il sur quoi il repose ?

   Défaut trouvé par l'utilisateur : cliquer « Calculer » sans déposer la
   moindre facture produisait un verdict aussi affirmatif qu'un dossier
   vérifié. Ces vérifications tiennent la promesse : l'écran nomme toujours
   l'origine de ses chiffres, et refuse une date impossible.
*/
const { chromium } = require('playwright');

const BASE = process.env.MIZAN_URL || 'http://127.0.0.1:8811';
let pass = 0, fail = 0;
function check(label, ok, detail) {
  if (ok) { pass++; console.log('ok    ' + label); }
  else { fail++; console.log('FAIL  ' + label + (detail ? '   [' + detail + ']' : '')); }
}

(async () => {
  const b = await chromium.launch();
  const page = await b.newPage({ viewport: { width: 1280, height: 1400 } });
  const errs = [];
  // Le refus d'une date impossible EST un 400 : c'est la réponse correcte,
  // pas une panne. On ne compte que les vraies erreurs de script.
  page.on('console', m => {
    if (m.type() !== 'error') return;
    const t = m.text();
    if (/status of 400/.test(t)) return;
    errs.push(t);
  });
  page.on('pageerror', e => errs.push('PAGEERROR: ' + e.message));

  await page.goto(BASE + '/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(400);

  // --- 1. calcul SANS facture : le verdict doit se déclarer estimation ------
  // page.fill() ne déclenche pas toujours l'événement qui active le bouton :
  // on saisit comme un humain, au clavier.
  await page.click('#amount'); await page.type('#amount', '9874');
  await page.fill('#idate', '2026-05-12');
  await page.dispatchEvent('#idate', 'input');
  await page.waitForFunction(() => !document.querySelector('#go').disabled,
                             null, { timeout: 5000 });
  await page.click('#go');
  await page.waitForTimeout(900);

  const visible = await page.$eval('#origine', el => !el.hidden).catch(() => false);
  check("l'origine des chiffres est affichée", visible);

  const cls = await page.$eval('#origine', el => el.className).catch(() => '');
  check('un calcul sans facture est marqué « déclaré »', /declaree/.test(cls), cls);

  const txt = await page.$eval('#origine', el => el.textContent).catch(() => '');
  check("le texte dit qu'aucune facture n'a été vérifiée",
        /Aucune facture/i.test(txt), txt.slice(0, 80));
  check('le texte reste honnête sur la validité du calcul',
        /exacts?/i.test(txt), txt.slice(0, 120));

  // le verdict lui-même doit rester affiché : on informe, on ne bloque pas
  const vHidden = await page.$eval('#verdict', el => el.hidden).catch(() => true);
  check('le verdict reste affiché malgré la mention', !vHidden);

  // --- 2. date future : refus explicite, pas un calcul poli ----------------
  await page.fill('#idate', '2026-09-14');
  await page.dispatchEvent('#idate', 'input');
  await page.waitForTimeout(200);
  await page.click('#go');
  await page.waitForTimeout(900);
  const body = await page.$eval('body', el => el.textContent);
  check('une facture datée du futur est refusée',
        /après aujourd|ne peut pas commencer/i.test(body),
        body.slice(0, 0) || 'aucun message de refus');

  // --- 3. aucune erreur JS -------------------------------------------------
  check('aucune erreur console', errs.length === 0, errs.slice(0, 2).join(' | '));

  await b.close();
  console.log('\n' + pass + '/' + (pass + fail) + ' checks passed');
  process.exit(fail ? 1 : 0);
})();
