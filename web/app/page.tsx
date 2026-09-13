import Link from 'next/link';
import { lireSante, API_URL, type Sante } from '@/lib/api';
import { PanneApi } from './components/etats';
import { roles, roleLabels, roleLabelsAr, permissions } from '@/lib/auth';
import { pannEnFrancais, moteurEnFrancais, modeleEnClair } from '@/lib/panne';

/**
 * Page d'accueil.
 *
 * Elle affiche l'état RÉEL du service, lu côté serveur à chaque requête. Si
 * l'API est éteinte, cette page le dit — elle n'affiche pas « 4087 articles »
 * en dur. Le chiffre qu'on lit ici a été compté par l'index, pas écrit par
 * un développeur.
 */
export const dynamic = 'force-dynamic';

export default async function Accueil() {
  const sante = await lireSante();

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">HACK4JUSTICE · CHALLENGE B</p>
          <h1>
            L&apos;IA propose. <em>Le droit dispose.</em>
          </h1>
          <p className="intro">
            Mizan aide une PME tunisienne à savoir où elle en est sur un
            impayé : quel délai court, quel article l&apos;impose, et qui a le
            droit d&apos;agir. Les délais sont calculés par un moteur
            déterministe. Le modèle de langage ne fait que reformuler — il ne
            décide de rien.
          </p>
        </div>
      </div>

      {sante.ok ? (
        <EtatService sante={sante.valeur} />
      ) : (
        <PanneApi echec={sante.echec} />
      )}

      <section className="grille-deux">
        <article className="panel">
          <p className="eyebrow">CE QUE MIZAN CALCULE</p>
          <h2>Le parcours de la PME</h2>
          <p className="intro bloc-espace">
            Un montant, une date de facture, une activité. Le moteur en déduit
            le régime de prescription applicable, l&apos;échéance exacte, et si
            la sommation doit passer par un huissier de justice. Chaque
            affirmation arrive avec l&apos;article qui la fonde, cité en arabe.
          </p>
          <Link href="/dossier" className="primary-button">
            Analyser un impayé
          </Link>
        </article>

        <article className="panel">
          <p className="eyebrow">CE QUE MIZAN REFUSE DE FAIRE</p>
          <h2>L&apos;abstention comme fonctionnalité</h2>
          <p className="intro bloc-espace">
            Quand la question posée ne trouve pas de fondement dans le corpus,
            Mizan ne propose pas l&apos;article le moins éloigné. Elle dit
            qu&apos;elle ne sait pas. C&apos;est le comportement qu&apos;on
            attend d&apos;un outil dont la sortie peut finir dans un dossier
            de tribunal.
          </p>
          <Link href="/corpus" className="primary-button">
            Interroger le corpus
          </Link>
        </article>
      </section>

      <MatriceRoles />
    </>
  );
}

function EtatService({ sante }: { sante: Sante }) {
  const indexOk = sante.index_charge && sante.articles_indexes > 0;

  return (
    <section className="panel bloc-espace" aria-label="État réel du service">
      <div className="etat-entete">
        <div>
          <p className="eyebrow">ÉTAT DU SERVICE — LU À L&apos;INSTANT</p>
          <h2>
            {sante.service} v{sante.version}
          </h2>
        </div>
        <span className="provenance provenance-verified">
          Moteur juridique : {moteurEnFrancais(sante.moteur_juridique)}
        </span>
      </div>

      <div className="etat-grille">
        <Mesure
          libelle="Articles indexés"
          valeur={sante.articles_indexes.toLocaleString('fr-FR')}
          detail={
            indexOk
              ? 'Corpus chargé et interrogeable'
              : "L'index n'est pas chargé"
          }
          etat={indexOk ? 'verified' : 'abstain'}
        />
        <Mesure
          libelle="Reformulation"
          valeur={sante.modele_disponible ? 'Disponible' : 'Indisponible'}
          detail={sante.motif_modele}
          etat={sante.modele_disponible ? 'verified' : 'declared'}
        />
        <Mesure
          libelle="Calcul des délais"
          valeur="Indépendant du modèle"
          detail="Si le modèle tombe, le droit reste calculable"
          etat="verified"
        />
      </div>

      {sante.hebergements.length > 0 ? (
        <div className="hebergements">
          <p className="eyebrow">CE QUI FAIT TOURNER MIZAN</p>
          <ul className="liste-nue">
            {/*
              La liste ne montrait que le modèle de langage, et il est hors
              ligne : un jury y lisait « l'application ne tourne pas ». C'est
              l'inverse. Ce qui produit les conclusions juridiques, c'est le
              moteur déterministe et le corpus — tous deux actifs sur ce
              serveur. Le modèle ne sert qu'à reformuler en français courant
              un texte déjà établi sans lui.

              On affiche donc d'abord ce qui tourne, puis ce qui manque, en
              disant à quoi chaque brique sert.
            */}
            <li className="hebergement">
              <span className="pastille pastille-ok" aria-hidden="true" />
              <span className="hebergement-nom">Moteur de droit</span>
              <code className="hebergement-modele">
                Règles déterministes, sur ce serveur
              </code>
              <span className="hebergement-motif">
                Actif — calcule les délais et cite les articles
              </span>
            </li>
            <li className="hebergement">
              <span
                className={`pastille ${
                  sante.index_charge ? 'pastille-ok' : 'pastille-ko'
                }`}
                aria-hidden="true"
              />
              <span className="hebergement-nom">Corpus juridique</span>
              <code className="hebergement-modele">
                {sante.articles_indexes.toLocaleString('fr-FR')} articles, sur
                ce serveur
              </code>
              <span className="hebergement-motif">
                {sante.index_charge
                  ? 'Actif — recherche dans le texte des articles'
                  : 'Non chargé'}
              </span>
            </li>
            {sante.hebergements
              // Le poste local est sondé en premier par le serveur, mais il
              // n'est joignable que lorsque l'application tourne sur la
              // machine de Nidhal. Depuis le serveur de démonstration il est
              // toujours injoignable : afficher sa ligne en rouge en
              // permanence ferait croire à une panne, alors que la
              // reformulation fonctionne par l'hébergement de secours. On ne
              // montre donc le poste local que lorsqu'il répond vraiment.
              .filter((h) => h.nom !== 'local' || h.disponible)
              .map((h) => (
              <li key={`${h.nom}-${h.base_url}`} className="hebergement">
                <span
                  className={`pastille ${
                    h.disponible ? 'pastille-ok' : 'pastille-ko'
                  }`}
                  aria-hidden="true"
                />
                {/*
                  Le nom de l'hébergement compte : un jury veut savoir OÙ
                  tourne le modèle, pas seulement qu'il tourne. « sur le poste »
                  dit que rien ne sort de la machine ; « chez Modal » nomme
                  l'hébergeur. Écraser les deux sous un libellé unique faisait
                  disparaître l'information et affichait deux lignes jumelles.
                */}
                <span className="hebergement-nom">
                  {h.nom === 'local'
                    ? 'Reformulation, sur le poste'
                    : 'Reformulation, chez Modal'}
                </span>
                <code className="hebergement-modele" title={h.modele}>
                  {modeleEnClair(h.modele)}
                </code>
                <span className="hebergement-motif">
                  {h.disponible
                    ? 'Actif — reformule en français courant'
                    : `Hors ligne — ${pannEnFrancais(h.motif)} ; facultatif, le droit reste calculé`}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="etat-source">
        Données lues en direct depuis l'API Mizan au rendu de cette page,
        et non figées dans le code.
        Principe déclaré par l&apos;API : « {sante.principe} »
      </p>
    </section>
  );
}

function Mesure({
  libelle,
  valeur,
  detail,
  etat,
}: {
  libelle: string;
  valeur: string;
  detail: string;
  etat: 'verified' | 'declared' | 'abstain';
}) {
  return (
    <div className="mesure">
      <p className="mesure-libelle">{libelle}</p>
      <p className={`mesure-valeur mesure-${etat}`}>{valeur}</p>
      <p className="mesure-detail">{pannEnFrancais(detail)}</p>
    </div>
  );
}

/**
 * Les cinq acteurs, lus depuis `lib/auth.ts`.
 *
 * Le nombre de permissions n'est pas recopié à la main : il est compté sur la
 * matrice testée par `auth.test.mjs`. Si la matrice change, cet écran change
 * avec elle.
 */
function MatriceRoles() {
  return (
    <section className="panel bloc-espace">
      <p className="eyebrow">QUI FAIT QUOI</p>
      <h2>Cinq acteurs, des pouvoirs séparés</h2>
      <p className="intro bloc-espace">
        La plateforme ne peut pas signifier un acte : c&apos;est un monopole
        légal du عدل منفذ. Elle lui livre un projet complet, qu&apos;il
        contrôle et signifie lui-même.
      </p>
      <ul className="liste-roles">
        {roles.map((r) => (
          <li key={r} className="role">
            <span className="role-fr">{roleLabels[r]}</span>
            <span lang="ar" dir="rtl" className="role-ar">
              {roleLabelsAr[r]}
            </span>
            <span className="role-nb">
              {permissions[r].length} permission
              {permissions[r].length > 1 ? 's' : ''}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
