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


class MultiLineTest(unittest.TestCase):
    def test_enter_starts_a_line_and_a_blank_line_or_ctrl_d_ends_the_note(self):
        dialog = TextInput(["note:"], multiline=True)
        self.assertIsNone(type_keys(dialog, list("wiki") + ["enter"] + list("push")))
        self.assertEqual(dialog.lines(), ["note:", "> wiki", "> push"])
        self.assertIsNone(dialog.on_key("enter"))
        self.assertEqual(dialog.on_key("enter"), ("done", "wiki\npush"))
        dialog = TextInput(["note:"], multiline=True, initial="a\nb")
        self.assertEqual(dialog.on_key("ctrl-d"), ("done", "a\nb"))
        self.assertEqual(TextInput([], multiline=True).on_key("enter"), ("done", ""))

    def test_backspace_on_an_empty_line_goes_back_to_the_line_before(self):
        dialog = TextInput(["note:"], multiline=True, initial="ab\n")
        type_keys(dialog, ["backspace", "backspace"])
        self.assertEqual(dialog.lines(), ["note:", "> a"])


if __name__ == "__main__":
    unittest.main()
