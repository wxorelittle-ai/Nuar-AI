FROM python:3.12-slim

# Не пишем .pyc, не буферизуем логи
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Сначала зависимости — лучше кэшируется
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# По умолчанию — веб-сервер (gunicorn + uvicorn workers).
# Команда воркера переопределяется в docker-compose (worker service).
CMD ["gunicorn", "web.app:app", "-k", "uvicorn.workers.UvicornWorker", \
     "-b", "0.0.0.0:8000", "-w", "3", "--timeout", "120"]
