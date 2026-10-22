from __future__ import annotations

import abc
import datetime
import json
import logging
import re
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


class QAItem(BaseModel):
    title: str = Field(..., description="Short title of the test idea")
    description: str = Field(..., description="Test procedure or condition to verify")
    expected_result: str = Field(..., description="Expected device behavior grounded in text")
    source_reference: str = Field(..., description="Section heading, number, or exact clause referenced")


class QAResult(BaseModel):
    node_id: str
    version: str
    content_hash: str
    generated_at: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    provider: str
    test_ideas: list[QAItem] = Field(..., min_length=3, max_length=5)



class LLMGenerationError(Exception):
    """Raised when structured LLM QA generation fails after all bounded retries."""
    pass


class BaseLLMProvider(abc.ABC):
    @abc.abstractmethod
    def generate_raw(
        self,
        node_id: str,
        version: str,
        heading: str,
        content: str,
        retry_count: int = 0,
    ) -> str:
        """Return raw JSON string from LLM."""
        pass

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        pass

    @property
    def name(self) -> str:
        return self.provider_name

    def generate_qa(
        self,
        context: str = "",
        content: str = "",
        node_id: str = "unknown",
        heading: str = "unknown",
        version: str = "v1",
    ) -> str:
        text = content or context
        return self.generate_raw(node_id=node_id, version=version, heading=heading, content=text)



class GeminiLLMProvider(BaseLLMProvider):
    def __init__(self, api_key: str, model_name: str = "gemini-1.5-flash"):
        self.api_key = api_key
        self.model_name = model_name
        self._configured = False

    def _init_gemini(self):
        if not self._configured:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._configured = True

    @property
    def provider_name(self) -> str:
        return f"gemini ({self.model_name})"

    def generate_raw(
        self,
        node_id: str,
        version: str,
        heading: str,
        content: str,
        retry_count: int = 0,
    ) -> str:
        self._init_gemini()
        import google.generativeai as genai

        prompt = f"""You are a medical device QA engineer.
Your task is to generate 3 to 5 structured test ideas grounded STRICTLY and ONLY in the provided manual section.
Do NOT invent specifications or requirements not mentioned in the text.

Section Node ID: {node_id} (Manual Version {version})
Heading: {heading}
Content:
\"\"\"{content}\"\"\"

Generate a valid JSON object matching this schema:
{{
  "test_ideas": [
    {{
      "title": "Short title of test",
      "description": "Specific test procedure or condition to verify",
      "expected_result": "Exact expected device behavior based on manual text",
      "source_reference": "Section {node_id} - {heading}"
    }}
  ]
}}

Requirements:
1. Provide between 3 and 5 test ideas (inclusive).
2. Return ONLY the raw JSON object. No markdown fences, no explanatory text.
"""
        model = genai.GenerativeModel(self.model_name)
        response = model.generate_content(prompt)
        text = response.text.strip()
        # Clean markdown code fences if present
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        return text.strip()


class DeterministicFallbackProvider(BaseLLMProvider):
    """
    Deterministic rule-based QA idea generator used when no external API key
    is configured or when running offline. Always produces 3-4 grounded test ideas.
    """

    @property
    def provider_name(self) -> str:
        return "deterministic-fallback"

    def generate_raw(
        self,
        node_id: str,
        version: str,
        heading: str,
        content: str,
        retry_count: int = 0,
    ) -> str:
        source_ref = f"Section {node_id} ({heading}, {version})"
        test_ideas: list[dict[str, str]] = []

        # 1. Functional Verification Idea
        test_ideas.append(
            {
                "title": f"Verify Functional Behavior for {heading}",
                "description": f"Execute standard device operation and verify compliance with the documented behavior for '{heading}'.",
                "expected_result": f"Device operates strictly in accordance with documented procedure in Section {node_id}.",
                "source_reference": source_ref,
            }
        )

        # 2. Limit / Threshold / Boundary Idea
        # Look for numeric patterns in content (e.g. mmHg, cycles, %, seconds)
        num_match = re.findall(r"(\d+(?:\.\d+)?\s*(?:mmHg|bpm|cm|cycles|%|seconds?|years?|V))", content, re.IGNORECASE)
        if num_match:
            spec_item = ", ".join(num_match[:2])
            test_ideas.append(
                {
                    "title": f"Boundary and Threshold Verification ({spec_item})",
                    "description": f"Test device limits at threshold values ({spec_item}) described in Section {node_id}.",
                    "expected_result": f"Device honors stated parameter thresholds ({spec_item}) without deviation or unexpected shutoff.",
                    "source_reference": source_ref,
                }
            )
        else:
            test_ideas.append(
                {
                    "title": f"Boundary and Constraint Verification for {heading}",
                    "description": f"Validate all constraints and environmental boundaries stipulated in '{heading}'.",
                    "expected_result": f"Device maintains normal operating bounds as specified in Section {node_id}.",
                    "source_reference": source_ref,
                }
            )

        # 3. Error Handling / Fault Condition Idea
        # Look for error codes or safety mentions
        err_match = re.findall(r"(E[1-6]|fault|leak|artifact|overpressure|contraindication)", content, re.IGNORECASE)
        if err_match:
            err_term = err_match[0]
            test_ideas.append(
                {
                    "title": f"Safety Fault / Error Condition Test ({err_term})",
                    "description": f"Simulate fault or edge condition related to '{err_term}' in Section {node_id}.",
                    "expected_result": f"Device detects condition '{err_term}', displays proper indication, and aborts or protects safely.",
                    "source_reference": source_ref,
                }
            )
        else:
            test_ideas.append(
                {
                    "title": f"Negative / Invalid Input Handling for {heading}",
                    "description": f"Simulate anomalous user operation or disrupted sequence during '{heading}'.",
                    "expected_result": f"Device handles unexpected condition safely without corrupting memory or entering an undefined state.",
                    "source_reference": source_ref,
                }
            )

        # 4. User Feedback and Indicator Test
        test_ideas.append(
            {
                "title": f"Display and Feedback Verification for {heading}",
                "description": f"Inspect visual icons, LCD indicators, or audible alerts associated with '{heading}'.",
                "expected_result": f"All indications match documentation for Section {node_id} on version {version}.",
                "source_reference": source_ref,
            }
        )

        return json.dumps({"test_ideas": test_ideas})


class LLMGenerationService:
    """
    Orchestrates LLM QA generation with Pydantic validation and bounded retries.
    """

    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        gemini_model: str = "gemini-1.5-flash",
        max_retries: int = 3,
        provider: Optional[BaseLLMProvider] = None,
    ):
        self.max_retries = max_retries
        if provider is not None:
            self.provider = provider
            logger.info(f"Using explicitly configured provider: {provider.provider_name}")
        elif gemini_api_key and gemini_api_key.strip():
            self.provider = GeminiLLMProvider(
                api_key=gemini_api_key.strip(),
                model_name=gemini_model,
            )
            logger.info("Configured GeminiLLMProvider for QA generation.")
        else:
            self.provider = DeterministicFallbackProvider()
            logger.info("No Gemini API key found. Using DeterministicFallbackProvider.")


    def generate_qa(
        self,
        node_id: str = "unknown",
        version: str = "v1",
        heading: str = "unknown",
        content: str = "",
        content_hash: str = "",
        context: str = "",
    ) -> QAResult:
        """
        Generate structured QA ideas for a node with bounded retry on malformed outputs.
        """
        effective_content = content or context
        last_error: Optional[str] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                raw_text = self.provider.generate_raw(
                    node_id=node_id,
                    version=version,
                    heading=heading,
                    content=effective_content,
                    retry_count=attempt - 1,
                )

                # Attempt JSON parsing
                try:
                    data = json.loads(raw_text)
                except json.JSONDecodeError as jde:
                    raise ValueError(f"Malformed JSON returned by provider: {jde}")

                if not isinstance(data, dict) or "test_ideas" not in data:
                    raise ValueError("Response JSON missing required 'test_ideas' key")

                test_ideas_data = data["test_ideas"]
                if not isinstance(test_ideas_data, list):
                    raise ValueError("'test_ideas' must be a list")

                if len(test_ideas_data) < 3 or len(test_ideas_data) > 5:
                    raise ValueError(
                        f"Expected between 3 and 5 test ideas, but got {len(test_ideas_data)}"
                    )

                # Validate individual items
                parsed_items: list[QAItem] = []
                for item_dict in test_ideas_data:
                    parsed_items.append(QAItem.model_validate(item_dict))

                # Build validated QAResult
                now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
                result = QAResult(
                    node_id=node_id,
                    version=version,
                    content_hash=content_hash,
                    generated_at=now_str,
                    provider=self.provider.provider_name,
                    test_ideas=parsed_items,
                )
                return result

            except (ValueError, ValidationError) as ex:
                last_error = str(ex)
                logger.warning(
                    f"Attempt {attempt}/{self.max_retries} failed structured QA validation for node {node_id}: {last_error}"
                )

                # Fallback to deterministic provider on final retry if Gemini failed
                if attempt == self.max_retries - 1 and isinstance(self.provider, GeminiLLMProvider):
                    logger.info("Switching to DeterministicFallbackProvider for final attempt.")
                    self.provider = DeterministicFallbackProvider()

        raise LLMGenerationError(
            f"Failed to generate valid structured QA for node '{node_id}' after {self.max_retries} retries. "
            f"Last validation error: {last_error}"
        )
