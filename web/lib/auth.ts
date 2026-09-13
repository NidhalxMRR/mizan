/**
 * Rôles et permissions — Mizan
 *
 * Transposé du modèle de Pharmalink (Omar) : une matrice explicite plutôt que
 * des vérifications éparpillées dans les composants. `can()` est la seule
 * porte d'entrée, ce qui la rend testable.
 *
 * Les acteurs viennent du brief Challenge B §4, qui nomme explicitement :
 *   « a Commercial Court Clerk, Official Mediator, Arbitrator,
 *     or RNE Dispute Officer »
 * et du droit tunisien, qui en ajoute un que le brief ne nomme pas.
 */

export const roles = [
  'platform_admin',   // exploitation de la plateforme
  'msme',             // la PME : dépose, consulte, accepte
  'avocat',           // محام — voir la note ci-dessous
  'accredited_pro',   // médiateur · conciliateur · arbitre agréé
  'court_clerk',      // greffier du tribunal de commerce
  'huissier',         // عدل منفذ — voir la note ci-dessous
] as const;

export type Role = (typeof roles)[number];

/**
 * Sur le عدل منفذ (huissier de justice).
 *
 * CPC art. 5  : toute citation, notification ou exécution passe par lui.
 * CPC art. 60 : au-delà de 150 DT, l'إنذار doit être signifié par son
 *               intermédiaire, cinq jours francs avant saisine.
 *
 * C'est un monopole légal : la plateforme ne peut pas signifier un acte.
 * Mais elle peut lui livrer un projet complet — parties identifiées, montant
 * calculé, articles cités et relus — qu'il n'a plus qu'à contrôler et
 * signifier. Le brief §4 demande de « generate » la mise en demeure ;
 * générer n'est pas signifier. Le document ne disparaît donc pas : il change
 * de destinataire, et `issue_formal_notice` n'appartient qu'à lui.
 */

/**
 * Sur le محام (avocat).
 *
 * CDPF art. 57 : « تكون إنابة المحامي وجوبية إذا تجاوز مبلغ الأداء الموظف
 *                 إجباريا أو المبلغ المطلوب استرجاعه خمسة وعشرين ألف دينار »
 *                — au-delà de 25 000 dinars, la représentation par avocat
 *                n'est pas une faculté : elle est obligatoire.
 * CDPF art. 35 : la requête et les mémoires en réponse sont signés par un
 *                avocat auprès de la cassation ou de l'appel.
 * CDPF art. 19 : la saisine des chambres d'appel se fait par voie d'avocat.
 *
 * L'avocat n'est donc ni le tiers neutre qu'est le professionnel accrédité —
 * il défend une partie, il ne concilie pas les deux — ni l'officier
 * ministériel qu'est l'huissier : il ne signifie rien. Sa matrice ne recopie
 * aucune des deux. Ce qu'il apporte et que personne d'autre n'a, c'est la
 * représentation en justice et la signature des écritures.
 */

export const permissions = {
  platform_admin: [
    'manage_tenants', 'manage_users', 'view_all', 'manage_corpus',
  ],
  msme: [
    'upload_evidence',      // brief §4.1 — contrats, bons, factures
    'view_own_case',
    'request_notice',       // demande le projet d'acte ; ne le signifie pas
    'open_ecma',            // ouvre une conciliation/médiation
    'accept_settlement',    // accepte un projet de صلح (COC art. 1458)
    'choose_professional',
  ],
  avocat: [
    'view_assigned_case',   // le dossier que son client lui confie
    'represent_client',     // CDPF art. 57 — obligatoire au-delà de 25 000 DT
    'draft_pleading',
    'sign_pleading',        // CDPF art. 35 — la signature, pas la rédaction
    'request_missing_piece',
  ],
  accredited_pro: [
    'view_assigned_case',
    'conduct_ecma',
    'draft_settlement',
    'sign_settlement',      // PV de conciliation — brief §6
    'request_missing_piece',
  ],
  court_clerk: [
    'view_queue',           // brief §4 — module institutionnel obligatoire
    'review_evidence',
    'approve_dossier',
    'schedule_mediation',
    'export_dossier',
  ],
  huissier: [
    'view_notice_request',
    'issue_formal_notice',  // le seul à pouvoir signifier — CPC art. 5 et 60
    'record_service',       // consigne la date de signification
  ],
} satisfies Record<Role, string[]>;

export type Permission = (typeof permissions)[Role][number];

export function can(role: Role, permission: string): boolean {
  return permissions[role]?.includes(permission) ?? false;
}

/** Libellés affichés. L'interface est en français. */
export const roleLabels: Record<Role, string> = {
  platform_admin: 'Administrateur',
  msme: 'Entreprise',
  avocat: 'Avocat',
  accredited_pro: 'Professionnel accrédité',
  court_clerk: 'Greffier',
  huissier: 'Huissier de justice',
};

/** Le même, en arabe : ces acteurs portent un nom officiel dans le corpus. */
export const roleLabelsAr: Record<Role, string> = {
  platform_admin: 'مدير المنصة',
  msme: 'المؤسسة',
  avocat: 'محام',
  accredited_pro: 'الوسيط المعتمد',
  court_clerk: 'كاتب المحكمة',
  huissier: 'عدل منفذ',
};
