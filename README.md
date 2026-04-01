---
title: WebRoulette
emoji: 🌐
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: true
---

# 🌐 WebRoulette — Discover Random Websites

A random website discovery platform that indexes the entire web using:

- **Certificate Transparency Logs** — Real-time domain discovery via CertStream
- **Common Crawl** — Batch import from the largest public web archive
- **BFS Recursive Crawler** — Breadth-first link extraction and traversal
- **Polite Validation** — Rate-limited, robots.txt-compliant URL verification

## Features

- 🎲 **Random Button** — Instant redirect to a random live website
- 🔍 **Search** — Find specific indexed websites
- ➕ **Submit URLs** — Add websites to the index
- 📊 **Live Counter** — Real-time count of active indexed sites (via Supabase Realtime)

## Architecture

- **Backend**: Python / FastAPI with async workers
- **Frontend**: Vanilla HTML/CSS/JS with Supabase JS client
- **Database**: Supabase (PostgreSQL) with RLS and Realtime
- **Deployment**: Docker on Hugging Face Spaces

## Links

- [GitHub Repository](https://github.com/guestcoder0906/RandomWebsite)
