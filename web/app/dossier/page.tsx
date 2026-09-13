import { analyserDossier, API_URL, type Analyse } from '@/lib/api';
import { PanneApi, TexteArabe } from '../components/etats';
import { FormulaireDossier } from './formulaire';
import { Reformulation } from './reformulation';

export const metadata = { title: 'Mon impayé — Mizan' };

/**
 * Le parcours PME.
 *
 * L'analyse est calculée CÔTÉ SERVEUR, à chaque requête, par un appel réel à
 * `/dossiers/analyser`. Le résultat est donc présent dans le HTML envoyé au
 * navigateur : c'est vérifiable au `curl`, et c'est le seul niveau de preuve
 * qui compte ici.
 *
 * La reformulation par le modèle, elle, reste un îlot client déclenché à la
 * demande — parce qu'elle est facultative et lente, et surtout parce qu'elle
 * ne doit jamais retarder l'affichage du droit.
 */
export const dynamic = 'force-dynamic';

const DEFAUTS = {
  montant: '9520',
  date: '2025-11-03',
  activite: 'menuiserie',
};

export default async function DossierPage(props: PageProps<'/dossier'>) {
  const params = await props.searchParams;
  const lire = (c: string) => {
    const v = params[c];
    return Array.isArray(v) ? v[0] : v;
  };

  const montant = lire('montant') ?? DEFAUTS.montant;
  const date = lire('date') ?? DEFAUTS.date;
  const activite = lire('activite') ?? DEFAUTS.activite;

  const valeur = Number(montant);
  const saisieValide = Number.isFinite(valeur) && valeur > 0;

  // On n'appelle l'API que si la saisie a une chance d'être acceptée. Un
  // aller-retour réseau pour apprendre qu'un champ est vide est du temps
  // perdu devant un jury.
  const resultat = saisieValide
    ? await analyserDossier({
        montant_tnd: valeur,
        date_facture: date,
        activite: activite.trim() || 'menuiserie',
      })
    : null;

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">PARCOURS PME</p>
          <h1>
            Où en est <em>mon impayé</em> ?
          </h1>
          <p className="intro">
            Le moteur calcule le délai de prescription applicable, la date
            d&apos;échéance et les suites possibles. Chaque conclusion est
            rattachée à l&apos;article qui la fonde. Rien n&apos;est estimé,
            rien n&apos;est arrondi.
          </p>
        </div>
      </div>

      <FormulaireDossier
        montantInitial={montant}
        dateInitiale={date}
        activiteInitiale={activite}
      />

      {!saisieValide ? (
        <div className="bloc-espace">
          <PanneApi
            echec={{
              genre: 'refus',
              url: `${API_URL}/dossiers/analyser`,
              message:
                'Le montant doit être un nombre strictement positif, en dinars. Aucun appel n\u2019a été fait au moteur.',
            }}
          />
        </div>
      ) : null}

      {resultat && !resultat.ok ? (
        <div className="bloc-espace">
          <PanneApi echec={resultat.echec} />
        </div>
      ) : null}

      {resultat && resultat.ok ? (
        <>
          <CompteARebours a={resultat.valeur} />
          <PourquoiCeDelai a={resultat.valeur} />
          {resultat.valeur.huissier_requis ? (
            <EncartHuissier a={resultat.valeur} />
          ) : (
            <EncartSansHuissier />
          )}
          <Etapes a={resultat.valeur} />
          <Articles a={resultat.valeur} />
          <Reformulation
            montant={valeur}
            date={date}
            activite={activite.trim() || 'menuiserie'}
            apiUrl={API_URL}
          />
        </>
      ) : null}
    </>
  );
}

/**
 * Le compte à rebours de prescription.
 *
 * `jours_restants` est signé : négatif quand le délai est dépassé. On
 * n'affiche jamais « -489 jours restants », qui ne veut rien dire pour un
 * artisan — on bascule la phrase entière.
 */
function CompteARebours({ a }: { a: Analyse }) {
  const jours = Math.abs(a.jours_restants);
  const classe = a.est_prescrit
    ? 'rebours-expire'
    : a.urgence === 'critical'
      ? 'rebours-critique'
      : a.urgence === 'warning'
        ? 'rebours-attention'
        : 'rebours-ok';
  const u = etiquetteUrgence(a.urgence);

  return (
    <section className={`panel bloc-espace rebours ${classe}`}>
      <p className="eyebrow">DÉLAI DE PRESCRIPTION</p>
      <p className="rebours-nombre">{jours.toLocaleString('fr-FR')}</p>
      <p className="rebours-unite">
        {a.est_prescrit
          ? `jour${jours > 1 ? 's' : ''} depuis l'expiration du délai`
          : `jour${jours > 1 ? 's' : ''} avant l'expiration du délai`}
      </p>
      <p className="rebours-phrase">
        {a.est_prescrit ? (
          <>
            Le délai est <strong>dépassé</strong> depuis le{' '}
            {formatDate(a.echeance)}. Une action reste matériellement possible,
            mais le débiteur peut opposer la prescription et l&apos;affaire
            s&apos;arrête là.
          </>
        ) : (
          <>
            Vous avez jusqu&apos;au <strong>{formatDate(a.echeance)}</strong>{' '}
            pour agir. Passé cette date, la créance se prescrit.
          </>
        )}
      </p>
      <span className={`provenance ${u.classe}`}>Niveau : {u.texte}</span>
    </section>
  );
}

function etiquetteUrgence(u: string): { texte: string; classe: string } {
  switch (u) {
    case 'expired':
      return { texte: 'délai expiré', classe: 'provenance-abstain' };
    case 'critical':
      return { texte: 'critique', classe: 'provenance-declared' };
    case 'warning':
      return { texte: 'à surveiller', classe: 'provenance-declared' };
    case 'ok':
      return { texte: 'le temps ne presse pas', classe: 'provenance-verified' };
    // Une valeur inconnue s'affiche telle quelle plutôt que traduite au
    // hasard : si le moteur produit un niveau nouveau, on veut le voir.
    default:
      return { texte: u, classe: 'provenance-abstain' };
  }
}

function PourquoiCeDelai({ a }: { a: Analyse }) {
  return (
    <section className="panel bloc-espace">
      <p className="eyebrow">POURQUOI CE DÉLAI ET PAS UN AUTRE</p>
      <h2>Régime retenu : {a.regime}</h2>
      <p className="motif-regime">{a.regime_reason_fr}</p>
      <div className="faits">
        <Fait libelle="Montant" valeur={`${formatMontant(a.montant_tnd)} DT`} />
        <Fait libelle="Facture du" valeur={formatDate(a.date_facture)} />
        <Fait libelle="Échéance" valeur={formatDate(a.echeance)} />
        <Fait libelle="Calculé le" valeur={formatDate(a.aujourdhui)} />
      </div>
    </section>
  );
}

/**
 * L'encart huissier.
 *
 * C'est la limite que Mizan s'impose, et le point le plus souvent mal
 * compris : la plateforme prépare l'acte, elle ne le signifie pas. Le
 * monopole du عدل منفذ n'est pas une contrainte technique qu'une version
 * ultérieure lèvera — c'est la loi (CPC art. 5 et 60).
 */
function EncartHuissier({ a }: { a: Analyse }) {
  return (
    <section className="panel bloc-espace encart-huissier">
      <div className="etat-entete">
        <div>
          <p className="eyebrow eyebrow-or">
            ACTE RÉSERVÉ — MIZAN NE PEUT PAS LE FAIRE À VOTRE PLACE
          </p>
          <h2>
            La sommation doit être signifiée par un{' '}
            <span lang="ar" dir="rtl" className="incise-ar">
              عدل منفذ
            </span>
          </h2>
        </div>
        <span className="provenance provenance-declared">
          {a.jours_francs} jours francs
        </span>
      </div>
      <p className="intro bloc-espace">
        Votre créance de {formatMontant(a.montant_tnd)} DT dépasse le seuil
        légal. L&apos;huissier de justice signifie la mise en demeure et laisse{' '}
        {a.jours_francs} jours francs au débiteur pour payer. Ce n&apos;est
        qu&apos;ensuite qu&apos;une injonction de payer peut être demandée.
      </p>
      <p className="intro">
        Mizan prépare le projet d&apos;acte — parties identifiées, montant
        calculé, articles cités et relus — puis le lui transmet. Elle ne le
        signifie pas : un logiciel n&apos;a pas ce pouvoir, et prétendre le
        contraire exposerait la PME à voir son acte annulé.
      </p>
    </section>
  );
}

function EncartSansHuissier() {
  return (
    <section className="panel bloc-espace">
      <p className="eyebrow">FORMALISME</p>
      <h2>Sommation par huissier non exigée à ce montant</h2>
      <p className="intro bloc-espace">
        En dessous du seuil légal, la mise en demeure n&apos;a pas à être
        signifiée par un{' '}
        <span lang="ar" dir="rtl" className="incise-ar">
          عدل منفذ
        </span>
        . Une lettre recommandée avec accusé de réception suffit à faire courir
        les effets du retard.
      </p>
    </section>
  );
}

function Etapes({ a }: { a: Analyse }) {
  if (a.etapes.length === 0) return null;
  return (
    <section className="panel bloc-espace">
      <p className="eyebrow">CE QUE VOUS POUVEZ FAIRE, DANS L&apos;ORDRE</p>
      <h2>
        {a.etapes.length} étape{a.etapes.length > 1 ? 's' : ''} calculée
        {a.etapes.length > 1 ? 's' : ''} par le moteur
      </h2>
      <ol className="etapes">
        {a.etapes.map((e) => (
          <li key={e.order} className="etape">
            <span className="etape-numero" aria-hidden="true">
              {e.order}
            </span>
            <div className="etape-corps">
              <h3 className="etape-titre">{e.title_fr}</h3>
              <p className="etape-detail">{e.detail_fr}</p>
              <TexteArabe className="etape-citation">
                {e.citation_ar}
              </TexteArabe>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Articles({ a }: { a: Analyse }) {
  return (
    <section className="panel bloc-espace">
      <div className="etat-entete">
        <div>
          <p className="eyebrow">LES ARTICLES QUI FONDENT CE QUI PRÉCÈDE</p>
          <h2>
            {a.sources.length} référence{a.sources.length > 1 ? 's' : ''} relue
            {a.sources.length > 1 ? 's' : ''} dans le corpus
          </h2>
        </div>
        <span className="provenance provenance-verified">
          Source : {a.origine}
        </span>
      </div>
      <ul className="liste-nue bloc-espace">
        {a.sources.map((s) => (
          <li key={`${s.code_id}-${s.article}`} className="citation">
            <span className="citation-ref">{s.short_fr}</span>
            <TexteArabe>{s.citation_ar}</TexteArabe>
            <p className="citation-fr">{s.label_fr}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

// --- Mise en forme ----------------------------------------------------------

function formatMontant(n: number): string {
  return n.toLocaleString('fr-FR', {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  });
}

/**
 * L'API renvoie des dates ISO. On les affiche au format tunisien sans jamais
 * les recalculer : si la chaîne n'a pas la forme attendue, on la rend telle
 * quelle plutôt que d'afficher « Invalid Date ».
 */
function formatDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : iso;
}

function Fait({ libelle, valeur }: { libelle: string; valeur: string }) {
  return (
    <div className="fait">
      <p className="fait-libelle">{libelle}</p>
      <p className="fait-valeur">{valeur}</p>
    </div>
  );
}
