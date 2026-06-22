import asyncio
import aiohttp
import json
import datetime
import redis
from typing import List, Dict, Optional

from src.PolyAPI import POLY_WEBSOCKET_MARKET
from src.PolyMarket import PolyMarket
from src.PolyDirection import PolyDirection
from src.PolyTokenEssence import PolyTokenEssence


class PolyStreamer:
    """
    Stream Order Book with WebSocket to redis server
    """

    def __init__(self, token_essence: Optional[List[PolyTokenEssence]] = None):
        self._token_essence_dict: Dict = {}
        self.token_essence_list = token_essence if token_essence is not None else []

    @property
    def token_ids(self):
        return list(self._token_essence_dict.keys())

    @property
    def token_essence_list(self):
        return self._token_essence_list

    @token_essence_list.setter
    def token_essence_list(self, value: List[PolyTokenEssence]):
        self._token_essence_list = value
        self._token_essence_dict: Dict = {}
        for te in self._token_essence_list:
            self._token_essence_dict |= te.to_dict()

    @property
    def token_essence_dict(self):
        return self._token_essence_dict

    async def _heartbeat(self, ws: aiohttp.ClientWebSocketResponse):
        """Send PING every 10 seconds to keep the connection alive."""
        while True:
            await asyncio.sleep(10)
            await ws.send_str("PING")

    async def get_ob_ws(self, stream_to_redis: bool = True):

        r = None
        if stream_to_redis:
            # connect with Redis
            try:
                r = redis.asyncio.Redis(host="localhost", port=6379, db=0)
                print(await r.ping())
            except Exception as e:
                print(f"  Redis connection failed: {e}")

        # Fetch order book by subscribing to websocket
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(POLY_WEBSOCKET_MARKET) as ws:
                # Subscribe immediately after connecting
                subscription = {
                    "assets_ids": self.token_ids,
                    "type": "market",
                    "custom_feature_enabled": True,  # enables best_bid_ask, new_market, market_resolved
                }
                await ws.send_json(subscription)
                print("Subscribed to market channel")

                # Start heartbeat in background
                heartbeat_task = asyncio.create_task(self._heartbeat(ws))

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        if msg.data == "PONG":
                            print("Heartbeat OK")
                            continue
                        data = json.loads(msg.data)
                        # print(f"Received: {data}")
                        payload = data if isinstance(data, list) else [data]
                        if stream_to_redis and r is not None:
                            await self.stream_to_redis(r, payload)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        print(f"WebSocket error: {ws.exception()}")
                        break

                heartbeat_task.cancel()
                if r is not None:
                    await r.aclose()

    async def stream_to_redis(self, r: redis.asyncio.Redis, ws_data: List[Dict]):
        for m in ws_data:
            if (
                not m.get("asset_id")
                or m.get("asset_id") not in self.token_essence_dict
            ):
                continue  # skip messages without a known asset_id (e.g. book snapshots have nested structure)

            essence = self.token_essence_dict[m.get("asset_id")]
            await r.xadd(
                essence["market_slug"],
                {
                    "direction": essence["direction"],
                    "timestamp": str(m.get("timestamp", "")),
                    "event_type": str(m.get("event_type")),
                    "raw": str(m),
                },
            )


if __name__ == "__main__":
    from datetime import datetime
    import requests

    next_15m = int(((datetime.now().timestamp() // 300) + 1) * 300)

    pm = PolyMarket()
    pm.slug = f"btc-updown-5m-{next_15m}"
    print(pm.slug)

    # create a requests session
    with requests.Session() as requests_session:
        pm.get_market(requests_session)

    print(pm.token_ids)

    token_essence = pm.get_token_essence_pair()

    ps = PolyStreamer()
    ps.token_essence_list = token_essence
    # print(ps.token_ids)
    # print(ps.token_essence_list)
    # print(ps.token_essence_dict)

    asyncio.run(ps.get_ob_ws())
