import unittest
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python 3.9 and 3.10; the 3.12 run reads the manifest
    tomllib = None

from agent_parking import state

MANIFEST = Path(__file__).resolve().parents[1] / "herdr-plugin.toml"


@unittest.skipIf(tomllib is None, "tomllib needs Python 3.11")
class ManifestTest(unittest.TestCase):
    def setUp(self):
        self.manifest = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_the_manifest_declares_the_dashboard_pane_and_the_two_open_actions(self):
        manifest = self.manifest
        self.assertEqual((manifest["id"], manifest["min_herdr_version"]), (state.PLUGIN_ID, "0.9.1"))
        self.assertEqual(manifest["platforms"], ["linux", "macos"])
        [pane] = manifest["panes"]
        self.assertEqual((pane["id"], pane["placement"]), ("dashboard", "overlay"))
        self.assertEqual(pane["command"], ["python3", "-m", "agent_parking", "dashboard"])
        actions = {action["id"]: action for action in manifest["actions"]}
        self.assertEqual(sorted(actions), ["open", "open-tab"])
        for action_id, action in actions.items():
            with self.subTest(action=action_id):
                self.assertEqual(action["command"], ["python3", "-m", "agent_parking", action_id])
                self.assertEqual(action["contexts"], ["global"])
                self.assertTrue(action["title"])


if __name__ == "__main__":
    unittest.main()
