# Use lightweight Python base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .
COPY core.py .

# Create instance directory for SQLite
RUN mkdir -p /app/instance

# Set permissions for the instance directory
RUN chmod -R 777 /app/instance

# Expose configurable port
ENV PORT=8000
EXPOSE $PORT

# Set Uvicorn log level for debugging
ENV UVICORN_LOG_LEVEL=debug

# Run the application using Uvicorn
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT --log-level $UVICORN_LOG_LEVEL"]