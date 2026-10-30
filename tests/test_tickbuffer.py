import math

import numpy as np
import pytest

from feature import COLUMNS, TickBuffer, tick_from_order_book
from src.PolyOrderBook import PolyOrderBook


def make_ticks(n, seed=0):
    rng = np.random.default_rng(seed)
    mid = np.clip(0.5 + np.cumsum(rng.choice([-0.01, 0.0, 0.01], n)), 0.01, 0.99)
    spread = rng.choice([0.01, 0.02, 0.03], n)
    imbalance = rng.uniform(-1, 1, n)
    timestamp = 1_781_891_317_670 + np.arange(n, dtype=np.int64) * 250
    volume = rng.uniform(0, 100, n)
    return mid, spread, imbalance, timestamp, volume


@pytest.fixture
def wrapped():
    """A buffer that has wrapped around: 25 ticks pushed into capacity 10."""
    ticks = make_ticks(25)
    buf = TickBuffer(10)
    buf.extend(*ticks)
    return buf, [col[-10:] for col in ticks]


# reference implementations


def ref_zscore_series(x, window):
    out = np.full(len(x), np.nan)
    for i in range(window - 1, len(x)):
        w = x[i - window + 1 : i + 1]
        sd = w.std(ddof=1)
        out[i] = (x[i] - w.mean()) / sd if sd > 1e-9 else 0.0
    return out


def ref_ewma_series(x, alpha):
    out = np.empty(len(x))
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = alpha * x[i] + (1 - alpha) * out[i - 1]
    return out


# ring buffer


def test_capacity_must_be_positive():
    with pytest.raises(ValueError):
        TickBuffer(0)


def test_fills_then_wraps_keeping_newest_oldest_first(wrapped):
    buf, (mid, spread, imbalance, timestamp, volume) = wrapped
    assert len(buf) == 10 and buf.full and buf.capacity == 10
    np.testing.assert_array_equal(buf.mids(), mid)
    np.testing.assert_array_equal(buf.spreads(), spread)
    np.testing.assert_array_equal(buf.imbalances(), imbalance)
    np.testing.assert_array_equal(buf.timestamps(), timestamp)
    np.testing.assert_array_equal(buf.volumes(), volume)


def test_partial_buffer_before_wrap():
    buf = TickBuffer(10)
    for i in range(3):
        buf.push(0.5 + i / 100, 0.01, 0.0, i)
    assert len(buf) == 3 and not buf.full
    np.testing.assert_array_equal(buf.timestamps(), [0, 1, 2])


def test_getitem_supports_negative_index_and_bounds(wrapped):
    buf, (mid, spread, imbalance, timestamp, volume) = wrapped
    assert buf[0] == (mid[0], spread[0], imbalance[0], timestamp[0], volume[0])
    assert buf[-1] == buf[9]
    with pytest.raises(IndexError):
        buf[10]
    with pytest.raises(IndexError):
        buf[-11]


def test_clear():
    buf = TickBuffer(3)
    buf.push(0.5, 0.01, 0.0, 1)
    buf.clear()
    assert len(buf) == 0
    assert buf.mids().shape == (0,)
    assert buf.to_numpy().shape == (0, 5)


def test_extend_rejects_mismatched_lengths():
    buf = TickBuffer(5)
    with pytest.raises(ValueError):
        buf.extend([0.5, 0.6], [0.01], [0.0, 0.0], [1, 2])
    with pytest.raises(ValueError):
        buf.extend([0.5], [0.01], [0.0], [1], volume=[1.0, 2.0])


# numpy export


def test_to_numpy_matches_columns(wrapped):
    buf, cols = wrapped
    arr = buf.to_numpy()
    assert COLUMNS == ("mid", "spread", "imbalance", "timestamp", "volume")
    assert arr.shape == (10, 5) and arr.dtype == np.float64
    for j, col in enumerate(cols):
        np.testing.assert_array_equal(arr[:, j], np.asarray(col, dtype=np.float64))


def test_exported_arrays_are_copies(wrapped):
    buf, _ = wrapped
    mids = buf.mids()
    mids[:] = -1
    assert buf.mids()[0] != -1


def test_timestamps_are_int64(wrapped):
    buf, _ = wrapped
    assert buf.timestamps().dtype == np.int64


# features


def test_vwap(wrapped):
    buf, (mid, _, _, _, volume) = wrapped
    for n in (1, 5, 10, 50):
        k = min(n, 10)
        expected = np.average(mid[-k:], weights=volume[-k:])
        assert buf.vwap(n) == pytest.approx(expected)


def test_vwap_without_volume_is_nan():
    buf = TickBuffer(5)
    buf.push(0.5, 0.01, 0.0, 1)
    assert math.isnan(buf.vwap(5))
    assert math.isnan(TickBuffer(5).vwap(5))


@pytest.mark.parametrize("window", [2, 5, 10])
def test_mid_zscore_matches_reference(wrapped, window):
    buf, (mid, *_) = wrapped
    expected = ref_zscore_series(mid, window)
    np.testing.assert_allclose(buf.mid_zscore_series(window), expected, atol=1e-9)
    assert buf.mid_zscore(window) == pytest.approx(expected[-1], abs=1e-9)


def test_mid_zscore_nan_until_window_filled():
    buf = TickBuffer(10)
    buf.extend(*make_ticks(3)[:4])
    assert math.isnan(buf.mid_zscore(5))
    assert np.isnan(buf.mid_zscore_series(5)).all()


def test_mid_zscore_flat_window_is_zero():
    buf = TickBuffer(20)
    for i in range(20):
        buf.push(0.5 if i < 5 else 0.51, 0.01, 0.0, i)
    assert buf.mid_zscore(10) == 0.0
    assert buf.mid_zscore_series(10)[-1] == 0.0


def test_mid_zscore_rejects_small_window(wrapped):
    buf, _ = wrapped
    with pytest.raises(ValueError):
        buf.mid_zscore(1)


@pytest.mark.parametrize("alpha", [0.05, 0.3, 1.0])
def test_imbalance_ewma_matches_reference(wrapped, alpha):
    buf, (_, _, imbalance, _, _) = wrapped
    expected = ref_ewma_series(imbalance, alpha)
    np.testing.assert_allclose(buf.imbalance_ewma_series(alpha), expected)
    assert buf.imbalance_ewma(alpha) == pytest.approx(expected[-1])


@pytest.mark.parametrize("alpha", [0.0, -0.1, 1.5, float("nan")])
def test_imbalance_ewma_rejects_bad_alpha(wrapped, alpha):
    buf, _ = wrapped
    with pytest.raises(ValueError):
        buf.imbalance_ewma(alpha)


# order book adapter


def test_tick_from_order_book():
    ob = PolyOrderBook()
    ob.order_book = {
        "timestamp": "1781891317670",
        "bids": [{"price": "0.48", "size": "300"}, {"price": "0.47", "size": "50"}],
        "asks": [{"price": "0.52", "size": "100"}, {"price": "0.53", "size": "80"}],
    }
    mid, spread, imbalance, ts = tick_from_order_book(ob)
    assert mid == pytest.approx(0.50)
    assert spread == pytest.approx(0.04)
    assert imbalance == pytest.approx(0.5)
    assert ts == 1781891317670

    buf = TickBuffer(4)
    buf.push(mid, spread, imbalance, ts)
    assert buf[0][:4] == pytest.approx((mid, spread, imbalance, ts))


def test_tick_from_one_sided_book_is_none():
    ob = PolyOrderBook()
    ob.order_book = {"timestamp": "1", "bids": [{"price": "0.4", "size": "1"}], "asks": []}
    assert tick_from_order_book(ob) is None
