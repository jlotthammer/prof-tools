"""The explicit performance workflow requests Labcoat only for its campaign."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class OptInTests(unittest.TestCase):
    def test_explicit_optin_and_manual_hook_fallback(self):
        skill = (ROOT / "skills/prof-tools/SKILL.md").read_text()
        self.assertIn("disable-model-invocation: true", skill)
        self.assertIn("explicitly opts into Labcoat", skill)
        self.assertIn("run Labcoat's annotation and validation scripts", skill)
        self.assertIn("external notes repository", skill)
        agent = (ROOT / "agents-optional/prof-tools-coordinator.md").read_text()
        self.assertIn("no second user prompt", agent)
        self.assertIn("vendor", agent)
        policy = (ROOT / "skills/prof-tools/agents/openai.yaml").read_text()
        self.assertIn("allow_implicit_invocation: false", policy)


if __name__ == "__main__":
    unittest.main()
