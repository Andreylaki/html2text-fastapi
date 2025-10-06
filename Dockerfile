FROM python:3.11-slim

# оптимизации сборки
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# сначала зависимости — так кэш лучше работает
COPY requirements.txt .
RUN pip install -r requirements.txt

# затем код
COPY app.py ./app.py

# Railway обычно прокидывает PORT через env
EXPOSE 8000
CMD ["sh","-c","uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
