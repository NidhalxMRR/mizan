'use client';

import { useRef, useState, useTransition } from 'react';
import { useRouter } from 'next/navigation';
import { deposerPiece, type EchecApi, type PieceDeposee } from '@/lib/api';
import { urlDossier } from '@/lib/actes';
import type { ActeInterruptifEntree } from '@/lib/api';
import { dateEnClair } from '@/lib/date-fr';
import { PanneApi, EnAttente } from '../components/etats';

/**
 * Le dépôt de la facture.
 *
 * Ce composant existe pour une raison précise : l'API sait lire un PDF de
 * facture depuis le début, mais rien à l'écran ne le montrait. Une capacité
 * qu'on ne voit pas n'existe pas pour celui qui regarde.
 *
 * Il est le seul endroit de l'application qui fait un appel HTTP depuis le
 * navigateur plutôt que par l'URL. C'est inévitable : un fichier ne se met
 * pas dans une adresse. On garde donc le reste de la discipline maison —
 * un échec s'affiche, un refus s'affiche, et aucune valeur n'est inventée
 * pour combler un trou.
 *
 * Ce qui s'affiche après lecture n'est PAS un résumé : ce sont les champs
 * renvoyés par le moteur, recopiés. En particulier `ligne_montant`, la ligne
 * brute du document d'où le chiffre est tiré. C'est elle qui distingue une
 * extraction d'une hallucination : le jury peut ouvrir le PDF et retrouver
 * cette ligne mot pour mot. Un modèle de langage, lui, produirait un montant
 * plausible sans pouvoir désigner sa source.
 */

type Etat =
  | { phase: 'vierge' }
  | { phase: 'lecture'; nom: string }
  | { phase: 'lue'; piece: PieceDeposee }
  | { phase: 'echec'; echec: EchecApi };

export function DeposerPiece({
  activite,
  actes,
}: {
  activite: string;
  actes: ActeInterruptifEntree[];
}) {
  const router = useRouter();
  const [etat, setEtat] = useState<Etat>({ phase: 'vierge' });
  const [enCours, demarrer] = useTransition();
  const champFichier = useRef<HTMLInputElement>(null);

  async function choisir(evt: React.ChangeEvent<HTMLInputElement>) {
    const fichier = evt.target.files?.[0];
    if (!fichier) return;

    setEtat({ phase: 'lecture', nom: fichier.name });
    const r = await deposerPiece(fichier);
    setEtat(
      r.ok ? { phase: 'lue', piece: r.valeur } : { phase: 'echec', echec: r.echec },
    );
  }

  /**
   * Reporte le montant et la date extraits dans le formulaire d'analyse.
   *
   * On passe par l'URL, comme tout le reste du parcours : la page se rend à
   * nouveau côté serveur et l'analyse affichée reste vérifiable au `curl`.
   * L'artisan ne ressaisit rien — et surtout, il ne peut pas se tromper en
   * recopiant un montant à la main.
   *
   * Le bouton n'apparaît que si les deux valeurs existent réellement.
   */
  function reporter(piece: PieceDeposee) {
    if (piece.montant_tnd === null || !piece.date_facture) return;
    demarrer(() => {
      router.push(
        urlDossier({
          montant: String(piece.montant_tnd),
          date: piece.date_facture as string,
          activite,
          actes,
        }),
        { scroll: false },
      );
    });
  }

  function recommencer() {
    if (champFichier.current) champFichier.current.value = '';
    setEtat({ phase: 'vierge' });
  }

  return (
    <section className="panel bloc-espace">
      <p className="eyebrow">LA PIÈCE ELLE-MÊME — LECTURE AUTOMATIQUE</p>
      <h2>Déposer la facture au format PDF</h2>
      <p className="intro bloc-espace">
        Le moteur ouvre le document, en recopie le montant, la date, le numéro
        et le client, puis affiche la ligne exacte dont il a tiré le chiffre.
        Rien n&apos;est deviné : si la pièce n&apos;est pas une facture, elle
        est refusée et le motif est écrit en clair.
      </p>

      <div className="depot">
        <label htmlFor="piece-fichier" className="depot-label">
          Fichier de la facture
        </label>
        {/*
          Le navigateur dessine lui-même le contenu d'un <input type="file"> et
          le libelle dans la langue du SYSTÈME, pas dans celle de la page : sur
          un poste anglophone il affiche « Choose File / No file chosen » au
          milieu d'une interface française. Aucun attribut HTML ne permet de le
          traduire.

          On garde donc l'input réel — c'est lui qui porte l'accessibilité et
          la sélection de fichier — mais on le rend invisible, et on affiche à
          sa place un bouton français qui le déclenche. Le clavier fonctionne
          toujours : le label est associé à l'input par htmlFor.
        */}
        <input
          ref={champFichier}
          id="piece-fichier"
          name="piece-fichier"
          type="file"
          accept="application/pdf,.pdf"
          className="depot-champ-natif"
          onChange={choisir}
          disabled={etat.phase === 'lecture'}
          aria-describedby="piece-aide"
        />
        <div className="depot-commande">
          <button
            type="button"
            className="depot-bouton"
            onClick={() => champFichier.current?.click()}
            disabled={etat.phase === 'lecture'}
          >
            Choisir un fichier
          </button>
          <span className="depot-nom-fichier">
            {etat.phase === 'lecture'
              ? etat.nom
              : etat.phase === 'lue'
                ? etat.piece.nom_fichier
                : etat.phase === 'echec'
                  ? 'Fichier refusé'
                  : 'Aucun fichier sélectionné'}
          </span>
        </div>
        <p id="piece-aide" className="champ-aide">
          Un seul PDF, celui de la facture impayée. Il est lu sur ce poste par
          l&apos;API Mizan ; aucun service extérieur n&apos;y accède.
        </p>
      </div>

      {etat.phase === 'lecture' ? (
        <div className="depot-attente" aria-busy="true" role="status">
          <p className="formulaire-attente">
            Lecture de {etat.nom} — empreinte calculée, puis texte extrait.
          </p>
          <EnAttente lignes={3} />
        </div>
      ) : null}

      {etat.phase === 'echec' ? (
        <div className="bloc-espace">
          <PanneApi echec={etat.echec} />
        </div>
      ) : null}

      {etat.phase === 'lue' ? (
        <PieceLue
          piece={etat.piece}
          enCours={enCours}
          onReporter={() => reporter(etat.piece)}
          onRecommencer={recommencer}
        />
      ) : null}
    </section>
  );
}

/**
 * Ce que le moteur a lu — ou pourquoi il a refusé.
 *
 * Les deux cas partagent l'empreinte et le nom du fichier, parce que ces
 * deux-là existent indépendamment du résultat de la lecture. Le reste
 * diverge : un refus n'affiche aucun champ extrait, puisqu'il n'y en a pas.
 */
function PieceLue({
  piece,
  enCours,
  onReporter,
  onRecommencer,
}: {
  piece: PieceDeposee;
  enCours: boolean;
  onReporter: () => void;
  onRecommencer: () => void;
}) {
  const reportable = piece.montant_tnd !== null && Boolean(piece.date_facture);

  return (
    <div
      className={`depot-resultat ${
        piece.acceptee ? 'depot-acceptee' : 'depot-refusee'
      }`}
      role="status"
    >
      <div className="etat-entete">
        <div>
          <p
            className="eyebrow"
            style={{ color: piece.acceptee ? 'var(--verified)' : 'var(--danger)' }}
          >
            {piece.acceptee ? 'PIÈCE ACCEPTÉE' : 'PIÈCE REFUSÉE'}
          </p>
          <h3 className="depot-nom">{piece.nom_fichier}</h3>
        </div>
        <span
          className={`provenance ${
            piece.acceptee ? 'provenance-verified' : 'provenance-danger'
          }`}
        >
          {formatTaille(piece.taille_octets)}
          {piece.methode_extraction
            ? ` · lu par « ${piece.methode_extraction} »`
            : ' · aucun texte extrait'}
        </span>
      </div>

      {/*
        Le refus passe AVANT tout le reste. Une PME dont la pièce est écartée
        doit le lire en premier, pas le déduire de l'absence de montant plus
        bas. Le motif est celui du moteur, mot pour mot.
      */}
      {!piece.acceptee ? (
        <div className="depot-refus">
          <p className="depot-refus-motif">
            {piece.motif_refus ??
              "Le moteur a refusé cette pièce sans en donner le motif. Aucune donnée n'en a été tirée."}
          </p>
          {piece.indices_manquants.length > 0 ? (
            <div className="depot-indices">
              <p className="depot-indices-titre">
                Ce qui manquait pour reconnaître une facture
              </p>
              <ul className="liste-nue depot-indices-liste">
                {piece.indices_manquants.map((i) => (
                  <li key={i} className="depot-indice depot-indice-manquant">
                    {i}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <p className="depot-refus-suite">
            Aucun montant n&apos;a été repris dans le formulaire. Déposez la
            facture elle-même, ou saisissez les valeurs à la main plus haut.
          </p>
        </div>
      ) : null}

      {/* --- Ce que le moteur a lu dans le document --------------------- */}
      {piece.acceptee ? (
        <>
          <div className="faits depot-faits">
            <FaitLu
              libelle="Montant lu"
              valeur={
                piece.montant_tnd !== null
                  ? `${formatMontant(piece.montant_tnd)} DT`
                  : null
              }
            />
            <FaitLu
              libelle="Date de facture"
              valeur={dateEnClair(piece.date_facture)}
            />
            <FaitLu libelle="Numéro" valeur={piece.numero_facture} />
            <FaitLu libelle="Client" valeur={piece.client} />
          </div>

          {/*
            La preuve. Sans cette ligne, le montant affiché a exactement la
            même tête qu'un chiffre inventé par un modèle. Avec elle, le jury
            ouvre le PDF et la retrouve telle quelle.
          */}
          {piece.ligne_montant ? (
            <div className="depot-preuve">
              <p className="depot-preuve-titre">
                La ligne du document dont ce montant est tiré
              </p>
              <p className="depot-preuve-ligne">{piece.ligne_montant}</p>
              <p className="depot-preuve-note">
                Recopiée telle quelle depuis le PDF. Aucun modèle de langage
                n&apos;intervient dans cette lecture : le chiffre vient du
                document, et cette ligne permet de le vérifier à l&apos;œil.
              </p>
            </div>
          ) : (
            <p className="depot-preuve-absente">
              Le moteur n&apos;a pas su désigner la ligne d&apos;où viendrait
              un montant. Rien n&apos;est donc proposé au report.
            </p>
          )}

          {piece.dates_trouvees.length > 1 ? (
            <p className="depot-autres-dates">
              {piece.dates_trouvees.length} dates figurent dans ce document
              {' : '}
              {piece.dates_trouvees
                .map((d) => dateEnClair(d) ?? d)
                .join(', ')}
              . Le moteur a retenu la première comme date de facture —
              vérifiez-la avant de lancer le calcul.
            </p>
          ) : null}

          {piece.indices_trouves.length > 0 ? (
            <div className="depot-indices">
              <p className="depot-indices-titre">
                Ce qui a permis de reconnaître une facture
              </p>
              <ul className="liste-nue depot-indices-liste">
                {piece.indices_trouves.map((i) => (
                  <li key={i} className="depot-indice depot-indice-trouve">
                    {i}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      ) : null}

      {/* --- L'empreinte : vraie même quand la pièce est refusée --------- */}
      <div className="depot-empreinte">
        <p className="depot-empreinte-titre">
          Empreinte SHA-256 de la pièce reçue
        </p>
        {/*
          Tronquée à l'écran : 64 caractères hexadécimaux débordent d'une
          fenêtre de 479 px et ne se lisent de toute façon pas à l'œil. Le
          `title` porte la valeur complète pour qui la survole, et elle reste
          sélectionnable au copier-coller.
        */}
        <p className="depot-empreinte-valeur" title={piece.sha256}>
          <code>{tronquer(piece.sha256)}</code>
        </p>
        <p className="depot-empreinte-note">
          Cette empreinte est calculée sur le fichier reçu, avant toute
          analyse. Elle permet au greffier de vérifier que la pièce
          enregistrée au dossier est bien celle qui a été déposée : deux
          fichiers identiques donnent la même empreinte, un seul caractère
          modifié la change entièrement.
        </p>
      </div>

      <p className="depot-avertissement">{piece.avertissement}</p>

      <div className="depot-actions">
        {piece.acceptee && reportable ? (
          <button
            type="button"
            className="primary-button"
            onClick={onReporter}
            disabled={enCours}
          >
            {enCours
              ? 'Le moteur recalcule…'
              : 'Reporter ces valeurs dans le formulaire'}
          </button>
        ) : null}
        <button type="button" className="secondary-button" onClick={onRecommencer}>
          Déposer une autre pièce
        </button>
      </div>

      {piece.acceptee && reportable ? (
        <p className="depot-actions-note">
          Le montant et la date ci-dessus remplacent ceux du formulaire, et
          l&apos;analyse est relancée. Vous n&apos;avez rien à ressaisir.
        </p>
      ) : null}
    </div>
  );
}

/**
 * Un champ extrait — ou son absence, dite explicitement.
 *
 * Un tiret discret suffirait visuellement. Il laisserait croire que la valeur
 * est vide dans le document, alors qu'elle n'a pas été trouvée. Les deux ne
 * s'équivalent pas devant un juge, donc on écrit lequel des deux c'est.
 */
function FaitLu({
  libelle,
  valeur,
}: {
  libelle: string;
  valeur: string | null;
}) {
  return (
    <div className="fait">
      <p className="fait-libelle">{libelle}</p>
      <p className={`fait-valeur ${valeur ? '' : 'fait-valeur-absente'}`.trim()}>
        {valeur ?? 'non trouvé dans le document'}
      </p>
    </div>
  );
}

// --- Mise en forme ----------------------------------------------------------

/** Les 16 premiers et 8 derniers caractères : de quoi comparer à l'œil. */
function tronquer(sha: string): string {
  return sha.length > 28 ? `${sha.slice(0, 16)}…${sha.slice(-8)}` : sha;
}

function formatMontant(n: number): string {
  return n.toLocaleString('fr-FR', {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  });
}

function formatTaille(octets: number): string {
  if (octets < 1024) return `${octets} octets`;
  const ko = octets / 1024;
  if (ko < 1024) return `${ko.toFixed(0)} Ko`;
  return `${(ko / 1024).toFixed(1)} Mo`;
}
