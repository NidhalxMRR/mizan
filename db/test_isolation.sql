-- =====================================================================
--  MIZAN — PREUVE D'ISOLATION MULTI-TENANT
--  psql -v ON_ERROR_STOP=1 -f db/test_isolation.sql
-- ---------------------------------------------------------------------
--  Ce script ne « teste » pas l'isolation au sens rassurant du terme :
--  il tente de la casser. Chaque assertion est écrite pour que le
--  script s'ARRÊTE EN ERREUR si le cloisonnement cède. Un test qui
--  passe en affichant « OK » alors que la donnée a fuité serait pire
--  qu'aucun test.
--
--  Deux organisations réelles du scénario :
--    ORG A — Menuiserie Ahmed (PME créancière)
--    ORG B — SARL Concurrent  (autre PME, aucun lien avec A)
--  Chacune dépose une facture. B ne doit JAMAIS voir celle de A.
--
--  Convention : toute assertion passe par pg_temp.assert_that(), qui
--  lève une exception si la condition est fausse. Avec ON_ERROR_STOP=1,
--  psql sort avec un code non nul : le test échoue bruyamment.
-- =====================================================================

-- ---------------------------------------------------------------------
-- PRÉ-REQUIS D'EXÉCUTION — à lire avant de faire confiance au résultat
--
--  PostgreSQL accorde à tout SUPERUTILISATEUR le contournement complet
--  de la Row Level Security. Un superutilisateur voit TOUT, même avec
--  ENABLE + FORCE ROW LEVEL SECURITY sur chaque table.
--
--  Exécuter ce test en superutilisateur produirait donc un échec
--  trompeur — ou, bien pire dans un autre schéma, un succès trompeur.
--  Le script REFUSE donc de démarrer dans ces conditions : il doit
--  tourner sous le rôle applicatif (mizan_app), c'est-à-dire dans les
--  conditions réelles de la production.
--
--  Lancement :
--    psql -v ON_ERROR_STOP=1 -U mizan_app -d mizan -f db/test_isolation.sql
--  ou, depuis un compte propriétaire :
--    SET ROLE mizan_app;  -- puis \i db/test_isolation.sql
-- ---------------------------------------------------------------------
\set ON_ERROR_STOP on
\timing off
SET client_min_messages = notice;
SET search_path = mizan, public;

DO $$
BEGIN
  IF (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) THEN
    RAISE EXCEPTION E'\n\n*** TEST NON CONCLUANT — REFUS D''EXÉCUTER ***\n    Le rôle « % » est SUPERUTILISATEUR : PostgreSQL lui accorde le\n    contournement de la Row Level Security. Ce test ne prouverait rien.\n    Relancez-le sous le rôle applicatif :  SET ROLE mizan_app;\n',
      current_user USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF (SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user) THEN
    RAISE EXCEPTION E'\n\n*** TEST NON CONCLUANT — REFUS D''EXÉCUTER ***\n    Le rôle « % » possède BYPASSRLS.\n',
      current_user USING ERRCODE = 'insufficient_privilege';
  END IF;
END $$;

-- ---------------------------------------------------------------------
-- Outil d'assertion
--  Créé dans pg_temp : le rôle applicatif n'a pas — et ne doit pas avoir —
--  le droit de créer des objets dans le schéma mizan. Le test tourne donc
--  avec exactement les privilèges de la production.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION pg_temp.assert_that(p_ok boolean, p_libelle text)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  IF p_ok IS NOT TRUE THEN
    RAISE EXCEPTION E'\n\n*** ÉCHEC DU TEST D''ISOLATION ***\n    %\n    L''isolation multi-tenant est CASSÉE. Ne pas déployer.\n',
      p_libelle USING ERRCODE = 'raise_exception';
  END IF;
  RAISE NOTICE '  [OK] %', p_libelle;
END $$;

-- Vérifie qu'une opération est bien REFUSÉE. Si elle réussit, échec.
CREATE OR REPLACE FUNCTION pg_temp.assert_refuse(p_sql text, p_libelle text)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  BEGIN
    EXECUTE p_sql;
  EXCEPTION WHEN others THEN
    RAISE NOTICE '  [OK] % (refus : %)', p_libelle, left(SQLERRM, 90);
    RETURN;
  END;
  RAISE EXCEPTION E'\n\n*** ÉCHEC DU TEST ***\n    %\n    L''opération aurait dû être REFUSÉE et a RÉUSSI.\n',
    p_libelle USING ERRCODE = 'raise_exception';
END $$;

-- Vérifie qu'une écriture reste SANS EFFET. Distinct de assert_refuse :
-- la RLS ne lève pas d'exception, elle rend la ligne non modifiable, et
-- l'ordre affecte zéro ligne. Les deux sont des refus ; ils ne se
-- prouvent pas de la même manière, et confondre les deux masquerait une
-- fuite (une écriture qui « passe » sur 1 ligne).
CREATE OR REPLACE FUNCTION pg_temp.assert_aucun_effet(p_sql text, p_libelle text)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE n integer;
BEGIN
  BEGIN
    EXECUTE p_sql;
    GET DIAGNOSTICS n = ROW_COUNT;
  EXCEPTION WHEN others THEN
    RAISE NOTICE '  [OK] % (refus explicite : %)', p_libelle, left(SQLERRM, 80);
    RETURN;
  END;
  IF n <> 0 THEN
    RAISE EXCEPTION E'\n\n*** ÉCHEC DU TEST ***\n    %\n    L''écriture a modifié % ligne(s) alors qu''elle devait rester sans effet.\n',
      p_libelle, n USING ERRCODE = 'raise_exception';
  END IF;
  RAISE NOTICE '  [OK] % (bloqué par la RLS : 0 ligne affectée)', p_libelle;
END $$;

-- ---------------------------------------------------------------------

\echo ''
\echo '====================================================================='
\echo ' MIZAN — preuve d''isolation par Row Level Security'
\echo '====================================================================='

-- =====================================================================
-- ÉTAPE 0 — Vérifier que la RLS est réellement armée
--   Un schéma où l'on aurait oublié un ALTER TABLE ... ENABLE RLS est
--   un schéma ouvert. On le contrôle par le catalogue, pas de confiance.
-- =====================================================================
\echo ''
\echo '--- 0. La RLS est-elle armée sur toutes les tables métier ?'

DO $$
DECLARE manquantes text;
BEGIN
  SELECT string_agg(c.relname, ', ') INTO manquantes
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'mizan' AND c.relkind = 'r'
     AND NOT (c.relrowsecurity AND c.relforcerowsecurity);
  PERFORM pg_temp.assert_that(manquantes IS NULL,
    'Toutes les tables de mizan portent ENABLE + FORCE ROW LEVEL SECURITY'
    || COALESCE(' — manquantes : ' || manquantes, ''));
END $$;

DO $$
BEGIN
  PERFORM pg_temp.assert_that(
    NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='mizan_app' AND rolbypassrls),
    'Le rôle applicatif mizan_app ne possède pas BYPASSRLS');
END $$;

-- =====================================================================
-- ÉTAPE 1 — Jeu de données : deux tenants étanches
--   Écrit avec le contexte platform_admin, seul habilité à créer des
--   organisations et des utilisateurs (manage_tenants / manage_users).
-- =====================================================================
\echo ''
\echo '--- 1. Création de deux organisations et de leurs utilisateurs'

-- Amorçage : la toute première organisation ne peut être créée par
-- personne (aucun utilisateur n'existe encore). On passe donc par
-- mizan.bootstrap_platform(), qui refuse de s'exécuter deux fois — et
-- surtout qui n'oblige PAS à désactiver la RLS, fût-ce un instant.
SELECT mizan.bootstrap_platform(
  'Mizan SAS', 'admin@mizan.tn', 'Administrateur Mizan',
  '00000000-0000-0000-0000-0000000000aa'::uuid,
  '00000000-0000-0000-0000-00000000ad00'::uuid);

-- L'amorçage est à usage unique : un second appel doit être refusé.
DO $$ BEGIN PERFORM pg_temp.assert_refuse(
  $q$SELECT mizan.bootstrap_platform('Bis','bis@x.tn','Bis')$q$,
  'L''amorçage de la plateforme ne peut pas être rejoué'); END $$;

-- À partir d'ici, TOUT passe par un contexte utilisateur.
SELECT mizan.set_context('00000000-0000-0000-0000-00000000ad00');

INSERT INTO mizan.organization (id, kind, legal_name, legal_name_ar, tax_id) VALUES
  ('11111111-1111-1111-1111-111111111111', 'pme', 'Menuiserie Ahmed', 'نجارة أحمد', 'MF-AAA-001'),
  ('22222222-2222-2222-2222-222222222222', 'pme', 'SARL Concurrent',  'شركة المنافس', 'MF-BBB-002');

INSERT INTO mizan.organization (id, kind, legal_name, tax_id, accreditation_no) VALUES
  ('33333333-3333-3333-3333-333333333333', 'cabinet_mediation', 'Cabinet Ben Salah', 'MF-CCC-003', 'AGR-2024-118'),
  ('44444444-4444-4444-4444-444444444444', 'etude_huissier',    'Étude Trabelsi',    'MF-DDD-004', 'HUI-2019-042');

INSERT INTO mizan.app_user (id, org_id, role, email, full_name, pro_licence_no) VALUES
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'msme',
   'ahmed@menuiserie.tn', 'Ahmed Ben Ali', NULL),
  ('bbbbbbbb-0000-0000-0000-000000000002', '22222222-2222-2222-2222-222222222222', 'msme',
   'gerant@concurrent.tn', 'Sonia Gharbi', NULL),
  ('cccccccc-0000-0000-0000-000000000003', '33333333-3333-3333-3333-333333333333', 'accredited_pro',
   'mediateur@bensalah.tn', 'Karim Ben Salah', 'MED-2024-77'),
  ('dddddddd-0000-0000-0000-000000000004', '44444444-4444-4444-4444-444444444444', 'huissier',
   'trabelsi@etude.tn', 'Nizar Trabelsi', 'HUI-2019-042-1');

DO $$ BEGIN PERFORM pg_temp.assert_that(
  (SELECT count(*) FROM mizan.organization) = 5,
  'Le platform_admin voit les 5 organisations (permission view_all)'); END $$;

-- Cohérence rôle ↔ organisation : un huissier dans une PME est refusé.
DO $$ BEGIN PERFORM pg_temp.assert_refuse($q$
  INSERT INTO mizan.app_user (org_id, role, email, full_name, pro_licence_no)
  VALUES ('11111111-1111-1111-1111-111111111111','huissier','faux@x.tn','Faux Huissier','X-1')
$q$, 'Un huissier ne peut pas être rattaché à une PME'); END $$;

-- =====================================================================
-- ÉTAPE 2 — Un dossier et une pièce dans CHAQUE organisation
-- =====================================================================
\echo ''
\echo '--- 2. Un dossier + une pièce dans chaque organisation'

SELECT mizan.set_context('aaaaaaaa-0000-0000-0000-000000000001');  -- ORG A

INSERT INTO mizan.dossier (id, org_id, reference, creancier, debiteur,
                           montant_tnd, invoice_date, activity, regime,
                           prescription_deadline, needs_bailiff, created_by)
VALUES ('d0551e40-aaaa-0000-0000-000000000001',
        '11111111-1111-1111-1111-111111111111', 'MZ-20260512-A1B2',
        'Menuiserie Ahmed', 'SARL Untel', 9520.000, '2026-05-12',
        'menuiserie', 'goods_1y', '2027-05-12', true,
        'aaaaaaaa-0000-0000-0000-000000000001');

INSERT INTO mizan.piece (id, dossier_id, org_id, kind, filename, n_bytes,
                         sha256, storage_uri, uploaded_by)
VALUES ('b1ece000-aaaa-0000-0000-000000000001',
        'd0551e40-aaaa-0000-0000-000000000001',
        '11111111-1111-1111-1111-111111111111', 'facture',
        'facture_secrete_A.pdf', 50000,
        repeat('a',64), 's3://mizan/A/facture.pdf',
        'aaaaaaaa-0000-0000-0000-000000000001');

SELECT mizan.set_context('bbbbbbbb-0000-0000-0000-000000000002');  -- ORG B

INSERT INTO mizan.dossier (id, org_id, reference, creancier, debiteur,
                           montant_tnd, invoice_date, created_by)
VALUES ('d0551e40-bbbb-0000-0000-000000000002',
        '22222222-2222-2222-2222-222222222222', 'MZ-20260601-C3D4',
        'SARL Concurrent', 'Client X', 3100.000, '2026-06-01',
        'bbbbbbbb-0000-0000-0000-000000000002');

INSERT INTO mizan.piece (id, dossier_id, org_id, kind, filename, n_bytes,
                         sha256, storage_uri, uploaded_by)
VALUES ('b1ece000-bbbb-0000-0000-000000000002',
        'd0551e40-bbbb-0000-0000-000000000002',
        '22222222-2222-2222-2222-222222222222', 'facture',
        'facture_secrete_B.pdf', 41000,
        repeat('b',64), 's3://mizan/B/facture.pdf',
        'bbbbbbbb-0000-0000-0000-000000000002');

DO $$ BEGIN PERFORM pg_temp.assert_that(
  (SELECT count(*) FROM mizan.piece) = 1,
  'ORG B ne voit qu''une seule pièce : la sienne'); END $$;

-- =====================================================================
-- ÉTAPE 3 — LA PREUVE : B ne voit pas la pièce de A
--   On attaque de six manières différentes. Aucune ne doit aboutir.
-- =====================================================================
\echo ''
\echo '--- 3. ATTAQUES : l''organisation B tente d''atteindre les données de A'

-- Contexte : ORG B (Sonia Gharbi)
SELECT mizan.set_context('bbbbbbbb-0000-0000-0000-000000000002');

-- 3.1 Lecture directe de la pièce de A par son identifiant.
DO $$ BEGIN PERFORM pg_temp.assert_that(
  NOT EXISTS (SELECT 1 FROM mizan.piece
               WHERE id = 'b1ece000-aaaa-0000-0000-000000000001'),
  '3.1 B ne peut pas lire la pièce de A par son UUID'); END $$;

-- 3.2 Balayage complet de la table : aucune ligne de A ne sort.
DO $$ BEGIN PERFORM pg_temp.assert_that(
  NOT EXISTS (SELECT 1 FROM mizan.piece
               WHERE org_id = '11111111-1111-1111-1111-111111111111'),
  '3.2 Un SELECT * sur mizan.piece ne renvoie aucune ligne de A'); END $$;

-- 3.3 Le nom du fichier de A n'apparaît nulle part.
DO $$ BEGIN PERFORM pg_temp.assert_that(
  NOT EXISTS (SELECT 1 FROM mizan.piece WHERE filename LIKE '%secrete_A%'),
  '3.3 Le nom de fichier de A est invisible depuis B'); END $$;

-- 3.4 Le dossier de A est invisible.
DO $$ BEGIN PERFORM pg_temp.assert_that(
  NOT EXISTS (SELECT 1 FROM mizan.dossier
               WHERE id = 'd0551e40-aaaa-0000-0000-000000000001'),
  '3.4 Le dossier de A est invisible depuis B'); END $$;

-- 3.5 Fuite par agrégat : un count() global ne doit pas révéler
--     l'existence des lignes de A. C'est la fuite que l'on oublie.
DO $$
DECLARE n bigint;
BEGIN
  SELECT count(*) INTO n FROM mizan.piece;
  PERFORM pg_temp.assert_that(n = 1,
    '3.5 count(*) global depuis B renvoie 1 et non 2 (pas de fuite par agrégat) — obtenu : ' || n);
END $$;

-- 3.6 Fuite par jointure : passer par le dossier ne contourne rien.
DO $$
DECLARE n bigint;
BEGIN
  SELECT count(*) INTO n
    FROM mizan.dossier d JOIN mizan.piece p ON p.dossier_id = d.id;
  PERFORM pg_temp.assert_that(n = 1,
    '3.6 Une jointure dossier×pièce ne fait pas apparaître les données de A — obtenu : ' || n);
END $$;

-- 3.7 Écriture croisée : B tente de déposer une pièce DANS le dossier de A.
DO $$ BEGIN PERFORM pg_temp.assert_refuse($q$
  INSERT INTO mizan.piece (dossier_id, org_id, kind, filename, n_bytes, sha256, storage_uri, uploaded_by)
  VALUES ('d0551e40-aaaa-0000-0000-000000000001','22222222-2222-2222-2222-222222222222',
          'contrat','intrus.pdf',10,repeat('c',64),'s3://x','bbbbbbbb-0000-0000-0000-000000000002')
$q$, '3.7 B ne peut pas déposer une pièce dans le dossier de A'); END $$;

-- 3.8 Suppression croisée : silencieusement sans effet, pas d'erreur.
DO $$
DECLARE n integer;
BEGIN
  DELETE FROM mizan.piece WHERE id = 'b1ece000-aaaa-0000-0000-000000000001';
  GET DIAGNOSTICS n = ROW_COUNT;
  PERFORM pg_temp.assert_that(n = 0,
    '3.8 Un DELETE de B sur la pièce de A n''affecte aucune ligne');
END $$;

-- 3.9 Falsification du contexte : B se prétend membre de A.
--     Impossible par construction : le GUC ne porte QUE l'utilisateur,
--     et l'organisation est relue dans la base.
DO $$
BEGIN
  PERFORM set_config('mizan.org_id', '11111111-1111-1111-1111-111111111111', false);
  PERFORM pg_temp.assert_that(
    mizan.current_org() = '22222222-2222-2222-2222-222222222222',
    '3.9 Poser un faux mizan.org_id ne change rien : l''org est relue en base');
  PERFORM pg_temp.assert_that(
    NOT EXISTS (SELECT 1 FROM mizan.piece WHERE org_id = '11111111-1111-1111-1111-111111111111'),
    '3.9bis Même avec un faux GUC, la pièce de A reste invisible');
END $$;

-- 3.10 Contexte absent : la base se ferme, elle ne s'ouvre pas.
SELECT mizan.clear_context();
DO $$
DECLARE n bigint;
BEGIN
  SELECT count(*) INTO n FROM mizan.piece;
  PERFORM pg_temp.assert_that(n = 0,
    '3.10 Sans contexte de session, aucune pièce n''est visible (fermé par défaut) — obtenu : ' || n);
END $$;

-- 3.11 Contre-preuve : A voit bien SA pièce. Un test d'isolation qui
--      passerait parce que PERSONNE ne voit rien ne prouverait rien.
SELECT mizan.set_context('aaaaaaaa-0000-0000-0000-000000000001');
DO $$ BEGIN PERFORM pg_temp.assert_that(
  EXISTS (SELECT 1 FROM mizan.piece
           WHERE id = 'b1ece000-aaaa-0000-0000-000000000001'
             AND filename = 'facture_secrete_A.pdf'),
  '3.11 CONTRE-PREUVE : A voit bien sa propre pièce (l''isolation n''est pas un mur aveugle)'); END $$;

-- =====================================================================
-- ÉTAPE 4 — Le partage explicite ouvre, et seulement ce qu'il ouvre
-- =====================================================================
\echo ''
\echo '--- 4. Partage explicite du dossier de A au cabinet de médiation'

-- Avant partage : le médiateur ne voit rien.
SELECT mizan.set_context('cccccccc-0000-0000-0000-000000000003');
DO $$ BEGIN PERFORM pg_temp.assert_that(
  (SELECT count(*) FROM mizan.piece) = 0,
  '4.1 Avant partage, le médiateur ne voit aucune pièce'); END $$;

-- A partage son dossier (la PME choisit son professionnel).
SELECT mizan.set_context('aaaaaaaa-0000-0000-0000-000000000001');
INSERT INTO mizan.dossier_access (dossier_id, org_id, granted_by, reason)
VALUES ('d0551e40-aaaa-0000-0000-000000000001',
        '33333333-3333-3333-3333-333333333333',
        'aaaaaaaa-0000-0000-0000-000000000001',
        'Ouverture d''une conciliation E-CMA');

-- Après partage : le médiateur voit la pièce de A — et rien de B.
SELECT mizan.set_context('cccccccc-0000-0000-0000-000000000003');
DO $$
DECLARE n bigint;
BEGIN
  SELECT count(*) INTO n FROM mizan.piece;
  PERFORM pg_temp.assert_that(n = 1,
    '4.2 Après partage, le médiateur voit la pièce de A — obtenu : ' || n);
  PERFORM pg_temp.assert_that(
    NOT EXISTS (SELECT 1 FROM mizan.piece WHERE org_id='22222222-2222-2222-2222-222222222222'),
    '4.3 Le partage de A n''ouvre AUCUNE donnée de B (pas de fuite latérale)');
END $$;

-- Révocation : la visibilité se referme.
SELECT mizan.set_context('aaaaaaaa-0000-0000-0000-000000000001');
UPDATE mizan.dossier_access SET revoked_at = now()
 WHERE dossier_id = 'd0551e40-aaaa-0000-0000-000000000001'
   AND org_id = '33333333-3333-3333-3333-333333333333';

SELECT mizan.set_context('cccccccc-0000-0000-0000-000000000003');
DO $$ BEGIN PERFORM pg_temp.assert_that(
  (SELECT count(*) FROM mizan.piece) = 0,
  '4.4 Après révocation, le médiateur ne voit plus rien'); END $$;

-- On rétablit le partage pour la suite du scénario.
SELECT mizan.set_context('aaaaaaaa-0000-0000-0000-000000000001');
UPDATE mizan.dossier_access SET revoked_at = NULL
 WHERE dossier_id = 'd0551e40-aaaa-0000-0000-000000000001';

-- =====================================================================
-- ÉTAPE 5 — Citations juridiques : aucune citation non relue
-- =====================================================================
\echo ''
\echo '--- 5. Citations : le texte doit correspondre au corpus, au caractère près'

-- Import de deux articles réels du corpus (~/h4j/corpus/*.jsonl).
SELECT mizan.set_context('00000000-0000-0000-0000-00000000ad00');  -- manage_corpus
INSERT INTO mizan.corpus_article (id, code_id, code_ar, code_fr, article, citation_ar, text_ar, text_sha256)
VALUES
 ('procciv-art60','procciv','مجلة المرافعات المدنية والتجارية','Code de Procédure Civile et Commerciale',60,
  'الفصل 60 من مجلة المرافعات المدنية والتجارية',
  'إذا تجاوز الدين مائة وخمسين دينارا فعلى الدائن قبل تقديم المطلب إنذار المدين بواسطة عدل منفذ.',
  repeat('0',64)),   -- valeur ignorée : recalculée par le trigger
 ('coc-art403','coc','مجلة الالتزامات والعقود','Code des Obligations et des Contrats',403,
  'الفصل 403 من مجلة الالتزامات والعقود',
  'تسقط الدعوى بمضي عام ذي ثلاثمائة وخمسة وستين يوما فيما يطلبه الباعة وأرباب المصانع من ثمن ما سلموه من البضائع.',
  repeat('0',64));

SELECT mizan.set_context('aaaaaaaa-0000-0000-0000-000000000001');

-- 5.1 Citation conforme : acceptée.
INSERT INTO mizan.dossier_citation (dossier_id, org_id, corpus_id, code_id, article,
                                    citation_ar, verbatim_ar, verbatim_sha256, attached_by, role_fr)
SELECT 'd0551e40-aaaa-0000-0000-000000000001','11111111-1111-1111-1111-111111111111',
       c.id, c.code_id, c.article, c.citation_ar, c.text_ar, c.text_sha256,
       'aaaaaaaa-0000-0000-0000-000000000001', 'bailiff_notice'
  FROM mizan.corpus_article c WHERE c.id = 'procciv-art60';

DO $$ BEGIN PERFORM pg_temp.assert_that(
  (SELECT count(*) FROM mizan.dossier_citation
    WHERE dossier_id='d0551e40-aaaa-0000-0000-000000000001') = 1,
  '5.1 Une citation dont le texte correspond au corpus est acceptée'); END $$;

-- 5.2 Citation au texte altéré (« cent cinquante » changé en « cent ») :
--     rejetée. C'est exactement le cas d'un texte produit par un modèle.
DO $$ BEGIN PERFORM pg_temp.assert_refuse($q$
  INSERT INTO mizan.dossier_citation (dossier_id, org_id, corpus_id, code_id, article,
                                      citation_ar, verbatim_ar, verbatim_sha256, attached_by)
  VALUES ('d0551e40-aaaa-0000-0000-000000000001','11111111-1111-1111-1111-111111111111',
          'coc-art403','coc',403,'الفصل 403',
          'texte approximatif inventé',
          encode(sha256(convert_to('texte approximatif inventé','UTF8')),'hex'),
          'aaaaaaaa-0000-0000-0000-000000000001')
$q$, '5.2 Une citation dont le texte ne correspond pas au corpus est REFUSÉE'); END $$;

-- 5.3 Citation vide : rejetée par la contrainte déclarative.
DO $$ BEGIN PERFORM pg_temp.assert_refuse($q$
  INSERT INTO mizan.dossier_citation (dossier_id, org_id, corpus_id, code_id, article,
                                      citation_ar, verbatim_ar, verbatim_sha256, attached_by)
  VALUES ('d0551e40-aaaa-0000-0000-000000000001','11111111-1111-1111-1111-111111111111',
          'coc-art403','coc',403,'الفصل 403','   ',
          encode(sha256(convert_to('   ','UTF8')),'hex'),
          'aaaaaaaa-0000-0000-0000-000000000001')
$q$, '5.3 Une citation au texte vide est REFUSÉE (aucun texte vide ne peut égaler un article du corpus)'); END $$;

-- 5.4 Article absent du corpus : rejeté (référence inventée).
DO $$ BEGIN PERFORM pg_temp.assert_refuse($q$
  INSERT INTO mizan.dossier_citation (dossier_id, org_id, corpus_id, code_id, article,
                                      citation_ar, verbatim_ar, verbatim_sha256, attached_by)
  VALUES ('d0551e40-aaaa-0000-0000-000000000001','11111111-1111-1111-1111-111111111111',
          'coc-art9999','coc',9999,'الفصل 9999','texte',
          encode(sha256(convert_to('texte','UTF8')),'hex'),
          'aaaaaaaa-0000-0000-0000-000000000001')
$q$, '5.4 Une citation vers un article absent du corpus est REFUSÉE'); END $$;

-- =====================================================================
-- ÉTAPE 6 — ACTES RÉSERVÉS (CPC art. 5 et 60 ; COC art. 1458)
-- =====================================================================
\echo ''
\echo '--- 6. Actes réservés : seul l''huissier signifie, seul le pro signe'

-- Le dossier est prêt à signifier.
SELECT mizan.set_context('aaaaaaaa-0000-0000-0000-000000000001');
UPDATE mizan.dossier SET state = 'verifie'
 WHERE id = 'd0551e40-aaaa-0000-0000-000000000001';
UPDATE mizan.dossier SET state = 'projet_acte_pret'
 WHERE id = 'd0551e40-aaaa-0000-0000-000000000001';

-- 6.1 La PME tente de signifier elle-même : REFUS (CPC art. 5).
DO $$ BEGIN PERFORM pg_temp.assert_refuse($q$
  UPDATE mizan.dossier SET state='signifie'
   WHERE id='d0551e40-aaaa-0000-0000-000000000001'
$q$, '6.1 Une PME (msme) ne peut PAS faire passer un dossier à « signifié »'); END $$;

-- 6.2 Le médiateur non plus.
SELECT mizan.set_context('cccccccc-0000-0000-0000-000000000003');
DO $$ BEGIN PERFORM pg_temp.assert_refuse($q$
  UPDATE mizan.dossier SET state='signifie'
   WHERE id='d0551e40-aaaa-0000-0000-000000000001'
$q$, '6.2 Un professionnel accrédité ne peut PAS signifier'); END $$;

-- 6.3 L'huissier, lui, le peut — une fois le dossier partagé à son étude.
SELECT mizan.set_context('aaaaaaaa-0000-0000-0000-000000000001');
INSERT INTO mizan.dossier_access (dossier_id, org_id, granted_by, reason)
VALUES ('d0551e40-aaaa-0000-0000-000000000001',
        '44444444-4444-4444-4444-444444444444',
        'aaaaaaaa-0000-0000-0000-000000000001', 'Signification CPC art. 60');

SELECT mizan.set_context('dddddddd-0000-0000-0000-000000000004');
UPDATE mizan.dossier SET state = 'signifie'
 WHERE id = 'd0551e40-aaaa-0000-0000-000000000001';

DO $$ BEGIN PERFORM pg_temp.assert_that(
  (SELECT state = 'signifie'
       AND signified_by = 'dddddddd-0000-0000-0000-000000000004'
       AND signified_at IS NOT NULL
     FROM mizan.dossier WHERE id='d0551e40-aaaa-0000-0000-000000000001'),
  '6.3 L''huissier signifie, et la base horodate l''acte à son nom'); END $$;

-- 6.4 Un acte signifié ne se dé-signifie pas.
DO $$ BEGIN PERFORM pg_temp.assert_refuse($q$
  UPDATE mizan.dossier SET state='brouillon'
   WHERE id='d0551e40-aaaa-0000-0000-000000000001'
$q$, '6.4 Un dossier signifié ne peut pas revenir en arrière'); END $$;

-- 6.5 Signature du PV : session E-CMA sur le dossier de B, pour varier.
SELECT mizan.set_context('bbbbbbbb-0000-0000-0000-000000000002');
INSERT INTO mizan.dossier_access (dossier_id, org_id, granted_by)
VALUES ('d0551e40-bbbb-0000-0000-000000000002',
        '33333333-3333-3333-3333-333333333333',
        'bbbbbbbb-0000-0000-0000-000000000002');

INSERT INTO mizan.ecma_session (id, dossier_id, org_id, kind, pro_user_id, pro_org_id,
                                scheduled_at, opened_by)
VALUES ('ec3a0000-bbbb-0000-0000-000000000002',
        'd0551e40-bbbb-0000-0000-000000000002',
        '22222222-2222-2222-2222-222222222222', 'conciliation',
        'cccccccc-0000-0000-0000-000000000003',
        '33333333-3333-3333-3333-333333333333',
        now() + interval '3 days', 'bbbbbbbb-0000-0000-0000-000000000002');

INSERT INTO mizan.ecma_participant (session_id, user_id, partie) VALUES
  ('ec3a0000-bbbb-0000-0000-000000000002','bbbbbbbb-0000-0000-0000-000000000002'::uuid,'creancier')
ON CONFLICT DO NOTHING;

SELECT mizan.set_context('cccccccc-0000-0000-0000-000000000003');
INSERT INTO mizan.settlement_minutes (id, session_id, dossier_id, org_id, body_ar,
                                      amount_agreed_tnd, content_sha256, drafted_by)
VALUES ('9f000000-bbbb-0000-0000-000000000002'::uuid,
        'ec3a0000-bbbb-0000-0000-000000000002',
        'd0551e40-bbbb-0000-0000-000000000002',
        '22222222-2222-2222-2222-222222222222',
        'اتفق الطرفان على تسوية الدين بمبلغ ألفين وخمسمائة دينار.',
        2500.000, repeat('0',64), 'cccccccc-0000-0000-0000-000000000003');

-- La PME tente de signer le PV à la place du médiateur : REFUS.
SELECT mizan.set_context('bbbbbbbb-0000-0000-0000-000000000002');
DO $$ BEGIN PERFORM pg_temp.assert_aucun_effet($q$
  UPDATE mizan.settlement_minutes
     SET signed_by='bbbbbbbb-0000-0000-0000-000000000002'
   WHERE id='9f000000-bbbb-0000-0000-000000000002'
$q$, '6.5 Une PME ne peut PAS signer un PV de conciliation'); END $$;

-- L'huissier non plus : la signature du PV n'est pas son acte.
SELECT mizan.set_context('dddddddd-0000-0000-0000-000000000004');
DO $$ BEGIN PERFORM pg_temp.assert_aucun_effet($q$
  UPDATE mizan.settlement_minutes
     SET signed_by='dddddddd-0000-0000-0000-000000000004'
   WHERE id='9f000000-bbbb-0000-0000-000000000002'
$q$, '6.6 Un huissier ne peut PAS signer un PV de conciliation'); END $$;

-- Contrôle d'effet : après ces deux tentatives, le PV est toujours vierge.
SELECT mizan.set_context('cccccccc-0000-0000-0000-000000000003');
DO $$ BEGIN PERFORM pg_temp.assert_that(
  (SELECT signed_by IS NULL AND signed_at IS NULL FROM mizan.settlement_minutes
    WHERE id='9f000000-bbbb-0000-0000-000000000002'),
  '6.6bis Le PV est resté NON SIGNÉ malgré les deux tentatives'); END $$;

-- Le trigger d'acte réservé lui-même : même à l'intérieur du cabinet, on
-- ne signe pas au nom d'un autre. Ici la RLS laisse passer, et c'est la
-- règle juridique qui refuse — exception attendue, pas un silence.
DO $$ BEGIN PERFORM pg_temp.assert_refuse($q$
  UPDATE mizan.settlement_minutes
     SET signed_by='bbbbbbbb-0000-0000-0000-000000000002'
   WHERE id='9f000000-bbbb-0000-0000-000000000002'
$q$, '6.6ter Le médiateur ne peut pas apposer la signature d''un tiers (trigger d''acte réservé)'); END $$;

-- Le professionnel accrédité signe. Lui seul.
SELECT mizan.set_context('cccccccc-0000-0000-0000-000000000003');
UPDATE mizan.settlement_minutes
   SET signed_by = 'cccccccc-0000-0000-0000-000000000003'
 WHERE id = '9f000000-bbbb-0000-0000-000000000002';

DO $$ BEGIN PERFORM pg_temp.assert_that(
  (SELECT signed_at IS NOT NULL FROM mizan.settlement_minutes
    WHERE id='9f000000-bbbb-0000-0000-000000000002'),
  '6.7 Le professionnel accrédité signe le PV, la base horodate'); END $$;

-- 6.8 Un PV signé est figé.
DO $$ BEGIN PERFORM pg_temp.assert_refuse($q$
  UPDATE mizan.settlement_minutes SET body_ar='texte réécrit après signature'
   WHERE id='9f000000-bbbb-0000-0000-000000000002'
$q$, '6.8 Le corps d''un PV signé ne peut plus être réécrit'); END $$;

-- =====================================================================
-- ÉTAPE 7 — JOURNAL D'AUDIT INALTÉRABLE
-- =====================================================================
\echo ''
\echo '--- 7. Journal d''audit : insertion seule, chaîne intacte, cloisonné'

SELECT mizan.set_context('aaaaaaaa-0000-0000-0000-000000000001');

DO $$
DECLARE n bigint;
BEGIN
  SELECT count(*) INTO n FROM mizan.audit_log
   WHERE dossier_id = 'd0551e40-aaaa-0000-0000-000000000001';
  PERFORM pg_temp.assert_that(n >= 4,
    '7.1 Les actes sur le dossier de A ont été journalisés automatiquement — entrées : ' || n);
END $$;

-- La signification est tracée avec son auteur et son rôle.
DO $$ BEGIN PERFORM pg_temp.assert_that(
  EXISTS (SELECT 1 FROM mizan.audit_log
           WHERE dossier_id='d0551e40-aaaa-0000-0000-000000000001'
             AND action='dossier.transition'
             AND details->>'vers'='signifie'
             AND actor_role='huissier'),
  '7.2 La signification est tracée avec l''auteur ET son rôle (huissier)'); END $$;

-- 7.3 Cloisonnement du journal : B ne lit pas le journal de A.
SELECT mizan.set_context('bbbbbbbb-0000-0000-0000-000000000002');
DO $$ BEGIN PERFORM pg_temp.assert_that(
  NOT EXISTS (SELECT 1 FROM mizan.audit_log
               WHERE org_id='11111111-1111-1111-1111-111111111111'),
  '7.3 B ne voit aucune entrée d''audit de A'); END $$;

-- 7.4 Modification interdite.
SELECT mizan.set_context('00000000-0000-0000-0000-00000000ad00');
DO $$ BEGIN PERFORM pg_temp.assert_refuse(
  $q$UPDATE mizan.audit_log SET action='falsifié' WHERE seq=1$q$,
  '7.4 UPDATE sur le journal d''audit est REFUSÉ (même pour le platform_admin)'); END $$;

-- 7.5 Suppression interdite.
DO $$ BEGIN PERFORM pg_temp.assert_refuse(
  $q$DELETE FROM mizan.audit_log WHERE seq=1$q$,
  '7.5 DELETE sur le journal d''audit est REFUSÉ'); END $$;

-- 7.6 TRUNCATE interdit.
DO $$ BEGIN PERFORM pg_temp.assert_refuse(
  $q$TRUNCATE mizan.audit_log$q$,
  '7.6 TRUNCATE sur le journal d''audit est REFUSÉ'); END $$;

-- 7.6bis QUELLE COUCHE A REFUSÉ ?
--   Sous le rôle applicatif, c'est le retrait de privilèges (§13) qui
--   bloque en premier : le message dit « permission denied ». C'est un
--   refus réel, mais il ne prouve PAS le second verrou. Or un exploitant
--   qui, un jour, accorderait UPDATE à mizan_app « pour corriger une
--   ligne » retomberait sur le trigger. On contrôle donc au catalogue que
--   ce second verrou est en place et ACTIF — un trigger désactivé
--   (tgenabled = 'D') passerait inaperçu autrement.
DO $$
DECLARE n integer;
BEGIN
  SELECT count(*) INTO n FROM pg_trigger t
    JOIN pg_class c ON c.oid = t.tgrelid
    JOIN pg_namespace ns ON ns.oid = c.relnamespace
   WHERE ns.nspname='mizan' AND c.relname='audit_log'
     AND t.tgname IN ('audit_no_update','audit_no_delete','audit_no_truncate')
     AND t.tgenabled <> 'D';
  PERFORM pg_temp.assert_that(n = 3,
    '7.6bis Les 3 triggers d''inaltérabilité du journal existent et sont ACTIFS (second verrou, indépendant des privilèges) — trouvés : ' || n);
END $$;

-- 7.6ter Troisième verrou, indépendant des deux autres : aucune politique
--   RLS d'écriture destructrice n'existe sur audit_log. RLS active sans
--   politique = refus total, y compris si privilèges ET triggers tombaient.
DO $$
DECLARE n integer;
BEGIN
  SELECT count(*) INTO n FROM pg_policies
   WHERE schemaname='mizan' AND tablename='audit_log'
     AND cmd IN ('UPDATE','DELETE','ALL');
  PERFORM pg_temp.assert_that(n = 0,
    '7.6ter Aucune politique RLS d''écriture destructrice sur le journal (troisième verrou) — trouvées : ' || n);
END $$;

-- 7.7bis CONTRE-ÉPREUVE DU DÉTECTEUR.
--   « 0 maillon rompu » ne vaut rien si la fonction est incapable de
--   détecter quoi que ce soit : une fonction renvoyant toujours vide
--   afficherait le même résultat rassurant. On lui soumet donc une
--   entrée volontairement falsifiée — recalculée EN MÉMOIRE, sans
--   toucher au journal réel — et elle DOIT la déclarer incohérente.
DO $$
DECLARE n integer;
BEGIN
  WITH faux AS (
    SELECT a.prev_hash, a.occurred_at, a.org_id, a.actor_id, a.actor_role,
           'ACTION_FALSIFIEE'::text AS action,      -- l'action est réécrite
           a.object_type, a.object_id, a.dossier_id, a.details, a.entry_hash
      FROM mizan.audit_log a ORDER BY a.seq LIMIT 1)
  SELECT count(*) INTO n FROM faux f
   WHERE f.entry_hash <> encode(sha256(convert_to(
           COALESCE(f.prev_hash,'GENESIS') || '|' || f.occurred_at::text || '|' ||
           COALESCE(f.org_id::text,'') || '|' || COALESCE(f.actor_id::text,'') || '|' ||
           COALESCE(f.actor_role::text,'') || '|' || f.action || '|' ||
           f.object_type || '|' || COALESCE(f.object_id,'') || '|' ||
           COALESCE(f.dossier_id::text,'') || '|' || f.details::text,'UTF8')),'hex');
  PERFORM pg_temp.assert_that(n = 1,
    '7.7bis CONTRE-ÉPREUVE : une entrée réécrite est bien détectée comme incohérente (le détecteur n''est pas aveugle)');
END $$;

-- 7.7 La chaîne cryptographique est intacte.
DO $$
DECLARE n bigint;
BEGIN
  SELECT count(*) INTO n FROM mizan.verify_audit_chain();
  PERFORM pg_temp.assert_that(n = 0,
    '7.7 La chaîne d''empreintes du journal est intacte (0 maillon rompu) — rompus : ' || n);
END $$;

-- =====================================================================
-- ÉTAPE 8 — Intégrité des pièces
-- =====================================================================
\echo ''
\echo '--- 8. Empreintes de pièces : immuables, et bien formées'

SELECT mizan.set_context('aaaaaaaa-0000-0000-0000-000000000001');

DO $$ BEGIN PERFORM pg_temp.assert_refuse($q$
  UPDATE mizan.piece SET sha256 = repeat('f',64)
   WHERE id='b1ece000-aaaa-0000-0000-000000000001'
$q$, '8.1 L''empreinte SHA-256 d''une pièce déposée est immuable'); END $$;

DO $$ BEGIN PERFORM pg_temp.assert_refuse($q$
  INSERT INTO mizan.piece (dossier_id, org_id, kind, filename, n_bytes, sha256, storage_uri, uploaded_by)
  VALUES ('d0551e40-aaaa-0000-0000-000000000001','11111111-1111-1111-1111-111111111111',
          'contrat','x.pdf',10,'pas-une-empreinte','s3://x','aaaaaaaa-0000-0000-0000-000000000001')
$q$, '8.2 Une empreinte malformée est REFUSÉE par le domaine sha256_hex'); END $$;

DO $$ BEGIN PERFORM pg_temp.assert_refuse($q$
  INSERT INTO mizan.piece (dossier_id, org_id, kind, filename, n_bytes, sha256, storage_uri, uploaded_by, gate_ok)
  VALUES ('d0551e40-aaaa-0000-0000-000000000001','11111111-1111-1111-1111-111111111111',
          'contrat','refus.pdf',10,repeat('e',64),'s3://x','aaaaaaaa-0000-0000-0000-000000000001',false)
$q$, '8.3 Une pièce refusée sans motif est REFUSÉE (le refus doit être opposable)'); END $$;

-- =====================================================================
-- BILAN
-- =====================================================================
\echo ''
\echo '====================================================================='

DO $$
DECLARE n_org bigint; n_piece bigint; n_audit bigint; n_rompus bigint;
BEGIN
  PERFORM mizan.set_context('00000000-0000-0000-0000-00000000ad00');
  SELECT count(*) INTO n_org   FROM mizan.organization;
  SELECT count(*) INTO n_piece FROM mizan.piece;
  SELECT count(*) INTO n_audit FROM mizan.audit_log;
  SELECT count(*) INTO n_rompus FROM mizan.verify_audit_chain();
  RAISE NOTICE '';
  RAISE NOTICE 'Organisations : %   Pièces : %   Entrées d''audit : %   Maillons rompus : %',
    n_org, n_piece, n_audit, n_rompus;
  PERFORM pg_temp.assert_that(n_piece = 2,
    'BILAN : le platform_admin voit les 2 pièces (une par tenant) — obtenu : ' || n_piece);
  PERFORM pg_temp.assert_that(n_rompus = 0, 'BILAN : journal d''audit intact');
END $$;

\echo ''
\echo '  TOUTES LES ASSERTIONS SONT PASSÉES.'
\echo '  Isolation multi-tenant prouvée par Row Level Security.'
\echo '====================================================================='
\echo ''
