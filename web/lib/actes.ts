/**
 * Les actes interruptifs, lus depuis l'URL.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * ENCODAGE — un paramètre `acte`, RÉPÉTABLE :
 *
 *     /dossier?montant=9520&date=2026-05-12&acte=sommation_huissier:2026-07-01
 *     /dossier?...&acte=paiement_partiel:2026-06-01:Acompte de 1 200 DT
 *     /dossier?...&acte=paiement_partiel:2026-06-01&acte=sommation_huissier:2026-07-01
 *
 * Forme :  type ":" date[ ":" description ]
 *   - `type` : l'un des six types acceptés par l'API (voir TYPES_ACTES) ;
 *   - `date` : AAAA-MM-JJ ;
 *   - `description` : facultative, texte libre ; elle peut contenir des
 *     deux-points, on ne découpe donc que sur les deux PREMIERS.
 *
 * Pourquoi l'URL et pas un POST de formulaire : la page doit rester rendue
 * côté serveur. Le résultat de l'interruption est alors dans le HTML, donc
 * vérifiable au `curl`, et une URL de démonstration se rejoue à l'identique
 * sans toucher un clavier.
 * ─────────────────────────────────────────────────────────────────────────────
 *
 * Ce module ne juge RIEN sur le fond : il ne décide jamais qu'un acte
 * interrompt ou n'interrompt pas. Il vérifie seulement qu'une chaîne d'URL a
 * la forme attendue, et laisse le moteur juridique dire le droit. Un acte mal
 * écrit est signalé tel quel plutôt que silencieusement ignoré : une PME qui
 * croit avoir déclaré sa sommation et ne la voit pas prise en compte, c'est
 * exactement la situation qu'on veut rendre impossible.
 */

import type { ActeInterruptifEntree, TypeActeInterruptif } from './api';

/**
 * Les six types acceptés par `api/schemas.py::ActeInterruptifEntree`.
 *
 * Les trois premiers émanent du créancier (COC art. 396), les trois derniers
 * du débiteur (COC art. 397). Le libellé sert à l'affichage du formulaire ;
 * celui que le moteur renvoie dans sa réponse (`libelle_fr`) reste
 * prioritaire partout où il existe.
 */
export const TYPES_ACTES: ReadonlyArray<{
  valeur: TypeActeInterruptif;
  libelle: string;
  auteur: 'créancier' | 'débiteur';
  article: 396 | 397;
}> = [
  {
    valeur: 'sommation_huissier',
    libelle: 'Sommation de payer par huissier',
    auteur: 'créancier',
    article: 396,
  },
  {
    valeur: 'demande_justice',
    libelle: 'Demande en justice',
    auteur: 'créancier',
    article: 396,
  },
  {
    valeur: 'saisie_conservatoire',
    libelle: 'Saisie conservatoire',
    auteur: 'créancier',
    article: 396,
  },
  {
    valeur: 'reconnaissance_dette',
    libelle: 'Reconnaissance de dette écrite',
    auteur: 'débiteur',
    article: 397,
  },
  {
    valeur: 'paiement_partiel',
    libelle: 'Paiement partiel (acompte)',
    auteur: 'débiteur',
    article: 397,
  },
  {
    valeur: 'arrete_compte',
    libelle: 'Arrêté de compte signé',
    auteur: 'débiteur',
    article: 397,
  },
] as const;

const VALEURS = new Set<string>(TYPES_ACTES.map((t) => t.valeur));

export function libelleType(valeur: string): string {
  return TYPES_ACTES.find((t) => t.valeur === valeur)?.libelle ?? valeur;
}

/** Un acte d'URL qu'on n'a pas su lire, et pourquoi. */
export type ActeIllisible = { brut: string; motif: string };

export type LectureActes = {
  actes: ActeInterruptifEntree[];
  illisibles: ActeIllisible[];
};

const FORME_DATE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Une date de calendrier, pas seulement une chaîne bien formée.
 *
 * `2026-02-31` passe la regex mais n'existe pas ; l'API la refuserait avec un
 * 422 illisible pour un juriste. On préfère le dire ici, en français.
 */
function dateReelle(iso: string): boolean {
  if (!FORME_DATE.test(iso)) return false;
  const [a, m, j] = iso.split('-').map(Number);
  const d = new Date(Date.UTC(a, m - 1, j));
  return (
    d.getUTCFullYear() === a && d.getUTCMonth() === m - 1 && d.getUTCDate() === j
  );
}

/** Décode un seul `acte=…`. */
export function lireActe(brut: string): ActeInterruptifEntree | ActeIllisible {
  const texte = brut.trim();
  if (!texte) return { brut, motif: 'Paramètre vide.' };

  // On ne découpe que sur les deux premiers deux-points : la description est
  // du texte libre et peut en contenir (« réf : 2026/041 »).
  const p1 = texte.indexOf(':');
  if (p1 === -1) {
    return {
      brut,
      motif: 'Forme attendue : type:AAAA-MM-JJ (les deux-points manquent).',
    };
  }
  const type = texte.slice(0, p1).trim();
  const reste = texte.slice(p1 + 1);
  const p2 = reste.indexOf(':');
  const date = (p2 === -1 ? reste : reste.slice(0, p2)).trim();
  const description = p2 === -1 ? '' : reste.slice(p2 + 1).trim();

  if (!VALEURS.has(type)) {
    return {
      brut,
      motif: `Type d'acte inconnu « ${type} ». Types admis : ${TYPES_ACTES.map(
        (t) => t.valeur,
      ).join(', ')}.`,
    };
  }
  if (!dateReelle(date)) {
    return {
      brut,
      motif: `Date « ${date} » inexploitable : il faut une date réelle au format AAAA-MM-JJ.`,
    };
  }

  return { type: type as TypeActeInterruptif, date, description };
}

/**
 * Décode tous les `acte=…` d'une URL.
 *
 * Next fournit `string | string[] | undefined` selon que le paramètre est
 * présent une ou plusieurs fois : les deux cas sont traités, parce que la
 * démonstration utilise l'un et l'autre.
 */
export function lireActesDepuisUrl(
  valeur: string | string[] | undefined,
): LectureActes {
  const bruts = valeur === undefined ? [] : Array.isArray(valeur) ? valeur : [valeur];

  const actes: ActeInterruptifEntree[] = [];
  const illisibles: ActeIllisible[] = [];
  for (const b of bruts) {
    const lu = lireActe(b);
    if ('motif' in lu) illisibles.push(lu);
    else actes.push(lu);
  }
  return { actes, illisibles };
}

/** Réencode un acte pour le remettre dans une URL. */
export function ecrireActe(a: ActeInterruptifEntree): string {
  return a.description
    ? `${a.type}:${a.date}:${a.description}`
    : `${a.type}:${a.date}`;
}

/**
 * Construit l'URL du parcours : les trois champs, puis un `acte` par acte.
 *
 * `URLSearchParams.append` est utilisé volontairement — `set` écraserait les
 * actes précédents et on n'en garderait qu'un seul.
 */
export function urlDossier(champs: {
  montant: string;
  date: string;
  activite: string;
  actes: ActeInterruptifEntree[];
}): string {
  const p = new URLSearchParams({
    montant: champs.montant,
    date: champs.date,
    activite: champs.activite,
  });
  for (const a of champs.actes) p.append('acte', ecrireActe(a));
  return `/dossier?${p}`;
}
