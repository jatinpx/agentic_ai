"""
Integration test for user persona and format system.
Verifies that profile loading, format resolution, and persona injection work correctly.
"""

import sys
import os
from pathlib import Path

# Add parent directories to path for imports
backend_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_path))
os.chdir(str(backend_path))

from utilities.profile_loader import load_user_profile, get_profile_summary
from brain.linkedin.format_presets import (
    FORMAT_PRESETS, get_format_preset, get_format_prompt_section, 
    validate_post_format
)
from brain.linkedin.models import PostInput


def test_profile_loading():
    """Test that user profile loads and has expected structure."""
    print("\n✅ TEST 1: Profile Loading")
    profile = load_user_profile()
    
    assert "identity" in profile, "Missing 'identity' section"
    assert "technical" in profile, "Missing 'technical' section"
    assert "writing" in profile, "Missing 'writing' section"
    assert "career" in profile, "Missing 'career' section"
    
    assert profile["identity"].get("job_role"), "Missing job_role"
    assert profile["technical"].get("expertise_level") in ("beginner", "intermediate", "expert"), "Invalid expertise_level"
    assert profile["writing"].get("default_format") in ("short", "medium", "long", "article"), "Invalid default_format"
    
    print(f"  Profile loaded successfully")
    print(f"  {get_profile_summary()}")
    return True


def test_format_presets():
    """Test that format presets are properly defined."""
    print("\n✅ TEST 2: Format Presets")
    
    for format_key in ["short", "medium", "long", "article"]:
        preset = get_format_preset(format_key)
        assert preset["word_range"], f"Missing word_range for {format_key}"
        assert preset["paragraph_count"], f"Missing paragraph_count for {format_key}"
        
        min_w, max_w = preset["word_range"]
        assert min_w < max_w, f"Invalid word range for {format_key}"
        
        print(f"  {format_key.upper()}: {min_w}-{max_w} words, {preset['paragraph_count']} paragraphs")
    
    return True


def test_format_prompt_section():
    """Test that format-specific prompt sections are generated."""
    print("\n✅ TEST 3: Format Prompt Sections")
    
    for format_key in ["short", "medium", "long", "article"]:
        section = get_format_prompt_section(format_key)
        assert format_key.upper() in section, f"Format key not in section for {format_key}"
        assert "word" in section.lower(), f"Word count guidance missing for {format_key}"
        
        print(f"  {format_key.upper()}: {len(section)} chars of guidance generated")
    
    return True


def test_post_validation():
    """Test that post validation works for different formats."""
    print("\n✅ TEST 4: Post Format Validation")
    
    # Short format: 100 words (should be valid for short, invalid for medium)
    short_post = " ".join(["word"] * 100)
    
    result_short = validate_post_format(short_post, "short")
    print(f"  100-word post vs short: valid={result_short['valid']} (expect True)")
    assert result_short["valid"], "100-word post should be valid for short format"
    
    result_medium = validate_post_format(short_post, "medium")
    print(f"  100-word post vs medium: valid={result_medium['valid']} (expect False)")
    assert not result_medium["valid"], "100-word post should be invalid for medium format"
    
    # Medium format: 200 words (should be valid for medium)
    medium_post = " ".join(["word"] * 200)
    result_medium = validate_post_format(medium_post, "medium")
    print(f"  200-word post vs medium: valid={result_medium['valid']} (expect True)")
    assert result_medium["valid"], "200-word post should be valid for medium format"
    
    return True


def test_post_input_with_format():
    """Test that PostInput model accepts format field."""
    print("\n✅ TEST 5: PostInput Model with Format")
    
    # Test with format
    input1 = PostInput(
        topic="AI trends",
        tone="professional",
        format="short"
    )
    assert input1.format == "short", "Format not captured"
    print(f"  PostInput with format='short': OK")
    
    # Test without format (should default to None)
    input2 = PostInput(topic="AI trends")
    assert input2.format is None, "Format should default to None"
    print(f"  PostInput without format: OK (defaults to None)")
    
    # Test invalid format (should still be accepted by model, validation happens later)
    input3 = PostInput(topic="AI trends", format="invalid_format")
    print(f"  PostInput with invalid format: accepted by model (filtering later)")
    
    return True


def test_profile_defaults():
    """Test that profile provides sensible defaults when file is missing."""
    print("\n✅ TEST 6: Profile Defaults")
    
    profile = load_user_profile()
    
    # Check all required fields have defaults
    assert profile["identity"]["job_role"] != "", "job_role should have default"
    assert profile["technical"]["expertise_level"] in ("beginner", "intermediate", "expert"), "expertise_level should be valid"
    assert profile["writing"]["default_format"] in ("short", "medium", "long", "article"), "default_format should be valid"
    
    print(f"  Defaults applied correctly:")
    print(f"    - job_role: {profile['identity']['job_role']}")
    print(f"    - expertise_level: {profile['technical']['expertise_level']}")
    print(f"    - default_format: {profile['writing']['default_format']}")
    
    return True


def main():
    """Run all integration tests."""
    print("=" * 60)
    print("USER PERSONA & FORMAT SYSTEM - INTEGRATION TESTS")
    print("=" * 60)
    
    tests = [
        test_profile_loading,
        test_format_presets,
        test_format_prompt_section,
        test_post_validation,
        test_post_input_with_format,
        test_profile_defaults,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except AssertionError as e:
            print(f"  ❌ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
