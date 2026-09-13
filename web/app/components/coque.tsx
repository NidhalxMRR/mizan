'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';

/**
 * La coque : barre latérale, fil d'Ariane, zone de contenu.
 *
 * Client component pour une seule raison — `usePathname()`, qui sert à
 * marquer l'entrée de navigation active. Tout le reste de l'application
 * rend côté serveur.
 *
 * La note de bas de barre rappelle le monopole du عدل منفذ (CPC art. 5 et
 * 60). Ce n'est pas de la décoration : c'est la limite que la plateforme
 * s'impose, et un jury doit la voir sans cliquer.
 */

const entrees = [
  { href: '/', libelle: 'Principe', cle: 'accueil' },
  { href: '/dossier', libelle: 'Mon impayé', cle: 'dossier' },
  { href: '/corpus', libelle: 'Le corpus', cle: 'corpus' },
  // L'espace de travail manquait à la navigation : on y arrivait après la
  // connexion, mais aucun lien n'y ramenait ensuite. Un visiteur qui
  // revenait à l'accueil perdait le chemin de son propre espace et n'avait
  // plus que le bouton de retour du navigateur pour le retrouver.
  { href: '/espace', libelle: 'Mon espace', cle: 'espace' },
] as const;

const filsAriane: Record<string, string> = {
  '/': 'Principe',
  '/dossier': 'Mon impayé',
  '/corpus': 'Le corpus',
  '/espace': 'Mon espace',
  '/connexion': 'Connexion',
  '/inscription': 'Créer mon espace',
};

export function Coque({ children }: { children: React.ReactNode }) {
  const chemin = usePathname();

  /*
   * L'adresse du second volet se déduit du nom d'hôte par lequel la page a
   * été ouverte, jamais d'une valeur figée à la compilation. La leçon a déjà
   * été payée une fois sur ce projet : une adresse en dur envoyait le
   * navigateur du visiteur interroger sa propre machine, et tous les appels
   * partaient dans le vide sans laisser de trace côté serveur.
   *
   * `useState` avec une fonction d'initialisation plutôt qu'une lecture
   * directe : le rendu se fait aussi sur le serveur, où `window` n'existe
   * pas. Le lien porte alors une adresse relative inoffensive, que le
   * navigateur corrige dès son arrivée.
   */
  const [volet2, setVolet2] = useState('#');
  useEffect(() => {
    setVolet2(`${window.location.protocol}//${window.location.hostname}:8830/`);
  }, []);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">
            ⚖
          </div>
          <div>
            <p className="brand-name">
              Mizan <span>ميزان</span>
            </p>
            <p className="brand-caption">RÉSOLUTION DES LITIGES</p>
          </div>
        </div>

        <nav className="main-nav" aria-label="Navigation principale">
          <p className="nav-label">PARCOURS</p>
          {entrees.map((e) => {
            const actif = chemin === e.href;
            return (
              <Link
                key={e.cle}
                href={e.href}
                className={`nav-item${actif ? ' nav-item-active' : ''}`}
                aria-current={actif ? 'page' : undefined}
              >
                {e.libelle}
              </Link>
            );
          })}

          {/*
            Le second volet, tenu par Zied, vit dans une application
            distincte servie sur son propre port. Les deux moitiés se
            répondent : ici l'on regarde la facture qu'une société n'a pas
            payée ; là-bas, le client qui ne règle pas l'entreprise, jusqu'à
            l'écran où le débiteur lui-même reçoit la réclamation.

            On y renvoie par un lien ordinaire, et non par une passerelle
            interne : chaque application garde ses ports, ses dépendances et
            ses pannes. Si l'une tombe, l'autre n'en sait rien — ce qui, le
            jour d'une démonstration, vaut mieux qu'une élégance commune.

            L'adresse se déduit de celle par laquelle la page a été ouverte,
            afin qu'un visiteur venu de l'extérieur ne soit pas renvoyé vers
            la machine sur laquelle il se trouve.
          */}
          <a
            className="nav-item nav-item-voisin"
            href={volet2}
            target="_blank"
            rel="noreferrer"
          >
            Le recouvrement
          </a>
        </nav>

        <div className="security-note">
          <span aria-hidden="true">🔒</span>
          <span>
            {/*
              Le grand encadré de la page d'accueil énonce trois limites :
              Mizan ne signifie pas, ne juge pas, ne représente personne. Un
              visiteur qui entre par une autre page ne le lisait jamais, et
              c'est pourtant ce qui distingue l'outil d'un robot qui promet
              de régler un litige à la place d'un avocat.

              On reprend donc les trois ici, en une ligne chacune, présentes
              sur tous les écrans. Le résumé ne remplace pas l'encadré : il
              en porte la substance là où le regard passe de toute façon.

              La phrase se tient en français seul. Le terme arabe consacré
              vient en apposition, entre parenthèses, et non comme sujet ou
              complément : un lecteur francophone doit pouvoir lire la ligne
              d'un trait sans buter sur un mot qu'il ne déchiffre pas. Le
              segment arabe est isolé pour que les parenthèses restent de
              part et d'autre et ne basculent pas de l'autre côté.
            */}
            <strong className="note-titre">
              Ce que Mizan ne fera jamais à votre place
            </strong>
            <span className="note-ligne">
              Elle ne <strong>signifie</strong> pas : seul un huissier de
              justice{' '}
              <span className="incise-ar" dir="rtl">
                (عدل منفذ)
              </span>{' '}
              le peut.
            </span>
            <span className="note-ligne">
              Elle ne <strong>juge</strong> pas : le tribunal seul tranche.
            </span>
            <span className="note-ligne">
              Elle ne <strong>représente</strong> personne : c’est l’avocat
              qui plaide.
            </span>
            <span className="note-ligne note-ligne-fin">
              Elle calcule les délais, cite les articles, prépare le dossier.
            </span>
          </span>
        </div>
      </aside>

      <div className="content-area">
        <header className="topbar">
          <div className="breadcrumb">
            <span>Mizan</span>
            <span aria-hidden="true">/</span>
            <strong>{filsAriane[chemin] ?? 'Page'}</strong>
          </div>
          <p className="topbar-principe">L&apos;IA propose. Le droit dispose.</p>
        </header>
        <main className="page-content">{children}</main>
      </div>
    </div>
  );
}
