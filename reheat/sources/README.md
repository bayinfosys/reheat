# reheat/sources

Source providers pull raw query data into the reheat pipeline.
Each provider implements `SourceProvider` and is configured via a `SourceConfig` record.

## Usage

```bash
reheat sources create --source-type google_search_console --domain bayis.co.uk
reheat sources list
reheat runs create --source-id <id>
```

## Providers

### google_search_console
Pulls search analytics from Google Search Console via OAuth2.

Required credentials: `client_secrets_path`, `token_path`
Settings: `days` (default 90), `limit` (default 200)

### serp
Enriches queries with PAA and related searches from SerpAPI.
Operates on existing QueryRecords rather than producing them.

Required credentials: `api_key`
Settings: `delay` (default 0.5s), `limit` (default 50), `headless` (default false)

## Adding a provider

1. Create `reheat/sources/<name>.py` with a class extending `SourceProvider`
2. Set `source_type = "<name>"` on the class
3. Implement `validate()` and `fetch()` (or `enrich()` for enrichment sources)
4. Register it in `reheat/sources/__init__.py`

## Todo

- **Bing Webmaster Tools** -- equivalent to GSC, broader index coverage
- **YouTube Analytics** -- query data for video content, useful for channels with
  significant search traffic
- **Google Ads (AdWords)** -- keyword planner data, adds search volume estimates
  not available in GSC
- **Facebook/Meta** -- page search and discovery data
- **Ahrefs / Semrush API** -- third-party rank and keyword data as an alternative
  to SerpAPI for PAA enrichment
- **CSV import** -- offline fallback for any source that exports CSV
  (`reheat sources create --source-type csv --file queries.csv`)
