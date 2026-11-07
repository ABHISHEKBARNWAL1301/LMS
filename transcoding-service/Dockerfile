FROM python:3.11-slim

# Install system dependencies (ffmpeg)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run the application
# Using shell form to allow specific port variable expansion if needed, 
# though Railway sets PORT env var which uvicorn can use if passed correctly.
# We default to 8000 if PORT is not set.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
