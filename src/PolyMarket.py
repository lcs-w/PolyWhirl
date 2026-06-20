import ast
import aiohttp
import asyncio
from typing import Dict, List
import requests

from src.PolyAPI import POLY_GAMMA_API_URL, POLY_CLOB_API_URL
from src.PolyOrderBook import PolyOrderBook
from src.PolyDirection import PolyDirection
from src.PolyTokenEssence import PolyTokenEssence


class PolyMarket:
    def __init__(self, market: Dict = None, slug: str = None):
        self._market = market
        self._slug = slug
        self._token_ids: Dict = {}

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

    @property
    def token_ids(self):
        return self._token_ids

    @token_ids.setter
    def token_ids(self, token_ids: Dict):
        self._token_ids = token_ids

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
                self.token_ids = {
                    str(PolyDirection.YES): self.market["clobTokenIds"][0],
                    str(PolyDirection.NO): self.market["clobTokenIds"][1],
                }
                return self.market
        except requests.RequestException:
            return {}

    def get_order_book(
        self,
        requests_session: requests.Session,
        direction: PolyDirection = PolyDirection.YES,
    ) -> PolyOrderBook:
        """Fetch order book for the provided direction with aiohttp. Default to be Yes."""
        token_id = self.token_ids[str(direction)]

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
        token_id = self.token_ids[str(direction)]

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

    def get_token_essence_pair(self) -> List[PolyTokenEssence]:
        """return a pair of token essence objects for both directions"""
        return [
            PolyTokenEssence(self.token_ids["Yes"], self.slug, PolyDirection.YES),
            PolyTokenEssence(self.token_ids["No"], self.slug, PolyDirection.NO),
        ]
