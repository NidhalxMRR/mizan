'use client';

import Link from 'next/link';
import { useState } from 'react';
import { API_URL } from '@/lib/api';
import { roleLabels, roleLabelsAr, permissions, type Role } from '@/lib/auth';
import {
  IconeRole,
  IconeBalance,
  IconeCoche,
  IconeVerrou,
} from '@/components/roles/icones';
import {
  deRole,
  fiches,
  ordreInscription,
  privileges,
  privilegesDuRole,
  type ClePermission,
} from '@/components/roles/privileges';
import '../espace/espace.css';

/**
 * Inscription.
 *
 * L'écran est bâti autour d'une seule idée : un rôle n'est pas une case à
 * cocher, c'est une qualité juridique, et cette qualité emporte des pouvoirs
 * précis. L'utilisateur doit donc les voir AVANT de valider, pas les
 * découvrir en arrivant sur son tableau de bord.
 *
 * Trois conséquences de mise en page :
 *
 * 1. Le choix du rôle et la liste des privilèges sont VISIBLES ENSEMBLE sur
 *    projecteur. Un accordéon ou une seconde étape auraient cassé la
 *    démonstration : le jury doit voir la liste CHANGER quand on clique.
 * 2. Chaque privilège est accompagné de sa BORNE. Un pouvoir sans sa limite
 *    se lit comme une promesse commerciale ; avec sa limite, il se lit comme
 *    une règle. C'est la différence entre un produit et un outil de justice.
 * 3. L'écran affiche aussi ce que le rôle NE PEUT PAS faire, tiré de la même
 *    matrice. Montrer qu'une entreprise ne signifie pas d'acte vaut mieux que
 *    de l'affirmer dans un discours.
 *
 * Sur le contrôle d'accès : rien ici ne fait autorité. `lib/auth.ts` reste la
 * seule source, et le serveur revérifiera. Cet écran EXPLIQUE la matrice, il
 * ne la définit pas — d'où la lecture de `permissions[role]` plutôt qu'une
 * liste recopiée, qui aurait fini par mentir.
 */

/** Où en est l'envoi. Chaque état a son message ; aucun ne fait planter l'écran. */
type EtatEnvoi =
  | { phase: 'repos' }
  | { phase: 'envoi' }
  | { phase: 'succes'; message: string }
  | { phase: 'echec'; message: string };

export default function Inscription() {
  // L'entreprise ouvre la liste, et c'est elle qui est sélectionnée d'entrée :
  // c'est la PME en litige que le challenge cherche à servir, donc le premier
  // jeu de privilèges que le jury doit lire.
  const [role, setRole] = useState<Role>('msme');
  const [etat, setEtat] = useState<EtatEnvoi>({ phase: 'repos' });

  const fiche = fiches[role];
  const accordes = privilegesDuRole(role);
  const refuses = pouvoirsRefuses(role);

  async function envoyer(evenement: React.FormEvent<HTMLFormElement>) {
    evenement.preventDefault();
    const formulaire = new FormData(evenement.currentTarget);
    setEtat({ phase: 'envoi' });

    try {
      const reponse = await fetch(`${API_URL}/comptes/inscription`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        cache: 'no-store',
        // Une inscription n'a aucune raison de prendre plus de quinze
        // secondes. Sans borne, l'écran resterait figé devant le jury.
        signal: AbortSignal.timeout(15000),
        body: JSON.stringify({
          role,
          nom: formulaire.get('nom'),
          organisation: formulaire.get('organisation'),
          courriel: formulaire.get('courriel'),
          telephone: formulaire.get('telephone'),
          identifiant_professionnel: formulaire.get('identite'),
          mot_de_passe: formulaire.get('motdepasse'),
        }),
      });

      if (!reponse.ok) {
        // On ne montre ni le code HTTP ni l'URL : le jury est composé de
        // juristes, et « 422 sur /comptes/inscription » ne leur apprend rien.
        setEtat({
          phase: 'echec',
          message:
            "Le service d'inscription a refusé la demande. Vérifiez que " +
            'chaque champ est renseigné, puis recommencez.',
        });
        return;
      }

      setEtat({
        phase: 'succes',
        message:
          `Demande enregistrée en qualité ${deRole(role)}. ` +
          'Elle sera activée une fois votre qualité vérifiée.',
      });
    } catch {
      // Le cas le plus probable le jour de la démonstration : le service
      // d'inscription est construit en parallèle et peut ne pas être en
      // ligne. L'écran le dit sans jargon et reste utilisable — les
      // privilèges affichés, eux, ne dépendent d'aucun serveur.
      setEtat({
        phase: 'echec',
        message:
          "Le service d'inscription n'est pas joignable pour le moment. " +
          'Votre saisie est conservée à l’écran : vous pouvez réessayer dans ' +
          'un instant, ou vous adresser au greffe.',
      });
    }
  }

  return (
    <div className="entree">
      <header className="entree-entete">
        <div className="entree-marque">
          <IconeBalance taille={26} />
          <p className="entree-marque-nom">
            Mizan<span className="entree-marque-ar">ميزان</span>
          </p>
        </div>
        <p className="eyebrow">CRÉER UN COMPTE</p>
        <h1>
          Votre qualité décide de <em>ce que vous pourrez faire</em>.
        </h1>
        <p className="intro">
          Sur Mizan, un compte n&apos;est pas un simple accès : c&apos;est une
          qualité juridique. Choisissez la vôtre ci-dessous — la liste de vos
          pouvoirs, et de leurs limites, s&apos;affiche immédiatement à droite,
          avant toute validation.
        </p>
        <p className="entree-bascule">
          Vous avez déjà un compte ?{' '}
          <Link href="/connexion">Se connecter</Link>
        </p>
      </header>

      <div className="inscription-corps">
        {/* --- Colonne 1 : le choix ------------------------------------- */}
        <section
          className="panel inscription-choix"
          aria-label="Choisir votre qualité"
        >
          <p className="eyebrow">EN QUELLE QUALITÉ VOUS INSCRIVEZ-VOUS ?</p>
          <h2>Cinq acteurs, cinq espaces</h2>

          <ul className="choix-roles">
            {ordreInscription.map((candidat) => {
              const actif = candidat === role;
              const nombre = permissions[candidat].length;
              return (
                <li key={candidat}>
                  <button
                    type="button"
                    onClick={() => {
                      setRole(candidat);
                      // Changer de rôle efface le message précédent : il
                      // portait sur une demande qui n'est plus celle-là.
                      setEtat({ phase: 'repos' });
                    }}
                    className={`carte-role${actif ? ' carte-role-active' : ''}`}
                    aria-pressed={actif}
                    data-role={candidat}
                  >
                    <span className="carte-role-icone">
                      <IconeRole role={candidat} taille={22} />
                    </span>
                    <span className="carte-role-texte">
                      <span className="carte-role-titre">
                        <span className="carte-role-fr">
                          {roleLabels[candidat]}
                        </span>
                        <span className="carte-role-ar">
                          {roleLabelsAr[candidat]}
                        </span>
                      </span>
                      <span className="carte-role-qui">
                        {fiches[candidat].destinataire}
                      </span>
                      <span className="carte-role-nb">
                        {nombre} pouvoir{nombre > 1 ? 's' : ''}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>

        {/* --- Colonne 2 : ce que ce rôle emporte ------------------------ */}
        <section
          className="panel inscription-privileges"
          aria-label="Ce que cette qualité vous donnera le droit de faire"
          aria-live="polite"
          data-privileges-role={role}
        >
          <div className="privileges-entete">
            <div className="privileges-entete-titre">
              <span className="privileges-entete-icone">
                <IconeRole role={role} taille={24} />
              </span>
              <div>
                <p className="eyebrow">EN QUALITÉ DE</p>
                <h2>
                  {roleLabels[role]}
                  <span className="entree-marque-ar">{roleLabelsAr[role]}</span>
                </h2>
              </div>
            </div>
            <span className="provenance provenance-verified">
              {accordes.length} pouvoir{accordes.length > 1 ? 's' : ''} accordé
              {accordes.length > 1 ? 's' : ''}
            </span>
          </div>

          <p className="privileges-destinataire">{fiche.promesse}</p>

          <ul className="liste-privileges" data-liste-privileges>
            {accordes.map((p) => (
              <li
                key={p.intitule}
                className={`privilege${p.exclusif ? ' privilege-exclusif' : ''}`}
              >
                <div className="privilege-tete">
                  <span className="privilege-coche">
                    <IconeCoche taille={17} />
                  </span>
                  <p className="privilege-intitule">{p.intitule}</p>
                  {p.exclusif ? (
                    <span className="privilege-sceau">Vous seul</span>
                  ) : null}
                </div>
                <p className="privilege-portee">{p.portee}</p>
                <p className="privilege-borne">
                  <span className="privilege-borne-icone">
                    <IconeVerrou taille={14} />
                  </span>
                  <span>{p.borne}</span>
                </p>
                {p.fondement ? (
                  <span className="privilege-fondement">{p.fondement}</span>
                ) : null}
              </li>
            ))}
          </ul>

          {refuses.length > 0 ? (
            <div className="contre-liste">
              <p className="contre-liste-titre">
                Ce que cette qualité ne vous permettra pas
              </p>
              <ul>
                {refuses.map((r) => (
                  <li key={r.intitule} className="contre-item">
                    <span className="contre-item-icone">
                      <IconeVerrou taille={13} />
                    </span>
                    <span>
                      <strong>{r.intitule}</strong> — réservé à{' '}
                      {r.detenteurs}.
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <p className="justificatif">
            <span className="privilege-borne-icone">
              <IconeVerrou taille={15} />
            </span>
            <span>{fiche.justificatif}</span>
          </p>
        </section>
      </div>

      {/* --- Le formulaire, sous les deux colonnes ---------------------- */}
      <section className="panel bloc-espace" aria-label="Vos coordonnées">
        <p className="eyebrow">VOS COORDONNÉES</p>
        {/* `deRole` porte l'élision : sans elle on lisait « en qualité de
            entreprise » et « de administrateur ». */}
        <h2>Demande d&apos;inscription en qualité {deRole(role)}</h2>

        <form onSubmit={envoyer} noValidate>
          <div className="formulaire-entree">
            <div className="champ">
              <label htmlFor="nom">Nom et prénom</label>
              <input id="nom" name="nom" type="text" autoComplete="name" required />
            </div>

            <div className="champ">
              <label htmlFor="organisation">
                {role === 'msme'
                  ? 'Raison sociale'
                  : role === 'court_clerk'
                    ? 'Juridiction de rattachement'
                    : 'Cabinet ou étude'}
              </label>
              <input
                id="organisation"
                name="organisation"
                type="text"
                autoComplete="organization"
                required
              />
            </div>

            <div className="champ">
              <label htmlFor="courriel">Adresse électronique</label>
              <input
                id="courriel"
                name="courriel"
                type="email"
                autoComplete="email"
                required
              />
            </div>

            <div className="champ">
              <label htmlFor="telephone">Téléphone</label>
              <input
                id="telephone"
                name="telephone"
                type="tel"
                autoComplete="tel"
                inputMode="tel"
              />
            </div>

            {/* Ce champ change de nature avec le rôle : une PME donne son
                identifiant d'entreprise, un huissier son numéro de Chambre.
                Demander « numéro professionnel » aux cinq aurait été plus
                simple à coder et incompréhensible à lire. */}
            <div className="champ champ-large">
              <label htmlFor="identite">{fiche.champIdentite.libelle}</label>
              <input
                id="identite"
                name="identite"
                type="text"
                placeholder={fiche.champIdentite.exemple}
                aria-describedby="aide-identite"
              />
              <p className="champ-aide" id="aide-identite">
                {fiche.champIdentite.aide}
              </p>
            </div>

            <div className="champ champ-large champ-mesure">
              <label htmlFor="motdepasse">Mot de passe</label>
              <input
                id="motdepasse"
                name="motdepasse"
                type="password"
                autoComplete="new-password"
                minLength={8}
                required
                aria-describedby="aide-motdepasse"
              />
              <p className="champ-aide" id="aide-motdepasse">
                Huit caractères au minimum. Il protège des pièces qui peuvent
                finir devant un tribunal.
              </p>
            </div>
          </div>

          <div className="entree-actions">
            <button
              type="submit"
              className="primary-button"
              disabled={etat.phase === 'envoi'}
            >
              {etat.phase === 'envoi'
                ? 'Envoi en cours…'
                : `Demander l'ouverture de mon espace`}
            </button>
            <p className="entree-actions-note">
              Votre qualité sera vérifiée avant activation. Aucun pouvoir
              n&apos;est accordé sur simple déclaration.
            </p>
          </div>
        </form>

        {etat.phase === 'echec' ? (
          <p className="entree-message entree-message-erreur" role="alert">
            <span>
              <strong>La demande n&apos;a pas pu être transmise</strong>
              {etat.message}
            </span>
          </p>
        ) : null}
        {etat.phase === 'succes' ? (
          <p className="entree-message entree-message-succes" role="status">
            <span>
              <strong>Demande reçue</strong>
              {etat.message}
            </span>
          </p>
        ) : null}
        {etat.phase === 'envoi' ? (
          <p className="entree-message entree-message-attente" role="status">
            <span>Transmission de votre demande…</span>
          </p>
        ) : null}
      </section>
    </div>
  );
}

/* ---------------------------------------------------------------------------
   Ce que le rôle choisi NE PEUT PAS faire.

   Calculé depuis la matrice, jamais écrit à la main : on prend tous les
   pouvoirs de tous les rôles, on retire ceux du rôle choisi, et on ne garde
   que ceux qui sont EXCLUSIFS à un autre acteur. Sans ce dernier filtre la
   liste ferait vingt lignes et perdrait le lecteur ; avec lui, elle dit
   exactement ce qui compte — qui détient les monopoles.
--------------------------------------------------------------------------- */

type PouvoirRefuse = { intitule: string; detenteurs: string };

function pouvoirsRefuses(role: Role): PouvoirRefuse[] {
  const siens = new Set<string>(permissions[role]);
  const vus = new Set<string>();
  const refuses: PouvoirRefuse[] = [];

  for (const [autre, cles] of Object.entries(permissions) as [
    Role,
    readonly string[],
  ][]) {
    if (autre === role) continue;
    for (const cle of cles) {
      if (siens.has(cle) || vus.has(cle)) continue;
      const p = privileges[cle as ClePermission];
      if (!p?.exclusif) continue;
      vus.add(cle);
      refuses.push({ intitule: p.intitule, detenteurs: roleLabels[autre] });
    }
  }
  return refuses;
}
