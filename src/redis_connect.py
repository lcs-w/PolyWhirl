import redis
import requests
from datetime import datetime
from typing import List
import time
import aiohttp
import asyncio


from .PolyMarket import PolyMarket
from .PolyDirection import PolyDirection
from .PolyOrderBook import PolyOrderBook


async def async_get_ob(market: PolyMarket):
    async with aiohttp.ClientSession() as session:
        # Pass the same session throughout the lifecycle
        order_book_yes, order_book_no = await market.get_ob_async(session)

    return order_book_yes, order_book_no


if __name__ == "__main__":
    try:
        r = redis.Redis(host="localhost", port=6379, db=0)
        print(r.ping())
    except Exception as e:
        print(f"  Redis connection failed: {e}")

    request_session = requests.Session()

    ballon_dor_mbapp = PolyMarket()
    ballon_dor_mbapp.slug = "will-kylian-mbapp-win-the-2026-ballon-dor"
    ballon_dor_mbapp.get_market(request_session)

    fetch_w_aiohttp = datetime.now().timestamp()

    order_book_yes, order_book_no = asyncio.run(async_get_ob(ballon_dor_mbapp))

    after_request = datetime.now().timestamp()

    def set_redis_order_book(order_book: PolyOrderBook) -> None:
        key = f"{order_book.market_slug}:{int(bool(order_book.direction))}"
        value = {
            "timestamp": order_book.timestamp,
            "highest_bid": order_book.bids_highest.get("price", 0),
            "lowest_ask": order_book.asks_lowest.get("price", 0),
        }
        r.json().set(key, "$", value)
        r.expire(key, 300)

    def push_redis_list(list_order_book: List[PolyOrderBook]) -> None:
        for ob in list_order_book:
            r.lpush(
                ob.market_slug,
                str(
                    {
                        "direction": int(bool(ob.direction)),
                        "timestamp": ob.timestamp,
                        "highest_bid": ob.bids_highest.get("price", 0),
                        "lowest_ask": ob.asks_lowest.get("price", 0),
                    }
                ),
            )
            r.expire(ob.market_slug, 120 * 60)

    set_redis_order_book(order_book_yes)
    set_redis_order_book(order_book_no)

    push_redis_list([order_book_yes, order_book_no])

    end = datetime.now().timestamp()

    request_session.close()

    print(f"fetch with aiohttp: {after_request - fetch_w_aiohttp:0.6f}")
    print(f"write to Redis:     {end - after_request:0.6f}")
    print(f"total time:         {end - fetch_w_aiohttp:0.6f}")
