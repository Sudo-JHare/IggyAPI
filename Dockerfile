# Use lightweight Python base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .

# Create instance directory for SQLite
RUN mkdir -p /app/instance

# Set permissions for the instance directory
RUN chmod -R 777 /app/instance

# Expose configurable port
ENV PORT=8000
EXPOSE $PORT

# Run the application
CMD ["python", "main.py"]