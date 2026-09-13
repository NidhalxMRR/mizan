import type { Role } from '@/lib/auth';
import { permissions } from '@/lib/auth';
import { privileges, type ClePermission } from '@/components/roles/privileges';

/**
 * Le contenu des cinq tableaux de bord.
 *
 * Règle unique et non négociable de ce fichier : **une action n'apparaît sur
 * un tableau de bord que si la matrice de `lib/auth.ts` l'autorise pour ce
 * rôle**. Les actions sont donc désignées par leur clé de permission, et
 * `actionsDuRole()` refuse de rendre une carte dont la permission n'est pas
 * accordée. Un écran ne peut pas promettre ce que le contrôle d'accès
 * refusera.
 *
 * Deuxième règle : ce que le rôle ne peut PAS faire n'est pas simplement
 * absent. Sur chaque tableau de bord, une ou deux actions sont affichées
 * FERMÉES, avec le motif juridique. Un bouton absent se lit comme un oubli
 * de développeur ; un bouton fermé qui cite le Code de procédure civile se
 * lit comme une règle. C'est la thèse du projet et elle se montre là.
 *
 * Sur les données affichées : ce sont des dossiers de démonstration, écrits
 * dans ce fichier. Ils ne prétendent pas venir de l'API — aucun chiffre ici
 * n'est présenté comme « calculé ». Les calculs réels vivent dans /dossier,
 * qui interroge le moteur déterministe.
 */

/* ---------------------------------------------------------------------------
   Types
--------------------------------------------------------------------------- */

export type Mesure = {
  libelle: string;
  valeur: string;
  detail: string;
  /** Reprend les trois états de provenance déjà définis dans globals.css. */
  etat: 'verified' | 'declared' | 'abstain';
};

/** Une action ouverte : elle DOIT correspondre à une permission du rôle. */
export type ActionOuverte = {
  cle: ClePermission;
  /**
   * Le texte de la carte. Quand il est absent, on reprend l'intitulé et la
   * portée du dictionnaire des privilèges — c'est le cas le plus fréquent, et
   * cela garantit que l'inscription et le tableau de bord disent la même
   * chose du même pouvoir.
   */
  intitule?: string;
  portee?: string;
};

/** Une action fermée : le motif est obligatoire, sinon elle ressemble à un bug. */
export type ActionFermee = {
  intitule: string;
  motif: string;
  /** Qui la détient. Toujours renseigné : une barrière a un bénéficiaire. */
  reservee: string;
  fondement?: string;
};

export type Dossier = {
  reference: string;
  parties: string;
  montant: string;
  etat: string;
  /** Reprend .provenance-* de globals.css : verified, declared, abstain, danger. */
  etatTon: 'verified' | 'declared' | 'abstain' | 'danger';
  /** Le compte à rebours. Absent quand le délai ne concerne pas ce rôle. */
  delai?: { nombre: string; libelle: string; ton: 'ok' | 'attention' | 'critique' };
};

export type Tableau = {
  /** Ce que la personne voit en arrivant. Une phrase, son métier. */
  accroche: string;
  mesures: Mesure[];
  /** Titre de la section des dossiers : « Mes dossiers », « La file »… */
  titreListe: string;
  sousTitreListe: string;
  dossiers: Dossier[];
  titreActions: string;
  actions: ActionOuverte[];
  fermees: ActionFermee[];
  /** Le bandeau de pied : la limite que ce rôle rencontre. */
  limite: { titre: string; corps: React.ReactNode };
};

/* ---------------------------------------------------------------------------
   Les cinq tableaux
--------------------------------------------------------------------------- */

export const tableaux: Record<Role, Tableau> = {
  /* --- Entreprise --------------------------------------------------------- */
  msme: {
    accroche:
      'Vos impayés, le délai qui court sur chacun, et ce qui reste possible.',
    mesures: [
      {
        libelle: 'Dossiers ouverts',
        valeur: '3',
        detail: 'Dont un en conciliation',
        etat: 'verified',
      },
      {
        libelle: 'Montant en jeu',
        valeur: '47 200 DT',
        detail: 'Somme des créances déclarées',
        etat: 'declared',
      },
      {
        libelle: 'Délai le plus court',
        // Relevé sur capture, confirmé en lisant le DOM : la carte annonçait
        // « 41 jours » et « dossier le plus ancien », alors que la liste
        // juste dessous montre 41 / 186 / 9 jours et que le dossier le plus
        // ancien (2023-064) est celui à 9 jours. La mesure de tête
        // contredisait donc la liste sur les deux points à la fois. Sur un
        // produit dont l'argument est la prescription, un jury de juristes
        // fait le rapprochement en dix secondes.
        valeur: '9 jours',
        detail: 'Avant prescription — dossier Ets Mabrouk, ci-dessous',
        etat: 'declared',
      },
    ],
    titreListe: 'Mes dossiers',
    sousTitreListe:
      'Vous ne voyez que les vôtres. Aucune autre entreprise n’y a accès.',
    dossiers: [
      {
        reference: 'Facture 2024-118 — Société Kairouan Textile',
        parties: 'Vous, créancier · Kairouan Textile, débiteur',
        montant: '28 400 DT',
        etat: 'Mise en demeure chez l’huissier',
        etatTon: 'declared',
        delai: { nombre: '41', libelle: 'jours restants', ton: 'attention' },
      },
      {
        reference: 'Facture 2024-207 — Comptoir du Sud',
        parties: 'Vous, créancier · Comptoir du Sud, débiteur',
        montant: '12 900 DT',
        etat: 'Conciliation ouverte',
        etatTon: 'verified',
        delai: { nombre: '186', libelle: 'jours restants', ton: 'ok' },
      },
      {
        reference: 'Facture 2023-064 — Ets Mabrouk',
        parties: 'Vous, créancier · Ets Mabrouk, débiteur',
        montant: '5 900 DT',
        etat: 'Pièce manquante réclamée',
        etatTon: 'abstain',
        delai: { nombre: '9', libelle: 'jours restants', ton: 'critique' },
      },
    ],
    titreActions: 'Ce que vous pouvez faire',
    actions: [
      { cle: 'upload_evidence' },
      { cle: 'request_notice' },
      { cle: 'open_ecma' },
      { cle: 'choose_professional' },
      { cle: 'accept_settlement' },
      // « Ouvrir un dossier » annonçait une création là où la portée de la
      // carte décrit une consultation (« Consulter à tout moment l'état de
      // vos litiges… »). Titre et corps de la même carte se contredisaient.
      { cle: 'view_own_case', intitule: 'Consulter un de vos dossiers' },
    ],
    fermees: [
      {
        intitule: 'Signifier vous-même la mise en demeure',
        motif:
          'Toute citation, notification ou exécution passe par le ministère ' +
          "d'un huissier de justice. Mizan prépare l'acte ; elle ne le " +
          'signifie pas, et vous non plus.',
        reservee: 'à l’huissier de justice',
        fondement: 'Code de procédure civile et commerciale, art. 5 et 60',
      },
      {
        intitule: 'Approuver votre dossier pour audience',
        motif:
          'La régularité formelle du dossier est constatée par le greffe, ' +
          'pas par la partie qui le dépose.',
        reservee: 'au greffier',
      },
    ],
    limite: {
      titre: 'Ce que Mizan ne fera jamais à votre place',
      corps: (
        <>
          La plateforme calcule vos délais, cite les articles et prépare vos
          actes. Elle ne signifie rien, ne juge rien et ne vous représente pas.
          Le monopole de la signification appartient au{' '}
          <span className="incise-ar">عدل منفذ</span>, et il n’est pas
          négociable.
        </>
      ),
    },
  },

  /* --- Professionnel accrédité -------------------------------------------- */
  accredited_pro: {
    accroche:
      'Les dossiers où les parties vous ont retenu, et les séances à conduire.',
    mesures: [
      {
        libelle: 'Dossiers confiés',
        valeur: '4',
        detail: 'Vous n’accédez qu’à ceux-là',
        etat: 'verified',
      },
      {
        libelle: 'Séances à conduire',
        valeur: '2',
        detail: 'Cette semaine',
        etat: 'declared',
      },
      {
        libelle: 'Accords signés',
        valeur: '11',
        detail: 'Depuis votre accréditation',
        etat: 'verified',
      },
    ],
    titreListe: 'Dossiers qui vous sont confiés',
    sousTitreListe:
      'Il n’existe pas de vue générale : les dossiers où vous n’êtes pas saisi vous restent fermés.',
    dossiers: [
      {
        reference: 'Conciliation 2024-C-044',
        parties: 'Comptoir du Sud · Atelier de la Médina',
        montant: '12 900 DT',
        etat: 'Deuxième séance à tenir',
        etatTon: 'declared',
        delai: { nombre: '3', libelle: 'jours avant séance', ton: 'attention' },
      },
      {
        reference: 'Médiation 2024-M-017',
        parties: 'Sfax Métal · Transports Jelassi',
        montant: '61 500 DT',
        etat: 'Accord en rédaction',
        etatTon: 'verified',
        delai: { nombre: '12', libelle: 'jours pour signer', ton: 'ok' },
      },
      {
        reference: 'Conciliation 2024-C-051',
        parties: 'Ets Mabrouk · Fournitures Zarzis',
        montant: '5 900 DT',
        etat: 'Pièce réclamée, en attente',
        etatTon: 'abstain',
      },
    ],
    titreActions: 'Votre office',
    actions: [
      { cle: 'conduct_ecma' },
      { cle: 'draft_settlement' },
      { cle: 'sign_settlement' },
      { cle: 'request_missing_piece' },
      { cle: 'view_assigned_case', intitule: 'Ouvrir un dossier confié' },
    ],
    fermees: [
      {
        intitule: 'Trancher le litige',
        motif:
          'Votre office est d’amener les parties à un accord, non de leur ' +
          'imposer une solution. Ce qui n’est pas convenu devant vous reste ' +
          'au juge.',
        reservee: 'au juge',
      },
      {
        intitule: 'Signifier un acte à une partie',
        motif:
          'La convocation que vous adressez n’est pas une signification. ' +
          'Seul un huissier de justice signifie.',
        reservee: 'à l’huissier de justice',
        fondement: 'Code de procédure civile et commerciale, art. 5',
      },
    ],
    limite: {
      titre: 'Conduire n’est pas juger',
      corps: (
        <>
          Vous consignez ce que les parties acceptent. Votre signature atteste
          de ce qui a été convenu devant vous — elle ne garantit ni la
          véracité des pièces, ni la solvabilité du débiteur.
        </>
      ),
    },
  },

  /* --- Huissier de justice ------------------------------------------------ */
  huissier: {
    accroche:
      'Les projets de mise en demeure qui vous sont adressés, prêts à contrôler.',
    mesures: [
      {
        libelle: 'Projets reçus',
        valeur: '6',
        detail: 'Parties identifiées, montants calculés',
        etat: 'declared',
      },
      {
        libelle: 'Actes signifiés',
        valeur: '23',
        detail: 'Dates consignées au dossier',
        etat: 'verified',
      },
      {
        libelle: 'Projets refusés',
        valeur: '2',
        detail: 'Renvoyés au demandeur avec motif',
        etat: 'abstain',
      },
    ],
    titreListe: 'Demandes de signification',
    sousTitreListe:
      'Un projet reçu n’est pas un acte accepté : vous restez libre de le refuser ou de le faire corriger.',
    dossiers: [
      {
        reference: 'Projet d’إنذار — Atelier de la Médina',
        parties: 'Contre Kairouan Textile · Tunis',
        montant: '28 400 DT',
        etat: 'À contrôler avant signification',
        etatTon: 'declared',
        delai: { nombre: '5', libelle: 'jours francs requis', ton: 'attention' },
      },
      {
        reference: 'Projet d’إنذار — Sfax Métal',
        parties: 'Contre Transports Jelassi · Sfax',
        montant: '61 500 DT',
        etat: 'Signifié le 4 septembre',
        etatTon: 'verified',
      },
      {
        reference: 'Projet d’إنذار — Fournitures Zarzis',
        parties: 'Contre Ets Mabrouk · Médenine',
        montant: '890 DT',
        etat: 'Montant inférieur au seuil — à vérifier',
        etatTon: 'abstain',
      },
    ],
    titreActions: 'Votre ministère',
    actions: [
      { cle: 'issue_formal_notice' },
      { cle: 'record_service' },
      { cle: 'view_notice_request', intitule: 'Examiner un projet reçu' },
    ],
    fermees: [
      {
        intitule: 'Déposer une facture au dossier',
        motif:
          'Les pièces sont versées par la partie qui les détient. Vous ' +
          'signifiez l’acte, vous ne constituez pas le dossier.',
        reservee: 'à l’entreprise',
      },
      {
        intitule: 'Rédiger un procès-verbal de conciliation',
        motif:
          'La conduite de la conciliation et la rédaction de l’accord ' +
          'relèvent du professionnel accrédité que les parties ont retenu.',
        reservee: 'au professionnel accrédité',
      },
    ],
    limite: {
      titre: 'Le monopole est le vôtre, et il vous oblige',
      corps: (
        <>
          La plateforme vous livre un projet complet ; elle ne signifie jamais
          à votre place. La date que vous consignez fait courir les cinq jours
          francs et engage votre responsabilité professionnelle.
        </>
      ),
    },
  },

  /* --- Greffier ----------------------------------------------------------- */
  court_clerk: {
    accroche:
      'La file de votre juridiction, classée par urgence de prescription.',
    mesures: [
      {
        libelle: 'Dossiers en file',
        valeur: '18',
        detail: 'Tribunal de commerce de Tunis',
        etat: 'verified',
      },
      {
        libelle: 'Prêts pour audience',
        valeur: '7',
        detail: 'Pièces complètes et empreintes intactes',
        etat: 'verified',
      },
      {
        libelle: 'À compléter',
        valeur: '4',
        detail: 'Renvoyés à la partie avec motif',
        etat: 'declared',
      },
    ],
    titreListe: 'File d’attente du greffe',
    sousTitreListe:
      'Votre juridiction uniquement. Les dossiers d’un autre tribunal ne vous sont pas présentés.',
    dossiers: [
      {
        reference: 'Dossier 2024/TC/0912',
        parties: 'Atelier de la Médina · Kairouan Textile',
        montant: '28 400 DT',
        etat: 'Pièces complètes',
        etatTon: 'verified',
        delai: { nombre: '41', libelle: 'jours restants', ton: 'attention' },
      },
      {
        reference: 'Dossier 2024/TC/0934',
        parties: 'Sfax Métal · Transports Jelassi',
        montant: '61 500 DT',
        etat: 'Médiation à fixer',
        etatTon: 'declared',
        delai: { nombre: '128', libelle: 'jours restants', ton: 'ok' },
      },
      {
        reference: 'Dossier 2024/TC/0871',
        parties: 'Ets Mabrouk · Fournitures Zarzis',
        montant: '5 900 DT',
        etat: 'Bon de livraison illisible',
        etatTon: 'danger',
        delai: { nombre: '9', libelle: 'jours restants', ton: 'critique' },
      },
    ],
    titreActions: 'Vos diligences',
    actions: [
      { cle: 'review_evidence' },
      { cle: 'approve_dossier' },
      { cle: 'schedule_mediation' },
      { cle: 'export_dossier' },
      { cle: 'view_queue', intitule: 'Trier la file par échéance' },
    ],
    fermees: [
      {
        intitule: 'Apprécier la valeur d’une preuve',
        motif:
          'Votre examen porte sur la régularité formelle : les pièces ' +
          'annoncées sont-elles au dossier, lisibles, intactes. ' +
          'L’appréciation de la preuve appartient au juge.',
        reservee: 'au juge',
      },
      {
        intitule: 'Signifier une mise en demeure',
        motif:
          'Le greffe enregistre et transmet ; il ne signifie pas. ' +
          'La signification relève du ministère de l’huissier.',
        reservee: 'à l’huissier de justice',
        fondement: 'Code de procédure civile et commerciale, art. 5',
      },
    ],
    limite: {
      titre: 'Constater n’est pas préjuger',
      corps: (
        <>
          Approuver un dossier, c’est constater qu’il est complet et en état
          d’être présenté. Ce n’est ni juger, ni préjuger de son issue. Chaque
          export reste tracé au dossier, avec sa date et son destinataire.
        </>
      ),
    },
  },

  /* --- Administrateur ----------------------------------------------------- */
  platform_admin: {
    accroche:
      'L’exploitation du service : les organisations, les comptes, le corpus.',
    mesures: [
      {
        libelle: 'Organisations ouvertes',
        valeur: '12',
        detail: '3 juridictions · 5 études · 4 entreprises',
        etat: 'verified',
      },
      {
        libelle: 'Comptes en attente',
        valeur: '5',
        detail: 'Qualité à vérifier avant activation',
        etat: 'declared',
      },
      {
        libelle: 'Corpus',
        valeur: '4 087 articles',
        detail: 'Dernier versement : Code de commerce',
        etat: 'verified',
      },
    ],
    titreListe: 'Organisations',
    sousTitreListe:
      'Vous ouvrez et fermez ces espaces. Vous n’accédez pas aux pièces qu’ils contiennent.',
    dossiers: [
      {
        reference: 'Tribunal de commerce de Tunis',
        parties: '4 greffiers rattachés · file active',
        montant: '18 dossiers',
        etat: 'Espace actif',
        etatTon: 'verified',
      },
      {
        reference: 'Étude HJ-TUN-0871',
        parties: '2 huissiers rattachés',
        montant: '6 projets',
        etat: 'Espace actif',
        etatTon: 'verified',
      },
      {
        reference: 'Cabinet Ben Ali — médiation',
        parties: 'Accréditation à revérifier',
        montant: '4 dossiers',
        etat: 'Vérification en attente',
        etatTon: 'declared',
      },
    ],
    titreActions: 'Exploitation',
    actions: [
      { cle: 'manage_tenants' },
      { cle: 'manage_users' },
      { cle: 'manage_corpus' },
      { cle: 'view_all', intitule: 'Consulter l’activité agrégée' },
    ],
    fermees: [
      {
        intitule: 'Ouvrir le dossier d’une entreprise',
        motif:
          'Ouvrir un espace ne donne pas le droit de le lire. Le contenu ' +
          'd’un dossier reste accessible aux seules parties et au ' +
          'professionnel saisi.',
        reservee: 'aux parties et au professionnel saisi',
      },
      {
        intitule: 'Vous accorder une qualité réglementée',
        motif:
          'La qualité d’huissier, de greffier ou d’accrédité se justifie ' +
          'auprès de l’autorité qui la délivre. Elle ne se coche pas.',
        reservee: 'aux autorités d’accréditation',
      },
    ],
    limite: {
      titre: 'Exploiter n’est pas accéder',
      corps: (
        <>
          Vous tenez le service en état de marche : les espaces, les comptes,
          le corpus que le moteur cite. Le secret des dossiers vous reste
          opposable, et le moteur reste déterministe — vous versez des textes,
          vous ne les interprétez pas.
        </>
      ),
    },
  },
};

/* ---------------------------------------------------------------------------
   Le filtre. C'est lui qui fait tenir la promesse de l'écran.
--------------------------------------------------------------------------- */

export type ActionAffichee = {
  cle: ClePermission;
  intitule: string;
  portee: string;
  borne: string;
  fondement?: string;
  exclusif: boolean;
};

/**
 * Les actions d'un rôle, filtrées par la matrice de `lib/auth.ts`.
 *
 * Le filtre n'est pas décoratif : si quelqu'un ajoutait un jour une carte
 * « Signifier l'acte » au tableau de l'entreprise, elle ne s'afficherait pas,
 * parce que `permissions.msme` ne contient pas `issue_formal_notice`. Le
 * contrôle d'accès du serveur et l'écran ne peuvent pas diverger.
 */
export function actionsDuRole(role: Role): ActionAffichee[] {
  const accordees = new Set<string>(permissions[role]);

  return tableaux[role].actions
    .filter((a) => accordees.has(a.cle))
    .map((a) => {
      const p = privileges[a.cle];
      return {
        cle: a.cle,
        intitule: a.intitule ?? p.intitule,
        portee: a.portee ?? p.portee,
        borne: p.borne,
        fondement: p.fondement,
        exclusif: Boolean(p.exclusif),
      };
    });
}
