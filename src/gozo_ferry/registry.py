"""Register runs and move aliases in the MLflow model registry (Session 6, Stage 14).

  gozo-registry register            register the run gozo-train just recorded, only if it passed the gate
                                    and came from committed code
  gozo-registry alias champion 2    point the champion alias at version 2
  gozo-registry card 2 docs/model_card.md   attach the model card to version 2
  gozo-registry show                list versions and aliases
"""
import argparse
import logging
import os
import sys
from pathlib import Path

import mlflow
from dotenv import load_dotenv
from mlflow import MlflowClient

from gozo_ferry.config import load_config
from gozo_ferry.logging_setup import setup_logging
from gozo_ferry.train import LAST_RUN

logger = logging.getLogger(__name__)


def register(client, config, run_id=None):
    """Register one run: the one named, or the last one gozo-train recorded on this machine."""
    if run_id is None:
        if not Path(LAST_RUN).exists():
            logger.error("No run recorded here yet: run gozo-train first, or pass --run-id")
            return 1
        run_id = Path(LAST_RUN).read_text().strip()
    run = client.get_run(run_id)
    if run.data.tags.get("gate_passed") != "true":
        logger.error("Run %s failed the gate: tracked, but not registered", run_id)
        return 1
    if run.data.tags.get("git_dirty") == "true":
        logger.error("Run %s came from uncommitted changes: commit, train again, then register", run_id)
        return 1
    version = mlflow.register_model(run.data.tags["model_uri"], config["mlflow"]["model_name"])
    logger.info("Registered run %s as %s version %s", run_id, version.name, version.version)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Work with the Gozo ferry model registry.")
    sub = parser.add_subparsers(dest="command", required=True)
    reg = sub.add_parser("register")
    reg.add_argument("--run-id")
    alias = sub.add_parser("alias")
    alias.add_argument("name")
    alias.add_argument("version")
    card = sub.add_parser("card")
    card.add_argument("version")
    card.add_argument("path")
    sub.add_parser("show")
    args = parser.parse_args(argv)

    load_dotenv()
    setup_logging(os.environ.get("LOG_LEVEL", "INFO"))
    config = load_config()
    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", config["mlflow"]["tracking_uri"]))
    client = MlflowClient()
    name = config["mlflow"]["model_name"]

    if args.command == "register":
        sys.exit(register(client, config, args.run_id))
    if args.command == "alias":
        client.set_registered_model_alias(name, args.name, args.version)
        logger.info("%s@%s -> version %s", name, args.name, args.version)
    elif args.command == "card":
        client.update_model_version(name, args.version, description=Path(args.path).read_text())
        logger.info("Model card attached to %s version %s", name, args.version)
    elif args.command == "show":
        if not client.search_registered_models(filter_string=f"name='{name}'"):
            logger.error("No model called %s is registered yet: run make register", name)
            sys.exit(1)
        aliases = {}
        for alias_name, version in client.get_registered_model(name).aliases.items():
            aliases.setdefault(version, []).append(alias_name)
        for v in sorted(client.search_model_versions(f"name='{name}'"), key=lambda v: int(v.version)):
            run = client.get_run(v.run_id)
            metric = run.data.metrics.get(f"holdout_{config['gate_metric']}", float("nan"))
            precision = run.data.metrics.get("holdout_precision", float("nan"))
            print(f"version {v.version:>3}  {config['gate_metric']} {metric:.3f}  precision {precision:.3f}  "
                  f"train_start {run.data.params.get('train_start'):<10}  {' '.join(aliases.get(v.version, []))}")
    sys.exit(0)


if __name__ == "__main__":
    main()
