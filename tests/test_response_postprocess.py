from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from response_postprocess import enforce_coach_style  # noqa: E402


class ResponsePostprocessTests(unittest.TestCase):
    def test_summary_dump_is_rewritten_into_coach_style(self) -> None:
        text = (
            "Common math topics for K-12 students include understanding place value, "
            "adding and subtracting multi-digit numbers, and geometry."
        )

        result = enforce_coach_style("what is this about", text)

        self.assertNotIn("Common math topics", result)
        self.assertTrue(result.endswith("?"))

    def test_confirmation_question_gets_direct_answer_first(self) -> None:
        text = "You can check your work by multiplying."

        result = enforce_coach_style("so I was right, correct?", text)

        self.assertTrue(result.startswith("Yes, you're right.") or result.startswith("Not quite."))
        self.assertTrue(result.endswith("?"))

    def test_help_seeking_question_gets_concrete_step(self) -> None:
        text = "Common math topics for K-12 students include geometry and fractions."

        result = enforce_coach_style("what do I do then", text)

        self.assertTrue(result.startswith("Start with one small step."))
        self.assertTrue(result.endswith("?"))


if __name__ == "__main__":
    unittest.main()
