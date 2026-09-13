'use client';

/**
 * Le pont entre l'écran de connexion et l'agent.
 *
 * POURQUOI CE FICHIER EXISTE
 * --------------------------
 * Deux briques ont été construites séparément, et c'est exactement la
 * situation que `api/main.py` décrit déjà côté serveur : le garde d'accès
 * sait lire un jeton, l'agent attend de trouver la session déjà vérifiée, et
 * ni l'un ni l'autre ne pouvait écrire dans le fichier de l'autre. Le serveur
 * a résolu cela par un intergiciel qui ne décide rien et se contente de poser
 * le lien. Ce fichier est le même geste, côté navigateur.
 *
 * L'écran `/connexion` appelle `POST /comptes/connexion` puis redirige vers
 * `/espace` sans rien conserver de la réponse : le jeton signé est reçu et
 * jeté. Tant qu'il en va ainsi, l'agent — qui exige une session vérifiée et
 * n'a pas de mode anonyme — resterait fermé à un utilisateur qui vient
 * pourtant de s'identifier correctement.
 *
 * CE QUE LE PONT FAIT, ET RIEN DE PLUS
 * ------------------------------------
 *   1. Il regarde passer les appels à `/comptes/connexion`.
 *   2. Si le corps porte une adresse sous le nom « courriel » alors que le
 *      serveur l'attend sous le nom « email », il ajoute le champ attendu
 *      sans retirer l'autre. C'est une attelle, pas une correction : la
 *      correction appartient au fichier de l'écran de connexion, et elle y
 *      sera faite par la personne qui en a la charge. L'attelle est écrite
 *      ici pour que la démonstration ne dépende pas de cette coordination.
 *   3. Si la réponse est un succès, il range le jeton là où la bulle le
 *      cherchera — et prévient les composants montés, qui ne rechargent pas
 *      la page.
 *
 * CE QU'IL NE FAIT JAMAIS
 * -----------------------
 * Il ne modifie aucune autre requête, n'intercepte aucun mot de passe, ne
 * conserve rien d'autre que ce que `session.ts` déclare, et ne lève jamais :
 * la moindre exception ici casserait toutes les requêtes de l'application.
 * Tout est enveloppé, et en cas de doute on laisse passer la requête telle
 * quelle.
 */

import {
  enregistrerSession,
  sessionDepuisConnexion,
  type SessionMizan,
} from './session';

/** Émis quand une session vient d'être ouverte ou refermée. */
export const EVENEMENT_SESSION = 'mizan:session';

/** Marque posée sur `window` pour ne jamais installer le pont deux fois. */
const MARQUE = '__mizanPontConnexion';

function estUneConnexion(cible: string): boolean {
  return cible.includes('/comptes/connexion');
}

/** Ajoute `email` quand seul `courriel` est présent. Rend le corps à envoyer. */
function reparerLeCorps(corps: unknown): string | null {
  if (typeof corps !== 'string' || !corps) return null;
  try {
    const lu = JSON.parse(corps) as Record<string, unknown>;
    if (typeof lu !== 'object' || lu === null) return null;
    if (typeof lu.email === 'string' && lu.email) return null; // déjà correct
    const adresse = lu.courriel ?? lu.adresse;
    if (typeof adresse !== 'string' || !adresse) return null;
    return JSON.stringify({ ...lu, email: adresse });
  } catch {
    return null;
  }
}

export function annoncerLaSession(session: SessionMizan | null): void {
  if (typeof window === 'undefined') return;
  try {
    window.dispatchEvent(
      new CustomEvent<SessionMizan | null>(EVENEMENT_SESSION, {
        detail: session,
      }),
    );
  } catch {
    /* un navigateur sans CustomEvent ne casse pas la connexion pour autant */
  }
}

export function installerLePontDeConnexion(): void {
  if (typeof window === 'undefined') return;

  const fenetre = window as unknown as Record<string, unknown>;
  if (fenetre[MARQUE]) return;
  fenetre[MARQUE] = true;

  const origine = window.fetch.bind(window);

  window.fetch = async function (
    entree: RequestInfo | URL,
    options?: RequestInit,
  ): Promise<Response> {
    let cible = '';
    try {
      cible =
        typeof entree === 'string'
          ? entree
          : entree instanceof URL
            ? entree.href
            : entree.url;
    } catch {
      cible = '';
    }

    if (!estUneConnexion(cible)) {
      return origine(entree, options);
    }

    // --- 1. l'attelle sur le nom du champ ---------------------------------
    let optionsFinales = options;
    try {
      const repare = reparerLeCorps(options?.body);
      if (repare) optionsFinales = { ...options, body: repare };
    } catch {
      optionsFinales = options;
    }

    const reponse = await origine(entree, optionsFinales);

    // --- 2. la capture du jeton -------------------------------------------
    try {
      if (reponse.ok) {
        // On lit un CLONE : le corps d'une réponse ne se lit qu'une fois, et
        // l'écran de connexion doit pouvoir le lire à son tour.
        const donnees = await reponse.clone().json();
        if (donnees && typeof donnees.jeton === 'string' && donnees.jeton) {
          const session = sessionDepuisConnexion(donnees);
          enregistrerSession(session);
          annoncerLaSession(session);
        }
      }
    } catch {
      // Corps non-JSON, lecture refusée : la connexion de l'utilisateur n'est
      // pas concernée, seule la bulle restera fermée. Elle le dira elle-même.
    }

    return reponse;
  } as typeof window.fetch;
}
