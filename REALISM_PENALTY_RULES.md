# Realism Penalty Rules Reference

## Quick Penalty Table

```
┌─────────────────────────────────────────┬──────────┬────────────────────────────────┐
│ Condition                               │ Penalty  │ Improvement Suggestion         │
├─────────────────────────────────────────┼──────────┼────────────────────────────────┤
│ < 2 independent sources                 │ -0.2     │ Add independent sources        │
│ All sources blog-only                   │ -0.1     │ Add non-blog sources           │
│ Any self-benchmark claim                │ -0.2     │ Add third-party validation     │
│ Hyperbolic hook detected                │ -0.1     │ Soften absolutist language     │
│ Funding from Wikipedia-only             │ -0.1     │ Cite primary funding sources   │
└─────────────────────────────────────────┴──────────┴────────────────────────────────┘
```

**Total Max Penalty**: -0.7 (leaves conservative floor of 0.0 for worst case)

---

## Scoring Examples

### Example 1: Strong Claim
```
Claim: "Sarvam AI raised $50M Series B in 2024"
Sources: TechCrunch, Crunchbase, Sarvam AI blog
Independent sources: 2+ (news + official)
Blog-only: FALSE (news source present)
Self-benchmark: FALSE
Wikipedia only: FALSE

Realism Base: 0.7 (LLM scored well)
Penalties Applied: 0.0
Result: 0.7 → 7.0/10 realism dimension
→ Score: ACCEPTABLE, publish-ready
```

### Example 2: Weak Claim (Typical Sarvam AI Pattern)
```
Claim: "Our benchmark shows 95% accuracy"
Sources: Sarvam AI blog, Medium post about Sarvam
Independent sources: 0 (all self)
Blog-only: TRUE
Self-benchmark: TRUE
Wikipedia only: N/A

Realism Base: 0.7 (LLM scored it)
Penalties Applied:
  - < 2 independent sources: -0.2
  - All blog-only: -0.1
  - Self-benchmark: -0.2
  Total: -0.5
Result: 0.7 - 0.5 = 0.2 → 2.0/10 realism dimension
→ Status: FAIL realism gate, trigger retry or reject
```

### Example 3: Mixed Evidence
```
Claim: "Sarvam AI is building foundation models"
Sources: LinkedIn announcement (blog-adjacent), Reuters tech news
Independent sources: 1-2 (one journalistic)
Blog-only: FALSE (news source present)
Self-benchmark: FALSE
Wikipedia only: FALSE

Realism Base: 0.6 (LLM moderate confidence)
Penalties Applied: 0.0 (no penalties triggered)
Result: 0.6 → 6.0/10 realism dimension
→ Status: BORDERLINE, acceptable with caveats
```

---

## Hook Softening Examples

### Example 1: News-Friendly Softening
```
Original: "The generalist AI narrative just died"
Detection: _is_hyperbolic_hook() → TRUE (contains "just died")
Softened: "The generalist AI narrative took a serious hit"
Penalty: -0.1 (flagged as hyperbolic)
```

### Example 2: Strong Claim → Credible Claim
```
Original: "LLMs will destroy traditional ML forever"
Detection: Contains "destroy"
Softened: "LLMs will challenge traditional ML significantly"
Penalty: -0.1 (hyperbolic)
```

### Example 3: Absolutist → Hedged
```
Original: "AI will always outperform humans"
Detection: Contains " always "
Softened: "AI will often outperform humans"
Penalty: -0.1 (hyperbolic)
```

### Example 4: No Softening Needed
```
Original: "Here's why Sarvam AI's research matters"
Detection: _is_hyperbolic_hook() → FALSE (no absolutist markers)
Softened: "Here's why Sarvam AI's research matters" (unchanged)
Penalty: 0.0
```

---

## Implementation Locations

### File: [nodes.py](AI/autonomus-ai-employee/backend/brain/linkedin/nodes.py)

**Lines 324-382**: Helper functions
- `_is_blog_domain()` [L324-335]
- `_is_wikipedia_url()` [L298-322]
- `_is_self_benchmark_claim()` [L337-342]
- `_is_hyperbolic_hook()` [L344-358]
- `_soften_absolutist_hook()` [L360-382]

**Lines 695-720**: Fact verification metadata enrichment
- Counts `independent_sources`
- Flags `blog_only`, `wikipedia_only`, `self_benchmark`
- Stores source URLs

**Lines 1650-1680**: Realism penalty application in viral_scorer
- Reads metadata from verified_claims
- Applies exact -0.2/-0.1 penalties per rule
- Generates improvement_suggestions
- Stores realism_adjusted score

**Lines 817-1030**: Hook generator integration
- Line 1024: `selected_hook = _soften_absolutist_hook(selected_hook)`

---

## Validation Commands

### Check all helper functions are present:
```bash
grep -n "def _is_\|def _soften_" nodes.py
```
Expected output: 5 functions (blog_domain, wikipedia_url, self_benchmark_claim, hyperbolic_hook, soften_absolutist_hook)

### Check penalties are applied:
```bash
grep -n "realism_penalty +=" nodes.py
```
Expected output: 5 penalty lines (0.2 + 0.1 + 0.2 + 0.1 + 0.1 = 0.7 max)

### Check metadata is enriched:
```bash
grep -n "independent_sources\|blog_only\|wikipedia_only\|self_benchmark" nodes.py
```
Expected output: Multiple references in fact_verification and scorer

### Check hook softening is integrated:
```bash
grep -n "_soften_absolutist_hook" nodes.py
```
Expected output: Definition + 1 usage in hook_generator_node

---

## Testing Checklist

- [ ] Realism score for weak evidence < 0.5 (not 1.0)
- [ ] Realism score for strong evidence ≥ 0.6
- [ ] Hook softening visible in final post (no "just died", "destroyed", etc.)
- [ ] Improvement suggestions appear when penalties triggered
- [ ] Research confidence retry loop activates for low confidence
- [ ] Max retries capped at 3 (no infinite loops)
- [ ] Blog detection catches Medium, Dev.to, Substack, blogs
- [ ] Wikipedia detection catches Wikipedia and Wikimedia URLs
- [ ] Self-benchmark detection catches "our benchmark", "we tested", "proprietary study"
- [ ] Expected score distribution: weak evidence 2-4/10, strong evidence 7-9/10

---

## User-Facing Output Examples

### Example 1: Weak Evidence Post (Rejected)
```
Topic: Sarvam AI

Research Confidence: 0.32
Realism Score: 2.1/10
Overall Score: 3.4/10
Status: ❌ NEEDS IMPROVEMENT

Improvement Suggestions:
  • Add at least 2 independent sources for key claims.
  • Add at least one non-blog source (news/research/filing).
  • Treat self-benchmarks as provisional; add third-party validation.
  • For funding claims, cite primary sources instead of Wikipedia.
```

### Example 2: Strong Evidence Post (Approved)
```
Topic: Sarvam AI

Research Confidence: 0.78
Realism Score: 7.2/10
Overall Score: 8.1/10
Status: ✅ PUBLISH-READY

Selected Hook: "Sarvam AI took a serious hit in the open-source race"

Final Post:
Sarvam AI took a serious hit in the open-source race. While their 
foundation models show promise, recent funding rounds were 50% below 
industry expectations (TechCrunch, 2024). The team's focus on efficiency 
over raw performance highlights a strategic pivot toward edge deployment.
```

---

## FAQ

**Q: Why is my realism score 0.2 when I have one good source?**  
A: You have < 2 independent sources (-0.2 penalty). Even one quality source needs validation. Add one more independent source (news, research, or filing).

**Q: My hook is "The AI bubble took a serious hit" but it's still marked as hyperbolic.**  
A: "took a serious hit" is our softened alternative. It's not hyperbolic anymore. If you see the penalty, check for other markers like "always", "never", "destroyed", "obliterated", "game over".

**Q: Why does my self-benchmark penalty me -0.2 so hard?**  
A: Self-benchmarks (your own tests) are unverified until third parties validate them. The penalty is steep because "we tested 95%" doesn't prove credibility—competitors always benchmark well on their own hardware.

**Q: Can I publish even with realism score < 0.5?**  
A: No, not yet. The confidence loop will retry discovery. If retries also fail, you'll see improvement suggestions. Either make those changes or pick a different topic.

**Q: Does hook softening change my message?**  
A: No, it preserves impact while adding credibility. "took a serious hit" vs "just died" conveys the same severity to your audience, but doesn't risk claims of sensationalism.

**Q: What if my sources are all Wikipedia?**  
A: If funding claims are sourced only from Wikipedia, that's -0.1 penalty. Wikipedia is fine for general info, but use primary sources (CapTable, press release, TechCrunch) for major facts.

---

## Summary

The realism system is **deterministic, transparent, and strict**. Every penalty has a clear improvement path. The goal is to shift your thought leadership from "easy virality" to "credible authority."
