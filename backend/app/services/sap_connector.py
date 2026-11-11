"""
SAP RFC Connector — direct ctypes binding to sapnwrfc.dll.

No PyRFC required. Uses the SAP NW RFC SDK DLL directly.
Based on: https://github.com/jdsricardo/SAP-RFC-Python-without-PyRFC
Extended with SAProuter support for einv project.
"""

import os
import sys
import time
import logging
from ctypes import (
    Structure, c_long, c_ulong, c_void_p, c_wchar, c_wchar_p,
    POINTER, byref, create_unicode_buffer,
)

if sys.platform == "win32":
    from ctypes import windll  # Windows-only; Linux uses the PyRFC connector below
else:
    windll = None

from app.config import settings
from app.services.sap_credentials import current_sap_user, current_sap_passwd

logger = logging.getLogger(__name__)


# ── RFC C Structures ──────────────────────────────────────────────────────────

class RFC_ERROR_INFO(Structure):
    _fields_ = [
        ("code", c_long),
        ("group", c_long),
        ("key", c_wchar * 128),
        ("message", c_wchar * 512),
        ("abapMsgClass", c_wchar * 21),
        ("abapMsgType", c_wchar * 2),
        ("abapMsgNumber", c_wchar * 4),
        ("abapMsgV1", c_wchar * 51),
        ("abapMsgV2", c_wchar * 51),
        ("abapMsgV3", c_wchar * 51),
        ("abapMsgV4", c_wchar * 51),
    ]


class RFC_CONNECTION_PARAMETER(Structure):
    _fields_ = [("name", c_wchar_p), ("value", c_wchar_p)]


class RFC_FUNCTION_DESC_HANDLE(c_void_p):
    pass


class RFC_FUNCTION_HANDLE(c_void_p):
    pass


class RFC_TABLE_HANDLE(c_void_p):
    pass


# ── SAP RFC Connector ─────────────────────────────────────────────────────────

class SAPConnector:
    """
    Connect to SAP via RFC and call BAPIs/function modules.

    Usage:
        sap = SAPConnector()
        sap.connect()
        result = sap.call("RFC_SYSTEM_INFO", output_params=["RFCSI_EXPORT"])
        sap.disconnect()
    """

    def __init__(self, dll_directory: str = None):
        self.dll_directory = dll_directory or settings.SAP_NWRFC_SDK_PATH
        self.dll_path = os.path.join(self.dll_directory, "lib", "sapnwrfc.dll")

        if not os.path.exists(self.dll_path):
            raise FileNotFoundError(
                f"sapnwrfc.dll not found at {self.dll_path}. "
                f"Set SAP_NWRFC_SDK_PATH in .env to the SDK root folder."
            )

        os.add_dll_directory(os.path.join(self.dll_directory, "lib"))

        self.error_info = RFC_ERROR_INFO()
        self.sap_lib = None
        self.connection_handle = None

        self._load_dll()

    def _load_dll(self):
        self.sap_lib = windll.LoadLibrary(self.dll_path)
        self._setup_prototypes()
        logger.info("SAP NW RFC SDK loaded successfully")

    def _setup_prototypes(self):
        lib = self.sap_lib

        lib.RfcOpenConnection.argtypes = [
            POINTER(RFC_CONNECTION_PARAMETER), c_ulong, POINTER(RFC_ERROR_INFO),
        ]
        lib.RfcOpenConnection.restype = c_void_p

        lib.RfcCloseConnection.argtypes = [c_void_p, POINTER(RFC_ERROR_INFO)]
        lib.RfcCloseConnection.restype = c_ulong

        lib.RfcGetFunctionDesc.argtypes = [
            c_void_p, c_wchar_p, POINTER(RFC_ERROR_INFO),
        ]
        lib.RfcGetFunctionDesc.restype = RFC_FUNCTION_DESC_HANDLE

        lib.RfcCreateFunction.argtypes = [RFC_FUNCTION_DESC_HANDLE, POINTER(RFC_ERROR_INFO)]
        lib.RfcCreateFunction.restype = RFC_FUNCTION_HANDLE

        lib.RfcDestroyFunction.argtypes = [RFC_FUNCTION_HANDLE, POINTER(RFC_ERROR_INFO)]

        lib.RfcInvoke.argtypes = [c_void_p, RFC_FUNCTION_HANDLE, POINTER(RFC_ERROR_INFO)]

        lib.RfcGetTable.argtypes = [
            c_void_p, c_wchar_p, POINTER(RFC_TABLE_HANDLE), POINTER(RFC_ERROR_INFO),
        ]

        lib.RfcAppendNewRow.argtypes = [RFC_TABLE_HANDLE, POINTER(RFC_ERROR_INFO)]
        lib.RfcAppendNewRow.restype = c_void_p

        lib.RfcGetRowCount.argtypes = [RFC_TABLE_HANDLE, POINTER(c_ulong), POINTER(RFC_ERROR_INFO)]

        lib.RfcMoveToNextRow.argtypes = [RFC_TABLE_HANDLE, POINTER(RFC_ERROR_INFO)]

        lib.RfcMoveToFirstRow.argtypes = [RFC_TABLE_HANDLE, POINTER(RFC_ERROR_INFO)]

        lib.RfcGetCurrentRow.argtypes = [RFC_TABLE_HANDLE, POINTER(RFC_ERROR_INFO)]
        lib.RfcGetCurrentRow.restype = c_void_p

        lib.RfcSetString.argtypes = [
            c_void_p, c_wchar_p, c_wchar_p, c_ulong, POINTER(RFC_ERROR_INFO),
        ]

        lib.RfcGetString.argtypes = [
            c_void_p, c_wchar_p, c_wchar_p, c_ulong, POINTER(c_ulong), POINTER(RFC_ERROR_INFO),
        ]

        # Structure field access
        lib.RfcGetStructure.argtypes = [
            c_void_p, c_wchar_p, POINTER(c_void_p), POINTER(RFC_ERROR_INFO),
        ]

    # ── Connection ────────────────────────────────────────────────────────────

    def connect(self):
        """Open RFC connection to SAP using settings from .env."""
        params = [
            ("ASHOST", settings.SAP_ASHOST),
            ("SYSNR", settings.SAP_SYSNR),
            ("CLIENT", settings.SAP_CLIENT),
            # Per-user SAP login when the request set one, else the global SAP_USER.
            ("USER", current_sap_user()),
            ("PASSWD", current_sap_passwd()),
        ]

        # Add SAProuter if configured
        if settings.SAP_SAPROUTER:
            params.append(("SAPROUTER", settings.SAP_SAPROUTER))

        # Add SysID if configured
        if settings.SAP_SYSID:
            params.append(("SYSID", settings.SAP_SYSID))

        conn_params = (RFC_CONNECTION_PARAMETER * len(params))()
        for i, (k, v) in enumerate(params):
            conn_params[i].name = k
            conn_params[i].value = v or ""

        start = time.time()
        self.connection_handle = self.sap_lib.RfcOpenConnection(
            conn_params, len(params), byref(self.error_info)
        )

        if not self.connection_handle:
            raise RuntimeError(self._format_error("OpenConnection"))

        elapsed = time.time() - start
        logger.info(f"SAP connected in {elapsed:.2f}s (host={settings.SAP_ASHOST}, client={settings.SAP_CLIENT})")
        return True

    def disconnect(self):
        """Close the RFC connection."""
        if self.connection_handle:
            self.sap_lib.RfcCloseConnection(self.connection_handle, byref(self.error_info))
            self.connection_handle = None
            logger.info("SAP disconnected")

    def is_connected(self) -> bool:
        return self.connection_handle is not None

    # ── RFC Call ──────────────────────────────────────────────────────────────

    def call(self, function_name: str, **kwargs) -> dict:
        """
        Call an SAP RFC function module / BAPI.

        Keyword args:
            input_tables: dict of table_name → list of row dicts (for input tables)
            tables: list of output table names to extract
            table_fields: dict of table_name → list of field names
            output_params: list of scalar output parameter names
            Any other kwargs are set as importing parameters (string values).

        Returns: dict with extracted output params and tables.
        """
        if not self.connection_handle:
            self.connect()

        func_desc = self.sap_lib.RfcGetFunctionDesc(
            self.connection_handle, function_name, byref(self.error_info)
        )
        if not func_desc:
            raise RuntimeError(self._format_error(f"GetFunctionDesc({function_name})"))

        func_handle = self.sap_lib.RfcCreateFunction(func_desc, byref(self.error_info))
        if not func_handle:
            raise RuntimeError(self._format_error(f"CreateFunction({function_name})"))

        input_tables = kwargs.pop("input_tables", {})
        input_structures = kwargs.pop("input_structures", {})
        output_tables = kwargs.pop("tables", [])
        output_fields = kwargs.pop("table_fields", {})
        output_params = kwargs.pop("output_params", [])
        output_structures = kwargs.pop("output_structures", {})

        # Set input structures (IMPORT parameters that are structures, e.g. HEADERDATA)
        for struct_name, fields_dict in input_structures.items():
            self._set_structure(func_handle, struct_name, fields_dict)

        # Set input tables
        for table_name, rows in input_tables.items():
            self._set_table(func_handle, table_name, rows)

        # Set importing parameters
        for name, value in kwargs.items():
            self.sap_lib.RfcSetString(
                func_handle, name, str(value), len(str(value)), byref(self.error_info)
            )

        # Invoke
        start = time.time()
        rc = self.sap_lib.RfcInvoke(self.connection_handle, func_handle, byref(self.error_info))
        elapsed = time.time() - start

        if self.error_info.code != 0:
            error_msg = self._format_error(f"Invoke({function_name})")
            self.sap_lib.RfcDestroyFunction(func_handle, byref(self.error_info))
            raise RuntimeError(error_msg)

        logger.info(f"SAP RFC {function_name} executed in {elapsed:.2f}s")

        # Extract results
        result = {}

        for table in output_tables:
            fields = output_fields.get(table)
            result[table] = self._extract_table(func_handle, table, fields)

        for param in output_params:
            buffer = create_unicode_buffer(1024)
            length = c_ulong()
            self.sap_lib.RfcGetString(
                func_handle, param, buffer, 1024, byref(length), byref(self.error_info)
            )
            result[param] = buffer.value

        for struct_name, fields in output_structures.items():
            result[struct_name] = self._extract_structure(func_handle, struct_name, fields)

        self.sap_lib.RfcDestroyFunction(func_handle, byref(self.error_info))
        return result

    # ── Structure Input ────────────────────────────────────────────────────────

    def _set_structure(self, func_handle, struct_name: str, fields: dict):
        """Set fields on an import structure parameter (e.g. HEADERDATA)."""
        struct_handle = c_void_p()
        self.sap_lib.RfcGetStructure(
            func_handle, struct_name, byref(struct_handle), byref(self.error_info)
        )
        if not struct_handle.value:
            raise RuntimeError(self._format_error(f"GetStructure({struct_name})"))

        for field_name, value in fields.items():
            val_str = str(value) if value is not None else ""
            self.sap_lib.RfcSetString(
                struct_handle, field_name, val_str, len(val_str), byref(self.error_info)
            )

    # ── Table Input ───────────────────────────────────────────────────────────

    def _set_table(self, func_handle, table_name: str, rows: list[dict]):
        table_handle = RFC_TABLE_HANDLE()
        self.sap_lib.RfcGetTable(
            func_handle, table_name, byref(table_handle), byref(self.error_info)
        )

        for row in rows:
            struct_handle = self.sap_lib.RfcAppendNewRow(table_handle, byref(self.error_info))
            for field, value in row.items():
                if isinstance(value, list):
                    self._set_nested_table(struct_handle, field, value)
                else:
                    self.sap_lib.RfcSetString(
                        struct_handle, field, str(value), len(str(value)), byref(self.error_info)
                    )

    def _set_nested_table(self, parent_handle, table_name: str, rows: list[dict], level=1):
        if level > 3:
            return
        table_handle = RFC_TABLE_HANDLE()
        rc = self.sap_lib.RfcGetTable(
            parent_handle, table_name, byref(table_handle), byref(self.error_info)
        )
        if rc != 0:
            return
        for row in rows:
            struct_handle = self.sap_lib.RfcAppendNewRow(table_handle, byref(self.error_info))
            for field, value in row.items():
                if isinstance(value, list):
                    self._set_nested_table(struct_handle, field, value, level + 1)
                else:
                    self.sap_lib.RfcSetString(
                        struct_handle, field, str(value), len(str(value)), byref(self.error_info)
                    )

    # ── Table/Structure Extraction ────────────────────────────────────────────

    def _extract_table(self, func_handle, table_name: str, fields: list[str] | None, buf_size=1024):
        table_handle = RFC_TABLE_HANDLE()
        rc = self.sap_lib.RfcGetTable(
            func_handle, table_name, byref(table_handle), byref(self.error_info)
        )
        if rc != 0:
            return []

        row_count = c_ulong()
        self.sap_lib.RfcGetRowCount(table_handle, byref(row_count), byref(self.error_info))

        # Rewind the row cursor to the first row before reading. A table that was
        # populated as an INPUT parameter (e.g. the FIELDS table of RFC_READ_TABLE)
        # leaves the cursor at the last appended row; without this rewind, reading
        # it back as output starts at the end and yields wrong/empty values.
        if row_count.value > 0:
            self.sap_lib.RfcMoveToFirstRow(table_handle, byref(self.error_info))

        result = []
        for i in range(row_count.value):
            if i > 0:
                self.sap_lib.RfcMoveToNextRow(table_handle, byref(self.error_info))

            row = {}
            for field in (fields or []):
                buffer = create_unicode_buffer(buf_size)
                length = c_ulong()
                self.sap_lib.RfcGetString(
                    table_handle, field, buffer, buf_size, byref(length), byref(self.error_info)
                )
                row[field] = buffer.value
            result.append(row)

        return result

    def _extract_structure(self, func_handle, struct_name: str, fields: list[str]):
        struct_handle = c_void_p()
        self.sap_lib.RfcGetStructure(
            func_handle, struct_name, byref(struct_handle), byref(self.error_info)
        )
        if not struct_handle.value:
            return {}

        row = {}
        for field in fields:
            buffer = create_unicode_buffer(1024)
            length = c_ulong()
            self.sap_lib.RfcGetString(
                struct_handle, field, buffer, 1024, byref(length), byref(self.error_info)
            )
            row[field] = buffer.value
        return row

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _format_error(self, operation: str) -> str:
        return (
            f"SAP RFC error during {operation}: "
            f"code={self.error_info.code}, key={self.error_info.key}, "
            f"message={self.error_info.message}"
        )

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    def ping(self) -> bool:
        """Test connection with RFC_PING."""
        try:
            self.call("RFC_PING")
            return True
        except Exception:
            return False

    def get_system_info(self) -> dict:
        """Get SAP system info via RFC_SYSTEM_INFO."""
        result = self.call(
            "RFC_SYSTEM_INFO",
            output_structures={
                "RFCSI_EXPORT": [
                    "RFCSYSID", "RFCDBHOST", "RFCDBSYS", "RFCSAPRL",
                    "RFCMACH", "RFCOPSYS", "RFCIPADDR", "RFCHOST",
                ],
            },
        )
        return result.get("RFCSI_EXPORT", {})


# ── Linux: PyRFC-based connector ──────────────────────────────────────────────
# The ctypes binding above marshals strings as c_wchar, which is 2 bytes on
# Windows (matching SAP's UTF-16) but 4 bytes on Linux — so it cannot be used
# on Linux. There we delegate to SAP's official PyRFC binding (which handles
# the UTF-16 marshalling), exposing the exact same interface the services use:
# connect() / disconnect() / call(function_name, input_structures=, input_tables=,
# tables=, table_fields=, output_params=, output_structures=, **scalar_imports).

def _stringify(v):
    return "" if v is None else str(v)


class SAPConnectorPyRFC:
    """Drop-in SAPConnector for Linux, backed by PyRFC."""

    def __init__(self, dll_directory: str = None):
        try:
            from pyrfc import Connection  # needs libsapnwrfc.so on LD_LIBRARY_PATH
        except ImportError as e:
            # The image was built with --build-arg SAP_SDK=off, so it carries no
            # SDK and no PyRFC. Say so plainly — a bare ImportError here reads
            # like a broken deployment rather than a deliberate build choice.
            raise RuntimeError(
                "PyRFC is not installed in this image — it was built with "
                "SAP_SDK=off and has no live SAP support. Run with SAP_MODE=fake, "
                "or rebuild the image with the SAP NW RFC SDK."
            ) from e
        self._Connection = Connection
        self.conn = None

    def connect(self):
        params = dict(
            ashost=settings.SAP_ASHOST,
            sysnr=settings.SAP_SYSNR,
            client=settings.SAP_CLIENT,
            # Per-user SAP login when the request set one, else the global SAP_USER.
            user=current_sap_user(),
            passwd=current_sap_passwd(),
        )
        if settings.SAP_SAPROUTER:
            params["saprouter"] = settings.SAP_SAPROUTER
        if settings.SAP_SYSID:
            params["sysid"] = settings.SAP_SYSID
        start = time.time()
        self.conn = self._Connection(**params)
        logger.info(
            f"SAP connected via PyRFC in {time.time() - start:.2f}s "
            f"(host={settings.SAP_ASHOST}, client={settings.SAP_CLIENT})"
        )
        return True

    def disconnect(self):
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None
            logger.info("SAP disconnected")

    def is_connected(self) -> bool:
        return self.conn is not None

    def call(self, function_name: str, **kwargs) -> dict:
        if not self.conn:
            self.connect()

        input_tables = kwargs.pop("input_tables", {})
        input_structures = kwargs.pop("input_structures", {})
        output_tables = kwargs.pop("tables", [])
        output_fields = kwargs.pop("table_fields", {})
        output_params = kwargs.pop("output_params", [])
        output_structures = kwargs.pop("output_structures", {})

        params = {}
        params.update(input_structures)   # dicts pass through natively
        params.update(input_tables)       # lists of row dicts (nested lists OK)
        for k, v in kwargs.items():
            # RFC_READ_TABLE's ROWCOUNT is a true INT parameter; every other
            # scalar import this app sends (QUERY_TABLE, DELIMITER, WAIT,
            # INVOICEDOCNUMBER, ...) is CHAR and must stay a string.
            params[k] = int(v) if k == "ROWCOUNT" else str(v)

        start = time.time()
        res = self.conn.call(function_name, **params)
        logger.info(f"SAP RFC {function_name} executed in {time.time() - start:.2f}s")

        result = {}
        for table in output_tables:
            rows = res.get(table) or []
            fields = output_fields.get(table)
            out_rows = []
            for row in rows:
                if fields:
                    out_rows.append({f: _stringify(row.get(f, "")) for f in fields})
                else:
                    out_rows.append({k: _stringify(v) for k, v in row.items()})
            result[table] = out_rows

        for p in output_params:
            result[p] = _stringify(res.get(p, ""))

        for struct_name, fields in output_structures.items():
            data = res.get(struct_name) or {}
            result[struct_name] = {f: _stringify(data.get(f, "")) for f in fields}

        return result

    def ping(self) -> bool:
        """Test connection with RFC_PING."""
        try:
            self.call("RFC_PING")
            return True
        except Exception:
            return False

    def get_system_info(self) -> dict:
        if not self.conn:
            self.connect()
        res = self.conn.call("RFC_SYSTEM_INFO")
        info = res.get("RFCSI_EXPORT", {}) or {}
        return {k: _stringify(v) for k, v in info.items()}


if settings.SAP_MODE == "fake" and settings.DEBUG:
    # Local demos and offline tests: no SDK, no network, no SAP. Fixture-backed.
    # The import sits INSIDE the branch so the module is never even loaded in a
    # production process; it also refuses to import when DEBUG is False.
    from app.services.sap_connector_fake import SAPConnectorFake

    SAPConnector = SAPConnectorFake  # noqa: F811
elif sys.platform != "win32":
    # On Linux the ctypes class above is unusable (c_wchar width mismatch);
    # swap in the PyRFC-backed implementation under the same name.
    SAPConnector = SAPConnectorPyRFC  # noqa: F811
