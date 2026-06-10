from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol


class HistoryLogger(Protocol):
    def append(self, record: dict[str, Any]) -> None:
        ...

    def recent_by_school_id(self, school_id: str, limit: int) -> list[dict[str, Any]]:
        ...


@dataclass(frozen=True)
class HistorySettings:
    mode: str = "local"
    region_name: str = "us-east-1"
    profile_name: str | None = None
    dynamodb_table: str = ""
    s3_bucket: str = ""
    s3_prefix: str = "chat-history"
    local_path: Path = Path("logs/chat_history.jsonl")

    def normalized_mode(self) -> str:
        return self.mode.strip().lower() or "local"

    def validation_errors(self) -> list[str]:
        mode = self.normalized_mode()
        if mode not in {"local", "aws"}:
            return ["Chat history mode must be local or aws."]
        if mode == "aws":
            errors = []
            if not self.dynamodb_table.strip():
                errors.append("DynamoDB chat history table is required.")
            if not self.s3_bucket.strip():
                errors.append("S3 chat log bucket is required.")
            return errors
        return []


class LocalJsonlHistoryLogger:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as history_file:
            history_file.write(json.dumps(record, ensure_ascii=False) + "\n")

    def recent_by_school_id(self, school_id: str, limit: int) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []

        records = []
        target_pk = f"SCHOOL#{school_id.strip()}"
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("pk") == target_pk:
                records.append(record)

        return records[-limit:]


class AwsHistoryLogger:
    def __init__(
        self,
        *,
        table_name: str,
        bucket_name: str,
        prefix: str,
        region_name: str,
        profile_name: str | None = None,
        dynamodb_resource: Any | None = None,
        s3_client: Any | None = None,
    ) -> None:
        self.table_name = table_name
        self.bucket_name = bucket_name
        self.prefix = prefix.strip("/")

        if dynamodb_resource is None or s3_client is None:
            try:
                import boto3
            except ImportError as exc:
                raise RuntimeError("boto3 is required for AWS chat history logging.") from exc

            session_kwargs: dict[str, str] = {"region_name": region_name}
            if profile_name:
                session_kwargs["profile_name"] = profile_name
            session = boto3.Session(**session_kwargs)
            dynamodb_resource = dynamodb_resource or session.resource("dynamodb")
            s3_client = s3_client or session.client("s3")

        self.table = dynamodb_resource.Table(table_name)
        self.s3_client = s3_client

    def append(self, record: dict[str, Any]) -> None:
        self.table.put_item(Item=record)
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=s3_key_for_record(record, self.prefix),
            Body=(json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"),
            ContentType="application/json",
        )

    def recent_by_school_id(self, school_id: str, limit: int) -> list[dict[str, Any]]:
        try:
            from boto3.dynamodb.conditions import Key
        except ImportError as exc:
            raise RuntimeError("boto3 is required for DynamoDB history retrieval.") from exc

        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"SCHOOL#{school_id.strip()}"),
            ScanIndexForward=False,
            Limit=limit,
        )
        items = response.get("Items") or []
        return list(reversed(items))


def make_history_logger(settings: HistorySettings) -> HistoryLogger:
    errors = settings.validation_errors()
    if errors:
        raise ValueError(" ".join(errors))

    if settings.normalized_mode() == "aws":
        return AwsHistoryLogger(
            table_name=settings.dynamodb_table,
            bucket_name=settings.s3_bucket,
            prefix=settings.s3_prefix,
            region_name=settings.region_name,
            profile_name=settings.profile_name,
        )

    return LocalJsonlHistoryLogger(settings.local_path)


def build_history_record(
    *,
    session_id: str,
    school_id: str | None,
    role: str,
    content: str,
    event: str = "message",
    citations: list[dict[str, Any]] | None = None,
    bedrock_session_id: str | None = None,
) -> dict[str, Any]:
    timestamp = datetime.now(UTC).isoformat()
    event_id = uuid.uuid4().hex
    normalized_school_id = (school_id or "unknown").strip() or "unknown"
    citation_sources = citation_source_list(citations or [])

    return {
        "pk": f"SCHOOL#{normalized_school_id}",
        "sk": f"{timestamp}#{event_id}",
        "timestamp": timestamp,
        "event_id": event_id,
        "event": event,
        "school_id": normalized_school_id,
        "session_id": session_id,
        "bedrock_session_id": bedrock_session_id or "",
        "role": role,
        "content": content,
        "citation_count": len(citations or []),
        "citation_sources": citation_sources,
    }


def format_history_context(records: list[dict[str, Any]], max_chars: int) -> str:
    lines = []
    used_chars = 0

    for record in records:
        event = record.get("event")
        role = record.get("role")
        content = str(record.get("content") or "").strip()
        if event == "school_id_submitted" or not content:
            continue
        if role not in {"user", "assistant"}:
            continue

        line = f"{role}: {content}"
        if used_chars + len(line) + 1 > max_chars:
            break
        lines.append(line)
        used_chars += len(line) + 1

    return "\n".join(lines)


def query_with_history(user_query: str, history_context: str) -> str:
    if not history_context.strip():
        return user_query

    return (
        "Previous conversation with this student:\n"
        f"{history_context}\n\n"
        "Current student message:\n"
        f"{user_query}"
    )


def citation_source_list(citations: list[dict[str, Any]]) -> list[str]:
    sources = []
    for citation in citations:
        source = citation.get("source")
        if source:
            sources.append(str(source))
    return sources


def s3_key_for_record(record: dict[str, Any], prefix: str) -> str:
    timestamp = str(record["timestamp"])
    date_part = timestamp.split("T", maxsplit=1)[0]
    year, month, day = date_part.split("-")
    school_id_hash = hashlib.sha256(str(record["school_id"]).encode("utf-8")).hexdigest()[:16]
    session_id = str(record["session_id"])
    event_id = str(record["event_id"])
    safe_timestamp = timestamp.replace(":", "-")
    key_prefix = prefix.strip("/")

    return (
        f"{key_prefix}/year={year}/month={month}/day={day}/"
        f"school_id_hash={school_id_hash}/session_id={session_id}/"
        f"{safe_timestamp}_{event_id}.json"
    )
