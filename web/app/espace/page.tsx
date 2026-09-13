'use client';

import Link from 'next/link';
import { useState } from 'react';
import { roleLabels, roleLabelsAr, type Role } from '@/lib/auth';
import {
  IconeRole,
  IconeCoche,
  IconeVerrou,
  IconeBalance,
} from '@/components/roles/icones';
import { ordreInscription } from '@/components/roles/privileges';
import { tableaux, actionsDuRole } from './tableaux';
import './espace.css';

/**
 * L'espace de travail.
 *
 * Cinq tableaux de bord, un par qualité. Ils ne diffèrent pas par la
 * décoration : ils diffèrent par ce qu'ils PROPOSENT. Une entreprise n'y
 * trouve pas de bouton pour signifier un acte ; un huissier n'y trouve pas de
 * bouton pour déposer une facture. Ce n'est pas un choix d'ergonomie, c'est
 * la matrice de `lib/auth.ts` rendue visible.
 *
 * Sur le sélecteur de rôle en haut à droite : il n'existe QUE pour la
 * démonstration. En exploitation, le rôle vient du compte identifié et ne se
 * choisit pas. Il est donc annoncé pour ce qu'il est — « affichage de
 * démonstration » — plutôt que déguisé en fonctionnalité. Sans lui, montrer
 * les cinq espaces à un jury demanderait cinq déconnexions, soit à peu près
 * tout le temps de parole disponible.
 *
 * Sur l'absence d'appel à l'API : cet écran ne dépend d'aucun serveur. C'est
 * délibéré. Le jour de la démonstration, si le service d'identification n'est
 * pas en ligne, les cinq tableaux restent montrables. Les chiffres affichés
 * sont des dossiers de démonstration et ne prétendent jamais avoir été
 * calculés : les calculs réels vivent dans « Mon impayé », qui interroge le
 * moteur déterministe et affiche l'article qui fonde chaque résultat.
 */

export default function Espace() {
  const [role, setRole] = useState<Role>('msme');

  const tableau = tableaux[role];
  const actions = actionsDuRole(role);

  return (
    <div className="entree" data-espace-role={role}>
      <header className="espace-entete">
        <div className="espace-identite">
          <span className="espace-identite-icone">
            <IconeRole role={role} taille={28} />
          </span>
          <div className="espace-identite-texte">
            <p className="eyebrow">VOTRE ESPACE</p>
            <h1>
              {roleLabels[role]}
              <span className="espace-identite-ar">{roleLabelsAr[role]}</span>
            </h1>
            <p className="espace-identite-sous">{tableau.accroche}</p>
          </div>
        </div>

        <div className="selecteur-role">
          <p className="selecteur-role-titre">
            Affichage de démonstration — voir l&apos;espace de
          </p>
          <div className="selecteur-role-boutons">
            {ordreInscription.map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => setRole(r)}
                aria-pressed={r === role}
                data-selecteur-role={r}
                className={`selecteur-bouton${
                  r === role ? ' selecteur-bouton-actif' : ''
                }`}
              >
                <IconeRole role={r} taille={15} />
                {roleLabels[r]}
              </button>
            ))}
          </div>
        </div>
      </header>

      {/* --- Les mesures de tête ---------------------------------------- */}
      <section className="espace-mesures" aria-label="Vue d’ensemble">
        {tableau.mesures.map((m) => (
          <article className="mesure" key={m.libelle}>
            <p className="mesure-libelle">{m.libelle}</p>
            <p className={`mesure-valeur mesure-${m.etat}`}>{m.valeur}</p>
            <p className="mesure-detail">{m.detail}</p>
          </article>
        ))}
      </section>

      {/* --- Ce que ce rôle peut faire ---------------------------------- */}
      <section className="espace-section" aria-label={tableau.titreActions}>
        <div className="espace-section-titre">
          <div>
            <p className="eyebrow">{tableau.titreActions.toUpperCase()}</p>
            <h2>
              {actions.length} action{actions.length > 1 ? 's' : ''} vous
              {actions.length > 1 ? ' sont ouvertes' : ' est ouverte'}
            </h2>
          </div>
          {/* Le badge ne répète pas le nombre déjà écrit dans le titre : il
              dit ce que le nombre ne dit pas, à savoir que la liste est
              exhaustive. Tout ce que la qualité permet est sur cet écran ;
              ce qui n'y figure pas lui est fermé. */}
          <span className="provenance provenance-verified">
            Tous vos pouvoirs figurent ici
          </span>
        </div>

        <div className="grille-actions" data-grille-actions>
          {actions.map((a) => (
            <button
              key={a.cle}
              type="button"
              className="action"
              data-action={a.cle}
            >
              <span className="action-tete">
                <span className="action-icone">
                  <IconeCoche taille={18} />
                </span>
                <span className="action-intitule">{a.intitule}</span>
              </span>
              <span className="action-portee">{a.portee}</span>
              <span className="action-borne">{a.borne}</span>
              {a.fondement ? (
                <span className="privilege-fondement">{a.fondement}</span>
              ) : null}
            </button>
          ))}
        </div>
      </section>

      {/* --- Ce que ce rôle ne peut PAS faire ---------------------------
          Affiché, pas masqué. Une action absente se lit comme un oubli de
          développeur ; une action fermée qui cite son article se lit comme
          une règle — et c'est précisément ce qu'un jury de juristes doit
          voir pour croire au reste de l'écran. */}
      <section
        className="espace-section"
        aria-label="Actions fermées à votre qualité"
      >
        <div className="espace-section-titre">
          <div>
            <p className="eyebrow">FERMÉ À VOTRE QUALITÉ</p>
            <h2>Et pourquoi</h2>
          </div>
        </div>

        <div className="grille-actions" data-grille-fermees>
          {tableau.fermees.map((f) => (
            <div
              key={f.intitule}
              className="action action-fermee"
              aria-disabled="true"
            >
              <span className="action-tete">
                <span className="action-icone">
                  <IconeVerrou taille={17} />
                </span>
                <span className="action-intitule">{f.intitule}</span>
              </span>
              <span className="action-portee">{f.motif}</span>
              <span className="action-motif">
                <strong>Réservé {f.reservee}.</strong>
                {f.fondement ? ` ${f.fondement}.` : ''}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* --- Les dossiers ----------------------------------------------- */}
      <section className="espace-section" aria-label={tableau.titreListe}>
        <div className="espace-section-titre">
          <div>
            <p className="eyebrow">{tableau.titreListe.toUpperCase()}</p>
            <p className="intro">{tableau.sousTitreListe}</p>
          </div>
        </div>

        <ul className="dossiers">
          {tableau.dossiers.map((d) => (
            <li className="dossier-ligne" key={d.reference}>
              <div className="dossier-identite">
                {/* <bdi> : certaines références contiennent un mot arabe
                    au milieu d'une phrase française (« Projet d'إنذار — … »).
                    Sans isolation, le tiret cadratin qui suit bascule à
                    gauche du bloc arabe. */}
                <p className="dossier-reference">
                  <bdi>{d.reference}</bdi>
                </p>
                <p className="dossier-parties">
                  {d.parties} · <span className="dossier-montant">{d.montant}</span>
                </p>
              </div>
              <span
                className={`provenance provenance-${d.etatTon} dossier-etat`}
              >
                {d.etat}
              </span>
              {d.delai ? (
                <span className="dossier-delai">
                  <span
                    className={`dossier-delai-nombre dossier-delai-${d.delai.ton}`}
                  >
                    {d.delai.nombre}
                  </span>
                  <span className="dossier-delai-libelle">
                    {d.delai.libelle}
                  </span>
                </span>
              ) : (
                <span className="dossier-delai">
                  <span className="dossier-delai-libelle">—</span>
                </span>
              )}
            </li>
          ))}
        </ul>
      </section>

      {/* --- La limite du rôle ------------------------------------------ */}
      <aside className="limite-role" aria-label="La limite de votre qualité">
        <span className="limite-role-icone">
          <IconeBalance taille={22} />
        </span>
        <div className="limite-role-texte">
          <p className="limite-role-titre">{tableau.limite.titre}</p>
          <p className="limite-role-corps">{tableau.limite.corps}</p>
        </div>
      </aside>

      <p className="entree-bascule">
        Ce n&apos;est pas votre qualité ?{' '}
        <Link href="/inscription">Créer le bon espace</Link> ·{' '}
        <Link href="/connexion">Changer de compte</Link>
      </p>
    </div>
  );
}
