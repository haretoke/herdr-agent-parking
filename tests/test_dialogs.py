import unittest

from agent_parking.dialogs import TextInput


def type_keys(dialog, keys):
    """Feed keys; the result of the last one."""
    result = None
    for key in keys:
        result = dialog.on_key(key)
    return result


class SingleLineTest(unittest.TestCase):
    def test_typing_editing_and_enter_give_the_text(self):
        dialog = TextInput(["threshold (minutes):"], initial="60")
        self.assertEqual(dialog.lines(), ["threshold (minutes):", "> 60"])
        self.assertIsNone(type_keys(dialog, ["backspace", "backspace", "9", "0"]))
        self.assertEqual(dialog.lines()[-1], "> 90")
        self.assertEqual(dialog.on_key("enter"), ("done", "90"))

    def test_ctrl_u_clears_and_esc_or_ctrl_c_cancel(self):
        dialog = TextInput(["filter:"], initial="api")
        dialog.on_key("ctrl-u")
        self.assertEqual(dialog.lines()[-1], "> ")
        self.assertEqual(dialog.on_key("esc"), ("cancel", None))
        self.assertEqual(TextInput([]).on_key("ctrl-c"), ("cancel", None))


if __name__ == "__main__":
    unittest.main()
