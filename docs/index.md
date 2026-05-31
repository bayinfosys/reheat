---
layout: default
title: reheat
description: >
  reheat is an open source Python CLI for SEO analysis. Pull queries from
  Google Search Console, cluster by intent, and surface content gaps.
---

# reheat

Open source Python CLI for SEO analysis. Pull your Google Search Console
queries, enrich them with related searches and People Also Ask data, cluster
by semantic intent, and surface content gaps and opportunities.

Built by [Edward Grundy](https://bayis.co.uk) at
[Bay Information Systems](https://bayis.co.uk).

---

## Install

```bash
pip install reheat
```

Requires Python 3.10+.

---

## Quick start

```bash
# Configure your Search Console source
reheat sources create \
  --source-type google_search_console \
  --domain yourdomain.com \
  --client-secrets-path ~/.reheat/google-search-console.json

# Authenticate
reheat sources auth

# Run the pipeline
reheat runs create
reheat enrich tags
reheat enrich embed
reheat enrich cluster
reheat enrich gap
reheat analyse opportunities
reheat project create
reheat report scatter create
reheat report summary create
reheat report coverage create

# Open the web interface
reheat serve
```

---

## Inference providers

Cluster summarisation (`reheat analyse summarise`) works with
[OpenAI](https://openai.com), [Anthropic](https://anthropic.com), or
[Marigold](https://marigold.run). Set the relevant API key in your
environment or `.env` file and reheat will pick it up automatically.

---

## Links

- [GitHub repository](https://github.com/bayinfosys/reheat)
- [PyPI](https://pypi.org/project/reheat)
- [Bay Information Systems](https://bayis.co.uk)
- [dynawrap](https://github.com/bayinfosys/dynawrap) -- persistence layer
