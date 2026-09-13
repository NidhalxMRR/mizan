'use client';

import { useRouter } from 'next/navigation';
import { useState, useTransition } from 'react';
import { urlDossier } from '@/lib/actes';
import type { ActeInterruptifEntree } from '@/lib/api';
import { dateEnClair } from '@/lib/date-fr';

/**
 * Le formulaire du parcours PME.
 *
 * Il ne fait pas l'appel HTTP lui-même : il écrit les trois valeurs dans
 * l'URL et laisse la page se rendre côté serveur. Deux conséquences voulues :
 *   - l'analyse affichée est dans le HTML, pas injectée après coup — on peut
 *     la vérifier avec un `curl`, ce qui est la seule preuve qui vaille ;
 *   - une URL de démonstration se partage et se rejoue à l'identique.
 *
 * L'état d'attente n'est pas simulé : `useTransition` reste en `pending`
 * pendant tout l'aller-retour serveur, c'est-à-dire pendant l'appel réel à
 * l'API.
 *
 * Les actes interruptifs déjà déclarés sont réécrits dans la nouvelle URL.
 * Sans cela, corriger un montant effacerait une sommation sans prévenir —
 * et l'échéance changerait sous les yeux de la PME sans qu'elle sache
 * pourquoi.
 */

const SUGGESTIONS = [
  'menuiserie',
  'textile',
  'imprimerie',
  'agroalimentaire',
  'quincaillerie',
  'transport',
  'conseil',
  'informatique',
  'maintenance',
  'architecture',
];

export function FormulaireDossier({
  montantInitial,
  dateInitiale,
  activiteInitiale,
  actes,
}: {
  montantInitial: string;
  dateInitiale: string;
  activiteInitiale: string;
  actes: ActeInterruptifEntree[];
}) {
  const router = useRouter();
  const [enCours, demarrer] = useTransition();

  const [montant, setMontant] = useState(montantInitial);
  const [date, setDate] = useState(dateInitiale);
  const [activite, setActivite] = useState(activiteInitiale);

  // La date relue en toutes lettres, pour lever l'ambiguïté jj/mm vs mm/jj
  // que le champ natif introduit selon la locale du système.
  const dateLisible = dateEnClair(date);

  function soumettre(evt: React.FormEvent) {
    evt.preventDefault();
    demarrer(() => {
      router.push(
        urlDossier({
          montant,
          date,
          activite: activite.trim() || 'menuiserie',
          actes,
        }),
        { scroll: false },
      );
    });
  }

  return (
    <section className="panel">
      <p className="eyebrow">LES TROIS SEULES CHOSES DEMANDÉES</p>
      <form onSubmit={soumettre} className="formulaire">
        <div className="champ">
          <label htmlFor="montant">Montant réclamé (DT)</label>
          <input
            id="montant"
            name="montant"
            type="number"
            inputMode="decimal"
            min="0.001"
            step="0.001"
            value={montant}
            onChange={(e) => setMontant(e.target.value)}
            required
          />
          <p className="champ-aide">
            Au-delà de 150 DT, la sommation change de nature.
          </p>
        </div>

        <div className="champ">
          <label htmlFor="date">Date de la facture</label>
          <input
            id="date"
            name="date"
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            required
          />
          {/*
            Le format affiché par un champ date natif suit la locale du
            SYSTÈME, pas l'attribut lang de la page : un poste configuré en
            anglais écrit « 05/12/2026 » là où la fiche du cas annonce
            « facture du 12/05/2026 ». Même jour, lecture inverse — et un
            artisan qui croit s'être trompé ressaisit à l'envers.

            On ne peut pas imposer le format au navigateur. On affiche donc
            la date TELLE QUE LE MOTEUR LA LIT, en toutes lettres : aucune
            ambiguïté ne survit à « 12 mai 2026 ».
          */}
          <p className="champ-aide">
            {dateLisible
              ? <>Lue par le moteur : <strong>{dateLisible}</strong>. C&apos;est elle qui fait courir le délai.</>
              : <>C&apos;est elle qui fait courir le délai.</>}
          </p>
        </div>

        <div className="champ">
          <label htmlFor="activite">Votre activité</label>
          <input
            id="activite"
            name="activite"
            list="activites-connues"
            value={activite}
            onChange={(e) => setActivite(e.target.value)}
            autoComplete="off"
          />
          <datalist id="activites-connues">
            {SUGGESTIONS.map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
          <p className="champ-aide">
            Livrer un bien ou rendre un service ne se prescrit pas pareil.
          </p>
        </div>

        <div className="champ champ-action">
          <button type="submit" className="primary-button" disabled={enCours}>
            {enCours ? 'Le moteur calcule…' : 'Analyser'}
          </button>
        </div>
      </form>
      {enCours ? (
        <p className="formulaire-attente" role="status">
          Appel en cours au moteur juridique — les règles de prescription sont
          appliquées à votre situation.
        </p>
      ) : null}
    </section>
  );
}
