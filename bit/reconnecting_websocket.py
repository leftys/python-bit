import asyncio
import contextlib
import ujson
import logging
from random import random
import websockets as ws


class ReconnectingWebsocket:

    # STREAM_URL = "wss://ws.bit.com"
    STREAM_URL = "wss://betaws.bitexch.dev"
    MAX_RECONNECTS = 5
    MAX_RECONNECT_SECONDS = 60
    MIN_RECONNECT_WAIT = 0.1
    TIMEOUT = 30

    def __init__(self, loop, path, coro, prefix='', reconnect_auth_coro = None):
        async def empty_coro():
            pass

        self._loop = loop
        self._log = logging.getLogger(__name__)
        self._path = path
        self._coro = coro
        self._prefix = prefix
        self._reconnect_auth_coro = reconnect_auth_coro or empty_coro
        self._reconnects = 0
        self._conn = None
        self._socket = None
        self.connected = asyncio.Event()

        self._connect()

    def _connect(self):
        self._conn = asyncio.ensure_future(self._run(), loop=self._loop)
        self._conn.add_done_callback(self._handle_conn_done)

    async def start(self):
        await self.connected.wait()

    async def _run(self):
        ws_url = self.STREAM_URL + self._prefix + self._path
        async with ws.connect(ws_url) as socket:
            self._socket = socket
            self._reconnects = 0
            self._messages_in_a_row = 0
            self.connected.set()

            try:
                while self.connected.is_set():
                    queue_len = len(self._socket.messages)
                    if queue_len == 0:
                        self._messages_in_a_row = 0
                    if queue_len > 10 and self._messages_in_a_row == 0:
                        self._log.info(
                            'Many messages just arrived, new = %d after = %d already processed on path = %s',
                            queue_len, self._messages_in_a_row, self._path
                        )

                    evt = await self._socket.recv()
                    self._messages_in_a_row += 1
                    try:
                        evt_obj = ujson.loads(evt)
                    except ValueError:
                        self._log.info('error parsing evt json:{}'.format(evt))
                    else:
                        await self._coro(evt_obj)

                    # Yield every now and then to let new tasks being processed
                    if queue_len > 1 and self._messages_in_a_row % 5 == 0:
                        await asyncio.sleep(0)
            except ws.ConnectionClosed as e:
                self._log.info('ws connection closed: %r', e)
                asyncio.create_task(self._reconnect())
            except asyncio.CancelledError:
                self._log.debug('ws connection cancelled')
                raise
            except Exception as e:
                self._log.warning('ws exception: %r', e)
                asyncio.create_task(self._reconnect())
        self.connected.clear()

    def _handle_conn_done(self, task: asyncio.Task):
        self.connected.clear()
        try:
            task.result()
        except asyncio.CancelledError:
            self._log.debug('ws connection cancelled')
        except Exception:
            self._log.exception('connection finished with exception')

    def _get_reconnect_wait(self, attempts: int) -> int:
        expo = 2 ** attempts
        return round(random() * min(self.MAX_RECONNECT_SECONDS, expo - 1))

    async def _reconnect(self):
        await self.cancel()
        self._reconnects += 1
        if self._reconnects < self.MAX_RECONNECTS:

            self._log.info("websocket {} reconnecting {} reconnects left".format(
                self._path, self.MAX_RECONNECTS - self._reconnects)
            )
            reconnect_wait = self._get_reconnect_wait(self._reconnects)
            await asyncio.sleep(reconnect_wait)
            self._connect()
            await self.connected.wait()
            await self._reconnect_auth_coro()
        else:
            self._log.error('Max reconnections {} reached:'.format(self.MAX_RECONNECTS))

    async def send(self, data):
        if not self.connected.is_set():
            self._log.warning('Trying to send data on closed socket')
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self.connected.wait(), timeout = 10)
        await self._socket.send(data)

    async def send_ping(self):
        if self._socket:
            await self._socket.ping()

    async def cancel(self):
        if self._conn:
            self._log.debug('Cancelling conn')
            self.connected.clear()
            self._conn.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._conn
        self._socket = None
        self._log.debug('Done')
