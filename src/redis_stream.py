import asyncio
import aiohttp
import time
import redis
import requests

from PolyMarket import PolyMarket
from PolyOrderBook import PolyOrderBook


async def redis_stream(r: redis.asyncio.Redis, order_book: PolyOrderBook) -> None:
    await r.xadd(
        order_book.market_slug,
        {
            "direction": int(bool(order_book.direction)),
            "timestamp": order_book.timestamp,
            "highest_bid": order_book.bids_highest.get("price", 0),
            "lowest_ask": order_book.asks_lowest.get("price", 0),
        },
    )


async def main(market: PolyMarket, duration_sec: int = 10, interval: float = 0.5):

    # connect with Redis
    try:
        r = redis.asyncio.Redis(host="localhost", port=6379, db=0)
        print(await r.ping())
    except Exception as e:
        print(f"  Redis connection failed: {e}")

    async with aiohttp.ClientSession() as session:
        start_time = time.perf_counter()

        # Calculate total iterations (120 iterations for 60 seconds at 0.5s intervals)
        iterations = int(duration_sec / interval)

        for i in range(iterations):
            # Fetch both books
            order_book_yes, order_book_no = await market.get_ob_async(session)

            # stream to redis
            await asyncio.gather(
                redis_stream(r, order_book_yes),
                redis_stream(r, order_book_no),
            )

            # Process your data here
            print(f"Iteration {i+1}/{iterations} completed.")

            # Wait for the remainder of the interval
            await asyncio.sleep(interval)

        end_time = time.perf_counter()
        print(f"Loop finished after {end_time - start_time:.2f} seconds.")

    await r.aclose()


if __name__ == "__main__":
    pm = PolyMarket()
    pm.slug = "btc-updown-15m-1781818200"

    # create a requests session
    with requests.Session() as requests_session:
        pm.get_market(requests_session)

    asyncio.run(main(pm))
