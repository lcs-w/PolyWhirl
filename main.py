import argparse
import asyncio

import requests

from src.PolyEvent import PolyEvent
from src.PolyStreamer import PolyStreamer


def fetch_tokens(slug: str):
    pe = PolyEvent()
    pe.slug = slug
    tokens = []
    with requests.Session() as s:
        pe.get_event(s)
        for m in pe.markets:
            m.get_market(s)
            tokens.extend(m.get_token_essence_pair())
    return tokens


def main():
    parser = argparse.ArgumentParser(
        description="Stream a Polymarket event's order flow into Redis."
    )
    parser.add_argument("slug", help="last path segment of polymarket.com/event/<slug>")
    args = parser.parse_args()

    tokens = fetch_tokens(args.slug)
    print(f"Streaming {len(tokens)} tokens from {args.slug}")
    asyncio.run(PolyStreamer(tokens).get_ob_ws())


if __name__ == "__main__":
    main()
