FROM python:3.12-slim

# Pull in Debian security updates on top of the base image
RUN apt-get update \
  && apt-get upgrade -y \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY campuses.json .
COPY templates/ templates/

# data.json is mounted as a volume at runtime
VOLUME ["/app/data.json"]

EXPOSE 7474

CMD ["python", "server.py"]
