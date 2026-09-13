/**
 * Les six icônes de rôle — dessinées à la main, en SVG inline.
 *
 * Pourquoi à la main plutôt qu'une bibliothèque : la salle de démonstration
 * n'a pas de wifi garanti. Une icône chargée depuis un CDN, une police
 * d'icônes distante ou un paquet npm supplémentaire, c'est un rond vide à
 * l'écran devant le jury. Ici il n'y a que des tracés, dans le fichier.
 *
 * Contraintes tenues sur les six, pour qu'elles forment une famille et non
 * une collection :
 *   - même boîte : viewBox 0 0 24 24, tracés contenus entre 2 et 22 ;
 *   - même épaisseur : 1.6, jointures et extrémités arrondies ;
 *   - aucune couleur écrite : `stroke="currentColor"`, donc l'icône prend la
 *     couleur du texte qui l'entoure — teal sur une carte sélectionnée, gris
 *     sur une carte au repos, sans avoir à la redessiner ;
 *   - aucun remplissage : un aplat aurait mal vieilli sur fond mint.
 *
 * Chaque dessin dit le métier, pas l'abstraction : un organigramme pour
 * l'administrateur, une devanture pour l'entreprise, un sceau pour
 * l'accréditation, un registre pour le greffe, un pli cacheté pour l'huissier.
 * Et pour l'avocat, la robe : col, rabat et épitoge. Pas une balance — elle
 * appartient à la juridiction, pas au conseil, et elle sert déjà de marque à
 * Mizan ; deux balances à l'écran auraient brouillé les deux.
 */

import type { Role } from '@/lib/auth';

type ProprietesIcone = {
  /** Taille en pixels. Le tracé est prévu pour rester lisible dès 18 px. */
  taille?: number;
  className?: string;
};

/**
 * Attributs communs. Les regrouper évite qu'une icône dérive discrètement de
 * la famille au fil des retouches : on ne peut pas changer l'épaisseur d'une
 * seule sans le voir.
 */
function socle(
  taille: number,
  className?: string,
): React.SVGProps<SVGSVGElement> {
  // Le type de retour est annoté : sans lui, TypeScript élargit `focusable`
  // en `string` et refuse ensuite de l'étaler sur un <svg>.
  return {
    width: taille,
    height: taille,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.6,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    // Décoratives : le nom du rôle est toujours écrit à côté, en toutes
    // lettres. Les faire lire par un lecteur d'écran doublerait l'annonce.
    'aria-hidden': true,
    focusable: 'false',
    className,
  };
}

/** Administrateur — un organigramme : une tête, trois organisations. */
export function IconeAdministrateur({ taille = 24, className }: ProprietesIcone) {
  return (
    <svg {...socle(taille, className)}>
      <rect x="9" y="2.5" width="6" height="4.6" rx="1.2" />
      <path d="M12 7.1v3.1" />
      <path d="M5 10.2h14" />
      <path d="M5 10.2v3.2M12 10.2v3.2M19 10.2v3.2" />
      <rect x="2" y="13.4" width="6" height="4.6" rx="1.2" />
      <rect x="9" y="13.4" width="6" height="4.6" rx="1.2" />
      <rect x="16" y="13.4" width="6" height="4.6" rx="1.2" />
      <path d="M3.6 20.6h16.8" />
    </svg>
  );
}

/** Entreprise — une devanture : auvent, vitrine, porte. */
export function IconeEntreprise({ taille = 24, className }: ProprietesIcone) {
  return (
    <svg {...socle(taille, className)}>
      <path d="M3 9.2 5.6 4.4h12.8L21 9.2" />
      <path d="M4.6 9.2v11.4h14.8V9.2" />
      <rect x="10" y="14" width="4" height="6.6" rx="0.6" />
      <rect x="6.6" y="11.8" width="2.6" height="2.6" rx="0.5" />
      <rect x="14.8" y="11.8" width="2.6" height="2.6" rx="0.5" />
      <path d="M2.6 20.6h18.8" />
    </svg>
  );
}

/**
 * Avocat — la robe : les épaules, le col en V largement ouvert, et le rabat
 * en deux bandes au creux du V.
 *
 * Le premier tracé était juste mais illisible : à 22 px — la taille réelle des
 * cartes de qualité — le V se refermait, le rabat se lisait comme la poignée
 * d'une mallette, et l'épitoge ajoutait un trait de plus dans une zone déjà
 * chargée. Vérifié sur capture à 479 px comme à 1280 px. Il reste donc quatre
 * gestes, pas davantage : deux épaules, un V profond, deux bandes. Une icône
 * exacte que personne ne déchiffre ne vaut pas une icône simple qui se lit.
 */
export function IconeAvocat({ taille = 24, className }: ProprietesIcone) {
  return (
    <svg {...socle(taille, className)}>
      {/* Les épaules et les pans de la robe, qui tombent droit. */}
      <path d="M8.6 3.2 4.4 5.4a2 2 0 0 0-1.2 1.9v13.5h17.6V7.3a2 2 0 0 0-1.2-1.9L15.4 3.2" />
      {/* Le col : un V large et profond, seul signe réellement lisible à 22 px. */}
      <path d="M8.6 3.2 12 11.2 15.4 3.2" />
      {/* Le rabat : deux bandes verticales jointives, au creux du col. */}
      <path d="M10.7 11.6v3.9" />
      <path d="M13.3 11.6v3.9" />
    </svg>
  );
}

/** Professionnel accrédité — un sceau à ruban : l'agrément, pas le diplôme. */
export function IconeProfessionnel({ taille = 24, className }: ProprietesIcone) {
  return (
    <svg {...socle(taille, className)}>
      <circle cx="12" cy="9.2" r="6.1" />
      <path d="M9.3 9.4 11.2 11.3 14.9 7.3" />
      <path d="M8.5 14.4 6.9 21.4 12 19.1 17.1 21.4 15.5 14.4" />
    </svg>
  );
}

/** Greffier — le registre du rôle : reliure, signet, mentions portées. */
export function IconeGreffier({ taille = 24, className }: ProprietesIcone) {
  return (
    <svg {...socle(taille, className)}>
      <rect x="3.6" y="3" width="16.8" height="18" rx="2" />
      <path d="M7.4 3v18" />
      <path d="M14.4 3v6.2l2.3-1.7 2.3 1.7V3" />
      <path d="M10.3 13.2h6.6" />
      <path d="M10.3 17h6.6" />
    </svg>
  );
}

/** Huissier — le pli et son cachet : l'acte signifié, pas l'acte rédigé. */
export function IconeHuissier({ taille = 24, className }: ProprietesIcone) {
  return (
    <svg {...socle(taille, className)}>
      <rect x="2.4" y="4.4" width="15.6" height="11.6" rx="1.6" />
      <path d="M2.4 5.6 10.2 11.6 18 5.6" />
      <circle cx="17.6" cy="17.6" r="4" />
      <path d="M15.8 17.6h3.6M17.6 15.8v3.6" />
    </svg>
  );
}

/**
 * Aiguillage par rôle. Un seul endroit à modifier le jour où un sixième
 * acteur apparaît — et TypeScript refusera de compiler tant qu'il manquera.
 */
const parRole: Record<Role, (p: ProprietesIcone) => React.JSX.Element> = {
  platform_admin: IconeAdministrateur,
  msme: IconeEntreprise,
  avocat: IconeAvocat,
  accredited_pro: IconeProfessionnel,
  court_clerk: IconeGreffier,
  huissier: IconeHuissier,
};

export function IconeRole({
  role,
  taille = 24,
  className,
}: ProprietesIcone & { role: Role }) {
  const Dessin = parRole[role];
  return <Dessin taille={taille} className={className} />;
}

/* ---------------------------------------------------------------------------
   Quelques pictogrammes d'appoint, de la même famille (24, 1.6, currentColor).
   Ils servent aux cartes d'action des tableaux de bord ; sans eux il aurait
   fallu importer une bibliothèque, ce qu'on s'interdit.
--------------------------------------------------------------------------- */

/** Cadenas — une action fermée à ce rôle. */
export function IconeVerrou({ taille = 24, className }: ProprietesIcone) {
  return (
    <svg {...socle(taille, className)}>
      <rect x="4.6" y="10.4" width="14.8" height="10.2" rx="2" />
      <path d="M8.2 10.4V7.6a3.8 3.8 0 0 1 7.6 0v2.8" />
      <path d="M12 14.4v2.4" />
    </svg>
  );
}

/** Coche — un privilège accordé. */
export function IconeCoche({ taille = 24, className }: ProprietesIcone) {
  return (
    <svg {...socle(taille, className)}>
      <path d="M4.6 12.6 9.4 17.4 19.4 7.2" />
    </svg>
  );
}

/** Balance — rappel de la marque sur les écrans d'entrée. */
export function IconeBalance({ taille = 24, className }: ProprietesIcone) {
  return (
    <svg {...socle(taille, className)}>
      <path d="M12 3.4v17.2" />
      <path d="M5 6.6h14" />
      <path d="M8.4 20.6h7.2" />
      <path d="M5 6.6 2.4 13.2h5.2Z" />
      <path d="M19 6.6l-2.6 6.6h5.2Z" />
    </svg>
  );
}
