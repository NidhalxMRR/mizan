import type {
  Analyse,
  Interruption,
  InterruptionRetenue,
  ActeSansEffet,
  Source,
} from '@/lib/api';
import { TexteArabe } from '../components/etats';

/**
 * L'interruption de la prescription, rendue lisible.
 *
 * Le moteur sait depuis longtemps appliquer les articles 396 à 398 du COC.
 * Encore fallait-il que l'écran le montre : un délai qui repart à zéro, c'est
 * la différence entre une créance recouvrable et une créance perdue, et
 * personne ne le lit dans un JSON.
 *
 * Trois choses sont affichées, dans cet ordre, parce que c'est l'ordre dans
 * lequel un juriste les vérifie :
 *   1. l'échéance AVANT et APRÈS, et le nombre de jours gagnés ;
 *   2. quel acte a produit l'effet, à quelle date, sur quel article ;
 *   3. les actes qui n'ont RIEN interrompu, avec leur motif.
 *
 * Le point 3 n'est jamais masqué, même quand il fait mauvaise impression.
 * Un acte qu'on croit interruptif et qui ne l'est pas, c'est précisément ce
 * qui fait perdre un procès : le taire pour rendre l'écran plus flatteur
 * serait la pire chose que cette interface puisse faire.
 *
 * Aucune phrase juridique n'est rédigée ici. `fondement_fr`, `effet_fr`,
 * `motif_fr` et `resume_fr` viennent du moteur et sont affichés mot pour mot.
 */
export function BlocInterruption({ a }: { a: Analyse }) {
  const i = a.interruption;
  if (!i) return null;

  return (
    <section
      className={`panel bloc-espace interruption ${
        i.interrompu ? 'interruption-retenue' : 'interruption-nulle'
      }`}
      aria-label="Interruption de la prescription"
    >
      <div className="etat-entete">
        <div>
          <p className={`eyebrow ${i.interrompu ? 'eyebrow-teal' : ''}`}>
            INTERRUPTION DE LA PRESCRIPTION — COC ART. 396 À 398
          </p>
          <h2>
            {i.interrompu
              ? 'Le délai a été interrompu : il repart en entier'
              : "Aucun acte n'a interrompu le délai"}
          </h2>
        </div>
        <span
          className={`provenance ${
            i.interrompu ? 'provenance-verified' : 'provenance-abstain'
          }`}
        >
          {i.interrompu
            ? `${i.interruptions.length} acte${
                i.interruptions.length > 1 ? 's' : ''
              } retenu${i.interruptions.length > 1 ? 's' : ''}`
            : 'aucun acte retenu'}
        </span>
      </div>

      <Balance i={i} />

      <p className="interruption-resume">{i.resume_fr}</p>

      {i.interruptions.length > 0 ? (
        <div className="interruption-liste">
          <p className="interruption-soustitre">
            Ce qui a produit l&apos;effet
          </p>
          {i.interruptions.map((r) => (
            <ActeRetenu key={`${r.type}-${r.date}`} r={r} />
          ))}
        </div>
      ) : null}

      {i.actes_sans_effet.length > 0 ? (
        <div className="interruption-liste">
          <p className="interruption-soustitre interruption-soustitre-alerte">
            {i.actes_sans_effet.length} acte
            {i.actes_sans_effet.length > 1 ? 's' : ''} produit
            {i.actes_sans_effet.length > 1 ? 's' : ''} mais sans aucun effet
          </p>
          {i.actes_sans_effet.map((s) => (
            <ActeInutile key={`${s.type}-${s.date}`} s={s} />
          ))}
        </div>
      ) : null}

      {i.sources.length > 0 ? <SourcesInterruption sources={i.sources} /> : null}
    </section>
  );
}

/**
 * La balance : échéance avant, échéance après, jours gagnés.
 *
 * C'est la seule information que le jury doit retenir s'il ne lit rien
 * d'autre. Elle est donc traitée comme le compte à rebours : gros corps,
 * serif, et une flèche qui dit le sens de la lecture.
 *
 * Quand rien n'a été interrompu, les deux dates sont identiques — on ne
 * bricole pas un affichage triomphal sur une égalité.
 */
function Balance({ i }: { i: Interruption }) {
  return (
    <div className="balance">
      <div className="balance-borne">
        <p className="balance-libelle">Échéance sans interruption</p>
        {/* Le barré ne s'applique QUE si cette date a réellement été
            abandonnée. Barrer une date qui n'a pas bougé ferait croire à un
            gain là où il n'y en a aucun — exactement le contresens que ce
            bloc existe pour empêcher. */}
        <p
          className={`balance-date ${
            i.interrompu ? 'balance-date-avant' : 'balance-date-inchangee'
          }`}
        >
          {formatDate(i.echeance_initiale)}
        </p>
        <p className="balance-note">
          Délai courant depuis la facture du {formatDate(i.date_depart_initiale)}
        </p>
      </div>

      <div className="balance-fleche" aria-hidden="true">
        <span className="balance-fleche-trait" />
      </div>

      <div className="balance-borne">
        <p className="balance-libelle">Échéance retenue par le moteur</p>
        <p
          className={`balance-date ${
            i.interrompu ? 'balance-date-apres' : 'balance-date-inchangee'
          }`}
        >
          {formatDate(i.echeance_effective)}
        </p>
        <p className="balance-note">
          {i.interrompu ? (
            <>
              Le délai repart du {formatDate(i.date_depart_effective)}, date du
              dernier acte retenu
            </>
          ) : (
            <>Inchangée : le point de départ reste la date de la facture</>
          )}
        </p>
      </div>

      <div
        className={`balance-gain ${
          i.jours_gagnes > 0 ? 'balance-gain-positif' : 'balance-gain-nul'
        }`}
      >
        {/* Un seul nœud de texte : sinon React insère un séparateur entre le
            signe et le nombre, et « +50 » cesse d'être une chaîne contiguë
            dans le HTML — ce qui rend la preuve au `curl` inutilement
            fragile pour une raison purement technique. */}
        <p className="balance-gain-nombre">
          {`${i.jours_gagnes > 0 ? '+' : ''}${i.jours_gagnes.toLocaleString(
            'fr-FR',
          )}`}
        </p>
        <p className="balance-gain-unite">
          {`jour${Math.abs(i.jours_gagnes) > 1 ? 's' : ''} ${
            i.jours_gagnes > 0 ? 'gagnés' : 'gagné'
          }`}
        </p>
      </div>
    </div>
  );
}

/** Un acte retenu : ce qu'il est, ce qu'il fonde, ce qu'il produit. */
function ActeRetenu({ r }: { r: InterruptionRetenue }) {
  return (
    <article className="acte acte-retenu">
      <div className="acte-entete">
        <div className="acte-identite">
          <h3 className="acte-titre">{r.libelle_fr}</h3>
          <p className="acte-date">
            Acte du <strong>{formatDate(r.date)}</strong>
            {r.description ? <> — {r.description}</> : null}
          </p>
        </div>
        <span className="provenance provenance-verified acte-article">
          COC art. {r.article_cause}
        </span>
      </div>

      <p className="acte-fondement">{r.fondement_fr}</p>

      <p className="acte-effet">
        <span className="acte-effet-libelle">Effet — COC art. 398</span>
        {r.effet_fr}
      </p>

      <ul className="liste-nue acte-citations">
        {r.articles.map((s) => (
          <li key={`${s.code_id}-${s.article}`} className="citation">
            <span className="citation-ref">{s.short_fr}</span>
            <TexteArabe>{s.citation_ar}</TexteArabe>
            <p className="citation-fr">{s.label_fr}</p>
          </li>
        ))}
      </ul>
    </article>
  );
}

/**
 * Un acte sans effet.
 *
 * Le bloc le plus utile de l'écran. Il porte volontairement les couleurs de
 * l'alerte — pas celles de l'erreur technique : le système n'est pas en
 * panne, c'est la créance qui l'est. Le motif vient du moteur et détaille
 * l'écart en jours : on ne le résume pas.
 */
function ActeInutile({ s }: { s: ActeSansEffet }) {
  return (
    <article className="acte acte-sans-effet">
      <div className="acte-entete">
        <div className="acte-identite">
          <h3 className="acte-titre">{s.libelle_fr}</h3>
          <p className="acte-date">
            Acte du <strong>{formatDate(s.date)}</strong>
            {s.description ? <> — {s.description}</> : null}
          </p>
        </div>
        <span className="provenance provenance-danger acte-article">
          n&apos;a rien interrompu
        </span>
      </div>

      <p className="acte-motif">{s.motif_fr}</p>

      <ul className="liste-nue acte-citations">
        {s.articles.map((a) => (
          <li key={`${a.code_id}-${a.article}`} className="citation">
            <span className="citation-ref">{a.short_fr}</span>
            <TexteArabe>{a.citation_ar}</TexteArabe>
            <p className="citation-fr">{a.label_fr}</p>
          </li>
        ))}
      </ul>
    </article>
  );
}

/** Les articles mobilisés par le calcul d'interruption, tous confondus. */
function SourcesInterruption({ sources }: { sources: Source[] }) {
  return (
    <details className="interruption-sources">
      <summary className="interruption-sources-titre">
        {sources.length > 1
          ? `Les ${sources.length} articles mobilisés pour ce calcul d’interruption`
          : 'L’article mobilisé pour ce calcul d’interruption'}
      </summary>
      <ul className="liste-nue">
        {sources.map((s) => (
          <li key={`${s.code_id}-${s.article}`} className="citation">
            <span className="citation-ref">{s.short_fr}</span>
            <TexteArabe>{s.citation_ar}</TexteArabe>
            <p className="citation-fr">{s.label_fr}</p>
          </li>
        ))}
      </ul>
    </details>
  );
}

/** Même règle que la page : on affiche une date ISO, on ne la recalcule pas. */
function formatDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : iso;
}
