"""Kafka producer / consumer wrappers for async agent communication.

Stage 1 note: these are functional stubs that log instead of sending.
Stage 2 will replace the bodies with real confluent-kafka calls when
the Orchestrator starts routing tasks across agents.
"""

import json
from typing import Callable


class KafkaProducer:
    """Wraps a Kafka producer. Currently stubs — wire up confluent-kafka in Stage 2."""

    def __init__(self, bootstrap_servers: str) -> None:
        self.bootstrap_servers = bootstrap_servers
        print(f"[KafkaProducer] stub initialised (servers={bootstrap_servers})")

    def send(self, topic: str, message: dict) -> None:
        """Publish a JSON message to a topic."""
        print(f"[KafkaProducer] STUB → topic='{topic}' payload={json.dumps(message)}")


class KafkaConsumer:
    """Wraps a Kafka consumer. Currently stubs — wire up confluent-kafka in Stage 2."""

    def __init__(self, topic: str, bootstrap_servers: str, group_id: str) -> None:
        self.topic = topic
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        print(f"[KafkaConsumer] stub initialised (topic={topic}, group={group_id})")

    def listen(self, handler: Callable[[dict], None]) -> None:
        """Block and call handler for each incoming message."""
        print(f"[KafkaConsumer] STUB → would listen on topic='{self.topic}'")
