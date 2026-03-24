FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        "aiogram>=3.22.0" \
        "asyncpg>=0.31.0" \
        "dotenv>=0.9.9" \
        "lava-top-sdk>=1.1.1" \
        "pytz>=2026.1.post1" \
        "sqlalchemy>=2.0.48"

COPY . /app

CMD ["python", "bot.py"]
