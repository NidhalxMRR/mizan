/**
 * Traduire les capacités du serveur en phrases qu'un juriste peut cliquer.
 *
 * `GET /api/agent/capacites` renvoie des noms d'outils — « analyser_impaye »,
 * « preparer_mise_en_demeure ». Ces noms ne doivent JAMAIS atteindre l'écran :
 * ce sont des identifiants de code, et un jury de juristes n'a pas à lire du
 * code pour comprendre ce que la plateforme sait faire.
 *
 * On ne fabrique donc pas la suggestion à partir du nom. On tient une table :
 * à chaque capacité que le serveur déclare correspond une question déjà
 * rédigée, telle qu'un chef d'entreprise la poserait. La table est la seule
 * chose écrite ici ; la LISTE, elle, vient du serveur et dépend du rôle. Une
 * entreprise ne verra donc jamais proposer de signifier un acte, et un
 * huissier ne verra jamais proposer de déposer une facture — non parce que
 * l'écran les aurait cachés, mais parce que le serveur ne les a pas cités.
 *
 * Une capacité inconnue de cette table est simplement ignorée : mieux vaut
 * une suggestion de moins qu'un nom de fonction affiché à un jury.
 */

import type { Capacite } from './service';

export type Suggestion = {
  /** Le libellé court, sur le bouton. */
  titre: string;
  /** La question réellement envoyée à l'agent quand on clique. */
  question: string;
};

const TABLE: Record<string, Suggestion> = {
  analyser_impaye: {
    titre: 'Ma créance est-elle encore récupérable ?',
    question:
      'Ma créance de 9520 DT du 12/05/2026 est-elle encore récupérable ? ' +
      'activité menuiserie',
  },
  chercher_article: {
    titre: 'Que dit la loi sur la prescription ?',
    question: 'Que dit la loi tunisienne sur la prescription des créances commerciales ?',
  },
  preparer_mise_en_demeure: {
    titre: 'Préparer une mise en demeure',
    question:
      'Prépare le projet de mise en demeure pour une créance de 9520 DT du ' +
      '12/05/2026 contre la société Nour Distribution.',
  },
  analyser_risques_facture: {
    titre: 'Ma facture est-elle contestable ?',
    question:
      'Quels risques un débiteur pourrait-il opposer à ma facture de 9520 DT ' +
      'du 12/05/2026 ?',
  },
  recommander_professionnel: {
    titre: 'Quel médiateur pour mon litige ?',
    question:
      'Quel professionnel accrédité peut conduire un règlement amiable pour ' +
      'un recouvrement de 9520 DT à Tunis ?',
  },
  ouvrir_conciliation: {
    titre: 'Ouvrir un règlement amiable',
    question:
      'Ouvre un règlement amiable pour 9520 DT contre la société Nour ' +
      'Distribution, litige de recouvrement.',
  },
  consulter_mes_dossiers: {
    titre: 'Où en sont mes dossiers ?',
    question: 'Où en sont mes dossiers en cours ?',
  },
  signifier_mise_en_demeure: {
    titre: 'Consigner une signification',
    question:
      'Consigne la signification de la mise en demeure à la société Nour ' +
      'Distribution le 13/09/2026.',
  },
  administrer_organisations: {
    titre: 'Les organisations inscrites',
    question: 'Donne-moi la vue des organisations inscrites sur la plateforme.',
  },
};

/**
 * Trois suggestions au maximum.
 *
 * Au-delà, le bas de la bulle se remplit de boutons et le champ de saisie
 * descend sous la ligne de flottaison à 479 px. Trois tient dans tous les cas
 * mesurés, et trois suffisent à montrer qu'elles dépendent du rôle.
 */
export function suggestionsPour(capacites: Capacite[]): Suggestion[] {
  const vues = new Set<string>();
  const retenues: Suggestion[] = [];

  for (const c of capacites) {
    const s = TABLE[c.nom];
    if (!s || vues.has(c.nom)) continue;
    vues.add(c.nom);
    retenues.push(s);
    if (retenues.length === 3) break;
  }

  return retenues;
}
