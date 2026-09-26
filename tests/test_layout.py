import unittest

from agent_parking import layout


def leaf(pane_id):
    return {"type": "pane", "pane_id": pane_id, "cwd": "/w"}


# A | (B / C) at 0.3 and 0.7, the shape `layout.export` gave in spike 0-15.
TREE = {"type": "split", "direction": "right", "ratio": 0.3, "first": leaf("w1:pC"),
        "second": {"type": "split", "direction": "down", "ratio": 0.7,
                   "first": leaf("w1:pD"), "second": leaf("w1:pE")}}


class HintTest(unittest.TestCase):
    def test_a_pane_beside_a_single_pane_names_it(self):
        self.assertEqual(layout.hint(TREE, "w1:pE"), {"sibling_pane_id": "w1:pD", "position": "second",
                                                      "direction": "down", "ratio": 0.7, "path": [True]})
        self.assertEqual(layout.hint(TREE, "w1:pD"), {"sibling_pane_id": "w1:pE", "position": "first",
                                                      "direction": "down", "ratio": 0.7, "path": [True]})

    def test_a_pane_beside_a_subtree_has_no_sibling_pane(self):
        self.assertEqual(layout.hint(TREE, "w1:pC"), {"sibling_pane_id": None, "position": "first",
                                                      "direction": "right", "ratio": 0.3, "path": []})

    def test_a_lone_pane_or_an_unknown_one_has_no_hint(self):
        self.assertIsNone(layout.hint(leaf("w1:p1"), "w1:p1"))
        self.assertIsNone(layout.hint(TREE, "w1:p9"))
        self.assertIsNone(layout.hint(None, "w1:p1"))


if __name__ == "__main__":
    unittest.main()
