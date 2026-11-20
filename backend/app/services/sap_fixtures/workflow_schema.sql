-- Fake SAP — Lucky Cement's custom workflow log tables (services/sap_workflow.py).
--
-- Kept apart from schema.sql and written IF NOT EXISTS because it is applied on
-- EVERY start, not only when the store is first seeded: a file-backed store
-- (SAP_FAKE_DB_PATH) created before these tables existed gains them without
-- losing what was parked in it.
--
-- ZMIR7_WF_LOG columns are AUP's real ones (RFC_READ_TABLE FIELDS, 2026-11-20;
-- the fake keeps those VIM reads plus a few for show). One row per workflow
-- step (ITEM); the latest row decides. ZMIR7_ERROR_LOG's columns are AUP's
-- too (no OBJKEY: keyed by BELNR + GJAHR). Change with sap_workflow.py.

-- Written by the fake on park (BLK) and by sap_wf_decide.py / decide_workflow().
CREATE TABLE IF NOT EXISTS ZMIR7_WF_LOG (
    OBJKEY TEXT,       -- company code(4) + document number(10) + fiscal year(4); CHAR 40 in SAP
    ITEM TEXT,         -- step counter, NUMC 4
    BELNR TEXT,        -- invoice document (stays the same when SAP posts it)
    GJAHR TEXT,
    BUKRS TEXT,
    WF_STATUS TEXT,    -- INIT (stored INI, CHAR 3) not started, BLK in process, APP approved+posted, REJ rejected
    PERNR TEXT,
    ERDAT TEXT,        -- YYYYMMDD
    ERZET TEXT         -- HHMMSS
);

-- Posting log: S = success, E = error (W / I / A too).
CREATE TABLE IF NOT EXISTS ZMIR7_ERROR_LOG (
    SR_NO INTEGER,
    BELNR TEXT,
    GJAHR TEXT,
    TYPE TEXT,
    ZMESSAGE TEXT,
    CDATE TEXT,        -- YYYYMMDD
    CTIME TEXT,        -- HHMMSS
    Z_FROM TEXT
);
