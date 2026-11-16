-- Fake SAP — Lucky Cement's custom workflow log tables (services/sap_workflow.py).
--
-- Kept apart from schema.sql and written IF NOT EXISTS because it is applied on
-- EVERY start, not only when the store is first seeded: a file-backed store
-- (SAP_FAKE_DB_PATH) created before these tables existed gains them without
-- losing what was parked in it.
--
-- Column names are ASSUMED (see WF_LOG_FIELDS / ERROR_LOG_FIELDS in
-- sap_workflow.py) until the real ones are read from DD03L. Change both together.

-- Workflow status per parked invoice. Written by the fake when the event is
-- raised (BLK) and by sap_wf_decide.py / decide_workflow() (APP / REJ).
CREATE TABLE IF NOT EXISTS ZMIR7_WF_LOG (
    OBJKEY TEXT,       -- company code(4) + document number(10) + fiscal year(4)
    STATUS TEXT,       -- INIT not started · BLK in process · APP approved · REJ rejected
    POSTED_DOC TEXT    -- document number SAP posted after approval
);

-- Posting log: S = success, E = error.
CREATE TABLE IF NOT EXISTS ZMIR7_ERROR_LOG (
    OBJKEY TEXT,
    TYPE TEXT,
    MESSAGE TEXT
);
