from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    from src.PolyOrderBook import PolyOrderBook


def tick_from_order_book(
    order_book: "PolyOrderBook",
) -> Optional[Tuple[float, float, float, int]]:
    """Reduce an order book to a (mid, spread, imbalance, timestamp) tick.

    Imbalance is top-of-book: (bid_size - ask_size) / (bid_size + ask_size), in [-1, 1].
    Returns None if either side of the book is empty.
    """
    bid, ask = order_book.bids_highest, order_book.asks_lowest
    if not bid or not ask:
        return None

    depth = bid["size"] + ask["size"]
    return (
        (bid["price"] + ask["price"]) / 2,
        ask["price"] - bid["price"],
        (bid["size"] - ask["size"]) / depth if depth > 0 else 0.0,
        order_book.timestamp,
    )
