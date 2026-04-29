import unittest

from jobfleet.text import has_excluded_seniority, is_india_job, parse_experience, role_score


class ExperienceParsingTests(unittest.TestCase):
    def test_unspecified_is_allowed(self):
        allowed, exp, note = parse_experience("Build dashboards and partner with business teams.")
        self.assertTrue(allowed)
        self.assertEqual(exp, "Unspecified")
        self.assertEqual(note, "")

    def test_overlapping_range_is_allowed(self):
        allowed, exp, _note = parse_experience("Requires 2-5 years of analytics experience.")
        self.assertTrue(allowed)
        self.assertEqual(exp, "2-5 years")

    def test_minimum_four_is_rejected(self):
        allowed, exp, note = parse_experience("Minimum 4 years of market research experience required.")
        self.assertFalse(allowed)
        self.assertIn("4", exp)
        self.assertIn("above 3", note)

    def test_three_plus_is_allowed(self):
        allowed, exp, _note = parse_experience("3+ years of experience with SQL preferred.")
        self.assertTrue(allowed)
        self.assertEqual(exp, "3+ years")


class IndiaFilterTests(unittest.TestCase):
    def test_india_location(self):
        self.assertTrue(is_india_job("Bengaluru, India"))

    def test_non_india_location(self):
        self.assertFalse(is_india_job("London, United Kingdom"))

    def test_non_india_location_wins_over_description_noise(self):
        self.assertFalse(is_india_job("Canada", "This company also has offices in India."))


class SeniorityFilterTests(unittest.TestCase):
    def test_sr_abbreviations_are_excluded(self):
        self.assertTrue(has_excluded_seniority("Sr. Business Analyst"))
        self.assertTrue(has_excluded_seniority("Sr Business Analyst"))

    def test_senior_titles_are_excluded(self):
        self.assertTrue(has_excluded_seniority("Senior Data Analyst"))
        self.assertTrue(has_excluded_seniority("Lead Research Analyst"))

    def test_regular_analyst_titles_are_allowed(self):
        self.assertFalse(has_excluded_seniority("Business Analyst"))
        self.assertFalse(has_excluded_seniority("Research Associate"))


class RoleScoringTests(unittest.TestCase):
    def test_reordered_operations_title_matches(self):
        score, matches = role_score(
            "Analyst - Finance Operations",
            "Intermediate working knowledge of MS Excel.",
            ["Finance Operations Analyst"],
            ["excel"],
        )
        self.assertGreaterEqual(score, 45)
        self.assertIn("Finance Operations Analyst", matches)


if __name__ == "__main__":
    unittest.main()
