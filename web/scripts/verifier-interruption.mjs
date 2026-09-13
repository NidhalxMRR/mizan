/**
 * Preuve que l'écran affiche bien ce que le moteur a calculé.
 *
 * Le contrôle est le seul qui vaille devant un jury : on appelle l'API
 * directement, on demande la page au serveur Next, et on vérifie que CHAQUE
 * valeur du JSON se retrouve dans le HTML servi — y compris les phrases
 * juridiques et les citations arabes, mot pour mot.
 *
 * Rien n'est attendu en dur dans ce fichier : les valeurs cherchées sont
 * celles que l'API vient de renvoyer. Si le moteur change d'avis, ce script
 * change avec lui — c'est précisément ce qui prouve que l'interface ne
 * récite pas un résultat mémorisé.
 *
 * Usage :
 *     BASE_URL=http://127.0.0.1:3300 node scripts/verifier-interruption.mjs
 */

const API = (process.env.API_URL ?? 'http://127.0.0.1:8820') + '/dossiers/analyser';
const WEB = process.env.BASE_URL ?? 'http://127.0.0.1:3300';

async function api(corps) {
  const r = await fetch(API, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(corps),
  });
  if (!r.ok) throw new Error(`API ${r.status} sur ${API}`);
  return r.json();
}

async function page(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`page ${r.status} sur ${url}`);
  return r.text();
}

/**
 * Le texte qu'un oeil lit : balises retirées, entités résolues.
 *
 * `toLocaleString('fr-FR')` sépare les milliers par une espace fine
 * insécable (U+202F) : « 2 068 ». On la normalise en espace ordinaire,
 * sinon la comparaison échoue sur une différence purement typographique.
 */
function texteVisible(h) {
  return h
    .replace(/<script[\s\S]*?<\/script>/g, ' ')
    .replace(/<style[\s\S]*?<\/style>/g, ' ')
    .replace(/<!--[\s\S]*?-->/g, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&#x27;|&#39;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&nbsp;|\u00a0/g, ' ')
    .replace(/[\u202f\u2009]/g, ' ')
    .replace(/\u200b/g, '')
    .replace(/\s+/g, ' ');
}

const fr = (iso) => {
  const [a, m, j] = iso.split('-');
  return `${j}/${m}/${a}`;
};

/** Le nombre TEL QU'IL EST AFFICHÉ par la page, séparateur compris. */
const nombreFr = (n) => n.toLocaleString('fr-FR').replace(/[\u202f\u2009\u00a0]/g, ' ');

let echecs = 0;

async function controle(nom, url, corps) {
  console.log('═'.repeat(78));
  console.log(`CAS : ${nom}`);
  console.log(`  page : ${url}`);
  console.log(`  API  : POST ${API} ${JSON.stringify(corps)}`);

  const d = await api(corps);
  const i = d.interruption;
  const brut = await page(url);
  const t = texteVisible(brut);

  const attendus = [
    ['jours restants (compte à rebours)', nombreFr(Math.abs(d.jours_restants))],
    ['echeance retenue', fr(d.echeance)],
  ];
  if (i) {
    attendus.push(
      ['interruption.echeance_initiale', fr(i.echeance_initiale)],
      ['interruption.echeance_effective', fr(i.echeance_effective)],
      // Le signe fait partie de l'affichage : « +50 » ou « 0 ». Le chercher
      // évite qu'un simple « 0 » présent ailleurs dans la page passe pour
      // une preuve.
      [
        'interruption.jours_gagnes (tel qu’affiché)',
        (i.jours_gagnes > 0 ? '+' : '') + nombreFr(i.jours_gagnes),
      ],
      ['interruption.resume_fr (mot pour mot)', i.resume_fr],
    );
    for (const r of i.interruptions) {
      attendus.push(
        ['acte retenu — libelle_fr', r.libelle_fr],
        [`acte retenu — date ${r.date}`, fr(r.date)],
        ['acte retenu — fondement_fr', r.fondement_fr],
        ['acte retenu — effet_fr', r.effet_fr],
        [`acte retenu — article de cause`, `COC art. ${r.article_cause}`],
      );
      for (const a of r.articles)
        attendus.push([`citation arabe art. ${a.article}`, a.citation_ar]);
    }
    for (const s of i.actes_sans_effet) {
      attendus.push(
        ['acte SANS EFFET — libelle_fr', s.libelle_fr],
        ['acte SANS EFFET — motif_fr (mot pour mot)', s.motif_fr],
      );
      for (const a of s.articles)
        attendus.push([`citation arabe art. ${a.article}`, a.citation_ar]);
    }
  }

  console.log(
    `  API  jours_restants=${d.jours_restants} echeance=${d.echeance}` +
      (i
        ? ` interrompu=${i.interrompu} jours_gagnes=${i.jours_gagnes}`
        : ' interruption=null'),
  );
  console.log(`  HTML ${brut.length} octets servis par Next`);
  console.log('  ── valeurs de l’API retrouvées dans le HTML rendu ──');
  for (const [libelle, valeur] of attendus) {
    const present = t.includes(valeur);
    if (!present) echecs++;
    const extrait = valeur.length <= 62 ? valeur : valeur.slice(0, 59) + '…';
    console.log(
      `   [${present ? 'OK    ' : 'MANQUE'}] ${libelle.padEnd(42)} « ${extrait} »`,
    );
  }
  console.log();
}

const enc = encodeURIComponent;

// 1. Le cas d'Ahmed, AVEC une sommation.
await controle(
  'Ahmed + sommation par huissier',
  `${WEB}/dossier?montant=9520&date=2026-05-12&activite=menuiserie&acte=${enc(
    'sommation_huissier:2026-07-01:Sommation de payer signifiée à la société débitrice',
  )}`,
  {
    montant_tnd: 9520.0,
    date_facture: '2026-05-12',
    activite: 'menuiserie',
    actes_interruptifs: [
      {
        type: 'sommation_huissier',
        date: '2026-07-01',
        description: 'Sommation de payer signifiée à la société débitrice',
      },
    ],
  },
);

// 2. Le même dossier SANS acte : l'écran ne doit inventer aucune interruption.
await controle(
  'Ahmed sans aucun acte déclaré (interruption = null)',
  `${WEB}/dossier?montant=9520&date=2026-05-12&activite=menuiserie`,
  { montant_tnd: 9520.0, date_facture: '2026-05-12', activite: 'menuiserie' },
);

// 3. LE PIÈGE : une créance de 2020, une sommation de 2026.
await controle(
  'PIÈGE — créance du 15/01/2020 + sommation tardive du 01/01/2026',
  `${WEB}/dossier?montant=9520&date=2020-01-15&activite=menuiserie&acte=${enc(
    "sommation_huissier:2026-01-01:Sommation signifiée après l'expiration du délai",
  )}`,
  {
    montant_tnd: 9520.0,
    date_facture: '2020-01-15',
    activite: 'menuiserie',
    actes_interruptifs: [
      {
        type: 'sommation_huissier',
        date: '2026-01-01',
        description: "Sommation signifiée après l'expiration du délai",
      },
    ],
  },
);

// 4. Deux actes, dont un fait du débiteur : COC 397 puis COC 396.
await controle(
  'Deux actes : acompte du débiteur (COC 397) puis sommation (COC 396)',
  `${WEB}/dossier?montant=9520&date=2026-05-12&activite=menuiserie` +
    `&acte=${enc('paiement_partiel:2026-06-01:Acompte de 1 200 DT encaissé')}` +
    `&acte=${enc('sommation_huissier:2026-07-01:Sommation par huissier')}`,
  {
    montant_tnd: 9520.0,
    date_facture: '2026-05-12',
    activite: 'menuiserie',
    actes_interruptifs: [
      {
        type: 'paiement_partiel',
        date: '2026-06-01',
        description: 'Acompte de 1 200 DT encaissé',
      },
      {
        type: 'sommation_huissier',
        date: '2026-07-01',
        description: 'Sommation par huissier',
      },
    ],
  },
);

// 5. Un acte mal écrit dans l'URL : signalé, jamais ignoré en silence.
{
  const url =
    `${WEB}/dossier?montant=9520&date=2026-05-12&activite=menuiserie` +
    `&acte=${enc('sommation_huissier:2026-02-31')}` +
    `&acte=${enc('nawak:2026-07-01')}&acte=nawak`;
  console.log('═'.repeat(78));
  console.log(
    "CAS : actes d'URL illisibles (date inexistante, type inconnu, forme absente)",
  );
  console.log(`  page : ${url}`);
  const t = texteVisible(await page(url));
  for (const attendu of [
    'NON TRANSMIS AU MOTEUR',
    'Date « 2026-02-31 » inexploitable',
    "Type d'acte inconnu « nawak »",
    'Forme attendue : type:AAAA-MM-JJ',
  ]) {
    const present = t.includes(attendu);
    if (!present) echecs++;
    console.log(`   [${present ? 'OK    ' : 'MANQUE'}] « ${attendu} »`);
  }
  console.log();
}

console.log('═'.repeat(78));
console.log(
  echecs === 0
    ? '✓ Toutes les valeurs renvoyées par l’API se retrouvent dans le HTML servi.'
    : `✗ ${echecs} valeur(s) attendue(s) absente(s) du HTML.`,
);
process.exit(echecs === 0 ? 0 : 1);
