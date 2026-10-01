FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# onnxruntime powers human detection but ships no wheels for armhf/armv7/i386,
# which this add-on still supports. Keep the failure non-fatal: HumanDetector
# detects the missing import and degrades to "detection unavailable".
RUN pip install --no-cache-dir "onnxruntime>=1.17" \
    || echo "onnxruntime unavailable for this architecture — human detection disabled"

COPY src/ ./src/
COPY models/ ./models/
COPY run.sh .
RUN chmod +x run.sh

CMD ["/app/run.sh"]
