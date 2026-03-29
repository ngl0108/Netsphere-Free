from app.services.oui_service import OUIService


def test_oui_service_lookup_vendor_from_override_map():
    OUIService.set_override_map_for_tests({"aabbcc": "Acme"})
    try:
        assert OUIService.lookup_vendor("aa:bb:cc:11:22:33") == "Acme"
        assert OUIService.lookup_vendor("aabb.ccdd.eeff") == "Acme"
        assert OUIService.lookup_vendor("zz") is None
    finally:
        OUIService.set_override_map_for_tests(None)


def test_oui_service_normalizes_vendor_aliases_and_driver_candidates():
    OUIService.set_override_map_for_tests({"00d0cb": "Dasan Networks"})
    try:
        detail = OUIService.lookup_vendor_detail("00:d0:cb:11:22:33")
        assert detail["raw_vendor"] == "Dasan Networks"
        assert detail["normalized_vendor"] == "Dasan"
        assert detail["driver_candidates"][0] == "dasan_nos"
    finally:
        OUIService.set_override_map_for_tests(None)


def test_oui_service_marks_generic_chipset_vendors():
    OUIService.set_override_map_for_tests({"aabbcc": "Intel Corporate"})
    try:
        detail = OUIService.lookup_vendor_detail("aa:bb:cc:11:22:33")
        assert detail["raw_vendor"] == "Intel Corporate"
        assert detail["is_generic_chipset"] is True
    finally:
        OUIService.set_override_map_for_tests(None)


def test_oui_service_expands_domestic_aliases_and_driver_candidates():
    OUIService.set_override_map_for_tests({"112233": "Woori-Net"})
    try:
        detail = OUIService.lookup_vendor_detail("11:22:33:44:55:66")
        assert detail["normalized_vendor"] == "WooriNet"
        assert detail["driver_candidates"][0] == "domestic_cisco_like"
        assert OUIService.normalize_vendor_name("ip-time") == "EFMNetworks"
        assert OUIService.normalize_vendor_name("davo link") == "Davolink"
        assert OUIService.is_generic_chipset_vendor("Ralink Technology") is True
    finally:
        OUIService.set_override_map_for_tests(None)
