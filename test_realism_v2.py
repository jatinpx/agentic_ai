#!/usr/bin/env python3
"""
Standalone test script for Sarvam AI topic with v2 realism penalties and hook softening.
Simulates the /linkedin/generate call to validate new quality improvements.
"""

import sys
import os
import json
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent / "AI/autonomus-ai-employee/backend"
sys.path.insert(0, str(backend_path))

# Set environment for testing
os.environ.setdefault("LOG_LEVEL", "INFO")

def main():
    """Run test of realism penalties and hook softening on Sarvam AI topic."""
    
    print("=" * 80)
    print("LINKEDIN CONTENT AGENT V2 - REALISM PENALTIES & HOOK SOFTENING TEST")
    print("=" * 80)
    print()
    
    try:
        # Import after sys.path is set
        from brain.linkedin.state import LinkedInState
        from brain.linkedin.graph import create_linkedin_graph
        
        print("✓ Imported core modules successfully")
        print()
        
        # Create initial state
        initial_state = LinkedInState(
            original_topic="Sarvam AI",
            company_name="Sarvam AI",
            research_focus="AI startup funding, product updates, team growth",
            generated_posts=[],
            viral_posts_data=[],
            trend_candidates=[],
            extracted_claims=[],
            verified_claims=[],
            angle_package=None,
            hook_package=None,
            final_post=None,
            score_metadata=None,
            research_confidence=0.0,
            research_retry_count=0,
            realism_score=0.0,
        )
        
        print(f"✓ Created initial state for topic: {initial_state.original_topic}")
        print()
        
        # Create graph
        graph = create_linkedin_graph()
        print("✓ Created LangGraph pipeline")
        print()
        
        # Run graph
        print("Running graph pipeline...")
        print("-" * 80)
        
        try:
            result = graph.invoke(input=initial_state)
            
            print("-" * 80)
            print()
            print("PIPELINE EXECUTION COMPLETE")
            print("=" * 80)
            print()
            
            # Extract key outputs
            if isinstance(result, dict):
                final_state = result
            else:
                final_state = result if hasattr(result, '__dict__') else {}
            
            # Convert to dict if LinkedInState object
            if hasattr(final_state, '__dict__'):
                final_state_dict = final_state.__dict__
            else:
                final_state_dict = final_state
            
            # Print results
            print("FINAL STATE SUMMARY:")
            print("-" * 80)
            print(f"Topic: {final_state_dict.get('original_topic', 'N/A')}")
            print(f"Research Confidence: {final_state_dict.get('research_confidence', 'N/A')}")
            print(f"Research Retry Count: {final_state_dict.get('research_retry_count', 'N/A')}")
            print(f"Realism Score: {final_state_dict.get('realism_score', 'N/A')}")
            print()
            
            # Trend candidates
            trends = final_state_dict.get('trend_candidates', [])
            print(f"Trends Discovered: {len(trends)}")
            if trends:
                for i, trend in enumerate(trends[:3], 1):
                    print(f"  {i}. {trend.get('title', 'N/A')[:60]}...")
            print()
            
            # Extracted claims
            claims = final_state_dict.get('extracted_claims', [])
            print(f"Claims Extracted: {len(claims)}")
            if claims:
                for i, claim in enumerate(claims[:3], 1):
                    print(f"  {i}. {claim.get('claim_text', 'N/A')[:60]}...")
                    print(f"     Type: {claim.get('type', 'N/A')}")
            print()
            
            # Verified claims
            verified = final_state_dict.get('verified_claims', [])
            print(f"Claims Verified: {len(verified)}")
            if verified:
                for i, claim in enumerate(verified[:3], 1):
                    print(f"  {i}. {claim.get('claim_text', 'N/A')[:60]}...")
                    print(f"     Truth Score: {claim.get('truth_score', 'N/A')}")
                    print(f"     Independent Sources: {claim.get('independent_sources', 0)}")
                    print(f"     Blog Only: {claim.get('blog_only', False)}")
                    print(f"     Self Benchmark: {claim.get('self_benchmark', False)}")
                    print(f"     Wikipedia Only: {claim.get('wikipedia_only', False)}")
            print()
            
            # Angle package
            angle = final_state_dict.get('angle_package', {})
            if angle:
                print(f"Angle: {angle.get('angle_text', 'N/A')[:80]}...")
                print()
            
            # Hook package
            hooks = final_state_dict.get('hook_package', {})
            if hooks:
                selected_hook = hooks.get('selected_hook', '')
                print(f"Selected Hook: {selected_hook}")
                print()
            
            # Score metadata
            score = final_state_dict.get('score_metadata', {})
            if score:
                print(f"Score Breakdown:")
                print(f"  Overall Score: {score.get('final_score', 'N/A')}/10")
                print(f"  Realism Dimension: {score.get('realism_score_dimension', 'N/A')}")
                print(f"  Viral Potential: {score.get('viral_dimension', 'N/A')}")
                print(f"  Credibility: {score.get('credibility_dimension', 'N/A')}")
                print()
                
                # Check for improvement suggestions (from realism penalties)
                if score.get('improvement_suggestions'):
                    print(f"Improvement Suggestions (Realism-based):")
                    for sugg in score['improvement_suggestions'][:3]:
                        print(f"  - {sugg}")
                print()
            
            # Final post
            post = final_state_dict.get('final_post', '')
            if post:
                print(f"Final Post Prepared:")
                print(f"  {post[:200]}...")
                print()
            
            print("=" * 80)
            print("TEST SUMMARY")
            print("=" * 80)
            print()
            
            # Validation checks
            checks = []
            
            # Check 1: Realism score < 0.6 if weak evidence
            realism = final_state_dict.get('realism_score', 0.0)
            if realism < 0.7:
                checks.append(f"✓ Realism score is conservative ({realism}), indicating penalty application")
            else:
                checks.append(f"⚠ Realism score is high ({realism}), penalties may not have applied")
            
            # Check 2: Verified claims have metadata
            if verified and 'independent_sources' in verified[0]:
                checks.append(f"✓ Fact verification enriched with source metadata")
            else:
                checks.append(f"⚠ Fact verification missing source metadata")
            
            # Check 3: Hook softening
            if hooks and selected_hook:
                soft_words = ['took a serious hit', 'losing ground', 'challenged', 'turning point']
                has_soft = any(w in selected_hook.lower() for w in soft_words)
                has_hard = any(w in selected_hook.lower() for w in ['just died', 'is dead', 'obliterated', 'destroyed'])
                
                if has_soft or not has_hard:
                    checks.append(f"✓ Hook softening applied (no absolutist language detected)")
                else:
                    checks.append(f"⚠ Hook may contain absolutist language")
            
            # Check 4: Research confidence and retries
            confidence = final_state_dict.get('research_confidence', 0.0)
            retries = final_state_dict.get('research_retry_count', 0)
            if confidence >= 0.6:
                checks.append(f"✓ Research confidence >= 0.6, no retry needed (retries: {retries})")
            else:
                checks.append(f"⚠ Research confidence < 0.6 (confidence: {confidence}, retries: {retries})")
            
            for check in checks:
                print(check)
            
            print()
            print("=" * 80)
            
        except Exception as e:
            print(f"❌ Error during pipeline execution:")
            print(f"  {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            return 1
    
    except ImportError as e:
        print(f"❌ Failed to import backend modules:")
        print(f"  {str(e)}")
        print()
        print("Ensure backend requirements are installed:")
        print(f"  cd {backend_path}")
        print(f"  pip install -r requirements.txt")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
