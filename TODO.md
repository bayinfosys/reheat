# reheat TODO

## Bugs / known issues

- SerpAPI free tier detection -- hitting the limit mid-run produces a flood
  of 429 warnings with no clear summary. Should detect exhaustion early and
  stop cleanly with a message.

- `cmd_runs_delete --all` uses `input()` for confirmation -- interactive only.
  Needs a `--force` flag for non-interactive use via the API.

- `SerpAPIProvider.enrich` return annotation is `List[QueryRecord]` but the
  function returns `Dict[str, dict]`. Fix the annotation.

- ProjectionData: cross-run visual comparability requires a shared projection
  model. Evaluate ProjectionModel DBItem (analogous to ClusterModel) that
  stores a fitted UMAP transform and can be applied to new runs.
  Current per-run UMAP fits are not comparable across runs.

## Performance

- Async SerpAPI enrichment -- replace sequential loop in `sources/serp.py`
  with `asyncio` + `httpx`, ~5 concurrent requests with a semaphore.
  Would bring 50-query enrichment from ~2 minutes to ~10 seconds.

## Features

- LLM cluster summarisation -- `reheat analyse summarise` calls
  `get_instruct_provider` and works with OpenAI, Anthropic, or Marigold.
  Requires a provider key to be configured. Needs an end-to-end test run.

- Queries page sortable columns -- sort indicators exist but the initial
  sort on page load should respect the `?sort=` param visually (highlight
  the correct column header).

- Explorer: auto-select latest run on load rather than showing empty detail
  panel.

- Explorer: run the report pipeline from the UI -- a "Run pipeline" button
  that fires the enrich/project/report commands via the API.

- pipeline/mst.py: implement minimum spanning tree over cluster centroids.
  ClusterBackbone DBItem is defined in state/execution.py.
  Command cmd_enrich_backbone is not yet registered.

## Refactoring

- `cmd_config_set` type coercion uses `str(annotation)` string comparison
  to determine field types. Replace with direct `is int`, `is float`
  checks against the actual annotation object from `model_fields`.

- `transform.py`: two unrelated concerns in one file, and imports appear
  mid-file. Split into:
    - `reheat/pipeline/text.py` -- `to_embedding_text` only
    - `reheat/pipeline/project_transform.py` -- `project_embeddings`,
      `reduce_embeddings`
  Move all imports to the top of each resulting file.

- Add a `register_all_commands()` function in `reheat/commands/__init__.py`
  that imports all command modules explicitly. Call it from `__main__.py`
  instead of the current bare import block. Add a comment explaining
  that the imports are not unused -- they register commands as a side effect.

- Expose the registry via a public accessor (`get_commands()` or
  `iter_commands()`) in `registry.py`. Remove direct imports of the private
  `_registry` name from both adapters.

- Ensure `dynawrap` has a published PyPI release pinned to a minimum version
  in `pyproject.toml`. Confirm `pip install reheat` succeeds on a clean
  environment with no pre-existing bayis packages.

## Sources backlog

- Bing Webmaster Tools source provider
- YouTube Analytics source provider
- Google Ads keyword planner source provider
- CSV import source provider (`reheat sources create --source-type csv`)
- Ahrefs / Semrush API source provider

## Infrastructure

- JSON file backend for dynawrap -- `dynawrap/backends/json_file.py` exists
  in reheat but should be contributed upstream to dynawrap so local
  development does not require postgres.

- Multi-user support -- `user_id` is hardcoded to `"default"` throughout.
  Should be derived from auth context once multi-tenancy is needed.

- Schema migrations -- dynawrap stores `schema_version` on every record.
  No migration tooling yet.

## Documentation

- bayis.co.uk product page for reheat with Marigold tie-in and waitlist CTA
- API reference documentation
- docs/index.md -- GitHub Pages entry point with Jekyll config

## Hosted product (subscription tier)

These items are the path from local CLI tool to hosted subscription product.

### Authentication and accounts

- User authentication layer -- email/password or OAuth (Google sign-in is
  the natural choice given the GSC dependency). Session management via
  JWT or similar. UserState maps to an authenticated account rather than
  the hardcoded "default" user_id.

- Account creation flow -- email verification, password reset, basic
  account management page.

### Billing

- Stripe integration -- subscription tiers, payment method capture,
  invoice generation. Start with a single paid tier (GBP 20-50/month)
  and a free tier with a run limit (e.g. one run, no SerpAPI enrichment).

- Usage tracking -- runs per account, enrichment calls per account.
  Required for enforcing tier limits and for understanding usage patterns
  before pricing is finalised.

- Upgrade/downgrade flow -- in-product prompt when a free tier user hits
  a limit.

### Google Search Console onboarding

- Hosted OAuth2 flow -- register reheat as a Google Cloud application,
  implement the OAuth2 consent flow in the web interface. The user clicks
  "Connect Google Search Console", authorises in a browser popup, and the
  token is stored server-side against their account. No JSON file download,
  no CLI command.

- Domain selection -- after OAuth2, fetch the list of properties the user
  has access to in Search Console and present them as a dropdown. No
  manual domain entry.

- First-run pipeline trigger -- after domain selection, offer to run the
  pipeline immediately. A progress indicator in the UI rather than terminal
  output.

- Token refresh -- handle GSC token expiry server-side with no user
  intervention required.

### Onboarding flow

- Welcome screen -- shown on first login. Three steps: connect Search
  Console, select domain, run first analysis. Each step has a clear
  completion state.

- Empty state handling -- every page in the UI should have a useful empty
  state that explains what will appear there and links to the next action.

- First run completion -- after the first pipeline run completes, surface
  the scatter plot and opportunities table immediately with a brief
  explanation of what each shows. Do not require the user to navigate.

- SerpAPI key prompt -- after first run, prompt the user to add a SerpAPI
  key for enrichment. Explain what it adds and link to serpapi.com. Make
  it easy to skip.

### Infrastructure for hosted deployment

- Environment configuration -- DATABASE_URL, STRIPE_SECRET_KEY,
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and inference provider keys
  loaded from environment. No credentials in config files in a hosted
  context.

- Multi-tenancy -- user_id derived from authenticated session throughout.
  Prerequisite for the hosted product.

- Background job queue -- pipeline stages are slow (embedding, SerpAPI
  enrichment). In a hosted context these must run as background jobs with
  progress reported to the UI via polling or websocket. FastAPI + a simple
  task queue (Celery or arq) is the likely approach.

- Deployment target -- the architecture already supports DynamoDB as the
  persistence backend. AWS Lambda + DynamoDB + S3 for static assets is a
  natural hosted configuration. Document the deployment path.


## From session 2026-06-08

- `--rollback` flag for pipeline commands: each granular command needs to
  return a `_written` list of `(table, pk, sk)` tuples so the pipeline
  runner can clean up partial writes on failure.

- `reheat enrich list --run-id` command to list enrichment records for a
  run without dropping to psql.

- `RunRecord` should store `days` and `limit` from the GSC source settings
  so each run is self-describing.

- `UserState` should carry a `schedule_items` setting to control the target
  count in `build_schedule` without touching the prompt.

- `summarise_all` skips adjacent-only clusters -- fixed in this session.
  Monitor whether the `[adjacent-only]` description prefix causes issues
  in downstream report rendering.

- Per-run source filtering: `--serp-source-id` flag on `reheat enrich adjacent`
  to restrict enrichment to a specific serp source without container separation.

- `reheat enrich` help text shows `subcommand ...` as required even when
  a default function is registered. Fix the help formatter to show
  `[subcommand]` when a default exists.

- `cmd_sources_auth` removed -- OAuth flow is now automatic on first fetch.
  Confirm no references remain in docs or tests.

- Remove `requests` from `pyproject.toml` dependencies -- replaced by
  `httpx[http2]` in `serp.py`.

- Serp source `limit` default is inconsistent: registration defaults to 200
  but provider defaults to 50. Align both to 50.
