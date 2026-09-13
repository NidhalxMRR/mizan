-- =====================================================================
--  MIZAN — Schéma PostgreSQL multi-tenant
--  Plateforme tunisienne de résolution de litiges commerciaux pour PME
--  Hack4Justice — HiiL / ESPRIT
-- ---------------------------------------------------------------------
--  PRINCIPE DIRECTEUR
--
--  Ce schéma part d'un refus : ne pas faire reposer l'isolation des
--  données sur la discipline du code applicatif. Une colonne `org_id`
--  et un `WHERE org_id = ?` oublié dans une seule requête sur deux
--  cents, et la facture d'une PME se retrouve chez une autre. Ici,
--  l'isolation est déclarée au niveau de la base : Row Level Security,
--  FORCE ROW LEVEL SECURITY, politique par défaut fermée. Une requête
--  sans contexte ne renvoie pas une erreur — elle renvoie zéro ligne.
--
--  Le tenant n'est JAMAIS déclaré par le client. Le client annonce une
--  identité d'utilisateur (`mizan.user_id`) ; l'organisation et le rôle
--  sont RELUS DANS LA BASE à chaque évaluation de politique. Un client
--  compromis ne peut donc pas se prétendre membre d'une autre
--  organisation : il ne peut usurper qu'une identité, ce qui relève de
--  l'authentification, pas du cloisonnement.
--
--  Les rôles font autorité depuis web/lib/auth.ts :
--    platform_admin · msme · accredited_pro · court_clerk · huissier
--
--  Compatible PostgreSQL 13+ (testé sur 18.3).
--  Exécuter en tant que superutilisateur ou propriétaire de base.
-- =====================================================================

\set ON_ERROR_STOP on

BEGIN;

-- ---------------------------------------------------------------------
-- 0. Rôles base de données
--    mizan_owner : propriétaire du schéma (migrations)
--    mizan_app   : rôle applicatif — SANS BYPASSRLS. C'est lui qui se
--                  connecte depuis l'application Next.js.
--    FORCE ROW LEVEL SECURITY est activé sur chaque table : même le
--    propriétaire est soumis aux politiques.
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mizan_owner') THEN
    CREATE ROLE mizan_owner NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mizan_app') THEN
    CREATE ROLE mizan_app NOLOGIN;
  END IF;
END $$;

CREATE SCHEMA IF NOT EXISTS mizan AUTHORIZATION CURRENT_USER;
SET search_path = mizan, public;

-- pgcrypto seulement pour gen_random_uuid() ; sha256() est natif (PG 11+).
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------
-- 1. Domaines et énumérations métier
-- ---------------------------------------------------------------------

-- Les cinq rôles de web/lib/auth.ts. La base refuse tout autre libellé.
CREATE TYPE mizan.user_role AS ENUM (
  'platform_admin',   -- exploitation de la plateforme
  'msme',             -- la PME : dépose, consulte, accepte
  'accredited_pro',   -- médiateur · conciliateur · arbitre agréé
  'court_clerk',      -- greffier du tribunal de commerce
  'huissier'          -- عدل منفذ — CPC art. 5 et 60
);

-- Type d'organisation : le tenant. Un cabinet de médiation et une PME
-- sont deux tenants distincts, même s'ils travaillent sur le même litige.
CREATE TYPE mizan.org_kind AS ENUM (
  'pme',              -- la PME créancière ou débitrice
  'cabinet_mediation',-- cabinet de médiation / conciliation agréé
  'etude_huissier',   -- étude d'عدل منفذ
  'greffe',           -- greffe du tribunal de commerce
  'plateforme'        -- l'exploitant lui-même
);

-- États du dossier de litige, dans l'ordre du parcours réel.
CREATE TYPE mizan.dossier_state AS ENUM (
  'brouillon',         -- pièces en cours de dépôt
  'verifie',           -- pièces obligatoires présentes et passées par la porte
  'prescrit',          -- COC art. 402/403 : le délai est éteint — cul-de-sac
  'en_conciliation',   -- session E-CMA ouverte
  'accord_signe',      -- PV de conciliation signé (COC art. 1458)
  'projet_acte_pret',  -- projet de mise en demeure prêt à signifier
  'signifie',          -- signifié par huissier — CPC art. 5 et 60
  'transmis_greffe'    -- déposé au tribunal de commerce
);

-- Nature des pièces : reprise EXACTE des clés de h4j/app/dossier.py
-- (PIECES_ATTENDUES), pour que le manifeste produit par le moteur
-- juridique et la base parlent le même vocabulaire.
CREATE TYPE mizan.piece_kind AS ENUM (
  'facture',
  'mise_en_demeure',
  'preuve_livraison',  -- bon de livraison / preuve d'exécution
  'contrat',           -- contrat ou bon de commande
  'echanges'           -- emails, courriers
);

CREATE TYPE mizan.ecma_kind AS ENUM ('conciliation', 'mediation', 'arbitrage');

CREATE TYPE mizan.ecma_state AS ENUM (
  'planifiee', 'en_cours', 'ajournee', 'accord', 'echec', 'annulee'
);

-- Une empreinte SHA-256 est 64 caractères hexadécimaux minuscules.
-- Le domaine rend l'invariant inviolable, y compris par un import brut.
CREATE DOMAIN mizan.sha256_hex AS text
  CHECK (VALUE ~ '^[0-9a-f]{64}$');

-- Codes du corpus indexé (~/h4j/corpus/*.jsonl).
CREATE DOMAIN mizan.code_id AS text
  CHECK (VALUE IN ('coc','procciv','commerce','societes','fiscal','arbitrage'));

-- ---------------------------------------------------------------------
-- 2. Contexte de session — le socle de l'isolation
--
--  Le client ne pose QU'UN seul GUC : mizan.user_id.
--  L'organisation et le rôle sont relus dans mizan.app_user. Le client
--  ne peut donc pas revendiquer une organisation qui n'est pas la sienne.
--  Contexte absent ou utilisateur inconnu => NULL => toutes les
--  politiques sont fausses => zéro ligne. Fermé par défaut.
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION mizan.current_user_id() RETURNS uuid
LANGUAGE plpgsql STABLE AS $$
DECLARE v text;
BEGIN
  v := current_setting('mizan.user_id', true);
  IF v IS NULL OR v = '' THEN RETURN NULL; END IF;
  RETURN v::uuid;
EXCEPTION WHEN others THEN
  RETURN NULL;   -- un GUC malformé ne doit pas ouvrir de brèche
END $$;

-- Créée avant app_user : redéfinie plus bas une fois la table connue.
-- (déclaration différée — voir §4bis)

-- ---------------------------------------------------------------------
-- 3. Organisations (les tenants) et utilisateurs
-- ---------------------------------------------------------------------

CREATE TABLE mizan.organization (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind          mizan.org_kind NOT NULL,
  legal_name    text NOT NULL,
  legal_name_ar text,
  -- Matricule fiscal tunisien / identifiant RNE. Unique quand renseigné.
  tax_id        text UNIQUE,
  rne_id        text UNIQUE,
  -- Numéro d'agrément : exigé pour un cabinet de médiation ou une étude
  -- d'huissier. Une organisation qui prétend conduire une conciliation
  -- sans agrément n'a pas sa place dans la base.
  accreditation_no text,
  is_active     boolean NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT org_accreditation_requise CHECK (
    kind NOT IN ('cabinet_mediation','etude_huissier')
    OR (accreditation_no IS NOT NULL AND length(trim(accreditation_no)) > 0)
  )
);
COMMENT ON TABLE mizan.organization IS
  'Le tenant. Toute donnée métier appartient à exactement une organisation.';

CREATE TABLE mizan.app_user (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id     uuid NOT NULL REFERENCES mizan.organization(id) ON DELETE RESTRICT,
  role       mizan.user_role NOT NULL,
  email      text NOT NULL UNIQUE,
  full_name  text NOT NULL,
  -- Numéro d'inscription professionnelle (huissier, médiateur agréé).
  pro_licence_no text,
  is_active  boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  -- Un huissier ou un professionnel accrédité porte un numéro
  -- d'inscription : c'est ce qui autorise ses actes réservés (§8).
  CONSTRAINT user_licence_requise CHECK (
    role NOT IN ('huissier','accredited_pro')
    OR (pro_licence_no IS NOT NULL AND length(trim(pro_licence_no)) > 0)
  )
);
CREATE INDEX ON mizan.app_user (org_id);

-- Cohérence rôle ↔ type d'organisation : un huissier n'exerce pas
-- depuis une PME, un greffier n'exerce pas depuis un cabinet privé.
CREATE OR REPLACE FUNCTION mizan.trg_user_role_coherent() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE k mizan.org_kind;
BEGIN
  SELECT kind INTO k FROM mizan.organization WHERE id = NEW.org_id;
  IF (NEW.role = 'huissier'       AND k <> 'etude_huissier')
  OR (NEW.role = 'accredited_pro' AND k <> 'cabinet_mediation')
  OR (NEW.role = 'court_clerk'    AND k <> 'greffe')
  OR (NEW.role = 'msme'           AND k <> 'pme')
  OR (NEW.role = 'platform_admin' AND k <> 'plateforme') THEN
    RAISE EXCEPTION
      'Rôle % incompatible avec une organisation de type % (utilisateur %)',
      NEW.role, k, NEW.email
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER user_role_coherent
  BEFORE INSERT OR UPDATE OF role, org_id ON mizan.app_user
  FOR EACH ROW EXECUTE FUNCTION mizan.trg_user_role_coherent();

-- ---------------------------------------------------------------------
-- 4bis. Contexte (suite) — maintenant que app_user existe.
--
--  SECURITY DEFINER : la lecture du contexte doit ignorer la RLS, sinon
--  la politique s'appellerait elle-même (récursion infinie).
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION mizan.current_org() RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mizan, pg_temp AS $$
  SELECT u.org_id FROM mizan.app_user u
   WHERE u.id = mizan.current_user_id() AND u.is_active;
$$;
COMMENT ON FUNCTION mizan.current_org() IS
  'Organisation de l''appelant, RELUE DANS LA BASE. Le client ne peut pas la falsifier.';

CREATE OR REPLACE FUNCTION mizan.current_role_name() RETURNS mizan.user_role
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mizan, pg_temp AS $$
  SELECT u.role FROM mizan.app_user u
   WHERE u.id = mizan.current_user_id() AND u.is_active;
$$;

CREATE OR REPLACE FUNCTION mizan.is_platform_admin() RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT mizan.current_role_name() = 'platform_admin';
$$;

-- Confort applicatif : ouvre la session au nom d'un utilisateur.
-- Ne prend PAS d'org_id en paramètre — c'est volontaire.
CREATE OR REPLACE FUNCTION mizan.set_context(p_user_id uuid) RETURNS void
LANGUAGE sql VOLATILE AS $$
  SELECT set_config('mizan.user_id', p_user_id::text, false); SELECT NULL::void;
$$;

CREATE OR REPLACE FUNCTION mizan.clear_context() RETURNS void
LANGUAGE sql VOLATILE AS $$
  SELECT set_config('mizan.user_id', '', false); SELECT NULL::void;
$$;

-- ---------------------------------------------------------------------
-- 5. Corpus juridique (référentiel, non cloisonné)
--
--  4087 articles issus de ~/h4j/corpus/*.jsonl (clé 'text_ar').
--  Ce référentiel est COMMUN à tous les tenants : la loi tunisienne
--  n'appartient à personne. Il est donc en lecture pour tous, et en
--  écriture pour le seul platform_admin (permission manage_corpus).
-- ---------------------------------------------------------------------

CREATE TABLE mizan.corpus_article (
  id           text PRIMARY KEY,              -- ex. 'procciv-art60'
  code_id      mizan.code_id NOT NULL,
  code_ar      text NOT NULL,
  code_fr      text NOT NULL,
  article      integer NOT NULL CHECK (article > 0),
  citation_ar  text NOT NULL,
  text_ar      text NOT NULL CHECK (length(trim(text_ar)) > 0),
  n_chars      integer GENERATED ALWAYS AS (length(text_ar)) STORED,
  source_method text,                          -- 'ocr' | NULL
  -- Empreinte du texte verbatim : c'est elle qui sert de preuve de
  -- relecture au moment d'attacher une citation à un dossier (§7).
  text_sha256  mizan.sha256_hex NOT NULL,
  imported_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (code_id, article)
);
CREATE INDEX ON mizan.corpus_article (code_id, article);

-- L'empreinte n'est jamais fournie par le client : elle est calculée.
CREATE OR REPLACE FUNCTION mizan.trg_corpus_hash() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.text_sha256 := encode(sha256(convert_to(NEW.text_ar, 'UTF8')), 'hex');
  RETURN NEW;
END $$;

CREATE TRIGGER corpus_hash
  BEFORE INSERT OR UPDATE OF text_ar ON mizan.corpus_article
  FOR EACH ROW EXECUTE FUNCTION mizan.trg_corpus_hash();

-- ---------------------------------------------------------------------
-- 6. Dossiers de litige
-- ---------------------------------------------------------------------

CREATE TABLE mizan.dossier (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  -- LE cloisonnement : organisation propriétaire du dossier.
  org_id        uuid NOT NULL REFERENCES mizan.organization(id) ON DELETE RESTRICT,
  -- Référence MZ-AAAAMMJJ-XXXX, déterministe (h4j/app/dossier.py).
  reference     text NOT NULL,
  state         mizan.dossier_state NOT NULL DEFAULT 'brouillon',

  creancier     text NOT NULL,
  debiteur      text NOT NULL,
  montant_tnd   numeric(14,3) NOT NULL CHECK (montant_tnd > 0),
  invoice_date  date NOT NULL,
  activity      text,                          -- qualifie le régime de prescription

  -- Verdict du moteur juridique (h4j/app/legal_engine.py). Recopié ici
  -- pour être auditable, jamais recalculé à la volée par l'interface.
  regime            text CHECK (regime IN ('goods_1y','general_15y','indetermine')),
  prescription_deadline date,
  needs_bailiff     boolean,                   -- CPC art. 60 : > 150 DT

  created_by    uuid NOT NULL REFERENCES mizan.app_user(id),
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  -- Renseignés par le trigger de l'acte réservé (§8).
  signified_at  timestamptz,
  signified_by  uuid REFERENCES mizan.app_user(id),

  UNIQUE (org_id, reference),
  -- Une facture ne peut pas être datée du futur : le moteur juridique
  -- lève DateImpossible, la base le refuse aussi.
  CONSTRAINT facture_pas_dans_le_futur CHECK (invoice_date <= CURRENT_DATE),
  -- L'état 'signifie' ne peut exister sans trace de qui a signifié.
  CONSTRAINT signification_tracee CHECK (
    (state <> 'signifie') OR (signified_at IS NOT NULL AND signified_by IS NOT NULL)
  )
);
CREATE INDEX ON mizan.dossier (org_id, state);
CREATE INDEX ON mizan.dossier (prescription_deadline) WHERE state <> 'prescrit';

-- ---------------------------------------------------------------------
-- 6bis. Partage explicite d'un dossier entre organisations
--
--  Un médiateur doit pouvoir instruire le dossier d'une PME. Mais la
--  visibilité ne doit JAMAIS être implicite : elle est une ligne de
--  table, datée, attribuée, révocable, et auditée. Sans ligne ici,
--  aucune organisation tierce ne voit quoi que ce soit.
-- ---------------------------------------------------------------------

CREATE TABLE mizan.dossier_access (
  dossier_id  uuid NOT NULL REFERENCES mizan.dossier(id) ON DELETE CASCADE,
  org_id      uuid NOT NULL REFERENCES mizan.organization(id) ON DELETE CASCADE,
  granted_by  uuid NOT NULL REFERENCES mizan.app_user(id),
  granted_at  timestamptz NOT NULL DEFAULT now(),
  revoked_at  timestamptz,
  reason      text,
  PRIMARY KEY (dossier_id, org_id)
);
CREATE INDEX ON mizan.dossier_access (org_id) WHERE revoked_at IS NULL;

-- Prédicat unique réutilisé par toutes les politiques métier.
-- SECURITY DEFINER : il doit voir dossier_access sans être filtré par
-- la RLS de dossier_access elle-même.
CREATE OR REPLACE FUNCTION mizan.can_see_dossier(p_dossier uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mizan, pg_temp AS $$
  SELECT mizan.is_platform_admin()
      OR EXISTS (SELECT 1 FROM mizan.dossier d
                  WHERE d.id = p_dossier AND d.org_id = mizan.current_org())
      OR EXISTS (SELECT 1 FROM mizan.dossier_access a
                  WHERE a.dossier_id = p_dossier
                    AND a.org_id = mizan.current_org()
                    AND a.revoked_at IS NULL);
$$;

-- ---------------------------------------------------------------------
-- 7. Pièces justificatives — empreinte SHA-256 obligatoire
--
--  L'empreinte est ce qui permet à un greffier d'affirmer que la
--  facture qu'il lit est bien celle qui a été déposée. Elle est donc
--  immuable : la modifier reviendrait à effacer la preuve.
-- ---------------------------------------------------------------------

CREATE TABLE mizan.piece (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  dossier_id  uuid NOT NULL REFERENCES mizan.dossier(id) ON DELETE CASCADE,
  -- Dénormalisé VOLONTAIREMENT : la politique RLS doit pouvoir trancher
  -- sans jointure, et une pièce reste rattachée à son déposant même si
  -- le dossier est partagé. Le trigger ci-dessous garantit la cohérence.
  org_id      uuid NOT NULL REFERENCES mizan.organization(id),
  kind        mizan.piece_kind NOT NULL,
  filename    text NOT NULL CHECK (length(trim(filename)) > 0),
  mime_type   text,
  n_bytes     bigint NOT NULL CHECK (n_bytes > 0),
  sha256      mizan.sha256_hex NOT NULL,
  storage_uri text NOT NULL,
  -- Verdict de la porte d'entrée (h4j/app/gate.py, doc_gate) au dépôt.
  gate_ok     boolean NOT NULL DEFAULT true,
  gate_reason text,
  source_method text NOT NULL DEFAULT 'upload',
  uploaded_by uuid NOT NULL REFERENCES mizan.app_user(id),
  uploaded_at timestamptz NOT NULL DEFAULT now(),
  -- Une pièce refusée doit dire pourquoi. Un refus sans motif n'est
  -- pas opposable au déposant.
  CONSTRAINT refus_motive CHECK (
    gate_ok OR (gate_reason IS NOT NULL AND length(trim(gate_reason)) > 0)
  ),
  -- Deux fois la même pièce dans le même dossier : c'est un doublon.
  UNIQUE (dossier_id, sha256)
);
CREATE INDEX ON mizan.piece (org_id);
CREATE INDEX ON mizan.piece (dossier_id);

-- org_id de la pièce = org_id du dossier. Non négociable, sinon la
-- dénormalisation ci-dessus deviendrait un trou de sécurité.
CREATE OR REPLACE FUNCTION mizan.trg_piece_org_coherent() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = mizan, pg_temp AS $$
DECLARE o uuid;
BEGIN
  SELECT d.org_id INTO o FROM mizan.dossier d WHERE d.id = NEW.dossier_id;
  IF o IS NULL THEN
    RAISE EXCEPTION 'Dossier % inexistant', NEW.dossier_id;
  END IF;
  NEW.org_id := o;   -- imposé, pas vérifié : le client ne le choisit pas
  RETURN NEW;
END $$;

CREATE TRIGGER piece_org_coherent
  BEFORE INSERT OR UPDATE OF dossier_id, org_id ON mizan.piece
  FOR EACH ROW EXECUTE FUNCTION mizan.trg_piece_org_coherent();

-- L'empreinte et le contenu sont immuables. On peut retirer une pièce,
-- on ne peut pas la réécrire en silence.
CREATE OR REPLACE FUNCTION mizan.trg_piece_empreinte_immuable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.sha256 IS DISTINCT FROM OLD.sha256
  OR NEW.n_bytes IS DISTINCT FROM OLD.n_bytes
  OR NEW.storage_uri IS DISTINCT FROM OLD.storage_uri THEN
    RAISE EXCEPTION
      'Empreinte de pièce immuable : la pièce % ne peut pas être réécrite (déposez une nouvelle pièce)',
      OLD.id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER piece_empreinte_immuable
  BEFORE UPDATE ON mizan.piece
  FOR EACH ROW EXECUTE FUNCTION mizan.trg_piece_empreinte_immuable();

-- ---------------------------------------------------------------------
-- 8. Citations juridiques attachées à un dossier
--
--  EXIGENCE : impossible d'enregistrer une citation sans texte vérifié.
--  « Vérifié » ne veut pas dire « non vide » : le texte verbatim doit
--  correspondre AU CARACTÈRE PRÈS à l'article du corpus, contrôlé par
--  comparaison d'empreintes SHA-256. Une citation approximative, ou
--  produite par un modèle de langage, est rejetée par la base.
-- ---------------------------------------------------------------------

CREATE TABLE mizan.dossier_citation (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  dossier_id  uuid NOT NULL REFERENCES mizan.dossier(id) ON DELETE CASCADE,
  org_id      uuid NOT NULL REFERENCES mizan.organization(id),
  corpus_id   text NOT NULL REFERENCES mizan.corpus_article(id) ON DELETE RESTRICT,
  code_id     mizan.code_id NOT NULL,
  article     integer NOT NULL CHECK (article > 0),
  citation_ar text NOT NULL,
  -- Le texte relu, recopié depuis le corpus au moment de l'attachement.
  verbatim_ar text NOT NULL,
  verbatim_sha256 mizan.sha256_hex NOT NULL,
  -- Preuve explicite de relecture : NOT NULL + CHECK vrai. Aucune
  -- citation ne peut être insérée avec verified = false.
  verified    boolean NOT NULL DEFAULT true,
  verified_at timestamptz NOT NULL DEFAULT now(),
  attached_by uuid NOT NULL REFERENCES mizan.app_user(id),
  role_fr     text,                             -- ex. 'prescription_goods'
  UNIQUE (dossier_id, corpus_id),
  -- Barrière déclarative n°1 : un texte vide n'est pas une citation.
  CONSTRAINT citation_texte_non_vide CHECK (length(trim(verbatim_ar)) > 0),
  -- Barrière déclarative n°2 : la vérification n'est pas optionnelle.
  CONSTRAINT citation_obligatoirement_verifiee CHECK (verified),
  -- Barrière déclarative n°3 : l'empreinte déclarée est bien celle du
  -- texte stocké. Immuable et vérifiable sans quitter la ligne.
  CONSTRAINT citation_empreinte_coherente CHECK (
    verbatim_sha256 = encode(sha256(convert_to(verbatim_ar, 'UTF8')), 'hex')
  )
);
CREATE INDEX ON mizan.dossier_citation (dossier_id);
CREATE INDEX ON mizan.dossier_citation (org_id);

-- Barrière n°4, la décisive : le texte doit être CELUI DU CORPUS.
-- Un CHECK ne peut pas interroger une autre table ; c'est donc un
-- trigger, qui va lire l'article et comparer les empreintes.
CREATE OR REPLACE FUNCTION mizan.trg_citation_relue() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = mizan, pg_temp AS $$
DECLARE a mizan.corpus_article%ROWTYPE;
        o uuid;
BEGIN
  SELECT * INTO a FROM mizan.corpus_article WHERE id = NEW.corpus_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION
      'Citation refusée : l''article % ne figure pas dans le corpus indexé',
      NEW.corpus_id USING ERRCODE = 'foreign_key_violation';
  END IF;

  -- L'empreinte du verbatim doit égaler celle de l'article du corpus.
  IF NEW.verbatim_sha256 <> a.text_sha256 THEN
    RAISE EXCEPTION
      'Citation refusée : le texte attaché au dossier ne correspond pas au texte du corpus pour % (attendu %, reçu %). Mizan n''enregistre aucune citation non relue.',
      NEW.corpus_id, a.text_sha256, NEW.verbatim_sha256
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;

  IF NEW.code_id <> a.code_id OR NEW.article <> a.article THEN
    RAISE EXCEPTION
      'Citation refusée : référence incohérente (% art. % ≠ % art. %)',
      NEW.code_id, NEW.article, a.code_id, a.article
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;

  NEW.citation_ar := a.citation_ar;   -- la référence arabe fait foi

  SELECT d.org_id INTO o FROM mizan.dossier d WHERE d.id = NEW.dossier_id;
  NEW.org_id := o;
  RETURN NEW;
END $$;

CREATE TRIGGER citation_relue
  BEFORE INSERT OR UPDATE ON mizan.dossier_citation
  FOR EACH ROW EXECUTE FUNCTION mizan.trg_citation_relue();

-- ---------------------------------------------------------------------
-- 9. Sessions E-CMA (conciliation / médiation / arbitrage)
-- ---------------------------------------------------------------------

CREATE TABLE mizan.ecma_session (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  dossier_id   uuid NOT NULL REFERENCES mizan.dossier(id) ON DELETE CASCADE,
  org_id       uuid NOT NULL REFERENCES mizan.organization(id),  -- org du dossier
  kind         mizan.ecma_kind NOT NULL,
  state        mizan.ecma_state NOT NULL DEFAULT 'planifiee',
  -- Le professionnel accrédité qui conduit la session, et son cabinet.
  pro_user_id  uuid REFERENCES mizan.app_user(id),
  pro_org_id   uuid REFERENCES mizan.organization(id),
  scheduled_at timestamptz NOT NULL,
  opened_at    timestamptz,
  closed_at    timestamptz,
  minutes_ar   text,                    -- محضر — corps du PV
  minutes_fr   text,
  opened_by    uuid NOT NULL REFERENCES mizan.app_user(id),
  created_at   timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ecma_chronologie CHECK (
    (opened_at IS NULL OR opened_at >= scheduled_at - interval '1 day')
    AND (closed_at IS NULL OR opened_at IS NOT NULL)
    AND (closed_at IS NULL OR closed_at >= opened_at)
  )
);
CREATE INDEX ON mizan.ecma_session (dossier_id);
CREATE INDEX ON mizan.ecma_session (org_id);
CREATE INDEX ON mizan.ecma_session (pro_org_id);

CREATE TABLE mizan.ecma_participant (
  session_id uuid NOT NULL REFERENCES mizan.ecma_session(id) ON DELETE CASCADE,
  user_id    uuid NOT NULL REFERENCES mizan.app_user(id) ON DELETE RESTRICT,
  -- Qualité procédurale, distincte du rôle applicatif.
  partie     text NOT NULL CHECK (partie IN
               ('creancier','debiteur','conciliateur','observateur','greffe')),
  invited_at timestamptz NOT NULL DEFAULT now(),
  joined_at  timestamptz,
  PRIMARY KEY (session_id, user_id)
);

-- Le PV de conciliation : c'est lui que seul un accredited_pro signe.
CREATE TABLE mizan.settlement_minutes (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id  uuid NOT NULL UNIQUE REFERENCES mizan.ecma_session(id) ON DELETE CASCADE,
  dossier_id  uuid NOT NULL REFERENCES mizan.dossier(id) ON DELETE CASCADE,
  org_id      uuid NOT NULL REFERENCES mizan.organization(id),
  body_ar     text NOT NULL CHECK (length(trim(body_ar)) > 0),
  amount_agreed_tnd numeric(14,3) CHECK (amount_agreed_tnd IS NULL OR amount_agreed_tnd >= 0),
  content_sha256 mizan.sha256_hex NOT NULL,
  drafted_by  uuid NOT NULL REFERENCES mizan.app_user(id),
  drafted_at  timestamptz NOT NULL DEFAULT now(),
  -- Signature : COC art. 1458 (transaction) — acte réservé §10.
  signed_by   uuid REFERENCES mizan.app_user(id),
  signed_at   timestamptz,
  CONSTRAINT signature_complete CHECK (
    (signed_by IS NULL) = (signed_at IS NULL)
  )
);
CREATE INDEX ON mizan.settlement_minutes (org_id);

-- ---------------------------------------------------------------------
-- 10. ACTES RÉSERVÉS — la contrainte juridique matérialisée
--
--  CPC art. 5  : toute citation, notification ou exécution passe par
--                l'عدل منفذ.
--  CPC art. 60 : au-delà de 150 DT, l'إنذار doit être signifié par son
--                intermédiaire, cinq jours francs avant saisine.
--  => La base refuse le passage à 'signifie' par quiconque n'est pas
--     huissier. Pas un commentaire : une exception.
--
--  COC art. 1458 / brief §6 : le PV de conciliation est signé par le
--  professionnel accrédité. => signed_by doit être un accredited_pro.
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION mizan.trg_dossier_actes_reserves() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = mizan, pg_temp AS $$
DECLARE r mizan.user_role := mizan.current_role_name();
        acteur uuid := mizan.current_user_id();
        n_signature integer;
BEGIN
  NEW.updated_at := now();

  -- ---- Acte réservé n°1 : la signification -------------------------
  IF NEW.state = 'signifie' AND OLD.state IS DISTINCT FROM 'signifie' THEN
    IF r IS DISTINCT FROM 'huissier' THEN
      RAISE EXCEPTION
        'Acte réservé : seul un huissier de justice (عدل منفذ) peut faire passer un dossier à l''état « signifié ». Rôle de l''appelant : %. Fondement : CPC art. 5 et 60.',
        COALESCE(r::text, 'aucun contexte')
        USING ERRCODE = 'insufficient_privilege';
    END IF;
    -- La trace est imposée par la base, pas fournie par le client.
    NEW.signified_by := acteur;
    NEW.signified_at := COALESCE(NEW.signified_at, now());
    -- On ne signifie pas un dossier qui n'a pas de projet d'acte prêt.
    IF OLD.state NOT IN ('projet_acte_pret','verifie') THEN
      RAISE EXCEPTION
        'Transition interdite : % -> signifie. Un projet d''acte doit être prêt avant signification.',
        OLD.state USING ERRCODE = 'check_violation';
    END IF;
  END IF;

  -- Une fois signifié, l'acte ne se dé-signifie pas.
  IF OLD.state = 'signifie' AND NEW.state <> 'signifie'
     AND NEW.state <> 'transmis_greffe' THEN
    RAISE EXCEPTION
      'Transition interdite : un dossier signifié ne peut que passer au greffe (tentative : % -> %)',
      OLD.state, NEW.state USING ERRCODE = 'check_violation';
  END IF;

  -- ---- Acte réservé n°2 : l'accord signé ---------------------------
  -- Un dossier ne passe à 'accord_signe' que s'il existe un PV
  -- effectivement signé par un professionnel accrédité.
  IF NEW.state = 'accord_signe' AND OLD.state IS DISTINCT FROM 'accord_signe' THEN
    SELECT count(*) INTO n_signature
      FROM mizan.settlement_minutes m
      JOIN mizan.app_user s ON s.id = m.signed_by
     WHERE m.dossier_id = NEW.id
       AND m.signed_at IS NOT NULL
       AND s.role = 'accredited_pro';
    IF n_signature = 0 THEN
      RAISE EXCEPTION
        'Acte réservé : l''état « accord signé » suppose un PV de conciliation signé par un professionnel accrédité (COC art. 1458). Aucun PV signé trouvé pour le dossier %.',
        NEW.reference USING ERRCODE = 'insufficient_privilege';
    END IF;
  END IF;

  -- ---- Un dossier prescrit est un cul-de-sac -----------------------
  IF OLD.state = 'prescrit' AND NEW.state <> 'prescrit' THEN
    RAISE EXCEPTION
      'Transition interdite : un dossier prescrit (COC art. 402/403) ne peut pas être réactivé.'
      USING ERRCODE = 'check_violation';
  END IF;

  RETURN NEW;
END $$;

CREATE TRIGGER dossier_actes_reserves
  BEFORE UPDATE ON mizan.dossier
  FOR EACH ROW EXECUTE FUNCTION mizan.trg_dossier_actes_reserves();

-- Signature du PV : réservée à l'accredited_pro, et à lui seul.
CREATE OR REPLACE FUNCTION mizan.trg_pv_signature_reservee() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = mizan, pg_temp AS $$
DECLARE r_signataire mizan.user_role;
        r_appelant   mizan.user_role := mizan.current_role_name();
BEGIN
  -- L'empreinte du PV est calculée, jamais déclarée.
  NEW.content_sha256 := encode(sha256(convert_to(NEW.body_ar,'UTF8')),'hex');

  IF TG_OP = 'UPDATE' THEN
    -- Un PV signé est figé : ni le corps ni le signataire ne bougent.
    IF OLD.signed_at IS NOT NULL THEN
      IF NEW.body_ar IS DISTINCT FROM OLD.body_ar
      OR NEW.signed_by IS DISTINCT FROM OLD.signed_by
      OR NEW.signed_at IS DISTINCT FROM OLD.signed_at THEN
        RAISE EXCEPTION
          'PV de conciliation déjà signé le % : son contenu et sa signature sont figés.',
          OLD.signed_at USING ERRCODE = 'integrity_constraint_violation';
      END IF;
    END IF;
  END IF;

  IF NEW.signed_by IS NOT NULL
     AND (TG_OP = 'INSERT' OR OLD.signed_by IS DISTINCT FROM NEW.signed_by) THEN
    SELECT role INTO r_signataire FROM mizan.app_user WHERE id = NEW.signed_by;
    IF r_signataire IS DISTINCT FROM 'accredited_pro' THEN
      RAISE EXCEPTION
        'Acte réservé : seul un professionnel accrédité (médiateur · conciliateur · arbitre) peut signer un PV de conciliation. Rôle du signataire : %.',
        COALESCE(r_signataire::text, 'utilisateur inconnu')
        USING ERRCODE = 'insufficient_privilege';
    END IF;
    -- On ne signe pas à la place d'un autre.
    IF r_appelant IS DISTINCT FROM 'accredited_pro'
       OR mizan.current_user_id() IS DISTINCT FROM NEW.signed_by THEN
      RAISE EXCEPTION
        'Acte réservé : la signature d''un PV ne peut pas être apposée pour le compte d''autrui (appelant %, signataire déclaré %).',
        COALESCE(mizan.current_user_id()::text,'aucun contexte'), NEW.signed_by
        USING ERRCODE = 'insufficient_privilege';
    END IF;
    NEW.signed_at := COALESCE(NEW.signed_at, now());
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER pv_signature_reservee
  BEFORE INSERT OR UPDATE ON mizan.settlement_minutes
  FOR EACH ROW EXECUTE FUNCTION mizan.trg_pv_signature_reservee();

-- ---------------------------------------------------------------------
-- 11. JOURNAL D'AUDIT INALTÉRABLE
--
--  Trois verrous superposés :
--   a) privilèges : mizan_app n'a que INSERT et SELECT (§13) ;
--   b) trigger : UPDATE et DELETE lèvent une exception, y compris pour
--      le propriétaire de la table ;
--   c) chaînage cryptographique : chaque entrée scelle l'empreinte de
--      la précédente. Supprimer ou réécrire une ligne casse la chaîne,
--      et mizan.verify_audit_chain() le montre.
-- ---------------------------------------------------------------------

CREATE TABLE mizan.audit_log (
  seq         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  org_id      uuid REFERENCES mizan.organization(id),
  actor_id    uuid REFERENCES mizan.app_user(id),
  actor_role  mizan.user_role,
  action      text NOT NULL CHECK (length(trim(action)) > 0),
  object_type text NOT NULL,
  object_id   text,
  dossier_id  uuid REFERENCES mizan.dossier(id),
  details     jsonb NOT NULL DEFAULT '{}'::jsonb,
  db_user     text NOT NULL DEFAULT current_user,
  prev_hash   mizan.sha256_hex,
  entry_hash  mizan.sha256_hex NOT NULL
);
CREATE INDEX ON mizan.audit_log (org_id, occurred_at DESC);
CREATE INDEX ON mizan.audit_log (dossier_id);

CREATE OR REPLACE FUNCTION mizan.trg_audit_seal() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = mizan, pg_temp AS $$
DECLARE p mizan.sha256_hex;
BEGIN
  -- Sérialise le chaînage : deux inserts concurrents ne peuvent pas
  -- lire le même maillon précédent.
  PERFORM pg_advisory_xact_lock(hashtext('mizan.audit_log'));
  SELECT entry_hash INTO p FROM mizan.audit_log ORDER BY seq DESC LIMIT 1;

  NEW.prev_hash  := p;
  NEW.org_id     := COALESCE(NEW.org_id, mizan.current_org());
  NEW.actor_id   := COALESCE(NEW.actor_id, mizan.current_user_id());
  NEW.actor_role := COALESCE(NEW.actor_role, mizan.current_role_name());
  NEW.db_user    := current_user;
  NEW.occurred_at := clock_timestamp();
  NEW.entry_hash := encode(sha256(convert_to(
      COALESCE(p,'GENESIS') || '|' ||
      NEW.occurred_at::text || '|' ||
      COALESCE(NEW.org_id::text,'') || '|' ||
      COALESCE(NEW.actor_id::text,'') || '|' ||
      COALESCE(NEW.actor_role::text,'') || '|' ||
      NEW.action || '|' || NEW.object_type || '|' ||
      COALESCE(NEW.object_id,'') || '|' ||
      COALESCE(NEW.dossier_id::text,'') || '|' ||
      NEW.details::text, 'UTF8')), 'hex');
  RETURN NEW;
END $$;

CREATE TRIGGER audit_seal
  BEFORE INSERT ON mizan.audit_log
  FOR EACH ROW EXECUTE FUNCTION mizan.trg_audit_seal();

-- Verrou (b) : insertion seule. Aucune modification, aucune suppression.
CREATE OR REPLACE FUNCTION mizan.trg_audit_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION
    'Journal d''audit inaltérable : % interdit sur mizan.audit_log (insertion seule).',
    TG_OP USING ERRCODE = 'insufficient_privilege';
END $$;

CREATE TRIGGER audit_no_update BEFORE UPDATE ON mizan.audit_log
  FOR EACH ROW EXECUTE FUNCTION mizan.trg_audit_append_only();
CREATE TRIGGER audit_no_delete BEFORE DELETE ON mizan.audit_log
  FOR EACH ROW EXECUTE FUNCTION mizan.trg_audit_append_only();
CREATE TRIGGER audit_no_truncate BEFORE TRUNCATE ON mizan.audit_log
  FOR EACH STATEMENT EXECUTE FUNCTION mizan.trg_audit_append_only();

-- Verrou (c) : contrôle de la chaîne. Renvoie les maillons rompus ;
-- aucune ligne = journal intact.
CREATE OR REPLACE FUNCTION mizan.verify_audit_chain()
RETURNS TABLE (seq bigint, probleme text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mizan, pg_temp AS $$
  WITH chaine AS (
    SELECT a.seq, a.prev_hash, a.entry_hash,
           lag(a.entry_hash) OVER (ORDER BY a.seq) AS attendu,
           encode(sha256(convert_to(
             COALESCE(a.prev_hash,'GENESIS') || '|' || a.occurred_at::text || '|' ||
             COALESCE(a.org_id::text,'') || '|' || COALESCE(a.actor_id::text,'') || '|' ||
             COALESCE(a.actor_role::text,'') || '|' || a.action || '|' ||
             a.object_type || '|' || COALESCE(a.object_id,'') || '|' ||
             COALESCE(a.dossier_id::text,'') || '|' || a.details::text, 'UTF8')),'hex')
             AS recalcule
      FROM mizan.audit_log a
  )
  SELECT c.seq,
         CASE WHEN c.entry_hash <> c.recalcule
                THEN 'entrée réécrite : empreinte incohérente'
              ELSE 'maillon rompu : entrée supprimée ou insérée hors chaîne'
         END
    FROM chaine c
   WHERE c.entry_hash <> c.recalcule
      OR c.prev_hash IS DISTINCT FROM c.attendu;
$$;

-- Écriture d'audit depuis l'application (ou depuis un trigger métier).
CREATE OR REPLACE FUNCTION mizan.audit(
  p_action text, p_object_type text, p_object_id text DEFAULT NULL,
  p_dossier uuid DEFAULT NULL, p_details jsonb DEFAULT '{}'::jsonb)
RETURNS bigint
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = mizan, pg_temp AS $$
  INSERT INTO mizan.audit_log (action, object_type, object_id, dossier_id, details)
  VALUES (p_action, p_object_type, p_object_id, p_dossier, p_details)
  RETURNING seq;
$$;

-- Audit automatique des transitions d'état : le trigger métier ne peut
-- pas être contourné par l'application, donc la trace non plus.
CREATE OR REPLACE FUNCTION mizan.trg_dossier_audit() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = mizan, pg_temp AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    INSERT INTO mizan.audit_log (org_id, action, object_type, object_id, dossier_id, details)
    VALUES (NEW.org_id, 'dossier.cree', 'dossier', NEW.reference, NEW.id,
            jsonb_build_object('etat', NEW.state, 'montant_tnd', NEW.montant_tnd));
  ELSIF NEW.state IS DISTINCT FROM OLD.state THEN
    INSERT INTO mizan.audit_log (org_id, action, object_type, object_id, dossier_id, details)
    VALUES (NEW.org_id, 'dossier.transition', 'dossier', NEW.reference, NEW.id,
            jsonb_build_object('de', OLD.state, 'vers', NEW.state));
  END IF;
  RETURN NULL;
END $$;

CREATE TRIGGER dossier_audit
  AFTER INSERT OR UPDATE ON mizan.dossier
  FOR EACH ROW EXECUTE FUNCTION mizan.trg_dossier_audit();

CREATE OR REPLACE FUNCTION mizan.trg_piece_audit() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = mizan, pg_temp AS $$
BEGIN
  INSERT INTO mizan.audit_log (org_id, action, object_type, object_id, dossier_id, details)
  VALUES (NEW.org_id, 'piece.deposee', 'piece', NEW.id::text, NEW.dossier_id,
          jsonb_build_object('nature', NEW.kind, 'sha256', NEW.sha256,
                             'gate_ok', NEW.gate_ok, 'fichier', NEW.filename));
  RETURN NULL;
END $$;

CREATE TRIGGER piece_audit AFTER INSERT ON mizan.piece
  FOR EACH ROW EXECUTE FUNCTION mizan.trg_piece_audit();

-- ---------------------------------------------------------------------
-- 11bis. Amorçage de la plateforme
--
--  Problème d'œuf et de poule : toutes les politiques exigent un
--  contexte utilisateur, mais le tout premier utilisateur ne peut être
--  créé par personne. Plutôt que d'inviter l'exploitant à désactiver la
--  RLS « juste une fois » — geste qu'on finit toujours par refaire en
--  production — l'amorçage est une fonction SECURITY DEFINER, bornée :
--  elle refuse de s'exécuter dès qu'une organisation existe.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION mizan.bootstrap_platform(
  p_org_name text, p_admin_email text, p_admin_name text,
  p_org_id uuid DEFAULT gen_random_uuid(),
  p_admin_id uuid DEFAULT gen_random_uuid())
RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = mizan, pg_temp AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM mizan.organization) THEN
    RAISE EXCEPTION
      'Amorçage refusé : la plateforme est déjà initialisée. Créez les organisations suivantes avec un contexte platform_admin.'
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  INSERT INTO mizan.organization (id, kind, legal_name)
  VALUES (p_org_id, 'plateforme', p_org_name);
  INSERT INTO mizan.app_user (id, org_id, role, email, full_name)
  VALUES (p_admin_id, p_org_id, 'platform_admin', p_admin_email, p_admin_name);
  RETURN p_admin_id;
END $$;

-- =====================================================================
-- 12. ROW LEVEL SECURITY
--
--  Modèle : refus par défaut. Chaque table porte ENABLE + FORCE, et
--  n'expose une ligne que si l'appelant appartient à l'organisation
--  propriétaire, ou dispose d'un partage explicite, ou est
--  platform_admin (permission view_all de auth.ts).
--
--  FORCE ROW LEVEL SECURITY est essentiel : sans lui, le propriétaire
--  des tables — donc les migrations, donc un pool mal configuré —
--  verrait tout.
-- =====================================================================

ALTER TABLE mizan.organization       ENABLE ROW LEVEL SECURITY;
ALTER TABLE mizan.organization       FORCE  ROW LEVEL SECURITY;
ALTER TABLE mizan.app_user           ENABLE ROW LEVEL SECURITY;
ALTER TABLE mizan.app_user           FORCE  ROW LEVEL SECURITY;
ALTER TABLE mizan.dossier            ENABLE ROW LEVEL SECURITY;
ALTER TABLE mizan.dossier            FORCE  ROW LEVEL SECURITY;
ALTER TABLE mizan.dossier_access     ENABLE ROW LEVEL SECURITY;
ALTER TABLE mizan.dossier_access     FORCE  ROW LEVEL SECURITY;
ALTER TABLE mizan.piece              ENABLE ROW LEVEL SECURITY;
ALTER TABLE mizan.piece              FORCE  ROW LEVEL SECURITY;
ALTER TABLE mizan.dossier_citation   ENABLE ROW LEVEL SECURITY;
ALTER TABLE mizan.dossier_citation   FORCE  ROW LEVEL SECURITY;
ALTER TABLE mizan.ecma_session       ENABLE ROW LEVEL SECURITY;
ALTER TABLE mizan.ecma_session       FORCE  ROW LEVEL SECURITY;
ALTER TABLE mizan.ecma_participant   ENABLE ROW LEVEL SECURITY;
ALTER TABLE mizan.ecma_participant   FORCE  ROW LEVEL SECURITY;
ALTER TABLE mizan.settlement_minutes ENABLE ROW LEVEL SECURITY;
ALTER TABLE mizan.settlement_minutes FORCE  ROW LEVEL SECURITY;
ALTER TABLE mizan.audit_log          ENABLE ROW LEVEL SECURITY;
ALTER TABLE mizan.audit_log          FORCE  ROW LEVEL SECURITY;
ALTER TABLE mizan.corpus_article     ENABLE ROW LEVEL SECURITY;
ALTER TABLE mizan.corpus_article     FORCE  ROW LEVEL SECURITY;

-- --- organization : on ne voit que la sienne (et celles avec qui on
--     partage un dossier, pour pouvoir nommer son interlocuteur).
CREATE POLICY org_visible ON mizan.organization FOR SELECT
  USING (
    mizan.is_platform_admin()
    OR id = mizan.current_org()
    OR EXISTS (
      SELECT 1 FROM mizan.dossier_access a
       JOIN mizan.dossier d ON d.id = a.dossier_id
      WHERE a.revoked_at IS NULL
        AND ((a.org_id = mizan.current_org() AND d.org_id = organization.id)
          OR (d.org_id = mizan.current_org() AND a.org_id = organization.id)))
  );
CREATE POLICY org_admin_write ON mizan.organization FOR ALL
  USING (mizan.is_platform_admin()) WITH CHECK (mizan.is_platform_admin());

-- --- app_user : annuaire strictement interne au tenant.
CREATE POLICY user_meme_org ON mizan.app_user FOR SELECT
  USING (mizan.is_platform_admin() OR org_id = mizan.current_org());
CREATE POLICY user_admin_write ON mizan.app_user FOR ALL
  USING (mizan.is_platform_admin()) WITH CHECK (mizan.is_platform_admin());

-- --- corpus_article : la loi est commune. Lecture pour tout contexte
--     valide, écriture réservée au platform_admin (manage_corpus).
CREATE POLICY corpus_lecture ON mizan.corpus_article FOR SELECT
  USING (mizan.current_user_id() IS NOT NULL);
CREATE POLICY corpus_ecriture ON mizan.corpus_article FOR ALL
  USING (mizan.is_platform_admin()) WITH CHECK (mizan.is_platform_admin());

-- --- dossier : organisation propriétaire, ou partage explicite.
CREATE POLICY dossier_lecture ON mizan.dossier FOR SELECT
  USING (mizan.can_see_dossier(id));
CREATE POLICY dossier_creation ON mizan.dossier FOR INSERT
  WITH CHECK (org_id = mizan.current_org()
              AND mizan.current_role_name() IN ('msme','platform_admin'));
CREATE POLICY dossier_modification ON mizan.dossier FOR UPDATE
  USING (mizan.can_see_dossier(id))
  WITH CHECK (org_id = (SELECT d.org_id FROM mizan.dossier d WHERE d.id = dossier.id));
CREATE POLICY dossier_suppression ON mizan.dossier FOR DELETE
  USING (org_id = mizan.current_org() AND state = 'brouillon');

-- --- dossier_access : visible aux deux parties ; octroyé par le seul
--     propriétaire du dossier (la PME choisit son professionnel).
CREATE POLICY acces_lecture ON mizan.dossier_access FOR SELECT
  USING (mizan.is_platform_admin()
         OR org_id = mizan.current_org()
         OR EXISTS (SELECT 1 FROM mizan.dossier d
                     WHERE d.id = dossier_access.dossier_id
                       AND d.org_id = mizan.current_org()));
CREATE POLICY acces_octroi ON mizan.dossier_access FOR INSERT
  WITH CHECK (EXISTS (SELECT 1 FROM mizan.dossier d
                       WHERE d.id = dossier_access.dossier_id
                         AND d.org_id = mizan.current_org()));
CREATE POLICY acces_revocation ON mizan.dossier_access FOR UPDATE
  USING (EXISTS (SELECT 1 FROM mizan.dossier d
                  WHERE d.id = dossier_access.dossier_id
                    AND d.org_id = mizan.current_org()));

-- --- piece : LE point dur de l'énoncé.
--     Une pièce déposée par une PME n'est visible que de cette PME, et
--     des organisations à qui le dossier a été explicitement partagé.
--     Aucune autre organisation, jamais.
CREATE POLICY piece_lecture ON mizan.piece FOR SELECT
  USING (mizan.can_see_dossier(dossier_id));
CREATE POLICY piece_depot ON mizan.piece FOR INSERT
  WITH CHECK (
    EXISTS (SELECT 1 FROM mizan.dossier d
             WHERE d.id = piece.dossier_id AND d.org_id = mizan.current_org())
    AND mizan.current_role_name() IN ('msme','platform_admin')
  );
CREATE POLICY piece_annotation ON mizan.piece FOR UPDATE
  USING (mizan.can_see_dossier(dossier_id))
  WITH CHECK (mizan.can_see_dossier(dossier_id));
CREATE POLICY piece_retrait ON mizan.piece FOR DELETE
  USING (org_id = mizan.current_org()
         AND EXISTS (SELECT 1 FROM mizan.dossier d
                      WHERE d.id = piece.dossier_id AND d.state = 'brouillon'));

-- --- citations
CREATE POLICY citation_lecture ON mizan.dossier_citation FOR SELECT
  USING (mizan.can_see_dossier(dossier_id));
CREATE POLICY citation_ecriture ON mizan.dossier_citation FOR INSERT
  WITH CHECK (mizan.can_see_dossier(dossier_id));
CREATE POLICY citation_retrait ON mizan.dossier_citation FOR DELETE
  USING (org_id = mizan.current_org());

-- --- E-CMA : visible au dossier ET au cabinet qui conduit la session.
CREATE POLICY ecma_lecture ON mizan.ecma_session FOR SELECT
  USING (mizan.can_see_dossier(dossier_id) OR pro_org_id = mizan.current_org());
CREATE POLICY ecma_ouverture ON mizan.ecma_session FOR INSERT
  WITH CHECK (mizan.can_see_dossier(dossier_id)
              AND mizan.current_role_name() IN ('msme','accredited_pro','court_clerk','platform_admin'));
CREATE POLICY ecma_conduite ON mizan.ecma_session FOR UPDATE
  USING (mizan.can_see_dossier(dossier_id) OR pro_org_id = mizan.current_org())
  WITH CHECK (mizan.can_see_dossier(dossier_id) OR pro_org_id = mizan.current_org());

CREATE POLICY participant_lecture ON mizan.ecma_participant FOR SELECT
  USING (EXISTS (SELECT 1 FROM mizan.ecma_session s
                  WHERE s.id = ecma_participant.session_id
                    AND (mizan.can_see_dossier(s.dossier_id)
                         OR s.pro_org_id = mizan.current_org())));
CREATE POLICY participant_ecriture ON mizan.ecma_participant FOR ALL
  USING (EXISTS (SELECT 1 FROM mizan.ecma_session s
                  WHERE s.id = ecma_participant.session_id
                    AND (mizan.can_see_dossier(s.dossier_id)
                         OR s.pro_org_id = mizan.current_org())))
  WITH CHECK (EXISTS (SELECT 1 FROM mizan.ecma_session s
                  WHERE s.id = ecma_participant.session_id
                    AND (mizan.can_see_dossier(s.dossier_id)
                         OR s.pro_org_id = mizan.current_org())));

CREATE POLICY pv_lecture ON mizan.settlement_minutes FOR SELECT
  USING (mizan.can_see_dossier(dossier_id)
         OR EXISTS (SELECT 1 FROM mizan.ecma_session s
                     WHERE s.id = settlement_minutes.session_id
                       AND s.pro_org_id = mizan.current_org()));
CREATE POLICY pv_redaction ON mizan.settlement_minutes FOR INSERT
  WITH CHECK (mizan.current_role_name() = 'accredited_pro'
              AND EXISTS (SELECT 1 FROM mizan.ecma_session s
                           WHERE s.id = settlement_minutes.session_id
                             AND s.pro_org_id = mizan.current_org()));
CREATE POLICY pv_signature ON mizan.settlement_minutes FOR UPDATE
  USING (EXISTS (SELECT 1 FROM mizan.ecma_session s
                  WHERE s.id = settlement_minutes.session_id
                    AND s.pro_org_id = mizan.current_org()))
  WITH CHECK (EXISTS (SELECT 1 FROM mizan.ecma_session s
                  WHERE s.id = settlement_minutes.session_id
                    AND s.pro_org_id = mizan.current_org()));

-- --- audit_log : chacun lit son journal ; personne ne lit celui d'un
--     autre tenant ; tout contexte valide peut écrire (jamais modifier).
CREATE POLICY audit_lecture ON mizan.audit_log FOR SELECT
  USING (mizan.is_platform_admin()
         OR org_id = mizan.current_org()
         OR (dossier_id IS NOT NULL AND mizan.can_see_dossier(dossier_id)));
CREATE POLICY audit_ecriture ON mizan.audit_log FOR INSERT
  WITH CHECK (mizan.current_user_id() IS NOT NULL);
-- Aucune politique UPDATE ni DELETE : RLS active sans politique =
-- refus total. C'est le quatrième verrou du journal.

-- =====================================================================
-- 13. PRIVILÈGES
--
--  mizan_app n'a AUCUN droit d'UPDATE ou de DELETE sur audit_log : même
--  si un trigger était désactivé, le SGBD refuserait l'ordre.
-- =====================================================================

GRANT USAGE ON SCHEMA mizan TO mizan_app, mizan_owner;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA mizan TO mizan_app;
REVOKE UPDATE, DELETE, TRUNCATE ON mizan.audit_log FROM mizan_app;
REVOKE UPDATE, DELETE, TRUNCATE ON mizan.corpus_article FROM mizan_app;
GRANT SELECT, INSERT ON mizan.audit_log TO mizan_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA mizan TO mizan_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA mizan TO mizan_app;

-- Le rôle applicatif ne doit jamais contourner la RLS.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='mizan_app' AND rolbypassrls) THEN
    RAISE EXCEPTION 'mizan_app possède BYPASSRLS : l''isolation serait illusoire.';
  END IF;
END $$;

COMMIT;

-- =====================================================================
-- FIN DU SCHÉMA
--  Pour prouver l'isolation : psql -v ON_ERROR_STOP=1 -f test_isolation.sql
-- =====================================================================
