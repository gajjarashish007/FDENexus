# M09 AI Engineering & Multi-Agent Platform

Build custom agents and teams on the model provider you choose: Anthropic Claude, OpenAI ChatGPT, AWS Bedrock,
or any OpenAI-compatible server (Azure OpenAI, Ollama, LM Studio, Groq, OpenRouter, vLLM, Together, Mistral).

Owner: AI Platform · UI: `ai-platform.html` (sidebar → AI → AI platform)

## Capabilities

| Capability | Status | Notes |
|---|---|---|
| Agent orchestration | live | Teams: a lead delegates to member agents (one level, budgeted). |
| Model gateway | live | Four adapters (Anthropic, OpenAI, OpenAI-compatible, Bedrock). Adapters are tested against stub servers. Run Test on each provider to check your real key. |
| Model selection | live | Each agent chooses its provider and model. |
| Prompt versioning | planned | System prompts are edited in place. |
| Retrieval-augmented generation | planned | Not built yet. |
| Knowledge base | planned | Not built yet. |
| Vector database | planned | Not built yet. |
| Agent memory boundaries | planned | Each run starts with no memory of earlier runs. |
| Tool registry | live | Read-only built-in tools (see below). |
| Tool authorization | live | Agent allow-list AND the caller's role must both allow the tool. |
| Human approval | planned | No write tools exist yet. Write tools will go through M03 approval. |
| Agent evaluation | planned | Not built yet. |
| Hallucination controls | planned | Answers are not checked against sources. |
| Prompt injection protection | partial | Tool output is wrapped as data and the system prompt forbids following it. Reduces risk, does not remove it. |
| Data leakage prevention | partial | Obvious secrets are redacted from tool output. Prompts still reach the chosen provider. |
| Execution tracing | live | Every model call, tool call, delegation, token count and duration is stored. |
| Cost monitoring | partial | Tokens are always counted. Cost shows only when you enter the provider's price per million tokens. |

## Built-in tools (read-only)

| Tool | Minimum role | What it does |
|---|---|---|
| `current_time` | viewer | UTC time. |
| `list_modules` | viewer | Module names, maturity and capability counts. |
| `cache_search` | viewer | Searches the synced AWS account data cache by service, name, id or tag text. Returns summaries only. |

Add a tool by editing `build_tools()` in `backend/m09_agents.py`. Keep tools read-only unless they go through an approval flow.

## Providers

Keys are never sent to the browser and never written to logs.

- **Anthropic Claude**: base URL defaults to `https://api.anthropic.com`. Key from env var `ANTHROPIC_API_KEY`, or pasted and stored encrypted.
- **OpenAI ChatGPT**: base URL defaults to `https://api.openai.com/v1`. Key from `OPENAI_API_KEY`, or pasted and stored encrypted.
- **OpenAI-compatible**: any server with `/chat/completions`. Base URL is required. Use `https://` for hosted servers. Plain `http://` is accepted for `localhost` and `127.0.0.1` only (for example Ollama at `http://localhost:11434/v1`).
- **AWS Bedrock**: uses a connected AWS account's credentials (the account picker on the Providers form) and a region. Enable model access in the Bedrock console for the model you use.

Stored keys are encrypted with a key derived from `JWT_SECRET`. If `JWT_SECRET` changes, stored keys become unreadable and must be pasted again. Prefer env vars in production.

## Safety model

- Roles: viewers can see agents and runs and cannot build or run. Developers and above can create and run agents and teams. Only admins manage providers.
- Owners and admins can edit or delete an agent or team.
- A run uses the caller's identity and role. An agent cannot do more than its caller.
- Limits per run: step count (up to 10 per agent), token budget (default 60,000, max 300,000), 3 delegations, and a 4-minute wall-clock limit.
- Team members cannot delegate further.

## API

`/api/m09/`: `overview`, `kinds`, `tools`, `providers` (+ `/<id>`, `/<id>/test`), `agents` (+ `/<id>`, `/<id>/run`), `teams` (+ `/<id>`, `/<id>/run`), `runs` (+ `/<id>`).

## Known limits

- Runs are synchronous HTTP requests. Long runs hold the request open until they finish or hit the time limit.
- No streaming output yet.
- No write tools, so agents cannot act on infrastructure.
