# e-Houwiya — état réel du raccordement : NON IMPLÉMENTÉ

## Ce qui est établi

e-Houwiya (الهوية الإلكترونية) est le **Mobile ID officiel tunisien**, adossé à
**TunTrust / ANCE** (Agence Nationale de Certification Électronique), l'autorité
de certification racine nationale. C'est une infrastructure d'État réelle.

## Ce qui n'est PAS implémenté dans Mizan

**Rien.** Aucune ligne de code de ce projet ne parle à e-Houwiya.

`packages/identite/signature.py::FournisseurEHouwiya` existe uniquement pour
occuper la place dans l'interface `FournisseurIdentite` et pour **lever une
exception explicite** (`FournisseurIndisponible`) à toute tentative d'usage.

C'est délibéré. Produire des sceaux estampillés « e-Houwiya » sans qu'aucun
raccordement n'existe serait un faux, et un faux qui se découvre au pire
moment : devant un juge, quand la partie adverse demande à voir le certificat.

## Ce qui est UNKNOWN

Les points suivants n'ont **pas pu être vérifiés** auprès d'une source
officielle au moment de l'écriture de ce module, et ne sont **pas devinés** :

| Élément                                      | État      |
|----------------------------------------------|-----------|
| Protocole d'intégration (OIDC ? SOAP ? autre) | UNKNOWN   |
| Format des certificats délivrés               | UNKNOWN   |
| Points d'accès (endpoints) de production/test | UNKNOWN   |
| Modalités d'enrôlement d'un éditeur tiers     | UNKNOWN   |
| Algorithmes de signature imposés              | UNKNOWN   |
| Existence d'une autorité d'horodatage (RFC 3161) rattachée | UNKNOWN |

### Pourquoi UNKNOWN et non « à compléter »

Les tentatives de vérification menées depuis l'environnement de développement
ont toutes échoué pour des raisons d'infrastructure, et non parce que
l'information n'existe pas :

- recherche web indisponible (erreur de facturation du fournisseur) ;
- extraction de page indisponible (même cause) ;
- automatisation navigateur : le démon ne démarre pas ;
- `curl https://www.tuntrust.tn/` : échec d'établissement TLS depuis cette
  machine (HTTP 000, 0 octet reçu).

Aucune de ces informations n'a donc été obtenue. Elles sont marquées UNKNOWN
plutôt que remplies au jugé.

## Ce qu'il faut pour lever le NON IMPLÉMENTÉ

1. Un **accord de raccordement avec TunTrust/ANCE**.
2. La **documentation d'intégration** officielle correspondante.
3. Des **certificats de test**, puis de production.

Tant que ces trois éléments n'existent pas, `FournisseurEHouwiya` doit
continuer de lever une exception. Le test
`test_ehouwiya_refuse_de_signer_et_dit_pourquoi` verrouille ce comportement :
il échouera si quelqu'un remplace l'exception par une simulation.

## Ce qu'on utilise en attendant

`FournisseurLocal` : une paire de clés Ed25519 générée par la plateforme.

Sa valeur probante est **plus faible** et elle est documentée comme telle dans
chaque rapport d'attribution :

- ce n'est **pas** une signature électronique qualifiée (aucun certificat d'un
  prestataire de confiance reconnu n'atteste que le détenteur de la clé est
  bien la personne nommée) ;
- l'horodatage n'est **pas** un horodatage qualifié (horloge de la machine, pas
  une autorité d'horodatage) ;
- l'attribution n'est établie que si la clé publique du signataire était
  **connue d'avance** (registre de clés, échange hors bande). Vérifier une
  signature avec la clé que le document transporte lui-même ne prouve rien.

C'est suffisant pour prouver, entre deux parties qui se sont échangé leurs
clés, qu'un document n'a pas été retouché et qu'il vient bien de l'autre.
C'est insuffisant pour l'opposer à un tiers qui n'a jamais reconnu la clé.
