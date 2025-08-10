# Use a small official Python image
FROM python:3.11-slim

# Environment: no .pyc, unbuffered logs, safer pip
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Set workdir
WORKDIR /app

# Install Python deps first to leverage Docker layer cache
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Expose app ports
EXPOSE 3000 6000

# Start the app (unbuffered logs due to PYTHONUNBUFFERED=1)
CMD ["python", "main.py"]
