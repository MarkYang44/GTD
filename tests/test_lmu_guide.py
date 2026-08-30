import unittest

import lmu_guide_data as guide


EXPECTED_SLUGS = (
    "bahrain", "barcelona", "le-mans", "paul-ricard", "cota", "daytona",
    "fuji", "imola", "interlagos", "lusail", "monza", "portimao",
    "sebring", "silverstone-international", "spa", "laguna-seca",
)
EXPECTED_DLC = {
    "barcelona", "paul-ricard", "cota", "daytona", "imola",
    "interlagos", "lusail", "silverstone-international", "laguna-seca",
}


class LmuGuideDataTests(unittest.TestCase):
    def test_current_official_circuit_snapshot_is_complete_and_ordered(self):
        self.assertEqual(tuple(item.slug for item in guide.CIRCUITS), EXPECTED_SLUGS)
        self.assertEqual(
            {item.slug for item in guide.CIRCUITS if item.is_dlc},
            EXPECTED_DLC,
        )

    def test_each_circuit_has_three_unique_recommendations_per_requested_class(self):
        for circuit in guide.CIRCUITS:
            with self.subTest(circuit=circuit.slug):
                self.assertEqual(len(circuit.lmgt3), 3)
                self.assertEqual(len(circuit.hypercar), 3)
                self.assertEqual(len({item.car_slug for item in circuit.lmgt3}), 3)
                self.assertEqual(len({item.car_slug for item in circuit.hypercar}), 3)
                self.assertTrue(all(guide.CARS[item.car_slug].car_class == "LMGT3" for item in circuit.lmgt3))
                self.assertTrue(all(guide.CARS[item.car_slug].car_class == "Hypercar" for item in circuit.hypercar))

    def test_copy_and_sources_are_complete_without_fastest_claims(self):
        guide.validate_guide_data()
        forbidden = ("绝对最快", "必胜", "guaranteed fastest")
        for circuit in guide.CIRCUITS:
            copy = " ".join((circuit.character, circuit.challenge, circuit.advice))
            self.assertTrue(circuit.source_url.startswith("https://lemansultimate.com/"))
            self.assertFalse(any(token in copy.lower() for token in forbidden))
            for recommendation in (*circuit.lmgt3, *circuit.hypercar):
                self.assertGreaterEqual(len(recommendation.fit), 12)
