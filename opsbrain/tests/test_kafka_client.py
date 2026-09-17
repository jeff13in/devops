"""Unit tests for the shared Kafka message serialization helpers.

These test the pure serialize/deserialize functions only — no broker needed.
Live producer/consumer behavior against a real Kafka broker was verified
manually (see opsbrain/memory.md); constructing KafkaProducer/KafkaConsumer
connects immediately, so it isn't something to unit test without a broker.
"""

from __future__ import annotations

import unittest

from shared.kafka_client import deserialize_message, serialize_message
from shared.models import AgentMessage


class KafkaSerializationTests(unittest.TestCase):
    def test_round_trips_a_plain_dict(self) -> None:
        message = {"task_id": "t1", "from_agent": "orchestrator", "to_agent": "infra", "payload": {"question": "eks status?"}}

        raw = serialize_message(message)
        result = deserialize_message(raw)

        self.assertEqual(result, message)

    def test_round_trips_an_agent_message_model(self) -> None:
        message = AgentMessage(
            task_id="t2",
            from_agent="orchestrator",
            to_agent="code",
            payload={"pr_number": 42},
        )

        raw = serialize_message(message)
        result = deserialize_message(raw)

        self.assertEqual(result, message.model_dump())

    def test_serialize_produces_utf8_json_bytes(self) -> None:
        raw = serialize_message({"task_id": "t3", "from_agent": "a", "to_agent": "b", "payload": {}})

        self.assertIsInstance(raw, bytes)
        self.assertIn(b'"task_id"', raw)


if __name__ == "__main__":
    unittest.main()
