"""The ferry knowledge files must conform to their schema, link every row of the operations log, and answer the
competency questions, where a keyword search does not (Session 7, Stage 16)."""
import hashlib

import pytest

from gozo_ferry.ask import answer_from, keyword_rows, knowledge_rows
from gozo_ferry.config import load_config
from gozo_ferry.knowledge import check_against_schema, label_index, link_log, load_knowledge, load_log, load_questions

# The data the earlier sessions were built on must not change: the model, the gate and the monitoring depend on
# it. The operations log is added beside it, and pinned too, because the expected answers were worked out from it.
DATA_SHA256 = {
    "data/gozo_ferry.csv": "ebd606dde638a982a5d3be651e8e2a38af81222217a229d4d558b02d8d0f74ba",
    "data/holdout.csv": "fa8745708256b933415deaca764ce549328e69344b15280cccc7fa06dfc3d91d",
    "data/gozo_operations_2025.csv": "04ad294553946908ca87bcd9d2a28e35898b71c45b626ca251fd893b563f06af",
}


@pytest.fixture(scope="module")
def kg():
    return load_knowledge()


@pytest.fixture(scope="module")
def linked(kg):
    return link_log(load_log(load_config()), kg)  # raises if a port, vessel or reason is written in an unknown way


@pytest.mark.parametrize("path", sorted(DATA_SHA256))
def test_the_data_files_are_unchanged(path):
    with open(path, "rb") as f:
        assert hashlib.sha256(f.read()).hexdigest() == DATA_SHA256[path]


def test_the_knowledge_files_conform_to_the_schema(kg):
    assert check_against_schema(kg) == []


def test_every_row_of_the_log_links_to_a_port_vessel_and_reason(linked):
    assert linked[["port", "vessel", "reason"]].notna().all().all()
    assert len(linked) == 77


def test_the_cancellation_key_is_unique(linked):
    assert linked["key"].is_unique


def test_no_label_names_two_things(kg):
    for items in (kg.ports, kg.vessels, kg.reasons):
        label_index(items)  # raises on a label claimed twice


def test_every_staff_word_names_something_known(kg):
    known = set(kg.ports) | set(kg.vessels) | set(kg.reasons)
    assert set(kg.synonyms.values()) <= known


def test_the_reason_taxonomy_has_no_cycles(kg):
    for start in kg.reasons:
        seen, current = set(), start
        while current is not None:
            assert current not in seen, f"cycle through {current}"
            seen.add(current)
            current = kg.reasons[current].get("is_a")


def test_the_knowledge_route_gives_the_expected_answers(kg, linked):
    for q in load_questions():
        assert answer_from(knowledge_rows(q, linked, kg), q, kg) == q["expected"], q["id"]


def test_a_keyword_search_does_not(kg, linked):
    """The reason for the knowledge layer: on the log alone, every question gets a wrong answer."""
    for q in load_questions():
        assert answer_from(keyword_rows(q, linked), q, kg) != q["expected"], q["id"]
