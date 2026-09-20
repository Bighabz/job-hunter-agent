import unittest
from unittest.mock import patch

from workable_discovery import company_name


class CompanyDataTests(unittest.TestCase):
    def test_accepts_supported_company_formats(self):
        for value in ({'title': 'Example'}, '{"title":"Example"}', "{'title': 'Example'}"):
            self.assertEqual(company_name(value), 'Example')

    def test_rejects_executable_board_data(self):
        with patch('os.system') as execute:
            self.assertIsNone(company_name("__import__('os').system('echo injected')"))
            execute.assert_not_called()

    def test_missing_or_wrong_shaped_company_is_unset(self):
        for value in (None, 1, [], '[]', 'null', 'invalid', '{}'):
            self.assertIsNone(company_name(value))


if __name__ == '__main__':
    unittest.main()
