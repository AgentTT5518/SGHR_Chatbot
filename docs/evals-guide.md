# Evals Guide

When and how to set up quality testing for AI-generated outputs.

---

## What Are Evals?

Evals are structured test cases that measure the quality of AI-generated outputs. They answer one question: **"Is the AI output good enough?"**

| Regular Tests | Evals |
|---------------|-------|
| Deterministic — same input, same output | Non-deterministic — AI may vary each run |
| Binary pass/fail | Scored on a spectrum (1-5 per dimension) |
| Test YOUR code logic | Test the AI's BEHAVIOR given your prompts |
| Every project needs them | Only AI-output projects need them |

Evals catch regressions that unit tests can't — when a prompt change makes outputs slightly worse, or a model upgrade shifts tone.

## When You Need Evals

| Your Project... | Need Evals? | Type |
|-----------------|-------------|------|
| Generates user-facing text (emails, docs, chat) | **Yes** | Content quality evals |
| Has AI-powered features (summaries, analysis, recommendations) | **Yes** | Accuracy + relevance evals |
| Uses prompts that change over time | **Yes** | Regression evals |
| Produces content with brand voice requirements | **Yes** | Tone + style evals |
| Has no AI-generated outputs | **No** | Standard tests are sufficient |

**If you answered "No" to all of the above, skip this guide.** Your project doesn't need evals.

---

## Eval Structure

```
eval-[name]/
  README.md             # What this eval tests
  scoring-rubric.md     # How to grade outputs (1-5 per dimension)
  cases/
    example-case.json   # Individual test cases
    typical-request.json
    edge-case-short.json
    adversarial-ambiguous.json
```

Each eval focuses on one output type. If your AI generates blog posts AND error messages, create two separate evals.

---

## Step-by-Step: Creating Your First Eval

### Step 1: Identify What to Evaluate

Map each AI feature to an eval:

| AI Feature | Eval Name | Key Dimensions |
|-----------|-----------|----------------|
| [e.g., Blog post generator] | [blog-quality] | [Accuracy, Tone, Completeness] |
| [e.g., Chat responses] | [chat-quality] | [Relevance, Tone, Helpfulness] |
| [e.g., Code review comments] | [review-quality] | [Accuracy, Actionability, Tone] |

### Step 2: Copy the Template

```bash
cp -r docs/templates/eval-template eval-[name]
```

Replace `[name]` with a descriptive kebab-case name matching your AI feature.

### Step 3: Define Your Scoring Rubric

Open `eval-[name]/scoring-rubric.md` and customize:

1. **Pick dimensions** — what matters for this output type? (Accuracy, Relevance, Tone, Completeness are good defaults)
2. **Set weights** — not all dimensions matter equally. Weights must sum to 100%
3. **Write level descriptions** — what does a 5 vs 3 vs 1 look like for each dimension?
4. **Set the passing threshold** — minimum weighted average and minimum per-dimension

**Calibration tip:** Score 3-5 real outputs before finalizing the rubric. If you can't distinguish a 3 from a 4, rewrite the descriptions.

### Step 4: Write Test Cases

Open `eval-[name]/cases/example-case.json` as your starting point. Create at least 5 cases:

| Case Type | Count | Purpose |
|-----------|-------|---------|
| Ideal input | 1 | Baseline — should score 5/5 on all dimensions |
| Typical input | 2 | Common real-world usage |
| Edge case | 1 | Boundary conditions (very short, very long, unusual format) |
| Adversarial | 1 | Tricky inputs that expose weaknesses (ambiguous, contradictory) |

Each case file defines:
- `input` — what you send to the AI feature
- `expected_output` — what good output looks like (must_include, must_not_include, tone, format)
- `tags` — for filtering (e.g., run only "regression" cases after a prompt change)

### Step 5: Run and Score

**Manual process (start here):**
1. Feed each case's input to your AI feature
2. Capture the output
3. Score each dimension using the rubric (be honest — 3s are OK)
4. Record in the Score Log table
5. Check against passing threshold

**When to automate:** Once you have 10+ cases and run evals regularly, consider scripting the input→output step. Keep scoring manual for subjective dimensions (tone, style) until you trust automated scoring.

### Step 6: Track Over Time

The Score Log in `scoring-rubric.md` shows trends. Watch for:
- **Score drops after prompt changes** — the change made things worse
- **Consistently low dimensions** — a systemic issue to fix
- **High variance between cases** — the AI is inconsistent, needs more constraints

---

## Connecting Evals to Brand Voice

If your project has brand docs (`docs/brand/`), connect them to your evals:

1. Add a "Tone & Style" dimension to your scoring rubric
2. Define scores by referencing `BRAND-PROFILE.md` — a 5 means "matches brand personality traits"
3. Include `must_not_include` in test cases for banned words from `STYLE-GUIDE.md`
4. Add tone expectations from `TONE-MATRIX.md` to each case's `expected_output.tone` field

See `docs/brand-voice-guide.md` for full details on brand docs.

## Best Practices

- **Minimum 5 cases** before trusting results — fewer is noise
- **Separate evals per output type** — don't combine blog evals with error message evals
- **Include adversarial cases** — tricky inputs expose real weaknesses
- **Re-run after every prompt change** — the whole point is catching regressions
- **Re-run after model upgrades** — different models have different tendencies
- **Calibrate with your team** — have two people score the same output independently, then discuss differences
- **Start manual, automate later** — manual scoring builds intuition about what matters

---

## Reference

- Template: `docs/templates/eval-template/`
- Brand voice guide: `docs/brand-voice-guide.md`
- Decision guide: `docs/project-setup-guide.md`
