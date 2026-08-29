# AWS Bedrock Knowledge Base Chatbot

Maintainer: `song9fl`

This repository contains a Streamlit chatbot framework powered by Amazon Bedrock Knowledge Bases. It includes a K-12 math-coach prompt and response post-processing, but the public repository is not a self-contained math coach because it does not include the curriculum dataset or a populated Bedrock Knowledge Base.

A working math-coach deployment requires an external Bedrock Knowledge Base that has already been populated with appropriate math curriculum/source documents. Live deployment values, source datasets, local secrets, and teacher/student chat data are intentionally excluded from git.

## What This Repo Includes

- Streamlit chat UI.
- Bedrock Knowledge Base `retrieve_and_generate` request handling.
- A sample K-12 math-coach generation prompt.
- Response post-processing that keeps answers short and coach-like.
- Optional local JSONL or AWS DynamoDB/S3 conversation history.
- AWS deployment templates for ECS/Fargate, CloudFront HTTPS, DynamoDB, S3, ECR, and CodeBuild.
- Unit tests that run without AWS.

## What This Repo Does Not Include

- Curriculum PDFs, textbook excerpts, lesson files, assessment items, or other math source documents.
- A populated Bedrock Knowledge Base.
- Live AWS resource identifiers, account IDs, CloudFront URLs, buckets, or credentials.
- Teacher/student chat history.

For the data needed to turn this framework into a real math coach, see `docs/data-requirements.md`.

## What Reviewers Can Check

- Run the unit tests without AWS.
- Start the Streamlit UI locally.
- Connect the chatbot to your own populated Bedrock Knowledge Base by filling in local secrets.
- Review the AWS deployment templates for ECS/Fargate, DynamoDB, S3, ECR, and CodeBuild.
- Review the CloudFront HTTPS template for a secure public endpoint.
- Run a separate dashboard app from the sibling `bedrock-kb-dashboard` folder that reads chatbot user history and shows raw messages, IDs, and event labels.

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
knowledge_base_id = "YOUR_POPULATED_KNOWLEDGE_BASE_ID"
model_arn = "arn:aws:bedrock:us-east-1:YOUR_AWS_ACCOUNT_ID:inference-profile/us.meta.llama4-maverick-17b-instruct-v1:0"
```

`YOUR_POPULATED_KNOWLEDGE_BASE_ID` must point to a Bedrock Knowledge Base that already contains the content you want the chatbot to use. Without that data source, the app runs as a KB chatbot shell but cannot provide grounded math-coach answers.

For local development, keep history in local JSONL mode:

```toml
[history]
mode = "local"
```

## Set Up Your AWS Account Values

Each reviewer should use their own AWS account or assigned sandbox account.

1. Find the AWS profile names already configured on your machine:

```bash
aws configure list-profiles
```

The profile name is the value you put in `.streamlit/secrets.toml`:

```toml
[aws]
profile = "YOUR_PROFILE_NAME"
```

2. If you do not have a profile yet, create one:

```bash
aws configure --profile YOUR_PROFILE_NAME
```

3. Find the AWS account ID for that profile:

```bash
aws sts get-caller-identity \
  --profile YOUR_PROFILE_NAME \
  --query Account \
  --output text
```

4. Copy the profile name and account ID into `.streamlit/secrets.toml`:

```toml
[aws]
region = "us-east-1"
profile = "YOUR_PROFILE_NAME"

[bedrock]
knowledge_base_id = "YOUR_POPULATED_KNOWLEDGE_BASE_ID"
model_arn = "arn:aws:bedrock:us-east-1:YOUR_AWS_ACCOUNT_ID:inference-profile/us.meta.llama4-maverick-17b-instruct-v1:0"
```

For AWS deployment, keep these values ready:

```text
AWS_PROFILE=YOUR_PROFILE_NAME
AWS_REGION=us-east-1
ACCOUNT_ID=YOUR_AWS_ACCOUNT_ID
KB_ID=YOUR_POPULATED_KNOWLEDGE_BASE_ID
KB_ARN=arn:aws:bedrock:us-east-1:YOUR_AWS_ACCOUNT_ID:knowledge-base/YOUR_POPULATED_KNOWLEDGE_BASE_ID
MODEL_ARN=arn:aws:bedrock:us-east-1:YOUR_AWS_ACCOUNT_ID:inference-profile/us.meta.llama4-maverick-17b-instruct-v1:0
```

Do not commit credentials, AWS profile names, access keys, account IDs, deployed URLs, or student/teacher history data. Use your own AWS profile unless I explicitly give you limited test credentials.

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

By default, the public app title is `Bedrock KB Chatbot`. A deployed math-coach instance can set:

```text
APP_TITLE=K-12 Math Coach
CHAT_PLACEHOLDER=Ask a math question
```

## Run The Dashboard

```bash
cd ../bedrock-kb-dashboard
streamlit run app.py
```

The dashboard is a separate app from the chatbot and now lives outside this repo in `../bedrock-kb-dashboard`. It reads the same history records and is meant for reviewing raw student messages, school IDs, session IDs, event labels, and categorization results.

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

Bedrock inserts retrieved Knowledge Base chunks through `$search_results$`. The `$output_format_instructions$` placeholder helps preserve citation metadata. The saved prompt is math-coach oriented, but its answer quality depends on the external Knowledge Base content.

## User-Facing UI

The app hides Streamlit configuration controls from the user-facing interface. Bedrock settings are configured through `.streamlit/secrets.toml` locally or environment variables in AWS.

## Conversation History

Local testing uses local JSONL history:

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

For the reusable AWS deployment procedure, see:

```text
docs/aws-deployment-runbook.md
```

The current supported hosting path is CloudFront HTTPS in front of ECS Fargate and an Application Load Balancer. A secure CloudFront URL should be used for public deployments. The raw HTTP ALB URL is not user-facing and should not be shared as the chatbot link.

Streamlit requires a working WebSocket route, and the templates are configured for that behavior. The ECS template keeps at least 2 tasks running and can autoscale up to 6 tasks based on CPU or memory.

## Main Files

- `app.py`: Streamlit UI and chat flow
- `bedrock_kb.py`: Bedrock Knowledge Base request builder and response helpers
- `history_store.py`: local JSONL and AWS DynamoDB/S3 history logging
- `prompts/generation_prompt.txt`: sample math-coach generation prompt
- `docs/data-requirements.md`: data requirements for a real math-coach deployment
- `.streamlit/secrets.example.toml`: local configuration template
- `deploy/aws-history-resources.yml`: DynamoDB, S3, and runtime IAM role
- `deploy/aws-build-resources.yml`: S3 source bucket and CodeBuild image builder
- `deploy/aws-ecs-fargate-service.yml`: ECS Fargate and ALB service
- `deploy/aws-cloudfront-https.yml`: CloudFront HTTPS endpoint for the ALB
- `docs/aws-deployment-runbook.md`: AWS deployment guide
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
