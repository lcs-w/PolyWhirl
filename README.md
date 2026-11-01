# PolyWhirl

Real-time Polymarket order-flow streamer and signal-detection toolkit.

PolyWhirl subscribes to Polymarket's CLOB market WebSocket, persists every order-book and trade event to Redis Streams, and layers signal detectors on top: order-book microstructure, LLM news sentiment, and VPIN-style toxic-flow detection. The goal is to spot informed flow and cross-market mispricing in prediction markets as it happens.

> **Status:** early-stage research code. Ingestion works end to end. `OrderBookSignal` (backed by the C++ `TickBuffer`) and `VPIN` are implemented as in-process classes; the Redis consumers that run them live and the signal combiner are not built yet. See [Roadmap](#roadmap).

## Architecture

```
                     Gamma API (REST)                     CLOB API (REST)
              event / market metadata, token IDs        /book snapshots
                          │                                    │
                          ▼                                    ▼
                ┌───────────────────┐              ┌──────────────────────┐
                │ PolyEvent         │──markets───► │ PolyMarket           │
                │ PolyMarket        │              │  get_order_book[_async]
                │ PolyTokenEssence  │              │  → PolyOrderBook     │
                └─────────┬─────────┘              └──────────────────────┘
                          │ token_id → (market_slug, YES/NO)
                          ▼
  Polymarket WS  ┌───────────────────┐   XADD   ┌──────────────────────────────┐
  /ws/market ───►│ PolyStreamer      │─────────►│ Redis Streams                │
  (book, price_  │  asyncio+aiohttp  │          │  key: {market_slug}:{event}  │
   change, last_ │  10s PING/PONG    │          │  e.g. iran-deal…:last_trade_ │
   trade_price,  └───────────────────┘          │       price                  │
   best_bid_ask…)                               └──────────────┬───────────────┘
                                                               │ XREAD (consumers planned)
                ┌──────────────────────────────────────────────┤
                │ book (YES token only)                        │ last_trade_price         news headlines
                │ + last_trade_price sizes                     │                                │
                ▼                                              ▼                                ▼
  ┌───────────────────────────────┐              ┌──────────────────────────┐   ┌──────────────────────────┐
  │ OrderBookSignal               │              │ VPIN                     │   │ SentimentDetector        │
  │  micro-price, depth-weighted  │              │  YES/NO merged into      │   │  headline vs. target     │
  │  OBI per snapshot             │              │  YES-space, volume-clock │   │  event → −2 … +2         │
  │        │ push tick            │              │  buckets → toxicity,     │   │  via Ollama gemma3:4b    │
  │        ▼                      │              │  signed flow, percentile │   │                          │
  │  TickBuffer (C++, pybind11)   │              │                          │   │                          │
  │  mid z-score, OBI EWMA, VWAP  │              │                          │   │                          │
  └───────────────┬───────────────┘              └─────────────┬────────────┘   └─────────────┬────────────┘
                  └────────────────────────────────┬───────────┴──────────────────────────────┘
                                                   ▼
                                     [ Combined trade signal ]  (planned)
```

The first piece is in place: the C++ [`TickBuffer`](#tickbuffer-c) feature engine, built with `pybind11` and `scikit-build-core`.

## Repository layout

| Path | Purpose |
|---|---|
| [src/PolyAPI.py](src/PolyAPI.py) | Polymarket endpoint constants (Gamma, Data, CLOB, WebSocket). |
| [src/PolyEvent.py](src/PolyEvent.py) | Fetch an event by slug and build its `PolyMarket`s. |
| [src/PolyMarket.py](src/PolyMarket.py) | Fetch market metadata and YES/NO token IDs; fetch order books (sync and async). |
| [src/PolyOrderBook.py](src/PolyOrderBook.py) | Parsed order book: sorted bids and asks, best bid/ask, Polars price-ladder export. |
| [src/PolyDirection.py](src/PolyDirection.py) | `YES` / `NO` outcome enum. |
| [src/PolyTokenEssence.py](src/PolyTokenEssence.py) | Maps a token ID to its market slug and direction. |
| [src/PolyStreamer.py](src/PolyStreamer.py) | **Main ingester.** WebSocket → Redis Streams. |
| [signal_detection/OrderBookSignal.py](signal_detection/OrderBookSignal.py) | Per-market order-book features: micro-price and depth-weighted imbalance per snapshot, plus their history in a `TickBuffer`. |
| [signal_detection/VPIN.py](signal_detection/VPIN.py) | Volume-synchronized probability of informed trading, with a `Trade` type that normalizes YES and NO trades into YES-space. |
| [signal_detection/SentimentDetector.py](signal_detection/SentimentDetector.py) | LLM headline-sentiment classifier against a target event. |
| [feature/](feature/) | **C++ `TickBuffer`** (pybind11): ring buffer of ticks with VWAP, mid z-score and imbalance EWMA, exported as numpy arrays. Built by [CMakeLists.txt](CMakeLists.txt). |
| [tests/](tests/) | pytest suite for `TickBuffer` and `OrderBookSignal`. |
| [src/requests_v_aiohttp.py](src/requests_v_aiohttp.py), [src/redis_connect.py](src/redis_connect.py) | Latency benchmarks: `requests` vs. `aiohttp`, Redis write cost. |
| [src/redis_stream.py](src/redis_stream.py) | Legacy REST-polling streamer, superseded by `PolyStreamer`. |
| `notebooks/` | Exploratory analysis (TickBuffer Benchmarking, Redis connect). |
| [src/Kafka_producer.py](src/Kafka_producer.py), [src/Kafka_consumer.py](src/Kafka_consumer.py) | Kafka smoke tests (not wired into the pipeline). |

## Prerequisites

- Python 3.12+ (the code uses 3.12 f-string syntax)
- [uv](https://docs.astral.sh/uv/)
- A C++17 compiler for the `feature` extension: MSVC (Visual Studio 2022 with "Desktop development with C++") on Windows, or gcc/clang elsewhere. CMake is fetched automatically during the build.
- Docker with Compose
- Optional: an NVIDIA GPU for Ollama. Without one, delete the `deploy:` block under the `ollama` service in [docker-compose.yml](docker-compose.yml).

## Quick start

### 1. Install dependencies

```bash
uv sync          # also compiles the C++ extension (first build takes a minute or two)
uv run pytest    # run the test suite
```

uv rebuilds the extension automatically when `CMakeLists.txt` or anything in `feature/cpp/` changes.

### 2. Start the infrastructure

```bash
# Just Redis (all you need for streaming):
docker compose up -d redis

# Or everything: Redis, Ollama (+ pulls gemma3:4b), Kafka, Zookeeper
docker compose up -d
```

| Service | Port | Notes |
|---|---|---|
| Redis Stack | `6379` | No persistence (`--save ""`), 2 GB LRU cap; data is ephemeral. |
| RedisInsight | `8001` | Browse streams at <http://localhost:8001>. |
| Ollama | `11434` | OpenAI-compatible endpoint used by `SentimentDetector`. |

### 3. Stream a Polymarket event into Redis

Run modules from the repo root with `-m` so the `src.` imports resolve:

```bash
uv run python -m src.PolyStreamer
```

This streams every market in the event slug set in the `__main__` block of [src/PolyStreamer.py](src/PolyStreamer.py). Edit `pe.slug` to target another event. The slug is the last path segment of the event URL, e.g. `polymarket.com/event/<slug>`.

Or use it from code:

```python
import asyncio, requests
from src.PolyEvent import PolyEvent
from src.PolyStreamer import PolyStreamer

pe = PolyEvent()
pe.slug = "your-event-slug"
tokens = []
with requests.Session() as s:
    pe.get_event(s)
    for m in pe.markets:
        m.get_market(s)
        tokens.extend(m.get_token_essence_pair())

asyncio.run(PolyStreamer(tokens).get_ob_ws())
```

### 4. Inspect the data

```bash
docker exec -it polymarket-hft-redis redis-cli
> KEYS *
> XREVRANGE <market_slug>:last_trade_price + - COUNT 5
```

Each stream entry has these fields:

| Field | Value |
|---|---|
| `direction` | `1` = YES token, `0` = NO token |
| `timestamp` | Exchange timestamp (ms) |
| `raw` | The original WebSocket message |

Stream keys follow `{market_slug}:{event_type}`, where `event_type` is one of `book`, `price_change`, `last_trade_price`, `best_bid_ask`, `tick_size_change`, `new_market`, or `market_resolved`. Messages without a top-level `asset_id` (e.g. batched `price_change`) are currently skipped.

### 5. Run the sentiment detector (optional)

Requires the `ollama` service with `gemma3:4b` pulled. `docker compose up -d` does the pull through `ollama-init`.

```bash
uv run python -m signal_detection.SentimentDetector
```

It outputs one integer per headline, from `-2` (prevents the target event) to `+2` (event imminent).

## Signal detection

| Detector | Input | Output | Use |
|---|---|---|---|
| **OrderBookSignal** | `book` snapshots (YES token) + trade sizes | Micro-price, depth-weighted imbalance, mid z-score, imbalance EWMA, gap to VWAP | Passive supply/demand pressure, and whether price has caught up with it |
| **VPIN** | `last_trade_price` (YES and NO merged into YES-space) | Toxicity in `[0,1]`, signed flow in `[-1,1]`, rolling percentile | Detect informed, one-sided aggressive flow |
| **SentimentDetector** | News headlines | `-2 … +2` per target event | Public-information baseline |

### OrderBookSignal

One instance per market. Feed it books and trades; each book returns an `OrderBookFeatures` record.

```python
from signal_detection.OrderBookSignal import OrderBookSignal
from signal_detection.VPIN import Trade

sig = OrderBookSignal(depth=5, z_window=100, alpha=0.1)

sig.on_trade(Trade.from_ws(trade_msg, direction))   # trade size becomes the next tick's volume
features = sig.on_book(order_book)                  # PolyOrderBook -> OrderBookFeatures | None
# features.microprice, .obi, .mid_z, .obi_ewma, .vwap_gap
```

- **Only YES-token books are used.** Polymarket's NO book is an exact mirror of the YES book (YES best bid = 1 − NO best ask in every one of 351 recorded snapshot pairs), so NO books are skipped rather than counted twice.
- Books that are out of order, share the previous timestamp, or have an empty side return `None`.
- `obi` weights level *i* by `decay**i` (default 0.5) across the top `depth` levels, so the best price counts most.
- `mid_z` is NaN until `z_window` books have arrived, and `vwap_gap` is NaN until at least one trade is seen. Treat NaN as "not enough data yet".

Reading the features together:

| `obi_ewma` | `mid_z` | Reading |
|---|---|---|
| Strongly + | ~0 | Buying pressure is building but price hasn't moved yet. |
| Strongly + | > +2 | The move already happened; watch for a reversal. |
| Flips sign | Extreme | Pressure fading after a run; mean-reversion candidate. |

Agreement with a high VPIN percentile (aggressive trades in the same direction) makes any of these stronger.

### TickBuffer (C++)

A fixed-capacity ring buffer of `(mid, spread, imbalance, timestamp, volume)` ticks, written in C++ and exposed through pybind11. Each field is stored in its own contiguous array, so exporting it to numpy takes at most two block copies.

```python
from feature import TickBuffer, tick_from_order_book

buf = TickBuffer(capacity=1_000)
buf.push(*tick_from_order_book(order_book), volume=traded_size)

buf.vwap(50)                     # volume-weighted mid over the last 50 ticks
buf.mid_zscore(100)              # latest mid vs. the last 100 (NaN until filled)
buf.imbalance_ewma(0.1)          # smoothed top-of-book imbalance

X = buf.to_numpy()               # (n, 5) float64, columns = feature.COLUMNS
z = buf.mid_zscore_series(100)   # per-tick features aligned with X, for ML
```

`extend(...)` bulk-loads from numpy arrays for backtests, so offline features come from the same C++ code as the live path. The buffer is not thread-safe.

Combining the detectors is the point. For example, high VPIN with strong signed buying while sentiment is `0` suggests informed trading *ahead* of public news.

## Roadmap

- [x] C++ `TickBuffer` feature engine (pybind11)
- [x] `OrderBookSignal`: micro-price, depth-weighted imbalance, time-series features
- [x] `VPIN` core class
- [ ] (Back)Tests for `VPIN`
- [ ] Redis consumers publishing `{slug}:obsignal` and `{slug}:vpin`
- [ ] Remaining `OrderBookSignal` ideas: book slope, walls, market-impact simulation
- [ ] Store `raw` as JSON (`json.dumps`) instead of a Python `repr`, and keep Redis writes in order
- [ ] Handle batched `price_change` messages

## Disclaimer

Research and educational use only. Nothing here is financial advice. Check Polymarket's Terms of Service and your local regulations before trading.
