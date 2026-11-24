-- Fake SAP — table definitions.
--
-- Tables and columns carry SAP's real names, because RFC_READ_TABLE's WHERE
-- clause is built by the application from those names and handed straight to
-- SQLite (see sap_connector_fake.py). Only the columns the app actually reads
-- are declared; the full SAP tables have hundreds.
--
-- EVERY column is TEXT on purpose. RFC_READ_TABLE returns all values as strings
-- and _parse_delimited_rows() strips them as strings; numeric affinity would
-- silently turn '0002000101' into 2000101 and break every key comparison.

-- ── Purchasing ──────────────────────────────────────────────────────────────

-- Einkaufsbeleg Kopf — PO header
CREATE TABLE EKKO (
    EBELN TEXT,   -- PO number (10, zero-padded)
    BSTYP TEXT,   -- document category: F = purchase order
    BSART TEXT,   -- document type: NB standard, FO framework
    BUKRS TEXT,   -- company code
    LIFNR TEXT,   -- vendor (10, zero-padded)
    BEDAT TEXT,   -- PO date, YYYYMMDD
    WAERS TEXT,   -- currency
    RLWRT TEXT,   -- total value
    EKGRP TEXT,   -- purchasing group
    ZTERM TEXT,   -- payment terms
    LOEKZ TEXT,   -- deletion indicator ('' = live)
    KNUMV TEXT    -- conditions record key
);

-- Einkaufsbeleg Position — PO line items
CREATE TABLE EKPO (
    EBELN TEXT,
    EBELP TEXT,   -- item number (5, zero-padded)
    TXZ01 TEXT,   -- short text
    MATNR TEXT,   -- material number
    MENGE TEXT,   -- quantity
    MEINS TEXT,   -- order unit (OUn)
    BPRME TEXT,   -- order price unit (OPU)
    NETPR TEXT,   -- net price
    NETWR TEXT,   -- net value
    WERKS TEXT,   -- plant
    MATKL TEXT,   -- material group
    PSTYP TEXT,   -- item category: 0 = standard (goods), 9 = service
    WEBRE TEXT,   -- GR-based invoice verification flag
    LOEKZ TEXT
);

-- Einkaufsbeleg Bestellentwicklung — PO history (GRs, invoices)
CREATE TABLE EKBE (
    EBELN TEXT,
    EBELP TEXT,
    GJAHR TEXT,   -- fiscal year
    BELNR TEXT,   -- material / invoice document
    BUZEI TEXT,   -- item in that document
    VGABE TEXT,   -- transaction type: 1 = goods receipt, 2 = invoice receipt
    BWART TEXT,   -- movement type: 101 receipt, 105 release
    BUDAT TEXT,   -- posting date
    MENGE TEXT,
    DMBTR TEXT,   -- amount in local currency
    WERKS TEXT,
    MATNR TEXT,
    SHKZG TEXT,   -- debit/credit: S = debit, H = credit
    LFBNR TEXT,   -- reference document (the GR a service line came from)
    LFGJA TEXT,   -- reference document year (the GR an invoice / reversal points at)
    LFPOS TEXT    -- reference document item
);

-- Einkaufsbeleg Bezugsnebenkosten — delivery costs
CREATE TABLE EKBZ (
    EBELN TEXT,
    EBELP TEXT,
    VGABE TEXT,
    SHKZG TEXT,   -- S = accrual/invoice, H = reversal/credit
    GJAHR TEXT,
    BELNR TEXT,   -- the goods receipt (or invoice) that accrued (consumed) it
    BUZEI TEXT,
    LIFNR TEXT,   -- the freight vendor
    KSCHL TEXT,   -- condition type (FRA1 freight, ZOLL customs, ...)
    MENGE TEXT,
    DMBTR TEXT,
    WAERS TEXT
);

-- ── Vendors ─────────────────────────────────────────────────────────────────

-- Lieferantenstamm allgemein — vendor master, general
-- Vendor withholding tax per company code (BP) — observation G.
CREATE TABLE LFBW (
    LIFNR TEXT,
    BUKRS TEXT,
    WITHT TEXT,       -- WHT type
    WT_WITHCD TEXT,   -- WHT code
    WT_SUBJCT TEXT    -- 'X' = vendor is subject to this WHT type
);

-- WHT codes per country: rate and portion of the base.
CREATE TABLE T059Z (
    LAND1 TEXT,
    WITHT TEXT,
    WT_WITHCD TEXT,
    QSATZ TEXT,       -- rate %
    QPROZ TEXT        -- % of the base subject to WHT
);

CREATE TABLE LFA1 (
    LIFNR TEXT,
    NAME1 TEXT,
    MCOD1 TEXT,   -- search term (upper case of NAME1)
    ORT01 TEXT,   -- city
    STCD1 TEXT,   -- tax number 1 — the NTN on this instance
    STCD2 TEXT,
    STCD3 TEXT,
    LOEVM TEXT,   -- flagged for deletion
    SPERR TEXT    -- posting block
);

-- Lieferantenstamm Buchungskreis — vendor master, per company code
CREATE TABLE LFB1 (
    LIFNR TEXT,
    BUKRS TEXT,
    AKONT TEXT,   -- reconciliation account
    ZTERM TEXT,
    LOEVM TEXT,
    SPERR TEXT
);

-- ── Invoices ────────────────────────────────────────────────────────────────

-- Rechnungsbeleg Kopf — incoming invoice header.
-- The fake WRITES this table: parking inserts a row so a later unpark can find
-- the document (sap_invoice_post.py reads RBSTAT to decide whether it exists).
CREATE TABLE RBKP (
    BELNR TEXT,   -- invoice document number
    GJAHR TEXT,
    RBSTAT TEXT,  -- A = parked, 5 = posted
    BKTXT TEXT    -- header text (HEADER_TXT); Lucky: chars 1-8 = PERNR
);

-- ── Configuration / master data ─────────────────────────────────────────────

CREATE TABLE T001 (       -- company codes
    BUKRS TEXT,
    LAND1 TEXT,           -- country
    KTOPL TEXT            -- chart of accounts
);

CREATE TABLE T005 (       -- countries
    LAND1 TEXT,
    KALSM TEXT            -- tax calculation procedure
);

CREATE TABLE T007A (      -- tax codes
    KALSM TEXT,
    MWSKZ TEXT,
    MWART TEXT            -- V = output/input tax
);

CREATE TABLE T007S (      -- tax code descriptions
    KALSM TEXT,
    MWSKZ TEXT,
    SPRAS TEXT,
    TEXT1 TEXT
);

CREATE TABLE TCURT (      -- currency descriptions
    WAERS TEXT,
    SPRAS TEXT,
    LTEXT TEXT
);

-- ── Fake-only bookkeeping ───────────────────────────────────────────────────

-- Z_ prefix, the SAP convention for customer tables, so it cannot collide with
-- a real table name the application might one day query.
CREATE TABLE Z_COUNTER (
    NAME TEXT PRIMARY KEY,
    VALUE TEXT
);
