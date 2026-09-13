'use client';

import { useState } from 'react';
import { demanderExplication, type Explication, type EchecApi } from '@/lib/api';
import { PanneApi, EnAttente } from '../components/etats';

/**
 * La reformulation par le modèle de langage.
 *
 * Le seul endroit de l'application où un LLM intervient, et il est encadré
 * de trois façons :
 *   - il n'est appelé que sur demande explicite, jamais au chargement ;
 *   - son texte est visuellement séparé du calcul, avec une étiquette qui
 *     dit d'où il vient et combien de temps il a mis ;
 *   - quand l'API bascule en mode dégradé (GPU occupé, modèle absent), elle
 *     retourne quand même 200 avec un texte rédigé à partir du moteur seul :
 *     on affiche alors le motif exact de la dégradation.
 *
 * Cacher qu'un modèle est tombé serait le genre de silence qui fait perdre la
 * confiance d'un juge. On préfère l'écrire.
 */

type Etat =
  | { phase: 'vierge' }
  | { phase: 'chargement' }
  | { phase: 'ok'; explication: Explication }
  | { phase: 'echec'; echec: EchecApi };

export function Reformulation({
  montant,
  date,
  activite,
  apiUrl,
}: {
  montant: number;
  date: string;
  activite: string;
  apiUrl: string;
}) {
  const [etat, setEtat] = useState<Etat>({ phase: 'vierge' });

  async function demander() {
    setEtat({ phase: 'chargement' });
    const r = await demanderExplication({
      montant_tnd: montant,
      date_facture: date,
      activite,
    });
    setEtat(
      r.ok
        ? { phase: 'ok', explication: r.valeur }
        : { phase: 'echec', echec: r.echec },
    );
  }

  return (
    <section className="panel bloc-espace">
      <p className="eyebrow">FACULTATIF — ET SÉPARÉ DU CALCUL</p>
      <h2>Faire reformuler en français simple</h2>
      <p className="intro bloc-espace">
        Le modèle de langage reçoit le résultat ci-dessus et le réécrit. Il
        n&apos;a pas le droit de citer un article : les références restent
        celles affichées plus haut, et l&apos;API retire toute référence
        qu&apos;il tenterait de produire.
      </p>

      {etat.phase === 'vierge' ? (
        <button type="button" className="secondary-button" onClick={demander}>
          Demander la reformulation
        </button>
      ) : null}

      {etat.phase === 'chargement' ? (
        <div aria-busy="true" role="status">
          <p className="intro">
            Appel à <code>{apiUrl}/assistant/expliquer</code> — le modèle
            tourne en local, cela peut prendre une minute.
          </p>
          <EnAttente lignes={3} />
        </div>
      ) : null}

      {etat.phase === 'echec' ? <PanneApi echec={etat.echec} /> : null}

      {etat.phase === 'ok' ? (
        <div className="reformulation">
          <span
            className={`provenance ${
              etat.explication.mode_degrade
                ? 'provenance-abstain'
                : 'provenance-declared'
            }`}
          >
            {etat.explication.mode_degrade
              ? 'Modèle indisponible — texte produit par le moteur seul'
              : `Reformulé par le modèle · ${etat.explication.origine} · ${etat.explication.duree_s.toFixed(1)} s`}
          </span>

          {etat.explication.mode_degrade &&
          etat.explication.motif_degradation ? (
            <p className="degradation-motif">
              Motif exact : {etat.explication.motif_degradation}
            </p>
          ) : null}

          <p className="reformulation-texte">{etat.explication.texte}</p>
          <p className="reformulation-avertissement">
            {etat.explication.avertissement}
          </p>

          <button
            type="button"
            className="secondary-button"
            onClick={demander}
          >
            Redemander
          </button>
        </div>
      ) : null}
    </section>
  );
}
