from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from history_store import (  # noqa: E402
    AwsHistoryLogger,
    HistorySettings,
    LocalJsonlHistoryLogger,
    build_history_record,
    format_history_context,
    query_with_history,
    s3_key_for_record,
)


class FakeTable:
    def __init__(self) -> None:
        self.items = []

    def put_item(self, Item: dict) -> None:  # noqa: N803
        self.items.append(Item)


class FakeDynamoDbResource:
    def __init__(self) -> None:
        self.table = FakeTable()

    def Table(self, _table_name: str) -> FakeTable:  # noqa: N802
        return self.table


class FakeS3Client:
    def __init__(self) -> None:
        self.objects = []

    def put_object(self, **kwargs) -> None:
        self.objects.append(kwargs)


class HistoryStoreTests(unittest.TestCase):
    def test_aws_mode_requires_dynamodb_and_s3(self) -> None:
        settings = HistorySettings(mode="aws")

        self.assertEqual(
            settings.validation_errors(),
            ["DynamoDB chat history table is required.", "S3 chat log bucket is required."],
        )

    def test_record_uses_school_id_partition_key(self) -> None:
        record = build_history_record(
            session_id="session-1",
            school_id="school-123",
            role="user",
            content="What is gravity?",
            citations=[{"source": "s3://bucket/source.pdf"}],
            bedrock_session_id="bedrock-session",
        )

        self.assertEqual(record["pk"], "SCHOOL#school-123")
        self.assertTrue(record["sk"].startswith(record["timestamp"]))
        self.assertEqual(record["session_id"], "session-1")
        self.assertEqual(record["bedrock_session_id"], "bedrock-session")
        self.assertEqual(record["citation_sources"], ["s3://bucket/source.pdf"])

    def test_s3_key_is_partitioned_by_date_and_hashed_school_id(self) -> None:
        record = {
            "timestamp": "2026-06-10T18:11:07.666233+00:00",
            "school_id": "school-123",
            "session_id": "session-1",
            "event_id": "event-1",
        }

        key = s3_key_for_record(record, "chat-history")

        self.assertTrue(key.startswith("chat-history/year=2026/month=06/day=10/school_id_hash="))
        self.assertIn("/session_id=session-1/", key)
        self.assertTrue(key.endswith("_event-1.json"))

    def test_local_logger_appends_jsonl_and_reads_recent_school_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.jsonl"
            logger = LocalJsonlHistoryLogger(path)
            first = build_history_record(session_id="s1", school_id="A", role="user", content="first")
            second = build_history_record(session_id="s1", school_id="B", role="user", content="second")
            third = build_history_record(session_id="s1", school_id="A", role="assistant", content="third")

            logger.append(first)
            logger.append(second)
            logger.append(third)

            records = logger.recent_by_school_id("A", limit=10)

            self.assertEqual([record["content"] for record in records], ["first", "third"])

    def test_aws_logger_writes_to_dynamodb_and_s3(self) -> None:
        dynamodb = FakeDynamoDbResource()
        s3 = FakeS3Client()
        logger = AwsHistoryLogger(
            table_name="history",
            bucket_name="bucket",
            prefix="chat-history",
            region_name="us-east-1",
            dynamodb_resource=dynamodb,
            s3_client=s3,
        )
        record = build_history_record(session_id="s1", school_id="A", role="user", content="hello")

        logger.append(record)

        self.assertEqual(dynamodb.table.items, [record])
        self.assertEqual(s3.objects[0]["Bucket"], "bucket")
        self.assertTrue(s3.objects[0]["Key"].startswith("chat-history/year="))
        self.assertEqual(json.loads(s3.objects[0]["Body"].decode("utf-8")), record)

    def test_history_context_is_bounded_and_skips_school_id_event(self) -> None:
        records = [
            {"event": "school_id_submitted", "role": "user", "content": "School ID submitted."},
            {"event": "message", "role": "user", "content": "What is gravity?"},
            {"event": "message", "role": "assistant", "content": "What do you already know?"},
        ]

        context = format_history_context(records, max_chars=200)

        self.assertNotIn("School ID submitted", context)
        self.assertIn("user: What is gravity?", context)
        self.assertIn("assistant: What do you already know?", context)

    def test_query_with_history_wraps_current_message(self) -> None:
        query = query_with_history("What next?", "user: What is gravity?")

        self.assertIn("Previous conversation", query)
        self.assertIn("Current student message", query)
        self.assertIn("What next?", query)


if __name__ == "__main__":
    unittest.main()
