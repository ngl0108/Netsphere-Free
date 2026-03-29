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


class TestPolicyTranslatorSecurityLinux(unittest.TestCase):
    def test_linux_ahnlab_generates_iptables(self):
        policy = _Policy(
            name="fw",
            rules=[
                _Rule(10, "permit", {"protocol": "tcp", "source": "10.0.0.0/24", "destination": "192.168.0.10", "port": 443}),
                _Rule(20, "deny", {"protocol": "udp", "source": "any", "destination": "192.168.0.0/24", "port": 53}),
            ],
        )
        cmds = PolicyTranslator.translate(policy, "linux_ahnlab")
        self.assertEqual(cmds[0], "iptables -A FORWARD -p tcp -s 10.0.0.0/24 -d 192.168.0.10/32 --dport 443 -j ACCEPT")
        self.assertTrue(cmds[1].endswith("-j DROP"))


if __name__ == "__main__":
    unittest.main()

