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

    def __init__(self, loop, path, coro, prefix=''):
        self._loop = loop
        self._log = logging.getLogger(__name__)
        self._path = path
        self._coro = coro
        self._prefix = prefix
        self._reconnects = 0
        self._conn = None
        self._ping_loop = None
        self._socket = None

        self._connect()

    def _connect(self):
        self._conn = asyncio.ensure_future(self._run(), loop=self._loop)
        self._ping_loop = asyncio.ensure_future(self._run_ping_loop(), loop=self._loop)
        self._conn.add_done_callback(self._handle_conn_done)

    async def _run(self):
        keep_waiting = True
        ws_url = self.STREAM_URL + self._prefix + self._path
        async with ws.connect(ws_url) as socket:
            self._socket = socket
            self._reconnects = 0
            self._messages_in_a_row = 0

            try:
                while keep_waiting:
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
                await self._reconnect()
            except asyncio.CancelledError:
                self._log.debug('ws connection cancelled')
                raise
            except Exception as e:
                self._log.warning('ws exception: %r', e)
                await self._reconnect()

    async def _run_ping_loop(self):
        await asyncio.sleep(self.TIMEOUT)
        while self._socket is not None:
            try:
                await self.send_ping()
            except ws.ConnectionClosed as ex:
                if self._socket is None and ex.code == 1000:
                    # Connection closed successfully
                    return
            except asyncio.CancelledError:
                raise
            except Exception as ex:
                if self._socket is not None:
                    self._log.error('Websocket ping failed')
            await asyncio.sleep(self.TIMEOUT)

    def _handle_conn_done(self, task: asyncio.Task):
        try:
            task.result()
        except asyncio.CancelledError:
            self._log.debug('ws connection cancelled')
        except Exception:
            self._log.exception('connection finished with exception')

    def _get_reconnect_wait(self, attempts: int) -> int:
        expo = 2 ** attempts
        return round(random() * min(self.MAX_RECONNECT_SECONDS, expo - 1) + 1)

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
        else:
            self._log.error('Max reconnections {} reached:'.format(self.MAX_RECONNECTS))

    async def send_ping(self):
        if self._socket:
            await self._socket.ping()

    async def cancel(self):
        if self._conn:
            self._log.debug('Cancelling conn')
            self._conn.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._conn
        self._socket = None
        if self._ping_loop:
            self._log.debug('Cancelling ping loop')
            self._ping_loop.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ping_loop
        self._log.debug('Done')
