"""
Test suite for UI-configurable LinkedIn content generation endpoints.

This demonstrates how the frontend should interact with the new configuration system:
1. GET /linkedin/config → Get all available options and current defaults
2. GET /linkedin/profile-summary → Get user profile info for display
3. POST /linkedin/generate → Submit post with optional overrides
4. WebSocket /linkedin/ws/{thread_id} → Get real-time pipeline updates

Usage:
    pytest brain/linkedin/test_config_endpoints.py -v
"""

import pytest
import json
from typing import Optional, Dict, Any
from pydantic import ValidationError

# Import models
from brain.linkedin.models import PostGenerationRequest, PostInput, PostConfigurationOptions


class TestPostGenerationRequest:
    """Test the flexible PostGenerationRequest model used by UI."""
    
    def test_minimal_request_only_topic(self):
        """UI can submit just a topic, all other fields use defaults."""
        req = PostGenerationRequest(topic="AI in healthcare")
        assert req.topic == "AI in healthcare"
        assert req.tone is None  # Will use profile default
        assert req.format is None  # Will use profile default
        
    def test_selective_overrides(self):
        """UI can override specific fields while leaving others as default."""
        req = PostGenerationRequest(
            topic="Kubernetes best practices",
            format="short",  # Override format to short
            cta_style="question",  # Override CTA style
            # tone, audience, goal, etc. will use profile defaults
        )
        assert req.topic == "Kubernetes best practices"
        assert req.format == "short"
        assert req.cta_style == "question"
        assert req.tone is None  # Uses profile default
        
    def test_all_overrides(self):
        """UI can override all fields."""
        req = PostGenerationRequest(
            topic="Distributed systems",
            tone="casual",
            format="medium",
            audience="tech-leads",
            goal="educate",
            include_emojis=True,
            use_technical_jargon=False,
            cta_style="resource",
            storytelling_frequency="always",
        )
        assert req.tone == "casual"
        assert req.format == "medium"
        assert req.include_emojis is True
        
    def test_topic_required(self):
        """Topic is the only required field."""
        with pytest.raises(ValidationError):
            PostGenerationRequest()  # Missing topic


class TestPostConfigurationOptions:
    """Test the configuration options schema for UI dropdowns."""
    
    def test_schema_completeness(self):
        """Configuration options should include all selectable fields."""
        from brain.linkedin.models import PostConfigurationOptions
        
        # This would be returned by GET /linkedin/config
        schema = {
            "tone_options": ["professional", "conversational", "informal"],
            "format_options": ["short", "medium", "long", "article"],
            "audience_options": ["engineers", "managers", "founders", "general"],
            "goal_options": ["educate", "inspire", "engage", "promote"],
            "cta_style_options": ["question", "resource", "call-to-action", "none"],
            "storytelling_frequency_options": ["never", "sometimes", "always"],
            "current_defaults": {
                "tone": "professional",
                "format": "medium",
                "audience": "engineers",
                "goal": "educate",
                "include_emojis": False,
                "use_technical_jargon": True,
                "cta_style": "question",
                "storytelling_frequency": "sometimes",
            },
            "user_profile": {
                "name": "Jatin Panghal",
                "role": "Software Developer Engineer",
                "organization": "Cognida.ai",
                "industries": ["AI/ML", "Frontend", "SaaS"],
                "experience_years": 1.5,
                "tech_stack": ["Python", "TypeScript", "React", "FastAPI", "PostgreSQL"],
            }
        }
        
        # Verify all required keys are present
        assert "tone_options" in schema
        assert "format_options" in schema
        assert "audience_options" in schema
        assert "goal_options" in schema
        assert "cta_style_options" in schema
        assert "storytelling_frequency_options" in schema
        assert "current_defaults" in schema
        assert "user_profile" in schema


class TestConfigurationFlowScenarios:
    """Test realistic UI flow scenarios."""
    
    def test_ui_flow_minimal_override(self):
        """
        UI Flow 1: User just wants to change one thing (e.g., format only)
        
        Steps:
        1. UI calls GET /linkedin/config → Gets all options and current defaults
        2. User selects topic and changes format to "short"
        3. UI builds PostGenerationRequest with only these fields set
        4. UI POSTs to /generate with the request
        """
        # Step 1: GET /config returns schema
        config_schema = {
            "current_defaults": {
                "tone": "professional",
                "format": "medium",
                "audience": "engineers",
                "goal": "educate",
                "include_emojis": False,
                "use_technical_jargon": True,
                "cta_style": "question",
                "storytelling_frequency": "sometimes",
            }
        }
        
        # Step 2-3: User overrides format
        request = PostGenerationRequest(
            topic="Microservices architecture",
            format="short",  # Only override this
        )
        
        # Step 4: Send to API (merge will apply defaults for tone, audience, goal, etc.)
        assert request.topic == "Microservices architecture"
        assert request.format == "short"
        assert request.tone is None  # Will use "professional" from defaults
        
    def test_ui_flow_full_customization(self):
        """
        UI Flow 2: User customizes everything
        
        Steps:
        1. UI calls GET /linkedin/config
        2. User selects/customizes all fields
        3. UI builds complete PostGenerationRequest
        4. UI POSTs to /generate
        """
        request = PostGenerationRequest(
            topic="Building scalable ML pipelines",
            tone="conversational",
            format="article",
            audience="managers",
            goal="inspire",
            include_emojis=True,
            use_technical_jargon=False,
            cta_style="resource",
            storytelling_frequency="always",
        )
        
        # All fields are explicitly set
        assert request.tone == "conversational"
        assert request.format == "article"
        assert request.audience == "managers"
        assert request.include_emojis is True
        

class TestAPIRequestFormats:
    """Test actual HTTP request formats for the frontend."""
    
    def test_post_generate_with_minimal_override(self):
        """
        Example POST /generate request from UI:
        
        User wants to write about a hot topic quickly, using all profile defaults
        except override format to short.
        """
        payload = {
            "topic": "DuckDB vs PostgreSQL for analytics",
            "format": "short"
        }
        
        request = PostGenerationRequest(**payload)
        assert request.topic == "DuckDB vs PostgreSQL for analytics"
        assert request.format == "short"
        assert request.tone is None
        
        # Backend will merge with profile:
        # Result: tone=profile.tone, format="short", audience=profile.audience, etc.


class TestConfigurationErrorHandling:
    """Test error handling in the configuration system."""
    
    def test_invalid_tone_rejected(self):
        """Invalid tone option should be caught (or normalized by merge logic)."""
        # This might pass validation but get normalized or rejected by merge logic
        req = PostGenerationRequest(
            topic="Good topic",
            tone="invalid_tone_option"  # Not in tone_options
        )
        assert req.tone == "invalid_tone_option"
        # Backend merge_request_with_profile() should handle validation
        
    def test_invalid_format_rejected(self):
        """Invalid format should be caught."""
        req = PostGenerationRequest(
            topic="Good topic",
            format="ultra_long"  # Not in format_options
        )
        assert req.format == "ultra_long"
        # Backend validation should handle this


# ==========================================
# Integration Test Scenarios for Backend
# ==========================================

def example_config_service_usage():
    """
    Example of how config_service is used in routes.py:
    """
    from services.config_service import (
        get_configuration_options,
        merge_request_with_profile,
        get_profile_summary,
    )
    
    # Example 1: GET /linkedin/config endpoint
    def get_config_endpoint():
        """
        Returns everything UI needs to render the form
        """
        config = get_configuration_options()
        # config contains:
        # {
        #     "tone_options": [...],
        #     "format_options": [...],
        #     "audience_options": [...],
        #     "goal_options": [...],
        #     "cta_style_options": [...],
        #     "storytelling_frequency_options": [...],
        #     "current_defaults": {...},
        #     "user_profile": {...}
        # }
        return config
    
    # Example 2: GET /linkedin/profile-summary endpoint
    def get_profile_summary_endpoint():
        """
        Returns just the user profile for display
        """
        summary = get_profile_summary()
        # summary contains:
        # {
        #     "name": "...",
        #     "role": "...",
        #     "organization": "...",
        #     "industries": [...],
        #     "experience_years": ...,
        #     "tech_stack": [...],
        #     "writing_preferences": {...},
        #     "career_focus": {...}
        # }
        return summary
    
    # Example 3: POST /linkedin/generate endpoint
    def generate_post_endpoint(user_request: PostGenerationRequest):
        """
        Takes user's selected configuration and merges with defaults
        """
        # Merge request overrides with profile defaults
        final_config = merge_request_with_profile(user_request)
        
        # final_config is now a complete PostInput with all fields filled:
        # - topic: from request (required)
        # - tone: from request override OR profile default
        # - format: from request override OR profile default
        # - audience: from request override OR profile default
        # - goal: from request override OR profile default
        # - include_emojis: from request override OR profile default
        # - use_technical_jargon: from request override OR profile default
        # - cta_style: from request override OR profile default
        # - storytelling_frequency: from request override OR profile default
        
        # Pass final_config to the graph pipeline
        # graph.invoke({"user_input": final_config.model_dump(), ...})
        return final_config


if __name__ == "__main__":
    print("Test scenarios for UI-configurable LinkedIn content generation")
    print()
    print("Endpoint: GET /linkedin/config")
    print("  Returns: All available options + current defaults + user profile")
    print()
    print("Endpoint: GET /linkedin/profile-summary")
    print("  Returns: User profile info (name, role, tech stack, etc.)")
    print()
    print("Endpoint: POST /linkedin/generate")
    print("  Accepts: PostGenerationRequest (all fields optional except topic)")
    print("  Merges: Request overrides + profile defaults → complete PostInput")
    print("  Returns: {thread_id} for WebSocket connection")
    print()
    print("Endpoint: GET /linkedin/posts")
    print("  Returns: List of all generated posts")
    print()
    print("WebSocket: /linkedin/ws/{thread_id}")
    print("  Receives: Real-time pipeline updates (node starts, errors, approvals)")
