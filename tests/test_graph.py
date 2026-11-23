"""The ferry knowledge layer as an RDF graph (Session 7, Stage 17). These tests need no server: the graph is built in
memory from the same files and log that make kg-load uses."""
import pytest
from rdflib import Graph, Literal
from rdflib.namespace import OWL, SKOS

from gozo_ferry.config import load_config
from gozo_ferry.graph import RELEASE, add_knowledge, answer, inputs, port_iri, save_store
from gozo_ferry.knowledge import load_questions, load_schema


@pytest.fixture(scope="module")
def built():
    return inputs(load_config())


@pytest.fixture(scope="module")
def graph(built):
    return add_knowledge(Graph(), *built)


def test_loading_twice_changes_nothing(built):
    g = add_knowledge(Graph(), *built)
    once = len(g)
    add_knowledge(g, *built)
    assert len(g) == once


def test_the_same_graph_always_gives_the_same_store(built, tmp_path):
    first = save_store(add_knowledge(Graph(), *built), tmp_path / "a.nt")
    second = save_store(add_knowledge(Graph(), *built), tmp_path / "b.nt")
    assert first == second


def test_every_cancellation_gets_its_own_iri(graph):
    from gozo_ferry.graph import GOZO
    assert len(set(graph.subjects(predicate=None, object=GOZO.Cancellation))) == 77


def test_every_spelling_of_mgarr_is_an_alternative_label_of_one_port(graph):
    for spelling in ("Mġarr", "Mgarr", "mgarr", "MGARR", "Mgarr Harbour", "Mġarr, Gozo"):
        assert set(graph.subjects(SKOS.altLabel, Literal(spelling))) == {port_iri("mgarr")}


def test_sparql_gives_the_expected_answers(graph):
    for q in load_questions():
        assert answer(graph, q) == q["expected"], q["id"]


def test_the_graph_states_the_release_it_was_built_from(graph):
    assert [str(v) for v in graph.objects(RELEASE, OWL.versionInfo)] == [load_schema()["version"]]
