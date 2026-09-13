/**
 * Ce que l'agent répond, recopié champ pour champ de `ReponseAgent.to_dict()`
 * dans `packages/agent/cerveau.py`. La même règle que `lib/api.ts` gouverne
 * ce fichier : l'interface n'invente rien, et quand l'appel échoue on remonte
 * l'échec tel quel plutôt que d'afficher une valeur par défaut « pour que
 * l'écran soit joli ».
 */

import { API_URL } from '@/lib/api';

/** Un article cité par le MOTEUR — jamais par le modèle de langage. */
export type ArticleCite = {
  code_id?: string;
  code_fr?: string;
  code_ar?: string;
  article?: number | string;
  citation_ar?: string;
  label_fr?: string;
  short_fr?: string;
  text_ar?: string;
};

export type IdentiteAgent = {
  organisation?: string;
  nom_organisation?: string;
  role?: string;
  libelle_role?: string;
  permissions?: string[];
};

export type ReponseAgent = {
  texte: string;
  outil_appele: string;
  refuse: boolean;
  abstention: boolean;
  mode_degrade: boolean;
  motif_degradation: string;
  articles: ArticleCite[];
  avertissements: string[];
  resultat: Record<string, unknown>;
  identite: IdentiteAgent;
  reformule_par_modele: boolean;
};

export type Capacite = { nom: string; description: string };

export type Capacites = {
  organisation: string;
  role: string;
  capacites: Capacite[];
};

/**
 * Pourquoi un appel de la bulle a échoué.
 *
 * `session` est distingué des autres : ce n'est pas une panne, c'est une
 * absence de droit d'entrée, et l'écran doit alors inviter à se connecter au
 * lieu d'afficher une avarie. Aucun de ces messages ne contient de code HTTP
 * ni d'URL : un juriste les lit.
 */
export type EchecAgent = {
  genre: 'session' | 'injoignable' | 'lenteur' | 'panne';
  message: string;
};

export type ResultatAgent<T> =
  | { ok: true; valeur: T }
  | { ok: false; echec: EchecAgent };

/**
 * Le délai au-delà duquel on rend la main.
 *
 * Le modèle met entre douze et vingt-sept secondes, mesuré sur le GPU
 * partagé de la démonstration. Soixante secondes seraient la borne haute du
 * mesuré ; on prend quatre-vingt-dix, parce qu'une salle pleine et un réseau
 * chargé ne se comportent pas comme un banc d'essai, et qu'abandonner une
 * réponse qui allait arriver est le pire des deux échecs possibles.
 */
const DELAI_MESSAGE_MS = 90000;

/** Les capacités ne traversent aucun modèle : elles doivent répondre vite. */
const DELAI_CAPACITES_MS = 12000;

async function appeler<T>(
  chemin: string,
  jeton: string,
  options: { methode?: 'GET' | 'POST'; corps?: unknown; delaiMs: number },
): Promise<ResultatAgent<T>> {
  const { methode = 'GET', corps, delaiMs } = options;

  let reponse: Response;
  try {
    reponse = await fetch(`${API_URL}${chemin}`, {
      method: methode,
      headers: {
        Authorization: `Bearer ${jeton}`,
        ...(corps ? { 'Content-Type': 'application/json' } : {}),
      },
      body: corps ? JSON.stringify(corps) : undefined,
      cache: 'no-store',
      signal: AbortSignal.timeout(delaiMs),
    });
  } catch (erreur) {
    const expire =
      erreur instanceof Error &&
      (erreur.name === 'TimeoutError' || erreur.name === 'AbortError');
    return {
      ok: false,
      echec: expire
        ? {
            genre: 'lenteur',
            message:
              "La réponse n'est pas arrivée dans le temps imparti. Le service " +
              'est très sollicité en ce moment. Vous pouvez reposer votre ' +
              'question : rien de ce que vous avez écrit n’est perdu.',
          }
        : {
            genre: 'injoignable',
            message:
              "Le service juridique n'est pas joignable depuis ce poste pour " +
              "l'instant. Aucune réponse ne peut être formée, et Mizan " +
              "préfère ne rien afficher plutôt que d'avancer un chiffre.",
          },
    };
  }

  if (reponse.status === 401 || reponse.status === 403) {
    return {
      ok: false,
      echec: {
        genre: 'session',
        message:
          "Votre session n'est plus ouverte. L'agent travaille au nom de " +
          'votre organisation et avec vos droits : il lui faut donc savoir ' +
          'qui vous êtes.',
      },
    };
  }

  if (!reponse.ok) {
    return {
      ok: false,
      echec: {
        genre: 'panne',
        message:
          "Le service juridique a rencontré une difficulté et n'a pas pu " +
          'former de réponse. Rien n’a été calculé, donc rien n’est affiché.',
      },
    };
  }

  try {
    return { ok: true, valeur: (await reponse.json()) as T };
  } catch {
    return {
      ok: false,
      echec: {
        genre: 'panne',
        message:
          'La réponse reçue est illisible. Plutôt que de vous en montrer une ' +
          'partie, Mizan ne vous en montre aucune.',
      },
    };
  }
}

export function envoyerAuAgent(
  jeton: string,
  message: string,
): Promise<ResultatAgent<ReponseAgent>> {
  return appeler<ReponseAgent>('/api/agent/message', jeton, {
    methode: 'POST',
    corps: { message },
    delaiMs: DELAI_MESSAGE_MS,
  });
}

export function lireCapacites(
  jeton: string,
): Promise<ResultatAgent<Capacites>> {
  return appeler<Capacites>('/api/agent/capacites', jeton, {
    delaiMs: DELAI_CAPACITES_MS,
  });
}
