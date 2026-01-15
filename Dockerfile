FROM python:3.11-slim

WORKDIR /app

# Install dependencies needed for simple system libraries if necessary
# RUN apt-get update && apt-get install -y --no-install-recommends ...

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
