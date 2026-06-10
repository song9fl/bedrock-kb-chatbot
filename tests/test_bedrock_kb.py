from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from bedrock_kb import (  # noqa: E402
    BedrockKnowledgeBaseSettings,
    build_retrieve_and_generate_request,
    extract_citations,
    validate_generation_prompt,
)


PROMPT = "Use this context: $search_results$\nQuestion: $query$\n$output_format_instructions$"


class BedrockKnowledgeBaseTests(unittest.TestCase):
    def test_builds_knowledge_base_request_with_saved_prompt_and_session(self) -> None:
        settings = BedrockKnowledgeBaseSettings(
            region_name="us-east-1",
            knowledge_base_id="KB123",
            model_arn="arn:aws:bedrock:us-east-1::foundation-model/test-model",
            number_of_results=8,
            search_type="HYBRID",
            max_tokens=1024,
            temperature=0.1,
            top_p=0.8,
            guardrail_id="gr-123",
            guardrail_version="1",
            kms_key_arn="arn:aws:kms:us-east-1:123456789012:key/example",
            query_decomposition=True,
        )

        request = build_retrieve_and_generate_request(
            query="  What is covered?  ",
            settings=settings,
            prompt_template=PROMPT,
            session_id="existing-session",
        )

        self.assertEqual(request["input"]["text"], "What is covered?")
        self.assertEqual(request["sessionId"], "existing-session")
        self.assertNotIn("sessionConfiguration", request)

        config = request["retrieveAndGenerateConfiguration"]
        self.assertEqual(config["type"], "KNOWLEDGE_BASE")
        kb_config = config["knowledgeBaseConfiguration"]
        self.assertEqual(kb_config["knowledgeBaseId"], "KB123")
        self.assertEqual(kb_config["modelArn"], "arn:aws:bedrock:us-east-1::foundation-model/test-model")
        self.assertEqual(
            kb_config["generationConfiguration"]["promptTemplate"]["textPromptTemplate"],
            PROMPT,
        )
        self.assertEqual(
            kb_config["generationConfiguration"]["guardrailConfiguration"],
            {"guardrailId": "gr-123", "guardrailVersion": "1"},
        )
        self.assertEqual(
            kb_config["retrievalConfiguration"]["vectorSearchConfiguration"],
            {"numberOfResults": 8, "overrideSearchType": "HYBRID"},
        )
        self.assertEqual(
            kb_config["orchestrationConfiguration"]["queryTransformationConfiguration"]["type"],
            "QUERY_DECOMPOSITION",
        )

    def test_default_search_omits_override_and_adds_kms_for_new_session(self) -> None:
        settings = BedrockKnowledgeBaseSettings(
            region_name="us-east-1",
            knowledge_base_id="KB123",
            model_arn="arn:aws:bedrock:us-east-1::foundation-model/test-model",
            search_type="DEFAULT",
            kms_key_arn="arn:aws:kms:us-east-1:123456789012:key/example",
        )

        request = build_retrieve_and_generate_request("Question?", settings, PROMPT)
        vector_config = request["retrieveAndGenerateConfiguration"]["knowledgeBaseConfiguration"][
            "retrievalConfiguration"
        ]["vectorSearchConfiguration"]

        self.assertEqual(vector_config, {"numberOfResults": 5})
        self.assertEqual(
            request["sessionConfiguration"],
            {"kmsKeyArn": "arn:aws:kms:us-east-1:123456789012:key/example"},
        )

    def test_prompt_validation_requires_search_results(self) -> None:
        validation = validate_generation_prompt("No placeholders here.")

        self.assertTrue(validation["errors"])
        self.assertTrue(validation["warnings"])

    def test_extract_citations_handles_text_rows_and_metadata(self) -> None:
        response = {
            "citations": [
                {
                    "generatedResponsePart": {
                        "textResponsePart": {
                            "text": "Cited generated sentence.",
                        }
                    },
                    "retrievedReferences": [
                        {
                            "content": {"text": "A source paragraph."},
                            "location": {"s3Location": {"uri": "s3://bucket/doc.pdf"}},
                            "metadata": {
                                "x-amz-bedrock-kb-source-uri": "s3://bucket/doc.pdf",
                                "x-amz-bedrock-kb-document-page-number": 7,
                            },
                        },
                        {
                            "content": {
                                "row": [
                                    {"columnName": "Name", "columnValue": "Alpha"},
                                    {"columnName": "Score", "columnValue": "42"},
                                ]
                            },
                            "location": {"webLocation": {"url": "https://example.com/table"}},
                            "metadata": {},
                        },
                    ],
                }
            ]
        }

        citations = extract_citations(response)

        self.assertEqual(len(citations), 2)
        self.assertEqual(citations[0]["source"], "s3://bucket/doc.pdf")
        self.assertEqual(citations[0]["page"], "7")
        self.assertEqual(citations[0]["content"], "A source paragraph.")
        self.assertEqual(citations[1]["source"], "https://example.com/table")
        self.assertIn("Name: Alpha", citations[1]["content"])


if __name__ == "__main__":
    unittest.main()
