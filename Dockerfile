FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure required directories exist in the container
RUN mkdir -p /app/static /app/templates

# Explicitly copy application assets
COPY static /app/static
COPY templates /app/templates

ENV LOCALSHARE_DATA_DIR=/data

EXPOSE 8000

CMD ["python", "main.py"]
