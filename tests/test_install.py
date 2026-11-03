import subprocess
import sys
import tempfile
import json
from pathlib import Path
import unittest


class InstallerTest(unittest.TestCase):
    def test_only_one_public_cli_and_namespace(self):
        repo = Path(__file__).resolve().parents[1]
        pyproject = (repo / "pyproject.toml").read_text()
        scripts = pyproject.split("[project.scripts]", 1)[1].split("[", 1)[0]
        self.assertEqual(scripts.strip(), 'prof-tools = "prof_tools.cli:main"')
        version = pyproject.split('version = "', 1)[1].split('"', 1)[0]
        for manifest in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
            self.assertEqual(json.loads((repo / manifest).read_text())["version"], version)
        self.assertTrue((repo / "src" / "prof_tools" / "cli.py").is_file())
        self.assertFalse((repo / "src" / "gpu_perf").exists())

    def test_five_optional_agent_definitions(self):
        repo = Path(__file__).resolve().parents[1]
        files = list((repo / 'agents-optional').glob('*.md'))
        self.assertEqual(len(files), 5)
        self.assertTrue((repo / 'agents-optional' / 'prof-tools-architecture-reviewer.md').is_file())

    def test_clean_codex_install_and_collision_handling(self):
        tool = Path(__file__).resolve().parent.parent / 'tools' / 'install_skills.py'
        with tempfile.TemporaryDirectory() as d:
            base = [sys.executable, str(tool), '--project', d, '--client', 'codex']
            subprocess.run(base, check=True, capture_output=True, text=True)
            actual = list((Path(d) / '.agents' / 'skills').glob('*/SKILL.md'))
            self.assertEqual(sorted(p.parent.name for p in actual), ["analyze", "optimize"])
            self.assertTrue((Path(d) / '.agents' / 'skills' / 'analyze' / 'SKILL.md').is_file())
            self.assertTrue((Path(d) / '.agents' / 'skills' / 'optimize' / 'references' / 'cpu.md').is_file())
            self.assertTrue((Path(d) / '.agents' / 'skills' / 'optimize' / 'references' / 'hardware' / 'mi300a.md').is_file())
            collision = subprocess.run(base, capture_output=True, text=True)
            self.assertNotEqual(collision.returncode, 0)
            subprocess.run(base + ['--force'], check=True, capture_output=True, text=True)


if __name__ == '__main__':
    unittest.main()
