'use client';

import { useRouter } from 'next/navigation';
import { useState, useTransition } from 'react';

/**
 * Le champ de recherche du corpus.
 *
 * Comme le formulaire du dossier, il pousse la requête dans l'URL et laisse
 * la page se rendre côté serveur : les articles arabes sont alors dans le
 * HTML, donc vérifiables autrement que sur parole.
 *
 * Les exemples proposés ne sont pas des résultats : ce sont des requêtes à
 * un clic. Le dernier est là exprès — il ne trouve rien, et c'est ce que le
 * jury doit voir.
 */

const EXEMPLES = [
  { q: 'التقادم', note: 'prescription' },
  { q: 'الفاتورة', note: 'facture' },
  { q: 'عدل منفذ', note: 'huissier' },
  { q: 'الصلح', note: 'conciliation' },
  { q: 'recette de couscous au poisson', note: 'hors corpus — ne trouve rien' },
];

export function ChampRecherche({ requeteInitiale }: { requeteInitiale: string }) {
  const router = useRouter();
  const [enCours, demarrer] = useTransition();
  const [q, setQ] = useState(requeteInitiale);

  function lancer(requete: string) {
    const propre = requete.trim();
    if (!propre) return;
    demarrer(() => {
      router.push(`/corpus?q=${encodeURIComponent(propre)}`, { scroll: false });
    });
  }

  return (
    <section className="panel">
      <p className="eyebrow">RECHERCHE DANS LE TEXTE DES ARTICLES</p>
      <form
        className="recherche"
        onSubmit={(e) => {
          e.preventDefault();
          lancer(q);
        }}
      >
        <label htmlFor="q" className="recherche-label">
          Votre question, de préférence en arabe
        </label>
        <div className="recherche-ligne">
          <input
            id="q"
            name="q"
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="التقادم"
            autoComplete="off"
            className="recherche-input"
          />
          <button type="submit" className="primary-button" disabled={enCours}>
            {enCours ? 'Recherche…' : 'Chercher'}
          </button>
        </div>
      </form>

      <div className="exemples">
        <p className="exemples-titre">Essais rapides :</p>
        <div className="exemples-liste">
          {EXEMPLES.map((e) => (
            <button
              key={e.q}
              type="button"
              className="exemple"
              onClick={() => {
                setQ(e.q);
                lancer(e.q);
              }}
              disabled={enCours}
            >
              <span
                lang={/[\u0600-\u06FF]/.test(e.q) ? 'ar' : 'fr'}
                dir={/[\u0600-\u06FF]/.test(e.q) ? 'rtl' : 'ltr'}
                className="exemple-q"
              >
                {e.q}
              </span>
              <span className="exemple-note">{e.note}</span>
            </button>
          ))}
        </div>
      </div>

      {enCours ? (
        <p className="formulaire-attente" role="status">
          Interrogation de l&apos;index en cours…
        </p>
      ) : null}
    </section>
  );
}
