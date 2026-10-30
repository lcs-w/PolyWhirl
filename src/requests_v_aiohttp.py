import requests
from datetime import datetime
import aiohttp
import asyncio

from src.PolyMarket import PolyMarket
from src.PolyDirection import PolyDirection
from src.PolyOrderBook import PolyOrderBook


async def async_get_ob(market: PolyMarket):
    async with aiohttp.ClientSession() as session:
        # Pass the same session throughout the lifecycle
        order_book_yes, order_book_no = await market.get_ob_async(session)

    return order_book_yes, order_book_no


if __name__ == "__main__":
    request_session = requests.Session()

    next_15m = int(((datetime.now().timestamp() // 900) + 1) * 900)

    pm = PolyMarket()
    pm.slug = f"btc-updown-5m-{next_15m}"
    pm.get_market(request_session)

    fetch_w_requests = datetime.now().timestamp()
    print(int(fetch_w_requests * 1000))

    order_book_yes = pm.get_order_book(request_session)
    order_book_no = pm.get_order_book(request_session, direction=PolyDirection.NO)

    fetch_w_aiohttp = datetime.now().timestamp()
    print(f"fetch with requests:    {fetch_w_aiohttp - fetch_w_requests:0.6f}")
    print(order_book_yes)
    print(order_book_no)

    print(int(fetch_w_aiohttp * 1000))
    order_book_yes_async, order_book_no_async = asyncio.run(async_get_ob(pm))

    end = datetime.now().timestamp()
    print(f"fetch with aiohttp:     {end - fetch_w_aiohttp:0.6f}")
    print(order_book_yes_async)
    print(order_book_no_async)

    print(f"total time:             {end - fetch_w_requests:0.6f}")
