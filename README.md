# IBKR MCP Service

An **MCP (Model Context Protocol) server** that exposes Interactive Brokers market data tools
via `ib_async`, with PostgreSQL persistence and background sync.

## Tools

| Tool | Description |
|---|---|
| `get_quotes` | Historical OHLCV bars — symbol, duration, bar size, adjusted flag |
| `get_fundamentals` | Financial summary / ratios XML from IBKR |
| `get_earnings` | Earnings calendar report XML from IBKR |

All results are cached in PostgreSQL and returned from cache on subsequent calls.
A background sync process refreshes all cached symbols on a configurable interval.

## Quick Start

### 1 — Prerequisites

- IB Gateway or TWS running with API enabled on port `7497` (TWS) / `4001` (Gateway)
- Docker + Docker Compose OR Python 3.11+ with [uv](https://github.com/astral-sh/uv)

### 2 — Docker (recommended)
