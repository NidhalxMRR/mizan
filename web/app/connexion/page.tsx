'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { API_URL } from '@/lib/api';
import { roleLabels, roleLabelsAr, type Role } from '@/lib/auth';
import { ordreInscription } from '@/components/roles/privileges';
import { IconeRole, IconeBalance } from '@/components/roles/icones';
import '../espace/espace.css';

/**
 * Connexion.
 *
 * Sobre, et c'est délibéré. Tout le poids pédagogique est à l'inscription :
 * c'est là qu'on explique ce qu'un rôle emporte. Ici on entre, point. Deux
 * champs, un bouton. Un écran d'entrée qui explique quelque chose est un
 * écran qu'on relit chaque matin pour rien.
 *
 * La colonne de droite rappelle les cinq acteurs sans rien demander : un jury
 * qui arrive par cette page doit comprendre en trois secondes que la
 * plateforme distingue cinq qualités, sans avoir à créer un compte.
 *
 * Les raccourcis de démonstration en bas remplissent l'adresse à la place de
 * l'orateur. Motif : taper une adresse au clavier devant un jury rate une
 * fois sur deux, et une faute de frappe coûte trente secondes sur une
 * démonstration qui en dure cent quatre-vingts.
 */

type EtatEnvoi =
  | { phase: 'repos' }
  | { phase: 'envoi' }
  | { phase: 'echec'; message: string };

/** Les comptes de démonstration. Ils n'existent que pour la salle. */
const comptesDemo: { role: Role; courriel: string }[] = [
  { role: 'msme', courriel: 'direction@atelier-medina.tn' },
  { role: 'accredited_pro', courriel: 'mediateur@cabinet-benali.tn' },
  { role: 'huissier', courriel: 'etude@hj-tunis.tn' },
  { role: 'court_clerk', courriel: 'greffe@tc-tunis.tn' },
  { role: 'platform_admin', courriel: 'exploitation@mizan.tn' },
];

export default function Connexion() {
  const router = useRouter();
  const [courriel, setCourriel] = useState('');
  const [etat, setEtat] = useState<EtatEnvoi>({ phase: 'repos' });

  async function envoyer(evenement: React.FormEvent<HTMLFormElement>) {
    evenement.preventDefault();
    const formulaire = new FormData(evenement.currentTarget);
    setEtat({ phase: 'envoi' });

    try {
      const reponse = await fetch(`${API_URL}/comptes/connexion`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        cache: 'no-store',
        signal: AbortSignal.timeout(15000),
        body: JSON.stringify({
          courriel: formulaire.get('courriel'),
          mot_de_passe: formulaire.get('motdepasse'),
        }),
      });

      if (!reponse.ok) {
        setEtat({
          phase: 'echec',
          message:
            "Adresse ou mot de passe incorrect. Si votre compte vient d'être " +
            "créé, il attend peut-être encore la vérification de votre qualité.",
        });
        return;
      }

      // Le service répond : on se rend dans l'espace. Le rôle réel est
      // déterminé côté serveur ; l'écran ne le devine pas.
      router.push('/espace');
    } catch {
      // Le service de connexion est construit en parallèle et peut ne pas
      // être en ligne. Plutôt que de bloquer la démonstration sur un écran
      // mort, on le dit clairement et on laisse l'accès à l'espace : les
      // tableaux de bord n'ont besoin d'aucun serveur pour être montrés.
      setEtat({
        phase: 'echec',
        message:
          "Le service d'identification n'est pas joignable pour le moment. " +
          'Les espaces de travail restent consultables en démonstration.',
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
        <p className="eyebrow">ACCÉDER À VOTRE ESPACE</p>
        <h1>
          Bon retour. <em>Le droit vous attend.</em>
        </h1>
        <p className="intro">
          Identifiez-vous pour retrouver vos dossiers. Votre espace de travail
          s&apos;ouvrira selon la qualité en laquelle vous êtes inscrit.
        </p>
      </header>

      <div className="connexion-corps">
        <section
          className="panel connexion-panneau"
          aria-label="Identification"
        >
          <form onSubmit={envoyer} noValidate>
            <div className="connexion-champs">
              <div className="champ">
                <label htmlFor="courriel">Adresse électronique</label>
                <input
                  id="courriel"
                  name="courriel"
                  type="email"
                  autoComplete="email"
                  value={courriel}
                  onChange={(e) => setCourriel(e.target.value)}
                  required
                />
              </div>

              <div className="champ">
                <label htmlFor="motdepasse">Mot de passe</label>
                <input
                  id="motdepasse"
                  name="motdepasse"
                  type="password"
                  autoComplete="current-password"
                  required
                />
              </div>
            </div>

            <div className="entree-actions">
              <button
                type="submit"
                className="primary-button"
                disabled={etat.phase === 'envoi'}
              >
                {etat.phase === 'envoi' ? 'Vérification…' : 'Entrer'}
              </button>
              <p className="entree-actions-note">
                Vos pièces sont conservées avec leur empreinte numérique. Votre
                mot de passe les protège.
              </p>
            </div>
          </form>

          {etat.phase === 'echec' ? (
            <p className="entree-message entree-message-erreur" role="alert">
              <span>
                <strong>Connexion impossible</strong>
                {etat.message}
              </span>
            </p>
          ) : null}

          <div className="demo-comptes">
            <p className="demo-comptes-titre">
              Comptes de démonstration — un clic remplit l&apos;adresse
            </p>
            <div className="demo-comptes-liste">
              {comptesDemo.map((c) => (
                <button
                  key={c.role}
                  type="button"
                  className="demo-compte"
                  onClick={() => {
                    setCourriel(c.courriel);
                    setEtat({ phase: 'repos' });
                  }}
                >
                  <IconeRole role={c.role} taille={15} />
                  {roleLabels[c.role]}
                </button>
              ))}
            </div>
          </div>

          <p className="entree-bascule">
            Pas encore de compte ?{' '}
            <Link href="/inscription">Créer mon espace</Link>
          </p>
        </section>

        <aside className="panel connexion-rappel" aria-label="Les cinq acteurs">
          <p className="eyebrow">CINQ QUALITÉS</p>
          <h2>Chacun son espace</h2>
          <ul className="connexion-rappel-liste">
            {ordreInscription.map((r) => (
              <li key={r} className="connexion-rappel-item">
                <IconeRole role={r} taille={18} />
                <span>{roleLabels[r]}</span>
                <span className="connexion-rappel-ar">{roleLabelsAr[r]}</span>
              </li>
            ))}
          </ul>
          <p className="privileges-destinataire">
            Les pouvoirs ne se cumulent pas et ne se déclarent pas : ils
            découlent de la qualité vérifiée à l&apos;inscription.
          </p>
        </aside>
      </div>
    </div>
  );
}
