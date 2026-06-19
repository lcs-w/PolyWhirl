from typing import List, Dict
import ast

from src.PolyDirection import PolyDirection


class PolyOrderBook:
    def __init__(self):
        self._order_book: Dict = {}

        self.market_id: str = ""
        self._market_slug: str = ""
        self.token_id: str = ""
        self.timestamp: int = 0
        self._direction: PolyDirection = PolyDirection.YES

        self.bids: List[Dict] = []
        self.bids_highest: Dict = {}

        self.asks: List[Dict] = []
        self.asks_lowest: Dict = {}

    @property
    def order_book(self) -> Dict:
        return self._order_book

    @order_book.setter
    def order_book(self, value: Dict):
        self._order_book = value

        self.market_id = value.get("market", "")
        self.token_id = value.get("asset_id", "")
        self.timestamp = int(value.get("timestamp", 0))

        self.bids = sorted(
            [
                {
                    **entry,
                    "price": float(entry.get("price", 0)),
                    "size": float(entry.get("size", 0)),
                }
                for entry in value.get("bids", [])
            ],
            key=lambda entry: entry["price"],
            reverse=True,
        )
        self.bids_highest = self.bids[0] if self.bids else {}

        self.asks = sorted(
            [
                {
                    **entry,
                    "price": float(entry.get("price", 0)),
                    "size": float(entry.get("size", 0)),
                }
                for entry in value.get("asks", [])
            ],
            key=lambda entry: entry["price"],
        )
        self.asks_lowest = self.asks[0] if self.asks else {}

    @property
    def market_slug(self) -> str:
        return self._market_slug

    @market_slug.setter
    def market_slug(self, value: str):
        self._market_slug = value

    @property
    def direction(self) -> PolyDirection:
        return self._direction

    @direction.setter
    def direction(self, value: PolyDirection):
        self._direction = value

    def __str__(self):
        if self._order_book:
            return f"PolyOrderBook(market_slug={self.market_slug}, direction={self.direction}, highest_bid={self.bids_highest}, lowest_ask={self.asks_lowest}, timestamp={self.timestamp})"
        else:
            return "PolyOrderBook(order_book is empty)"
