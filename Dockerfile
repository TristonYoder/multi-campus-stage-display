FROM python:3.12-slim

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
