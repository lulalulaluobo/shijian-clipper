FROM python:3.14-slim

WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN addgroup --system app && adduser --system --ingroup app app
COPY --chown=app:app backend /app/backend
COPY --chown=app:app poc /app/poc
ENV PYTHONPATH=/app
USER app
