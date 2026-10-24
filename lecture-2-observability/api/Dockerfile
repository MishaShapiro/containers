FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
USER 10001
EXPOSE 8080
# 1 воркер (счётчики Prometheus живут в памяти процесса), много потоков: /load ходит сам в себя
CMD ["gunicorn", "-b", "0.0.0.0:8080", "--workers", "1", "--threads", "32", "app:app"]
