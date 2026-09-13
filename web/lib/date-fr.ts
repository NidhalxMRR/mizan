/**
 * Relire une date ISO en toutes lettres.
 *
 * Un champ `<input type="date">` affiche le format de la locale du SYSTÈME,
 * pas celui de l'attribut `lang` de la page. Sur un poste configuré en
 * anglais, « 2026-05-12 » s'affiche « 05/12/2026 » alors que la fiche du cas
 * annonce « facture du 12/05/2026 ». Même jour, lecture inverse.
 *
 * Pour un artisan qui relit sa facture, cette contradiction ressemble à une
 * erreur de saisie : il corrige, et saisit une date fausse. Le format n'est
 * pas imposable au navigateur — on affiche donc la date telle que le moteur
 * la lit, en toutes lettres. Aucune ambiguïté ne survit à « 12 mai 2026 ».
 */

const MOIS = [
  'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
  'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre',
];

export function dateEnClair(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso.trim());
  if (!m) return null;

  const annee = Number(m[1]);
  const mois = Number(m[2]);
  const jour = Number(m[3]);

  const nomMois = MOIS[mois - 1];
  if (!nomMois) return null;
  if (jour < 1 || jour > 31) return null;

  // Une date que le calendrier refuse (31 février) ne doit pas être relue
  // comme si elle existait : le moteur la rejettera de toute façon.
  const d = new Date(Date.UTC(annee, mois - 1, jour));
  if (d.getUTCMonth() !== mois - 1 || d.getUTCDate() !== jour) return null;

  // « 1 mai » et non « 1er mai » : le moteur compte en jours entiers
  // (COC art. 401), on garde la forme la plus neutre possible.
  return `${jour} ${nomMois} ${annee}`;
}
