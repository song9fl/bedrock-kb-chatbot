# Bedrock Knowledge Base Streamlit Chatbot

Maintainer: `song9fl`

I built this repository as a local tester-facing Streamlit chatbot for Amazon Bedrock Knowledge Bases. The app uses `bedrock-agent-runtime.retrieve_and_generate`, a saved custom generation prompt, and local JSONL conversation history for testing.

## What Testers Can Check

- Run the unit tests without AWS.
- Start the Streamlit UI locally.
- Connect the chatbot to a Bedrock Knowledge Base by filling in local secrets.

The real local secrets file is ignored by git. Do not commit `.streamlit/secrets.toml`.

## Local Setup

```bash
git clone https://github.com/song9fl/bedrock-kb-chatbot.git
cd bedrock-kb-chatbot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .streamlit/secrets.example.toml .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml` with your AWS values:

```toml
[aws]
region = "us-east-1"
profile = "YOUR_LOCAL_AWS_PROFILE"

[bedrock]
knowledge_base_id = "ZFBRFHC0OO"
model_arn = "arn:aws:bedrock:us-east-1:YOUR_AWS_ACCOUNT_ID:inference-profile/us.meta.llama4-maverick-17b-instruct-v1:0"
```

For local development, keep history in local JSONL mode:

```toml
[history]
mode = "local"
```

## Set Up Your AWS Account Values

Each tester should use their own AWS account or assigned sandbox account.

1. Configure an AWS CLI profile on your machine:

```bash
aws configure --profile YOUR_PROFILE_NAME
```

2. Confirm the profile points to the expected account:

```bash
aws sts get-caller-identity --profile YOUR_PROFILE_NAME
```

3. Copy those values into `.streamlit/secrets.toml`:

```toml
[aws]
region = "us-east-1"
profile = "YOUR_PROFILE_NAME"

[bedrock]
knowledge_base_id = "ZFBRFHC0OO"
model_arn = "arn:aws:bedrock:us-east-1:YOUR_AWS_ACCOUNT_ID:inference-profile/us.meta.llama4-maverick-17b-instruct-v1:0"
```

The Knowledge Base ID is included for this project. Do not copy my credentials, AWS profile name, access keys, account ID, or deployed URLs. Use your own AWS profile unless I explicitly give you limited test credentials.

## Run Tests

The unit tests do not call AWS:

```bash
python -m unittest discover -s tests
```

## Run The Local App

```bash
streamlit run app.py
```

The app starts by asking for a school ID. In local mode, chat history is written to `logs/chat_history.jsonl`.

## Prompt

The generation prompt is saved at:

```text
prompts/generation_prompt.txt
```

Keep these placeholders in the prompt:

```text
$search_results$
$output_format_instructions$
```

Bedrock inserts retrieved Knowledge Base chunks through `$search_results$`. The `$output_format_instructions$` placeholder helps preserve citation metadata.

## User-Facing UI

The app hides Streamlit configuration controls from the user-facing interface. Bedrock settings are configured through `.streamlit/secrets.toml` locally or environment variables in AWS.

## Conversation History

Local testing uses local JSONL history:

```text
CHAT_HISTORY_MODE=local
```

The app asks for a school ID first. Local chat history is written to `logs/chat_history.jsonl`, which is ignored by git.

## Main Files

- `app.py`: Streamlit UI and chat flow
- `bedrock_kb.py`: Bedrock Knowledge Base request builder and response helpers
- `history_store.py`: local JSONL history logging helpers
- `prompts/generation_prompt.txt`: saved generation prompt
- `.streamlit/secrets.example.toml`: local configuration template
- `tests/`: unit tests that do not call AWS

## Local AWS Permissions

The local AWS profile needs permission to call the Knowledge Base and model:

```text
bedrock:Retrieve
bedrock:RetrieveAndGenerate
bedrock:GetInferenceProfile
bedrock:InvokeModel
bedrock:InvokeModelWithResponseStream
```

If you use a Bedrock inference profile, make sure the role can invoke the underlying foundation model resources that the profile routes to.
