"""Pytest fixtures."""

import pytest


@pytest.fixture
def sample_rubric_dict():
    return {
        "title": "Test Exam",
        "items": [
            {
                "question_number": "Q1",
                "max_marks": 5,
                "key_points": [
                    "Newton's second law F=ma",
                    "Force is proportional to acceleration",
                ],
                "negative_conditions": ["Wrong formula"],
                "partial_credit_rules": [
                    {"condition": "Partial explanation of force", "marks": 2}
                ],
            }
        ],
    }
