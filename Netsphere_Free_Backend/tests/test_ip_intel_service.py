import os

from app.services.ip_intel_service import IpIntelService


class _Resp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_guess_provider_keywords():
    assert IpIntelService.guess_provider("Amazon AWS") == "aws"
    assert IpIntelService.guess_provider("Microsoft Azure") == "azure"
    assert IpIntelService.guess_provider("Google Cloud") == "gcp"
    assert IpIntelService.guess_provider("NAVER CLOUD NTRUSS") == "naver"


def test_get_or_fetch_uses_bgpview_and_caches(db, monkeypatch):
    os.environ.pop("DISABLE_IP_INTEL", None)

    def fake_get(url, timeout=None, headers=None):
        assert "bgpview.io" in url
        return _Resp(
            200,
            {
                "status": "ok",
                "data": {
                    "prefixes": [
                        {
                            "asn": {
                                "asn": 16509,
                                "name": "AMAZON-02",
                                "description": "Amazon.com, Inc.",
                            }
                        }
                    ]
                },
            },
        )

    monkeypatch.setattr("app.services.ip_intel_service.requests.get", fake_get)

    ip = "203.0.113.50"
    r1 = IpIntelService.get_or_fetch(db, ip)
    assert r1 is not None
    assert r1["provider_guess"] == "aws"
    assert r1["asn"] == "16509"

    def fake_get_fail(url, timeout=None, headers=None):
        raise AssertionError("should not call network when cached")

    monkeypatch.setattr("app.services.ip_intel_service.requests.get", fake_get_fail)
    r2 = IpIntelService.get_or_fetch(db, ip)
    assert r2 is not None
    assert r2["provider_guess"] == "aws"

