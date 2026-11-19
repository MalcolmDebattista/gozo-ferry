FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml .
COPY src ./src
COPY config ./config
RUN pip install --no-cache-dir --no-deps .

# Session 6, Stage 15: the image holds code only. The model comes from the registry when the API starts
# (MODEL_URI, models:/gozo_ferry@champion by default), so a new model needs no new image.

# The code's version comes from pyproject.toml through `make build`; /ready reports it.
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

EXPOSE 8888
# Exec form: uvicorn runs as PID 1 and gets SIGTERM directly, so docker stop is immediate
CMD ["uvicorn", "gozo_ferry.api:app", "--host", "0.0.0.0", "--port", "8888"]
