/* Le poste greffier rend-il la file réelle, ou une page vide à 200 ?

   Assertions sur le TEXTE RENDU après exécution du JS. Un dashboard qui
   répond 200 avec un tableau vide est un échec, pas une réussite.
*/
const { chromium } = require('playwright');

let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; console.log('ok    ' + name); }
  else { fail++; console.log('FAIL  ' + name + (detail ? '   [' + detail + ']' : '')); }
}

// La suite repart d'une file neuve : sans cela, l'action greffier du run
// précédent laisse les dossiers dans leur état cible et les assertions
// changent de verdict d'un passage à l'autre. Un test dont le résultat
// dépend de l'ordre d'exécution ne prouve rien.
const { execSync } = require('child_process');
try {
  execSync('rm -f data/greffe/*.json && ./.venv/bin/python tools/seed_greffe.py',
           { cwd: __dirname + '/..', stdio: 'pipe' });
} catch (e) {
  console.log('FAIL  impossible de reconstruire la file   [' + e.message.slice(0, 120) + ']');
  process.exit(1);
}

(async () => {
  const b = await chromium.launch();
  const page = await b.newPage({ viewport: { width: 1280, height: 1400 } });
  const erreurs = [];
  page.on('pageerror', e => erreurs.push(e.message));

  await page.goto('http://127.0.0.1:8811/greffe', { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);

  check('aucune erreur JS', erreurs.length === 0, erreurs.join(' | '));

  // --- la file est réellement peuplée -------------------------------------
  const lignes = await page.$$eval('#file-body tr:not(.journal-row)', rs => rs.length);
  check('la file contient des dossiers', lignes >= 4, 'lignes=' + lignes);

  const corps = await page.textContent('#file-body');
  check('pas de placeholder de chargement', !/Chargement/.test(corps));
  check('greffe joignable', !/injoignable/.test(corps), corps.slice(0, 90));

  // --- le tri promis par la légende est le tri réel ------------------------
  const etats = await page.$$eval('#file-body tr:not(.journal-row) .verdict',
    vs => vs.map(v => v.className.includes('pret') ? 'pret' : 'attente'));
  const premierAttente = etats.indexOf('attente');
  const dernierPret = etats.lastIndexOf('pret');
  check('instruisables triés en tête',
        premierAttente === -1 || dernierPret === -1 || dernierPret < premierAttente,
        etats.join(','));

  // --- le tri suit l'échéance, pas la date de dépôt ------------------------
  const jours = await page.$$eval('#file-body tr:not(.journal-row)', rs => rs.map(r => {
    const d = r.querySelector('.delai');
    const t = d ? d.textContent.trim() : '';
    if (/Prescrite/.test(t)) return -1;
    const m = t.match(/(\d+)\s*j/);
    return m ? parseInt(m[1], 10) : null;
  }));
  const pretJours = jours.filter((_, i) => etats[i] === 'pret').filter(n => n !== null);
  const trieParUrgence = pretJours.every((n, i) => i === 0 || pretJours[i - 1] <= n);
  check('les instruisables sont triés par échéance la plus proche',
        trieParUrgence, pretJours.join(','));

  // --- l'écart d'urgence est visible, pas seulement écrit ------------------
  const jauges = await page.$$eval('.jauge i', is => is.map(i => parseFloat(i.style.width)));
  check('une jauge encode chaque échéance', jauges.length >= 3, 'jauges=' + jauges.length);
  check("l'écart 242 j vs 5408 j est visible",
        jauges.length >= 2 && (Math.max(...jauges) - Math.min(...jauges)) > 8,
        jauges.map(j => j.toFixed(0)).join('/'));

  // --- la jauge dit l'URGENCE, pas la durée -------------------------------
  // Verrouille une inversion réelle : la barre se remplissait quand il restait
  // BEAUCOUP de temps, donc « pleine » voulait dire « tranquille ».
  const paires = await page.$$eval('#file-body tr:not(.journal-row)', rs => rs.map(r => {
    const d = r.querySelector('.delai'); const i = r.querySelector('.jauge i');
    if (!d || !i) return null;
    const m = d.textContent.match(/(\d+)\s*j/);
    return m ? { j: parseInt(m[1], 10), w: parseFloat(i.style.width) } : null;
  }).filter(Boolean));
  const monotone = paires.every(a => paires.every(b => a.j <= b.j ? a.w >= b.w - 0.01 : true));
  check('jauge pleine = échéance proche (pas l\'inverse)', monotone,
        paires.map(p => p.j + 'j→' + p.w.toFixed(0) + '%').join(' '));

  // --- un dossier bloqué peut être débloqué -------------------------------
  // Tout l'écran sert à ça ; l'action manquait entièrement.
  const relances = await page.$$eval('#file-body tr.bloque:not(.journal-row)',
    rs => rs.map(r => [...r.querySelectorAll('.act')].map(a => a.textContent.trim()).join('|')));
  check('chaque dossier bloqué offre une relance',
        relances.length > 0 && relances.every(t => /Relancer/.test(t)),
        relances.join(' // '));

  // --- l'ambre ne veut pas dire deux choses à la fois ----------------------
  const court = await page.$$eval('.delai.court', ds => ds.map(d => getComputedStyle(d).color));
  const badge = await page.$$eval('.puce-manque', bs => bs.map(b => getComputedStyle(b).color));
  check('échéance urgente et pièce manquante ont des couleurs distinctes',
        court.length === 0 || badge.length === 0 || !court.some(c => badge.includes(c)),
        'court=' + court.join(',') + ' badge=' + badge.join(','));

  // --- le bandeau ne peint pas "bloqué" en vert de succès ------------------
  const cRenvoi = await page.$eval('#c-renvoi', el => getComputedStyle(el).color);
  const cPret = await page.$eval('#c-pret', el => getComputedStyle(el).color);
  check('bloqué et prêt ne partagent pas la même couleur', cRenvoi !== cPret,
        'renvoi=' + cRenvoi + ' pret=' + cPret);

  // --- la référence ne se coupe pas en deux -------------------------------
  const refWrap = await page.$$eval('.ref', rs => rs.map(r => {
    // Mesurer le <td> donne la hauteur de la LIGNE (étirée par la cellule
    // voisine la plus haute), pas celle du texte. Un Range mesure le texte
    // lui-même : autant de rectangles que de lignes réellement occupées.
    const range = document.createRange();
    range.selectNodeContents(r);
    return range.getClientRects().length > 1;
  }));
  check('aucune référence ne passe à la ligne', !refWrap.some(Boolean),
        refWrap.filter(Boolean).length + ' coupées');

  // --- un dossier incomplet NOMME la pièce qui manque ----------------------
  const manques = await page.$$eval('.puce-manque', ms => ms.map(m => m.textContent.trim()));
  check('les pièces manquantes sont nommées', manques.length >= 2, manques.join(' / '));
  check('la facture manquante est nommée',
        manques.some(m => /Facture/.test(m)), manques.join(' / '));
  check('la mise en demeure manquante est nommée',
        manques.some(m => /Mise en demeure/.test(m)), manques.join(' / '));

  // --- la prescription vient du moteur, pas d'une saisie -------------------
  const delais = await page.$$eval('.delai', ds => ds.map(d => d.textContent.trim()));
  check('un délai de prescription est calculé',
        delais.some(d => /\d+\s*j$|Prescrite/.test(d)), delais.join(' / '));

  // --- le bandeau de charge est chiffré -----------------------------------
  const total = (await page.textContent('#c-total')).trim();
  const pret  = (await page.textContent('#c-pret')).trim();
  check('bandeau de charge chiffré', /^\d+$/.test(total) && /^\d+$/.test(pret),
        'total=' + total + ' pret=' + pret);

  // --- le chiffre du brief est présent ET marqué comme hypothèse ----------
  const min = (await page.textContent('#b-min')).trim();
  check('Agency Benefit chiffré', /^\d+$/.test(min), min);
  const statut = (await page.textContent('#b-statut')).trim();
  check('chiffre marqué comme hypothèse, pas comme mesure',
        /hypothèse/i.test(statut), statut);
  const etapes = await page.$$eval('#b-etapes li', ls => ls.length);
  check('les étapes du calcul sont détaillées', etapes === 5, 'etapes=' + etapes);

  // --- une action greffier change réellement l'état ------------------------
  const avant = await page.textContent('#file-body');
  const nbActions = await page.$$eval('#file-body tr:not(.journal-row)',
    rs => rs.map(r => r.querySelectorAll('.act').length));
  check('chaque dossier offre au moins une action',
        nbActions.every(n => n >= 1), nbActions.join(','));
  const btn = await page.$('.act.primary');
  check('au moins un dossier propose une action primaire', !!btn,
        'aucun — tous déjà dans leur état cible ?');
  if (btn) {
    await btn.click();
    await page.waitForTimeout(900);
    const apres = await page.textContent('#file-body');
    check("l'action greffier modifie la file", avant !== apres);
    check('le journal enregistre l\'opération',
          /Journal — [2-9]/.test(apres) || /Journal — \d\d/.test(apres));
  }

  // --- pas de débordement sur petit écran (son navigateur ~479px) ---------
  await page.setViewportSize({ width: 479, height: 900 });
  await page.waitForTimeout(300);
  const debord = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth);
  check('pas de débordement horizontal à 479px', debord <= 1, 'debord=' + debord + 'px');

  await b.close();
  console.log('\n' + pass + '/' + (pass + fail) + ' checks passed');
  process.exit(fail ? 1 : 0);
})();
