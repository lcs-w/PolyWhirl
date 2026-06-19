# consumer.py
import json
from kafka import KafkaConsumer

consumer = KafkaConsumer(
    "my-test-topic",
    bootstrap_servers=["localhost:9092"],
    auto_offset_reset="earliest",
    group_id="my-group",
    value_deserializer=lambda x: json.loads(x.decode("utf-8")),
)

print("Started consuming...")
for message in consumer:
    print(f"Received: {message.value}")
