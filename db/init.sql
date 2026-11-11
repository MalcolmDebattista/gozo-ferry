-- Runs once, when the database is first created
CREATE TABLE predictions (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    wind_knots DOUBLE PRECISION NOT NULL,   -- as received from the caller
    probability DOUBLE PRECISION NOT NULL,
    warning BOOLEAN NOT NULL,
    model_version TEXT NOT NULL
);
