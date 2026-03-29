from app.core.device_fingerprints import extract_model_from_descr


def test_extract_model_from_sysdescr_korea_vendors():
    assert extract_model_from_descr("Dasan", "Dasan Networks V5624G NOS, Version 1.2.3") == "V5624G"
    assert extract_model_from_descr("Ubiquoss", "Ubiquoss L3 Switch UWS-5000 uNOS System, Version 7") == "UWS-5000"
    assert extract_model_from_descr("HanDreamnet", "SG2100 Series VIPM, build 123") == "SG2100"
    assert extract_model_from_descr("Handream", "SubGate SG2100 Series VIPM") in ("SG2100", "SubGate", "Subgate")
    assert extract_model_from_descr("Piolink", "PAS-K TiFRONT Version 9.0") in ("PAS-K", "TiFRONT")
    assert extract_model_from_descr("AhnLab", "AhnLab TrusGuard 3100 Version 1.0") in ("TrusGuard 3100", "TrusGuard")
    assert extract_model_from_descr("SECUI", "SECUI MF2 BLUEMAX Version 3.0") in ("MF2", "BLUEMAX")
    assert extract_model_from_descr("WINS", "Sniper IPS Sniper DDX-1200 build 1") in ("DDX-1200", "Sniper DDX-1200")
    assert extract_model_from_descr("MonitorApp", "AIWAF v5.0") == "AIWAF"
    assert extract_model_from_descr("EFMNetworks", "ipTime A3004NS Linux 5.10") == "A3004NS"
    assert extract_model_from_descr("Samsung", "Samsung WLAN AP SWL-1234 build 1") == "SWL-1234"

