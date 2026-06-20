from dataclasses import dataclass

from src.PolyDirection import PolyDirection


@dataclass
class PolyTokenEssence:
    """A custome dataclass which attaches token id with market slug and direction for more inituition."""

    token_id: str
    market_slug: str
    direction: PolyDirection

    def to_dict(self):
        return {
            self.token_id: {
                "market_slug": self.market_slug,
                "direction": int(bool(self.direction)),
            }
        }
