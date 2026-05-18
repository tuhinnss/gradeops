"""Tests for rubric parsing."""

import json
from pathlib import Path

import pytest

from app.schemas.rubric import RubricSchema
from app.services.rubric_parser import RubricParser


def test_parse_json_rubric(sample_rubric_dict, tmp_path):
    path = tmp_path / "rubric.json"
    path.write_text(json.dumps(sample_rubric_dict), encoding="utf-8")

    parser = RubricParser()
    schema = parser.parse_json(path)

    assert len(schema.items) == 1
    assert schema.items[0].question_number == "Q1"
    assert schema.items[0].max_marks == 5
    assert len(schema.items[0].key_points) == 2


def test_rubric_schema_from_dict(sample_rubric_dict):
    schema = RubricSchema.from_dict(sample_rubric_dict)
    assert schema.title == "Test Exam"
    assert schema.items[0].partial_credit_rules[0].marks == 2
