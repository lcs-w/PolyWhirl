import asyncio
import aiohttp
import time
import redis
import requests
from datetime import datetime

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
            "all_bids": str(order_book.bids),
            "all_asks": str(order_book.asks),
        },
    )


# stream order book data of f"btc-updown-15m-{next_15m}" until 15 minutes run up
async def main(
    market: PolyMarket,
    next_15m: int,
    interval: float = 1.0,
):
    now = int(datetime.now().timestamp())
    duration_sec = next_15m + 900 - now

    # connect with Redis
    try:
        r = redis.asyncio.Redis(host="localhost", port=6379, db=0)
        print(await r.ping())
    except Exception as e:
        print(f"  Redis connection failed: {e}")

    print(f"Fetching order book of {market.slug}")
    print(
        f"Expected to end at {datetime.fromtimestamp(next_15m + 900).strftime("%Y-%m-%d %H:%M:%S")}"
    )
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
        print(
            f"Loop finished after {end_time - start_time:.2f} seconds. Ended at timestamp {int(datetime.now().timestamp())}"
        )

    await r.aclose()


if __name__ == "__main__":
    from datetime import datetime

    next_15m = int(((datetime.now().timestamp() // 900) + 1) * 900)

    pm = PolyMarket()
    pm.slug = f"btc-updown-15m-{next_15m}"

    # create a requests session
    with requests.Session() as requests_session:
        pm.get_market(requests_session)

    asyncio.run(main(pm, next_15m))
