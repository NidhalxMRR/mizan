'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import {
  envoyerAuAgent,
  lireCapacites,
  type ArticleCite,
  type EchecAgent,
  type ReponseAgent,
} from './service';
import { lireSession, type SessionMizan } from './session';
import {
  EVENEMENT_SESSION,
  installerLePontDeConnexion,
} from './pont-connexion';
import { suggestionsPour, type Suggestion } from './suggestions';

/**
 * La bulle de dialogue de l'agent Mizan.
 *
 * Elle est montée sur toutes les pages et ne quitte jamais celle qu'on lit :
 * on pose une question depuis « Mon impayé » sans perdre son formulaire.
 *
 * TROIS PARTIS PRIS, QUI SONT LE PROJET LUI-MÊME
 * ----------------------------------------------
 * 1. L'organisation et le rôle sont écrits en permanence dans l'en-tête. Ce
 *    n'est pas un ornement : c'est la preuve, à l'écran, que l'agent n'agit
 *    jamais « en général » mais toujours au nom d'une entreprise précise et
 *    avec les droits de celle-ci. Ils viennent du serveur, jamais d'un choix
 *    local.
 *
 * 2. Un refus de droit et une abstention ne sont PAS traités comme des
 *    pannes. Un refus fondé sur le monopole de l'huissier est une réponse
 *    juridique exacte, et une abstention devant une question hors du droit
 *    tunisien est une fonctionnalité revendiquée. Ils ont donc chacun leur
 *    traitement visuel, distinct de celui d'une avarie — jamais un rouge
 *    d'erreur technique.
 *
 * 3. Rien n'est masqué en mode dégradé. Quand le modèle de langage ne peut
 *    pas reformuler, le calcul juridique a pourtant bien eu lieu : la réponse
 *    s'affiche, avec une ligne qui dit que seule la mise en forme manque.
 *
 * L'ATTENTE
 * ---------
 * Le modèle met de douze à vingt-sept secondes. Un écran figé pendant vingt
 * secondes se lit comme une panne, y compris — surtout — depuis le fond d'une
 * salle. L'indicateur d'attente annonce donc ce que la plateforme est en
 * train de faire, en français, et l'annonce change au fil des secondes. Tout
 * est en CSS pur : pas de bibliothèque, pas de police distante, pas de
 * requête réseau. La salle n'a peut-être pas de wifi.
 */

type Tour =
  | { qui: 'personne'; id: number; texte: string }
  | { qui: 'agent'; id: number; reponse: ReponseAgent }
  | { qui: 'avarie'; id: number; echec: EchecAgent };

/**
 * Les phases annoncées pendant l'attente.
 *
 * Elles décrivent ce que la plateforme fait réellement, dans l'ordre où elle
 * le fait : elle lit la demande, elle cherche dans le corpus indexé, elle
 * calcule les délais, puis elle fait mettre le résultat en français. Aucune
 * n'est inventée pour meubler, et la dernière reste affichée tant que la
 * réponse n'est pas arrivée — on ne promet jamais « presque fini ».
 */
const PHASES: { a: number; texte: string }[] = [
  { a: 0, texte: 'Je lis votre demande…' },
  { a: 3500, texte: 'Je consulte le corpus des codes tunisiens…' },
  { a: 9000, texte: 'Je calcule les délais…' },
  { a: 15000, texte: 'Je vérifie les articles qui fondent la réponse…' },
  { a: 22000, texte: 'Je mets la réponse en français courant…' },
];

function phaseAu(ms: number): string {
  let courante = PHASES[0].texte;
  for (const p of PHASES) if (ms >= p.a) courante = p.texte;
  return courante;
}

/**
 * La phrase qui rassure, sous l'annonce de phase.
 *
 * Défaut vu en relisant la capture d'attente : « Quelques secondes sont
 * normales » restait affichée telle quelle à la vingt-cinquième seconde. Une
 * phrase qui promet « quelques secondes » depuis une demi-minute cesse de
 * rassurer et se met à inquiéter — le jury la lit comme l'aveu d'un blocage.
 *
 * Elle change donc de registre avec le temps écoulé : d'abord elle explique
 * l'ordre des opérations, ensuite elle assume la durée, enfin elle rappelle
 * qu'on n'a pas abandonné. À aucun moment elle n'annonce « presque fini » :
 * on ne connaît pas le temps restant, et le promettre serait la seule vraie
 * faute possible ici.
 */
function rassuranceAu(ms: number): string {
  if (ms < 12000) {
    return 'Le calcul juridique est fait avant la mise en forme. Quelques secondes sont normales.';
  }
  if (ms < 30000) {
    return 'La mise en français prend plus de temps que le calcul. Le résultat, lui, est déjà arrêté.';
  }
  return 'C’est plus long que d’habitude, mais rien n’est perdu : je continue et la réponse s’affichera ici.';
}

/** La référence d'un article, en français, sans jargon ni identifiant. */
function referenceDe(a: ArticleCite): string {
  const code = a.label_fr || a.code_fr || a.short_fr || a.code_id || '';
  const numero = a.article !== undefined && a.article !== null ? `${a.article}` : '';
  if (code && numero) return `${code} — article ${numero}`;
  if (code) return code;
  if (numero) return `Article ${numero}`;
  return 'Article cité';
}

function texteArabeDe(a: ArticleCite): string {
  return (a.citation_ar || a.text_ar || '').trim();
}

let compteur = 0;
const prochainId = () => ++compteur;

export function BulleAgent() {
  const [ouverte, setOuverte] = useState(false);
  const [session, setSession] = useState<SessionMizan | null>(null);
  const [sessionLue, setSessionLue] = useState(false);
  const [tours, setTours] = useState<Tour[]>([]);
  const [saisie, setSaisie] = useState('');
  const [enAttente, setEnAttente] = useState(false);
  const [attenteMs, setAttenteMs] = useState(0);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);

  const filRef = useRef<HTMLDivElement | null>(null);
  const champRef = useRef<HTMLTextAreaElement | null>(null);

  /**
   * Le champ grandit avec ce qu'on y écrit.
   *
   * Défaut vu à la relecture des captures, aux deux largeurs : avec une seule
   * ligne fixe, la question « Ma créance de 9520 DT du 12/05/2026 est-elle
   * encore récupérable ? » s'affichait coupée en plein milieu. L'utilisateur
   * ne relisait donc pas ce qu'il s'apprêtait à envoyer. Le champ se
   * redimensionne sur son contenu, borné par `max-height` en CSS au-delà
   * duquel il défile — sans quoi un long collage mangerait tout le fil.
   */
  const ajusterLaHauteur = useCallback(() => {
    const champ = champRef.current;
    if (!champ) return;
    champ.style.height = 'auto';
    champ.style.height = `${champ.scrollHeight}px`;
  }, []);

  useEffect(() => {
    ajusterLaHauteur();
  }, [saisie, ouverte, ajusterLaHauteur]);

  // --- La session ---------------------------------------------------------
  // Le pont est installé au montage, donc avant que l'écran de connexion ne
  // soit utilisé. Il capte le jeton que cet écran reçoit puis jette.
  useEffect(() => {
    installerLePontDeConnexion();
    setSession(lireSession());
    setSessionLue(true);

    const surSession = (e: Event) => {
      const detail = (e as CustomEvent<SessionMizan | null>).detail;
      setSession(detail ?? lireSession());
    };
    // `storage` couvre le cas de la connexion faite dans un autre onglet.
    const surStockage = () => setSession(lireSession());

    window.addEventListener(EVENEMENT_SESSION, surSession);
    window.addEventListener('storage', surStockage);
    return () => {
      window.removeEventListener(EVENEMENT_SESSION, surSession);
      window.removeEventListener('storage', surStockage);
    };
  }, []);

  // --- Les suggestions, tirées du serveur et donc justes pour ce rôle ------
  useEffect(() => {
    if (!ouverte || !session?.jeton) return;
    let vivant = true;
    lireCapacites(session.jeton).then((r) => {
      if (!vivant) return;
      // Un échec ici ne s'affiche pas : l'absence de suggestions n'empêche
      // personne d'écrire sa question. On ne dérange pas pour ça.
      if (r.ok) setSuggestions(suggestionsPour(r.valeur.capacites ?? []));
    });
    return () => {
      vivant = false;
    };
  }, [ouverte, session?.jeton]);

  // --- Le compteur qui fait vivre l'indicateur d'attente -------------------
  useEffect(() => {
    if (!enAttente) {
      setAttenteMs(0);
      return;
    }
    const debut = Date.now();
    const minuteur = window.setInterval(
      () => setAttenteMs(Date.now() - debut),
      250,
    );
    return () => window.clearInterval(minuteur);
  }, [enAttente]);

  // --- On reste toujours au bas du fil ------------------------------------
  useEffect(() => {
    const fil = filRef.current;
    if (fil) fil.scrollTop = fil.scrollHeight;
  }, [tours, enAttente, attenteMs]);

  // --- Fermeture au clavier ------------------------------------------------
  useEffect(() => {
    if (!ouverte) return;
    const surTouche = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOuverte(false);
    };
    window.addEventListener('keydown', surTouche);
    return () => window.removeEventListener('keydown', surTouche);
  }, [ouverte]);

  const demander = useCallback(
    async (question: string) => {
      const propre = question.trim();
      if (!propre || enAttente) return;
      const jeton = session?.jeton;
      if (!jeton) return;

      setTours((t) => [
        ...t,
        { qui: 'personne', id: prochainId(), texte: propre },
      ]);
      setSaisie('');
      setSuggestions([]);
      setEnAttente(true);

      const r = await envoyerAuAgent(jeton, propre);

      setEnAttente(false);
      setTours((t) => [
        ...t,
        r.ok
          ? { qui: 'agent', id: prochainId(), reponse: r.valeur }
          : { qui: 'avarie', id: prochainId(), echec: r.echec },
      ]);
    },
    [enAttente, session?.jeton],
  );

  // L'en-tête doit tenir même avant la première réponse : on prend d'abord ce
  // que le serveur a confirmé dans le dernier tour, sinon ce que la connexion
  // avait annoncé. Jamais une valeur devinée.
  const dernierAgent = [...tours]
    .reverse()
    .find((t): t is Extract<Tour, { qui: 'agent' }> => t.qui === 'agent');
  const organisation =
    dernierAgent?.reponse.identite?.nom_organisation ||
    session?.nomOrganisation ||
    '';
  const role =
    dernierAgent?.reponse.identite?.libelle_role || session?.libelleRole || '';

  return (
    <>
      {/* Une seule affordance de fermeture.
       *
       * Défaut vu sur la capture à 479 px : la pastille flottante proposait
       * « Fermer » en bas à droite pendant que l'en-tête du panneau portait
       * déjà une croix en haut à droite. Deux commandes pour le même geste,
       * de deux styles opposés, aux deux coins opposés de l'écran : le
       * lecteur hésite, et l'hésitation se lit comme un défaut de
       * fabrication. Le déclencheur disparaît donc tant que le panneau est
       * ouvert — il n'a plus rien à déclencher. La croix de l'en-tête reste
       * la seule sortie, avec la touche Échap et le voile. */}
      {!ouverte ? (
        <button
          type="button"
          className="agent-declencheur"
          onClick={() => {
            setOuverte(true);
            window.setTimeout(() => champRef.current?.focus(), 120);
          }}
          aria-expanded={false}
          aria-controls="agent-panneau"
          data-test="agent-declencheur"
        >
          <span className="agent-declencheur-marque" aria-hidden="true">
            ⚖
          </span>
          {/*
            Le libellé ne nomme pas la plateforme. « Demander à Mizan »
            s'entend « demander à Mazen » — un prénom courant en Tunisie — et
            laisse croire qu'on écrit à une personne, au moment précis où le
            projet veut faire comprendre le contraire : la plateforme calcule,
            elle ne conseille pas. « Poser une question juridique » dit ce que
            le bouton fait, sans prêter de visage à un moteur.
          */}
          <span className="agent-declencheur-texte">
            Poser une question juridique
          </span>
        </button>
      ) : null}

      {ouverte ? (
        <>
        {/* Le voile.
         *
         * Sans lui, le titre de la page restait lisible autour du panneau et
         * se faisait couper net par son bord : on ne savait plus si l'on
         * lisait une couche posée par-dessus la page ou un bloc inséré
         * dedans. Le voile tranche la question en une fraction de seconde.
         * Il est teinté du bleu de l'identité, pas d'un noir d'obturateur,
         * et il ferme au clic comme la croix. */}
        <div
          className="agent-voile"
          onClick={() => setOuverte(false)}
          aria-hidden="true"
          data-test="agent-voile"
        />
        <section
          id="agent-panneau"
          className="agent-panneau"
          role="dialog"
          aria-modal="true"
          aria-label="Assistant juridique Mizan"
          data-test="agent-panneau"
        >
          {/* --- L'en-tête : la preuve du cloisonnement, en permanence --- */}
          <header className="agent-entete">
            <div className="agent-entete-titre">
              <p className="agent-entete-nom">
                Mizan <span aria-hidden="true">ميزان</span>
              </p>
              <p className="agent-entete-principe">
                L&apos;IA propose. Le droit dispose.
              </p>
            </div>
            <button
              type="button"
              className="agent-fermer"
              onClick={() => setOuverte(false)}
              aria-label="Fermer l'assistant"
            >
              <span aria-hidden="true">×</span>
            </button>
          </header>

          {session ? (
            <p className="agent-identite" data-test="agent-identite">
              <span className="agent-identite-mention">Agit au nom de</span>
              <strong className="agent-identite-organisation">
                {organisation || 'votre organisation'}
              </strong>
              {role ? (
                <span className="agent-identite-role">{role}</span>
              ) : null}
            </p>
          ) : null}

          {/* --- Le fil --- */}
          <div className="agent-fil" ref={filRef} data-test="agent-fil">
            {!sessionLue ? null : !session ? (
              <div className="agent-invite" data-test="agent-invite">
                <p className="agent-invite-titre">Faisons connaissance d&apos;abord</p>
                <p className="agent-invite-texte">
                  L&apos;assistant travaille au nom de votre organisation et
                  avec les droits qui sont les vôtres. Il a donc besoin de
                  savoir qui vous êtes avant de répondre — c&apos;est ce qui
                  garantit qu&apos;aucun dossier ne sort de chez vous.
                </p>
                <Link
                  href="/connexion"
                  className="agent-invite-lien"
                  onClick={() => setOuverte(false)}
                >
                  Ouvrir ma session
                </Link>
              </div>
            ) : (
              <>
                {tours.length === 0 ? (
                  <div className="agent-accueil">
                    <p className="agent-accueil-titre">
                      Posez votre question en français.
                    </p>
                    <p className="agent-accueil-texte">
                      Les montants, les dates et les délais sont calculés par
                      le moteur juridique. Les articles affichés sont relus
                      dans le texte officiel — ils ne sont jamais rédigés par
                      le modèle de langage.
                    </p>
                  </div>
                ) : null}

                {tours.map((tour) =>
                  tour.qui === 'personne' ? (
                    <p key={tour.id} className="agent-dit-vous">
                      {tour.texte}
                    </p>
                  ) : tour.qui === 'avarie' ? (
                    <div key={tour.id} className="agent-avarie" role="alert">
                      <p className="agent-avarie-titre">
                        {tour.echec.genre === 'session'
                          ? 'Votre session s’est refermée'
                          : tour.echec.genre === 'lenteur'
                            ? 'La réponse a mis trop longtemps'
                            : 'Aucune réponse n’a pu être formée'}
                      </p>
                      <p className="agent-avarie-texte">{tour.echec.message}</p>
                      {tour.echec.genre === 'session' ? (
                        <Link
                          href="/connexion"
                          className="agent-invite-lien"
                          onClick={() => setOuverte(false)}
                        >
                          Rouvrir ma session
                        </Link>
                      ) : null}
                    </div>
                  ) : (
                    <ReponseAffichee key={tour.id} reponse={tour.reponse} />
                  ),
                )}

                {enAttente ? (
                  <div className="agent-attente" data-test="agent-attente">
                    <span className="agent-attente-points" aria-hidden="true">
                      <i />
                      <i />
                      <i />
                    </span>
                    <span className="agent-attente-texte" aria-live="polite">
                      {phaseAu(attenteMs)}
                    </span>
                    <span className="agent-attente-note">
                      {rassuranceAu(attenteMs)}
                    </span>
                  </div>
                ) : null}
              </>
            )}
          </div>

          {/* --- Les suggestions, justes pour ce rôle --- */}
          {session && suggestions.length > 0 && !enAttente ? (
            <div className="agent-suggestions" data-test="agent-suggestions">
              {suggestions.map((s) => (
                <button
                  key={s.titre}
                  type="button"
                  className="agent-suggestion"
                  onClick={() => demander(s.question)}
                >
                  {s.titre}
                </button>
              ))}
            </div>
          ) : null}

          {/* --- La saisie --- */}
          {session ? (
            <form
              className="agent-saisie"
              onSubmit={(e) => {
                e.preventDefault();
                demander(saisie);
              }}
            >
              <label htmlFor="agent-champ" className="agent-champ-etiquette">
                Votre question
              </label>
              <textarea
                id="agent-champ"
                ref={champRef}
                className="agent-champ"
                rows={1}
                value={saisie}
                placeholder="Écrivez votre question…"
                onChange={(e) => setSaisie(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    demander(saisie);
                  }
                }}
                disabled={enAttente}
                data-test="agent-champ"
              />
              <button
                type="submit"
                className="agent-envoyer"
                disabled={enAttente || !saisie.trim()}
                data-test="agent-envoyer"
              >
                {enAttente ? 'En cours…' : 'Envoyer'}
              </button>
            </form>
          ) : null}
        </section>
        </>
      ) : null}
    </>
  );
}

/**
 * Une réponse de l'agent.
 *
 * L'ordre d'affichage est celui de la lecture juridique : d'abord la nature
 * de la réponse (refus, abstention, dégradation), puis la phrase, puis les
 * articles qui la fondent, puis les avertissements, et enfin, tout en bas et
 * discrètement, qui a rédigé la phrase.
 */
function ReponseAffichee({ reponse }: { reponse: ReponseAgent }) {
  const nature = reponse.refuse
    ? 'refus'
    : reponse.abstention
      ? 'abstention'
      : 'reponse';

  const articles = (reponse.articles ?? []).filter(
    (a) => texteArabeDe(a) || referenceDe(a),
  );

  return (
    <div
      className={`agent-dit-mizan agent-dit-${nature}`}
      data-test={`agent-reponse-${nature}`}
    >
      {reponse.refuse ? (
        <p className="agent-bandeau agent-bandeau-refus">
          <span className="agent-bandeau-sceau" aria-hidden="true">
            ⚖
          </span>
          <span>
            <strong>Ce n’est pas à Mizan de le faire.</strong> La loi réserve
            cet acte à une autre qualité que la vôtre. Ce n’est pas une panne :
            c’est la limite que la plateforme s’impose.
          </span>
        </p>
      ) : null}

      {reponse.abstention ? (
        <p className="agent-bandeau agent-bandeau-abstention">
          <span className="agent-bandeau-sceau" aria-hidden="true">
            ⌀
          </span>
          <span>
            <strong>Mizan s’abstient de répondre.</strong> Aucun texte tunisien
            indexé ne fonde de réponse à cette question. Mieux vaut une
            abstention dite qu’une réponse inventée.
          </span>
        </p>
      ) : null}

      <p className="agent-texte">{reponse.texte}</p>

      {articles.length > 0 ? (
        <div className="agent-articles">
          <p className="agent-articles-titre">
            Articles relus dans le texte officiel
          </p>
          {articles.map((a, i) => {
            const arabe = texteArabeDe(a);
            return (
              <div key={i} className="agent-article">
                <span className="agent-article-ref">{referenceDe(a)}</span>
                {arabe ? (
                  <p lang="ar" dir="rtl" className="legal-ar agent-article-ar">
                    {arabe}
                  </p>
                ) : null}
                {a.short_fr && a.short_fr !== a.label_fr ? (
                  <p className="agent-article-fr">{a.short_fr}</p>
                ) : null}
              </div>
            );
          })}
          <p className="agent-articles-source">
            Cités par le moteur juridique, pas par le modèle de langage.
          </p>
        </div>
      ) : null}

      {(reponse.avertissements ?? []).length > 0 ? (
        <ul className="agent-avertissements">
          {reponse.avertissements.map((a, i) => (
            <li key={i}>{a}</li>
          ))}
        </ul>
      ) : null}

      {/* La provenance de la phrase, en une seule ligne.
       *
       * Le mode dégradé avait jusqu'ici son propre encadré ambre, qui
       * annonçait en trois phrases qu'une mise en forme automatique était
       * indisponible. Le fond était juste — il faut dire qui a rédigé la
       * phrase — mais la forme disait autre chose que le fond : du fond
       * d'une salle, un cartouche ambre surmonté d'un mot en gras se lit
       * comme une panne, alors que le calcul juridique, lui, a bien eu
       * lieu, et que c'est le seul fait qui engage Mizan.
       *
       * On garde donc l'information et on change de registre. Le mode
       * dégradé ne dit plus ce qui manque, il dit d'où vient la phrase, sur
       * la même ligne de provenance qui clôt déjà toutes les autres
       * réponses. Rien n'est masqué, rien n'est dramatisé, et le jury lit
       * une précision d'origine là où il lisait un aveu. */}
      <p className="agent-plume" data-test="agent-plume">
        {reponse.reformule_par_modele
          ? 'Phrase mise en forme par le modèle de langage. Les chiffres et les articles viennent du moteur.'
          : 'Réponse rédigée directement par le moteur juridique, à partir du calcul et des textes cités.'}
      </p>
    </div>
  );
}
