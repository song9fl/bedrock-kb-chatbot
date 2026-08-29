from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import streamlit as st

from bedrock_kb import (
    BedrockKnowledgeBaseSettings,
    answer_text,
    extract_citations,
    load_prompt,
    make_bedrock_client,
    retrieve_and_generate,
    validate_generation_prompt,
)
from history_store import (
    HistorySettings,
    build_history_record,
    format_history_context,
    make_history_logger,
    query_with_history,
)
from response_postprocess import enforce_coach_style


APP_DIR = Path(__file__).resolve().parent
PROMPT_PATH = APP_DIR / "prompts" / "generation_prompt.txt"
HISTORY_PATH = APP_DIR / "logs" / "chat_history.jsonl"
SCHOOL_ID_PROMPT = "What's your school ID?"
READY_TO_LEARN_PROMPT = "Thanks. What would you like to learn about today?"
WELCOME_BACK_PROMPT = "Thanks. I found your earlier conversation, so we can keep going. What would you like to learn about today?"
APP_TITLE = os.getenv("APP_TITLE", "Bedrock KB Chatbot").strip() or "Bedrock KB Chatbot"
CHAT_PLACEHOLDER = os.getenv("CHAT_PLACEHOLDER", "Ask a question").strip() or "Ask a question"


st.set_page_config(page_title=APP_TITLE, page_icon=":material/calculate:", layout="wide")


def inject_app_styles() -> None:
    st.markdown(
        """
        <style>
        #MainMenu,
        footer,
        header,
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        [data-testid="collapsedControl"],
        .stDeployButton {
            display: none !important;
            visibility: hidden !important;
        }

        .stApp {
            background: #f7f8f5;
            color: #202725;
        }

        .block-container {
            max-width: 920px;
            padding: 2rem 1.25rem 6.5rem;
        }

        h1 {
            font-size: 1.45rem !important;
            font-weight: 650 !important;
            letter-spacing: 0 !important;
            margin: 0 0 0.25rem !important;
            color: #1f2a27;
        }

        [data-testid="stHorizontalBlock"] {
            align-items: center;
            border-bottom: 1px solid #dfe5df;
            padding-bottom: 0.65rem;
            margin-bottom: 1.25rem;
        }

        [data-testid="stChatMessage"] {
            background: transparent;
            padding: 0.45rem 0;
        }

        [data-testid="stChatMessageContent"] {
            border: 1px solid #dfe5df;
            border-radius: 8px;
            padding: 0.85rem 1rem;
            background: #ffffff;
            box-shadow: 0 1px 2px rgba(28, 42, 38, 0.04);
        }

        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageContent"] {
            background: #e8f2ec;
            border-color: #cadfce;
        }

        .stChatInput {
            background: rgba(247, 248, 245, 0.94);
            border-top: 1px solid #dfe5df;
            padding-top: 0.75rem;
        }

        .stChatInput textarea {
            border-radius: 8px !important;
            border-color: #b8c7be !important;
            box-shadow: none !important;
        }

        .stButton > button {
            border-radius: 8px;
            border-color: #becbc4;
            color: #26332f;
            background: #ffffff;
        }

        .stButton > button:hover {
            border-color: #4f7f63;
            color: #1f5d3e;
        }

        [data-testid="stExpander"] {
            border: 1px solid #dfe5df;
            border-radius: 8px;
            background: #ffffff;
        }

        [data-testid="stAlert"] {
            border-radius: 8px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource(show_spinner=False)
def cached_bedrock_client(region_name: str, profile_name: str | None) -> Any:
    return make_bedrock_client(region_name=region_name, profile_name=profile_name)


@st.cache_resource(show_spinner=False)
def cached_history_logger(
    mode: str,
    region_name: str,
    profile_name: str | None,
    dynamodb_table: str,
    s3_bucket: str,
    s3_prefix: str,
    local_path: str,
) -> Any:
    return make_history_logger(
        HistorySettings(
            mode=mode,
            region_name=region_name,
            profile_name=profile_name,
            dynamodb_table=dynamodb_table,
            s3_bucket=s3_bucket,
            s3_prefix=s3_prefix,
            local_path=Path(local_path),
        )
    )


def load_history_context(school_id: str, limit: int, max_chars: int) -> str:
    records = history_logger.recent_by_school_id(school_id, limit=limit)
    return format_history_context(records, max_chars=max_chars)


def extend_history_context(history_context: str, role: str, content: str, max_chars: int) -> str:
    role = str(role or "").strip()
    content = str(content or "").strip()
    if role not in {"user", "assistant"} or not content:
        return history_context.strip()

    lines = [line.strip() for line in history_context.splitlines() if line.strip()]
    lines.append(f"{role}: {content}")

    kept: list[str] = []
    used_chars = 0
    for line in reversed(lines):
        line_length = len(line)
        separator = 1 if kept else 0
        if used_chars + line_length + separator > max_chars:
            break
        kept.append(line)
        used_chars += line_length + separator

    return "\n".join(reversed(kept))


def config_value(section: str, key: str, env_name: str, default: str = "") -> str:
    env_value = os.getenv(env_name)
    if env_value:
        return env_value

    try:
        section_values = st.secrets.get(section, {})
    except Exception:
        return default

    if hasattr(section_values, "get"):
        value = section_values.get(key, default)
        return str(value or default)

    return default


def config_int(section: str, key: str, env_name: str, default: int) -> int:
    value = config_value(section, key, env_name, str(default))
    try:
        return int(value)
    except ValueError:
        return default


def config_float(section: str, key: str, env_name: str, default: float) -> float:
    value = config_value(section, key, env_name, str(default))
    try:
        return float(value)
    except ValueError:
        return default


def config_bool(section: str, key: str, env_name: str, default: bool) -> bool:
    value = config_value(section, key, env_name, str(default)).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def format_exception(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        error = response.get("Error") or {}
        code = error.get("Code")
        message = error.get("Message")
        if code and message:
            return f"{code}: {message}"
        if message:
            return str(message)

    return str(exc)


def client_ip_address() -> str | None:
    try:
        ip_address = getattr(st.context, "ip_address", None)
        if ip_address:
            return str(ip_address).strip() or None
    except Exception:
        pass

    try:
        headers = getattr(st.context, "headers", None)
        if headers:
            forwarded_for = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for")
            if forwarded_for:
                return str(forwarded_for).split(",")[0].strip() or None
    except Exception:
        pass

    return "127.0.0.1"


def render_sources(message_id: str, school_id: str | None, citations: list[dict[str, Any]]) -> None:
    if not citations:
        return

    visibility_key = f"sources_visible_{message_id}"
    button_key = f"sources_button_{message_id}"
    clicked = st.button(f"Sources ({len(citations)})", key=button_key)
    if clicked:
        st.session_state[visibility_key] = True
        append_history(
            school_id=school_id,
            role="event",
            content=f"Sources ({len(citations)})",
            event="sources_clicked",
            citations=citations,
            event_tags=["sources_clicked"],
            metadata={
                "message_id": message_id,
                "source_count": len(citations),
            },
        )

    if not st.session_state.get(visibility_key):
        return

    with st.expander(f"Sources ({len(citations)})", expanded=True):
        for index, citation in enumerate(citations, start=1):
            source = citation.get("source") or "Unknown source"
            page = citation.get("page")
            label = f"{index}. {source}"
            if page:
                label = f"{label} | page {page}"
            st.markdown(f"**{label}**")
            content = citation.get("content")
            if content:
                st.write(content)


def record_sources_not_clicked(message_id: str, school_id: str | None, citations: list[dict[str, Any]]) -> None:
    if not citations:
        return

    recorded_key = f"sources_not_clicked_recorded_{message_id}"
    if st.session_state.get(recorded_key):
        return

    st.session_state[recorded_key] = True
    append_history(
        school_id=school_id,
        role="event",
        content=f"Sources ({len(citations)})",
        event="sources_not_clicked",
        citations=citations,
        event_tags=["sources_not_clicked"],
        metadata={
            "message_id": message_id,
            "source_count": len(citations),
        },
    )


def append_history(
    *,
    school_id: str | None,
    role: str,
    content: str,
    event: str = "message",
    citations: list[dict[str, Any]] | None = None,
    event_tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if history_logger is None:
        raise RuntimeError("Chat history logging is not configured.")

    record = build_history_record(
        session_id=st.session_state.chat_session_id,
        school_id=school_id,
        role=role,
        content=content,
        event=event,
        citations=citations,
        bedrock_session_id=st.session_state.bedrock_session_id,
        client_ip=client_ip_address(),
        event_tags=event_tags,
        metadata=metadata,
    )
    history_logger.append(record)


def initial_messages() -> list[dict[str, Any]]:
    return [{"message_id": uuid4().hex, "role": "assistant", "content": SCHOOL_ID_PROMPT}]


def make_chat_message(
    *,
    role: str,
    content: str,
    citations: list[dict[str, Any]] | None = None,
    message_id: str | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "message_id": message_id or uuid4().hex,
        "role": role,
        "content": content,
    }
    if citations:
        message["citations"] = citations
    return message


def show_school_id_form(ready_errors: list[str]) -> None:
    st.markdown("### Start here")
    school_id_input = st.text_input(
        "School ID",
        key="school_id_input",
        placeholder="Enter your school ID",
        label_visibility="collapsed",
        disabled=bool(ready_errors),
    )
    continue_pressed = st.button("Continue", use_container_width=False, disabled=bool(ready_errors))

    if not continue_pressed:
        return

    cleaned_school_id = school_id_input.strip()
    if not cleaned_school_id:
        st.warning("Please enter a school ID to continue.")
        st.stop()

    st.session_state.school_id = cleaned_school_id
    st.session_state.messages.append(
        make_chat_message(role="user", content=f"School ID: {cleaned_school_id}")
    )
    append_history(
        school_id=cleaned_school_id,
        role="user",
        content=f"School ID: {cleaned_school_id}",
        event="school_id_submitted",
        event_tags=["school_id_submitted"],
    )

    st.session_state.history_context = load_history_context(
        cleaned_school_id,
        limit=history_context_limit,
        max_chars=history_context_max_chars,
    )
    assistant_text = WELCOME_BACK_PROMPT if st.session_state.history_context else READY_TO_LEARN_PROMPT
    st.session_state.messages.append(make_chat_message(role="assistant", content=assistant_text))
    append_history(
        school_id=cleaned_school_id,
        role="assistant",
        content=assistant_text,
        citations=[],
        event_tags=["welcome_prompt"],
    )
    st.rerun()


def init_session_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = initial_messages()
    if "bedrock_session_id" not in st.session_state:
        st.session_state.bedrock_session_id = None
    if "school_id" not in st.session_state:
        st.session_state.school_id = None
    if "chat_session_id" not in st.session_state:
        st.session_state.chat_session_id = uuid4().hex
    if "history_context" not in st.session_state:
        st.session_state.history_context = ""


def settings_fingerprint(settings: BedrockKnowledgeBaseSettings, prompt_template: str) -> str:
    parts = [
        settings.region_name,
        settings.profile_name or "",
        settings.knowledge_base_id,
        settings.model_arn,
        str(settings.number_of_results),
        settings.search_type,
        str(settings.max_tokens),
        str(settings.temperature),
        str(settings.top_p),
        settings.guardrail_id or "",
        settings.guardrail_version or "",
        settings.kms_key_arn or "",
        str(settings.query_decomposition),
        prompt_template,
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


inject_app_styles()
init_session_state()
prompt_template = load_prompt(PROMPT_PATH)
prompt_validation = validate_generation_prompt(prompt_template)

settings = BedrockKnowledgeBaseSettings(
    region_name=config_value(
        "aws",
        "region",
        "AWS_REGION",
        config_value("aws", "region", "AWS_DEFAULT_REGION", "us-east-1"),
    ).strip(),
    profile_name=config_value("aws", "profile", "AWS_PROFILE", "").strip() or None,
    knowledge_base_id=config_value("bedrock", "knowledge_base_id", "BEDROCK_KB_ID", "").strip(),
    model_arn=config_value("bedrock", "model_arn", "BEDROCK_MODEL_ARN", "").strip(),
    number_of_results=config_int("bedrock", "number_of_results", "BEDROCK_NUMBER_OF_RESULTS", 5),
    search_type=config_value("bedrock", "search_type", "BEDROCK_SEARCH_TYPE", "DEFAULT").strip() or "DEFAULT",
    max_tokens=config_int("bedrock", "max_tokens", "BEDROCK_MAX_TOKENS", 2048),
    temperature=config_float("bedrock", "temperature", "BEDROCK_TEMPERATURE", 0.2),
    top_p=config_float("bedrock", "top_p", "BEDROCK_TOP_P", 0.9),
    guardrail_id=config_value("bedrock", "guardrail_id", "BEDROCK_GUARDRAIL_ID", "").strip() or None,
    guardrail_version=config_value("bedrock", "guardrail_version", "BEDROCK_GUARDRAIL_VERSION", "").strip() or None,
    kms_key_arn=config_value("bedrock", "kms_key_arn", "BEDROCK_SESSION_KMS_KEY_ARN", "").strip() or None,
    query_decomposition=config_bool(
        "bedrock",
        "query_decomposition",
        "BEDROCK_QUERY_DECOMPOSITION",
        False,
    ),
)

history_settings = HistorySettings(
    mode=config_value("history", "mode", "CHAT_HISTORY_MODE", "local"),
    region_name=settings.region_name,
    profile_name=settings.profile_name,
    dynamodb_table=config_value("history", "dynamodb_table", "CHAT_HISTORY_DYNAMODB_TABLE", "").strip(),
    s3_bucket=config_value("history", "s3_bucket", "CHAT_HISTORY_S3_BUCKET", "").strip(),
    s3_prefix=config_value("history", "s3_prefix", "CHAT_HISTORY_S3_PREFIX", "chat-history").strip()
    or "chat-history",
    local_path=HISTORY_PATH,
)
app_environment = config_value("app", "environment", "APP_ENV", "local").strip().lower() or "local"
history_context_limit = config_int("history", "context_message_limit", "CHAT_HISTORY_CONTEXT_MESSAGE_LIMIT", 40)
history_context_max_chars = config_int("history", "context_max_chars", "CHAT_HISTORY_CONTEXT_MAX_CHARS", 6000)
history_errors = history_settings.validation_errors()
if app_environment == "production" and history_settings.normalized_mode() != "aws":
    history_errors.append("Production deployments must use AWS chat history logging.")

history_logger = None
if not history_errors:
    history_logger = cached_history_logger(
        history_settings.normalized_mode(),
        history_settings.region_name,
        history_settings.profile_name,
        history_settings.dynamodb_table,
        history_settings.s3_bucket,
        history_settings.s3_prefix,
        str(history_settings.local_path),
    )

title_col, action_col = st.columns([5, 1])
with title_col:
    st.title(APP_TITLE)
with action_col:
    st.write("")
    if st.button("Clear", use_container_width=True):
        st.session_state.messages = initial_messages()
        st.session_state.bedrock_session_id = None
        st.session_state.school_id = None
        st.session_state.chat_session_id = uuid4().hex
        st.session_state.history_context = ""
        st.rerun()


fingerprint = settings_fingerprint(settings, prompt_template)
if st.session_state.get("settings_fingerprint") != fingerprint:
    st.session_state.bedrock_session_id = None
    st.session_state.settings_fingerprint = fingerprint


ready_errors: list[str] = []
if not settings.region_name:
    ready_errors.append("AWS region is required.")
if not settings.knowledge_base_id:
    ready_errors.append("Knowledge Base ID is required.")
if not settings.model_arn:
    ready_errors.append("Model or inference profile ARN is required.")
ready_errors.extend(prompt_validation["errors"])
ready_errors.extend(history_errors)
if (settings.guardrail_id and not settings.guardrail_version) or (
    settings.guardrail_version and not settings.guardrail_id
):
    ready_errors.append("Guardrail ID and version must be provided together.")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant":
            render_sources(
                str(message.get("message_id") or ""),
                st.session_state.school_id,
                message.get("citations") or [],
            )

if ready_errors:
    st.info("The chat is not available yet. Please ask the app administrator to finish setup.")

if not st.session_state.school_id:
    show_school_id_form(ready_errors)
    st.stop()

chat_placeholder = CHAT_PLACEHOLDER
user_query = st.chat_input(chat_placeholder, disabled=bool(ready_errors))

if user_query:
    st.session_state.messages.append(make_chat_message(role="user", content=user_query))
    try:
        append_history(
            school_id=st.session_state.school_id,
            role="user",
            content=user_query,
            event_tags=["chat_message"],
        )
    except Exception as exc:
        print(f"Chat history write failed: {format_exception(exc)}")
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": "I can't continue because chat history logging is unavailable. Please try again later.",
                "citations": [],
            }
        )
        st.rerun()

    with st.chat_message("user"):
        st.markdown(user_query)

    with st.chat_message("assistant"):
        assistant_message_id = uuid4().hex
        with st.spinner("Querying Bedrock..."):
            try:
                client = cached_bedrock_client(settings.region_name, settings.profile_name)
                augmented_query = query_with_history(user_query, st.session_state.history_context)
                response = retrieve_and_generate(
                    client=client,
                    query=augmented_query,
                    settings=settings,
                    prompt_template=prompt_template,
                    session_id=st.session_state.bedrock_session_id,
                )
                st.session_state.bedrock_session_id = response.get("sessionId")
                citations = extract_citations(response)
                raw_assistant_text = answer_text(response)
                assistant_text = (
                    enforce_coach_style(user_query, raw_assistant_text, citations)
                    if raw_assistant_text.strip()
                    else "Bedrock returned an empty response."
                )
            except Exception as exc:
                print(f"Bedrock request failed: {format_exception(exc)}")
                assistant_text = "I could not reach the knowledge base. Please try again later."
                citations = []

        st.markdown(assistant_text)
        render_sources(
            assistant_message_id,
            st.session_state.school_id,
            citations,
        )

    st.session_state.messages.append(
        make_chat_message(role="assistant", content=assistant_text, citations=citations, message_id=assistant_message_id)
    )
    append_history(
        school_id=st.session_state.school_id,
        role="assistant",
        content=assistant_text,
        citations=citations,
        event_tags=["chat_message"],
    )
    record_sources_not_clicked(
        assistant_message_id,
        st.session_state.school_id,
        citations,
    )
    st.session_state.history_context = extend_history_context(
        st.session_state.history_context,
        "user",
        user_query,
        history_context_max_chars,
    )
    st.session_state.history_context = extend_history_context(
        st.session_state.history_context,
        "assistant",
        assistant_text,
        history_context_max_chars,
    )
    st.rerun()
