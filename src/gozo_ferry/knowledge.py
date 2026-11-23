"""The ferry operator's knowledge, read from the files in kg/ (Session 7, Stage 16).

The files of Gozo ferry knowledge v1.0 hold what the operations log alone cannot say:
    kg/schema.yaml     the classes, properties and relationships, with cardinalities; the files conform to it
    kg/ports.yaml      the two ports, each with every spelling the log uses
    kg/vessels.yaml    the fleet
    kg/reasons.yaml    the reasons, each a kind of its broader reason (a gale warning is wind, wind is weather)
    kg/synonyms.yaml   the words staff use in questions, each mapped to a port, a vessel or a reason
    kg/questions.yaml  the competency questions, with the answers worked out by hand

The operations log (data/gozo_operations_2025.csv) is data, written by staff on duty: one row per cancelled
crossing, with the date, the time, the vessel, the port of departure and the reason, as they wrote them. It does
not change gozo_ferry.csv or the frozen holdout, which the model and the gate depend on.
"""
import logging
from dataclasses import dataclass

import pandas as pd
import yaml

logger = logging.getLogger(__name__)

SCHEMA_PATH = "kg/schema.yaml"
PORTS_PATH = "kg/ports.yaml"
VESSELS_PATH = "kg/vessels.yaml"
REASONS_PATH = "kg/reasons.yaml"
SYNONYMS_PATH = "kg/synonyms.yaml"
QUESTIONS_PATH = "kg/questions.yaml"


@dataclass
class Knowledge:
    """Everything the operator knows about ports, vessels and reasons, read once from kg/."""
    ports: dict
    vessels: dict
    reasons: dict
    synonyms: dict


def _read_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_log(config):
    """The operations log as written: every value a string, nothing guessed."""
    return pd.read_csv(config["operations_path"], dtype=str, keep_default_na=False, encoding="utf-8")


def load_schema(path=SCHEMA_PATH):
    return _read_yaml(path)


def load_questions(path=QUESTIONS_PATH):
    return _read_yaml(path)["questions"]


def load_knowledge():
    return Knowledge(ports={p["id"]: p for p in _read_yaml(PORTS_PATH)["ports"]},
                     vessels={v["id"]: v for v in _read_yaml(VESSELS_PATH)["vessels"]},
                     reasons={r["id"]: r for r in _read_yaml(REASONS_PATH)["reasons"]},
                     synonyms=_read_yaml(SYNONYMS_PATH)["terms"])


def label_index(items):
    """Every label as written in the log, to the identifier it names. A label claimed twice is an error."""
    index = {}
    for item_id, item in items.items():
        for label in item.get("labels", []):
            if label in index:
                raise ValueError(f"Label {label!r} names both {index[label]} and {item_id}")
            index[label] = item_id
    return index


def normalise_time(text):
    """Staff wrote 5:00 as well as 05:00: the same scheduled departure, so one form, HH:MM."""
    hours, minutes = text.strip().split(":")
    return f"{int(hours):02d}:{int(minutes):02d}"


def cancellation_key(row):
    """A cancellation is one scheduled crossing that did not sail: a vessel can make one crossing at a time, so the
    date, the scheduled time and the vessel name it (ADR 0001). The date and time alone are not enough: twice in
    2025 two vessels were cancelled at the same time, one from each port."""
    return f"{row['date']}|{row['time']}|{row['vessel']}"


def link_log(log, kg):
    """Replace what staff wrote with the identifiers it means: port, vessel and reason, matched exactly against
    the labels in kg/. Any value with no match is an error, listed in full, rather than a guess."""
    linked = log.rename(columns={"departure": "departure_as_written", "reason": "reason_as_written",
                                 "vessel": "vessel_as_written"})
    linked["time"] = linked["time"].map(normalise_time)
    problems = []
    for column, items, written in (("port", kg.ports, "departure_as_written"),
                                   ("vessel", kg.vessels, "vessel_as_written"),
                                   ("reason", kg.reasons, "reason_as_written")):
        linked[column] = linked[written].map(label_index(items))
        unknown = sorted(linked.loc[linked[column].isna(), written].unique())
        if unknown:
            problems.append(f"{written.split('_')[0]} not in kg/: {unknown}")
    if problems:
        raise ValueError("; ".join(problems))
    linked["key"] = linked.apply(cancellation_key, axis=1)
    return linked


def narrower(hierarchy, broad_id):
    """The reason and every reason that is a kind of it, at any depth."""
    found = {broad_id}
    changed = True
    while changed:
        changed = False
        for item_id, item in hierarchy.items():
            if item.get("is_a") in found and item_id not in found:
                found.add(item_id)
                changed = True
    return found


def concepts_for(terms, kg):
    """The ports, vessels and reasons the staff's words mean, through the vocabulary."""
    return {kg.synonyms[t.lower()] for t in terms if t.lower() in kg.synonyms}


def cancellations_for(concept_id, linked, kg):
    """The cancellations a concept covers: from a port, on a vessel, or for a reason or any narrower one."""
    if concept_id in kg.ports:
        return linked[linked["port"] == concept_id]
    if concept_id in kg.vessels:
        return linked[linked["vessel"] == concept_id]
    return linked[linked["reason"].isin(narrower(kg.reasons, concept_id))]


def instances(kg):
    """The instances of each class in the schema, by key (the log's cancellations are data, not knowledge)."""
    return {"Port": set(kg.ports), "Vessel": set(kg.vessels), "Reason": set(kg.reasons), "Term": set(kg.synonyms)}


def relationships(kg):
    """Every relationship the knowledge files state, as (name, from, to) triples of keys."""
    rels = [("BROADER", r, v["is_a"]) for r, v in kg.reasons.items() if v.get("is_a")]
    rels += [("MEANS", t, c) for t, c in kg.synonyms.items()]
    return rels


def check_against_schema(kg, schema=None):
    """Check every relationship in the knowledge files against the schema: the class at each end, and how many each
    instance has. Returns a list of violations, empty when the files conform."""
    schema = schema or load_schema()
    inst = instances(kg)
    rels = relationships(kg)
    violations = []
    for spec in schema["relationships"]:
        if spec["from"] == "Cancellation":
            continue  # cancellations are data, linked by link_log, not knowledge files
        allowed = set().union(*(inst[c] for c in spec["to"]))
        found = [(a, b) for name, a, b in rels if name == spec["name"] and a in inst[spec["from"]]]
        for a, b in found:
            if b not in allowed:
                violations.append(f"{spec['name']} from {a} to {b}: {b} is not a {' or '.join(spec['to'])}")
        counts = pd.Series([a for a, b in found if b in allowed], dtype=object).value_counts()
        for a in sorted(inst[spec["from"]]):
            n = int(counts.get(a, 0))
            if n < spec["min"] or (spec["max"] is not None and n > spec["max"]):
                bounds = f"{spec['min']}..{spec['max'] if spec['max'] is not None else '*'}"
                violations.append(f"{spec['from']} {a} has {n} {spec['name']}, expected {bounds}")
    return violations
