from prometheus_client import Counter, Histogram

# Same metric names as the shop model, so the provided Grafana dashboard works unchanged
PREDICTIONS = Counter(
    "predictions",
    "Number of predictions served",
)
LATENCY = Histogram(
    "prediction_latency_seconds",
    "Time taken to answer a prediction request",
)
INPUTS = Histogram(
    "prediction_input",
    "Input values received (here: forecast wind speed in knots)",
    buckets=[5, 10, 15, 20, 25, 30, 35, 40, 50, 60],
)
