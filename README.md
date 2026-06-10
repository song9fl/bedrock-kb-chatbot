# Bedrock Knowledge Base Streamlit Chatbot

Maintainer: `song9fl`

I built this repository as a tester-facing Streamlit chatbot for Amazon Bedrock Knowledge Bases. The app uses `bedrock-agent-runtime.retrieve_and_generate`, a saved custom generation prompt, and optional local or AWS-backed conversation history.

## What Testers Can Check

- Run the unit tests without AWS.
- Start the Streamlit UI locally.
- Connect the chatbot to a Bedrock Knowledge Base by filling in local secrets.
- Review the AWS deployment templates for ECS/Fargate, DynamoDB, S3, ECR, and CodeBuild.

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

For AWS deployment, keep these values ready:

```text
AWS_PROFILE=YOUR_PROFILE_NAME
AWS_REGION=us-east-1
ACCOUNT_ID=YOUR_AWS_ACCOUNT_ID
KB_ID=ZFBRFHC0OO
KB_ARN=arn:aws:bedrock:us-east-1:YOUR_AWS_ACCOUNT_ID:knowledge-base/ZFBRFHC0OO
MODEL_ARN=arn:aws:bedrock:us-east-1:YOUR_AWS_ACCOUNT_ID:inference-profile/us.meta.llama4-maverick-17b-instruct-v1:0
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

Local testing:

```text
CHAT_HISTORY_MODE=local
```

Production AWS use:

```text
CHAT_HISTORY_MODE=aws
CHAT_HISTORY_DYNAMODB_TABLE=YOUR_DYNAMODB_TABLE
CHAT_HISTORY_S3_BUCKET=YOUR_HISTORY_BUCKET
CHAT_HISTORY_S3_PREFIX=chat-history
```

In AWS mode, the app stores durable history by school ID:

```text
pk = SCHOOL#{school_id}
```

When the same school ID returns, the app loads recent prior messages and sends a bounded history context to Bedrock with the current question. S3 stores a JSON event copy for every chat event.

## AWS Deployment

For my reusable AWS deployment procedure, see:

```text
docs/aws-deployment-runbook.md
```

The current supported hosting path is ECS Fargate behind an Application Load Balancer. Streamlit requires a working WebSocket route, and the ECS/ALB template is configured for that behavior.

## Main Files

- `app.py`: Streamlit UI and chat flow
- `bedrock_kb.py`: Bedrock Knowledge Base request builder and response helpers
- `history_store.py`: local JSONL and AWS DynamoDB/S3 history logging
- `prompts/generation_prompt.txt`: saved generation prompt
- `.streamlit/secrets.example.toml`: local configuration template
- `deploy/aws-history-resources.yml`: DynamoDB, S3, and runtime IAM role
- `deploy/aws-build-resources.yml`: S3 source bucket and CodeBuild image builder
- `deploy/aws-ecs-fargate-service.yml`: ECS Fargate and ALB service
- `docs/aws-deployment-runbook.md`: AWS deployment guide

## Required AWS Permissions

The runtime role for production needs access to:

```text
bedrock:Retrieve
bedrock:RetrieveAndGenerate
bedrock:GetInferenceProfile
bedrock:InvokeModel
bedrock:InvokeModelWithResponseStream
dynamodb:PutItem
dynamodb:Query
s3:PutObject
```

If you use a Bedrock inference profile, make sure the role can invoke the underlying foundation model resources that the profile routes to.
