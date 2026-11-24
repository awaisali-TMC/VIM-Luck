"""Income Tax / Sales Tax badges (client observation A): never guess a status.

Offline: FBR and the ATL tables are stubbed.

    py -3 backend/test_fbr_status.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services import fbr_verification as f  # noqa: E402

_failures = []


def expect(label, cond, extra=None):
    print(f"  [{'PASS' if cond else '**FAIL**'}] {label}" + (f"  ({extra})" if extra is not None and not cond else ""))
    if not cond:
        _failures.append(label)


print("WORDING")
for text, want in (("Active", "active"), ("OPERATIVE", "active"), ("Inactive", "inactive"), ("In-Active", "inactive"),
                   ("Non Active", "inactive"), ("Not Active", "inactive"), ("INOPERATIVE", "inactive"),
                   ("Suspended", "inactive"), ("Blacklisted", "inactive"), ("", "unknown"), ("Pending", "unknown")):
    expect(f"{text!r} -> {want}", f._status_from(text) == want, f._status_from(text))

print("\nNO RECORD vs NO ANSWER")
expect("plain 'No record exists' = no record", f._fbr_no_record({"status_code": 1, "response": "No record exists"}))
expect("an error reply is not 'no record'", not f._fbr_no_record({"status_code": 0, "response": "No record exists"}))
expect("other text is not 'no record'", not f._fbr_no_record({"status_code": 1, "response": "Service busy"}))


def detail(st_reply, live=True, lists=None):
    async def _lists(_n):
        return lists or {"IT": {"filing_status": "Active"}, "ST": None}

    def _q(ident, typ, proto, _is_retry=False, output_type="5", raw=False):
        return st_reply if proto == "1005" else None

    f._lookup_atl_lists, f._query_fbr_api_sync = _lists, _q
    return asyncio.run(f.fbr_status_detail("1328862-8", live=live))


print("\nBADGES")
d = detail({"Name": "X", "Filing Status": "In-Active"})
expect("client's case: Income Tax active, Sales Tax inactive",
       (d["income_tax"]["status"], d["sales_tax"]["status"]) == ("active", "inactive"), d)
expect("no status in the reply -> unknown, not active", detail({"Name": "X"})["sales_tax"]["status"] == "unknown")
expect("a checking date alone is not a status",
       detail({"Name": "X", "Filing Status Checking Date": "23-NOV-26"})["sales_tax"]["status"] == "unknown")
expect("another status title is read", detail({"Sales Tax Status": "Active"})["sales_tax"]["status"] == "active")
expect("FBR did not answer -> unknown, not 'Not on ATL'", detail(None)["sales_tax"]["status"] == "unknown")
expect("FBR says no record -> not_found", detail({})["sales_tax"]["status"] == "not_found")
expect("live off, not on the local list -> not_found", detail(None, live=False)["sales_tax"]["status"] == "not_found")
d = detail(None, lists={"IT": {"filing_status": "Inactive"}, "ST": {"filing_status": None}})
expect("a list row that says Inactive is inactive", d["income_tax"]["status"] == "inactive", d)
expect("a list row without a status is active (it is on the list)", d["sales_tax"]["status"] == "active", d)


async def _none(_n):
    return {"IT": None, "ST": None}


f._lookup_atl_lists = _none
for filing, want in (("Active", "active"), ("Inactive", "inactive"), ("Unknown", "unknown")):
    it = {"source": "live_api", "status": "verified_x", "is_active": filing == "Active", "filing_status": filing}
    got = asyncio.run(f.fbr_status_detail("1328862-8", live=True, it_result=it))["income_tax"]["status"]
    expect(f"income tax from the first live call: {filing} -> {want}", got == want, got)

print("\n" + "=" * 60)
if _failures:
    print(f"RESULT: {len(_failures)} FAILED -> {_failures}")
    sys.exit(1)
print("RESULT: ALL FBR STATUS TESTS PASSED")
