"""Fixture-backed SAPConnector — local demos and offline tests. NEVER production.

Drop-in replacement for `SAPConnector`: same six-method surface, same response
contract, no NW RFC SDK, no network, no SAP. `sap_connector.py` swaps it in under
the real name when SAP_MODE=fake and DEBUG is on, so every caller
(`sap_po_service`, `sap_invoice_post`, `routers/sap.py`, …) is untouched.

WHY A SQLITE STORE RATHER THAN CANNED RESPONSES
-----------------------------------------------
`RFC_READ_TABLE` reaches 16 of the 19 SAP tables this app reads, and the WHERE
clause the callers build is *already* valid SQL:

    EBELN = '4500009001' AND LOEKZ = ''
    LIFNR = '0002000101' OR LIFNR = '0002000102'
    NAME1 LIKE 'HAIER%'
    BEDAT >= '20260101' AND BEDAT <= '20261231'

SQLite understands all of it verbatim — `LIKE`/`%` behave identically, and SAP
dates are YYYYMMDD strings so range comparisons are plain string comparisons. So
the fixtures are a database whose tables carry SAP's real names, and the engine is
one SELECT instead of a hand-rolled predicate evaluator.

It also lets the fake hold state: parking INSERTs into RBKP, so a later unpark
finds the document, and BAPI_TRANSACTION_ROLLBACK genuinely discards — which makes
`mode="validate"` non-mutating here exactly as it is against real SAP.

ON INTERPOLATING THE WHERE CLAUSE
---------------------------------
The clause cannot be parameterised — it arrives as one opaque string. Two things
contain the blast radius: every table and column name is validated against the
schema before the query is built, and `Cursor.execute()` refuses more than one
statement, so nothing can be chained onto the SELECT. Worth knowing that the same
interpolation reaches *real* SAP on the live path (`sap_po_service.lookup_vendor`
puts a Gemini-extracted supplier name straight into the clause) — a pre-existing
issue there, not one this module introduces.
"""

import json
import logging
import sqlite3
import threading
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

if not settings.DEBUG:
    # Second, independent gate. sap_connector.py already refuses to import this
    # module unless DEBUG is on; this makes it true even if someone imports it
    # directly. A fake connector in production would report parking successes
    # for invoices that were never sent anywhere.
    raise RuntimeError(
        "sap_connector_fake is a demo/test facility and must not load with DEBUG=False."
    )

_FIXTURES = Path(__file__).parent / "sap_fixtures"

_conn: sqlite3.Connection | None = None
_columns: dict[str, list[str]] | None = None
_scripted: dict | None = None
_lock = threading.Lock()


# ── store ────────────────────────────────────────────────────────────────────

def _store() -> sqlite3.Connection:
    """The fixture database, opened on first use and kept for the process.

    Module-level rather than per-instance so documents parked through one
    connector are visible to the next one — callers construct a fresh
    SAPConnector per request.

    In memory by default, so every run starts from the same fixtures. Set
    SAP_FAKE_DB_PATH to put it in a file instead: then you can open it in any
    SQLite browser while the app is running and see what was actually parked,
    and it survives a restart.
    """
    global _conn, _columns
    if _conn is not None:
        return _conn
    with _lock:
        if _conn is not None:  # another thread won the race
            return _conn

        path = (settings.SAP_FAKE_DB_PATH or "").strip()
        target = str(Path(path).expanduser().resolve()) if path else ":memory:"
        if path:
            Path(target).parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(target, check_same_thread=False)
        conn.row_factory = sqlite3.Row

        # Seed only an empty database, so a file-backed store keeps whatever a
        # previous run parked instead of being wiped on every boot.
        seeded = conn.execute(
            "SELECT count(*) AS n FROM sqlite_master WHERE type = 'table' AND name = 'EKKO'"
        ).fetchone()["n"]
        if not seeded:
            conn.executescript((_FIXTURES / "schema.sql").read_text(encoding="utf-8"))
            conn.executescript((_FIXTURES / "data.sql").read_text(encoding="utf-8"))
            conn.commit()

        _columns = {
            t: [c["name"] for c in conn.execute(f"PRAGMA table_info({t})")]
            for t in (r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"))
        }
        _conn = conn
        logger.warning(
            "FAKE SAP connector active — %d fixture tables at %s, %s. No real SAP "
            "system is being contacted.",
            len(_columns), target, "seeded" if not seeded else "existing data kept")
        return _conn


def _scripts() -> dict:
    global _scripted
    if _scripted is None:
        _scripted = json.loads((_FIXTURES / "scripted.json").read_text(encoding="utf-8"))
    return _scripted


def reset_store() -> None:
    """Drop the in-memory database so the next call rebuilds it. Tests only."""
    global _conn, _columns, _scripted
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = None
        _columns = None
        _scripted = None


# ── helpers ──────────────────────────────────────────────────────────────────

def _s(v) -> str:
    """Every SAP scalar is a string. None would crash callers that .strip() it."""
    return "" if v is None else str(v)


def _shape(tables: dict, params: dict, structures: dict, kwargs: dict) -> dict:
    """Return only what the caller asked for, keyed exactly as it asked.

    Mirrors the real connector: names absent from `tables` / `output_params` /
    `output_structures` do not appear in the result, and a requested table that
    was not produced comes back as [] rather than raising.
    """
    out: dict = {}
    for name in kwargs.get("tables") or []:
        rows = tables.get(name, [])
        wanted = (kwargs.get("table_fields") or {}).get(name)
        out[name] = ([{f: _s(r.get(f)) for f in wanted} for r in rows]
                     if wanted else [dict(r) for r in rows])
    for name in kwargs.get("output_params") or []:
        out[name] = _s(params.get(name))
    for name, fields in (kwargs.get("output_structures") or {}).items():
        src = structures.get(name) or {}
        out[name] = {f: _s(src.get(f)) for f in fields}
    return out


def _msg(type_, id_, number, message, v1="", v2="") -> dict:
    return {"TYPE": type_, "ID": id_, "NUMBER": number, "MESSAGE": message,
            "MESSAGE_V1": v1, "MESSAGE_V2": v2}


# ── connector ────────────────────────────────────────────────────────────────

class SAPConnectorFake:
    """Same surface as SAPConnector. __init__ deliberately touches no SDK."""

    def __init__(self, dll_directory: str = None):
        # Accepted and ignored — the real connector raises FileNotFoundError here
        # when sapnwrfc.dll is absent, which is the whole problem this solves.
        self.dll_directory = dll_directory
        self._connected = False

    # -- lifecycle --

    def connect(self):
        _store()
        self._connected = True
        return True

    def disconnect(self):
        # The store outlives the connector on purpose; only the flag resets.
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    def ping(self) -> bool:
        return True

    def get_system_info(self) -> dict:
        return dict(_scripts()["system_info"])

    # -- dispatch --

    def call(self, function_name: str, **kwargs) -> dict:
        if not self._connected:
            self.connect()

        handler = {
            "RFC_READ_TABLE": self._read_table,
            "RFC_PING": lambda kw: {},
            "RFC_SYSTEM_INFO": self._system_info,
            "BAPI_INCOMINGINVOICE_PARK": lambda kw: self._invoice(kw, post=False),
            "BAPI_INCOMINGINVOICE_CREATE1": lambda kw: self._invoice(kw, post=True),
            "BAPI_INCOMINGINVOICE_DELETE": self._invoice_delete,
            "BAPI_TRANSACTION_COMMIT": self._commit,
            "BAPI_TRANSACTION_ROLLBACK": self._rollback,
            "BAPI_EXCHANGERATE_CREATEMULTIPLE": self._exchange_rate,
            "BAPI_EXCHANGERATE_CREATE": self._exchange_rate,
        }.get(function_name)

        if handler is None:
            # Text matters: routers/sap.py:168 sniffs for "GetFunctionDesc" to
            # decide whether to fall back to an older exchange-rate BAPI.
            raise RuntimeError(
                f"GetFunctionDesc({function_name}) failed: FUNCTION_NOT_FOUND — "
                f"the fake SAP connector implements no handler for it."
            )
        return handler(kwargs)

    # -- handlers --

    def _system_info(self, kwargs) -> dict:
        return _shape({}, {}, {"RFCSI_EXPORT": _scripts()["system_info"]}, kwargs)

    def _read_table(self, kwargs) -> dict:
        table = (kwargs.get("QUERY_TABLE") or "").strip().upper()
        delimiter = kwargs.get("DELIMITER") or "|"
        input_tables = kwargs.get("input_tables") or {}
        options = input_tables.get("OPTIONS") or []
        fields_in = input_tables.get("FIELDS") or []

        _store()
        if table not in (_columns or {}):
            raise RuntimeError(
                f"RFC_READ_TABLE: table {table!r} has no fixture. Add it to "
                f"sap_fixtures/schema.sql — returning an empty table here would be "
                f"indistinguishable from 'SAP has no such row'."
            )
        known = _columns[table]

        names = [(f.get("FIELDNAME") or "").strip().upper() for f in fields_in]
        names = [n for n in names if n] or list(known)
        unknown = [n for n in names if n not in known]
        if unknown:
            raise RuntimeError(
                f"RFC_READ_TABLE({table}): no such column(s) {unknown} in the "
                f"fixture schema. Known: {known}"
            )

        # Plain concatenation, no separator. The callers split long predicates
        # across ≲72-char rows with the trailing spaces already baked in; joining
        # with anything would corrupt "LIFNR = 'x' " + "OR LIFNR = 'y' ".
        where = "".join((r.get("TEXT") or "") for r in options).strip()

        sql = f'SELECT {", ".join(names)} FROM {table}'
        if where:
            sql += f" WHERE {where}"
        limit = _rowcount(kwargs.get("ROWCOUNT"))
        if limit:
            sql += f" LIMIT {limit}"

        try:
            rows = _store().execute(sql).fetchall()
        except sqlite3.Error as e:
            raise RuntimeError(
                f"RFC_READ_TABLE({table}) could not run: {e}. WHERE was: {where!r}"
            ) from e

        # FIELDS is echoed back because _parse_delimited_rows() positionally zips
        # it against the '|'-split WA string — the order here defines the columns.
        produced = {
            "DATA": [{"WA": delimiter.join(_s(r[n]) for n in names)} for r in rows],
            "FIELDS": [{"FIELDNAME": n, "OFFSET": "", "LENGTH": "",
                        "TYPE": "C", "FIELDTEXT": n} for n in names],
        }
        return _shape(produced, {}, {}, kwargs)

    def _invoice(self, kwargs, post: bool) -> dict:
        header = (kwargs.get("input_structures") or {}).get("HEADERDATA") or {}
        items = (kwargs.get("input_tables") or {}).get("ITEMDATA") or []

        errors = self._invoice_errors(header, items)
        if errors:
            return _shape({"RETURN": errors},
                          {"INVOICEDOCNUMBER": "", "FISCALYEAR": ""}, {}, kwargs)

        conn = _store()
        doc = self._next_document_number(conn)
        year = (header.get("PSTNG_DATE") or "")[:4] or "2026"
        # No commit — sap_invoice_post calls BAPI_TRANSACTION_COMMIT on success and
        # BAPI_TRANSACTION_ROLLBACK for mode="validate", exactly as against real SAP.
        conn.execute("INSERT INTO RBKP (BELNR, GJAHR, RBSTAT) VALUES (?, ?, ?)",
                     (doc, year, "5" if post else "A"))

        verb = "posted" if post else "parked"
        return _shape(
            {"RETURN": [_msg("S", "M8", "060", f"Document no. {doc} {verb}", doc)]},
            {"INVOICEDOCNUMBER": doc, "FISCALYEAR": year}, {}, kwargs)

    def _invoice_errors(self, header: dict, items: list) -> list:
        """Scripted failures first, then one honest structural check."""
        scripted = _scripts().get("park_errors") or {}
        for item in items:
            po = (item.get("PO_NUMBER") or "").strip()
            if po in scripted:
                return [dict(m) for m in scripted[po]]

        conn = _store()
        for item in items:
            po = (item.get("PO_NUMBER") or "").strip()
            po_item = (item.get("PO_ITEM") or "").strip()
            if not po:
                continue
            hit = conn.execute(
                "SELECT 1 FROM EKPO WHERE EBELN = ? AND EBELP = ?", (po, po_item)
            ).fetchone()
            if not hit:
                return [_msg("E", "M8", "147",
                             f"Purchase order item {po}/{po_item} does not exist",
                             po, po_item)]
        return []

    def _invoice_delete(self, kwargs) -> dict:
        doc = (kwargs.get("INVOICEDOCNUMBER") or "").strip()
        year = (kwargs.get("FISCALYEAR") or "").strip()
        conn = _store()
        gone = conn.execute(
            "DELETE FROM RBKP WHERE BELNR = ? AND GJAHR = ?", (doc, year)).rowcount

        if not gone:
            return _shape({"RETURN": [_msg("E", "M8", "022",
                                           f"Document {doc} {year} does not exist", doc)]},
                          {}, {}, kwargs)
        # SAP reports a successful reversal as an ERROR row, and
        # sap_invoice_post.py filters M8/417 back out before deciding. Emitting a
        # cheerful "S" here would be read as a FAILURE.
        return _shape({"RETURN": [_msg("E", "M8", "417",
                                       f"Document {doc} deleted", doc)]}, {}, {}, kwargs)

    def _commit(self, kwargs) -> dict:
        _store().commit()
        return {}

    def _rollback(self, kwargs) -> dict:
        _store().rollback()
        return {}

    def _exchange_rate(self, kwargs) -> dict:
        rates = (kwargs.get("input_tables") or {}).get("RATE_LIST") or []
        rate = (kwargs.get("input_structures") or {}).get("EXCH_RATE") or {}
        row = rates[0] if rates else rate
        pair = f"{row.get('FROM_CURR', '')}/{row.get('TO_CURRNCY', '')}"
        return _shape(
            {"RETURN": [_msg("S", "SG", "105", f"Exchange rate {pair} saved", pair)]},
            {}, {}, kwargs)

    # -- bookkeeping --

    @staticmethod
    def _next_document_number(conn: sqlite3.Connection) -> str:
        cur = conn.execute("SELECT VALUE FROM Z_COUNTER WHERE NAME = 'invoice_doc'")
        nxt = int(cur.fetchone()["VALUE"]) + 1
        conn.execute("UPDATE Z_COUNTER SET VALUE = ? WHERE NAME = 'invoice_doc'", (str(nxt),))
        return str(nxt)


def _rowcount(value) -> int:
    """ROWCOUNT arrives as a string, and is sometimes absent (= unlimited)."""
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return 0
    return n if n > 0 else 0
