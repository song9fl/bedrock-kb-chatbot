from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_GENERATION_PROMPT = """You are a careful assistant answering questions from an Amazon Bedrock Knowledge Base.

Use only the retrieved context to answer. If the context does not contain enough information, say that the knowledge base does not provide enough evidence.

<context>
$search_results$
</context>

<question>
$query$
</question>

Guidelines:
- Give a direct answer first.
- Keep the answer concise, but include necessary qualifications.
- Do not invent facts, source names, citations, or page numbers.
- If the retrieved context conflicts, explain the conflict briefly.

$output_format_instructions$
"""


@dataclass(frozen=True)
class BedrockKnowledgeBaseSettings:
    region_name: str
    knowledge_base_id: str
    model_arn: str
    number_of_results: int = 5
    search_type: str = "DEFAULT"
    max_tokens: int = 2048
    temperature: float = 0.2
    top_p: float = 0.9
    profile_name: str | None = None
    guardrail_id: str | None = None
    guardrail_version: str | None = None
    kms_key_arn: str | None = None
    query_decomposition: bool = False


def load_prompt(prompt_path: Path) -> str:
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")

    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(DEFAULT_GENERATION_PROMPT, encoding="utf-8")
    return DEFAULT_GENERATION_PROMPT


def save_prompt(prompt_path: Path, prompt_template: str) -> None:
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(prompt_template, encoding="utf-8")


def validate_generation_prompt(prompt_template: str) -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not prompt_template.strip():
        errors.append("Generation prompt is empty.")
    if "$search_results$" not in prompt_template:
        errors.append("Generation prompt must include $search_results$ for Knowledge Base context.")
    if "$output_format_instructions$" not in prompt_template:
        warnings.append(
            "Generation prompt does not include $output_format_instructions$; Bedrock citations may not be returned."
        )

    return {"errors": errors, "warnings": warnings}


def make_bedrock_client(region_name: str, profile_name: str | None = None) -> Any:
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 is not installed. Install dependencies with: pip install -r requirements.txt") from exc

    session_kwargs: dict[str, str] = {}
    if region_name:
        session_kwargs["region_name"] = region_name
    if profile_name:
        session_kwargs["profile_name"] = profile_name

    return boto3.Session(**session_kwargs).client("bedrock-agent-runtime")


def build_retrieve_and_generate_request(
    query: str,
    settings: BedrockKnowledgeBaseSettings,
    prompt_template: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    question = query.strip()
    if not question:
        raise ValueError("Query is empty.")
    if not settings.knowledge_base_id.strip():
        raise ValueError("Knowledge Base ID is required.")
    if not settings.model_arn.strip():
        raise ValueError("Model ARN or inference profile ARN is required.")

    prompt_validation = validate_generation_prompt(prompt_template)
    if prompt_validation["errors"]:
        raise ValueError(" ".join(prompt_validation["errors"]))

    text_inference_config: dict[str, Any] = {
        "maxTokens": int(settings.max_tokens),
        "temperature": float(settings.temperature),
        "topP": float(settings.top_p),
    }

    generation_configuration: dict[str, Any] = {
        "promptTemplate": {
            "textPromptTemplate": prompt_template,
        },
        "inferenceConfig": {
            "textInferenceConfig": text_inference_config,
        },
    }

    if settings.guardrail_id and settings.guardrail_version:
        generation_configuration["guardrailConfiguration"] = {
            "guardrailId": settings.guardrail_id,
            "guardrailVersion": settings.guardrail_version,
        }

    vector_search_configuration: dict[str, Any] = {
        "numberOfResults": int(settings.number_of_results),
    }

    search_type = settings.search_type.upper()
    if search_type in {"HYBRID", "SEMANTIC"}:
        vector_search_configuration["overrideSearchType"] = search_type
    elif search_type != "DEFAULT":
        raise ValueError("Search type must be DEFAULT, HYBRID, or SEMANTIC.")

    knowledge_base_configuration: dict[str, Any] = {
        "knowledgeBaseId": settings.knowledge_base_id.strip(),
        "modelArn": settings.model_arn.strip(),
        "generationConfiguration": generation_configuration,
        "retrievalConfiguration": {
            "vectorSearchConfiguration": vector_search_configuration,
        },
    }

    if settings.query_decomposition:
        knowledge_base_configuration["orchestrationConfiguration"] = {
            "queryTransformationConfiguration": {
                "type": "QUERY_DECOMPOSITION",
            },
        }

    request: dict[str, Any] = {
        "input": {
            "text": question,
        },
        "retrieveAndGenerateConfiguration": {
            "type": "KNOWLEDGE_BASE",
            "knowledgeBaseConfiguration": knowledge_base_configuration,
        },
    }

    if session_id:
        request["sessionId"] = session_id
    elif settings.kms_key_arn:
        request["sessionConfiguration"] = {
            "kmsKeyArn": settings.kms_key_arn,
        }

    return request


def retrieve_and_generate(
    client: Any,
    query: str,
    settings: BedrockKnowledgeBaseSettings,
    prompt_template: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    request = build_retrieve_and_generate_request(
        query=query,
        settings=settings,
        prompt_template=prompt_template,
        session_id=session_id,
    )
    return client.retrieve_and_generate(**request)


def answer_text(response: dict[str, Any]) -> str:
    output = response.get("output") or {}
    text = output.get("text") if isinstance(output, dict) else None
    return str(text or "")


def extract_citations(response: dict[str, Any], max_preview_chars: int = 900) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for citation in response.get("citations") or []:
        if not isinstance(citation, dict):
            continue

        cited_text = _citation_text(citation)
        for reference in citation.get("retrievedReferences") or []:
            if not isinstance(reference, dict):
                continue

            metadata = reference.get("metadata") or {}
            if not isinstance(metadata, dict):
                metadata = {}

            content = _content_to_text(reference.get("content") or {})
            preview = content[:max_preview_chars].strip()
            source = _source_from_reference(reference, metadata)
            page = _page_from_metadata(metadata)

            dedupe_key = (source, str(page or ""), preview[:160])
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            citations.append(
                {
                    "source": source,
                    "page": page,
                    "content": preview,
                    "cited_text": cited_text,
                    "metadata": metadata,
                }
            )

    return citations


def _citation_text(citation: dict[str, Any]) -> str:
    generated_part = citation.get("generatedResponsePart") or {}
    text_part = generated_part.get("textResponsePart") if isinstance(generated_part, dict) else {}
    if isinstance(text_part, dict):
        return str(text_part.get("text") or "")
    return ""


def _content_to_text(content: dict[str, Any]) -> str:
    if not isinstance(content, dict):
        return ""

    if content.get("text"):
        return str(content["text"])

    audio = content.get("audio")
    if isinstance(audio, dict) and audio.get("transcription"):
        return str(audio["transcription"])

    video = content.get("video")
    if isinstance(video, dict) and video.get("summary"):
        return str(video["summary"])

    rows = content.get("row")
    if isinstance(rows, list):
        cells = []
        for row in rows:
            if isinstance(row, dict):
                column = row.get("columnName") or "column"
                value = row.get("columnValue") or ""
                cells.append(f"{column}: {value}")
        return "; ".join(cells)

    if content.get("byteContent"):
        return "[Binary content returned by Bedrock.]"

    return ""


def _source_from_reference(reference: dict[str, Any], metadata: dict[str, Any]) -> str:
    metadata_source = metadata.get("x-amz-bedrock-kb-source-uri") or metadata.get("source") or metadata.get("uri")
    if metadata_source:
        return str(metadata_source)

    location = reference.get("location") or {}
    if not isinstance(location, dict):
        return "Unknown source"

    for location_key, value_keys in (
        ("s3Location", ("uri",)),
        ("webLocation", ("url",)),
        ("confluenceLocation", ("url",)),
        ("salesforceLocation", ("url",)),
        ("sharePointLocation", ("url",)),
        ("kendraDocumentLocation", ("uri",)),
        ("customDocumentLocation", ("id",)),
        ("sqlLocation", ("query",)),
    ):
        location_value = location.get(location_key)
        if isinstance(location_value, dict):
            for value_key in value_keys:
                value = location_value.get(value_key)
                if value:
                    return str(value)

    return "Unknown source"


def _page_from_metadata(metadata: dict[str, Any]) -> str | None:
    for key in (
        "x-amz-bedrock-kb-document-page-number",
        "page_number",
        "page",
    ):
        value = metadata.get(key)
        if value not in (None, ""):
            return str(value)
    return None
