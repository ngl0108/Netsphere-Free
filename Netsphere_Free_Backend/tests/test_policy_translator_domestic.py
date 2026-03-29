import unittest

from app.services.policy_translator import PolicyTranslator


class _Rule:
    def __init__(self, priority: int, action: str, match_conditions: dict):
        self.priority = priority
        self.action = action
        self.match_conditions = match_conditions


class _Policy:
    def __init__(self, name: str, rules: list):
        self.name = name
        self.rules = rules


class TestPolicyTranslatorDomestic(unittest.TestCase):
    def test_dasan_uses_cisco_acl(self):
        policy = _Policy(
            name="web",
            rules=[
                _Rule(10, "permit", {"protocol": "tcp", "source": "10.0.0.0/24", "destination": "any", "port": 443}),
            ],
        )
        cmds = PolicyTranslator.translate(policy, "dasan_nos")
        self.assertTrue(cmds and cmds[0].startswith("ip access-list extended"))
        self.assertTrue(any("permit tcp" in c for c in cmds))

    def test_ubiquoss_uses_cisco_acl(self):
        policy = _Policy(
            name="dns",
            rules=[
                _Rule(10, "permit", {"protocol": "udp", "source": "any", "destination": "10.0.0.53", "port": 53}),
            ],
        )
        cmds = PolicyTranslator.translate(policy, "ubiquoss_l2")
        self.assertTrue(cmds and cmds[0].startswith("ip access-list extended"))
        self.assertTrue(any("permit udp" in c for c in cmds))

    def test_new_domestic_vendors_use_cisco_acl(self):
        policy = _Policy(
            name="ops",
            rules=[
                _Rule(10, "permit", {"protocol": "tcp", "source": "10.10.10.0/24", "destination": "any", "port": 22}),
            ],
        )
        for device_type in ("soltech_switch", "coreedge_switch", "nst_switch"):
            cmds = PolicyTranslator.translate(policy, device_type)
            self.assertTrue(cmds and cmds[0].startswith("ip access-list extended"))
            self.assertTrue(any("permit tcp" in c for c in cmds))


if __name__ == "__main__":
    unittest.main()
