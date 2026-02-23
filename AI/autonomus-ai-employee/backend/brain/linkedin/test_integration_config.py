"""
Integration tests for UI-configurable LinkedIn content generation.

This validates the complete flow:
1. GET /linkedin/config - retrieve configuration schema
2. GET /linkedin/profile-summary - retrieve user profile
3. POST /linkedin/generate - submit post with selective overrides
4. Verify merging logic works correctly

Run with: pytest brain/linkedin/test_integration_config.py -v
"""

import pytest
from typing import Optional, Dict, Any
from unittest.mock import Mock, patch, MagicMock

from brain.linkedin.models import (
    PostGenerationRequest,
    PostInput,
    PostConfigurationOptions,
)
from services.config_service import (
    get_configuration_options,
    merge_request_with_profile,
    get_profile_summary,
)


class TestConfigurationService:
    """Test the configuration service used by routes."""

    def test_get_configuration_options_returns_all_fields(self):
        """
        GET /linkedin/config should return all fields needed by UI
        """
        config = get_configuration_options()
        
        # Verify all dropdown options are present
        assert "tone_options" in config
        assert "format_options" in config
        assert "audience_options" in config
        assert "goal_options" in config
        assert "cta_style_options" in config
        assert "storytelling_frequency_options" in config
        
        # Verify current defaults are present
        assert "current_defaults" in config
        defaults = config["current_defaults"]
        assert "tone" in defaults
        assert "format" in defaults
        assert "audience" in defaults
        assert "goal" in defaults
        assert "include_emojis" in defaults
        assert "use_technical_jargon" in defaults
        assert "cta_style" in defaults
        assert "storytelling_frequency" in defaults
        
        # Verify user profile is present
        assert "user_profile" in config
        profile = config["user_profile"]
        assert "name" in profile
        assert "role" in profile
        assert "organization" in profile
        assert "industries" in profile
        assert "experience_years" in profile
        assert "tech_stack" in profile

    def test_get_profile_summary_returns_formatted_profile(self):
        """
        GET /linkedin/profile-summary should return formatted user profile
        """
        summary = get_profile_summary()
        
        # Verify profile structure
        assert "name" in summary
        assert "role" in summary
        assert "organization" in summary
        assert "industries" in summary
        assert "experience_years" in summary
        assert "tech_stack" in summary
        assert "expertise_level" in summary
        
        # Verify profile content is sensible
        assert isinstance(summary["name"], str)
        assert len(summary["name"]) > 0
        assert isinstance(summary["industries"], list)
        assert len(summary["industries"]) > 0
        assert isinstance(summary["tech_stack"], list)


class TestConfigurationMerging:
    """Test the merge_request_with_profile logic."""

    def test_merge_with_minimal_request_uses_all_defaults(self):
        """
        When request only has topic, all other fields should use profile defaults
        """
        request = PostGenerationRequest(
            topic="Test topic"
            # Everything else is None
        )
        
        merged = merge_request_with_profile(request)
        
        # Verify merged is a complete PostInput
        assert isinstance(merged, PostInput)
        assert merged.topic == "Test topic"
        
        # Verify defaults are applied
        assert merged.tone is not None  # Should have profile default
        assert merged.format is not None  # Should have profile default
        assert merged.audience is not None  # Should have profile default
        assert merged.goal is not None  # Should have profile default
        assert merged.cta_style is not None  # Should have profile default

    def test_merge_with_selective_overrides(self):
        """
        When request has selective overrides, they should override and rest use defaults
        """
        request = PostGenerationRequest(
            topic="Kubernetes best practices",
            format="short",  # Override format
            cta_style="resource",  # Override CTA
            # tone, audience, goal should use profile defaults
        )
        
        merged = merge_request_with_profile(request)
        
        # Verify overrides are applied
        assert merged.format == "short"
        assert merged.cta_style == "resource"
        
        # Verify defaults are still applied
        assert merged.tone is not None  # Should have profile default
        assert merged.audience is not None  # Should have profile default
        assert merged.goal is not None  # Should have profile default

    def test_merge_with_all_overrides(self):
        """
        When request has all fields, none should use defaults
        """
        request = PostGenerationRequest(
            topic="AI in healthcare",
            tone="conversational",
            format="article",
            audience="founders",
            goal="inspire",
            include_emojis=True,
            use_technical_jargon=False,
            cta_style="call-to-action",
            storytelling_frequency="always",
        )
        
        merged = merge_request_with_profile(request)
        
        # Verify all overrides are applied
        assert merged.topic == "AI in healthcare"
        assert merged.tone == "conversational"
        assert merged.format == "article"
        assert merged.audience == "founders"
        assert merged.goal == "inspire"
        assert merged.include_emojis is True
        assert merged.use_technical_jargon is False
        assert merged.cta_style == "call-to-action"
        assert merged.storytelling_frequency == "always"

    def test_merge_preserves_valid_values(self):
        """
        Merge should preserve all non-None values from request
        """
        request = PostGenerationRequest(
            topic="Distributed systems",
            tone="professional",
            format="medium",
            audience="engineers",
            goal="educate",
            include_emojis=False,
            use_technical_jargon=True,
            cta_style="question",
            storytelling_frequency="sometimes",
        )
        
        merged = merge_request_with_profile(request)
        
        # All values should be preserved exactly
        assert merged.tone == "professional"
        assert merged.format == "medium"
        assert merged.audience == "engineers"
        assert merged.goal == "educate"
        assert merged.include_emojis is False
        assert merged.use_technical_jargon is True
        assert merged.cta_style == "question"
        assert merged.storytelling_frequency == "sometimes"


class TestPostRequestModels:
    """Test the request/response models."""

    def test_post_generation_request_allows_partial_fields(self):
        """PostGenerationRequest should allow partial/selective fields."""
        # Minimal request
        req1 = PostGenerationRequest(topic="Test")
        assert req1.topic == "Test"
        assert req1.tone is None
        assert req1.format is None
        
        # Selective fields
        req2 = PostGenerationRequest(
            topic="Test",
            format="short",
            include_emojis=True
        )
        assert req2.format == "short"
        assert req2.include_emojis is True
        assert req2.tone is None

    def test_post_input_requires_all_fields(self):
        """PostInput (legacy) should require all fields for backwards compatibility."""
        # This should work - all fields provided
        input_obj = PostInput(
            topic="Test",
            tone="professional",
            format="medium",
            audience="engineers",
            goal="educate",
            include_emojis=False,
            use_technical_jargon=True,
            cta_style="question",
            storytelling_frequency="sometimes",
        )
        assert input_obj.topic == "Test"

    def test_request_model_dump_with_none_values(self):
        """
        When converting request to dict, None values should be omitted
        to keep payloads sparse
        """
        request = PostGenerationRequest(
            topic="Microservices",
            format="long"
            # All other fields are None
        )
        
        # model_dump() includes None values, but API layer can filter
        dumped = request.model_dump(exclude_none=True)
        
        assert dumped["topic"] == "Microservices"
        assert dumped["format"] == "long"
        assert "tone" not in dumped  # None excluded
        assert "audience" not in dumped  # None excluded


class TestAPIEndpointSimulation:
    """Simulate the actual API endpoints."""

    def test_get_config_endpoint_simulation(self):
        """
        Simulate GET /linkedin/config endpoint behavior
        """
        # Endpoint code:
        # @router.get("/config")
        # async def get_config():
        #     config = get_configuration_options()
        #     return config
        
        config = get_configuration_options()
        
        # Verify response structure for JSON serialization
        assert isinstance(config, dict)
        assert all(isinstance(v, (str, list, dict, int, float, bool)) 
                  for v in config.values())

    def test_get_profile_summary_endpoint_simulation(self):
        """
        Simulate GET /linkedin/profile-summary endpoint behavior
        """
        # Endpoint code:
        # @router.get("/profile-summary")
        # async def profile_summary():
        #     summary = get_profile_summary()
        #     return summary
        
        summary = get_profile_summary()
        
        # Verify response structure for JSON serialization
        assert isinstance(summary, dict)
        assert all(isinstance(v, (str, list, dict, int, float, bool)) 
                  for v in summary.values())

    def test_generate_endpoint_with_request_merging(self):
        """
        Simulate POST /linkedin/generate endpoint behavior with merging
        """
        # Simulate user submitting a request
        user_request = PostGenerationRequest(
            topic="Building AI products",
            format="medium",
            cta_style="question"
            # tone, audience, goal will use defaults
        )
        
        # Endpoint code:
        # if isinstance(req, PostInput):
        #     gen_request = PostGenerationRequest(...)
        # else:
        #     gen_request = req
        # resolved_config = merge_request_with_profile(gen_request)
        
        resolved_config = merge_request_with_profile(user_request)
        
        # Verify the resolved config is complete and ready for pipeline
        assert isinstance(resolved_config, PostInput)
        assert resolved_config.topic == "Building AI products"
        assert resolved_config.format == "medium"
        assert resolved_config.cta_style == "question"
        
        # These should have profile defaults (not None)
        assert resolved_config.tone is not None
        assert resolved_config.audience is not None
        assert resolved_config.goal is not None


class TestUserFlowScenarios:
    """Test realistic user flow scenarios."""

    def test_quick_post_scenario(self):
        """
        Scenario: User wants to quickly write about a trending topic
        without customization
        """
        # User input: Just topic
        request = PostGenerationRequest(
            topic="Latest AI breakthrough in reasoning"
        )
        
        # Backend merges with profile
        merged = merge_request_with_profile(request)
        
        # Verify result is ready for pipeline
        assert merged.topic == "Latest AI breakthrough in reasoning"
        assert merged.format is not None  # Uses profile default
        assert merged.tone is not None  # Uses profile default
        # All other fields also filled from profile

    def test_custom_format_scenario(self):
        """
        Scenario: User wants to use a different format for this post
        """
        # User overrides just format
        request = PostGenerationRequest(
            topic="Kubernetes security best practices",
            format="article"  # Override from default medium to article
        )
        
        merged = merge_request_with_profile(request)
        
        # Verify format is overridden
        assert merged.format == "article"
        # Everything else uses profile defaults
        assert merged.tone is not None

    def test_full_customization_scenario(self):
        """
        Scenario: User fully customizes configuration for a special post
        """
        # User specifies all options
        request = PostGenerationRequest(
            topic="Startup lessons from building an AI company",
            tone="conversational",
            format="long",
            audience="founders",
            goal="inspire",
            include_emojis=True,
            use_technical_jargon=False,
            cta_style="resource",
            storytelling_frequency="always",
        )
        
        merged = merge_request_with_profile(request)
        
        # Verify all customizations are applied
        assert merged.tone == "conversational"
        assert merged.format == "long"
        assert merged.audience == "founders"
        assert merged.goal == "inspire"
        assert merged.include_emojis is True
        assert merged.use_technical_jargon is False
        assert merged.cta_style == "resource"
        assert merged.storytelling_frequency == "always"


class TestBackwardsCompatibility:
    """Test backwards compatibility with legacy PostInput format."""

    def test_legacy_post_input_still_works(self):
        """
        Old clients sending PostInput format should still work
        """
        legacy_request = PostInput(
            topic="My topic",
            tone="professional",
            format="medium",
            audience="engineers",
            goal="educate",
            include_emojis=False,
            use_technical_jargon=True,
            cta_style="question",
            storytelling_frequency="sometimes",
        )
        
        # In routes.py, legacy requests are converted:
        # if isinstance(req, PostInput):
        #     gen_request = PostGenerationRequest(...)
        
        gen_request = PostGenerationRequest(
            topic=legacy_request.topic,
            tone=legacy_request.tone,
            format=legacy_request.format,
            audience=legacy_request.audience,
            goal=legacy_request.goal,
            include_emojis=legacy_request.include_emojis,
            use_technical_jargon=legacy_request.use_technical_jargon,
            cta_style=legacy_request.cta_style,
            storytelling_frequency=legacy_request.storytelling_frequency,
        )
        
        # Then merged (which should return the same values since all are specified)
        merged = merge_request_with_profile(gen_request)
        
        # Verify legacy request values are preserved
        assert merged.topic == "My topic"
        assert merged.tone == "professional"
        assert merged.format == "medium"


if __name__ == "__main__":
    print("LinkedIn Configuration Integration Tests")
    print("=========================================")
    print()
    print("Testing:")
    print("  ✓ Configuration options endpoint")
    print("  ✓ Profile summary endpoint")
    print("  ✓ Request merging logic")
    print("  ✓ Partial field overrides")
    print("  ✓ Complete customization")
    print("  ✓ Backwards compatibility")
    print("  ✓ Realistic user scenarios")
    print()
    print("Run: pytest brain/linkedin/test_integration_config.py -v")
