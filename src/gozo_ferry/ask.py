"""Answer the staff questions two ways, and score each against the answers worked out by hand (Session 7).

    gozo-ask questions                 both routes, one line per question and route
    gozo-ask questions --route keyword the keyword route only
    gozo-ask questions --show          also list what each route counted, by the log's own wording
    gozo-ask profile                   the log as written: how each port and reason is spelt

The keyword route is what a simple assistant does with the log alone: keep the rows whose port or reason contains
a word from the question. The knowledge route looks the word up in the operator's vocabulary, follows it to a port,
vessel or reason, and from a reason down every level of the taxonomy, to the cancellations.
"""
import argparse
import logging
import os
import sys

from dotenv import load_dotenv

from gozo_ferry.config import load_config
from gozo_ferry.knowledge import (cancellations_for, concepts_for, link_log, load_knowledge, load_log,
                                  load_questions)
from gozo_ferry.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def keyword_rows(question, linked):
    """Rows whose port or reason, as written, contains any of the question's words (any case)."""
    column = f"{question['field']}_as_written"
    pattern = "|".join(question["terms"])
    return linked[linked[column].str.contains(pattern, case=False, regex=True)]


def knowledge_rows(question, linked, kg):
    """The question's words, through the vocabulary, to ports, vessels or reasons, to the cancellations."""
    keys = set()
    for concept_id in concepts_for(question["terms"], kg):
        keys |= set(cancellations_for(concept_id, linked, kg)["key"])
    return linked[linked["key"].isin(keys)]


def most(rows, kg):
    """The vessel with the most rows, by name; tied vessels joined by ' and '; None for no rows."""
    if rows.empty:
        return None
    counts = rows["vessel"].value_counts()
    top = sorted(kg.vessels[v]["name"] for v in counts[counts == counts.max()].index)
    return " and ".join(top)


def answer_from(rows, question, kg):
    return len(rows) if question["kind"] == "count" else most(rows, kg)


def questions(args, config):
    kg = load_knowledge()
    linked = link_log(load_log(config), kg)
    routes = ["keyword", "knowledge"] if args.route == "both" else [args.route]
    wrong = 0
    print(f"{'question':<11} {'route':<10} {'answer':>10} {'expected':>10}  right")
    for q in load_questions():
        for route in routes:
            rows = keyword_rows(q, linked) if route == "keyword" else knowledge_rows(q, linked, kg)
            found = answer_from(rows, q, kg)
            right = found == q["expected"]
            wrong += route == "knowledge" and not right
            print(f"{q['id']:<11} {route:<10} {str(found):>10} {str(q['expected']):>10}  {'yes' if right else 'NO'}")
            if args.show:
                column = f"{q['field']}_as_written"
                counted = rows[column].value_counts()
                print(f"{'':<22}counted: " + ", ".join(f"{k} {v}" for k, v in counted.items()) if len(counted)
                      else f"{'':<22}counted: nothing")
    return 1 if wrong else 0


def profile(config):
    log = load_log(config)
    linked = link_log(log, load_knowledge())
    print(f"cancellations                   {len(log)}, {log['date'].min()} to {log['date'].max()}")
    print(f"days with a cancellation        {log['date'].nunique()}")
    for column in ("departure", "reason", "vessel"):
        print(f"\n{column}: {log[column].nunique()} ways of writing it")
        for value, n in log[column].value_counts().items():
            print(f"  {value:<34} {n:>3}")
    print("\ntimes written without a leading zero:", int((log["time"].str.len() == 4).sum()))
    for key in (["date", "time"], ["date", "vessel"], ["date", "time", "vessel"]):
        print(f"rows sharing {' + '.join(key):<20} {int(log.duplicated(key).sum())}")
    print("\nA keyword search for each spelling of the port (any case):")
    for word in ("Mġarr", "Mgarr"):
        print(f"  {word:<8} {int(log['departure'].str.contains(word, case=False).sum()):>3} rows")
    print(f"  the port itself           {int((linked['port'] == 'mgarr').sum()):>3} rows")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Answer the staff questions and score the answers.")
    sub = parser.add_subparsers(dest="command", required=True)
    q = sub.add_parser("questions")
    q.add_argument("--route", choices=["keyword", "knowledge", "both"], default="both")
    q.add_argument("--show", action="store_true")
    sub.add_parser("profile")
    args = parser.parse_args(argv)

    load_dotenv()
    setup_logging(os.environ.get("LOG_LEVEL", "WARNING"))
    config = load_config()
    try:
        if args.command == "questions":
            sys.exit(questions(args, config))
        sys.exit(profile(config))
    except ValueError as err:
        logger.error("%s", err)
        sys.exit(1)


if __name__ == "__main__":
    main()
