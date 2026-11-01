import math
import time

import pytest

from signal_detection.OrderBookSignal import OrderBookSignal
from signal_detection.VPIN import Trade
from src.PolyDirection import PolyDirection
from src.PolyOrderBook import PolyOrderBook


def make_book(
    ts: int,
    bids: list[tuple[float, float]],  # list of (price, size) pairs
    asks: list[tuple[float, float]],
    direction: PolyDirection = PolyDirection.YES,
) -> PolyOrderBook:
    ob = PolyOrderBook()
    ob.direction = direction
    ob.order_book = {
        "timestamp": str(ts),
        "bids": [{"price": str(p), "size": str(s)} for p, s in bids],
        "asks": [{"price": str(p), "size": str(s)} for p, s in asks],
    }
    return ob


def test_microprice_leans_toward_thin_side():
    # more bid size -> price more likely to tick up -> microprice above mid
    mp = OrderBookSignal.microprice(
        {"price": 0.48, "size": 300}, {"price": 0.52, "size": 100}
    )
    assert mp == pytest.approx(0.51)


def test_order_book_imbalance_weights_levels():
    sig = OrderBookSignal(decay=0.5)
    bids = [{"price": 0.48, "size": 100}, {"price": 0.47, "size": 100}]
    asks = [{"price": 0.52, "size": 100}, {"price": 0.53, "size": 300}]
    # bid depth 100 + 50 = 150, ask depth 100 + 150 = 250
    assert sig.order_book_imbalance(bids, asks) == pytest.approx(-100 / 400)
    assert sig.order_book_imbalance([], []) == 0.0


def test_on_book_returns_features_and_pushes_tick():
    sig = OrderBookSignal()
    f = sig.on_book(make_book(1000, [(0.48, 300)], [(0.52, 100)]))
    assert f.timestamp == 1000
    assert f.mid == pytest.approx(0.50)
    assert f.microprice == pytest.approx(0.51)
    assert f.obi == pytest.approx(0.5)
    assert f.obi_ewma == pytest.approx(0.5)
    assert math.isnan(f.mid_z)  # window not filled yet
    assert math.isnan(f.vwap_gap)  # no trades yet
    assert len(sig.buffer) == 1


@pytest.mark.parametrize(
    "book",
    [
        make_book(2000, [(0.48, 1)], [(0.52, 1)], direction=PolyDirection.NO),
        make_book(1000, [(0.48, 1)], [(0.52, 1)]),  # same timestamp as the first book
        make_book(500, [(0.48, 1)], [(0.52, 1)]),  # out of order
        make_book(3000, [(0.48, 1)], []),  # one-sided
    ],
)
def test_on_book_skips_ignored_books(book):
    sig = OrderBookSignal()
    sig.on_book(make_book(1000, [(0.48, 1)], [(0.52, 1)]))
    assert sig.on_book(book) is None
    assert len(sig.buffer) == 1


def test_trades_become_volume_of_next_tick():
    sig = OrderBookSignal()
    sig.on_book(make_book(1000, [(0.48, 1)], [(0.52, 1)]))
    sig.on_trade(Trade(1100, 0.52, 20.0, 1))
    sig.on_trade(Trade(1200, 0.52, 5.0, 1))
    f = sig.on_book(make_book(1300, [(0.50, 1)], [(0.54, 1)]))
    assert sig.buffer.volumes().tolist() == [0.0, 25.0]
    assert f.vwap_gap == pytest.approx(0.0)  # only the latest tick has volume


def test_lag_ms_from_arrival_time():
    sig = OrderBookSignal()
    f = sig.on_book(make_book(1000, [(0.48, 1)], [(0.52, 1)]), arrival_ms=1250)
    assert f.lag_ms == 250


def test_lag_ms_defaults_to_now():
    sig = OrderBookSignal()
    exchange_ms = time.time_ns() // 1_000_000 - 100
    f = sig.on_book(make_book(exchange_ms, [(0.48, 1)], [(0.52, 1)]))
    assert 100 <= f.lag_ms < 5_000


def test_mid_zscore_after_window_fills():
    sig = OrderBookSignal(z_window=3)
    features = [
        sig.on_book(make_book(ts, [(bid, 1)], [(bid + 0.02, 1)]))
        for ts, bid in [(1, 0.40), (2, 0.41), (3, 0.42)]
    ]
    assert features[-1].mid_z == pytest.approx(1.0)
