FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml .
COPY src ./src
COPY config ./config
COPY data ./data
RUN pip install --no-cache-dir --no-deps .

RUN gozo-train

# The version comes from pyproject.toml through `make build`; the API reports it.
ARG MODEL_VERSION=dev
ENV MODEL_VERSION=${MODEL_VERSION}

EXPOSE 8888
# Exec form: uvicorn runs as PID 1 and gets SIGTERM directly, so docker stop is immediate
CMD ["uvicorn", "gozo_ferry.api:app", "--host", "0.0.0.0", "--port", "8888"]
