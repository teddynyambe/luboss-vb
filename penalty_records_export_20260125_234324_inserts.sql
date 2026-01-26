-- SQL INSERT statements for penalty_record
-- Generated: Sun Jan 25 23:43:25 MST 2026
-- 
-- Usage: Review this file, then run on production:
--   psql -d village_bank -f penalty_records_export_20260125_234324_inserts.sql

BEGIN;

-- Disable foreign key checks temporarily (if needed)
SET session_replication_role = 'replica';

-- Insert penalty records
INSERT INTO penalty_record (id, member_id, penalty_type_id, date_issued, status, created_by, approved_by, approved_at, journal_entry_id, notes) VALUES ('956fa570-8e0e-4e7e-b71a-24e2035cb394', 'e449b521-3666-45ac-8dce-ee7e7a78eaaa', 'b97034a3-561a-44eb-ad53-21866cfa0754', '2026-01-22 17:26:03.501207', 'APPROVED'::penaltyrecordstatus, 'bfece7fe-a54d-4c56-867c-58eae93c3372', NULL, NULL, NULL, 'Late Declaration - Declaration made after day 20 of January 2026 (Declaration period ends on day 20)');

-- Re-enable foreign key checks
SET session_replication_role = 'origin';

COMMIT;
