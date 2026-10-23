"""
One-time migration: add SAP posting columns to the invoices table.

Run with:  py -3 add_sap_posting_columns.py
"""

import sqlite3
import sys

DB_PATH = "invoices.db"

COLUMNS = [
    ("sap_document_number", "VARCHAR(50)"),
    ("sap_fiscal_year", "VARCHAR(10)"),
    ("sap_company_code", "VARCHAR(10)"),
    ("sap_posted_at", "DATETIME"),
]


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get existing column names
    cursor.execute("PRAGMA table_info(invoices)")
    existing = {row[1] for row in cursor.fetchall()}

    added = []
    for col_name, col_type in COLUMNS:
        if col_name not in existing:
            cursor.execute(f"ALTER TABLE invoices ADD COLUMN {col_name} {col_type}")
            added.append(col_name)

    conn.commit()
    conn.close()

    if added:
        print(f"Added columns: {', '.join(added)}")
    else:
        print("All columns already exist. No changes needed.")


if __name__ == "__main__":
    migrate()
