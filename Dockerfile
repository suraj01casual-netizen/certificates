# ==============================================================================
# Dockerfile for Django + WeasyPrint Certificate Platform
# Optimized for Railway Production Deployment
# ==============================================================================

FROM python:3.12-slim-bookworm

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install native Linux libraries required by WeasyPrint (Cairo, Pango, GObject, fonts)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fontconfig \
    fonts-dejavu-core \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . /app/

# Collect static files into STATIC_ROOT for WhiteNoise serving
RUN python manage.py collectstatic --noinput

# Expose default port (Railway dynamically assigns $PORT at runtime)
EXPOSE 8000

# Start production server: run migrations then launch Gunicorn on $PORT
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3 --timeout 120 --access-logfile - --error-logfile -"]
