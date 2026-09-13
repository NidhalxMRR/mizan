import type { Metadata } from 'next';
import './globals.css';
import { Coque } from './components/coque';
import { BulleAgent } from './components/agent/bulle';

/**
 * Aucun `next/font/google` ici : la démonstration se fait sans wifi, et une
 * police distante fait soit échouer le build, soit clignoter la page. Les
 * familles utilisées sont déclarées dans globals.css et existent déjà sur la
 * machine.
 */
export const metadata: Metadata = {
  title: 'Mizan — ميزان · résolution des litiges commerciaux',
  description:
    "Plateforme tunisienne d'aide aux PME en litige commercial. " +
    "Le moteur juridique est déterministe : l'IA propose, le droit dispose.",
};

export default function RootLayout({ children }: LayoutProps<'/'>) {
  return (
    <html lang="fr" dir="ltr">
      <body>
        <Coque>{children}</Coque>
        {/*
          La bulle est montée ici, et non dans la coque, pour une raison
          précise : elle est en `position: fixed` et ne doit hériter d'aucun
          contexte d'empilement créé par la barre latérale. Montée dans la
          coque, elle passerait sous le bandeau de navigation sur téléphone.

          Montée sur toutes les pages, elle ne fait jamais quitter celle qu'on
          lit : on interroge l'agent depuis « Mon impayé » sans perdre le
          formulaire en cours de saisie.
        */}
        <BulleAgent />
      </body>
    </html>
  );
}
