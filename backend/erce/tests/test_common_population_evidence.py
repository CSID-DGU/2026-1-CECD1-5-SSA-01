import unittest
from backend.erce.common_population_evidence import population_series, common_population_rows


class CommonPopulationTests(unittest.TestCase):
    def test_age_and_sex_sums(self):
        total=population_series("total_population",2025,5)
        adult=population_series("adult_population",2025,5)
        child=population_series("under18_population",2025,5)
        self.assertEqual(total,[a+b for a,b in zip(adult,child)])
        self.assertEqual(adult,[a+b for a,b in zip(population_series("age18_64_population",2025,5),population_series("age65_population",2025,5))])
        self.assertEqual(total,[a+b for a,b in zip(population_series("total_population",2025,5,"male"),population_series("total_population",2025,5,"female"))])
        self.assertEqual(population_series("under18_population",2026,1),[6358318])

    def test_versioned_rows_and_unsupported_period(self):
        rows=common_population_rows()
        self.assertEqual(len(rows),135)
        self.assertTrue(all(r["source_class"]=="official_standard" and r["population_vintage"]=="2023-12" for r in rows))
        self.assertEqual(population_series("age65_population",2031,1),[13417660])
        for args in (("adult_population",2032,1),("unknown",2025,5),("adult_population",2025,5,"unknown")):
            with self.assertRaises(ValueError):population_series(*args)
