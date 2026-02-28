# Agent Harnesses

The agent harness defines which agentic system and underlying model runs the benchmark. Each cell in the benchmark matrix is evaluated by exactly one harness.

Use the most intelligent model available for each harness, with maximum thinking/reasoning enabled where supported.

---

## Claude Code

**Tool**: [Claude Code](https://claude.ai/claude-code) (`claude` CLI)

**Model**: Most intelligent model available; enable extended thinking.

**Invocation**:

```bash
# Run benchmark with Claude Code (most intelligent model, max thinking)
claude --plugin-dir ./plugins/ml-skills

# Non-interactive / scripted run
claude -p "Run check-dataset-quality on data/train.csv --label-col label" \
  --plugin-dir ./plugins/ml-skills
```

**Notes**:
- Skills in this repo are available when `--plugin-dir` points to `plugins/ml-skills`
- Token usage is reported in session output and API response metadata
- Use `--output-format json` to capture structured output for telemetry

---

## Codex (OpenAI)

**Tool**: [OpenAI Codex CLI](https://github.com/openai/codex) (`codex` CLI)

**Model**: Most intelligent model available; use full reasoning mode.

**Invocation**:

```bash
# Run benchmark with Codex (most intelligent model)
codex "Run an end-to-end ML pipeline on data/train.csv targeting the label column"

# Approval policy for automated runs
codex --approval-policy auto "..."
```

**Notes**:
- Skills in this repo are not natively available; the no-plugin mode is the natural fit
- Token usage available via OpenAI API usage metadata
- `--approval-policy auto` enables non-interactive execution

---

## Gemini CLI

**Tool**: [Gemini CLI](https://github.com/google-gemini/gemini-cli) (`gemini` CLI)

**Model**: Most intelligent model available; enable extended thinking where supported.

**Invocation**:

```bash
# Run benchmark with Gemini CLI (most intelligent model)
gemini "Run an end-to-end ML pipeline on data/train.csv targeting the label column"
```

**Notes**:
- Skills in this repo are not natively available; no-plugin mode applies
- Requires `GEMINI_API_KEY` or gcloud ADC
- Token usage available via `--show-usage` flag or API response metadata

---

## Selecting a harness for a benchmark run

Document for each run:

- harness name (`claude-code`, `codex`, `gemini-cli`)
- model ID and version used
- CLI version (`claude --version`, `codex --version`, `gemini --version`)
- thinking/reasoning mode and budget (if configurable)
- any non-default flags

This metadata goes in the run log alongside mode and scenario so results are reproducible.
