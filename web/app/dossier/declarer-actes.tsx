'use client';

import { useRouter } from 'next/navigation';
import { useState, useTransition } from 'react';
import { TYPES_ACTES, urlDossier } from '@/lib/actes';
import type { ActeInterruptifEntree, TypeActeInterruptif } from '@/lib/api';

/**
 * La déclaration des actes interruptifs.
 *
 * Même principe que le formulaire du dossier : ce composant n'appelle pas
 * l'API. Il écrit les actes dans l'URL sous la forme `acte=type:date[:texte]`,
 * répétable, et laisse la page se rendre côté serveur. L'interruption
 * affichée est donc dans le HTML — vérifiable au `curl`, rejouable en
 * collant une adresse.
 *
 * La liste est tenue côté client uniquement le temps de la saisie : dès
 * qu'on valide, l'URL devient la seule source de vérité. Recharger la page
 * ne perd rien.
 *
 * Aucune règle de droit ici : ce composant ne dit jamais qu'un acte
 * interrompt. Il transmet ce que la PME déclare, et c'est le moteur qui
 * tranche — y compris pour dire que l'acte ne sert à rien.
 */
export function DeclarerActes({
  montant,
  date,
  activite,
  actesInitiaux,
}: {
  montant: string;
  date: string;
  activite: string;
  actesInitiaux: ActeInterruptifEntree[];
}) {
  const router = useRouter();
  const [enCours, demarrer] = useTransition();

  const [actes, setActes] = useState<ActeInterruptifEntree[]>(actesInitiaux);
  const [type, setType] = useState<TypeActeInterruptif>('sommation_huissier');
  const [dateActe, setDateActe] = useState('');
  const [description, setDescription] = useState('');
  const [erreur, setErreur] = useState<string | null>(null);

  function naviguer(liste: ActeInterruptifEntree[]) {
    demarrer(() => {
      router.push(urlDossier({ montant, date, activite, actes: liste }), {
        scroll: false,
      });
    });
  }

  function ajouter(evt: React.FormEvent) {
    evt.preventDefault();
    if (!dateActe) {
      setErreur("Indiquez la date de l'acte : c'est elle qui décide de l'effet.");
      return;
    }
    setErreur(null);
    const liste = [
      ...actes,
      { type, date: dateActe, description: description.trim() },
    ];
    setActes(liste);
    setDateActe('');
    setDescription('');
    naviguer(liste);
  }

  function retirer(index: number) {
    const liste = actes.filter((_, i) => i !== index);
    setActes(liste);
    naviguer(liste);
  }

  return (
    <section className="panel bloc-espace">
      <p className="eyebrow">
        UN ACTE A-T-IL INTERROMPU LE DÉLAI ? — COC ART. 396 ET 397
      </p>
      <h2>Déclarer une sommation, une action en justice, un acompte reçu</h2>
      <p className="intro bloc-espace">
        Un acte interruptif annule tout le temps déjà écoulé : le délai repart
        en entier à compter de sa date (COC art. 398). Déclarez-le ici — le
        moteur dira lui-même s&apos;il produit cet effet, ou s&apos;il arrive
        trop tard pour produire quoi que ce soit.
      </p>

      {actes.length > 0 ? (
        <ul className="liste-nue actes-declares">
          {actes.map((a, index) => (
            <li key={`${a.type}-${a.date}-${index}`} className="acte-declare">
              <span className="acte-declare-type">
                {TYPES_ACTES.find((t) => t.valeur === a.type)?.libelle ?? a.type}
              </span>
              <span className="acte-declare-date">{formatDate(a.date)}</span>
              {a.description ? (
                <span className="acte-declare-desc">{a.description}</span>
              ) : null}
              <button
                type="button"
                className="acte-declare-retirer"
                onClick={() => retirer(index)}
                disabled={enCours}
                aria-label={`Retirer l'acte du ${formatDate(a.date)}`}
              >
                Retirer
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <form onSubmit={ajouter} className="formulaire formulaire-acte">
        <div className="champ">
          <label htmlFor="acte-type">Nature de l&apos;acte</label>
          <select
            id="acte-type"
            name="acte-type"
            value={type}
            onChange={(e) => setType(e.target.value as TypeActeInterruptif)}
            className="champ-select"
          >
            <optgroup label="Acte du créancier — COC art. 396">
              {TYPES_ACTES.filter((t) => t.article === 396).map((t) => (
                <option key={t.valeur} value={t.valeur}>
                  {t.libelle}
                </option>
              ))}
            </optgroup>
            <optgroup label="Fait du débiteur — COC art. 397">
              {TYPES_ACTES.filter((t) => t.article === 397).map((t) => (
                <option key={t.valeur} value={t.valeur}>
                  {t.libelle}
                </option>
              ))}
            </optgroup>
          </select>
          <p className="champ-aide">
            Un simple acompte du débiteur vaut reconnaissance de dette.
          </p>
        </div>

        <div className="champ">
          <label htmlFor="acte-date">Date de l&apos;acte</label>
          <input
            id="acte-date"
            name="acte-date"
            type="date"
            value={dateActe}
            onChange={(e) => setDateActe(e.target.value)}
          />
          <p className="champ-aide">
            Jour/mois/année. Un acte postérieur à l&apos;expiration
            n&apos;interrompt rien.
          </p>
        </div>

        <div className="champ">
          <label htmlFor="acte-description">Précision (facultative)</label>
          <input
            id="acte-description"
            name="acte-description"
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Nom de l'huissier…"
            autoComplete="off"
          />
          <p className="champ-aide">
            Elle est reprise telle quelle dans le dossier.
          </p>
        </div>

        <div className="champ champ-action">
          <button type="submit" className="primary-button" disabled={enCours}>
            {enCours ? 'Le moteur recalcule…' : "Ajouter l'acte"}
          </button>
        </div>
      </form>

      {erreur ? (
        <p className="formulaire-erreur" role="alert">
          {erreur}
        </p>
      ) : null}

      {enCours ? (
        <p className="formulaire-attente" role="status">
          Nouvel appel au moteur — les articles 396 à 398 sont appliqués à la
          date que vous venez de déclarer.
        </p>
      ) : null}
    </section>
  );
}

function formatDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : iso;
}
