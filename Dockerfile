FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway injects PORT at runtime; config.py reads it. Volume (if attached)
# should be mounted at /data, matched by LOCALSHARE_DATA_DIR below.
ENV LOCALSHARE_DATA_DIR=/data

EXPOSE 8000

CMD ["python", "main.py"]
