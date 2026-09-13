import {
  rechercherCorpus,
  lireSante,
  API_URL,
  type Recherche,
  type ArticleTrouve,
} from '@/lib/api';
import { PanneApi, TexteArabe } from '../components/etats';
import { ChampRecherche } from './champ';

export const metadata = { title: 'Le corpus — Mizan' };

/**
 * La recherche dans le corpus.
 *
 * C'est ici que se joue la différence du projet. N'importe quel outil sait
 * renvoyer les cinq articles les moins éloignés d'une question. Mizan fait
 * autre chose : elle applique un garde-fou (`packages/legal/gate.py`) qui
 * vérifie que les termes de la question figurent réellement dans le texte
 * trouvé, et quand ce n'est pas le cas elle le dit au lieu de laisser croire
 * que le corpus a répondu.
 *
 * L'abstention est donc traitée comme un résultat de plein droit, pas comme
 * une erreur : elle a son propre bloc, sa propre couleur (grise, pas rouge —
 * ne pas savoir n'est pas une panne), et elle passe AVANT les articles pour
 * qu'on ne puisse pas la manquer.
 */
export const dynamic = 'force-dynamic';

export default async function CorpusPage(props: PageProps<'/corpus'>) {
  const params = await props.searchParams;
  const brut = params.q;
  const q = (Array.isArray(brut) ? brut[0] : brut)?.trim() ?? '';

  // Les deux appels sont indépendants : on ne les met pas en file d'attente
  // l'un derrière l'autre.
  const [sante, recherche] = await Promise.all([
    lireSante(),
    q ? rechercherCorpus(q, 5) : Promise.resolve(null),
  ]);

  const nbArticles =
    sante.ok && sante.valeur.index_charge ? sante.valeur.articles_indexes : null;

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">CORPUS JURIDIQUE TUNISIEN</p>
          <h1>
            Ce que le corpus dit — <em>et ce qu&apos;il ne dit pas</em>
          </h1>
          <p className="intro">
            {nbArticles !== null ? (
              <>
                {nbArticles.toLocaleString('fr-FR')} articles indexés, comptés
                par l&apos;API à l&apos;instant. La recherche renvoie des
                articles réels, ou bien elle renvoie une abstention motivée.
                Jamais une référence approchante présentée comme une réponse.
              </>
            ) : (
              <>
                L&apos;index n&apos;a pas pu être interrogé : le nombre
                d&apos;articles n&apos;est pas affiché plutôt que d&apos;être
                supposé.
              </>
            )}
          </p>
        </div>
      </div>

      <ChampRecherche requeteInitiale={q} />

      {!q ? <Invitation /> : null}

      {recherche && !recherche.ok ? (
        <div className="bloc-espace">
          <PanneApi echec={recherche.echec} />
        </div>
      ) : null}

      {recherche && recherche.ok ? (
        <Resultats r={recherche.valeur} />
      ) : null}

      <p className="etat-source bloc-espace">
        Recherche servie par <code>{API_URL}/corpus/rechercher</code> — index
        Recherche effectuée sur ce poste, aucun appel vers l’extérieur.
      </p>
    </>
  );
}

function Invitation() {
  return (
    <section className="panel bloc-espace">
      <p className="eyebrow">AUCUNE RECHERCHE LANCÉE</p>
      <h2>Posez une question, ou prenez un essai rapide ci-dessus</h2>
      <p className="intro bloc-espace">
        Rien n&apos;est affiché tant que rien n&apos;a été demandé. Le dernier
        essai rapide — une recette de cuisine — est le plus instructif : il
        montre ce que Mizan fait quand la réponse n&apos;existe pas dans le
        corpus.
      </p>
    </section>
  );
}

function Resultats({ r }: { r: Recherche }) {
  return (
    <>
      {!r.fonde ? <Abstention r={r} /> : <Fondee r={r} />}

      {r.resultats.length > 0 ? (
        <section className="bloc-espace">
          {!r.fonde ? (
            <p className="avert-non-fonde">
              Les {r.resultats.length} textes ci-dessous sont ceux que l&apos;index
              a rapprochés de votre question. Ils sont montrés pour que vous
              puissiez juger vous-même — <strong>Mizan ne les présente pas
              comme une réponse</strong>.
            </p>
          ) : null}

          <ul className="liste-nue">
            {r.resultats.map((a) => (
              <Article key={a.id} a={a} fonde={r.fonde} />
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}

/**
 * Le bloc d'abstention.
 *
 * Gris, et non rouge : `--abstain` existe pour ça dans les jetons. Une
 * abstention n'est pas une panne, c'est une décision du système. Le message
 * vient de l'API (`gate.ABSTAIN_MESSAGE`) — il n'est pas recopié ici, sinon
 * les deux finiraient par diverger.
 */
function Abstention({ r }: { r: Recherche }) {
  return (
    <section className="panel bloc-espace bloc-abstention">
      <span className="provenance provenance-abstain">
        ABSTENTION MOTIVÉE — GARDE-FOU DÉCLENCHÉ
      </span>

      <p className="abstention-message">
        {r.message ??
          "Le corpus ne répond pas à cette question avec une confiance suffisante."}
      </p>

      {r.motif_abstention ? (
        <p className="abstention-motif">
          Motif retourné par le garde-fou : <strong>{r.motif_abstention}</strong>
        </p>
      ) : null}

      <p className="abstention-explication">
        Un moteur de recherche ordinaire aurait affiché les mêmes textes sans
        rien dire, et vous auriez pu croire qu&apos;ils répondaient à votre
        question. C&apos;est ce comportement-là que Mizan refuse : une
        référence fausse dans un dossier de tribunal coûte plus cher
        qu&apos;une absence de réponse.
      </p>

      <p className="abstention-requete">
        Question posée :{' '}
        <span
          lang={estArabe(r.requete) ? 'ar' : 'fr'}
          dir={estArabe(r.requete) ? 'rtl' : 'ltr'}
          className="abstention-requete-texte"
        >
          {r.requete}
        </span>{' '}
        — {r.nombre} texte{r.nombre > 1 ? 's' : ''} rapproché
        {r.nombre > 1 ? 's' : ''}, 0 retenu.
      </p>
    </section>
  );
}

function Fondee({ r }: { r: Recherche }) {
  return (
    <section className="panel bloc-espace">
      <div className="etat-entete">
        <div>
          <p className="eyebrow">LE CORPUS RÉPOND</p>
          <h2>
            {r.nombre} article{r.nombre > 1 ? 's' : ''} retenu
            {r.nombre > 1 ? 's' : ''} pour «&nbsp;
            <span
              lang={estArabe(r.requete) ? 'ar' : 'fr'}
              dir={estArabe(r.requete) ? 'rtl' : 'ltr'}
              className="incise-ar"
            >
              {r.requete}
            </span>
            &nbsp;»
          </h2>
        </div>
        <span className="provenance provenance-verified">
          Garde-fou passé : termes retrouvés dans le texte
        </span>
      </div>
      <p className="intro bloc-espace">
        Les termes de votre question figurent réellement dans les textes
        ci-dessous. C&apos;est ce que vérifie le garde-fou avant d&apos;autoriser
        Mizan à présenter ces articles comme une réponse.
      </p>
    </section>
  );
}

function Article({ a, fonde }: { a: ArticleTrouve; fonde: boolean }) {
  return (
    <li className={`panel article ${fonde ? 'article-fonde' : 'article-doute'}`}>
      <div className="article-entete">
        <div className="article-identite">
          <span className="citation-ref">{a.citation_ar}</span>
          <p className="article-code-fr">{a.code_fr}</p>
          <p lang="ar" dir="rtl" className="article-code-ar">
            {a.code_ar}
          </p>
        </div>
        <div className="article-meta">
          <span className="article-score" title="Force de la correspondance entre votre question et cet article">
            score {a.score.toFixed(2)}
          </span>
          <code className="article-id">{a.id}</code>
        </div>
      </div>

      <TexteArabe className="article-texte">{a.text_ar}</TexteArabe>
    </li>
  );
}

/** Détection de script : décide de `dir` sans rien deviner sur la langue. */
function estArabe(s: string): boolean {
  return /[\u0600-\u06FF]/.test(s);
}
