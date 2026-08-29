# AWS Deployment Runbook

Maintainer: `song9fl`

This is a reusable deployment guide for the AWS Bedrock Knowledge Base chatbot. The repository includes a math-coach prompt and deployment pattern, but it does not include the curriculum dataset or populated Bedrock Knowledge Base required for a real K-12 math-coach deployment.

Use your own Bedrock Knowledge Base ID, AWS profile, account ID, credentials, buckets, and deployment URLs unless I explicitly provide limited test credentials.

## Project Values

Use these project-level values:

```text
APP_NAME=bedrock-kb-chatbot
AWS_REGION=us-east-1
KB_ID=YOUR_POPULATED_KNOWLEDGE_BASE_ID
MODEL_ID=meta.llama4-maverick-17b-instruct-v1:0
INFERENCE_PROFILE_NAME=us.meta.llama4-maverick-17b-instruct-v1:0
```

Use your own account-level values:

```text
AWS_PROFILE=YOUR_PROFILE_NAME
ACCOUNT_ID=YOUR_AWS_ACCOUNT_ID
HISTORY_BUCKET=YOUR_GLOBALLY_UNIQUE_HISTORY_BUCKET
BUILD_BUCKET=YOUR_GLOBALLY_UNIQUE_BUILD_BUCKET
```

Derived ARNs:

```text
KB_ARN=arn:aws:bedrock:us-east-1:YOUR_AWS_ACCOUNT_ID:knowledge-base/YOUR_POPULATED_KNOWLEDGE_BASE_ID
MODEL_ARN=arn:aws:bedrock:us-east-1:YOUR_AWS_ACCOUNT_ID:inference-profile/us.meta.llama4-maverick-17b-instruct-v1:0
ECR_URI=YOUR_AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/bedrock-kb-chatbot
```

Before deploying a math-coach instance, create or select a Bedrock Knowledge Base that has been synced with appropriate math source documents. See `docs/data-requirements.md`.

## Local AWS Profile

Create or use an AWS CLI profile:

```bash
aws configure --profile YOUR_PROFILE_NAME
```

Check the account:

```bash
aws sts get-caller-identity --profile YOUR_PROFILE_NAME
```

The `Account` value from that command is your `ACCOUNT_ID`.

For local Streamlit testing, put the profile in `.streamlit/secrets.toml`:

```toml
[aws]
region = "us-east-1"
profile = "YOUR_PROFILE_NAME"

[bedrock]
knowledge_base_id = "YOUR_POPULATED_KNOWLEDGE_BASE_ID"
model_arn = "arn:aws:bedrock:us-east-1:YOUR_AWS_ACCOUNT_ID:inference-profile/us.meta.llama4-maverick-17b-instruct-v1:0"
```

Do not commit `.streamlit/secrets.toml`.

## Architecture

The supported production path is CloudFront HTTPS in front of ECS Fargate and an Application Load Balancer.

Every public deployment from this project should have a secure public web link before it is shared with reviewers or users. The required user-facing link is the CloudFront `https://...cloudfront.net` URL or a custom HTTPS domain pointed at CloudFront.

Do not use the raw HTTP ALB URL as the user-facing URL. CloudFront provides the secure endpoint and forwards Streamlit WebSocket traffic to the ALB. After CloudFront is working, I restrict the ALB security group so only CloudFront origin-facing IPs can reach it.

Do not use App Runner for this Streamlit UI. Streamlit needs a working WebSocket route. CloudFront plus ECS/ALB should be verified with:

```text
/                  -> 200 OK
/_stcore/health    -> 200 OK
/_stcore/stream    -> 101 Switching Protocols
```

## Private Deployment Record

The live deployment record is intentionally excluded from the public repository because it contains operational URLs, account-specific resource names, and references to external data sources.

For production deployments, add CloudFront HTTPS in front of the ECS/ALB service and restrict direct ALB access to CloudFront origin-facing IPs.

Secure chatbot URL:

```text
https://YOUR_CLOUDFRONT_DISTRIBUTION.cloudfront.net
```

Verification completed:

```text
HTTPS homepage      -> 200 OK
Streamlit health    -> 200 OK
Streamlit WebSocket -> 101 Switching Protocols
Direct raw ALB HTTP  -> not user-facing
```

## Production Capacity Default

For reviewer-facing or user-facing deployments, I keep at least 2 ECS Fargate tasks running. The ECS template also enables target-tracking autoscaling:

```text
DesiredCount=2
MinTaskCount=2
MaxTaskCount=6
CpuTargetValue=60
MemoryTargetValue=70
```

This gives the chatbot a healthier baseline than a single task, keeps the service available during deployments, and lets ECS add capacity when CPU or memory pressure rises. DynamoDB history uses on-demand billing, and S3 logging is not expected to be the first bottleneck.

## Required AWS Permissions

The runtime role needs:

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

For this Llama 4 Maverick inference profile, Bedrock can route the underlying model call across US Bedrock regions. The runtime role should allow the inference profile ARN plus foundation-model invocation:

```text
arn:aws:bedrock:us-east-1:YOUR_AWS_ACCOUNT_ID:inference-profile/us.meta.llama4-maverick-17b-instruct-v1:0
arn:aws:bedrock:*::foundation-model/*
```

## Set Shell Variables

```bash
export AWS_PROFILE=YOUR_PROFILE_NAME
export AWS_REGION=us-east-1
export APP_NAME=bedrock-kb-chatbot
export ACCOUNT_ID=YOUR_AWS_ACCOUNT_ID
export KB_ID=YOUR_POPULATED_KNOWLEDGE_BASE_ID
export KB_ARN="arn:aws:bedrock:${AWS_REGION}:${ACCOUNT_ID}:knowledge-base/${KB_ID}"
export MODEL_ARN="arn:aws:bedrock:${AWS_REGION}:${ACCOUNT_ID}:inference-profile/us.meta.llama4-maverick-17b-instruct-v1:0"
export ECR_REPO=bedrock-kb-chatbot
export ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"
export HISTORY_BUCKET=YOUR_GLOBALLY_UNIQUE_HISTORY_BUCKET
export BUILD_BUCKET=YOUR_GLOBALLY_UNIQUE_BUILD_BUCKET
export CLOUDFRONT_PREFIX_LIST_ID=YOUR_CLOUDFRONT_ORIGIN_FACING_PREFIX_LIST_ID
```

Find the CloudFront origin-facing prefix list in `us-east-1`:

```bash
aws ec2 describe-managed-prefix-lists \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --filters Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing \
  --query 'PrefixLists[0].PrefixListId' \
  --output text
```

## Create History Resources

This stack creates DynamoDB, S3 history logging, and the runtime role:

```bash
aws cloudformation deploy \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --template-file deploy/aws-history-resources.yml \
  --stack-name bedrock-kb-chatbot-history \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    AppName="$APP_NAME" \
    HistoryBucketName="$HISTORY_BUCKET" \
    BedrockKnowledgeBaseArn="$KB_ARN" \
    BedrockModelOrInferenceProfileArn="$MODEL_ARN"
```

## History Data Model

History writes happen on every chat event. The app writes the same record to DynamoDB and S3 at the same time.
This history structure is supported by the current app code and reusable for future chatbot deployments from this project.

### DynamoDB

Table name:

```text
bedrock-kb-chatbot-history
```

Primary key shape:

```text
pk = SCHOOL#{school_id}
sk = {timestamp}#{event_id}
```

Common record fields:

```text
timestamp
event_id
event
school_id
session_id
bedrock_session_id
role
content
citation_count
citation_sources
event_tags
client_ip
metadata
```

Important event names:

```text
school_id_submitted
chat_message
sources_clicked
sources_not_clicked
```

### S3

Bucket name:

```text
YOUR_GLOBALLY_UNIQUE_HISTORY_BUCKET
```

Prefix:

```text
chat-history/
```

Object key layout:

```text
chat-history/year=YYYY/month=MM/day=DD/
  school_id_hash=<hash>/session_id=<session_id>/
  <timestamp>_<event_id>.json
```

Each S3 object stores one JSON event record. S3 does not mirror DynamoDB later; the app writes both destinations directly during the same append call.

For source tracking:
- `sources_clicked` means the user opened the Sources control for that answer.
- `sources_not_clicked` means the answer was rendered with sources but the user did not open them.
- `content` still shows the visible label, such as `Sources (4)`.
- `metadata.message_id` ties the event back to the specific assistant response.

## Create ECR And Build Resources

Create the ECR repository:

```bash
aws ecr create-repository \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --repository-name "$ECR_REPO"
```

If it already exists, continue.

Create the CodeBuild resources:

```bash
aws cloudformation deploy \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --template-file deploy/aws-build-resources.yml \
  --stack-name bedrock-kb-chatbot-build \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    AppName="$APP_NAME" \
    SourceBucketName="$BUILD_BUCKET" \
    EcrRepositoryArn="arn:aws:ecr:${AWS_REGION}:${ACCOUNT_ID}:repository/${ECR_REPO}" \
    EcrRepositoryName="$ECR_REPO"
```

## Build And Push Image

```bash
export IMAGE_TAG="$(date +%Y%m%d%H%M%S)"

zip -r /tmp/bedrock-kb-chatbot-source.zip . \
  -x ".venv/*" "__pycache__/*" "*.pyc" ".DS_Store" "logs/*" "tests/*" ".streamlit/secrets.toml" ".git/*"

aws s3 cp \
  /tmp/bedrock-kb-chatbot-source.zip \
  "s3://${BUILD_BUCKET}/${APP_NAME}-source.zip" \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE"

aws codebuild start-build \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --project-name "${APP_NAME}-image-build" \
  --environment-variables-override name=IMAGE_TAG,value="$IMAGE_TAG",type=PLAINTEXT
```

When the build succeeds:

```bash
export IMAGE_URI="${ECR_URI}:${IMAGE_TAG}"
```

## Deploy ECS Fargate

Find a VPC and public subnets in the target AWS account:

```bash
aws ec2 describe-vpcs \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --filters Name=is-default,Values=true \
  --query 'Vpcs[0].VpcId' \
  --output text

aws ec2 describe-subnets \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --filters Name=default-for-az,Values=true \
  --query 'Subnets[].SubnetId' \
  --output text
```

Deploy:

```bash
aws cloudformation deploy \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --template-file deploy/aws-ecs-fargate-service.yml \
  --stack-name bedrock-kb-chatbot-ecs \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    AppName="$APP_NAME" \
    ImageUri="$IMAGE_URI" \
    RuntimeRoleArn="arn:aws:iam::${ACCOUNT_ID}:role/${APP_NAME}-runtime-role" \
    AwsRegion="$AWS_REGION" \
    VpcId="YOUR_VPC_ID" \
    PublicSubnetIds="SUBNET_1,SUBNET_2,SUBNET_3" \
    BedrockKnowledgeBaseId="$KB_ID" \
    BedrockModelArn="$MODEL_ARN" \
    ChatHistoryTable="${APP_NAME}-history" \
    ChatHistoryBucket="$HISTORY_BUCKET" \
    ChatHistoryPrefix="chat-history" \
    DesiredCount=2 \
    MinTaskCount=2 \
    MaxTaskCount=6 \
    CpuTargetValue=60 \
    MemoryTargetValue=70
```

Get the ALB DNS name:

```bash
aws cloudformation describe-stacks \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --stack-name bedrock-kb-chatbot-ecs \
  --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerDnsName`].OutputValue' \
  --output text
```

## Deploy CloudFront HTTPS

Create the HTTPS distribution:

```bash
aws cloudformation deploy \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --template-file deploy/aws-cloudfront-https.yml \
  --stack-name bedrock-kb-chatbot-cloudfront \
  --parameter-overrides \
    AppName="$APP_NAME" \
    AlbDnsName="YOUR_ALB_DNS_NAME" \
    PriceClass=PriceClass_100
```

Get the secure URL:

```bash
aws cloudformation describe-stacks \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --stack-name bedrock-kb-chatbot-cloudfront \
  --query 'Stacks[0].Outputs[?OutputKey==`HttpsUrl`].OutputValue' \
  --output text
```

After CloudFront works, restrict the ALB so only CloudFront origin-facing IPs can reach it:

```bash
aws cloudformation deploy \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --template-file deploy/aws-ecs-fargate-service.yml \
  --stack-name bedrock-kb-chatbot-ecs \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    AppName="$APP_NAME" \
    ImageUri="$IMAGE_URI" \
    RuntimeRoleArn="arn:aws:iam::${ACCOUNT_ID}:role/${APP_NAME}-runtime-role" \
    AwsRegion="$AWS_REGION" \
    VpcId="YOUR_VPC_ID" \
    PublicSubnetIds="SUBNET_1,SUBNET_2,SUBNET_3" \
    BedrockKnowledgeBaseId="$KB_ID" \
    BedrockModelArn="$MODEL_ARN" \
    ChatHistoryTable="${APP_NAME}-history" \
    ChatHistoryBucket="$HISTORY_BUCKET" \
    ChatHistoryPrefix="chat-history" \
    DesiredCount=2 \
    MinTaskCount=2 \
    MaxTaskCount=6 \
    CpuTargetValue=60 \
    MemoryTargetValue=70 \
    AllowedHttpPrefixListId="$CLOUDFRONT_PREFIX_LIST_ID"
```

## Verify Deployment

```bash
export SERVICE_URL=YOUR_CLOUDFRONT_HTTPS_URL
curl -I "$SERVICE_URL"
curl -I "$SERVICE_URL/_stcore/health"
```

Check WebSocket support:

```bash
curl -i -N --max-time 15 \
  -H 'Connection: Upgrade' \
  -H 'Upgrade: websocket' \
  -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
  -H 'Sec-WebSocket-Version: 13' \
  -H 'Sec-WebSocket-Protocol: streamlit' \
  -H "Origin: ${SERVICE_URL}" \
  "${SERVICE_URL}/_stcore/stream"
```

Expected:

```text
HTTP/1.1 101 Switching Protocols
```

## Logs

Application logs:

```bash
aws logs describe-log-streams \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --log-group-name /ecs/bedrock-kb-chatbot \
  --order-by LastEventTime \
  --descending \
  --max-items 5
```

Read a stream:

```bash
aws logs get-log-events \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --log-group-name /ecs/bedrock-kb-chatbot \
  --log-stream-name LOG_STREAM_NAME \
  --limit 120 \
  --query 'events[].message' \
  --output text
```

## Common Errors

`I could not reach the knowledge base. Please try again later.`

Check ECS logs. The app prints the underlying Bedrock or AWS exception.

`bedrock:Retrieve` denied

Add `bedrock:Retrieve` to the runtime role for the Knowledge Base ARN.

`GetInferenceProfile` denied

Add `bedrock:GetInferenceProfile` for the inference profile ARN.

`InvokeModel` denied on a foundation model ARN

The inference profile routed to an underlying model resource. Allow `arn:aws:bedrock:*::foundation-model/*` for model invocation.

Blank page

Check that the WebSocket endpoint returns `101 Switching Protocols`. If it returns `403`, the hosting runtime is not forwarding Streamlit WebSockets correctly.

Raw ALB URL still works over HTTP

Update the ECS stack with `AllowedHttpPrefixListId` set to the CloudFront origin-facing prefix list ID. The user-facing URL should be CloudFront HTTPS, not the ALB HTTP URL.

## Prompt Updates

If `prompts/generation_prompt.txt` changes, rebuild and redeploy the container image. The live ECS task reads the prompt from the image filesystem.
