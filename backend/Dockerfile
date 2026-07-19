FROM python:3.14-slim

WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend /app/backend
COPY poc /app/poc
ENV PYTHONPATH=/app
