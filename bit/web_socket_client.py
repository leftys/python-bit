from typing import List, Optional

import asyncio
import collections
import logging
import uuid
import time

import ujson
import websockets.exceptions

from bit.util import *
from bit.reconnecting_websocket import ReconnectingWebsocket
from bit.exceptions import BitAPIException, SubscribeException
from bit.rest_client import BitClient



class WebSocketClient:
    def __init__(self, api_key, api_secret):
        self.loop = asyncio.get_event_loop()
        self.ws = ReconnectingWebsocket(
            loop=self.loop,
            path='',
            coro=self.on_message,
            # TODO port reconnecting logic from python-ascendex version
            reconnect_auth_coro = self._on_reconnect,
        )
        self.subscribers = {}
        self.intervals = {}

        self.key = api_key
        self.secret = api_secret
        self._token = ''

    # @staticmethod
    # def utc_timestamp():
    #     tm = time.time()
    #     return int(tm * 1e3)

    async def _get_ws_token(self):
        restClient = BitClient(self.key, self.secret)
        ret = await restClient.spot_ws_auth()
        return ret["data"]["token"]

    # def make_user_trade_req(token):
    #     return {
    #         "type": "subscribe",
    #         "channels": ["user_trade"],
    #         "currencies": ["BTC"],
    #         "categories": ["future", "option"],
    #         "interval": "raw",
    #         "token": token,
    #     }


    # def make_user_order_req(token):
    #     return {
    #         "type": "subscribe",
    #         "channels": ["order"],
    #         "pairs": ["BTC-USD", "ETH-USD"],
    #         "categories": ["future", "option"],
    #         "interval": "raw",
    #         "token": token,
    #     }


    # def make_umaccount_req(token):
    #     return {
    #         "type": "subscribe",
    #         "channels": ["um_account"],
    #         "interval": "100ms",
    #         "token": token,
    #     }

    async def _on_reconnect(self):
        await self.start()
        # Resubscribe
        for channel, ids in self.subscribers.items():
            # Assume all intervals are same for all ids/pairs in channel
            await self._send_subscribe(ids, [channel], self.intervals[channel][ids[0]])

    async def _send_subscribe(self, symbols, channels, interval, unsubscribe=False):
        # if self.ws.connected.is_set():
        msg_type = "unsubscribe" if unsubscribe else "subscribe"
        msg = {
            "type": msg_type,
            "channels": channels,
            "token": self._token,
        }
        if symbols:
            msg["pairs"] = symbols
        if interval:
            msg["interval"] = interval
        await self.ws.send(ujson.dumps(msg))

    async def subscribe(self, *, coro, channels: List[str], pairs: List[str], interval: Optional[str] = ''):
        """
        Subscribe data. Only one subscriber is allowed per channel-id combination!
        :param coro: callback coroutine accepting channel, id and data parameters
        :param channel:  subscribe channel: order, trades, and so on
        :param id: symbol or account id, depending on channel
        :return:
        """
        if not pairs:
            pairs = ['']
        for ch in channels:
            channel_data = self.subscribers.setdefault(ch, dict())
            for p in pairs:
                subscribers = channel_data.setdefault(p, set())
                subscribers.add(coro)
                self.intervals[ch][p] = interval
        await self._send_subscribe(pairs, channels, interval)

    async def unsubscribe(self, channel, id_):
        """unsubscribe a symbol/account from channel"""
        await self._send_subscribe([id_], [channel], None, unsubscribe = True)
        # Clear the defaultdict
        del self.subscribers[channel][id_]
        del self.intervals[channel][id_]
        if not self.subscribers[channel]:
            del self.subscribers[channel]
            del self.intervals[channel]

    async def ping(self):
        """ping pong to keep connection live"""
        # if self.ws.connected.is_set():
        msg = ujson.dumps({"type": "ping"})
        await self.ws.send(msg)

    async def on_message(self, message):
        """
        callback fired when a complete WebSocket message was received.
        You usually need to override this method to consume the data.

        :param dict message: message dictionary.
        """
        topic = get_message_topic(message)

        if topic == 'pong':
            # Ignore pong replies
            return
        if topic == 'subscription':
            if message['data']['code'] != 0:
                raise SubscribeException(message['data']['code'], message['data']['message'])
            return

        if "data" in message:
            data = message["data"]

            if 'pair' in data:
                pair = data['pair']
            else:
                pair = ''
            try:
                subscribers = self.subscribers[topic][pair]
            except KeyError:
                logging.info(f'no subscribers {message}')
            else:
                for subscriber in subscribers:
                    await subscriber(topic, pair, data)
        else:
            logging.warning(f"unhandled message {message}")

    async def start(self):
        self._token = await self._get_ws_token()

    async def close(self):
        # TODO more graceful cancel
        await self.ws.cancel()
