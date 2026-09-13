/**
 * La session de l'agent : où le jeton est rangé, et par qui.
 *
 * CE QUI EXISTAIT AVANT CE FICHIER — et qu'il faut savoir avant de lire la
 * suite. L'écran `/connexion` appelle bien `POST /comptes/connexion`, mais il
 * ne conserve RIEN de ce que le serveur lui répond : le jeton signé est reçu
 * puis jeté, et l'écran redirige vers `/espace` — qui n'a besoin d'aucun
 * serveur pour s'afficher. Il n'existait donc, au moment d'écrire la bulle,
 * aucune convention de stockage à réutiliser. On n'en invente pas une
 * deuxième : on pose la première, sous un nom que tout l'écran pourra
 * partager le jour où `/connexion` conservera sa session.
 *
 * Le choix de `localStorage` plutôt que d'un cookie tient à une contrainte de
 * la démonstration : l'API est servie depuis un autre port que l'interface.
 * Un cookie posé par le navigateur sur `:3000` ne repartirait pas vers
 * `:8820`, et l'en-tête « Authorization » attendue par le garde d'accès doit
 * de toute façon être écrite à la main par le code appelant.
 *
 * Rien de confidentiel n'est recopié ici : ni mot de passe, ni empreinte. Le
 * jeton est signé côté serveur et expire ; le nom d'organisation et le rôle
 * ne sont conservés que pour pouvoir afficher l'en-tête de la bulle avant
 * même la première réponse.
 */

const CLE = 'mizan.session';

export type SessionMizan = {
  /** Le jeton signé, à renvoyer dans « Authorization: Bearer *** ». */
  jeton: string;
  /** Le nom lisible de l'organisation. Affiché en permanence dans la bulle. */
  nomOrganisation: string;
  /** Le libellé français du rôle (« Entreprise », « Huissier de justice »…). */
  libelleRole: string;
  /** L'identifiant technique du rôle. N'est JAMAIS affiché tel quel. */
  role: string;
  /** Horodatage (ms) au-delà duquel le jeton est périmé côté serveur. */
  expireLe: number;
};

/**
 * Lit la session en cours, ou `null`.
 *
 * Toute anomalie — stockage inaccessible, JSON illisible, jeton expiré — rend
 * `null` plutôt que de lever. Une bulle qui plante au chargement parce que le
 * navigateur refuse le stockage local coûterait la démonstration entière ;
 * une bulle qui dit « vous n'êtes pas connecté » ne coûte rien.
 */
export function lireSession(): SessionMizan | null {
  if (typeof window === 'undefined') return null;

  let brut: string | null = null;
  try {
    brut = window.localStorage.getItem(CLE);
  } catch {
    // Navigation privée, cookies bloqués, iframe cloisonnée : on fait comme
    // si personne n'était connecté. C'est vrai, du point de vue de l'écran.
    return null;
  }
  if (!brut) return null;

  try {
    const lu = JSON.parse(brut) as Partial<SessionMizan>;
    if (typeof lu.jeton !== 'string' || !lu.jeton) return null;
    if (typeof lu.expireLe === 'number' && lu.expireLe < Date.now()) {
      // Périmée : on la retire, sinon la bulle réessaierait indéfiniment un
      // jeton que le serveur refuse déjà.
      oublierSession();
      return null;
    }
    return {
      jeton: lu.jeton,
      nomOrganisation: String(lu.nomOrganisation ?? ''),
      libelleRole: String(lu.libelleRole ?? ''),
      role: String(lu.role ?? ''),
      expireLe: Number(lu.expireLe ?? 0),
    };
  } catch {
    return null;
  }
}

export function enregistrerSession(session: SessionMizan): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(CLE, JSON.stringify(session));
  } catch {
    // Le stockage a refusé. La session reste valable pour l'onglet en cours
    // — elle vit en mémoire dans le composant — elle ne survivra simplement
    // pas au rechargement. Silencieux volontairement : l'utilisateur n'a
    // aucune action à entreprendre.
  }
}

export function oublierSession(): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(CLE);
  } catch {
    /* voir ci-dessus */
  }
}

/**
 * Ce que renvoie `POST /comptes/connexion`, réduit à ce dont la bulle a besoin.
 * Recopié de `api/comptes.py` : `ConnexionFaite` et `CompteRendu`.
 */
type ConnexionFaite = {
  jeton: string;
  expire_dans_secondes: number;
  compte: {
    nom_organisation: string;
    organisation: string;
    role: string;
    role_libelle: string;
  };
};

export function sessionDepuisConnexion(
  reponse: ConnexionFaite,
): SessionMizan {
  const duree = Number(reponse.expire_dans_secondes) || 0;
  return {
    jeton: reponse.jeton,
    nomOrganisation:
      reponse.compte?.nom_organisation || reponse.compte?.organisation || '',
    libelleRole: reponse.compte?.role_libelle || '',
    role: reponse.compte?.role || '',
    expireLe: duree > 0 ? Date.now() + duree * 1000 : 0,
  };
}
