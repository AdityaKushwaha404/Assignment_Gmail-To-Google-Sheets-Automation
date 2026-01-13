FROM python:3.11-slim

# Install system dependencies required by some packages (if any).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install. Credentials are intentionally NOT copied.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the application code. Do not include credentials/ in the image.
COPY . /app

# Run the module. To provide credentials at runtime mount a volume such as:
# docker run --rm -v $PWD/credentials:/app/credentials:ro your-image-name
CMD ["python", "-m", "src.main"]
