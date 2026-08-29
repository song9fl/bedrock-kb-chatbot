# Data Requirements

This repository does not include a math curriculum dataset or a populated Amazon Bedrock Knowledge Base. It is the chatbot code, prompt, history logging, and AWS deployment template.

To make the app function as a real K-12 math coach, attach an external data source to Bedrock Knowledge Bases and sync it before deploying the app.

## Required Data

Use source material that the chatbot is allowed to retrieve from:

- Grade-level math curriculum documents.
- Lesson notes or worked examples.
- Problem-solving explanations.
- School or classroom-approved support material.
- Any usage, citation, or safety guidance that should shape answers.

Do not add student records, private teacher notes, credentials, or copyrighted files unless you have permission to use them in the target deployment.

## Bedrock Setup

1. Prepare the source documents.
2. Upload them to the selected Bedrock Knowledge Base data source.
3. Sync the Knowledge Base.
4. Put the resulting `knowledge_base_id` in `.streamlit/secrets.toml` for local testing or `BEDROCK_KB_ID` for AWS deployment.
5. Keep the live Knowledge Base ID, S3 buckets, account IDs, and deployment URLs out of the public repo.

## Expected Behavior Without Data

Without a populated Knowledge Base, the app still runs as a Streamlit chatbot shell, but it cannot produce grounded math-coach answers. The prompt and post-processing can shape tone, but the actual math content must come from retrieved Knowledge Base chunks.
