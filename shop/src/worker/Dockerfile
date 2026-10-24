FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY worker.py .
USER 10001
EXPOSE 8080
CMD ["python", "-u", "worker.py"]
