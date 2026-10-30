from collections import deque
from dataclasses import dataclass
import bisect

from src.PolyDirection import PolyDirection


@dataclass(frozen=True)
class Trade:
    """A trade normalized into YES-space."""

    timestamp: int  # ms
    price: float  # YES-equivalent price
    size: float  # shares
    sign: int  # +1 = aggressive YES buy, -1 = aggressive YES sell

    @classmethod
    def from_ws(cls, msg: dict, direction: PolyDirection) -> "Trade":
        """Build from a `last_trade_price` websocket message."""
        price, sign = float(msg["price"]), 1 if msg["side"] == "BUY" else -1
        if not direction:  # NO token: buying NO == selling YES at 1 - p
            price, sign = 1.0 - price, -sign
        return cls(int(msg["timestamp"]), price, float(msg["size"]), sign)


@dataclass
class Bucket:
    buy: float = 0.0
    sell: float = 0.0
    start_ts: int = 0
    end_ts: int = 0

    @property
    def volume(self) -> float:
        return self.buy + self.sell

    @property
    def imbalance(self) -> float:
        return self.buy - self.sell


class VPIN:
    """Volume-synchronized probability of informed trading for one market."""

    def __init__(
        self,
        bucket_volume: float,
        n_buckets: int = 50,
        max_bucket_ms: int | None = None,
        cdf_window: int = 1000,
    ):
        self.bucket_volume = bucket_volume
        self.n_buckets = n_buckets
        self.max_bucket_ms = max_bucket_ms
        self.buckets: deque[Bucket] = deque(maxlen=n_buckets)
        self._current = Bucket()
        self._history: deque[float] = deque(maxlen=cdf_window)
        self._sorted: list[float] = []

    def update(self, trade: Trade) -> list[Bucket]:
        """Add a trade, splitting it across buckets if needed. Returns closed buckets."""
        closed = []
        if self._stale(trade.timestamp):
            closed.append(self._close(trade.timestamp))
        remaining = trade.size
        while remaining > 0:
            if self._current.volume == 0:
                self._current.start_ts = trade.timestamp
            fill = min(remaining, self.bucket_volume - self._current.volume)
            if trade.sign > 0:
                self._current.buy += fill
            else:
                self._current.sell += fill
            remaining -= fill
            if self._current.volume >= self.bucket_volume:
                closed.append(self._close(trade.timestamp))
        return closed

    def _stale(self, ts: int) -> bool:
        return (
            self.max_bucket_ms is not None
            and self._current.volume > 0
            and ts - self._current.start_ts > self.max_bucket_ms
        )

    def _close(self, ts: int) -> Bucket:
        bucket, self._current = self._current, Bucket()
        bucket.end_ts = ts
        self.buckets.append(bucket)
        if self.ready:
            self._record(self.value)
        return bucket

    def _record(self, v: float):
        if len(self._history) == self._history.maxlen:
            self._sorted.pop(bisect.bisect_left(self._sorted, self._history[0]))
        self._history.append(v)
        bisect.insort(self._sorted, v)

    @property
    def ready(self) -> bool:
        return len(self.buckets) == self.n_buckets

    @property
    def value(self) -> float:
        """Classic VPIN in [0, 1]: magnitude of one-sided flow."""
        total = sum(b.volume for b in self.buckets)
        return sum(abs(b.imbalance) for b in self.buckets) / total if total else 0.0

    @property
    def signed(self) -> float:
        """Directional VPIN in [-1, 1]: + means informed flow is buying YES."""
        total = sum(b.volume for b in self.buckets)
        return sum(b.imbalance for b in self.buckets) / total if total else 0.0

    @property
    def cdf(self) -> float:
        """Percentile of the current VPIN within its rolling history."""
        if not self._sorted:
            return 0.0
        return bisect.bisect_right(self._sorted, self.value) / len(self._sorted)
