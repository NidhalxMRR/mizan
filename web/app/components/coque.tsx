'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

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
        </nav>

        <div className="security-note">
          <span aria-hidden="true">🔒</span>
          <span>
            {/*
              La phrase se tient en français seul. Le terme arabe consacré
              vient en apposition, entre parenthèses, et non comme sujet ou
              complément : un lecteur francophone doit pouvoir lire la ligne
              d'un trait sans buter sur un mot qu'il ne déchiffre pas. Le
              segment arabe est isolé pour que les parenthèses restent de
              part et d'autre et ne basculent pas de l'autre côté.
            */}
            Seul un <strong>huissier de justice</strong>{' '}
            <span className="incise-ar" dir="rtl">
              (عدل منفذ)
            </span>{' '}
            peut signifier un acte. Mizan prépare le dossier, elle ne le
            signifie pas.
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
