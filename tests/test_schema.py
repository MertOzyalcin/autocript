import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schema" / "transcript-v1.json").read_text(encoding="utf-8"))
ORNEK = json.loads((ROOT / "tests" / "fixtures" / "schema" / "ornek-v1.json").read_text(encoding="utf-8"))


@pytest.fixture
def validator():
    Draft202012Validator.check_schema(SCHEMA)
    return Draft202012Validator(SCHEMA)


@pytest.fixture
def doc():
    return copy.deepcopy(ORNEK)


def test_ornek_belge_gecerli(validator, doc):
    assert list(validator.iter_errors(doc)) == []


def test_segment_zamanlama_null_kelime_gecerli(validator, doc):
    doc["timing"] = "segment"
    doc["engine"]["route"] = "gemini_youtube"
    for w in doc["words"]:
        w["start"] = None
        w["end"] = None
        w["confidence"] = None
        w["low_confidence"] = False
    assert list(validator.iter_errors(doc)) == []


def test_word_zamanlama_null_start_gecersiz(validator, doc):
    doc["words"][0]["start"] = None
    assert not validator.is_valid(doc)


def test_segment_zamanlama_sayili_start_gecersiz(validator, doc):
    doc["timing"] = "segment"
    for w in doc["words"]:
        w["confidence"] = None
    assert not validator.is_valid(doc)


def test_confidence_aralik_disi_gecersiz(validator, doc):
    doc["words"][0]["confidence"] = 1.2
    assert not validator.is_valid(doc)


def test_non_speech_kind_gecersiz(validator, doc):
    doc["non_speech"][0]["kind"] = "noise"
    assert not validator.is_valid(doc)


def test_schema_version_zorunlu(validator, doc):
    del doc["schema_version"]
    assert not validator.is_valid(doc)


def test_schema_version_2_gecersiz(validator, doc):
    doc["schema_version"] = "2.0"
    assert not validator.is_valid(doc)


def test_bilinmeyen_ust_alan_gecersiz(validator, doc):
    doc["foo"] = 1
    assert not validator.is_valid(doc)


def test_range_uc_elemanli_gecersiz(validator, doc):
    doc["segments"][0]["word_range"] = [0, 1, 2]
    assert not validator.is_valid(doc)
