# Brand Voice Guide

How to define and enforce consistent writing style across AI-generated outputs.

---

## Why Brand Voice Matters for AI Projects

AI outputs represent your product. When your chatbot sounds different from your docs, or your error messages don't match your marketing tone, users notice — even if they can't articulate why. A defined brand voice makes AI outputs feel like they come from your team, not a generic model.

## When You Need Brand Docs

| Your Project... | Need Brand Docs? |
|-----------------|-----------------|
| Generates user-facing text (chat, emails, docs, UI copy) | **Yes** — full suite |
| Has a chatbot or AI assistant | **Yes** — full suite |
| Generates internal/developer-only content | **Optional** — STYLE-GUIDE.md alone may suffice |
| Has no text output | **No** — skip this guide |

## The Three Brand Documents

| Document | Purpose | Start Here If... |
|----------|---------|-----------------|
| `BRAND-PROFILE.md` | **Who you are** — personality traits, vocabulary, key messages, writing exemplars | You have no brand definition yet |
| `STYLE-GUIDE.md` | **How you write** — formatting rules, grammar, per-content-type rules, banned words | You have a brand but no writing rules |
| `TONE-MATRIX.md` | **How tone shifts** — adjustments by context, audience, and user emotional state | You have rules but tone is inconsistent across contexts |

**Fill them in this order.** Each document builds on the previous one.

---

## Step-by-Step: Setting Up Brand Voice

### Step 1: Define Your Brand Profile

```bash
mkdir -p docs/brand
cp docs/templates/brand/BRAND-PROFILE.md docs/brand/BRAND-PROFILE.md
```

**Fill in this order:**

1. **Identity table** — name, tagline, mission, audience, industry
2. **Voice traits** — pick 3-5 adjectives (these drive everything else)
3. **"We Sound Like" / "We Never Sound Like"** — write actual sentences in your voice and anti-voice
4. **Key Messages** — 3-5 themes that should recur naturally
5. **Vocabulary** — preferred and banned terms with reasons
6. **Writing Exemplars** — paste 3-5 real paragraphs you wrote that represent ideal voice

**The exemplars section is the most impactful.** Claude pattern-matches against real examples far better than abstract adjectives. Aim for 5-10 paragraphs from different content types (blog, email, docs, etc.).

### Step 2: Write Your Style Guide

```bash
cp docs/templates/brand/STYLE-GUIDE.md docs/brand/STYLE-GUIDE.md
```

Translate your personality traits into concrete rules:

| If Your Brand Is... | Style Rules Might Include... |
|--------------------|----------------------------|
| Direct | "Lead with the answer, not the context" |
| Approachable | "Use contractions. Write 'you'll' not 'you will'" |
| Technical but clear | "Define jargon on first use. Use code examples" |
| Encouraging | "Frame errors as fixable. 'Here's how to fix it' not 'You broke it'" |

Then add content-type sections for each type of text your AI generates (blog posts, error messages, docs, emails, etc.).

### Step 3: Build Your Tone Matrix

```bash
cp docs/templates/brand/TONE-MATRIX.md docs/brand/TONE-MATRIX.md
```

Identify the 4-6 most common contexts your AI operates in and define how tone shifts from the baseline:

1. **Context shifts** — onboarding vs error vs docs vs marketing
2. **Audience shifts** — developers vs non-technical vs executives
3. **Emotional state shifts** — frustrated vs confused vs excited vs neutral

The tone matrix includes a priority order: emotional state first, then audience, then context. This prevents conflicting adjustments.

### Step 4: Reference from Prompts

Once brand docs exist, reference them in your AI system prompts or CLAUDE.md:

```markdown
## Writing Rules
- ALWAYS read `docs/brand/BRAND-PROFILE.md` before generating content
- Match tone to context using `docs/brand/TONE-MATRIX.md`
- Validate output against `docs/brand/STYLE-GUIDE.md`
- Compare against exemplars in BRAND-PROFILE.md for voice consistency
```

### Step 5: Create Brand Evals

Connect brand docs to quality testing:

1. Create an eval with a "Tone & Style" dimension (see `docs/evals-guide.md`)
2. Score outputs against brand personality traits from BRAND-PROFILE.md
3. Add banned words from STYLE-GUIDE.md to test case `must_not_include` fields
4. Set tone expectations from TONE-MATRIX.md in each test case

---

## Where Brand Docs Live

```
docs/brand/
  BRAND-PROFILE.md    # Copied from docs/templates/brand/
  STYLE-GUIDE.md      # Copied from docs/templates/brand/
  TONE-MATRIX.md      # Copied from docs/templates/brand/
```

## Best Practices

- **One source of truth** — all prompts reference brand docs, never inline ad-hoc rules
- **Review quarterly** — voice evolves as products mature; update docs to match
- **Test with real outputs** — use evals to verify brand compliance, not gut feeling
- **Start minimal** — a 5-rule style guide beats a 50-rule one nobody reads
- **Exemplars over adjectives** — 5 real paragraphs do more than 20 personality traits
- **Don't over-constrain** — leave room for Claude to be natural within guardrails

---

## Reference

- Templates: `docs/templates/brand/`
- Evals guide: `docs/evals-guide.md`
- Eval template: `docs/templates/eval-template/`
- Decision guide: `docs/project-setup-guide.md`
