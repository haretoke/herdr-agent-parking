import unittest

from agent_parking.keys import KeyParser


class KeyParserTest(unittest.TestCase):
    def test_characters_arrows_and_control_keys(self):
        keys = KeyParser().feed(b"jk\x1b[A\x1bOB\r\x7f\x04\x03\x15")
        self.assertEqual(keys, ["j", "k", "up", "down", "enter", "backspace", "ctrl-d", "ctrl-c", "ctrl-u"])

    def test_a_split_escape_sequence_waits_for_its_end(self):
        parser = KeyParser()
        self.assertEqual(parser.feed(b"j\x1b["), ["j"])
        self.assertEqual(parser.feed(b"Bk"), ["down", "k"])

    def test_a_lone_escape_at_the_end_of_a_read_is_the_esc_key(self):
        self.assertEqual(KeyParser().feed(b"\x1b"), ["esc"])
        self.assertEqual(KeyParser().feed(b"\x1bq"), ["esc", "q"])

    def test_utf8_text_split_across_reads_is_one_character(self):
        parser = KeyParser()
        data = "メモ".encode()
        self.assertEqual(parser.feed(data[:2]), [])
        self.assertEqual(parser.feed(data[2:]), ["メ", "モ"])


if __name__ == "__main__":
    unittest.main()
