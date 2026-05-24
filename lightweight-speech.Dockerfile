FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

COPY lightweight_speech_service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r /tmp/requirements.txt

COPY lightweight_speech_service /app

EXPOSE 8020

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8020"]
