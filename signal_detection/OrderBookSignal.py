import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from feature import TickBuffer
from signal_detection.VPIN import Trade
from src.PolyDirection import PolyDirection
from src.PolyOrderBook import PolyOrderBook

# possible signals:
# 1. Micro-Price and Mid-Price Asymmetry
# 2. Order Book Imbalance (OBI): directional supply/demand mismatch across different depths of the book
# 3. Book slope (elasticity) and bid-ask spread convexity
# 4. "Walls" - Large Order Detection (Clustering)
# 5. Market impact simulation


@dataclass(frozen=True)
class OrderBookFeatures:
    timestamp: int
    mid: float
    microprice: float
    obi: float  # depth-weighted imbalance over the top levels, in [-1, 1]
    mid_z: float  # z-score of mid vs. recent mids; NaN until the window fills
    obi_ewma: float  # smoothed obi
    vwap_gap: float  # mid - volume-weighted mid; NaN until trades arrive
    lag_ms: int  # arrival_ms - exchange timestamp; includes local clock skew


class OrderBookSignal:
    """OrderBookSignal turns a stream of order books for one market into features.

    Snapshot features (micro-price, OBI) are computed per book; their history is kept
    in a C++ TickBuffer, which supplies the time-series features (mid z-score, OBI EWMA,
    VWAP) and numpy export for ML.

    Feed it YES-token books only: Polymarket's NO book mirrors the YES book exactly, so
    NO books are ignored rather than double counted.
    """

    def __init__(
        self,
        capacity: int = 2_000,
        depth: int = 5,
        decay: float = 0.5,
        z_window: int = 100,
        alpha: float = 0.1,
        vwap_n: int = 200,
    ):
        """
        Args:
            capacity (int): number of ticks kept in the buffer
            depth (int): number of price levels per side used for OBI
            decay (float): weight of level i is decay**i, so level 0 (best price) weighs most
            z_window (int): ticks in the mid z-score window
            alpha (float): EWMA smoothing factor for OBI, in (0, 1]
            vwap_n (int): ticks in the VWAP window
        """
        self.buffer = TickBuffer(capacity)
        self.depth = depth
        self.decay = decay
        self.z_window = z_window
        self.alpha = alpha
        self.vwap_n = vwap_n

        self._pending_volume: float = 0.0  # traded size since the last book tick
        self._last_ts: int = -1

    @staticmethod
    def microprice(best_bid: Dict, best_ask: Dict) -> float:
        """Size-weighted mid: leans toward the side with less resting size, i.e. where price is likely to move."""
        bid_size, ask_size = best_bid["size"], best_ask["size"]
        if bid_size + ask_size <= 0:
            return (best_bid["price"] + best_ask["price"]) / 2
        return (best_bid["price"] * ask_size + best_ask["price"] * bid_size) / (
            bid_size + ask_size
        )

    def order_book_imbalance(self, bids: List[Dict], asks: List[Dict]) -> float:
        """Depth-weighted (bid - ask) / (bid + ask) over the given levels, in [-1, 1]."""
        bid_depth = sum(b["size"] * self.decay**i for i, b in enumerate(bids))
        ask_depth = sum(a["size"] * self.decay**i for i, a in enumerate(asks))
        total = bid_depth + ask_depth
        return (bid_depth - ask_depth) / total if total > 0 else 0.0

    def on_trade(self, trade: Trade) -> None:
        """Accumulate traded size; it is attached to the next book tick as its volume."""
        self._pending_volume += trade.size

    def on_book(
        self, order_book: PolyOrderBook, arrival_ms: Optional[int] = None
    ) -> Optional[OrderBookFeatures]:
        """Push a YES-token book into the buffer and return its features.

        Args:
            order_book (PolyOrderBook): the book to process
            arrival_ms (int, optional): when the book reached this machine, in ms since
                the epoch, e.g. the Redis stream entry ID. Defaults to now.

        Returns None for NO-token books, out-of-order books, and one-sided books.
        """
        if arrival_ms is None:
            arrival_ms = time.time_ns() // 1_000_000

        if (
            order_book.direction is not PolyDirection.YES
            or order_book.timestamp <= self._last_ts
        ):
            return None

        bids, asks = order_book.bids[: self.depth], order_book.asks[: self.depth]
        if not bids or not asks:
            return None

        mid = (bids[0]["price"] + asks[0]["price"]) / 2
        obi = self.order_book_imbalance(bids, asks)
        self.buffer.push(
            mid,
            asks[0]["price"] - bids[0]["price"],
            obi,
            order_book.timestamp,
            volume=self._pending_volume,
        )
        self._pending_volume = 0.0
        self._last_ts = order_book.timestamp

        return OrderBookFeatures(
            timestamp=order_book.timestamp,
            mid=mid,
            microprice=self.microprice(bids[0], asks[0]),
            obi=obi,
            mid_z=self.buffer.mid_zscore(self.z_window),
            obi_ewma=self.buffer.imbalance_ewma(self.alpha),
            vwap_gap=mid - self.buffer.vwap(self.vwap_n),
            lag_ms=arrival_ms - order_book.timestamp,
        )
