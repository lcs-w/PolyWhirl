import requests
from typing import List, Dict

from PolyMarket import PolyMarket
from PolyAPI import POLY_GAMMA_API_URL


def list_event() -> Dict:
    try:
        response = requests.get(f"{POLY_GAMMA_API_URL}/events")
        if response.status_code == 200:
            return response.json()
    except requests.RequestException:
        return {}


class PolyEvent:
    """Get an event from Polymarket with an id."""

    def __init__(
        self,
    ):
        self._slug = None
        self.event = {}
        self.markets: List[PolyMarket] = []

    @property
    def event_url(self):
        return f"{POLY_GAMMA_API_URL}/events/slug/{self._slug}"

    @property
    def slug(self):
        return self._slug

    @slug.setter
    def slug(self, slug_str: str):
        self._slug = slug_str

    def get_event(self, include_chat: bool = False) -> dict:
        try:
            response = requests.get(
                f"{self.event_url}?include_chat={str(include_chat).lower()}"
            )
            if response.status_code == 200:
                # update self.event
                self.event = response.json()
                # update markets
                for m in self.event["markets"]:
                    self.markets.append(PolyMarket(market=m))
                return self.event

        except requests.RequestException:
            return {}


if __name__ == "__main__":
    spaceX_ipo_cap = PolyEvent()
    spaceX_ipo_cap.slug = "spacex-ipo-closing-market-cap-above"
    spaceX_ipo_cap.get_event()
    for m in spaceX_ipo_cap.markets:
        print(m.market["slug"])
