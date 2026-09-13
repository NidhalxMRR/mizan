/**
 * Ce que chaque rôle a le droit de faire, écrit pour un juriste.
 *
 * `lib/auth.ts` définit la matrice des permissions sous forme de clés
 * techniques : `issue_formal_notice`, `open_ecma`, `approve_dossier`. Ces
 * clés sont justes, mais elles sont illisibles — et le jury de Hack4Justice
 * est composé de juristes, pas de développeurs. Aucune ne doit atteindre
 * l'écran.
 *
 * Ce fichier est le dictionnaire entre les deux. Il ne redéfinit RIEN : il
 * lit `permissions` depuis `lib/auth.ts` et se contente de donner à chaque
 * clé une phrase française, la borne juridique qui va avec, et l'article qui
 * la fonde quand il en existe un.
 *
 * Trois garde-fous, dans cet ordre d'importance :
 *
 * 1. Le dictionnaire est VÉRIFIÉ PAR LE COMPILATEUR. `Record<ClePermission,
 *    Privilege>` échoue à compiler si une permission est ajoutée à
 *    `lib/auth.ts` sans sa traduction. On ne peut donc pas livrer un écran
 *    qui affiche une clé en anglais faute d'avoir pensé à la traduire.
 * 2. Les privilèges sont LUS depuis la matrice, jamais recopiés. Si la
 *    matrice change, les écrans changent. Une liste recopiée à la main aurait
 *    fini par mentir sur ce que le rôle peut réellement faire.
 * 3. Chaque privilège porte sa BORNE : ce que le rôle ne peut pas faire tient
 *    autant de place que ce qu'il peut. C'est la thèse du projet — la
 *    plateforme prépare, elle ne signifie pas — et elle ne se démontre qu'en
 *    l'écrivant à côté du pouvoir correspondant.
 */

import { permissions, roles, roleLabels, type Role } from '@/lib/auth';

/**
 * Sur les mots arabes qui apparaissent dans les phrases de ce fichier.
 *
 * Règle de rédaction : une phrase française visible doit se tenir debout toute
 * seule. Le terme arabe ne porte jamais la syntaxe — il vient en apposition,
 * entre parenthèses, après le mot français. « Le monopole appartient au عدل
 * منفذ » fait buter un lecteur francophone et paraît négligé devant un jury ;
 * « appartient à l'huissier de justice (عدل منفذ) » se lit d'un trait.
 *
 * Sur les deux caractères invisibles qui encadrent chaque mot arabe plus bas,
 * U+2068 et U+2069 : ce sont les isolateurs bidirectionnels d'Unicode. Ils
 * font dans une chaîne de texte ce que `unicode-bidi: isolate` fait dans une
 * feuille de style — et il en faut, car ces valeurs sont des CHAÎNES et non du
 * JSX : on ne peut pas les envelopper dans un `<span className="incise-ar">`.
 * Sans eux, l'algorithme bidi rattache la parenthèse fermante au segment arabe
 * et la renvoie de l'autre côté : on lit « (عدل منفذ( » au lieu de
 * « (عدل منفذ) ». À vérifier sur capture, pas au jugé.
 */

/** Toutes les clés de permission qui existent, tous rôles confondus. */
export type ClePermission = (typeof permissions)[Role][number];

export type Privilege = {
  /** La phrase affichée. Pas de verbe technique, pas d'anglais. */
  intitule: string;
  /** Ce que ce pouvoir autorise concrètement, en une phrase. */
  portee: string;
  /**
   * La limite. Rédigée du point de vue de l'utilisateur : « vous ne pouvez
   * pas… », parce qu'un privilège sans sa borne se lit comme une promesse.
   */
  borne: string;
  /** L'article qui fonde ou borne le pouvoir. Absent quand il n'y en a pas. */
  fondement?: string;
  /**
   * Vrai quand ce pouvoir n'appartient à AUCUN autre rôle. C'est ce qui rend
   * le choix du rôle irréversible pour l'utilisateur, donc ce qui doit être
   * signalé à l'écran avant qu'il valide.
   */
  exclusif?: boolean;
};

/**
 * Le dictionnaire. L'ordre des entrées n'a pas d'importance ici : c'est
 * l'ordre de la matrice dans `lib/auth.ts` qui détermine l'affichage, et cet
 * ordre-là a été choisi pour raconter le métier du plus courant au plus rare.
 */
export const privileges: Record<ClePermission, Privilege> = {
  // --- Administrateur -------------------------------------------------------
  manage_tenants: {
    intitule: 'Ouvrir et fermer les organisations',
    portee:
      "Créer l'espace d'un tribunal, d'un cabinet ou d'une entreprise, et " +
      'le refermer quand la convention prend fin.',
    borne:
      "Vous n'accédez pas aux pièces déposées dans ces espaces : ouvrir un " +
      'espace ne donne pas le droit de le lire.',
    exclusif: true,
  },
  manage_users: {
    intitule: 'Créer les comptes et accorder les rôles',
    portee:
      "Rattacher une personne à son organisation et lui donner le rôle qui " +
      'correspond à sa qualité réelle.',
    borne:
      "Vous ne pouvez pas vous accorder à vous-même un pouvoir réservé à une " +
      'profession réglementée — la qualité se justifie, elle ne se coche pas.',
    exclusif: true,
  },
  view_all: {
    intitule: "Consulter l'activité de la plateforme",
    portee:
      "Voir les volumes, les délais moyens, les dossiers en souffrance — le " +
      'fonctionnement du service.',
    borne:
      "Cette vue est agrégée. Le contenu d'un dossier reste accessible aux " +
      'seules parties et au professionnel saisi.',
  },
  manage_corpus: {
    intitule: 'Tenir le corpus juridique à jour',
    portee:
      'Verser un code, une loi ou un décret nouveau, et retirer un texte ' +
      'abrogé pour que le moteur cesse de le citer.',
    borne:
      "Vous versez des textes ; vous ne les interprétez pas. Le moteur reste " +
      'déterministe et cite ce qui est versé, mot pour mot.',
    exclusif: true,
  },

  // --- Entreprise -----------------------------------------------------------
  upload_evidence: {
    intitule: 'Déposer vos pièces',
    portee:
      'Verser au dossier vos factures, bons de livraison et contrats. ' +
      "Chaque pièce reçoit une empreinte numérique à l'instant du dépôt.",
    borne:
      "Une pièce déposée ne peut plus être retirée sans laisser trace : " +
      "c'est ce qui lui donne sa valeur probante.",
  },
  view_own_case: {
    intitule: 'Suivre vos dossiers',
    portee:
      "Consulter à tout moment l'état de vos litiges, le délai de " +
      'prescription qui court, et les actes déjà accomplis.',
    borne:
      'Vos dossiers, et eux seuls. Aucun accès aux dossiers des autres ' +
      'entreprises, même de votre secteur.',
  },
  request_notice: {
    intitule: 'Demander une mise en demeure',
    portee:
      "Faire préparer le projet d'acte : parties identifiées, montant " +
      'calculé, articles cités et relus.',
    borne:
      "Demander n'est pas signifier. Le projet part chez un huissier de " +
      'justice, seul habilité à le signifier à votre débiteur.',
    fondement: 'Code de procédure civile et commerciale, art. 5 et 60',
  },
  open_ecma: {
    intitule: 'Ouvrir une conciliation ou une médiation',
    portee:
      "Saisir la voie amiable avant le tribunal, en ligne, avec un " +
      'professionnel accrédité.',
    borne:
      "L'ouverture ne suspend pas la prescription à elle seule. Le délai " +
      'continue de courir tant que le compte à rebours ne le dit pas.',
  },
  accept_settlement: {
    intitule: 'Accepter un accord transactionnel',
    portee:
      'Donner votre consentement à un projet de règlement amiable ' +
      '(\u2068صلح\u2069) rédigé par le professionnel qui conduit la ' +
      'conciliation.',
    borne:
      "Votre acceptation vous engage. Une transation régulièrement conclue " +
      "a, entre les parties, l'autorité de la chose jugée.",
    fondement: 'Code des obligations et des contrats, art. 1458',
  },
  choose_professional: {
    intitule: 'Choisir votre professionnel',
    portee:
      'Retenir vous-même le médiateur, le conciliateur ou l’arbitre ' +
      'accrédité qui conduira la procédure.',
    borne:
      "Vous choisissez parmi les professionnels accrédités : la plateforme " +
      "ne vous en impose aucun, et n'en invente aucun.",
  },

  // --- Avocat ---------------------------------------------------------------
  represent_client: {
    intitule: 'Représenter votre client en justice',
    portee:
      'Agir au nom de votre client devant la juridiction saisie : porter ' +
      'ses prétentions, répondre à celles de la partie adverse, et le ' +
      'dispenser de comparaître lui-même.',
    borne:
      'Vous représentez celui qui vous a donné mandat, et lui seul. Le ' +
      'mandat se justifie ; il ne se déclare pas à l’écran.',
    fondement:
      'Code des droits et procédures fiscaux, art. 57 — la représentation ' +
      'est obligatoire au-delà de 25 000 dinars',
    exclusif: true,
  },
  draft_pleading: {
    intitule: 'Rédiger la requête et les mémoires',
    portee:
      'Établir l’écriture qui sera déposée : les faits, les moyens, et les ' +
      'articles du corpus qui les fondent, cités mot pour mot.',
    borne:
      'Mizan prépare la matière et cite les textes ; elle ne choisit ni vos ' +
      'moyens ni votre stratégie. L’argumentation reste la vôtre.',
  },
  sign_pleading: {
    intitule: 'Signer la requête et les mémoires',
    portee:
      'Apposer votre signature d’avocat sur l’écriture : c’est elle qui la ' +
      'rend recevable devant la cour d’appel et devant la cassation.',
    borne:
      'Votre signature engage votre responsabilité professionnelle. Un ' +
      'mémoire non signé par un avocat n’est pas recevable devant ces ' +
      'juridictions — et aucune autre qualité ne peut y suppléer.',
    fondement: 'Code des droits et procédures fiscaux, art. 35 et 19',
    exclusif: true,
  },

  // --- Professionnel accrédité ---------------------------------------------
  view_assigned_case: {
    intitule: 'Accéder aux dossiers qui vous sont confiés',
    portee:
      "Ouvrir l'entier dossier — pièces, échanges, calculs de délai — dès " +
      'que les parties vous ont retenu.',
    borne:
      "Les dossiers où vous n'êtes pas saisi vous restent fermés. Il n'y a " +
      'pas de vue générale pour un professionnel.',
  },
  conduct_ecma: {
    intitule: 'Conduire la conciliation ou la médiation',
    portee:
      'Convoquer les parties, mener les séances, consigner les positions ' +
      "de chacune à chaque étape.",
    borne:
      "Vous conduisez, vous ne tranchez pas : votre office est d'amener les " +
      'parties à un accord, non de leur imposer une solution.',
    exclusif: true,
  },
  draft_settlement: {
    intitule: "Rédiger le procès-verbal d'accord",
    portee:
      "Établir le projet de transaction reprenant ce que les parties ont " +
      'accepté, avec les articles qui le fondent.',
    borne:
      "Le projet n'a aucun effet tant que les deux parties ne l'ont pas " +
      'accepté. Rédiger ne vaut pas conclure.',
  },
  sign_settlement: {
    intitule: "Signer le procès-verbal de conciliation",
    portee:
      "Apposer votre signature d'accrédité sur le procès-verbal, ce qui " +
      'lui donne sa date et son authenticité.',
    borne:
      "Vous signez en qualité d'accrédité : votre signature atteste de ce " +
      'qui a été convenu devant vous, pas de la véracité des pièces.',
    exclusif: true,
  },
  request_missing_piece: {
    intitule: 'Réclamer une pièce manquante',
    portee:
      "Demander à une partie le document qui manque pour que le dossier " +
      'soit complet, avec le motif de la demande.',
    borne:
      "Vous demandez ; vous ne contraignez pas. Le refus d'une partie se " +
      'consigne, il ne se sanctionne pas ici.',
  },

  // --- Greffier -------------------------------------------------------------
  view_queue: {
    intitule: "Tenir la file d'attente du greffe",
    portee:
      'Voir les dossiers en instance de votre tribunal, classés par ' +
      "ancienneté et par urgence de prescription.",
    borne:
      'La file est celle de votre juridiction. Les dossiers relevant ' +
      "d'un autre tribunal ne vous sont pas présentés.",
    exclusif: true,
  },
  review_evidence: {
    intitule: 'Examiner les pièces produites',
    portee:
      "Vérifier que les pièces annoncées sont bien au dossier, lisibles, " +
      'et que leurs empreintes sont intactes.',
    borne:
      "Votre examen porte sur la régularité formelle, non sur le fond : " +
      "l'appréciation de la preuve appartient au juge.",
  },
  approve_dossier: {
    intitule: 'Approuver un dossier pour audience',
    portee:
      "Déclarer un dossier complet et en état d'être présenté, ou le " +
      'renvoyer à la partie avec le motif précis du renvoi.',
    borne:
      "Approuver, c'est constater que le dossier est complet. Ce n'est ni " +
      'juger, ni préjuger de son issue.',
    exclusif: true,
  },
  schedule_mediation: {
    intitule: 'Fixer une date de médiation',
    portee:
      "Inscrire la séance au calendrier de la juridiction et en aviser les " +
      'parties et le professionnel saisi.',
    borne:
      "La date se fixe dans les disponibilités réelles de la juridiction : " +
      'la plateforme ne crée pas de créneau qui n’existe pas.',
    exclusif: true,
  },
  export_dossier: {
    intitule: 'Exporter le dossier pour la juridiction',
    portee:
      "Produire le dossier complet, pièces et procès-verbaux, dans le " +
      'format attendu par le tribunal.',
    borne:
      "L'export est tracé : la date, l'heure et le destinataire restent au " +
      'dossier.',
    exclusif: true,
  },

  // --- Huissier de justice --------------------------------------------------
  view_notice_request: {
    intitule: 'Recevoir les demandes de signification',
    portee:
      "Consulter les projets de mise en demeure préparés par les " +
      'entreprises, avec leurs pièces et le calcul du délai.',
    borne:
      "Un projet reçu n'est pas un acte accepté : vous restez libre de le " +
      'refuser ou de le faire corriger avant toute signification.',
    // Le même article que les deux autres pouvoirs de l'huissier : c'est de
    // son ministère que découle le droit de recevoir ces projets. Sans lui,
    // la troisième carte du tableau de bord avait un pied vide là où ses
    // voisines portent une citation — relevé sur capture à 1280 px.
    fondement: 'Code de procédure civile et commerciale, art. 5',
    exclusif: true,
  },
  issue_formal_notice: {
    intitule: 'Signifier la mise en demeure',
    portee:
      "Vous seul en avez le pouvoir. Toute citation, notification ou " +
      'exécution passe par votre ministère.',
    borne:
      'Au-delà de 150 dinars, la mise en demeure (\u2068إنذار\u2069) doit ' +
      'être signifiée par votre intermédiaire, cinq jours francs avant toute ' +
      "saisine. La plateforme prépare l'acte ; elle ne le signifie jamais.",
    fondement: 'Code de procédure civile et commerciale, art. 5 et 60',
    exclusif: true,
  },
  record_service: {
    intitule: 'Consigner la date de signification',
    portee:
      "Porter au dossier la date et les modalités exactes de la " +
      "signification : c'est elle qui fait courir les cinq jours francs.",
    borne:
      "La date consignée engage votre responsabilité professionnelle. Elle " +
      'ne peut être corrigée que par une mention rectificative datée.',
    fondement: 'Code de procédure civile et commerciale, art. 60',
    exclusif: true,
  },
};

/**
 * Les privilèges d'un rôle, dans l'ordre de la matrice.
 *
 * On passe par `permissions[role]` plutôt que par une liste recopiée : c'est
 * le seul moyen de garantir que l'écran d'inscription montre exactement ce
 * que `can()` accordera ensuite. Promettre à l'inscription un pouvoir que le
 * contrôle d'accès refuserait serait pire qu'un écran laid.
 */
export function privilegesDuRole(role: Role): Privilege[] {
  return permissions[role].map((cle) => privileges[cle as ClePermission]);
}

/** Un rôle et sa présentation, pour les cartes de choix. */
export type FicheRole = {
  role: Role;
  /** À qui s'adresse ce rôle, en une phrase. Aide au choix. */
  destinataire: string;
  /** Ce que la personne vient faire ici. */
  promesse: string;
  /**
   * La pièce ou la qualité qui sera vérifiée. Écrit avant la validation,
   * pour qu'on ne découvre pas la contrainte après avoir rempli le formulaire.
   */
  justificatif: string;
  /** Champ d'identification propre au rôle, demandé dans le formulaire. */
  champIdentite: { libelle: string; exemple: string; aide: string };
};

export const fiches: Record<Role, FicheRole> = {
  msme: {
    role: 'msme',
    destinataire:
      'Vous dirigez une entreprise et un client ne vous a pas payé.',
    promesse:
      'Savoir quel délai court, ce qui reste possible, et par où commencer.',
    justificatif:
      "Votre identifiant unique d'entreprise sera vérifié au Registre " +
      'national des entreprises.',
    champIdentite: {
      libelle: "Identifiant unique de l'entreprise",
      exemple: '1234567 A/P/M/000',
      aide: 'Celui qui figure sur votre patente et vos factures.',
    },
  },
  avocat: {
    role: 'avocat',
    destinataire:
      'Vous êtes avocat (\u2068محام\u2069), inscrit au barreau, et vous ' +
      'défendez une entreprise.',
    promesse:
      'Recevoir le dossier que votre client vous confie, avec ses délais ' +
      'calculés et ses textes cités, et porter ses écritures.',
    justificatif:
      'Votre inscription à l’Ordre national des avocats de Tunisie sera ' +
      'vérifiée.',
    champIdentite: {
      libelle: 'Numéro d’inscription au barreau',
      exemple: 'AV-TUN-1204',
      aide:
        'Avec la section où vous êtes inscrit, et la mention « cassation » ' +
        'ou « appel » si vous en relevez.',
    },
  },
  accredited_pro: {
    role: 'accredited_pro',
    destinataire:
      'Vous êtes médiateur, conciliateur ou arbitre accrédité.',
    promesse:
      'Recevoir les dossiers où les parties vous retiennent, et les conduire.',
    justificatif:
      'Votre numéro d’accréditation sera vérifié auprès de l’autorité qui ' +
      "l'a délivrée.",
    champIdentite: {
      libelle: "Numéro d'accréditation",
      exemple: 'MED-2024-0142',
      aide: "Tel qu'il figure sur votre décision d'agrément.",
    },
  },
  huissier: {
    role: 'huissier',
    destinataire:
      'Vous êtes huissier de justice (\u2068عدل منفذ\u2069) en exercice.',
    promesse:
      'Recevoir des projets de mise en demeure déjà complets, à contrôler ' +
      'et à signifier.',
    justificatif:
      'Votre inscription à la Chambre nationale des huissiers de justice ' +
      'sera vérifiée.',
    champIdentite: {
      libelle: "Numéro d'inscription à la Chambre",
      exemple: 'HJ-TUN-0871',
      aide: 'Avec la circonscription où vous instrumentez.',
    },
  },
  court_clerk: {
    role: 'court_clerk',
    destinataire: 'Vous êtes greffier auprès d’un tribunal de commerce.',
    promesse:
      "Recevoir des dossiers complets plutôt que des dossiers à compléter.",
    justificatif:
      'Votre affectation sera confirmée par le chef de greffe de votre ' +
      'juridiction.',
    champIdentite: {
      libelle: 'Matricule et juridiction',
      exemple: 'GRF-0219 · Tribunal de commerce de Tunis',
      aide: 'La juridiction détermine la file d’attente que vous verrez.',
    },
  },
  platform_admin: {
    role: 'platform_admin',
    destinataire:
      'Vous exploitez la plateforme pour le compte de l’institution.',
    promesse:
      'Ouvrir les espaces, accorder les rôles, tenir le corpus à jour.',
    justificatif:
      'Ce rôle ne s’obtient pas par inscription : il est accordé par un ' +
      'administrateur déjà en fonction.',
    champIdentite: {
      libelle: 'Code d’habilitation',
      exemple: 'Remis par l’administrateur en fonction',
      aide: 'Sans ce code, la demande est mise en attente de validation.',
    },
  },
};

/**
 * L'ordre d'affichage des rôles à l'inscription.
 *
 * Ce n'est PAS l'ordre de `roles` dans `lib/auth.ts`, qui commence par
 * l'administrateur — un rôle d'exploitation, que personne ne vient choisir
 * spontanément. Ici on ouvre par l'entreprise, parce que c'est elle que le
 * jury doit voir en premier : c'est la PME en litige que le challenge
 * cherche à servir. L'administrateur ferme la liste.
 */
export const ordreInscription: Role[] = [
  'msme',
  'avocat',
  'accredited_pro',
  'huissier',
  'court_clerk',
  'platform_admin',
];

// Garde-fou de cohérence : si un rôle est ajouté à `lib/auth.ts` sans être
// placé dans l'ordre ci-dessus, il disparaîtrait silencieusement de l'écran
// d'inscription. Cette ligne ne s'exécute qu'au chargement du module et ne
// coûte rien, mais elle rend l'oubli visible immédiatement.
if (ordreInscription.length !== roles.length) {
  throw new Error(
    "Ordre d'inscription incomplet : un rôle défini dans lib/auth.ts " +
      "n'apparaîtrait pas à l'écran.",
  );
}

/**
 * Le nom du rôle précédé de « de », avec l'élision.
 *
 * Écrire `de ${roleLabels[role].toLowerCase()}` produisait « en qualité de
 * entreprise » et « de administrateur » — relevé sur une capture d'écran
 * réelle. Devant un jury de juristes tunisiens, une faute d'élision dans le
 * titre d'un formulaire coûte plus cher qu'un défaut d'alignement : elle
 * signale que personne n'a relu l'écran en français.
 *
 * On teste la voyelle plutôt que de tenir une table par rôle : la règle vaut
 * pour tout libellé futur, et le « h » d'« huissier » est muet, donc il
 * s'élide lui aussi.
 */
export function deRole(role: Role): string {
  const nom = roleLabels[role].toLowerCase();
  const elide = /^[aeiouyâàéèêëîïôöûü]/.test(nom) || nom.startsWith('h');
  return elide ? `d’${nom}` : `de ${nom}`;
}
