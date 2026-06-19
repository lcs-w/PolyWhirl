from src.PolyMarket import PolyMarket
from src.PolyOrderBook import PolyOrderBook


class OrderBookSignal:
    """OrderBookSignal detect signals from a snapshot of an order book at an arbitrary moment.

    possible signals:
    1. Micro-Price and Mid-Price Asymmetry
    2. Order Book Imbalance (OBI): directional supply/demand mismatch across different depths of the book
    3. Book slope (elasticity) and bid-ask spread convexity
    4.  "Walls" - Large Order Detection (Clustering)
    5. Market impact simulation
    """

    def __init__(self):
        pass
