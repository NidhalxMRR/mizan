import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  /**
   * En développement, Next.js ne sert ses ressources internes (dont la
   * WebSocket de rechargement à chaud) qu'à l'origine exacte utilisée pour
   * ouvrir la page. Une démonstration ouverte sur `127.0.0.1:3000` alors que
   * le serveur s'annonce sur `localhost:3000` voit donc sa WebSocket refusée,
   * React n'est jamais hydraté, et les boutons ne répondent plus — sans la
   * moindre erreur visible à l'écran.
   *
   * Le défaut a été constaté au pilotage d'un vrai navigateur : le bouton
   * « Demander la reformulation » ne déclenchait rien. Ces deux origines sont
   * celles du poste de démonstration, et ne concernent que `next dev`.
   */
  allowedDevOrigins: ['127.0.0.1', 'localhost'],
};

export default nextConfig;
