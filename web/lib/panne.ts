/**
 * Traduire une panne technique en une phrase qu'un juriste comprend.
 *
 * L'accueil affichait « local — ConnectError: [Errno 111] Connection refused »
 * sur l'écran d'ouverture de la démonstration. C'est exact, mais c'est une
 * trace de crash : devant un jury non technique, cela ne dit pas « le modèle
 * tourne sur une machine actuellement éteinte », cela dit « ce projet est
 * cassé ».
 *
 * On ne masque rien : la cause d'origine reste disponible pour qui inspecte
 * l'API. On la dit simplement en français.
 */
export function pannEnFrancais(motif: string): string {
  if (!motif) return motif;

  // Connexion refusée : rien n'écoute en face.
  if (/Errno 111|Connection refused|ECONNREFUSED/i.test(motif)) {
    return "machine hors ligne — le service ne répond pas";
  }
  // Délai dépassé : la machine existe mais ne répond pas à temps.
  if (/timed? ?out|ETIMEDOUT|ReadTimeout|ConnectTimeout/i.test(motif)) {
    return "délai dépassé — la machine ne répond plus";
  }
  // Nom introuvable : le tunnel ou le DNS est tombé.
  if (/Name or service not known|ENOTFOUND|getaddrinfo/i.test(motif)) {
    return "adresse introuvable — le tunnel est fermé";
  }
  // Réseau injoignable.
  if (/Network is unreachable|ENETUNREACH|Errno 101/i.test(motif)) {
    return "réseau injoignable";
  }
  return motif;
}

/**
 * `moteur_juridique` est une valeur d'énumération de l'API, en anglais
 * (« deterministic »). Elle s'affichait telle quelle au milieu d'une phrase
 * française, juste sous un chapô qui dit « moteur déterministe ».
 */
export function moteurEnFrancais(valeur: string): string {
  const table: Record<string, string> = {
    deterministic: 'déterministe',
    hybrid: 'hybride',
    llm: 'modèle de langage',
  };
  return table[valeur] ?? valeur;
}

/**
 * Un tag de modèle (« qwen2.5:7b-instruct-q4_K_M ») dit la quantification à
 * un juriste, ce qui ne lui apprend rien. On garde le tag exact en infobulle.
 */
export function modeleEnClair(tag: string): string {
  if (!tag) return tag;
  const m = /^([a-z]+)([\d.]+)?:?(\d+b)?/i.exec(tag);
  if (!m) return tag;
  const famille = m[1].charAt(0).toUpperCase() + m[1].slice(1);
  const version = m[2] ? ` ${m[2]}` : '';
  const taille = m[3] ? ` ${m[3].toUpperCase()}` : '';
  return `${famille}${version}${taille}`.trim();
}
