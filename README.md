![Reheat](imgs/reheat02-upscale01.jpeg)

# Reheat

**Semantic Intent Clustering + Content Gap Analysis for Google Search Console**

Reheat turns the flat, overwhelming list of queries in Google Search Console into **clear, actionable insights** about what your audience actually wants.

It pulls your GSC data, enriches it with related searches and People Also Ask, clusters queries by semantic intent, and shows you high-value topics and content opportunities in a local web dashboard.

### Screenshots from my own site (bayis.co.uk)

![High-Value Topics](docs/serve-high-value-topics.gif)
![Content Schedule](docs/serve-content-schedule.gif)
![Intent Map](docs/serve-intent-map.gif)

## Why people use Reheat

- Discover which **topics** your content already serves across many queries
- Find high-potential content gaps ranked by opportunity
- Get a practical content expansion schedule
- Understand real user intent instead of guessing
- Everything runs locally (or with Postgres)

Built and used daily by me on my own technical/ML content site.

---

## Quick Start

```bash
pip install reheat
```

Full setup instructions (including Google Search Console OAuth and SerpAPI key) -> [GETTING_STARTED.md](GETTING_STARTED.md)

Once set up, the basic flow is:
```bash
reheat fetch && reheat enrich && reheat analyse && reheat serve
```

Then open `localhost:8000`

## Key Features

+ Google Search Console data import
+ SerpAPI enrichment (related searches + PAA)
+ Local embeddings + semantic clustering
+ LLM cluster labelling (OpenAI / Anthropic / Marigold)
+ High-value topic detection
+ Content expansion recommendations
+ Interactive intent map (UMAP scatter plot)
+ Local FastAPI web dashboard

Continue reading for full setup, CLI reference, and architecture

---

## Getting started

### 1. Install

```bash
pip install reheat
# or in a virtualenv:
python -m venv venv && source venv/bin/activate
pip install reheat
```

See [GETTING_STARTED.md](GETTING_STARTED.md) for a full walkthrough including Google Cloud setup and SerpAPI configuration.

### 2. Start a postgres instance

reheat uses postgres to store runs, enrichments, and report data.

```bash
docker run -d \
  --name reheat-pg \
  --rm \
  -e POSTGRES_USER=reheat \
  -e POSTGRES_PASSWORD=reheat \
  -e POSTGRES_DB=reheat \
  -p 5432:5432 \
  postgres:16
```

### 3. Set environment variables

```bash
# database
export DATABASE_URL="postgresql://reheat:reheat@localhost:5432/reheat"

# google search console (OAuth2 Desktop app credentials)
export GOOGLE_CLIENT_SECRETS_PATH="/path/to/client_secrets.json"
export GOOGLE_TOKEN_PATH="/path/to/token.json"

# serpapi (optional, for related search enrichment)
export SERPAPI_KEY="your-serpapi-key"

# llm provider (one of the following)
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

The Google credentials file must be an OAuth 2.0 Client ID of type Desktop
app. In Google Cloud Console go to APIs and Services > Credentials > Create
Credentials > OAuth 2.0 Client ID, select Desktop app, and download the JSON
file. Service account keys and web application credentials will not work.

`GOOGLE_TOKEN_PATH` is where reheat writes the OAuth token after the first
consent flow. Point it to a persistent location. The browser consent flow runs
automatically on the first `reheat fetch` and is not required again until the
token expires.

### 4. Register sources

```bash
# google search console
reheat sources create \
  --source-type google_search_console \
  --domain yourdomain.com \
  --days 180

# serpapi (optional)
reheat sources create \
  --source-type serp \
  --domain google
```

The `--days` flag sets the GSC lookback window (default 90, maximum ~480).
The `--domain` flag on the serp source sets the search engine. Supported
values: `google`, `youtube`, `google_patents`, `google_news`.

### 5. Run the pipeline

```bash
reheat fetch
reheat enrich
reheat analyse
reheat serve
```

Open [http://localhost:8000](http://localhost:8000).

The four commands cover the full pipeline. Individual steps are also
available if you need to re-run a specific stage:

```bash
reheat fetch                      # pull queries from Google Search Console
reheat enrich adjacent            # fetch related searches via SerpAPI
reheat enrich tags                # auto-tag queries
reheat enrich embed               # generate embeddings
reheat enrich cluster             # cluster by semantic intent
reheat analyse summarise          # label clusters with an LLM
reheat analyse opportunities      # score content gaps
reheat analyse schedule           # generate content schedule
reheat analyse overview           # generate narrative summary
reheat project create             # compute UMAP projection
reheat report scatter create      # build scatter plot data
reheat report summary create      # build summary panel data
reheat report coverage create     # build coverage table data
reheat serve                      # start the web interface
```

---

## Inference providers

`reheat analyse` labels intent clusters and generates a content schedule
using an LLM. Set one of the following environment variables.

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

[Marigold](https://marigold.run) is a private inference API built by
Bay Information Systems. Configure it in reheat user settings:

```bash
reheat config set --key marigold_endpoint --value https://api.marigold.run
reheat config set --key marigold_api_key --value <key>
```

---

## CLI reference

```
reheat fetch
reheat enrich [adjacent | tags | embed | cluster]
reheat analyse [summarise | opportunities | schedule | overview]
reheat project [create | read]
reheat report [scatter | summary | coverage | opportunities | overlaps] [create | read]
reheat serve

reheat sources [create | list | show | update | delete]
reheat runs [list | show | delete]
reheat config [show | set]
reheat status
```

Pass `--json` before any command for machine-readable output:

```bash
reheat --json sources list
reheat --json runs list
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

**Persistence** uses [dynawrap](https://github.com/bayinfosys/aws-dynamodb-wrapper),
a lightweight key-value library with identical interfaces over PostgreSQL
and DynamoDB. Tables are passed at call time; models are backend-agnostic.
The backend is selected from `DATABASE_URL` at startup.

The web interface is a static SPA served by FastAPI. All pages share a
single stylesheet and a common `api.js` module that is the single source
of truth for API endpoint calls.

---

## Optional dependencies

```bash
pip install reheat[openai]       # OpenAI LLM support
pip install reheat[anthropic]    # Anthropic LLM support
pip install reheat[postgres]     # PostgreSQL backend (psycopg2)
pip install reheat[all]          # all of the above
```

---

## License

MIT. See [LICENSE](LICENSE).

Built by [Edward Grundy](https://bayis.co.uk) at [Bay Information Systems](https://bayis.co.uk).
