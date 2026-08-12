import unittest

from scraper.sister_client import NavigatoreSister


class SisterHistoricalParsingTests(unittest.TestCase):
    def test_maps_only_destination_columns_from_property_row(self):
        headers = [
            "",
            "Foglio",
            "Particella",
            "Sub",
            "Qualità",
            "Classe",
            "ha",
            "are",
            "ca",
            "Reddito dominicale",
            "Reddito agrario",
            "Partita",
            "Porzioni",
        ]
        values = [
            "",
            "7",
            "119",
            "",
            "ENTE URBANO",
            "",
            "0",
            "1",
            "37",
            "",
            "",
            "0000001",
            "",
        ]

        result = NavigatoreSister._property_result_from_cells(headers, values)

        self.assertEqual(result.sub, "")
        self.assertEqual(result.qualita, "ENTE URBANO")
        self.assertEqual((result.ha, result.are, result.ca), ("0", "1", "37"))
        self.assertEqual(result.mq, 137)
        self.assertFalse(hasattr(result, "classe"))
        self.assertFalse(hasattr(result, "partita"))
        self.assertFalse(hasattr(result, "porzioni"))

    def test_no_owner_message_is_a_valid_empty_result(self):
        class EmptyOwnersPage:
            frames = []

            @staticmethod
            def content():
                return "<legend>Elenco Intestati</legend><strong>NESSUNA CORRISPONDENZA TROVATA</strong>"

        self.assertEqual(NavigatoreSister.extract_owners(EmptyOwnersPage()), [])


if __name__ == "__main__":
    unittest.main()
