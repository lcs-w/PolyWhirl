import ast
import aiohttp
import asyncio
from typing import Dict, List
import requests

from PolyAPI import POLY_GAMMA_API_URL, POLY_CLOB_API_URL
from PolyOrderBook import PolyOrderBook
from PolyDirection import PolyDirection


class PolyMarket:
    def __init__(self, market: Dict = None, slug: str = None):
        self._market = market
        self._slug = slug

    @property
    def market_url(self):
        return f"{POLY_GAMMA_API_URL}/markets/slug/{self._slug}"

    @property
    def market(self):
        return self._market

    @market.setter
    def market(self, market_value: Dict):
        self._market = market_value

    @property
    def slug(self):
        return self._slug

    @slug.setter
    def slug(self, slug_str: str):
        self._slug = slug_str

    def get_market(
        self, requests_session: requests.Session, include_tag: bool = False
    ) -> dict:
        try:
            response = requests_session.get(
                f"{self.market_url}?include_tag={str(include_tag).lower()}"
            )
            if response.status_code == 200:
                self.market = response.json()
                self.market["clobTokenIds"] = ast.literal_eval(
                    self.market["clobTokenIds"]
                )
                return self.market
        except requests.RequestException:
            return {}

    def get_order_book(
        self,
        requests_session: requests.Session,
        direction: PolyDirection = PolyDirection.YES,
    ) -> PolyOrderBook:
        """Fetch order book for the provided direction with aiohttp. Default to be Yes."""
        token_id = (
            self.market["clobTokenIds"][0]
            if direction == PolyDirection.YES
            else self.market["clobTokenIds"][1]
        )

        order_book = PolyOrderBook()
        order_book.direction = direction

        try:
            response = requests_session.get(
                f"{POLY_CLOB_API_URL}/book?token_id={token_id}"
            )
            if response.status_code == 200:
                order_book.order_book = response.json()
                order_book.market_slug = self.slug
                return order_book
        except requests.RequestException:
            return order_book

    async def get_order_book_async(
        self,
        aiohttp_session: aiohttp.ClientSession,
        direction: PolyDirection = PolyDirection.YES,
    ) -> PolyOrderBook:
        """Fetch order book for the provided direction with aiohttp. Default to be Yes."""
        # Determine the token ID
        token_id = (
            self.market["clobTokenIds"][0]
            if direction == PolyDirection.YES
            else self.market["clobTokenIds"][1]
        )

        order_book = PolyOrderBook()
        order_book.direction = direction

        try:
            # Use aiohttp to perform the GET request
            async with aiohttp_session.get(
                f"{POLY_CLOB_API_URL}/book?token_id={token_id}"
            ) as response:
                if response.status == 200:
                    # Use await response.json() to parse the body asynchronously
                    order_book.order_book = await response.json()
                    order_book.market_slug = self.slug
                    return order_book

        except (aiohttp.ClientError, Exception) as e:
            # Handle exceptions appropriately for your logging/error handling
            print(f"Error fetching order book: {e}")
            return order_book

    async def get_ob_async(self, aiohttp_session: aiohttp.ClientSession):
        """Fetch order books for both directions with aiohttp"""
        tasks = [
            self.get_order_book_async(aiohttp_session, direction=PolyDirection.YES),
            self.get_order_book_async(aiohttp_session, direction=PolyDirection.NO),
        ]

        return await asyncio.gather(*tasks)


if __name__ == "__main__":
    spaceX_1T_ipo = PolyMarket()
    spaceX_1T_ipo.slug = "spacex-ipo-closing-market-cap-above-1t-274-469"
    spaceX_1T_ipo.get_market()
    print(spaceX_1T_ipo.market)
