# Session handover — last updated 2026-11-24

Handover from Claude Code sessions on this machine (`D:\VIM\VIM-Luck`). Read
`CLAUDE.md` and `CONTEXT.md` first; this file records only what these sessions did and
what is still open. (`HANDOFF.md` is the separate product feature-status doc.)
Newest session first; §1–§5 below are from session 1 and are still accurate.

## 2026-11-24 (LAN test 6): invoice 58, GRs still not ticked

Second screenshot after the pull: SRN numbers show, WHT right, unit MT, but none of the six GRs is ticked.
**Cause not known** (not readable from the screenshot): an empty choice saved earlier (`[]`), GRs ticked on
another live invoice of PO 1010027885, or saved line ids that no longer exist. Fixed the last one
(`billed_by_po_item`), and the card now says why nothing is ticked (`why_not`) and offers "Tick them" when
the receipts add up but something else was saved. Next: read that line on LAN, or tick by hand and Resubmit.

## 2026-11-24 (after `debb352`): the freight vendor may differ from the PO's vendor

Client's answer: "dosra hoskta hay kbi same hota hay". A freight-only invoice is now parked for the vendor
that issued it (by NTN), sent as `HEADERDATA-DIFF_INV` when it is not the PO's vendor; details in CLAUDE.md.
Offline tests and build pass, not run on AUP. **Before the first transporter park, confirm on AUP:**
`DIFF_INV` in `BAPI_INCINV_CREATE_HEADER` / `BAPI_INCINV_CHNG_HEADER` (`sap_dd03l.py <structure>`; PyRFC raises on
an unknown field), and that `TMC_VIM` may read LFB1 (skipped with a log line if not). A freight and a goods
invoice with the **same** number, vendor and PO are still a duplicate. Still open: freight tax code.

## 2026-11-24 (after `4fc4b84`): the papers need not arrive together; the summary is optional

User: "zarori nahe ek wqt may saari invoice ho" and "mil jaye to theek, nahe millay to asis chlay".
Built: a GRN summary attached later (Supporting Documents, type "Goods Receipt / GRN summary") is read;
goods and freight invoices of one PO use each other's GRs or summary when the amounts add up; no
summary (or one naming no GR of SAP) = as before. Offline tests and build pass, Gemini stubbed, not run
on AUP or in a browser.

## 2026-11-24: client can attach goods invoice + freight invoice + GRN summary together (built, offline only)

Client: one PDF of scanned pages. The extraction prompt now reads the SRN rows (`goods_receipts`), the
file is split into goods and freight drafts as before, both get the SRNs (`invoices.srn_list`, new
column), and after the PO match exactly those SRNs are ticked, checked against SAP (details in
CLAUDE.md). `test_srn_list.py` passes with Gemini **stubbed**: how well it reads a real scan is
**not tested**, and no sample file has been received. Nothing run on AUP or in a browser.

## 2026-11-24: freight comes on its own invoice (answer from the client)

"Freight ki alag invoice milti hai". Their SRN report (PO 1010027885) has one line per SRN with product,
18% sales tax and freight at 5,000/MT without tax; **SRN No. = the 105 document** (`5002029076`-`81`), while
VIM's GR key is the 103 (`5002029070`-`75`), so the GR card now prints the SRN too. Built: layout
"Planned delivery costs" = freight-only invoice with its own SRN ticks, double-billing refused, total
must equal the invoice (details in CLAUDE.md). Offline tests and build pass; **nothing of it has run on
AUP**.
- **Still to ask:** is the freight invoice from Hamza Trading or from a transporter (another SAP
  vendor)? VIM parks under the PO's vendor only. And the freight tax code (`I0` in the first MIR7
  screen, `2I` in the second, 15% in the PO's GSF1).
- MIR7's balance on the second screen is 127,482 above goods + freight; not explained.

## 2026-11-24 (LAN test 5): invoice 58 (151) on PO 1010027885

Full-page screenshot of the parked + REJ invoice. **Confirmed on AUP:** the 103/105 GR list (`675bb9d`):
six open GRs `5002029070`-`75`, 57.52 / 58.96 / 79.48 / 78.14 / 76.68 / 74.16 MT, the same as the client's
MIR7; the five subject WHT types, ticked, estimates right; FBR badges and profile; REJ read back.
**Problem:** no GR is ticked on it. It was parked (10:47) with nothing ticked, so by the code the whole
424.94 went on the **latest** GR (`5002029075`, 74.16 MT) as one row; check MIR4 `5105660695`. The
auto-tick skips invoices that are already in SAP, REJ included. Workaround: tick the six, Resubmit.
**Built on the user's yes:** auto-tick for REJ invoices; the park uses the same suggestion when nobody
chose; a park with nothing ticked is refused when a GR-based item bills more than its latest GR has
open. Offline tests and build pass; the Resubmit with six rows has not run on AUP.

## 2026-11-24: PO 1010027885 in MIR7: several GRNs + conditions (freight park fixed, offline only)

Client's screens for the same vendor invoice (424.94 MT): six GR lines 57.52 / 58.96 / 79.48 / 78.14 /
76.68 / 74.16 = **424.94** = 254,964 with tax code `2I`, plus **FRC1** freight 5,000/MT = 2,124,700 with
tax code `I0`, plus a `GSTR` row without amount. ME23N conditions: PBXX 600, FRC1 5,000, GSF1 15%, GSTR 18%;
OUn = OPU = MT. The paper invoice is 300,857.52 (goods + 18% only, no freight), so it is layout
**Goods/service items**; the goods side is what VIM builds. **Layout "both"/"delivery" was wrong in
four ways, fixed on the user's yes:**
1. EKBZ rows are added without `SHKZG`, so reversed GRs inflate the freight.
2. The whole open freight of the PO is sent, not that of the ticked GRs.
3. The goods tax code (`2I`) is sent on the freight; the client uses `I0` there.
4. Every open condition is sent, with no choice and no check of its own (freight) vendor.
Now: new *Planned Delivery Costs* card (only with layout delivery/both), `invoices.sap_delivery` (new
column, migrated), signs, per-GR share, own tax code per condition, freight-vendor check, and a park
refused when goods + freight + tax exceed the vendor's invoice total. Details in CLAUDE.md.
- **Never run on AUP.** Unconfirmed: EKBZ `SHKZG`/`GJAHR`/`BELNR`/`BUZEI`/`LIFNR` names (LIFNR falls back),
  whether `TMC_VIM` may read EKBZ, whether a delivery row needs `REF_DOC` on a GR-based PO item, and
  whether a freight row accrues on the 105. A separate transporter bill can't be parked (VIM parks
  under the PO's vendor).
- A fake SAP file (`SAP_FAKE_DB_PATH`) made before this lacks the new EKBZ columns: delete it once.
- Asked of the client: freight on the same invoice or a separate transporter bill; freight tax code
  (`I0` or 15%); are GSTR / GSF1 lines parked.

## 2026-11-24: SAP status re-read when the invoice page opens (after `ee4842d`)

User: the status must refresh on load, without clicking "Refresh from SAP". `SAPWorkflowStatus.jsx`
now calls the refresh once per page open when the invoice has a workflow and is not posted; the
button stays. Frontend only. Seen on LAN: invoice 58 (number 151) parked as `5105660695/2027`,
company code 1200, then `REJ` in SAP.

## 2026-11-24: GRs ticked automatically when they add up (after `3e51416`)

Live example from the client: Hamza Trading invoice **151**, PO `1010026689`, 424.94 x 600 + 18%, no
GRN printed: **one invoice, several GRNs** (supported by ticking several GRs, one SAP document). On the
user's yes, the card now ticks all open GRs of a PO item when they add up to the billed quantity
(`services/gr_suggest.py`; details in CLAUDE.md). Offline tests and build pass; not checked in a
browser or on AUP.
- The paper has `5105656318` handwritten and a 13 Aug 2024 stamp: probably already posted in SAP, so
  the GRs of `1010026689` may show as "fully invoiced" (check MIR4).
- Invoice 56 bills the same 424.94 on PO `1010027884`; same number + another PO is not a duplicate.
- Asked of the client, unanswered: is one invoice with several GRNs parked as **one** document or one
  per GRN (the second would be blocked as a duplicate)? May one GRN carry partial invoices?

## 2026-11-24: duplicates are also refused at Validate

Client: "Invoice 1234 / GRN 12345" twice must not be parked. It already was refused (the key has
Reference + PO; the GRN is not part of it, but a GRN belongs to one PO). New on the user's yes: the
**Validate** button refuses it too (`DUPLICATE_BLOCKED_STATUSES`), as soon as the PO is known (matched
or printed); without a PO it is caught at submit as before.
**Gaps told to the user, not built:** (1) the same GRN under *another* invoice number while the first
is only parked; (2) a copy of an invoice deleted from VIM only or set to `exception`; (3) invoices
entered directly in SAP; (4) `1234` vs `INV-1234`. To ask the client: same number + same PO but
*another* GRN (blocked today), and whether one GRN may carry partial invoices.

## 2026-11-24 (LAN test 4): unit of measure = OPU from the PO

Client on invoice 151 (GYPSUM, unit empty): the unit must come from ME23N, **OPU** = MT. The line was
empty because the invoice was **not matched to its PO yet** (no "on PO" badge; PO `1010026689` only
suggested), and the unit was only filled at match, from the order unit. Now `EKPO-BPRME` is read and
kept as `po_line_items.price_unit` (new column, migrated at startup) and used first; the invoice page
also shows it before the match when the printed PO is in VIM with one unit (`services/po_units.py`).
- A fake SAP file (`SAP_FAKE_DB_PATH`) made before this lacks `EKPO.BPRME`: delete it once.
- **Open:** if OPU and order unit differ, the park still sends the billed quantity with the order
  unit, unconverted (as before). Not checked on AUP or in a browser.
- The WHT and Goods Receipts cards only appear **after** the PO match (they need its vendor/GRs).

## 2026-11-24 (after `2ff7419`): WHT card, subject types ticked by default

The user clarified: the `subject = true` types must be **checked**, only those. The card shows a ticked
Subject box per type and **Change** starts with all of them ticked; unticking some saves a choice
(sent as `WITHTAXDATA`), all ticked = vendor BP = nothing sent. Frontend only, not checked in a browser.
**Watch on AUP:** the vendor of invoice 56 is subject to VI 4.5% *and* FB 5.5%; check in MIR4 which
types SAP really calculates when nothing is sent.

## 2026-11-24 (LAN test 3): WHT card, only subject types; estimate base fixed (dev-shahzaib only)

The LAN `/wht` read works: vendor `0053001052` / `1200` is subject to VI, FB, FE, V7, K1; KZ, V1, VG
and PA are in the BP but not subject. On the user's request ("Check only Subject is true") the card
shows and offers **only** `WT_SUBJCT = X` types, and the park refuses (422) any other.
- The estimate of sales-tax WHT (V7, K1...) was on the net amount (V7 showed 254,964 = 100% of net).
  It is now on the sales tax (`wht_base_kind()`, read from the code's name); C1, K5, PL, V2, V5 and
  W5 have no clear base in their name, so they get no estimate. Display only, nothing sent to SAP.
- **Change** started unticked in this commit ("Check" was read as a filter); superseded above.
- Tests and build pass. **Not checked** in a browser or on AUP; a WHT park has never run on AUP.
- Still not back from LAN: the GR card of invoice 56 after `675bb9d`.

## 2026-11-24 (LAN test 2): two-step GRs (103/105) - fixed (dev-shahzaib only, not verified on AUP)

`7e27e79`'s card showed the cause for PO `1010027884`: 7 GRs, all "received" negative. They are
**two-step receipts**: the 103 has no quantity, the 105 releases have it (13 rows), and the code
skipped every 105 while still subtracting the reversals. `fetch_gr_overview()` now counts the 105s
on their 103 (S adds, H subtracts); each GR lists its movements.
- The last six GRs total **424.94**, exactly what invoice 56 bills.
- **Not confirmed:** the 105 rows' `LFBNR` pointing at the 103 (if not, they show as "unused 105"
  again), and the net: 13 S rows against 8 H rows, so some GRs may really be reversed.
- EKBE has a `P` row: parked invoices **are** in EKBE, the earlier notes were wrong. They are
  reported ("parked"), not subtracted, until MM/ABAP say when SAP clears them.

## 2026-11-24 (LAN test): FBR profile works; GR list empty for PO 1010027884 (dev-shahzaib only)

- **A works on the LAN box:** the FBR profile (NTN Details) shows for NTN 1328862-8, with Income Tax
  and Sales Tax Active. The client's vendor (sales tax inactive) is still to be tried.
- **F:** `open-grs` returned `grs: []` without an error for PO `1010027884` (invoice 56). The cause is
  **not known yet**: every GR may really be invoiced, or the 101/103 filter may hide Lucky's movement
  type. The list could not say which, so `fetch_gr_overview()` now also returns the closed GRs with a
  reason, the EKBE row count and a count of rows that took no part; the card shows them and the log
  has `GRs for PO ...`. The filter itself is unchanged. Compare with ME23N > PO history.
- The user asked to hold merges to `main` until LAN testing is done. `main` was already at
  `b9546c9` when that message arrived; it was left there.

## 2026-11-24: OPEN ITEMS and corrections (read this first)

Everything up to `263f676` is on both `main` and `dev-shahzaib`. This handover update is the next
commit, on `dev-shahzaib` only.

**FBR commits the entries below don't describe:**
- `b1b1967`: `/api/fbr/verify-ntn` uses the live fallback when `FBR_LIVE_LOOKUP_ENABLED`. The card
  and the review screen call it with `check_live=false`.
- `8fe582e`: "NTN Details" panel with every profile field; tolerant reply parser (`_fbr_titles`).
- `1c57dce`: a profile reply that is not valid JSON is read as text, with an outputType 5 retry.
  **Not confirmed on the LAN box**: the last screenshot (before this commit) still said "FBR profile
  not available". If it stays empty, look for `FBR 1003` in the backend log.

**Seen working on the LAN box:** park + workflow, "Refresh from SAP" (REJ), the live FBR verify
(Income Tax and Sales Tax badges). **Never run on AUP or in a browser:** F (GR-wise parking), G
(WHT), bulk delete, the new tax-code dropdown, the T100 text (it still showed only `FF 724`).

**Known weak points:**
- **WHT (G), fixed after `3f62181`:** the 180 codes are one per type, so
  "another code" always meant another type. The card now ticks the vendor's own BP types, and the
  park refuses (422) any other type. **Still open with ABAP/FI:** `WITHTAXDATA` goes without base,
  amount or `SPLIT_KEY`; whether an unticked type is really dropped; whether SAP applies the BP
  defaults when nothing is sent.
- **Sales-tax badge (A), fixed after `3f62181`:** an unrecognised status or no
  answer from FBR is now **Unknown** (it was "Active" / "Not on ATL"); "Inoperative" is no longer
  read as active. New `test_fbr_status.py`. The real 1005 reply is still not inspected: if the
  badge says Unknown, the backend log has `FBR 1005 reply: status not recognised (fields: …)`.
  The big ATL badge above still says "NTN Not Found" when FBR does not answer.
- **Tax rate (C):** "first n% in the description", so `I5` (17% + 2%) counts as 17. VIM still does
  not read the PO item's tax code (`EKPO-MWSKZ`) or warn on a mismatch.
- **GRs (F):** GRs already used by a *parked* invoice still show as open. `LFGJA`/`LFPOS` are not yet
  checked on AUP (`sap_dd03l.py EKBE`).
- **No SAP dry run on submit** while `SAP_WF_DRY_RUN_SAFE=false`.
- `[wf-diag]` / `[park-diag]` still log at WARNING.

**To ask ABAP / FI:** (1) empty `WITHTAXDATA` = BP defaults? (2) are type + code enough, may the
type differ from the BP, is `SPLIT_KEY` needed? (3) is the `VALIDATE` check live? (4) does a change
through the BAPI restart the workflow (REJ -> BLK)? (5) how to see GRs already used by parked
invoices? (6) cancel the second workflow of `5105660678` and the dry-run one of invoice 46.
**FI:** PO code `I2` is 17% but the invoice is 18% (`2I`): which one, and fix `5105660691`?
**Basis:** T100 read, `S_RFC` on `ZINI_VERIFY`. **Network:** `ztmc_login` from 192.168.15.10.

**LAN housekeeping:** `fix_invoice_sap_year.py 54 2027 --yes` (and 53 if it shows `/0000`).
**Parked by the user:** the MIRO-like Simulation / Messages window.

## 2026-11-24 (later): client observation G — Withholding Tax — committed, pushed, merged to main

**Basis** granted `TMC_VIM` read access to LFBW, T059Z, DD02L, DD03L and FUPARAREF. The LAN box
ran `sap_dd03l.py`; the dump is in `content/sap-metadata-dump-2026-11-23.txt` on that box. It
confirmed:
- **LFBW:** `LIFNR`, `BUKRS`, `WITHT`, `WT_WITHCD`, `WT_SUBJCT`. The sample rows are company code
  1200 with `KZ`/`KZ`.
- **T059Z:** the rate is `QSATZ` and the portion is `QPROZ`.
- **Park BAPI `WITHTAXDATA`:** `WI_TAX_TYPE`, `WI_TAX_CODE`, `WI_TAX_BASE`, `WI_TAX_AMT`,
  `WI_TAX_WITHHELD_AMT`.

**Backend:**
- `sap_po_service.fetch_vendor_wht(vendor, bukrs)` reads LFBW and the T059Z rate; names come from
  `lucky_wht_codes.py`.
- `GET /api/sap/invoices/{id}/wht` returns the vendor's WHT, the invoice's override, the 180 PK
  codes and an estimate on the net amount.
- `PUT /api/invoices/{id}/wht` stores the override in the new column `invoices.sap_wht`, which has
  its migration.
- Park and resubmit send `WITHTAXDATA` with `WI_TAX_TYPE` and `WI_TAX_CODE` **only when
  overridden**. Otherwise SAP applies the BP defaults itself.

**Frontend:** `components/detail/WithholdingTaxCard.jsx` shows WHT type, code, description, rate
and estimate. It offers **Change** (a dropdown of the 180 codes) and **Use vendor BP**, and it is
locked once the invoice is in SAP.

**Fake SAP:** LFBW and T059Z tables, with vendor `0002000101` holding VG 4% and VN 8%.
`test_sap_workflow` has a new `WITHHOLDING TAX` section. All suites pass and the frontend builds.

**Not checked on AUP or in a browser. Open:**
- Confirm with Lucky/FI that SAP really derives WHT from the BP at park when `WITHTAXDATA` is
  empty, and that a code override computes the base and amount itself (VIM sends no
  `WI_TAX_BASE`).

## 2026-11-24: client observation F — GR-wise parking — committed, pushed

**Backend:**
- `sap_po_service.fetch_open_grs(po)` reads EKBE `VGABE` 1 and 2 with
  `LFGJA`/`LFBNR`/`LFPOS`. It returns one entry per GR material-document line, with the open
  quantity: received minus reversed minus posted-invoiced.
- `split_by_grs()` builds one ITEMDATA row per selected GR.
- `GET /api/sap/invoices/{id}/open-grs` and `PUT /api/invoices/{id}/parking-grs` are new. The
  selection is stored in the new column `invoices.parking_gr_refs`, which has its migration.
- In the park endpoint, ticked GRs replace the "latest GR" reference for their PO item. The park
  returns 422 when the ticked GRs don't add up to the billed quantity or are no longer open.
  Nothing ticked = the old behaviour.

**Frontend:** `components/detail/GoodsReceiptsCard.jsx` on the invoice page shows each GR with a
checkbox, the open quantity and amount, and the selected total per item. It is locked once the
invoice is in SAP, unless the invoice is REJ.

**Fake SAP:**
- `EKBE` gains `LFGJA` and `LFPOS`; old file stores get them through `ALTER TABLE`.
- PO `4500009001` item 10 is now two GRs, 12 + 8 (`5000009001` / `5000009006`).
- `test_sap_fake`'s GRN check was updated to match, and `test_sap_workflow` has a new
  `GR-WISE PARKING` section. All suites pass, and the frontend builds.

**Not checked on AUP or in a browser.**
- `LFGJA` and `LFPOS` are standard EKBE fields, but confirm the reversal and invoice references
  on a real PO.

**Open — client observation G (WHT):**
- It waits for the LFBW / park-BAPI `WITHTAXDATA` field names, either as screenshots or through
  Basis access to DD02L/DD03L/FUPARAREF.
- It also needs `S_TABU_DIS` for LFBW for `TMC_VIM`; the email draft went to the user.

## 2026-11-23 (night): client observations A–G — A, B done; G started — A, B + WHT list committed

The client's list (the user said to work from it and set earlier work aside):

**A. FBR status — done:** Income Tax, Sales Tax and Taxpayer Profile are now shown separately.
Example: income tax Active but sales tax not.
- `fbr_verification.fbr_status_detail()` reads the local ATL lists IT and ST separately
  (`_lookup_atl_lists`).
- With `FBR_LIVE_LOOKUP_ENABLED`, a miss goes live: protocol **1004** for the IT ATL and **1005**
  for the ST ATL. The profile comes from **1003**, the Taxpayer Profile Inquiry, with outputType 4.
  These protocol ids are read from IRIS's own portal bundle.
- The profile keeps Name, Category, Registered On, Tax Office, Registration Status ("Income Tax:
  Active, Sales Tax: OPERATIVE") and Registered for Sales Tax. (Email and Cell were dropped at first; since `8fe582e` every field FBR
  returns is shown, Email/Cell masked by FBR.)
- `/api/fbr/verify-ntn` returns `income_tax`, `sales_tax` and `profile`. The Vendor Verification
  card shows two badges plus the profile block.
- Tested offline with stubs. The live 1003 reply shape was seen once for NTN 1328862.

**B. Unit of measure from the PO — done:** at PO match, an invoice line with **no** unit takes the
matched PO line's unit (`po_matching.py`). A printed or typed unit is never overwritten.
`test_sap_workflow` covers it.

**C.** Tax codes: done in `b681d01`. **D:** resolved by business. **E:** testing only.

**G. Withholding tax — started:** the user chose "show and send to SAP".
- `services/lucky_wht_codes.py` holds the 180 PK codes from `Book3.xlsx` (T059Z: type, code,
  name, rate).
- **Next:** read the vendor's WHT types and codes from BP / `LFBW` (vendor + company code), show a
  WHT section on the invoice, and send `WITHTAXDATA` in the park BAPI.
- **Before coding,** confirm the field names on AUP from the LAN box:
  - `backend/.venv/bin/python backend/sap_dd03l.py LFBW --rows 2`
  - `backend/.venv/bin/python backend/sap_dd03l.py --fm BAPI_INCOMINGINVOICE_PARK`, which shows
    the `WITHTAXDATA` structure.

**F. GR-wise parking — to do:** list the PO's not-yet-invoiced GRs with checkboxes; only the ticked
ones are parked, each line referencing its GR.

## 2026-11-23 (evening): Lucky's official tax-code list replaces the old codes — committed, pushed

The user supplied `Tax Codes Details.xlsx`: 100 codes with their descriptions.

**Why it mattered:** the dropdown and the AI suggestion offered "I1 — Sales Tax 18%". That came
from the fake-SAP fixtures, cached in the LAN box's `sap_tax_codes`. In Lucky's SAP `I1` is
**Zero Rated 0%** and 18% is **`2I`**, which is why invoice 54 was refused with `FF 724`.

**Changes:**
- `backend/app/services/lucky_tax_codes.py` holds the list: 80 input and 20 output codes (`O…` and
  `$O` are output). The rate is the first "n%" in the description; 7 codes have none.
- `GET /api/sap/tax-codes` returns this list for every company code (`source: lucky_master`); the
  `sap_tax_codes` cache is no longer read.
- `tax_rate_for_code()` uses the list first and SAP only for unknown codes.
- The AI default (`pickDefaultTaxCode`, unchanged) now gives 18% → `2I`, 17% → `I2`, 0% → `I0`,
  16% → `IB`. Checked with node against the new list.
- The fake fixtures' `T007S` texts follow Lucky's meanings, and `2I` was added. Tests use `2I` for
  18%. All suites pass.

**Note:** invoices that already saved `sap_tax_code = I1` keep it. Re-pick the code on any open
invoice that is really 18%.

## 2026-11-23 (later): live FBR lookup failed behind the Fortinet proxy — CA bundle fix — committed, pushed

**Symptom:** after `90bd8f0`, invoice 56 showed `source: live_api` but still `not_found`.

**Cause:** the FBR module uses `requests`, which **ignores `SSL_CERT_FILE`** (it reads only
`REQUESTS_CA_BUNDLE` or certifi). Behind the office Fortinet proxy, which re-signs HTTPS, the IRIS
token fetch failed with `CERTIFICATE_VERIFY_FAILED`, so the lookup returned nothing. httpx (Gemini,
`ztmc_login`) does honour `SSL_CERT_FILE`, which is why those calls worked.

**Fix:** `fbr_verification._new_session()` sets `verify` from `FBR_CA_BUNDLE`, else
`REQUESTS_CA_BUNDLE`, else `SSL_CERT_FILE` (which `start-lan.sh` already sets). `FBR_CA_BUNDLE` is a
new setting and is in `.env.example`.

**Verified live from the Windows box,** with the Windows root store (which holds the Fortinet CAs)
exported to PEM:
- The token extracts (length 1106).
- `verify_ntn("1328862-8")` returns `verified_active`, INAM UL HAQ, "HAMZA TRADING ,UNIVERSAL
  EXPORTER", Active (source `live_api`).

**On the LAN box:**
1. `git pull` and restart.
2. Keep `FBR_LIVE_LOOKUP_ENABLED=true`.
3. If its system CA file lacks the Fortinet CA, point `FBR_CA_BUNDLE` at a PEM that has it.

## 2026-11-23: "NTN Not Found" for individuals — live FBR fallback on invoice verify — committed, pushed

**Case:** invoice 56, vendor HAMZA TRADING, NTN `1328862-8`. VIM said `not_found` (source
`local_db`), while FBR's site, searched **by NTN**, shows **Active** with Registration No
`4220148670085`, which is the owner's CNIC.

**Cause:** FBR's ATL file lists individuals by CNIC. The imported `atl_taxpayers` therefore has no
row under their NTN. VIM already handles both the 7-digit and 8-digit NTN forms.

**Fix:**
- The invoice verify (`POST /api/fbr/invoices/{id}/verify-fbr`) and the verify at save
  (`invoices.py`) now pass `check_live=settings.FBR_LIVE_LOOKUP_ENABLED`.
- So, with the flag on, an NTN missing from the local table falls through to the live FBR lookup
  (`live_fbr_lookup`). Before this they never asked for it, even with the flag on.
- Checked offline with a stubbed live lookup; it is not tried against FBR yet.

**To switch it on (LAN box):**
1. Set `FBR_LIVE_LOOKUP_ENABLED=true` in `backend/.env` and restart.
2. Click "Re-verify" on invoice 56.

**Open:**
- Confirm the box reaches `iris.fbr.gov.pk` / `api.fbr.gov.pk` through the Fortinet proxy
  (`SSL_CERT_FILE` is already set).
- **Settled:** the FBR portal searches by the 7-digit NTN base (`1328862`), so `live_fbr_lookup`
  now drops the check digit of an 8-digit NTN. Checked offline: `1328862-8`, `13288628` and
  `1328862` are all sent as `1328862`; a CNIC goes unchanged.

## 2026-11-21 (evening): resubmit tested on AUP — "0000" fiscal-year bug fixed — committed, pushed

The first live resubmits on AUP (invoices 53/54) showed four things:
- **`S_RFC` for `BAPI_INCOMINGINVOICE_CHANGE`** was missing (`RFC_NO_AUTHORITY`). Basis has since
  granted it.
- **`FF 724` "Tax entry not possible in this item"** was logged with the rejection, and the resubmit
  hit it too. VIM sent the AI-suggested `I1` together with an 18% tax amount. The PO item's code is
  `I2`. Lucky's list (2026-11-23) has `I1` = Zero Rated 0%, so a tax amount on a 0% code is the
  likely cause; the PO/`I1` mismatch was a first guess. Neither was confirmed by FI. **Caution:**
  invoice 54 went through with `I2` (17%) and an 18% tax amount of 51,197 - FI must check it. VIM never reads `EKPO-MWSKZ`; a follow-up is to default to it and warn on a
  mismatch (offered to the user). Choosing `I2` by hand made the resubmit go through.
- **Bug, now fixed:** when the number is unchanged, `BAPI_INCOMINGINVOICE_CHANGE` returns
  `INVOICEDOCNUMBER_NEW` / `FISCALYEAR_NEW` as initial values (`0000000000` / `0000`). VIM stored
  `0000` as the year, the OBJKEY became `…0000`, and "Refresh from SAP" stayed on "Waiting for
  SAP". `_change_parked()` now keeps the original document and year when the exports are
  initial. The fake connector returns them that way, and `test_sap_workflow` asserts it.
- **Repairing invoice 54:** run
  `backend/.venv/bin/python backend/fix_invoice_sap_year.py 54 2027 --yes`. It is report-only
  without `--yes`, and it restores the year and rebuilds the OBJKEY.

## 2026-11-21 (later): resubmit a REJECTED invoice on the same SAP document — committed, pushed

**Requirement:** when SAP's workflow rejects an invoice, the user corrects it in VIM and sends it
again. It must be the **same parked document**, which is Lucky's own functionality.

**ABAP confirmed:** changing and saving a rejected parked document makes `ZMIR7_PARK` restart the
workflow itself, and the `ZMIR7_WF_LOG` row turns from `REJ` back to `BLK`.

**`BAPI_INCOMINGINVOICE_CHANGE` on AUP** (SE37/SE11 screenshots from the user):
- IMPORT: `INVOICEDOCNUMBER`, `FISCALYEAR`, `INVOICE_DOC_STATUS` (optional), `TABLE_CHANGE`
  (`BAPI_INCINV_CHNG_TABLES`: `ITEMDATA`, `GLACCOUNTDATA`, `MATERIALDATA`, `TAXDATA`, …, 'X' =
  replace), `HEADERDATA_CHANGE` (`BAPI_INCINV_CHNG_HEADER`, same field names as the park header),
  `HEADERDATA_CHANGEX`, `ADRESSDATA_CHANGE(X)`.
- EXPORT: `INVOICEDOCNUMBER_NEW`, `FISCALYEAR_NEW`.
- TABLES: `ITEMDATA` (`BAPI_INCINV_CREATE_ITEM`) and `TAXDATA` (`BAPI_INCINV_CREATE_TAX`), the same
  structures as the park.

**Code:**
- `sap_invoice_post.post_invoice_to_sap(mode="change", change_doc_number=, change_fiscal_year=)`
  builds the same header, items and tax as a park, then calls `_change_parked()`.
- `_change_parked()` sends header fields `_CHANGE_HEADER_FIELDS` (never doc type, company code or
  currency) with `CHANGEX` 'X' and `TABLE_CHANGE` `ITEMDATA`/`TAXDATA` = 'X'. It commits on
  success and rolls back on E/A.
- Router `POST /api/sap/invoices/{id}/post` accepts `mode="change"` only for a parked invoice with
  workflow `REJ`; otherwise it returns 409. It runs the same gates as a park (duplicate,
  `ZINI_VERIFY`) and keeps the invoice parked on the same document.
- `invoices.py` adds `_locked_in_sap()`: line add, patch and delete are allowed when the workflow is
  `REJ`.
- Frontend: for a `REJ` invoice the fields, SAP card and lines are editable again, and a
  **"Resubmit to SAP"** button appears. The `REJ` hint in `SAPWorkflowStatus` now says so.
  "Unpark from SAP" stays.
- Fake SAP: `BAPI_INCOMINGINVOICE_CHANGE` refuses unknown structures, runs the park's item checks,
  rewrites BKTXT and flips `REJ` to `BLK`.

**Tests:** `test_sap_workflow.py` gains a `RESUBMIT` section. All SAP suites, `test_bulk_delete`
and `test_line_item_guards` pass. The frontend builds. **Not tried on AUP and not checked in a
browser.**

**Open on AUP:**
- `TMC_VIM` needs `S_RFC` for `BAPI_INCOMINGINVOICE_CHANGE`.
- Confirm the workflow restarts when the change comes **through the BAPI** (RFC), not only from
  MIR7.
- Find which header fields SAP lets change on a parked document; a refused field shows SAP's
  RETURN text.

## 2026-11-21: Inbox bulk delete (admin can drop SAP invoices from VIM only) — committed with sap_dd03l.py --fm

**Why:** many duplicate test invoices piled up, some of them parked in SAP. The user wants them
gone from **VIM only**; SAP is not to be touched.

**Backend:** `POST /api/invoices/bulk-delete` takes `{ids, vim_only}` and soft-deletes the
invoices. It returns `{deleted, skipped:[{id, reason}]}`.
- Without `vim_only`, an invoice with a SAP document is skipped.
- `vim_only=true` is **admin-only** (403 otherwise). It also removes parked/posted invoices, but
  only from VIM: no RFC is made, the SAP document and workflow stay as they are, and a WARNING is
  logged.

**Frontend:** the Invoice Inbox gets a checkbox per row, a select-all-on-page box and a
**"Delete selected (n)"** button.
- The confirm dialog shows admins an opt-in checkbox for the parked/posted ones, worded "from VIM
  only". Other roles are told those will be skipped.
- After the delete, a result banner lists what was deleted and what was skipped.

**Tests:** `backend/test_bulk_delete.py` passes; the frontend lint and build are clean.
**Not checked in a browser.**

**Also in that commit (`f886bfa`):** `sap_dd03l.py --fm <FUNCTION>` dumps an FM's interface (FUPARAREF) and its
structures (DD03L). It is meant for `BAPI_INCOMINGINVOICE_CHANGE`, which the "Resubmit a rejected
invoice to SAP" feature needs.
- The ABAP team confirmed that changing a rejected parked document makes `ZMIR7_PARK` restart the
  workflow itself, and that the `REJ` row turns back to `BLK`.
- The feature was built later, in `d8b05fb` (see the entry above).

## 2026-11-20 (night): workflow status read from the real ZMIR7_WF_LOG columns — committed `8068114`, pushed

**Why "Refresh from SAP" failed:** VIM asked `RFC_READ_TABLE` for guessed columns (`STATUS`,
`POSTED_DOC`). The SAP reply `TABLE_WITHOUT_DATA` was misleading. `ZMIR7_WF_LOG` is a transparent,
active table in AUP client 100 (ABAP team, SE11/SE16, SE37 test).

**Its real columns:**
`MANDT, OBJKEY(C40), ITEM(N4), BELNR, GJAHR, SCENARIO, ERDAT, ERZET, WF_STATUS(C3), PERNR, BUKRS,
TERMINAL, SCENARIO_DESC, AMOUNT, SLABID1, WAERS, AMOUNT_IN_LOC`.

**WF_STATUS values (ABAP team):**
- `INIT`: saved, but no workflow. The column is CHAR 3, so it is probably stored as `INI`; VIM reads
  both.
- `BLK`: in process.
- `APP`: approved **and posted**, under the same `BELNR`.
- `REJ`: rejected.

**`ZMIR7_ERROR_LOG`, also confirmed (SE37 FIELDS):**
`SR_NO(I), BELNR, GJAHR, TYPE(C1), ID, ZNUMBER, CDATE, CTIME, ZMESSAGE(C220), ZLOG_NO, ZLOG_MSG_NO,
ZMESSAGE_V1..V4, Z_FROM, TOTAL_APP, CURRENT_APPR`.
- The table has **no OBJKEY**, so VIM matches its rows by `BELNR` + `GJAHR` (`_read_error_log`).
- The newest row per document, by `CDATE` + `CTIME`, decides the result.
- `E` / `A` keeps an `APP` invoice parked and shows `ZMESSAGE`; `S` ("Document Posted") clears the
  error.
- `Z_FROM` is ignored, as the ABAP team said.
- The fake connector's `ZMIR7_ERROR_LOG` has the real shape, filled by `error_log_row`.

**Code (`sap_workflow.py`):**
- It reads `OBJKEY`, `ITEM`, `WF_STATUS`, `BELNR`, `ERDAT`, `ERZET` and takes the newest step per
  OBJKEY.
- `APP` means posted, with `posted_doc` = `BELNR`, unless the error log holds an `E` row.
- A failed error-log read is logged and skipped, so it never breaks the refresh.

**Other changes:**
- The table names are settings: `SAP_WF_LOG_TABLE`, `SAP_WF_ERROR_TABLE`.
- `backend/sap_dd03l.py` shows a table's DD03L columns; `--find ZMIR7` lists the objects and their
  TABCLASS.
- In the fake connector, `ZMIR7_WF_LOG` now has the real shape and one row per step
  (`wf_log_step`). An old-shape file store is rebuilt.
- The refresh 502 carries SAP's own text.

**Still needed from ABAP:**
- The `BKTXT = VALIDATE` check: the case is confirmed as upper-case `VALIDATE`, which is what VIM
  sends. Once ABAP says the check is live, set `SAP_WF_DRY_RUN_SAFE=true` on the LAN box.
- ~~Initiator from `BKTXT(8)`~~ **confirmed by ABAP (2026-11-20).**
- Cancel the extra workflows: the second one on `5105660678`, and invoice 46's dry-run workflow.

## 2026-11-20 (evening): submit dry run skipped while SAP raises the event — committed `5b6da8c`, pushed

**What happened:** invoice 46 got two workflows again, this time from **Submit & Park** plus
**Confirm & Park**. The submit dialog runs a SAP dry run, `mode=validate`: park, then
`BAPI_TRANSACTION_ROLLBACK`. The event raised inside `ZMIR7_PARK` **outlived the rollback** and
started a workflow for a document that was never kept.

**Fix:** new setting `SAP_WF_DRY_RUN_SAFE`, default `false`. With the workflow on and SAP raising
the event, validate stops after VIM's own checks and never calls SAP. Those checks are: duplicate,
GR pre-check, line selection, `ZINI_VERIFY`. The validate reply then carries `skipped_sap: true`.

**Submit dialog:** it shows an amber note, "VIM checks passed. SAP's own checks run when you
park…", instead of "SAP validation passed".

**Tests:** `test_sap_workflow.py` checks that validate calls no park BAPI and leaves no stray
workflow, and that `SAP_WF_DRY_RUN_SAFE=true` brings the dry run back.

**Agreed with the ABAP team instead:**
- A dry run sends `BKTXT = VALIDATE`; the value is the setting `SAP_DRY_RUN_HEADER_TEXT`.
- When `ZMIR7_PARK` sees that value, it raises no workflow event.
- A real park sends `<8-digit PERNR> <text>`.

**Wiring:**
- `post_invoice_to_sap` sends the marker in `mode=validate`.
- The fake connector starts no workflow for it.
- Tests check the dry run (`VALIDATE`, no stray workflow) and the real park (PERNR, exactly one
  workflow).

**To switch the SAP dry run back on:** once ABAP confirms their check is live, set
`SAP_WF_DRY_RUN_SAFE=true` in the LAN box's `.env`. The marker is sent either way. Check the
case: ABAP compares the text exactly, and VIM sends upper-case `VALIDATE`.

**Cleanup:** invoice 46's dry-run workflow has no kept document behind it, so cancel it in SAP.

## 2026-11-20 (later): VIM no longer raises the workflow event — SAP does (committed `2fdb3ee`, pushed)

The ABAP team confirmed that the event is created **inside `ZMIR7_PARK`** during the park. VIM's
own `SAP_WAPI_CREATE_EVENT` was therefore the second workflow.

**New setting `SAP_WF_RAISE_EVENT`, default `false`:**
- VIM parks and commits only; it makes no event call.
- It still stores `OBJKEY` (company code + document + year), so "Refresh from SAP" and the poller
  read `ZMIR7_WF_LOG` as before.
- `SAP_WF_EVENT` is not needed in this mode.
- The employee reaches SAP through `BKTXT(8)`.
- `true` restores the old VIM-raised event (`USERI` / `PWDI` container).

**Fake SAP:** the park writes the `BLK` row itself when the workflow is on and VIM does not raise
the event.

**Tests:**
- `test_sap_workflow.py` runs the old sections with `SAP_WF_RAISE_EVENT=true`.
- A new section checks the default: no event call, one workflow, `OBJKEY` stored, refresh to
  `BLK`, approve to posted.
- All SAP suites pass, as does `test_duplicate_check`.

**On the LAN box:**
- Keep `SAP_WORKFLOW_ENABLED=true`. With it off, VIM stores no `OBJKEY` and cannot track the
  workflow.
- Don't set `SAP_WF_RAISE_EVENT`; it defaults to `false`.
- After the pull and restart, park one invoice and check SWI1 for exactly one `WS90000096`.

**Open:** the ABAP team should confirm that their `ZMIR7_PARK` event reads the initiator from
`BKTXT(8)`, now that VIM sends no `USERI` / `PWDI`.

## 2026-11-20: false "Failed to park" + workflow started twice (fixed above)

**False failure — fixed (frontend):** invoice 44 parked as `5105660678/2027` with its workflow, but
the page said "Failed to park invoice in SAP". The ABAP team had the call paused in the debugger,
so it outlasted axios' 60 s timeout. The server finished anyway. Fixes:
- `postInvoiceToSAP` now uses a 180 s timeout.
- When a park request gets **no reply**, `InvoiceDetailPage` re-reads the invoice. If it has a
  document number it shows no error; if not, it says the server may still be working.
- SAP's own refusals are shown as before.

**Workflow started twice — open, on the SAP side so far:** SWI1 shows two `WS90000096`
instances (11:21:00 and 11:21:05) for the same document `5105660678` / OBJKEY
`120051056606782027`, each with a Ready approval item.
- VIM calls `SAP_WAPI_CREATE_EVENT` exactly once per park, with no retry anywhere: not in the
  connector, not in the workflow code, not in axios.
- A single document number means a single park.
- Suspects: the MIR7 park exit `ZXM08U30` or a BAdI also raises the event during the BAPI park, a
  double SWE2 linkage, or a step re-executed in the debugger.

**Test agreed with the user:**
1. Set `SAP_WORKFLOW_ENABLED=false` on the LAN box. VIM then parks without raising the event.
2. Park a new invoice without the debugger, and check SWEL and SWI1.
- **A workflow still starts:** SAP raises it itself. VIM should then stop raising the event but
  keep tracking the status. That needs a code change, because `sap_wf_objkey` is only stored when
  VIM raises the event.
- **No workflow:** the duplicate is on the SAP side (SWE2 or the debugger).

Afterwards, set the flag back to `true`. Separately, one of the two Ready items for `5105660678`
must be cancelled in SAP.

## 2026-11-19 (night): INPUT_CONTAINER rows are ELEMENT + VALUE only (SWR_CONT) — committed `12b923b`, pushed, WORKING on AUP

After `ca2a6fa` the LAN box failed with "field 'TAB_INDEX' not found". On AUP,
`SAP_WAPI_CREATE_EVENT`'s `INPUT_CONTAINER` is typed **SWR_CONT**, whose only fields are
`ELEMENT` and `VALUE`. So `_swcont_row()` became `_container_row()`, which sends just those
two. The fake connector now also refuses any other row field, and `test_sap_workflow.py`
checks that each row has exactly `ELEMENT` and `VALUE`. All SAP tests pass. `41e3a51`
(SAP's error text in the 502 reply) is pushed.

**Verified 2026-11-19 on the LAN box (live AUP):** after the pull and restart, the park plus
workflow event goes through. The user confirmed "working".

**Still open:**
- The ABAP team should confirm `BKTXT(8)` carries the PERNR (`81cd7f6`).
- Basis: `S_RFC` for `ZINI_VERIFY`.
- Network: the `ztmc_login` host from 192.168.15.10.
- `[wf-diag]` / `[park-diag]` log at WARNING; lower them once the flow is signed off.

## 2026-11-19 (evening): workflow event container back to INPUT_CONTAINER — committed `ca2a6fa`, pushed (superseded above: the SWCONT fields were wrong)

**Why:** on AUP the park failed with 502. PyRFC refused `SAP_WAPI_CREATE_EVENT` with
`RFC_INVALID_PARAMETER` "field 'SIMPLE_CONTAINER' not found". The live interface has no
`SIMPLE_CONTAINER` (TABLES: `INPUT_CONTAINER`, `MESSAGE_LINES`, `MESSAGE_STRUCT`). The park was
rolled back as designed, so nothing was left parked. Commit `9aecc4b` (made on Windows, where the
ctypes path silently ignores an unknown table) had switched to it.

- `sap_workflow.py`: the container is `INPUT_CONTAINER` again. Every row now fills all SWCONT
  fields through `_swcont_row()`: `ELEMENT`, `TAB_INDEX=000000`, `ELEMLENGTH=len(VALUE)` (3 digits),
  `TYPE=C`, `VALUE`. The old INPUT_CONTAINER rows sent only ELEMENT and VALUE, so `ELEMLENGTH` was
  `000`. That is the likely reason SAP then read the elements without names.
- The fake connector now refuses any table other than `INPUT_CONTAINER` on this FM, as PyRFC
  does. `test_sap_workflow.py` checks the table name and the full SWCONT rows.
- All of these pass: `test_sap_workflow`, `test_sap_fake`, `test_sap_employee` and
  `test_header_text_pernr`.
- **Open:** pull and restart on the LAN box. Then have the ABAP team check in the debugger that
  `USERI`, `SCENARIO_CHAR` and the other elements arrive **with their names**. If they don't, the
  fallback is to build the container on the ABAP side (`SWC_SET_ELEMENT`).

## 2026-11-19 (latest): employee ID in the park BAPI header text (BKTXT) — committed `81cd7f6`, pushed

**Why:** Lucky's ABAP team wants the parking employee in `BAPI_INCOMINGINVOICE_PARK`
itself, in `HEADER_TXT` (→ `RBKP-BKTXT`, CHAR 25). Agreed format: **chars 1–8 = 8-digit
PERNR, then a space, then the header text cut to 16**, e.g. `00004007 einv-HP-2026-041`.
ABAP reads `BKTXT(8)`. The workflow event (`USERI` / `PWDI`) is unchanged.

- `sap_invoice_post.build_header_text(text, sap_user)`: prefixes only when the user's
  `sap_username` is numeric (≤8 digits, zero-padded); otherwise the old text (cut to 25).
  Setting `SAP_HEADER_TEXT_PERNR` (default `true`). The stored `invoices.sap_header_text`
  stays the user's text, without the prefix.
- Log line `[park-diag] BAPI_INCOMINGINVOICE_PARK HEADER_TXT='…'` (WARNING) shows exactly
  what was sent.
- Fake SAP: `RBKP` gained `BKTXT` (the connector adds the column to an older
  `SAP_FAKE_DB_PATH` file), so `py -3 backend/sap_se16.py RBKP` shows it.
- Test: `backend/test_header_text_pernr.py` (offline). It passes, and so do `test_sap_fake`,
  `test_sap_workflow` and `test_sap_employee`.
- UI: hint under Header Text on the SAP posting card.
- **Open:** verify on AUP that the ABAP exit reads the PERNR from `BKTXT(8)`.

## 2026-11-19 (later): SAP authorization error log for the Basis team

**Why:** the user is getting SAP access from the Basis team and needs evidence when SAP
authorization fails.

- **New `backend/app/services/sap_auth_log.py`:** a dedicated `sap_auth` logger.
  - It writes timestamped lines to the console (the `start-lan.sh` output) and to
    **`backend/logs/sap_auth.log`**, which rotates at 5 MB and keeps 5 files.
    `SAP_AUTH_LOG_FILE` changes the path; empty means console only. `*.log` is git-ignored.
  - The app has no logging config, which is why it has its own handlers.
- **What gets logged:**
  - **Login service (`ztmc_login`):** every attempt. Success is logged at INFO with the name.
    Failures are logged at WARNING with:
    - a `kind`: `EMPLOYEE_REFUSED`, `BASIC_AUTH_REFUSED`, `SERVICE_NOT_FOUND`, `SERVER_ERROR`,
      `GATEWAY_ERROR`, `TLS`, `TIMEOUT`, `CONNECT` or `NOT_CONFIGURED`;
    - the PERNR, the VIM user (`id:email`), the URL, the Basic-auth user **name**, and whether its
      password is set;
    - the HTTP status, elapsed ms, errorCode/message, selected response headers (`sap-server`,
      `www-authenticate`, …) and a 600-character body excerpt;
    - a `hint` naming the Basis transaction to check (SU01, SU53, S_ICF/S_SERVICE, SICF, STRUST,
      ST22, SM21, SMICM).
  - **RFC failures:** for `ZINI_VERIFY`, the per-user RFC login test (`POST /api/sap/users/{id}/login-test`)
    and park/post. Each line has the kind (`RFC_LOGON_FAILURE`, `RFC_AUTHORIZATION_FAILURE` → S_RFC/SU53,
    `FUNCTION_NOT_FOUND`, `RFC_COMMUNICATION_FAILURE`), PyRFC's key/msg_class/msg_number/msg_v1-4,
    the RFC user, ashost/client/sysnr and the function.
  - **`HIERARCHY NOT FOUND`:** logged with the PERNR, amount, currency, the raw `EV_FLAG` and the
    configured OK flags (useful for confirming what `EV_FLAG` really returns).
- **No passwords or cookies are ever logged.** The test checks this.
- **Admin endpoint:** `GET /api/sap/auth-log?lines=200` returns the file's tail.
- `test_sap_employee.py` now also covers the log: all pass. `test_sap_fake`, `test_sap_workflow`
  and `test_duplicate_check` were re-run and pass.

**To send Basis on the LAN box:** `tail -n 100 backend/logs/sap_auth.log`, or grep for `FAILURE`.
Share the lines as they are; they contain no secrets.

## 2026-11-19: SAP employee login + ZINI_VERIFY hierarchy check (committed `d542e2c`, pushed)

**Requirement (Lucky Cement):** while uploading an invoice in Verity, (1) the user signs in
with their SAP employee ID via Lucky's login service, and (2) SAP's RFC `ZINI_VERIFY` checks
that an approval hierarchy exists for that employee and amount.

- Login service: `POST https://upgapp2023.lucky-cement.net/sap/bc/ztmc_login`, HTTP Basic auth,
  body `{"userId": "00004007", "paswrd": "..."}`. Success → `{"success": true, "errorCode": "OK",
  "userid", "name"}`. Failure → `{"success": false, "code": 401, "errorCode": "INVALID_PASSWORD"}`.
- `ZINI_VERIFY`: imports `IV_PERNR` (PERNR_D), `IV_WAERS` (WAERS, optional), `IV_AMOUNT` (WRBTR);
  export `EV_FLAG` (CHAR1).

**What was built** (all behind two switches, both **off** by default):

| File | Change |
|---|---|
| `backend/app/config.py`, `backend/.env.example` | `SAP_EMPLOYEE_LOGIN_ENABLED`, `SAP_LOGIN_API_URL/_USER/_PASSWORD/_CA_BUNDLE/_TIMEOUT_SECONDS`, `SAP_HIERARCHY_CHECK_ENABLED`, `SAP_HIERARCHY_RFC`, `SAP_HIERARCHY_OK_FLAGS` |
| `backend/app/services/sap_employee.py` | New. `verify_employee_login()` (httpx; Basic auth defaults to `SAP_USER`/`SAP_PASSWD`; it tells a wrong password apart from the service being unreachable) and `check_hierarchy()` (ZINI_VERIFY; PERNR zero-padded to 8; `IV_WAERS` is sent only when it looks like a currency key) |
| `backend/app/routers/sap.py` | `GET /api/sap/employee-login`: re-checks the stored login and returns the name. `POST /api/sap/employee-login`: on success it stores the PERNR plus the encrypted password in `sap_username`/`sap_password_enc`, so the workflow's USERI/PWDI use it. `POST /api/sap/hierarchy-check`. **Park gate**: when the check is on, `park` returns 422 and `validate` returns `ok:false` if there is no hierarchy for the parking user at the gross amount sent to SAP |
| `backend/app/services/sap_connector_fake.py`, `sap_fixtures/scripted.json` | Fake `ZINI_VERIFY` and fake employees: `00009001` (ok), `00009002` (limit 100,000), `00009099` (no hierarchy), password `demo123` |
| `frontend/src/components/upload/SapEmployeeLogin.jsx` | New. An "SAP Employee Login" card on the Upload page; the upload zone appears only after sign-in. Once signed in, a green bar shows "Signed in to SAP as NAME (PERNR) · Change". When the feature is off, it passes the page through unchanged |
| `frontend/src/App.jsx` | Wraps the internal `/upload` route with that card, and turns on `checkSapHierarchy` on `/results` (the supplier portal is untouched) |
| `frontend/src/pages/ExtractionResultsPage.jsx` | `SapHierarchyBanner`: a green or red banner with the ZINI_VERIFY result for the extracted total and currency. Saving is still allowed |
| `frontend/src/services/sapService.js` | `getSAPEmployeeLogin`, `signInSAPEmployee`, `checkSAPHierarchy` |
| `frontend/src/components/common/Button.jsx` | Optional `type` prop (default unchanged) |
| `backend/test_sap_employee.py` | New, offline: **38/38 pass** (mock HTTP for the login client, fake ZINI_VERIFY, the HTTP flow, the park gate) |

The submit dialog on the invoice page already shows the dry-run message, so "No SAP approval
hierarchy for employee … (ZINI_VERIFY returned EV_FLAG '')" appears there and blocks Confirm & Park.

**Verified:** all 9 other offline suites pass. `npm run build` OK. Lint: the new code is clean; the
2 `set-state-in-effect` errors in `ExtractionResultsPage.jsx` are old.
**Not verified:** the UI was not clicked through, because this checkout has no `backend/.env`.
Nothing has been run against the real login service or the real `ZINI_VERIFY` (both need the LAN box).

**Open, to confirm with Lucky's SAP team:**
1. ~~The meaning of `EV_FLAG`~~ **Confirmed by Lucky's ABAP team (2026-11-19):** `'X'` = hierarchy
   exists, space = none. This matches the default `SAP_HIERARCHY_OK_FLAGS=X`. Their example call:
   `IV_PERNR='00001234'`, `IV_WAERS='pkr'`, `IV_AMOUNT='63764.6'`. Verity sends the currency upper-case
   and the amount with 2 decimals.
2. **The Basic-auth user for the login service.** It defaults to the RFC technical user. Set
   `SAP_LOGIN_API_USER`/`_PASSWORD` if it differs. If `sap-client` is needed, append `?sap-client=NNN` to the URL.
3. **TLS:** if the service's certificate is from an internal CA, set `SAP_LOGIN_API_CA_BUNDLE`.

**To enable on the LAN box:** `git pull`, `backend/.venv/bin/pip install -r backend/requirements.txt`,
add `SAP_EMPLOYEE_LOGIN_ENABLED=true` and `SAP_HIERARCHY_CHECK_ENABLED=true` to `backend/.env`,
then restart `./start-lan.sh`. `httpx` was added to `requirements.txt`; it was already installed as a google-genai dependency.

**Local setup note:** this checkout is `D:\TMC\VIM-Luck`, not `D:\VIM\VIM-Luck`. A fresh
`backend\.venv` was created here (`py -3 -m venv`, requirements installed). Node is at
`%LOCALAPPDATA%\Programs\nodejs`. In PowerShell, use `npm.cmd`/`npx.cmd`, because script execution is blocked.

## 2026-11-16: SAP approval workflow merged, pushed, and deployed to Cloud Run (`e157da7`)

- **Built:** `feature/sap-workflow` (`631773d`), merged into `main` as `e157da7` and pushed.
  This is the Lucky Cement SAP approval workflow: the `ZMIR7_PARK` event is raised in the same LUW
  as the park, and the outcome is read back from `ZMIR7_WF_LOG` / `ZMIR7_ERROR_LOG`. See CLAUDE.md
  "SAP approval workflow". It is **off by default** (`SAP_WORKFLOW_ENABLED=false`), so behaviour is
  unchanged until it is switched on. `test_sap_workflow.py` and the other offline suites pass.
- **Deployed to Cloud Run at the user's request,** the same way as below (`git archive` + `cloudbuild.yaml`
  restored from `b57c810^`). Build `77d4600d`. API `lucky-cement-vim-api-00007-rx2`, web
  `lucky-cement-vim-web-00009-qn2`, both on image tag `e157da7`. The rollback targets are API `00006-slx`
  and web `00008-lwm`. No env vars were changed, so the workflow is off there too.
- **Live checks:** the web returns 200 and its bundle targets the `…527930147362` API and carries the
  new "Refresh from SAP" UI. The API starts cleanly with no ERROR logs, `/api/invoices/` returns 401
  without a token, and the new `POST /api/sap/invoices/{id}/workflow/refresh` is routed (401 without a
  token). A logged-in run-through was not done.
- **Open:**
  - The LAN server is still not updated. There is no SSH access from this machine. On the box: `git pull`,
    then restart `./start-lan.sh`. No new packages are needed.
  - To switch the workflow on anywhere, set `SAP_WORKFLOW_ENABLED=true` and `SAP_WF_EVENT` (awaited from
    the ABAP team). First confirm the Z-table column names against DD03L on AUP.

## 2026-11-16: dev-shahzaib merged, pushed, and deployed to Cloud Run (`52e90b9`)

- **Merged into `main` and pushed:** `origin/dev-shahzaib` (14 commits: Inbox filters/sort,
  PO-match GRN type-ahead, per-user SAP login, submit parks straight to SAP, extraction
  tweaks) and `origin/main`'s `b57c810` (Cloud deploy machinery removed). No conflicts.
  All 6 offline suites pass, and `npm run build` is OK.
- **Deployed to Cloud Run at the user's request,** although `CONTEXT.md` §3 says the LAN server is
  now the deploy target. API `lucky-cement-vim-api-00006-slx`, web `lucky-cement-vim-web-00008-lwm`,
  both image tag `52e90b9`. The rollback targets are API `00005-qhw` and web `00007-z96`.
- **How the deploy was built:** `cloudbuild.yaml` is no longer in the repo. It was restored from
  `b57c810^` into a `git archive HEAD` export in the session scratchpad and submitted from there,
  so no local `.env` or `node_modules` was uploaded.
- **gcloud on this machine:** a portable CLI at
  `%LOCALAPPDATA%\Programs\google-cloud-sdk` (user PATH), signed in as shahzaib.moin@.
- **Live checks:** the portal loads, its bundle targets the `…527930147362.us-central1.run.app`
  API, the API answers 401 without a token, and CORS passes. A logged-in run-through was not done.
- **Open:**
  - The LAN server has not been updated. Its address is unknown here, and `192.168.15.10`
    (from `CORS_ORIGINS`) did not answer on 22/8000/5173 from this network. On that box run
    `git pull`, `backend/.venv/bin/pip install -r backend/requirements.txt` (the new
    `cryptography` dependency), then restart `./start-lan.sh`.
  - `SAP_CRED_KEY` is unset on both. Set it before users save per-user SAP passwords.
  - A key `~/.ssh/vim_luck_lan` was generated for LAN access. Its public half was not
    installed anywhere yet.

## 2026-11-05: "View" showed nothing in the local preview (committed `34472b5`, NOT pushed or deployed)

**Push and deploy are blocked by the network here.** The office firewall (a Fortinet FortiGate,
`CN=FG4H1FT923900717`) inspects HTTPS and re-signs certificates with its own CA, which Windows does
not trust. As a result, `git push` and every `gcloud` call fail with `SEC_E_UNTRUSTED_ROOT`. Run
these from a network without that inspection, or after IT trusts the Fortinet CA or exempts
`github.com` and `*.googleapis.com`. Do not turn off certificate checks.

1. `git push origin main`
2. `gcloud builds submit --config=cloudbuild.yaml --project=tmc-presales-pocs --substitutions=_TAG=34472b5`
3. `gcloud run deploy lucky-cement-vim-web --image=us-central1-docker.pkg.dev/tmc-presales-pocs/presales-lucky-cement-vim/lucky-cement-vim-web:34472b5 --region=us-central1 --project=tmc-presales-pocs`

Only the web service changes; the API image is unchanged. The rollback target is
`lucky-cement-vim-web-00006-jcj`.

**Cause:** the Claude app's preview pane blocks new tabs, so `window.open` returned `null` and
"View" fell back to a download, which the pane never shows. Any browser that blocks the popup
behaved the same way: View quietly turned into a download.

**Fix:** when the new tab is blocked, View now opens the file in a viewer on the page instead.
Normal browsers still get the new tab, and Download is unchanged.

| File | Change |
|---|---|
| `frontend/src/components/common/DocumentViewer.jsx` | New. Built on the existing `Modal`: PDF in an `<iframe>`, JPEG/PNG as `<img>`, anything else (TIFF) a "can't be shown" note; Close and Download buttons; Esc closes; the object URL is freed on close |
| `frontend/src/utils/invoiceDocument.js` | `showOrSaveBlob` split into `saveBlob` (download) and `viewBlob` (new tab, else sends the `einv:view-document` event the viewer listens for) |
| `frontend/src/App.jsx` | Mounts `<DocumentViewer />` once for the internal portal |
| `frontend/src/pages/ExtractionResultsPage.jsx` | Review-page "View File" uses `viewBlob` |

**Verified in the pane** (`localhost:5173`, admin, invoice #1):
- Detail-page View shows the PDF in the viewer (screenshot). The viewer's Download saves `INV-DOC-0001.pdf`.
- Close removes the viewer and frees the URL. Esc closes too.
- Inbox-row View opens the viewer without opening the row.
- A PNG renders, and a TIFF shows the note.
- With a stubbed popup that is allowed, View still goes to the new tab.
- `npm run build` OK. The new files lint clean; the 2 lint errors in `ExtractionResultsPage.jsx` are old.

**Not covered:** the supplier portal has no viewer mounted. It has no View button today.

**Correction to the note below:** the pane does render PDFs inside an `<iframe>`. It only blocks
new tabs and top-level `blob:` navigation.

**Also why a file can be missing locally:** invoice #2 (`LOCAL-SUP-0001`) has no stored file
(`po-flip`), so it shows "—". New local uploads fail until `GEMINI_API_KEY` is set in `backend\.env`.

## Pulled 2026-11-04: supplier demo OTP moved into the database

`git pull --ff-only --autostash` brought in `9ae16b0` (supplier demo OTP now lives in the
`app_settings` table and is set under **Admin → Suppliers**) and `61d06b2` (`start-lan.sh`).
The uncommitted View/Download work below re-applied cleanly. After the pull, all 6 offline
suites still pass.

- **Local `.env` fixed:** the new config rejects unknown keys, so the old `SUPPLIER_DEMO_OTP=`
  line made the backend fail at startup. It is now **commented out**, keeping its old value in
  the comment. A copy of the pre-pull `.env` is in the session scratchpad only.
- **Local supplier login needs the OTP set once:** `app_settings` is empty, so sign in as admin
  and set it under Admin → Suppliers.
- **On the next deploy:** the cloud DB has no OTP row either, so **supplier login on the demo
  stops working until an admin sets it** there. The `SUPPLIER_DEMO_OTP` env var on
  `lucky-cement-vim-api` is ignored by the new code; it does no harm but could be removed later.
- Local AI extraction still needs `GEMINI_API_KEY` in `backend\.env` (it is empty).

## Latest: invoice document View / Download (client requirement, 2026-11-04)

**Requirement (from the client):** after a user uploads an invoice, they can view and
download that file. **Status: DEPLOYED 2026-11-04** (commit `88504a1`, images `:33e20f0`).

| Deploy record | |
|---|---|
| Bucket | `gs://lucky-cement-vim-uploads` (us-central1, uniform access, public access prevention). `lucky-cement-vim-sa` has `roles/storage.objectUser` on it |
| Cloud Build | `51c22ee0-8b72-4121-89fd-ebc07c721e6d`, SUCCESS in 1m27s |
| API | `lucky-cement-vim-api-00002-wrv`, 100%. Cloud Storage volume `uploads` mounted at `/mnt/uploads`, `UPLOAD_DIR=/mnt/uploads`. Default (gen1) execution environment worked; the log shows "File system has been successfully mounted." |
| Web | `lucky-cement-vim-web-00003-m2m`, 100% |
| Rollback | `gcloud run services update-traffic lucky-cement-vim-api --to-revisions=lucky-cement-vim-api-00001-x8n=100 --region=us-central1 --project=tmc-presales-pocs` and the same for `lucky-cement-vim-web` with `lucky-cement-vim-web-00002-tfv` |
| Verified from outside | `/health` 200; `GET /api/invoices/1/document` with no token → 401; route listed in `/openapi.json`; buttons present in the live bundle |
| **Not yet verified** | A real upload → View/Download on the live site (needs a login), and the file appearing in the bucket: `gcloud storage ls gs://lucky-cement-vim-uploads` |
| Side effects | The pulled OTP change is live too: **supplier login fails until an admin sets the OTP under Admin → Suppliers**. As with every new API revision, the fixture SAP store reset |

Before this, the original upload was saved (`Invoice.stored_filepath`) but nothing served
it: the detail page only showed the file name as text. (Supporting documents already had
their own download in `AttachmentsCard` / `routers/attachments.py`.)

| File | Change |
|---|---|
| `backend/app/services/file_storage.py` | `resolve_stored_file()`: only names `save_uploaded_file()` generates (32 hex chars + extension), looked up inside `UPLOAD_DIR`. `sniff_inline_type()`: type from the file's bytes |
| `backend/app/routers/invoices.py` | `GET /api/invoices/{id}/document` (inline; `?download=true` = attachment), `nosniff`, `no-store`; `document_available` in the detail response |
| `backend/app/schemas/invoice.py` | `document_available: bool` on `InvoiceDetailResponse` |
| `frontend/src/services/invoiceService.js` | `fetchInvoiceDocument()`: fetches as a Blob with the normal auth header (no `?token=` in URLs) |
| `frontend/src/pages/InvoiceDetailPage.jsx` | "View · Download" after the file name in the header, shown only when `document_available`. Errors go to the existing action-error banner. The supplier portal reuses this page |
| `backend/test_invoice_document.py` | New, offline, own temp DB + upload folder: **39/39 pass** |

**Follow-up: "View File" on the review page** (`/results`, and `/supplier/upload/review`, which
uses the same `ExtractionResultsPage.jsx`). A button next to "Raw Output" opens the uploaded file
from browser memory (`URL.createObjectURL` on the dropped `File`), with no server request, so users can
check the extracted fields against the document before saving. It is hidden for email-inbox
reviews, which only carry a `{name, size}` stand-in. If a popup is blocked, it opens in the in-page
viewer (2026-11-05; it used to download instead).
Checked in the pane with a stubbed upload response (the local Gemini key is empty): the button
renders, and the click opens a `blob:` URL holding the exact PDF. Lint and build unchanged.

**Follow-up 2: Invoice Inbox rows** (internal `InvoiceListPage.jsx`):
- Clicking anywhere on a row opens the invoice. This is skipped while text is selected, so an
  invoice number can still be copied.
- A new **Document** column shows "View · Download", or "—" when there is no file. The two
  buttons stop the click from also opening the row.
- The list API now sets `document_available` per row. `stored_files_available()` checks a page
  of rows with 8 threads, inside `asyncio.to_thread`: on Cloud Run each check is a Cloud Storage
  metadata call, and the event loop must not wait on it. Rows without a valid stored name (e.g.
  PO-flip) skip the check.
- View/Download logic now lives in one helper, `frontend/src/utils/invoiceDocument.js`, used by
  the inbox, the detail page and the review page.
- `test_invoice_document.py` has 7 more list checks (46 total, all pass). Verified in the pane:
  the column renders; View and Download fetch 200 without opening the row; a cell click opens
  `/invoices/1`; the detail-page and review-page links still work.
- **Eye icon removed** (client request, after the deploy below): the last "View invoice" column
  is gone, since the row click does the same. The `#id` link is now a real `<button>`, so an
  invoice can still be opened from the keyboard (Tab, then Enter: checked). **Deployed**: build
  `9dc785b9`, web `lucky-cement-vim-web-00005-thp` (`:845cbd2`); rollback target `00004-j5s`.
  The API was not redeployed.
- **Eye icons also removed from Reports and the supplier My Invoices list** (client request), the
  same way: the row opens the invoice (skipped while text is selected), and `#id` is a real
  button. Reports uses `DataTable`'s `onRowClick`, and `HistoryView` in `SupplierPortal.jsx` got a
  row `onClick`. Verified locally: on both screens, a cell click and Enter on `#id` open the
  invoice, and no eye icon is left.
  - **Local test data added for this check:** supplier "LOCAL TEST Supplier (delete me)"
    (mobile `03009990001`) and its draft invoice #2 `LOCAL-SUP-0001` in `backend\invoices.db`.
  - **Deployed 2026-11-05:** build `3bc3db83-f4ed-4e70-a3aa-e943935c8df2`, web
    `lucky-cement-vim-web-00006-jcj` (`:b08b75d`); rollback target `00005-thp`. The live bundles of
    both portals contain no eye buttons.
- **gcloud sign-in expires (seen 2026-11-05):** commands then stop at "Reauthentication required.
  Please enter your password". The browser flow (`gcloud auth login --force`) did not hand the
  login back on this machine. What worked: `gcloud auth login --force --no-launch-browser`; open
  the printed link, approve, and paste the verification code into **that terminal** (not the chat).
- **Not covered:** the supplier portal's own list (`HistoryView` in `SupplierPortal.jsx`) is a
  separate component and does not have the column.
- **Deployed 2026-11-04** together with the review-page View File (images `:74ad257`, build
  `1aa8dafe-8222-4026-a197-bf7830014c2f`):
  - API `lucky-cement-vim-api-00003-8kn`. This was an image-only deploy, and the bucket mount at
    `/mnt/uploads` was kept (checked with `describe`).
  - Web `lucky-cement-vim-web-00004-j5s`.
  - Live checks: `/health` 200; list and document routes return 401 without a token;
    `document_available` is in `/openapi.json`; all three UI pieces are in the live bundle.
  - Rollback targets: API `lucky-cement-vim-api-00002-wrv`, web `lucky-cement-vim-web-00003-m2m`.

**Why the path guard matters:** `/api/invoices/save` stores whatever `stored_filepath` the
client sends. Without the guard, any logged-in user (a supplier included) could point an
invoice at `/proc/self/environ` (the DB URL and API keys live in env vars on Cloud Run) and download it.
The test covers absolute paths, `../`, backslashes, the DB file, `/proc/self/environ`,
`po-flip`, missing files, HTML bytes behind a `.pdf` name, supplier A vs B, and no token (401).

**Checked locally:** the existing 5 offline suites still pass; `npm run build` OK; lint
unchanged (20 old errors, 0 new). In the app: the buttons render and `GET …/document` returns
the exact PDF (`application/pdf`). The Claude browser pane blocks new tabs and won't render
PDFs, so the "View" tab itself was not seen. Check it in Chrome/Edge. The supplier portal
was covered by the test, not clicked through.

**Local test data left behind:** invoice #1 `INV-DOC-0001` (draft) in `backend\invoices.db`,
and its PDF in `backend\uploads\`. Delete it in the app if unwanted.

**Server storage: Cloud Storage bucket (done, see the deploy record above).** Uploads used to go
to the API container's disk, which Cloud Run wipes on every restart or new revision. The steps
that were run:
1. Create a private bucket, e.g. `lucky-cement-vim-uploads` (us-central1, uniform access, public access prevention).
2. Grant `lucky-cement-vim-sa@tmc-presales-pocs.iam.gserviceaccount.com` `roles/storage.objectUser` on it.
3. Commit, build with `cloudbuild.yaml`, deploy **both** services. The API deploy adds a Cloud Storage
   volume mounted at `/mnt/uploads` and sets `UPLOAD_DIR=/mnt/uploads` (may need `--execution-environment=gen2`).
Files uploaded before this are already gone from the server, so older invoices will show no View/Download.

## 0. Session 2 — 2026-11-04 (onboarding review: run, test, risk scan)

No new code was written. The Analytics title fix from session 1 was committed, pushed
and deployed to **this repo's own server** (decision: `lucky-cement-vim-web`, not
vim-internal-web):

| | |
|---|---|
| Commits on `origin/main` | `a5ddde0` title fix, `205c020` this handover (author `ai.engineers1`, set for these commits only; this machine has **no git identity configured**) |
| Cloud Build | `1efb4b6d-6808-4689-b994-004a6c957e81`, SUCCESS in 1m8s. Both images pushed as `:205c020` |
| Rolled out | **web only**: `lucky-cement-vim-web` revision `lucky-cement-vim-web-00002-tfv`, 100% traffic. The backend `lucky-cement-vim-api` was **not** redeployed (no backend change) |
| Rollback | `gcloud run services update-traffic lucky-cement-vim-web --to-revisions=lucky-cement-vim-web-00001-4q6=100 --region=us-central1 --project=tmc-presales-pocs` (previous image `:9f3c063`) |
| Verified | Portal and `/supplier/dashboard` return 200; login page renders, no console errors; live bundle bakes in the `lucky-cement-vim-api-527930147362` URL; "Analytics & Insights" appears once in the bundle (top-bar title only). The signed-in Analytics page was **not** viewed on the live site (needs a real login) |
| Note | The first `/health` call returned 500: Cloud Run said "aborted after waiting too long for an available instance". That was the single API instance cold-starting; the next calls returned 200. Expect it on the first hit after idle |

**"I don't see any changes on Server" (raised after the deploy).** The fix is live on
`lucky-cement-vim-web` (index.html last-modified 2026-11-04 11:33 GMT, `cache-control: no-cache`,
no duplicate `<h2>` in the bundle). **vim-internal-web is untouched**: its index.html is from
2026-10-05 and its bundle still has the duplicate `<h2>`. A fix there is blocked on two things:
- **Source:** there's no local clone, and `awaisali-TMC/VIM-Demo` (the likely source: same
  "TMC eInvoice" brand and the same 2026-10-05 date as `DEMO` @ `ec9d7f3`) returns "Repository
  not found" with this machine's GitHub credentials.
- **GCP:** `shahzaib.moin@tmcltd.com` has no permission on project `297345409494`.
Deploying *this* repo there is still not recommended: it would replace that app with Lucky
Cement code and branding.

**gcloud on this machine:** Google Cloud SDK 592.0.0, unpacked (no admin) to
`%LOCALAPPDATA%\Programs\google-cloud-sdk`. It is **not on PATH**, so call
`& "$env:LOCALAPPDATA\Programs\google-cloud-sdk\bin\gcloud.cmd" …`. It is signed in as
`shahzaib.moin@tmcltd.com`. Six symlinked gsutil docs/test-cert files could not be unpacked
(Windows symlink rights); gcloud doesn't use them. Claude Code's own shell does **not** see
this login (it reports "No credentialed accounts"), so run gcloud from the app's Terminal
panel or your own PowerShell.

**Upload check:** the repo root has no `.gcloudignore`, so `gcloud builds submit` falls back
to `.gitignore`. `gcloud meta list-files-for-upload .` lists 322 files, with no `.env`,
database, venv, `node_modules`, uploads or credentials sheet among them. Re-run it if the
ignore files change.

**What was checked (all on this laptop, against the local SQLite DB):**

| Check | Result |
|---|---|
| Toolchain | Python 3.12.10 venv, `pip check` clean; Node 24.22.1; npm deps installed |
| Backend | Starts on :8000 via `.claude\launch.json`. Smoke test: `/health`, internal login, `/me`, `/api/sap/test` (fixture SAP, `RFCSYSID=FAK`), invoices, POs, analytics overview, 90-day volume trend (works on SQLite only, see §4 #1), workflow templates, roles: all 200 |
| Frontend | Starts on :5173. Internal portal renders Analytics with one title and no console errors |
| Offline tests | `test_sap_fake`, `test_line_item_guards`, `test_po_flip`, `test_supplier_vendor_gate`, `test_role_labels`: **all PASS** |
| Live-SAP tests | Not run (`test_po_regression.py`, `test_sap*.py`): there is no SAP system for this instance |
| `npm run build` | **OK.** Warning only: `main` (620 kB) and `supplierService` (523 kB) chunks are over 500 kB |
| `npm run lint` | **20 errors, 5 warnings, all pre-existing, none break the build**: unused vars (ApprovalProgressCard, CreditDebitNoteCard, GLCodingCard, InvoiceClassificationCard, POCreatePage, POListPage, SupplierNotificationsPage), React-compiler `set-state-in-effect` (AuditTrailCard, DuplicateWarningCard, LineItemsTable, AdminEmailInboxPage, ExtractionResultsPage), and `__dirname` in `vite.config.js` (false positive: the ESLint config has no Node globals for that file; Vite shims it) |

**Running the offline tests safely.** Four of the five scripts write rows into
`./invoices.db` in the *current directory*. Run them from a scratch copy so the dev DB
stays clean (they find `app/` themselves; `.env` and the DB are read from the cwd):

```powershell
$s = "$env:TEMP\vim-testrun"; New-Item -ItemType Directory -Force $s | Out-Null
Copy-Item D:\VIM\VIM-Luck\backend\.env, D:\VIM\VIM-Luck\backend\invoices.db $s
cd $s
foreach ($t in "test_sap_fake","test_line_item_guards","test_po_flip","test_supplier_vendor_gate","test_role_labels") { D:\VIM\VIM-Luck\backend\.venv\Scripts\python.exe -X utf8 "D:\VIM\VIM-Luck\backend\$t.py" }
Remove-Item -Recurse -Force $s   # the copy holds the local .env
```

Frontend: `cd D:\VIM\VIM-Luck\frontend; npm run lint; npm run build`.

**New finding: broken access control (most important open issue).**
Proved on a scratch DB copy with a faked supplier principal (same technique as the
existing tests):

- A **supplier** token can `PUT /api/workflow-templates/{id}` with `is_active=0`, which returns 200.
  With no active template, `workflow_engine.py:115` skips approval, so invoices go
  straight to parking. The supplier can also `POST /api/tax-rules` (200) and read
  `/api/audit-logs` and `/api/analytics/*` (200).
- Cause: `workflows.py`, `tax_rules.py`, `gl_accounts.py`, `audit.py` and `analytics.py` are
  mounted with `auth_dep` (internal user **or** supplier) and have no per-route role
  check. Any internal role, `auditor` included, can also change them. The admin pages are
  hidden in the UI, but the API does not enforce it.
- Other `auth_dep` routers (purchase_orders, po_matching, products, currency, fbr,
  comments, agent_invoices) were **not** audited route by route.

**AI / performance risks found in code (not changed):**

- Gemini is called **synchronously inside `async` handlers** (`routers/invoices.py`
  ~448, 463, 519, 582; `routers/inbox.py` ~241). Each extraction blocks the event loop
  for its full duration, and the API is capped at one Cloud Run instance, so one upload
  stalls every other user's requests. `po_flip.py` already uses `anyio.to_thread.run_sync`.
- No explicit request timeout on the Gemini client, and no token-usage logging
  (`usage_metadata` is never read). Cost per invoice cannot be measured.
- `gemini_extract.py` copies one model-reported `overall_confidence` onto **every** field,
  so the per-field confidence in the UI is not per-field.
- Prompts are unversioned module constants, the model id and prompt version are not stored
  with the extraction, and there is no extraction eval set.

## 1. Local environment (set up, working)

| | |
|---|---|
| Python | 3.12.10, installed by winget for this user (`%LOCALAPPDATA%\Programs\Python\Python312`). `py -3` may not be on PATH in old terminals |
| Node.js | 24.22.1 **portable** build at `%LOCALAPPDATA%\Programs\node-v24.22.1-win-x64`, added to user PATH (the MSI needed admin and was cancelled) |
| Backend venv | `backend\.venv`, `requirements.txt` installed |
| Backend config | `backend\.env`, copied from `.env.example`, then: `SAP_ENABLED=true`, `SAP_MODE=fake`, `INITIAL_ADMIN_PASSWORD` and `SUPPLIER_DEMO_OTP` set to local test values (read them from that file). `GEMINI_API_KEY` is **empty**, so AI extraction fails until it is filled in |
| Database | SQLite `backend\invoices.db`: 34 tables, seeded (1 admin user, 8 roles, 15 GL accounts, 10 tax rules, 500 products, default workflow). No invoices, no ATL rows |
| Frontend | `frontend\node_modules` installed |
| Launch config | `.claude\launch.json` with `backend` (:8000) and `frontend` (:5173) entries |

All of the above is git-ignored except `.claude\launch.json`.

Run by hand (two terminals):

```powershell
cd D:\VIM\VIM-Luck\backend; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload
cd D:\VIM\VIM-Luck\frontend; npm run dev
```

- Internal portal http://localhost:5173 (login `admin@tmcltd.com`), supplier portal http://localhost:5173/supplier/
- Check the fixture SAP is active: `GET /api/sap/test` returns `"mode": "fake"` (needs a login token)
- View the DB: VS Code "SQLite Viewer" extension on `backend\invoices.db` (read-only)

## 2. Code change (uncommitted)

**Duplicate "Analytics & Insights" title**: fixed in `frontend/src/pages/AnalyticsDashboard.jsx`.
The title showed twice because `components/layout/Layout.jsx` already renders the page
title in the top bar, and the page added its own `<h2>`. The `<h2>` is removed and the
7D/30D/90D selector is right-aligned. Verified locally: one heading. This is the
**only** change in the working tree. It is not committed and not deployed.

## 3. Deploy: resolved in session 2 (deployed to `lucky-cement-vim-web`, see §0)

Session 1's notes, kept for the record:

- The user asked to deploy to **https://vim-internal-web-297345409494.asia-south1.run.app/**.
  That is **not** this repo's instance. Inspecting its live bundle showed: brand "TMC eInvoice",
  backend `https://vim-internal-297345409494.asia-south1.run.app`, GCP project number
  `297345409494`. This repo deploys to `lucky-cement-vim-web` in `tmc-presales-pocs`
  (us-central1). Deploying this repo there would replace that app with Lucky Cement code
  and branding, and the backend URL is baked in at build time. It would also break the
  "repo isolation" rule in `CLAUDE.md`.
- **Recommended:** apply the same 3-line fix in vim-internal-web's own source repo (path or
  GitHub name still unknown) and deploy from there.
- **Alternative:** deploy to this repo's own server (`CONTEXT.md` §3). Only the frontend
  changed, so only `lucky-cement-vim-web` needs a rollout.
- **gcloud is not installed.** The winget user-scope install has no installer; the machine-wide
  install was interrupted, and nothing was installed. Deploying needs gcloud plus
  `gcloud auth login` by someone with access to the target project.

## 4. Other Analytics defects found (fixed, then reverted at the user's request)

Not applied; listed so they can be picked up later.

1. **The 90D button breaks the dashboard on Postgres (cloud).** `routers/analytics.py` `volume-trend` uses
   SQLite-only `strftime` for week/month grouping, so it fails. The page loads all its data in one
   `Promise.all`, so one failure leaves every card at 0. `AuditorDashboard` calls week grouping too.
   Fix: `to_char` on Postgres with the format as `literal_column(...)`. A bound parameter
   makes SELECT and GROUP BY different expressions under asyncpg.
2. **Suppliers can read `/api/analytics/*`.** The router is mounted with `auth_dep`, which accepts suppliers,
   so a supplier token sees all suppliers' names and totals. Fix: mount with
   `Depends(get_current_internal_user)`. The mobile app logs in as an internal user, so it is unaffected.
3. **Straight-through rate ignores `parked`.** It counts approved + posted only, but parked is the normal
   end state here.
4. **Status bar colours don't match their badges.** Processing's bar is amber but its badge is purple, so it
   looks like Parked.
5. **Volume trend labels use the full series** while only the last 30 bars are drawn.
6. **Load errors are swallowed** (`console.error` only), so a failure looks like "no data".
7. **Intake Sources labels every non-email source "Upload".** Supplier, po_flip and the rest are mislabelled.
8. **`fmt()` doesn't shorten negative amounts** (credit notes).

Not attempted: "Total Value" sums mixed currencies under a PKR label; Badge gives `parked` and
`pending_approval` the same amber; the KPI grid isn't responsive.

## 5. Next steps (updated in session 2, priority order)

1. **Close the access-control hole (§0).** Gate mutations in `workflows.py`, `tax_rules.py`
   and `gl_accounts.py` with `require_admin` (or the right `require_roles`). Mount `audit.py`
   and `analytics.py` behind `get_current_internal_user` (this also fixes §4 #2). Add a
   standalone test, in the style of `test_supplier_vendor_gate.py`, that expects 403 for a
   supplier. Then audit the remaining `auth_dep` routers route by route.
2. **Take Gemini off the event loop.** Wrap `extract_invoice` / `segment_invoice_pages`
   calls in `anyio.to_thread.run_sync`, set an explicit client timeout, and log
   `usage_metadata` token counts per call.
3. **Fix the 90D analytics on Postgres** (§4 #1): the cloud dashboard shows all zeros.
4. **Title fix: done** for `lucky-cement-vim-web` (§0). If vim-internal-web needs the same
   fix, it has to go in that app's own repo (location still unknown).
   Optionally view the signed-in Analytics page on the live site to confirm by eye.
5. **Extraction quality baseline.** Build a small golden set from `generate_demo_invoices.py`
   PDFs, and store the model id and prompt version with each extraction.

Lower priority: the remaining §4 items, lint cleanup, and code-splitting the two large chunks.
