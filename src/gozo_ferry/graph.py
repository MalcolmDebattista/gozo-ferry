"""The ferry operator's knowledge layer as an RDF graph (Session 7, Stage 17).

    gozo-kg load    add the knowledge files and the operations log to the graph store, kg/build/gozo.nt
    gozo-kg count   triples in the store, instances of each class, uses of each property, and the store's SHA-256
    gozo-kg ask     answer the staff questions in SPARQL and check them, as gozo-ask does
    gozo-kg check   what make ci runs: build the store from nothing, load it again, require the same SHA-256, and
                    answer every question from the store as written

The store is a file of N-Triples, one triple per line, written in sorted order: the same content always gives the
same file, and so the same SHA-256. Loading adds to what the store already holds. It is idempotent because every
resource is named by an IRI minted from its key, and a graph is a set of triples: adding a triple the graph already
holds changes nothing. A cancellation's key is its date, scheduled time and vessel (ADR 0001).

How the vocabulary is written in SKOS:
    skos:prefLabel   the official name (Mġarr, Gale warning)
    skos:altLabel    every way the operations log writes it, as written (MGARR, Mgarr Harbour, gale warning)
    skos:hiddenLabel the words staff use in questions (kg/synonyms.yaml): found by search, never displayed
"""
import argparse
import hashlib
import logging
import os
import sys
from pathlib import Path

from rdflib import RDF, RDFS, XSD, Graph, Literal, Namespace
from rdflib.namespace import OWL, SKOS

from gozo_ferry.config import load_config
from gozo_ferry.knowledge import link_log, load_knowledge, load_log, load_questions, load_schema
from gozo_ferry.logging_setup import setup_logging

logger = logging.getLogger(__name__)

STORE_PATH = Path("kg/build/gozo.nt")

# Every IRI the operator mints starts here. example.org is reserved for examples, so it can never clash with a real
# site.
GOZO = Namespace("https://ari3217.example.org/gozo/")
REASONS = GOZO["scheme/reasons"]
# The graph says which release of the knowledge it was built from, so any answer can be traced to a release.
RELEASE = GOZO["knowledge"]


# One function per kind of resource: the IRI is the key, so the same thing always gets the same name.
def port_iri(port_id):
    return GOZO[f"port/{port_id}"]


def vessel_iri(vessel_id):
    return GOZO[f"vessel/{vessel_id}"]


def reason_iri(reason_id):
    return GOZO[f"reason/{reason_id}"]


def cancellation_iri(row):
    """date / time without the colon / vessel id: 2025-01-05/0500/dwejra."""
    return GOZO[f"cancellation/{row['date']}/{row['time'].replace(':', '')}/{row['vessel']}"]


def concept_iri(concept_id, kg):
    if concept_id in kg.ports:
        return port_iri(concept_id)
    if concept_id in kg.vessels:
        return vessel_iri(concept_id)
    return reason_iri(concept_id)


def add_knowledge(g, kg, linked, version=None):
    """Add the knowledge files and the linked operations log to the graph g, as triples."""
    g.bind("gozo", GOZO)
    g.bind("skos", SKOS)
    g.bind("owl", OWL)
    g.add((RELEASE, RDF.type, GOZO.KnowledgeRelease))
    g.add((RELEASE, OWL.versionInfo, Literal(version or load_schema()["version"])))

    for pid, p in kg.ports.items():
        node = port_iri(pid)
        g.add((node, RDF.type, GOZO.Port))
        g.add((node, SKOS.prefLabel, Literal(p["name"], lang="mt")))
        g.add((node, GOZO.island, Literal(p["island"])))
        for label in p.get("labels", []):
            g.add((node, SKOS.altLabel, Literal(label)))
    for vid, v in kg.vessels.items():
        node = vessel_iri(vid)
        g.add((node, RDF.type, GOZO.Vessel))
        g.add((node, SKOS.prefLabel, Literal(v["name"])))
        for label in v.get("labels", []):
            g.add((node, SKOS.altLabel, Literal(label)))

    # The reasons are one SKOS concept scheme. skos:broader says "is a kind of".
    g.add((REASONS, RDF.type, SKOS.ConceptScheme))
    g.add((REASONS, SKOS.prefLabel, Literal("Reasons a crossing is cancelled", lang="en")))
    for rid, r in kg.reasons.items():
        node = reason_iri(rid)
        g.add((node, RDF.type, SKOS.Concept))
        g.add((node, RDF.type, GOZO.Reason))
        g.add((node, SKOS.prefLabel, Literal(r["name"], lang="en")))
        g.add((node, SKOS.inScheme, REASONS))
        if r.get("is_a"):
            g.add((node, SKOS.broader, reason_iri(r["is_a"])))
        else:
            g.add((node, SKOS.topConceptOf, REASONS))
        for label in r.get("labels", []):
            g.add((node, SKOS.altLabel, Literal(label)))

    # The staff vocabulary: each word a hidden label of what it means, so a search finds it.
    for term, target in kg.synonyms.items():
        g.add((concept_iri(target, kg), SKOS.hiddenLabel, Literal(term)))

    for row in linked.to_dict("records"):
        node = cancellation_iri(row)
        g.add((node, RDF.type, GOZO.Cancellation))
        g.add((node, GOZO.date, Literal(row["date"], datatype=XSD.date)))
        g.add((node, GOZO.scheduledTime, Literal(f"{row['time']}:00", datatype=XSD.time)))
        g.add((node, GOZO.departsFrom, port_iri(row["port"])))
        g.add((node, GOZO.onVessel, vessel_iri(row["vessel"])))
        g.add((node, GOZO.becauseOf, reason_iri(row["reason"])))
        # What staff wrote stays in the graph, beside what it was taken to mean.
        g.add((node, RDFS.comment, Literal(f"{row['departure_as_written']}; {row['reason_as_written']}")))
    return g


def open_store(path=STORE_PATH):
    g = Graph()
    g.bind("gozo", GOZO)
    g.bind("skos", SKOS)
    if path.exists():
        g.parse(path, format="nt")
    return g


def save_store(g, path=STORE_PATH):
    """Write the graph as sorted N-Triples, so that the same graph always gives the same file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = sorted(line for line in g.serialize(format="nt").splitlines() if line.strip())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs(config):
    kg = load_knowledge()
    return kg, link_log(load_log(config), kg)


def load(config):
    kg, linked = inputs(config)
    g = open_store()
    before = len(g)
    add_knowledge(g, kg, linked)
    fingerprint = save_store(g)
    logger.info("Store %s: %d triples before, %d after", STORE_PATH, before, len(g))
    print(f"triples before {before}, after {len(g)}; sha256 {fingerprint[:16]}")


PREFIXES = """
PREFIX gozo: <https://ari3217.example.org/gozo/>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
"""

COUNT_CLASSES = PREFIXES + """
SELECT ?class (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a ?class }
GROUP BY ?class ORDER BY ?class
"""

COUNT_PROPERTIES = PREFIXES + """
SELECT ?property (COUNT(*) AS ?n) WHERE { ?s ?property ?o }
GROUP BY ?property ORDER BY ?property
"""


def count(g):
    print(f"{'triples':<24} {len(g):>6}")
    for row in g.query(COUNT_CLASSES):
        print(f"{g.qname(row['class']):<24} {int(row['n']):>6}")
    for row in g.query(COUNT_PROPERTIES):
        print(f"{g.qname(row['property']):<24} {int(row['n']):>6}")
    for version in sorted(str(v) for v in g.objects(RELEASE, OWL.versionInfo)):
        print(f"{'release':<24} {version:>6}")
    if STORE_PATH.exists():
        print(f"{'sha256':<24} {hashlib.sha256(STORE_PATH.read_bytes()).hexdigest()[:16]}")


# From the question's words, through the vocabulary (skos:hiddenLabel), to a port, a vessel or a reason; and from a
# reason down the scheme to any depth: skos:broader* follows zero or more steps, zero for the reason itself.
# The port is reached through its IRI, never through a spelling, so every way the log writes Mġarr counts.
COVERS = """
  VALUES ?term { %(terms)s }
  ?concept skos:hiddenLabel ?term .
  { ?c gozo:departsFrom ?concept }
  UNION { ?c gozo:onVessel ?concept }
  UNION { ?c gozo:becauseOf/skos:broader* ?concept }
"""

COUNT = PREFIXES + """
SELECT (COUNT(DISTINCT ?c) AS ?n) WHERE {
""" + COVERS + """
}
"""

MOST = PREFIXES + """
SELECT ?name (COUNT(DISTINCT ?c) AS ?n) WHERE {
""" + COVERS + """
  ?c gozo:onVessel/skos:prefLabel ?name .
}
GROUP BY ?name
ORDER BY DESC(?n) ?name
"""


def terms_of(question):
    return " ".join(Literal(t.lower()).n3() for t in question["terms"])


def answer(g, question):
    """The answer to one competency question, from the graph alone."""
    if question["kind"] == "count":
        return int(next(iter(g.query(COUNT % {"terms": terms_of(question)})))["n"])
    rows = [(str(r["name"]), int(r["n"])) for r in g.query(MOST % {"terms": terms_of(question)})]
    if not rows:
        return None
    top = rows[0][1]
    return " and ".join(sorted(name for name, n in rows if n == top))


def ask(g):
    print(f"{'question':<11} {'route':<10} {'answer':>10} {'expected':>10}  right")
    wrong = 0
    for q in load_questions():
        found = answer(g, q)
        right = found == q["expected"]
        wrong += not right
        print(f"{q['id']:<11} {'graph':<10} {str(found):>10} {str(q['expected']):>10}  {'yes' if right else 'NO'}")
    return 1 if wrong else 0


def check(config):
    """Build the store from nothing, load the same release again, and require that the store does not change; then
    answer every question from the store as it was written to disk, so that what is checked is the artefact."""
    kg, linked = inputs(config)
    STORE_PATH.unlink(missing_ok=True)
    g = open_store()
    add_knowledge(g, kg, linked)
    first, size = save_store(g), len(g)
    g = open_store()
    add_knowledge(g, kg, linked)
    second = save_store(g)
    version = load_schema()["version"]
    print(f"release {version}: {size} triples, {len(g)} after a second load; sha256 {first[:16]}, then {second[:16]}")
    if second != first:
        print("The second load changed the store: some resource is not named by its key.", file=sys.stderr)
        return 1
    return ask(open_store())


def main(argv=None):
    parser = argparse.ArgumentParser(description="The ferry operator's knowledge layer as an RDF graph.")
    parser.add_argument("command", choices=["load", "count", "ask", "check"])
    args = parser.parse_args(argv)
    setup_logging(os.environ.get("LOG_LEVEL", "WARNING"))
    config = load_config()
    if args.command == "load":
        load(config)
        return 0
    if args.command == "check":
        return check(config)
    if not STORE_PATH.exists():
        print(f"No graph store yet at {STORE_PATH}: run make kg-load first.", file=sys.stderr)
        return 1
    g = open_store()
    if args.command == "count":
        count(g)
        return 0
    return ask(g)


if __name__ == "__main__":
    sys.exit(main())
