/**
 * Client de l'API Mizan.
 *
 * Une seule règle gouverne ce fichier : l'interface n'invente rien. Chaque
 * type ci-dessous est recopié de `api/schemas.py`, champ pour champ. Quand
 * l'API ne répond pas, on ne retombe pas sur une valeur par défaut « pour
 * que l'écran soit joli » — on remonte l'échec tel quel, et la page le dit.
 *
 * C'est la raison d'être de `Resultat<T>` : un appel réussit, ou il échoue
 * avec un motif lisible. Il n'y a pas de troisième cas où l'on afficherait
 * une donnée dont on ne sait pas d'où elle vient.
 */

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8820';

// --- /sante -----------------------------------------------------------------

export type EtatHebergement = {
  nom: string;
  base_url: string;
  modele: string;
  disponible: boolean;
  motif: string;
};

export type Sante = {
  service: string;
  version: string;
  moteur_juridique: 'deterministe';
  modele_disponible: boolean;
  motif_modele: string;
  hebergements: EtatHebergement[];
  articles_indexes: number;
  index_charge: boolean;
  principe: string;
};

// --- /dossiers/analyser -----------------------------------------------------

export type Source = {
  code_id: string;
  article: number;
  citation_ar: string;
  label_fr: string;
  short_fr: string;
};

export type Etape = {
  order: number;
  title_fr: string;
  detail_fr: string;
  citation_ar: string;
  code_id: string;
  article: number;
};

/**
 * L'interruption de la prescription (COC art. 396 à 398).
 *
 * Recopié de `api/schemas.py` : `ActeInterruptifEntree`, `InterruptionRetenue`,
 * `ActeSansEffet`, `Interruption`. Rien n'est reformulé ici — les phrases
 * juridiques (`fondement_fr`, `effet_fr`, `motif_fr`, `resume_fr`) sont
 * rédigées par le moteur et affichées mot pour mot. Si l'interface les
 * réécrivait, les deux finiraient par diverger et c'est l'écran qui aurait
 * tort devant un juge.
 */
export type TypeActeInterruptif =
  | 'sommation_huissier'
  | 'demande_justice'
  | 'saisie_conservatoire'
  | 'reconnaissance_dette'
  | 'paiement_partiel'
  | 'arrete_compte';

/** Ce qu'on ENVOIE : un acte invoqué par la PME. */
export type ActeInterruptifEntree = {
  type: TypeActeInterruptif;
  date: string;
  description: string;
};

/** Un acte que le moteur a RETENU : il a réellement interrompu le délai. */
export type InterruptionRetenue = {
  type: string;
  libelle_fr: string;
  date: string;
  description: string;
  /** 396 (acte du créancier) ou 397 (reconnaissance du débiteur). */
  article_cause: number;
  fondement_fr: string;
  effet_fr: string;
  nouvelle_echeance: string;
  articles: Source[];
};

/**
 * Un acte produit mais qui n'a RIEN interrompu, avec son motif.
 *
 * C'est le cas le plus dangereux du dossier : une PME croit son délai
 * relancé alors qu'il ne l'est pas. L'interface ne le masque jamais.
 */
export type ActeSansEffet = {
  type: string;
  libelle_fr: string;
  date: string;
  description: string;
  motif_fr: string;
  articles: Source[];
};

export type Interruption = {
  interrompu: boolean;
  date_depart_initiale: string;
  date_depart_effective: string;
  echeance_initiale: string;
  echeance_effective: string;
  jours_gagnes: number;
  interruptions: InterruptionRetenue[];
  actes_sans_effet: ActeSansEffet[];
  sources: Source[];
  resume_fr: string;
};

export type Analyse = {
  montant_tnd: number;
  date_facture: string;
  aujourdhui: string;
  regime: string;
  regime_reason_fr: string;
  echeance: string;
  jours_restants: number;
  est_prescrit: boolean;
  urgence: string;
  huissier_requis: boolean;
  jours_francs: number;
  sources: Source[];
  etapes: Etape[];
  /**
   * `null` quand aucun acte n'a été transmis : le délai court alors sans
   * interruption depuis la facture. Ce n'est pas une absence de donnée,
   * c'est une information.
   */
  interruption: Interruption | null;
  origine: 'moteur_deterministe';
};

// --- /corpus/rechercher -----------------------------------------------------

export type ArticleTrouve = {
  id: string;
  code_id: string;
  code_fr: string;
  code_ar: string;
  article: number | string;
  citation_ar: string;
  text_ar: string;
  score: number;
};

export type Recherche = {
  requete: string;
  nombre: number;
  fonde: boolean;
  motif_abstention: string | null;
  message: string | null;
  resultats: ArticleTrouve[];
};

// --- /assistant/expliquer ---------------------------------------------------

export type Explication = {
  texte: string;
  origine: 'local' | 'modal' | 'aucune';
  duree_s: number;
  mode_degrade: boolean;
  motif_degradation: string | null;
  analyse: Analyse;
  sources: Source[];
  avertissement: string;
};

// --- Transport --------------------------------------------------------------

/** Pourquoi un appel a échoué. Le genre décide de ce que la page affiche. */
export type EchecApi = {
  /**
   * `injoignable` : l'API n'a pas répondu du tout — elle est éteinte, ou le
   *   port n'est pas celui qu'on croit. C'est un problème d'exploitation.
   * `refus` : l'API a répondu, et elle a refusé la demande (400/422). Le
   *   motif vient du moteur et il est déjà rédigé pour un non-juriste : on
   *   l'affiche mot pour mot.
   * `panne` : l'API a répondu autre chose (500, 503…).
   */
  genre: 'injoignable' | 'refus' | 'panne';
  message: string;
  /** Code HTTP quand il y en a un. Absent si le serveur n'a jamais répondu. */
  statut?: number;
  /** L'URL appelée : sans elle, on debug à l'aveugle pendant une démo. */
  url: string;
};

export type Resultat<T> =
  | { ok: true; valeur: T }
  | { ok: false; echec: EchecApi };

/**
 * Extrait le motif d'un refus FastAPI.
 *
 * FastAPI renvoie `{"detail": "..."}` pour nos HTTPException, mais
 * `{"detail": [{...}]}` pour une erreur de validation Pydantic. Les deux
 * arrivent en démonstration ; on les traduit tous les deux plutôt que
 * d'afficher du JSON brut à un jury.
 */
function motifDuRefus(corps: unknown, statut: number): string {
  if (typeof corps === 'object' && corps !== null && 'detail' in corps) {
    const detail = (corps as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      const lignes = detail
        .map((e) => {
          if (typeof e !== 'object' || e === null) return null;
          const err = e as { loc?: unknown[]; msg?: string };
          const champ = Array.isArray(err.loc)
            ? err.loc.filter((p) => p !== 'body').join('.')
            : '';
          return champ ? `« ${champ} » : ${err.msg}` : (err.msg ?? null);
        })
        .filter((l): l is string => Boolean(l));
      if (lignes.length) return lignes.join(' ; ');
    }
  }
  return `L'API a répondu ${statut} sans motif exploitable.`;
}

type Options = {
  methode?: 'GET' | 'POST';
  corps?: unknown;
  /**
   * Au-delà, on rend la main. Sans borne, une page reste blanche pendant que
   * le jury regarde. L'explication passe par un modèle : elle a droit à plus.
   */
  delaiMs?: number;
};

async function appeler<T>(
  chemin: string,
  options: Options = {},
): Promise<Resultat<T>> {
  const { methode = 'GET', corps, delaiMs = 15000 } = options;
  const url = `${API_URL}${chemin}`;
  const minuteur = AbortSignal.timeout(delaiMs);

  let reponse: Response;
  try {
    reponse = await fetch(url, {
      method: methode,
      headers: corps ? { 'Content-Type': 'application/json' } : undefined,
      body: corps ? JSON.stringify(corps) : undefined,
      // Le droit change, l'index se reconstruit : on ne sert jamais de cache.
      // Un chiffre juridique périmé affiché avec aplomb, c'est exactement ce
      // que ce projet refuse.
      cache: 'no-store',
      signal: minuteur,
    });
  } catch (erreur) {
    const cause = erreur instanceof Error ? erreur.message : String(erreur);
    const expire =
      erreur instanceof Error &&
      (erreur.name === 'TimeoutError' || erreur.name === 'AbortError');
    return {
      ok: false,
      echec: {
        genre: 'injoignable',
        url,
        message: expire
          ? `L'API n'a pas répondu en moins de ${Math.round(delaiMs / 1000)} s.`
          : `L'API est injoignable (${cause}).`,
      },
    };
  }

  if (!reponse.ok) {
    let corpsErreur: unknown = null;
    try {
      corpsErreur = await reponse.json();
    } catch {
      // Une erreur non-JSON : on garde le code, c'est déjà une information.
    }
    const refus = reponse.status === 400 || reponse.status === 422;
    return {
      ok: false,
      echec: {
        genre: refus ? 'refus' : 'panne',
        statut: reponse.status,
        url,
        message: motifDuRefus(corpsErreur, reponse.status),
      },
    };
  }

  try {
    return { ok: true, valeur: (await reponse.json()) as T };
  } catch (erreur) {
    return {
      ok: false,
      echec: {
        genre: 'panne',
        statut: reponse.status,
        url,
        message: `Réponse illisible : ${
          erreur instanceof Error ? erreur.message : String(erreur)
        }`,
      },
    };
  }
}

// --- Les quatre appels utilisés par l'interface -----------------------------

export function lireSante(): Promise<Resultat<Sante>> {
  // L'état du service doit répondre vite ou pas du tout.
  return appeler<Sante>('/sante', { delaiMs: 6000 });
}

export function analyserDossier(demande: {
  montant_tnd: number;
  date_facture: string;
  activite: string;
  /**
   * Omis quand la liste est vide : on envoie au moteur exactement ce que la
   * PME a déclaré, pas un tableau vide qui laisserait croire à une saisie.
   */
  actes_interruptifs?: ActeInterruptifEntree[];
}): Promise<Resultat<Analyse>> {
  return appeler<Analyse>('/dossiers/analyser', {
    methode: 'POST',
    corps: demande,
  });
}

export function rechercherCorpus(
  q: string,
  k = 5,
): Promise<Resultat<Recherche>> {
  const params = new URLSearchParams({ q, k: String(k) });
  return appeler<Recherche>(`/corpus/rechercher?${params}`);
}

export function demanderExplication(demande: {
  montant_tnd: number;
  date_facture: string;
  activite: string;
}): Promise<Resultat<Explication>> {
  // Celui-ci traverse un modèle de langage. Sur un GPU partagé, 15 s ne
  // suffisent pas ; l'API bascule elle-même en mode dégradé si le modèle
  // ne répond pas, donc attendre ici est sans risque.
  return appeler<Explication>('/assistant/expliquer', {
    methode: 'POST',
    corps: demande,
    delaiMs: 90000,
  });
}
