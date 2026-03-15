# Eval: [Eval Name]
<!-- Replace [Eval Name] with the name of what you're evaluating -->
<!-- e.g., "Blog Post Quality", "API Response Accuracy", "Chatbot Tone" -->
<!-- DELETE these comments once you've customized the eval -->

## What This Eval Tests

[1-2 sentences: what AI output quality dimension this measures]

## Structure

```
eval-[name]/
  README.md             # This file — eval overview
  scoring-rubric.md     # How to grade outputs (1-5 scale per dimension)
  cases/
    example-case.json   # Sample test case (copy to create more)
```

## How to Run

1. Feed the `input` from a case file to your AI feature
2. Capture the AI output
3. Score the output against each dimension in `scoring-rubric.md`
4. Record scores in the rubric's Score Log table
5. Check against the passing threshold

## Adding New Cases

1. Copy `cases/example-case.json`
2. Rename to describe the scenario (e.g., `edge-case-short-input.json`)
3. Replace the `input`, `expected_output`, and `notes` fields
4. Add relevant `tags` for filtering

**Start with at least 5 cases:**

| Case Type | Purpose | Example |
|-----------|---------|---------|
| Ideal input | Baseline — should score 5/5 | Well-formed, typical request |
| Edge case | Tests boundaries | Very short input, very long input |
| Adversarial | Tests robustness | Ambiguous, contradictory, or tricky input |
| Typical (x2) | Covers common usage | Real-world inputs from your users |

## When to Run

- [ ] Before merging AI feature changes
- [ ] After prompt modifications
- [ ] After model upgrades
- [ ] After brand/style guide changes
- [ ] [Add project-specific triggers]
