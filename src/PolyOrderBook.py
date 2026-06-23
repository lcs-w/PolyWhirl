from typing import List, Dict
import polars as pl

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

        self.tick_size = float(value.get("tick_size", -1.0))

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

    def _create_price_size_df(
        self, price_size_dict: List[Dict], is_bid: bool
    ) -> pl.DataFrame:
        """
        Args:
            price_size_dict (List[Dict]): a list of dictionaries with price-size pairs
            bid (bool): True if they are bids, False if they are asks

        Returns:
            pl.DataFrame: a DataFrame with price as columns (0.01 to 0.99), size as value
        """
        df = pl.DataFrame(
            schema=pl.Struct(
                [pl.Field("timestamp", pl.Int64)]
                + [pl.Field("bid", pl.Boolean)]  # a boolean: 0 or 1
                + [pl.Field(f"{price/100}", pl.Float64) for price in range(1, 100, 1)],
            ),
        )
        row = (
            {"timestamp": None}
            | {"bid": is_bid}
            | {str(b["price"]): b["size"] for b in price_size_dict}
        )

        result = pl.concat([df, pl.DataFrame([row])], how="diagonal").fill_null(0)
        return result

    def get_all_bids(self) -> pl.DataFrame:
        """
        Returns:
            pl.DataFrame: returns all bids ordered from the highest
        """
        return self._create_price_size_df(self.bids, is_bid=True)

    def get_all_asks(self) -> pl.DataFrame:
        """
        Returns:
            pl.DataFrame: returns all bids ordered from the highest
        """
        return self._create_price_size_df(self.asks, is_bid=False)

    def __str__(self):
        if self._order_book:
            return f"PolyOrderBook(market_slug={self.market_slug}, direction={self.direction}, highest_bid={self.bids_highest}, lowest_ask={self.asks_lowest}, timestamp={self.timestamp})"
        else:
            return "PolyOrderBook(order_book is empty)"
