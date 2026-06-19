# producer.py
import json
from kafka import KafkaProducer
import time

# Add retry logic and connection timeout
producer = KafkaProducer(
    bootstrap_servers=["localhost:9092"],
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    retries=5,
    retry_backoff_ms=1000,
    request_timeout_ms=60000,  # Increase timeout to 60 seconds
    connections_max_idle_ms=540000,
)

topic = "my-test-topic"

for i in range(10):
    data = {"id": i, "message": "hello kafka"}
    producer.send(topic, value=data)
    print(f"Sent: {data}")
    time.sleep(1)

producer.flush()
producer.close()
