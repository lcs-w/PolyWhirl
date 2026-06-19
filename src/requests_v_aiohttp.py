import requests
from datetime import datetime
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
    request_session = requests.Session()

    ballon_dor_mbapp = PolyMarket()
    ballon_dor_mbapp.slug = "will-kylian-mbapp-win-the-2026-ballon-dor"
    ballon_dor_mbapp.get_market(request_session)

    fetch_w_requests = datetime.now().timestamp()

    order_book_yes = ballon_dor_mbapp.get_order_book(request_session)
    order_book_no = ballon_dor_mbapp.get_order_book(
        request_session, direction=PolyDirection.NO
    )

    fetch_w_aiohttp = datetime.now().timestamp()

    order_book_yes_async, order_book_no_async = asyncio.run(
        async_get_ob(ballon_dor_mbapp)
    )

    end = datetime.now().timestamp()

    print(f"fetch with requests:    {fetch_w_aiohttp - fetch_w_requests:0.6f}")
    print(f"fetch with aiohttp:     {end - fetch_w_aiohttp:0.6f}")
    print(f"total time:             {end - fetch_w_requests:0.6f}")

    print(order_book_yes)
    print(order_book_yes_async)
    print(order_book_no)
    print(order_book_no_async)
