# Reheat

Python CLI for SEO analysis. Pulls search queries from Google Search Console,
enriches them with related searches and People Also Ask data, clusters by
semantic intent, and surfaces content gaps and opportunities.

Built by [Edward Grundy](https://bayis.co.uk) at [Bay Information Systems](https://bayis.co.uk).

- Install: `pip install reheat`
- Docs: [bayinfosys.github.io/reheat](https://bayinfosys.github.io/reheat)
- PyPI: [pypi.org/project/reheat](https://pypi.org/project/reheat)

---

## Getting started

### Install

```bash
pip install reheat
```

Requires Python 3.10+. For the local web interface you also need a running
postgres instance (or use the JSON file backend for local development
without postgres).

```bash
docker run -d \
  --name reheat-pg \
  -e POSTGRES_USER=reheat \
  -e POSTGRES_PASSWORD=reheat \
  -e POSTGRES_DB=reheat \
  -p 5432:5432 \
  postgres:16

export DATABASE_URL=postgresql://reheat:reheat@localhost:5432/reheat
```

### Configure a Google Search Console source

Download OAuth2 credentials from Google Cloud Console (APIs and Services >
Credentials > OAuth 2.0 Client IDs, Desktop app type) and save as
`~/.reheat/google-search-console.json`. Then:

```bash
reheat sources create \
  --source-type google_search_console \
  --domain yourdomain.com \
  --client-secrets-path ~/.reheat/google-search-console.json
```

### Authenticate

```bash
reheat sources auth
```

Opens a browser for the Google OAuth2 consent flow. The token is persisted
to `~/.reheat/gsc_token.json` and refreshed automatically on subsequent runs.

### Configure a SerpAPI source (optional)

Required for PAA and related search enrichment. Get an API key at
[serpapi.com](https://serpapi.com).

```bash
reheat sources create \
  --source-type serp \
  --api-key YOUR_SERP_API_KEY
```

### Run the pipeline

```bash
# Fetch queries from Search Console
reheat runs create

# Enrich and process
reheat enrich adjacent
reheat enrich tags
reheat enrich embed
reheat enrich cluster
reheat analyse opportunities
reheat analyse summarise

# Build report data
reheat project create
reheat report scatter create
reheat report summary create
reheat report coverage create

# Start the web interface
reheat serve
```

Open [http://localhost:8000](http://localhost:8000).

---

## Inference providers

`reheat analyse summarise` labels intent clusters using an LLM. Configure
one of the following.

### OpenAI

Set `OPENAI_API_KEY` in your environment or `.env` file, or:

```bash
reheat config set --key openai_api_key --value sk-...
```

### Anthropic

Set `ANTHROPIC_API_KEY` in your environment or `.env` file, or:

```bash
reheat config set --key anthropic_api_key --value sk-ant-...
```

### Marigold

[Marigold](https://marigold.run) is a private inference API built by
Bay Information Systems. Set endpoint and key when available:

```bash
reheat config set --key marigold_endpoint --value https://api.marigold.run
reheat config set --key marigold_api_key --value <key>
```

---

## CLI reference

```
reheat config show / set
reheat sources create / list / show / update / delete / auth
reheat runs create / list / show / delete
reheat enrichments list / show / delete
reheat enrich adjacent / tags / embed / cluster
reheat analyse opportunities / summarise
reheat project create / read
reheat report scatter / summary / coverage / opportunities / overlaps  create / read
reheat serve
```

---

## Architecture

reheat has three layers.

**Commands** in `reheat/commands/` are the single source of truth for the
application surface. Each command is a Python function decorated with
`@command`, registered in a central registry, and exposed automatically
through both the CLI and the HTTP API.

**Pipeline** functions in `reheat/pipeline/` are pure data transforms:
embedding, clustering, gap analysis, report building. No persistence, no
side effects.

**Persistence** uses [dynawrap](https://github.com/bayinfosys/dynawrap),
a lightweight key-value library with identical interfaces over PostgreSQL
and DynamoDB. Tables are passed at call time; models are backend-agnostic.

The web interface is a static SPA served by FastAPI. All pages share a
single stylesheet and a common `api.js` module that is the single source
of truth for API endpoint calls.

---

## Requirements

- Python 3.10+
- PostgreSQL (or JSON file backend for local development)
- Google Search Console OAuth2 credentials
- SerpAPI key (optional, for PAA enrichment)
- OpenAI, Anthropic, or Marigold key (optional, for cluster summarisation)

---

## License

MIT. See [LICENSE](LICENSE).

---

Built by Edward Grundy [Bay Information Systems](https://bayis.co.uk)
