import type { Metadata } from 'next';
import './globals.css';
import { Coque } from './components/coque';

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
      </body>
    </html>
  );
}
