FROM python:3.12-slim

WORKDIR /app

# Instalacja zależności
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiuj kod aplikacji
COPY . .

# Katalog tymczasowy (zastąpiony przez wolumen w Fly.io)
RUN mkdir -p /app/uploads/zdjecia

EXPOSE 8080

# 2 workery, timeout 120s (dla wolnych odpowiedzi API Claude)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "120", "app:app"]
