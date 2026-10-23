"""Quick test: load SAP DLL and attempt connection."""
import os
import sys

SDK_LIB = r"C:\nwrfcsdk\lib"
os.add_dll_directory(SDK_LIB)

from ctypes import windll
lib = windll.LoadLibrary(os.path.join(SDK_LIB, "sapnwrfc.dll"))
print("SAP NW RFC DLL loaded successfully!")

# Now test full connection
sys.path.insert(0, os.path.dirname(__file__))
os.environ["SAP_NWRFC_SDK_PATH"] = r"C:\nwrfcsdk"

from app.services.sap_connector import SAPConnector

print("\nConnecting to SAP...")
print(f"  Host: 10.50.210.212")
print(f"  SysNr: 00, Client: 400")
print(f"  SAProuter: /H/103.111.160.96")

try:
    sap = SAPConnector()
    sap.connect()
    print("\nSAP Connection: SUCCESS!")

    print("\nTesting RFC_PING...")
    ok = sap.ping()
    print(f"RFC_PING: {'SUCCESS' if ok else 'FAILED'}")

    print("\nGetting system info...")
    info = sap.get_system_info()
    for k, v in info.items():
        print(f"  {k}: {v}")

    sap.disconnect()
    print("\nDisconnected. SAP integration is ready!")

except Exception as e:
    print(f"\nConnection FAILED: {e}")
