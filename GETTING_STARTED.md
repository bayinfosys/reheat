# Getting started with reheat

This guide walks through a complete first run: from installation to a
content schedule in the browser.

---

## Prerequisites

- Python 3.10 or later
- Docker (for the database)
- A Google Search Console property you have access to
- A Google Cloud project (free) with the Search Console API enabled
- A SerpAPI account (optional -- see note on costs below)
- An OpenAI or Anthropic API key

---

## 1. Install

```bash
python -m venv venv
source venv/bin/activate
pip install reheat
```

---

## 2. Start a database

reheat stores runs, enrichments, and report data in PostgreSQL.

```bash
docker run -d \
  --name reheat-pg \
  --rm \
  -e POSTGRES_USER=reheat \
  -e POSTGRES_PASSWORD=reheat \
  -e POSTGRES_DB=reheat \
  -p 5432:5432 \
  postgres:16

export DATABASE_URL="postgresql://reheat:reheat@localhost:5432/reheat"
```

---

## 3. Set up Google Search Console access

reheat reads your GSC query data using a Google OAuth2 Desktop application
that you create and own. reheat never has access to your credentials or
your data -- the OAuth flow runs entirely between your machine and Google.

**3a. Create a Google Cloud project**

Go to [console.cloud.google.com](https://console.cloud.google.com) and
create a new project, or select an existing one.

**3b. Enable the Search Console API**

Go to APIs and Services > Library, search for "Google Search Console API",
and enable it.
Direct link: [console.cloud.google.com/apis/library/searchconsole.googleapis.com](https://console.cloud.google.com/apis/library/searchconsole.googleapis.com)

**3c. Create OAuth2 credentials**

Go to APIs and Services > Credentials > Create Credentials > OAuth 2.0
Client ID. Select **Desktop app** as the application type. Download the
JSON file.

Direct link: [console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials)

> Service account keys and web application credentials will not work.
> The application type must be Desktop app.

**3d. Configure the OAuth consent screen**

If prompted, configure the consent screen. Set the user type to External,
add your own Google account as a test user, and add the scope
`https://www.googleapis.com/auth/webmasters.readonly`.

**3e. Set environment variables**

```bash
export GOOGLE_CLIENT_SECRETS_PATH="/path/to/client_secrets.json"
export GOOGLE_TOKEN_PATH="/path/to/token.json"
```

`GOOGLE_CLIENT_SECRETS_PATH` points to the downloaded JSON file (read-only).
`GOOGLE_TOKEN_PATH` is where reheat writes the OAuth token after the first
consent flow. Point it to a persistent writable location. The browser
consent flow runs once and is not required again until the token expires.

---

## 4. Set up SerpAPI

SerpAPI provides related search and People Also Ask data, which improves
cluster quality and opportunity scoring significantly.

```bash
export SERPAPI_KEY="your-serpapi-key"
```

Sign up at [serpapi.com](https://serpapi.com).

> **Cost note.** The SerpAPI free tier includes 250 searches per month.
> A single `reheat enrich adjacent` run against 250 queries will consume
> the full free allocation. If you are on a paid plan, use
> `--serp-enrich-limit` to cap the number of queries enriched (default is 50)
>
>     reheat config set --key serp_enrich_limit --value 50
>

---

## 5. Set up an LLM provider

`reheat analyse` uses an LLM to label clusters and generate the content
schedule. Set one of:

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

---

## 6. Initialise and verify config

```bash
reheat config init
reheat config show
```

The defaults are sensible for a first run. No values need editing before
proceeding.

---

## 7. Register sources

```bash
reheat sources create \
  --source-type google_search_console \
  --domain yourdomain.com

reheat sources create \
  --source-type serp \
  --domain google

reheat sources list
```

---

## 8. Fetch

```bash
reheat runs create
```

On the first run the browser opens for the Google OAuth consent flow.
Approve access and return to the terminal. The token is written to
`GOOGLE_TOKEN_PATH` and reused on subsequent runs.

This fetches up to `fetch_limit` queries (default 25,000) from the last
`fetch_days` days (default 90).

---

## 9. Enrich

```bash
reheat enrich
```

This runs four steps in sequence: adjacent search enrichment via SerpAPI,
query tagging, embedding, and clustering. The SerpAPI step is the slowest --
allow 2-3 minutes for 200 queries. The embedding step downloads the local
model on first run (~90MB) and is fast on subsequent runs.

---

## 10. Analyse

```bash
reheat analyse
```

Labels each cluster with an LLM, scores content opportunities, generates
the content schedule, computes the UMAP projection, and builds all report
data. Takes 30-60 seconds depending on the LLM provider.

> **What you might see.** If a brand name appears frequently across your
> GSC queries it may surface as a cluster label (for example,
> "Bay Information and Systems"). This is the embedding model treating a
> frequent string as a topical signal rather than a genuine content gap.
> See the Known Limitations section in the README.

---

## 11. View results

```bash
reheat serve
```

Open [http://localhost:8000](http://localhost:8000).

The content schedule are recommendations of new topics and SEO terms to include.
The Intent Map tab shows the UMAP projection with cluster labels.
The High-Value Topics tab lists queries appearing across multiple clusters -- a single piece of content targeting these serves several audiences at once.

The full HTTP API is documented at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## Screenshots

**Content schedule**
![Content schedule](docs/serve-content-schedule.gif)

**Intent map**
![Intent map](docs/serve-intent-map.gif)

**High-value topics**
![High-value topics](docs/serve-high-value-topics.gif)
