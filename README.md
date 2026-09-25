# ✍️ RoleRefine

**Rewrite job descriptions to reach a wider talent pool, in your company's own voice.**

RoleRefine flags gender-coded, age-coded and exclusionary language in a job posting, trims inflated requirements and rewrites it to match your company's culture. It explains every change it makes.

It's model-agnostic: the live demo runs on **Google Gemini's free tier**, and the same prompt runs on **Anthropic Claude** by changing one setting.

**[Live demo →](https://kyle-jd-optimizer.streamlit.app)** · No API key needed; click **See a demo result**.

---

## Why this matters

Wording shapes who applies. Research by [Gaucher, Friesen & Kay (2011)](https://doi.org/10.1037/a0022530) found that job ads with more masculine-coded words (such as *competitive*, *dominant* and *aggressive*) were rated as less appealing by women, and that this was driven by a lower sense of belonging, not by doubts about their ability. Age signals ("digital native"), unnecessary physical requirements and long must-have lists narrow the pool even further.

Most small and mid-size companies don't have anyone reviewing postings for this. RoleRefine does a first pass in seconds.

## What it does

| Input | Output |
|---|---|
| A job description | An inclusive rewrite |
| Culture profile: Startup, Enterprise, Mission-driven, Technical or a custom voice | A change log: every edit with its category and reason |
| Role level and company name (optional) | A before/after **scorecard** |
| | Suggestions it can't make itself (e.g. "add a salary range") |

**It checks for:** masculine- and feminine-coded language · age signals · physical requirements that aren't essential · inflated requirements · exclusionary idioms ("culture fit", "work hard, play hard") · missing inclusion signals (pay, benefits, equal-opportunity statement)

## How it works

```
                ┌──────────────────────────┐
 JD + culture → │  Prompt (prompts.py)     │ → Gemini or Claude → JSON: rewrite, changes, suggestions
                └──────────────────────────┘                     │
                                                                 ▼
 Original JD ─────────→ scoring.py (word lists, counts) ──→ Before/after scorecard
```

The project uses a **hybrid design**:

- **The LLM does the judgment calls:** rewriting in context, matching the tone and explaining each change.
- **Plain code does the measuring:** coded-word counts, required-qualification count and reading level. LLMs are unreliable at counting, so the scorecard is computed deterministically and can be reproduced.
- **Plain code also checks the facts:** the fact check below catches rewrites that quietly drop real parts of the job.

### Guardrail: automatic fact check

An inclusive rewrite is worse than useless if it hides real parts of the job. [`factcheck.py`](factcheck.py) compares the original and the rewrite, with no AI involved, and warns when any of these go missing:

- **Working conditions:** long hours, weekends, shifts, travel, relocation, commuting or on-site days, driving
- **Pay and employment type:** hourly, commission, unpaid, contract, part-time
- **Equipment** the candidate must supply
- **Numbers:** years of experience, pay ranges, percentages, days off. Allowed if the change is logged.
- **The reporting line**
- **Length:** changes of more than 25%

Testing showed why this matters: on a community organizer posting, prompt v1 removed "long hours and weekends", relocation, the daily commute and the hourly pay type. The fact check flags all of them, and prompt v2 was written to prevent it.

### Prompt engineering highlights

- **Role, rules and categories:** each bias category has examples and a specific fix.
- **Nuance over blanket bans:** "analytical" in a data role or "lead" in a leadership role is fine. The prompt aims for balance, not zero coded words, and doesn't strip feminine-coded words by default.
- **Hard guardrails:** never change facts (title, pay, location, duties); never invent benefits or salary; keep the length within ±20%; don't change text that's already good.
- **Structured output:** strict JSON schema, validated in code, with an automatic retry if parsing fails. Gemini's JSON mode is switched on as well.
- **One prompt, two providers:** the same system prompt and schema run on Gemini and Claude (`llm.py`), so results can be compared across models.
- **Few-shot example:** one full before/after pair anchors format and quality.
- **Prompt-injection defense:** the job description is wrapped in `<job_description>` tags, and the model is told to ignore instructions inside it.
- **Working conditions are protected:** hours, travel, relocation, on-site terms, pay type and required equipment can be reworded but never removed. Added in v2 after testing.
- **Every removal is logged,** and stated years of experience are never changed; inflated ones are flagged as suggestions instead.
- **Versioned and tested:** see [`prompt_versions/`](prompt_versions/). v2 fixes failures found by running v1 on real postings.

## Results

> _Fill this in after testing (see "Evaluate it" below)._
>
> To evaluate: run real postings through the app, download each **full report (.json)** from the Export tab into `evaluation/reports/`, then run `python evaluation/run_eval.py evaluation/reports/*.json`. The script re-scores every posting with the current code and prints a results table. Reports contain third-party postings, so they're git-ignored; publish the summary only.
>
> Across **N** real job postings: masculine-coded words dropped from **X** to **Y** on average, other flagged phrases from **X** to **Y**, and required qualifications from **X** to **Y**. No facts were changed in **N/N** rewrites.

## Run it locally

```bash
git clone https://github.com/kmbrad1024-prog/jd-optimizer.git
cd jd-optimizer
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # add your API key
streamlit run app.py
```

Get a free Gemini key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey), or an Anthropic key at [platform.claude.com](https://platform.claude.com) and set `PROVIDER = "anthropic"`. Without a key, the app runs in demo mode or lets each user paste their own.

Run the tests:

```bash
pip install -r requirements-dev.txt
pytest
```

## Deploy (free) on Streamlit Community Cloud

1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) → **Create app** → pick the repo, with `app.py` as the main file.
3. In **Advanced settings → Secrets**, paste `GEMINI_API_KEY = "..."`. New Google keys start with `AQ.`, older ones with `AIza`. To use Claude instead, paste `ANTHROPIC_API_KEY = "..."` and add `PROVIDER = "anthropic"`.
4. Deploy, then put the URL at the top of this README.

**Cost control:** each visitor gets 10 runs per session on your key (`MAX_RUNS_PER_SESSION` in `app.py`); after that they can paste their own key. On Gemini's free tier, Google's daily quota is the hard limit, and the app shows a friendly message when it's reached. On Claude, set a monthly spend limit in the Claude Console.

## Project structure

```
app.py              Streamlit UI
prompts.py          System prompt, culture profiles, user-message builder
llm.py              Gemini and Claude API calls, JSON validation, retry, friendly errors
scoring.py          Gender-coded word lists, flags, requirement count, reading level
factcheck.py        Flags facts the rewrite may have dropped (conditions, pay, numbers)
samples.py          Sample job descriptions and the demo-mode result
prompt_versions/    Prompt history and what each version fixed
evaluation/         Script that summarizes results across many postings
tests/              Unit tests (no API key needed)
```

## Limitations

- This is a writing assistant, not a legal or compliance review. A person should always review the final posting.
- Word-list scoring is a rough signal: it counts stems without understanding context (e.g. "responsible" matches the feminine-coded stem *respon*).
- The research behind the word lists is on English-language job ads, mostly in North America.
- The demo-mode result is pre-written to show the interface; live results come from the model.
- On Gemini's free tier, Google may use inputs to improve its products, so the app asks visitors not to paste confidential postings.

## Credits

- Gaucher, D., Friesen, J., & Kay, A. C. (2011). *Evidence that gendered wording in job advertisements exists and sustains gender inequality.* Journal of Personality and Social Psychology, 101(1), 109–128.
- Word-stem lists adapted from Kat Matfield's open-source [Gender Decoder](https://github.com/lovedaybrooke/gender-decoder).
- Built with [Streamlit](https://streamlit.io), [Google Gemini](https://ai.google.dev) and [Anthropic Claude](https://www.anthropic.com/claude).

Built by **Kyle Bradley** · [LinkedIn](https://www.linkedin.com/in/YOUR-PROFILE)
