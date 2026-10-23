-- Fake SAP — demo data.
--
-- EVERY identifier here is invented. The formats match SAP's (10-digit EBELN in
-- the 45/47 ranges, zero-padded LIFNR, YYYYMMDD dates) but no value is copied
-- from a real system — this data appears on screen in front of customers.
--
-- The story it supports:
--   4500009001  goods PO, fully received  -> the happy path, 2-way and 3-way match
--   4700009001  service PO with an entry sheet
--   4500009002  blocked vendor            -> the scripted failure
--   4500009003  second goods PO           -> so the PO list is not a single row
--   4700009002  second service PO, entry sheet 1000009002 accepted -> parks
--   4500009004  goods PO, 18 of 30 received -> a 30-unit invoice fails the
--               3-way match; an 18-unit invoice matches its receipt and parks
--   4700009003  service PO, no entry sheet accepted -> stopped before SAP
--   4500009005  three-item packaging PO (vendor TechServ, so the supplier login
--               sees it), fully received -> every invoice line is
--               selected for parking by default; a freight line the PO does not
--               carry has no PO item, so the park is refused by name until that
--               line is unchecked or deleted

-- ── Vendors ─────────────────────────────────────────────────────────────────
INSERT INTO LFA1 (LIFNR, NAME1, MCOD1, ORT01, STCD1, STCD2, STCD3, LOEVM, SPERR) VALUES
 ('0002000101','Haier Pakistan (Pvt) Ltd','HAIER PAKISTAN (PVT) LTD','Lahore','0912345-6','','','',''),
 ('0002000102','Bestway Cement Ltd','BESTWAY CEMENT LTD','Karachi','0456789-1','','','',''),
 ('0002000103','Office Solutions Karachi','OFFICE SOLUTIONS KARACHI','Karachi','1234567-8','','','',''),
 ('0002000104','Sindh Chemical Traders','SINDH CHEMICAL TRADERS','Karachi','7788990-3','','','','X'),
 ('0002000105','TechServ Solutions (Pvt) Ltd','TECHSERV SOLUTIONS (PVT) LTD','Karachi','3456789-2','','','',''),
 ('0002000106','Securitas Guarding Pakistan','SECURITAS GUARDING PAKISTAN','Lahore','5566778-4','','','','');

INSERT INTO LFB1 (LIFNR, BUKRS, AKONT, ZTERM, LOEVM, SPERR) VALUES
 ('0002000101','1100','0002100010','NT30','',''),
 ('0002000102','1100','0002100010','NT30','',''),
 ('0002000103','1100','0002100010','NT15','',''),
 ('0002000104','1100','0002100010','NT30','','X'),
 ('0002000105','1100','0002100010','NT15','',''),
 ('0002000106','1100','0002100010','NT15','','');

-- ── Purchase orders ─────────────────────────────────────────────────────────
INSERT INTO EKKO (EBELN, BSTYP, BSART, BUKRS, LIFNR, BEDAT, WAERS, RLWRT, EKGRP, ZTERM, LOEKZ, KNUMV) VALUES
 ('4500009001','F','NB','1100','0002000101','20260302','PKR','4900000','101','NT30','','0000090001'),
 ('4700009001','F','FO','1100','0002000103','20260210','PKR','360000','102','NT15','','0000090002'),
 ('4500009002','F','NB','1100','0002000104','20260305','PKR','350000','101','NT30','','0000090003'),
 ('4500009003','F','NB','1100','0002000102','20260218','PKR','2780000','101','NT30','','0000090004'),
 ('4700009002','F','FO','1100','0002000105','20260105','PKR','540000','102','NT15','','0000090005'),
 ('4500009004','F','NB','1100','0002000101','20260220','PKR','7500000','101','NT30','','0000090006'),
 ('4700009003','F','FO','1100','0002000106','20260226','PKR','480000','102','NT15','','0000090007'),
 ('4500009005','F','NB','1100','0002000105','20260224','PKR','2160000','101','NT30','','0000090008');

INSERT INTO EKPO (EBELN, EBELP, TXZ01, MATNR, MENGE, MEINS, NETPR, NETWR, WERKS, MATKL, PSTYP, WEBRE, LOEKZ) VALUES
 ('4500009001','00010','Split AC Unit 1.5 Ton Inverter','000000000000401001','20','ST','185000','3700000','1100','0401','0','X',''),
 ('4500009001','00020','Deep Freezer 500L','000000000000401002','5','ST','240000','1200000','1100','0401','0','X',''),
 ('4700009001','00010','Annual Office Cleaning Contract','','1','AU','360000','360000','1100','0900','9','',''),
-- WEBRE is blank on 4500009002 on purpose. With GR-based invoice verification
-- on, the app's own pre-check refuses the invoice before SAP is ever called, and
-- the scripted blocked-vendor refusal would never get a chance to fire. Blank
-- here means the request reaches "SAP" and comes back rejected — a different
-- failure mode, and the one worth demonstrating. 4500009003 keeps WEBRE='X' with
-- no goods receipt, so it still demonstrates the local pre-check.
 ('4500009002','00010','Industrial Solvent Drums 200L','000000000000205017','100','EA','3500','350000','1100','0205','0','',''),
 ('4500009003','00010','OPC Cement 50kg Bags','000000000000301004','2000','BAG','950','1900000','1100','0301','0','X',''),
 ('4500009003','00020','Steel Rebar Grade 60 12mm','000000000000302011','20','TO','44000','880000','1100','0302','0','X',''),
 ('4700009002','00010','IT Support & Maintenance - Q1 2026','','1','AU','540000','540000','1100','0900','9','',''),
 ('4500009004','00010','Laptop Core i7 16GB 512GB SSD','000000000000601001','30','ST','250000','7500000','1100','0601','0','X',''),
 ('4700009003','00010','Security Guard Services','','1','AU','480000','480000','1100','0900','9','',''),
 ('4500009005','00010','Aluminium Foil Roll 20 Micron','000000000000701001','400','ST','2250','900000','1100','0701','0','X',''),
 ('4500009005','00020','PVC Blister Film Roll 250mm','000000000000701002','300','ST','2200','660000','1100','0701','0','X',''),
 ('4500009005','00030','Corrugated Carton 5-Ply','000000000000701003','5000','EA','120','600000','1100','0701','0','X','');

INSERT INTO EKBE (EBELN, EBELP, GJAHR, BELNR, BUZEI, VGABE, BWART, BUDAT, MENGE, DMBTR, WERKS, MATNR, SHKZG, LFBNR) VALUES
 ('4500009001','00010','2026','5000009001','0001','1','101','20260310','20','3700000','1100','000000000000401001','S',''),
 ('4500009001','00020','2026','5000009001','0002','1','101','20260310','5','1200000','1100','000000000000401002','S',''),
 ('4700009001','00010','2026','5000009002','0001','1','101','20260228','1','360000','1100','','S','1000009001'),
-- 18 of the 30 laptops received; the rest are still in transit.
 ('4500009004','00010','2026','5000009003','0001','1','101','20260310','18','4500000','1100','000000000000601001','S',''),
-- Entry sheet 1000009002 accepted. 4700009003 gets no row: its service was
-- never confirmed, which is the whole point of that PO.
 ('4700009002','00010','2026','5000009004','0001','1','101','20260331','1','540000','1100','','S','1000009002'),
-- 4500009005: all three packaging items received in full.
 ('4500009005','00010','2026','5000009005','0001','1','101','20260328','400','900000','1100','000000000000701001','S',''),
 ('4500009005','00020','2026','5000009005','0002','1','101','20260328','300','660000','1100','000000000000701002','S',''),
 ('4500009005','00030','2026','5000009005','0003','1','101','20260328','5000','600000','1100','000000000000701003','S','');

-- Planned delivery cost on the AC order: freight condition FRA1. It is invoiced
-- through the Goods + planned delivery costs layout, read live from EKBZ.
INSERT INTO EKBZ (EBELN, EBELP, VGABE, KSCHL, MENGE, DMBTR, WAERS) VALUES
 ('4500009001','00010','1','FRA1','20','25000','PKR');

-- ── Configuration ───────────────────────────────────────────────────────────
INSERT INTO T001 (BUKRS, LAND1, KTOPL) VALUES ('1100','PK','1100');
INSERT INTO T005 (LAND1, KALSM) VALUES ('PK','TAXPK');

INSERT INTO T007A (KALSM, MWSKZ, MWART) VALUES
 ('TAXPK','I0','V'), ('TAXPK','I1','V'), ('TAXPK','I2','V'), ('TAXPK','I3','V');

INSERT INTO T007S (KALSM, MWSKZ, SPRAS, TEXT1) VALUES
 ('TAXPK','I0','E','Exempt - 0%'),
 ('TAXPK','I1','E','Sales Tax 18%'),
 ('TAXPK','I2','E','Sales Tax 17%'),
 ('TAXPK','I3','E','Services Sales Tax 15%');

INSERT INTO TCURT (WAERS, SPRAS, LTEXT) VALUES
 ('PKR','E','Pakistan Rupee'),
 ('USD','E','US Dollar'),
 ('EUR','E','Euro'),
 ('GBP','E','Pound Sterling'),
 ('AED','E','UAE Dirham'),
 ('CNY','E','Chinese Yuan Renminbi');

-- ── Fake bookkeeping ────────────────────────────────────────────────────────
-- Parked/posted documents are allocated from here, starting at 5105000001.
INSERT INTO Z_COUNTER (NAME, VALUE) VALUES ('invoice_doc','5105000000');
