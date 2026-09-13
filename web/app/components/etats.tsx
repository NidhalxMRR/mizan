import type { EchecApi } from '@/lib/api';

/**
 * Ce qu'on affiche quand l'API ne répond pas.
 *
 * Le réflexe habituel serait d'afficher un jeu de données d'exemple pour que
 * l'écran reste présentable. Ce projet fait l'inverse : un écran vide qui dit
 * pourquoi il est vide vaut mieux qu'un écran rempli de chiffres qui ne
 * viennent de nulle part. La commande de relance est donnée en clair, parce
 * qu'en démonstration on n'a pas le temps de la chercher.
 */
export function PanneApi({ echec }: { echec: EchecApi }) {
  const injoignable = echec.genre === 'injoignable';
  const titre = injoignable
    ? "L'API Mizan ne répond pas"
    : echec.genre === 'refus'
      ? 'Demande refusée par le moteur'
      : `Erreur du service${echec.statut ? ` (HTTP ${echec.statut})` : ''}`;

  return (
    <div className="panel bloc-panne" role="alert">
      <p className="eyebrow" style={{ color: 'var(--danger)' }}>
        AUCUNE DONNÉE AFFICHÉE
      </p>
      <h2>{titre}</h2>
      <p className="panne-motif">{echec.message}</p>
      {injoignable ? (
        <div className="panne-remede">
          <p className="panne-remede-titre">Pour la relancer :</p>
          <code className="panne-commande">
            cd ~/mizan &amp;&amp; .venv/bin/uvicorn api.main:app --port 8820
          </code>
        </div>
      ) : null}
      <p className="panne-url">
        Appel : <code>{echec.url}</code>
      </p>
      <p className="panne-serment">
        Mizan n&apos;affiche aucune donnée d&apos;exemple à la place. Ce qui
        manque ici manque vraiment.
      </p>
    </div>
  );
}

/**
 * Un article du corpus, en arabe.
 *
 * La page est en français, donc en LTR. Le texte arabe doit basculer en RTL
 * sans entraîner la mise en page avec lui : `unicode-bidi: isolate` dans
 * `.legal-ar` s'en charge, et l'attribut `dir="rtl"` explicite évite que le
 * navigateur devine mal sur un texte qui commence par un chiffre.
 */
export function TexteArabe({
  children,
  className = '',
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <p lang="ar" dir="rtl" className={`legal-ar ${className}`.trim()}>
      {children}
    </p>
  );
}

/** Le squelette d'attente. Aucun chiffre : on n'annonce pas un résultat. */
export function EnAttente({ lignes = 3 }: { lignes?: number }) {
  return (
    <div className="attente" aria-hidden="true">
      {Array.from({ length: lignes }, (_, i) => (
        <span key={i} className="attente-ligne" />
      ))}
    </div>
  );
}
