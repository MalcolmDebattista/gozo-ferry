"""Send a steady stream of prediction requests to a model API.

Provided for ARI3217 Session 4. Uses only the Python standard library,
so it runs with any Python 3, without a virtual environment.

Examples:
    python3 monitoring/traffic.py --field price --mean 23 --sd 12
    python3 monitoring/traffic.py --field price --mean 35 --sd 12
    python3 monitoring/traffic.py --field wind --mean 12 --sd 5 --rate 2
"""

import argparse
import json
import random
import time
import urllib.error
import urllib.request


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://localhost:8888/predict",
                        help="prediction endpoint")
    parser.add_argument("--field", default="price",
                        help="name of the input field in the request")
    parser.add_argument("--mean", type=float, default=23.0,
                        help="mean of the input values")
    parser.add_argument("--sd", type=float, default=12.0,
                        help="standard deviation of the input values")
    parser.add_argument("--minimum", type=float, default=1.0,
                        help="smallest value sent")
    parser.add_argument("--rate", type=float, default=5.0,
                        help="requests per second")
    parser.add_argument("--duration", type=float, default=120.0,
                        help="how long to run, in seconds")
    parser.add_argument("--seed", type=int, default=None,
                        help="random seed, for a repeatable stream")
    return parser.parse_args()


def send(url, field, value):
    body = json.dumps({field: round(value, 2)}).encode()
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status


def main():
    args = parse_args()
    rng = random.Random(args.seed)
    pause = 1.0 / args.rate
    end = time.monotonic() + args.duration
    sent = failed = 0
    next_report = time.monotonic() + 10
    print(f"Sending {args.field} ~ N({args.mean}, {args.sd}) "
          f"at {args.rate}/s for {args.duration:.0f}s to {args.url}")
    while time.monotonic() < end:
        started = time.monotonic()
        value = max(args.minimum, rng.gauss(args.mean, args.sd))
        try:
            send(args.url, args.field, value)
            sent += 1
        except (urllib.error.URLError, OSError) as error:
            failed += 1
            if failed == 1:
                print(f"Request failed: {error}")
        if time.monotonic() >= next_report:
            print(f"{sent} sent, {failed} failed")
            next_report += 10
        time.sleep(max(0.0, pause - (time.monotonic() - started)))
    print(f"Done: {sent} sent, {failed} failed")


if __name__ == "__main__":
    main()
