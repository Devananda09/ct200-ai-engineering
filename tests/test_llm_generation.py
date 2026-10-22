import json
import pytest
from pydantic import ValidationError
from app.services.llm_provider import (
    QAItem,
    QAResult,
    DeterministicFallbackProvider,
    LLMGenerationService,
    BaseLLMProvider,
    LLMGenerationError,
)



def test_qa_item_and_result_schema():
    item1 = QAItem(
        title="Battery Cycle Test",
        description="Verify device powers at least 250 cycles.",
        expected_result="Device operates without shutdown for 250 cycles.",
        source_reference="Section 2.1.1.1",
    )
    item2 = QAItem(
        title="Low Battery Warning",
        description="Check warning activates at 10% battery level.",
        expected_result="Low battery indicator flashes on display.",
        source_reference="Section 2.1.1.1",
    )
    item3 = QAItem(
        title="Cuff Inflation Pressure",
        description="Verify initial inflation steps in 30 mmHg increments.",
        expected_result="Pressure gauge advances smoothly by 30 mmHg.",
        source_reference="Section 3.2",
    )

    # Valid: 3 items
    res_valid = QAResult(
        node_id="2.1.1.1",
        version="v2",
        content_hash="abc12345",
        generated_at="2026-10-23T00:00:00Z",
        provider="test-provider",
        test_ideas=[item1, item2, item3],
    )
    assert len(res_valid.test_ideas) == 3

    # Invalid: fewer than 3 items
    with pytest.raises(ValidationError):
        QAResult(
            node_id="2.1.1.1",
            version="v2",
            content_hash="abc12345",
            generated_at="2026-10-23T00:00:00Z",
            provider="test-provider",
            test_ideas=[item1, item2],
        )

    # Invalid: more than 5 items
    with pytest.raises(ValidationError):
        QAResult(
            node_id="2.1.1.1",
            version="v2",
            content_hash="abc12345",
            generated_at="2026-10-23T00:00:00Z",
            provider="test-provider",
            test_ideas=[item1, item2, item3, item1, item2, item3],
        )


def test_deterministic_fallback_provider():
    provider = DeterministicFallbackProvider()
    assert provider.name == "deterministic-fallback"

    context = (
        "Operating temperature: 10°C to 40°C. Cuff pressure range: 0 to 299 mmHg. "
        "Pulse rate: 40 to 180 beats/min. Overpressure safety limit: 300 mmHg auto-deflate. "
        "Display shows SYS, DIA, and PULSE readings simultaneously."
    )

    raw_output = provider.generate_qa(context=context, node_id="2.1", heading="General Specs")
    data = json.loads(raw_output)
    assert "test_ideas" in data
    assert 3 <= len(data["test_ideas"]) <= 5

    # Validate against Pydantic schema
    qa_result = QAResult(
        node_id="2.1",
        version="v1",
        content_hash="samplehash",
        provider=provider.name,
        test_ideas=[QAItem(**item) for item in data["test_ideas"]],
    )
    assert len(qa_result.test_ideas) >= 3
    for idea in qa_result.test_ideas:
        assert idea.title
        assert idea.description
        assert idea.expected_result
        assert "2.1" in idea.source_reference


class MockFlakyLLMProvider(BaseLLMProvider):
    """
    Mock provider that returns malformed JSON on first calls, then valid JSON on retry.
    """
    def __init__(self, fail_count: int = 1, fail_mode: str = "malformed_json"):
        self.call_count = 0
        self.fail_count = fail_count
        self.fail_mode = fail_mode

    @property
    def provider_name(self) -> str:
        return "mock-flaky-llm"

    def generate_raw(
        self,
        node_id: str,
        version: str,
        heading: str,
        content: str,
        retry_count: int = 0,
    ) -> str:
        self.call_count += 1
        if self.call_count <= self.fail_count:
            if self.fail_mode == "malformed_json":
                return "This is not valid JSON at all!"
            elif self.fail_mode == "too_few_items":
                return json.dumps({
                    "test_ideas": [
                        {
                            "title": "Only one idea",
                            "description": "Desc",
                            "expected_result": "Result",
                            "source_reference": node_id,
                        }
                    ]
                })

        # Valid response
        return json.dumps({
            "test_ideas": [
                {
                    "title": "Idea 1",
                    "description": "Desc 1",
                    "expected_result": "Result 1",
                    "source_reference": f"Section {node_id}",
                },
                {
                    "title": "Idea 2",
                    "description": "Desc 2",
                    "expected_result": "Result 2",
                    "source_reference": f"Section {node_id}",
                },
                {
                    "title": "Idea 3",
                    "description": "Desc 3",
                    "expected_result": "Result 3",
                    "source_reference": f"Section {node_id}",
                },
            ]
        })


def test_llm_service_retry_on_malformed_json():
    flaky_provider = MockFlakyLLMProvider(fail_count=1, fail_mode="malformed_json")
    service = LLMGenerationService(provider=flaky_provider, max_retries=3)

    result = service.generate_qa(
        context="Sample node content",
        node_id="3.1",
        heading="Operation",
        version="v1",
        content_hash="hash31",
    )
    assert flaky_provider.call_count == 2
    assert len(result.test_ideas) == 3
    assert result.provider == "mock-flaky-llm"


def test_llm_service_retry_on_invalid_count():
    flaky_provider = MockFlakyLLMProvider(fail_count=1, fail_mode="too_few_items")
    service = LLMGenerationService(provider=flaky_provider, max_retries=3)

    result = service.generate_qa(
        context="Sample node content",
        node_id="3.1",
        heading="Operation",
        version="v1",
        content_hash="hash31",
    )
    assert flaky_provider.call_count == 2
    assert len(result.test_ideas) == 3


def test_llm_service_bounded_retry_exhaustion_raises():
    flaky_provider = MockFlakyLLMProvider(fail_count=5, fail_mode="malformed_json")
    service = LLMGenerationService(provider=flaky_provider, max_retries=2)

    with pytest.raises((ValueError, LLMGenerationError), match="Failed to generate valid"):
        service.generate_qa(
            context="Sample node content",
            node_id="3.1",
            heading="Operation",
            version="v1",
            content_hash="hash31",
        )
    assert flaky_provider.call_count == 2

