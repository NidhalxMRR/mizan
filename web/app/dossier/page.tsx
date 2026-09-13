import Link from 'next/link';
import { analyserDossier, API_URL, type Analyse } from '@/lib/api';
import { lireActesDepuisUrl, type ActeIllisible } from '@/lib/actes';
import { PanneApi, TexteArabe } from '../components/etats';
import { FormulaireDossier } from './formulaire';
import { DeposerPiece } from './deposer-piece';
import { DeclarerActes } from './declarer-actes';
import { BlocInterruption } from './interruption';
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
 *
 * Les actes interruptifs (COC art. 396 à 398) suivent exactement la même
 * règle : ils voyagent dans l'URL sous `acte=type:date[:texte]`, répétable
 * (voir `lib/actes.ts`), et sont transmis au moteur dans le même appel
 * serveur. Aucune interruption n'est calculée ici.
 */
export const dynamic = 'force-dynamic';

const DEFAUTS = {
  montant: '9520',
  date: '2025-11-03',
  activite: 'menuiserie',
};

/**
 * Les deux cas de démonstration, prêts à cliquer.
 *
 * Ce ne sont que des URL : elles n'embarquent aucun résultat. Le moteur
 * recalcule tout à chaque ouverture, et si l'API est éteinte l'écran le dit
 * au lieu d'afficher un chiffre d'archive. Le second cas est celui qu'un
 * jury doit voir — la sommation qui arrive trop tard et ne sert à rien.
 */
const CAS_DEMO = [
  {
    cle: 'ahmed-interrompu',
    titre: 'Ahmed, menuisier à Sfax — avec une sommation',
    detail:
      '9 520,000 DT, facture du 12/05/2026, sommation par huissier du 01/07/2026.',
    href:
      '/dossier?montant=9520&date=2026-05-12&activite=menuiserie' +
      '&acte=sommation_huissier%3A2026-07-01%3ASommation%20de%20payer%20signifi%C3%A9e%20%C3%A0%20la%20soci%C3%A9t%C3%A9%20d%C3%A9bitrice',
  },
  {
    cle: 'creance-prescrite',
    titre: 'Le piège — une créance de 2020 et une sommation de 2026',
    detail:
      '9 520,000 DT, facture du 15/01/2020, sommation du 01/01/2026 : elle arrive après la prescription.',
    href:
      '/dossier?montant=9520&date=2020-01-15&activite=menuiserie' +
      '&acte=sommation_huissier%3A2026-01-01%3ASommation%20signifi%C3%A9e%20apr%C3%A8s%20l%27expiration%20du%20d%C3%A9lai',
  },
] as const;

export default async function DossierPage(props: PageProps<'/dossier'>) {
  const params = await props.searchParams;
  const lire = (c: string) => {
    const v = params[c];
    return Array.isArray(v) ? v[0] : v;
  };

  const montant = lire('montant') ?? DEFAUTS.montant;
  const date = lire('date') ?? DEFAUTS.date;
  const activite = lire('activite') ?? DEFAUTS.activite;

  // `acte` est répétable : on lit le paramètre brut, pas seulement sa
  // première valeur. Ce qui n'a pas la forme attendue est conservé pour être
  // signalé — jamais silencieusement écarté.
  const { actes, illisibles } = lireActesDepuisUrl(params['acte']);

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
        // Omis quand la PME n'a rien déclaré : le moteur renvoie alors
        // `interruption: null`, ce qui est une information et non un vide.
        ...(actes.length > 0 ? { actes_interruptifs: actes } : {}),
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

      <CasDeDemonstration />

      {/*
        Le dépôt est placé AVANT le formulaire, et non en annexe plus bas.
        L'API savait lire une facture depuis le début, mais rien à l'écran ne
        le montrait : une capacité qu'on ne voit pas n'existe pas pour celui
        qui regarde. Le parcours naturel devient donc « je dépose ma facture,
        le moteur la lit, les champs se remplissent » — et la saisie manuelle
        reste possible juste en dessous pour qui n'a pas le PDF sous la main.
      */}
      <DeposerPiece activite={activite.trim() || 'menuiserie'} actes={actes} />

      <FormulaireDossier
        /*
          La `key` force le remontage du formulaire quand l'URL change.

          Sans elle, `useState(montantInitial)` ne se réévalue jamais après la
          première visite : une navigation côté client (report des valeurs
          lues dans le PDF, ou clic sur un cas de démonstration) met bien à
          jour l'URL et le calcul rendu côté serveur, mais les champs, eux,
          gardent l'ancienne saisie. On affichait alors une analyse du 12 mai
          2026 au-dessus d'un champ date resté au 3 novembre 2025 — deux
          dates contradictoires à l'écran, et c'est le formulaire qu'un
          artisan croit.
        */
        key={`${montant}|${date}|${activite}`}
        montantInitial={montant}
        dateInitiale={date}
        activiteInitiale={activite}
        actes={actes}
      />

      <DeclarerActes
        montant={montant}
        date={date}
        activite={activite.trim() || 'menuiserie'}
        actesInitiaux={actes}
      />

      {illisibles.length > 0 ? <ActesIllisibles liste={illisibles} /> : null}

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
          <BlocInterruption a={resultat.valeur} />
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
 * Les cas prêts à l'emploi.
 *
 * Des `Link`, pas des boutons : la démonstration ne demande aucune saisie au
 * clavier, et l'adresse reste visible et copiable dans la barre du
 * navigateur — ce qui permet de la rejouer au `curl` devant le jury.
 */
function CasDeDemonstration() {
  return (
    <section className="panel bloc-espace">
      <p className="eyebrow">DEUX CAS PRÊTS — AUCUNE SAISIE NÉCESSAIRE</p>
      <div className="cas-demo">
        {CAS_DEMO.map((c) => (
          <Link key={c.cle} href={c.href} className="cas">
            <span className="cas-titre">{c.titre}</span>
            <span className="cas-detail">{c.detail}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}

/**
 * Un acte d'URL mal formé.
 *
 * Il serait plus simple de l'ignorer. Ce serait aussi la faute la plus grave
 * possible ici : une PME qui a déclaré sa sommation et ne la voit nulle part
 * conclura que son délai n'a pas été interrompu. On dit donc précisément ce
 * qui n'a pas été compris.
 */
function ActesIllisibles({ liste }: { liste: ActeIllisible[] }) {
  return (
    <section className="panel bloc-espace bloc-panne" role="alert">
      <p className="eyebrow" style={{ color: 'var(--danger)' }}>
        {liste.length} ACTE{liste.length > 1 ? 'S' : ''} NON TRANSMIS AU MOTEUR
      </p>
      <h2>Une déclaration d&apos;acte n&apos;a pas pu être lue</h2>
      <p className="panne-motif">
        Ce qui suit figurait dans l&apos;adresse mais n&apos;a pas la forme
        attendue. Ces actes n&apos;ont donc PAS été soumis au moteur : le
        résultat affiché plus bas ne les prend pas en compte.
      </p>
      <ul className="liste-nue bloc-espace">
        {liste.map((i) => (
          <li key={i.brut} className="acte-illisible">
            <code className="acte-illisible-brut">acte={i.brut}</code>
            <span className="acte-illisible-motif">{i.motif}</span>
          </li>
        ))}
      </ul>
    </section>
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
      {/*
        Quand un acte a interrompu le délai, ce décompte le prend DÉJÀ en
        compte : il est calculé sur l'échéance reportée, pas sur celle de la
        facture. Sans cette phrase, un juriste voit deux cartes afficher la
        même date sans savoir si l'une additionne l'autre.
      */}
      {a.interruption?.jours_gagnes ? (
        <p className="rebours-note">
          Ce décompte tient déjà compte de l&apos;interruption détaillée
          ci-dessous.
        </p>
      ) : null}
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
      {/*
        `regime` est un identifiant interne (« goods_1y »). Devant un jury de
        juristes, un identifiant de code source n'a aucun sens et donne
        l'impression d'un prototype qui fuit ses entrailles. Le régime se dit
        en droit : une durée et son fondement. L'identifiant reste disponible
        pour qui inspecte l'API.
      */}
      <h2>
        {/*
          La durée doit se mesurer sur le délai LUI-MÊME, donc depuis son point
          de départ réel. Quand un acte a interrompu la prescription, ce point
          n'est plus la facture mais la date de l'acte (COC art. 398) : mesurer
          depuis la facture donnait « 415 jours » pour un régime d'un an.
        */}
        Délai retenu :{' '}
        {dureeRegimeFr(
          a.interruption?.date_depart_effective ?? a.date_facture,
          a.echeance,
        )}
      </h2>

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
            La sommation doit être signifiée par un huissier de justice{' '}
            <span lang="ar" dir="rtl" className="incise-ar">
              (عدل منفذ)
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
        signifiée par un huissier de justice{' '}
        <span lang="ar" dir="rtl" className="incise-ar">
          (عدل منفذ)
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
        {/*
          « moteur_deterministe » est le nom interne du calculateur. Ce que le
          jury doit lire, c'est la garantie que ce badge porte : ces articles
          viennent du corpus, pas d'un modèle de langage.
        */}
        <span className="provenance provenance-verified">
          {a.origine === 'moteur_deterministe'
            ? 'Calcul déterministe — aucun modèle de langage'
            : `Source : ${a.origine}`}
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

/**
 * La durée du régime, dite en droit plutôt qu'en identifiant.
 *
 * L'API renvoie « goods_1y » : un identifiant interne, sans le moindre sens
 * pour un juriste, et qui donne à l'écran l'air d'un prototype qui fuit ses
 * entrailles. La durée réelle se déduit des deux dates que le moteur fournit
 * déjà — on ne devine rien, on relit ce qu'il a calculé.
 */
function dureeRegimeFr(depart: string, echeance: string): string {
  const d = new Date(`${depart}T00:00:00Z`);
  const f = new Date(`${echeance}T00:00:00Z`);
  if (Number.isNaN(d.getTime()) || Number.isNaN(f.getTime())) return 'délai légal';

  const jours = Math.round((f.getTime() - d.getTime()) / 86400000);

  // Un régime annal se reconnaît à sa durée, pas au quantième d'arrivée : le
  // moteur place parfois l'échéance au même quantième (12/05/2026 →
  // 12/05/2027) et parfois à la veille (15/01/2020 → 14/01/2021, le jour de
  // départ ne comptant pas, COC art. 401). Les deux font un an ; comparer les
  // quantièmes affichait « 365 jours » dans un cas et « un an » dans l'autre.
  const ans = jours / 365;
  if (Number.isInteger(ans) && ans >= 1 && ans <= 30) {
    return ans === 1 ? 'un an' : `${ans} ans`;
  }
  // 366 : la même année civile, mais bissextile.
  if (jours === 366) return 'un an';

  return `${jours.toLocaleString('fr-FR')} jours`;
}

function Fait({ libelle, valeur }: { libelle: string; valeur: string }) {
  return (
    <div className="fait">
      <p className="fait-libelle">{libelle}</p>
      <p className="fait-valeur">{valeur}</p>
    </div>
  );
}
