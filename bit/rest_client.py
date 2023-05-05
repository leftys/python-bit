# A reference demo bit.com API client including (SPOT, COIN-M, USDT-M)
# feel free to copy and modify to suit your need
#
# API request/response format
# https://www.bit.com/docs/en-us/spot.html#order
#
# Guidelines for account mode
# https://www.bit.com/docs/en-us/spot.html#guidelines-for-account-mode
#
# API Host:
# https://www.bit.com/docs/en-us/spot.html#spot-api-hosts-production

import aiosonic
import hashlib
import hmac
import time
import ujson

from bit.exceptions import BitAPIException

class HttpMethod:
	GET = 'GET'
	POST = 'POST'
	PUT = 'PUT'
	DELETE = 'DELETE'
	HEAD = 'HEAD'


# SPOT
V1_SPOT_INSTRUMENTS = '/spot/v1/instruments'
V1_SPOT_ACCOUNTS = '/spot/v1/accounts'
V1_SPOT_ORDERS = '/spot/v1/orders'
V1_SPOT_CANCEL_ORDERS = '/spot/v1/cancel_orders'
V1_SPOT_OPENORDERS = '/spot/v1/open_orders'
V1_SPOT_USER_TRADES = '/spot/v1/user/trades'
V1_SPOT_AMEND_ORDERS = '/spot/v1/amend_orders'
V1_SPOT_TRANSACTION_LOGS = '/spot/v1/transactions'
V1_SPOT_WS_AUTH = '/spot/v1/ws/auth'
V1_SPOT_BATCH_ORDERS = '/spot/v1/batchorders'
V1_SPOT_AMEND_BATCH_ORDERS = '/spot/v1/amend_batchorders'
V1_SPOT_MMP_STATE = '/spot/v1/mmp_state'
V1_SPOT_MMP_UPDATE_CONFIG = '/spot/v1/update_mmp_config'
V1_SPOT_RESET_MMP = '/spot/v1/reset_mmp'
V1_SPOT_ACCOUNT_CONFIGS_COD = '/spot/v1/account_configs/cod'
V1_SPOT_ACCOUNT_CONFIGS = "/spot/v1/account_configs"


# UM
V1_UM_ACCOUNT_MODE = "/um/v1/account_mode"
V1_UM_ACCOUNTS = "/um/v1/accounts"
V1_UM_TRANSACTIONS = "/um/v1/transactions"
V1_UM_INTEREST_RECORDS = "/um/v1/interest_records"

# LINEAR
V1_LINEAR_POSITIONS = '/linear/v1/positions'
V1_LINEAR_ORDERS = '/linear/v1/orders'
V1_LINEAR_CANCEL_ORDERS = '/linear/v1/cancel_orders'
V1_LINEAR_OPENORDERS = '/linear/v1/open_orders'
V1_LINEAR_USER_TRADES = '/linear/v1/user/trades'
V1_LINEAR_AMEND_ORDERS = '/linear/v1/amend_orders'
V1_LINEAR_EST_MARGINS = '/linear/v1/margins'
V1_LINEAR_CLOSE_POS = '/linear/v1/close_positions'
V1_LINEAR_BATCH_ORDERS = '/linear/v1/batchorders'
V1_LINEAR_AMEND_BATCH_ORDERS = '/linear/v1/amend_batchorders'
V1_LINEAR_BLOCK_TRADES = '/linear/v1/blocktrades'
V1_LINEAR_USER_INFO = '/linear/v1/user/info'
V1_LINEAR_PLATFORM_BLOCK_TRADES = '/linear/v1/platform_blocktrades'
V1_LINEAR_ACCOUNT_CONFIGS = "/linear/v1/account_configs"
V1_LINEAR_LEVERAGE_RATIO = "/linear/v1/leverage_ratio"

class BitClient(object):
    # API_URL = "https://api.bit.com"
	API_URL = "https://betaapi.bitexch.dev"

	def __init__(self, ak, sk, base_url = API_URL, *, pool_size = 10, request_timeout = 30):
		self.access_key = ak
		self.secret_key = sk
		self.base_url = base_url
		self._pool_size = pool_size
		self.last_response_headers = {}
		self._timeouts = aiosonic.Timeouts(request_timeout = request_timeout)
		self.session = self._init_session()

	def _init_session(self) -> aiosonic.HTTPClient:
		session = aiosonic.HTTPClient(
			connector=aiosonic.TCPConnector(
				pool_size=self._pool_size,
				timeouts=self._timeouts,
			),
		)
		return session

	async def close(self):
		await self.session.shutdown()

	#############################
	# call private API
	#############################
	def _get_nonce(self):
		return str(int(round(time.time() * 1000)))

	def _encode_list(self, item_list):
		list_val = []
		for item in item_list:
			obj_val = self._encode_object(item)
			list_val.append(obj_val)
			print(list_val)
		# list_val = sorted(list_val)
		output = '&'.join(list_val)
		output = '[' + output + ']'
		return output

	def _encode_object(self, obj):
		if isinstance(obj, (str, int)):
			return obj

		# treat obj as dict
		sorted_keys = sorted(obj.keys())
		ret_list = []
		for key in sorted_keys:
			val = obj[key]
			if isinstance(val, list):
				list_val = self._encode_list(val)
				ret_list.append(f'{key}={list_val}')
			elif isinstance(val, dict):
				# call encode_object recursively
				dict_val = self._encode_object(val)
				ret_list.append(f'{key}={dict_val}')
			elif isinstance(val, bool):
				bool_val = str(val).lower()
				ret_list.append(f'{key}={bool_val}')
			else:
				general_val = str(val)
				ret_list.append(f'{key}={general_val}')

		sorted_list = sorted(ret_list)
		output = '&'.join(sorted_list)
		return output

	def _get_signature(self, http_method, api_path, param_map):
		str_to_sign = api_path + '&' + self._encode_object(param_map)
		sig = hmac.new(self.secret_key.encode('utf-8'), str_to_sign.encode('utf-8'),
					   digestmod=hashlib.sha256).hexdigest()
		return sig

	def _get_str(self, x):
		if isinstance(x, bool):
			return str(x).lower()
		else:
			return str(x)

	async def _call_private_api(self, path, method="GET", param_map=None):
		if param_map is None:
			param_map = {}

		nonce = self._get_nonce()
		param_map['timestamp'] = nonce

		sig = self._get_signature(
			http_method=method, api_path=path, param_map=param_map)
		param_map['signature'] = sig

		url = self.base_url + path

		js = None
		if method == HttpMethod.GET:
			query_string = '&'.join([f'{k}={self._get_str(v)}' for k, v in param_map.items()])
			url += '?' + query_string
		else:
			# js = ujson.loads(ujson.dumps(param_map))
			js = param_map
			js['timestamp'] = int(js['timestamp'])

		headers = {'X-Bit-Access-Key': self.access_key, 'language-type': '1'}

		# res = requests.request(method, url, headers=header, json=js)
		res = await self.session.request(
			url = url, method = method, headers = headers, params = js #, data = None
		)
		return await self._handle_response(url, js, res)
		# return await res.json()


	async def _handle_response(self, uri: str, params: str, response: aiosonic.HttpResponse):
		"""Internal helper for handling API responses from the Binance server.
		Raises the appropriate exceptions when necessary; otherwise, returns the
		response.
		"""
		if not str(response.status_code).startswith("2"):
			raise BitAPIException(uri, params, response, await response.text())
		self.last_response_headers = response.headers
		try:
			content = ujson.loads(await response.content())
		except ValueError:
			raise BitAPIException(uri, params, response, await response.text())
		except AttributeError:
			# weird aiosonic bug?
			# File "/home/ec2-user/bot/env/lib/python3.8/site-packages/aiosonic/__init__.py", line 263, in read_chunks
			# chunk_size = int((await self.connection.reader.readline()).rstrip(), 16)
			# AttributeError: 'NoneType' object has no attribute 'reader'
			raise BitAPIException(uri, params, response, 'Connection lost during _handle_response')

		if 'message' in content and 'reason' in content:
			raise BitAPIException(uri, params, response, content['reason'] + ': ' + content['message'])
		return content

	######################
	# SPOT endpoints
	######################
	async def spot_account_configs(self, req):
		return await self._call_private_api(V1_SPOT_ACCOUNT_CONFIGS, HttpMethod.GET, req)

	async def spot_query_accounts(self, params={}):
		return await self._call_private_api(V1_SPOT_ACCOUNTS, HttpMethod.GET, params)

	async def spot_query_transactions(self, params):
		return await self._call_private_api(V1_SPOT_TRANSACTION_LOGS, HttpMethod.GET, params)

	async def spot_query_orders(self, params):
		return await self._call_private_api(V1_SPOT_ORDERS, HttpMethod.GET, params)

	async def spot_query_open_orders(self, params):
		return await self._call_private_api(V1_SPOT_OPENORDERS, HttpMethod.GET, params)

	async def spot_query_trades(self, params):
		return await self._call_private_api(V1_SPOT_USER_TRADES, HttpMethod.GET, params)

	async def spot_place_order(self, order_req):
		return await self._call_private_api(V1_SPOT_ORDERS, HttpMethod.POST, order_req)

	async def spot_cancel_order(self, cancel_req):
		return await self._call_private_api(V1_SPOT_CANCEL_ORDERS, HttpMethod.POST, cancel_req)

	async def spot_amend_order(self, req):
		return await self._call_private_api(V1_SPOT_AMEND_ORDERS, HttpMethod.POST, req)

	async def spot_ws_auth(self):
		return await self._call_private_api(V1_SPOT_WS_AUTH, HttpMethod.GET)

	async def spot_new_batch_orders(self, req):
		return await self._call_private_api(V1_SPOT_BATCH_ORDERS, HttpMethod.POST, req)

	async def spot_amend_batch_orders(self, req):
		return await self._call_private_api(V1_SPOT_AMEND_BATCH_ORDERS, HttpMethod.POST, req)

	async def spot_query_mmp_state(self, req):
		return await self._call_private_api(V1_SPOT_MMP_STATE, HttpMethod.GET, req)

	async def spot_update_mmp_config(self, req):
		return await self._call_private_api(V1_SPOT_MMP_UPDATE_CONFIG, HttpMethod.POST, req)

	async def spot_reset_mmp(self, req):
		return await self._call_private_api(V1_SPOT_RESET_MMP, HttpMethod.POST, req)

	async def spot_enable_cod(self, req):
		return await self._call_private_api(V1_SPOT_ACCOUNT_CONFIGS_COD, HttpMethod.POST, req)

	######################
	# UM endpoints
	######################
	async def um_query_account_mode(self):
		return await self._call_private_api(V1_UM_ACCOUNT_MODE, HttpMethod.GET)

	async def um_query_accounts(self):
		return await self._call_private_api(V1_UM_ACCOUNTS, HttpMethod.GET)

	async def um_query_transactions(self, param):
		return await self._call_private_api(V1_UM_TRANSACTIONS, HttpMethod.GET, param)

	async def um_query_interest_records(self, param):
		return await self._call_private_api(V1_UM_INTEREST_RECORDS, HttpMethod.GET, param)

	######################
	# USD-M endpoints
	######################
	async def linear_account_configs(self, req):
		return await self._call_private_api(V1_LINEAR_ACCOUNT_CONFIGS, HttpMethod.GET, req)

	async def linear_query_positions(self, params):
		return await self._call_private_api(V1_LINEAR_POSITIONS, HttpMethod.GET, params)

	async def linear_query_orders(self, params):
		return await self._call_private_api(V1_LINEAR_ORDERS, HttpMethod.GET, params)

	async def linear_query_open_orders(self, params):
		return await self._call_private_api(V1_LINEAR_OPENORDERS, HttpMethod.GET, params)

	async def linear_query_trades(self, params):
		return await self._call_private_api(V1_LINEAR_USER_TRADES, HttpMethod.GET, params)

	async def linear_place_order(self, order_req):
		return await self._call_private_api(V1_LINEAR_ORDERS, HttpMethod.POST, order_req)

	async def linear_cancel_order(self, cancel_req):
		return await self._call_private_api(V1_LINEAR_CANCEL_ORDERS, HttpMethod.POST, cancel_req)

	async def linear_amend_order(self, req):
		return await self._call_private_api(V1_LINEAR_AMEND_ORDERS, HttpMethod.POST, req)

	async def linear_new_batch(self, req):
		return await self._call_private_api(V1_LINEAR_BATCH_ORDERS, HttpMethod.POST, req)

	async def linear_amend_batch(self, req):
		return await self._call_private_api(V1_LINEAR_AMEND_BATCH_ORDERS, HttpMethod.POST, req)

	async def linear_close_position(self, req):
		return await self._call_private_api(V1_LINEAR_CLOSE_POS, HttpMethod.POST, req)

	async def linear_estimated_margins(self, req):
		return await self._call_private_api(V1_LINEAR_EST_MARGINS, HttpMethod.GET, req)

	async def linear_query_leverage_ratio(self, params):
		return await self._call_private_api(V1_LINEAR_LEVERAGE_RATIO, HttpMethod.GET, params)

	async def linear_update_leverage_ratio(self, params):
		return await self._call_private_api(V1_LINEAR_LEVERAGE_RATIO, HttpMethod.POST, params)

	# usdx blocktrades
	async def linear_new_blocktrades(self, order_req):
		return await self._call_private_api(V1_LINEAR_BLOCK_TRADES, HttpMethod.POST, order_req)

	async def linear_query_blocktrades(self, req):
		return await self._call_private_api(V1_LINEAR_BLOCK_TRADES, HttpMethod.GET, req)

	async def linear_query_userinfo(self, req={}):
		return await self._call_private_api(V1_LINEAR_USER_INFO, HttpMethod.GET, req)

	async def linear_query_platform_blocktrades(self, req):
		return await self._call_private_api(V1_LINEAR_PLATFORM_BLOCK_TRADES, HttpMethod.GET, req)


if __name__ == '__main__':
	# api_host = "https://api.bit.com" # production

	api_host = "https://betaapi.bitexch.dev" # testnet
	ak = "<input_your_access_key>"
	sk = "<input_your_private_key>"
	client = BitClient(ak, sk, api_host)

	mode_resp = client.um_query_account_mode()
	mode = mode_resp['data']['account_mode']

	# get account information
	if mode == 'um':
		um_account = client.um_query_accounts()
		print(um_account)
	elif mode == 'classic':
		classic_account_btc = client.query_accounts({'currency':'BTC'})
		classic_account_eth = client.query_accounts({'currency':'ETH'})
		classic_account_bch = client.query_accounts({'currency':'BCH'})
		classic_account_spot = client.spot_query_accounts({})

		print('BTC account = ' + str(classic_account_btc))
		print('ETH account = ' + str(classic_account_eth))
		print('BCH account = ' + str(classic_account_bch))
		print('Spot account = ' + str(classic_account_spot))
	else:
		print('account in transient state: ' + mode)

	# query USD-M(linear) positions
	await client.linear_query_positions({
		'currency':'USD'
	})

	# place USD-M(linear) limit order
	await client.linear_place_order({
		'instrument_id': 'ETH-USD-PERPETUAL',
		'side':'buy',
		'qty':'0.05',
		'price': '1500',
		'order_type':'limit',
		'post_only': True
	})

	# place trigger limit order
	await client.linear_place_order({
		'instrument_id': 'BTC-USD-PERPETUAL',
		'side':'buy',
		'qty':'0.01',
		'order_type':'trigger-market',
		'time_in_force': 'gtc',
		'stop_price': '25800',
		'trigger_type': 'last-price'
	})

	# new batch orders
	await client.linear_new_batch({
		'currency': 'USD',
		'orders_data': [
			{'instrument_id': 'XRP-USD-PERPETUAL', 'side': 'buy', 'qty': '200', 'price': '0.371', 'order_type': 'limit', 'post_only': True},
			{'instrument_id': 'XRP-USD-PERPETUAL', 'side': 'buy', 'qty': '300', 'price': '0.36', 'order_type': 'limit', 'post_only': True},
			{'instrument_id': 'XRP-USD-PERPETUAL', 'side': 'buy', 'qty': '400', 'price': '0.37', 'order_type': 'limit', 'post_only': True}
		]
	})


	# cancel order
	await client.linear_cancel_order({
		'currency':'USD',
		'instrument_id': 'BTC-USD-PERPETUAL',
		'order_id': '14232321'
	})


	# amend order
	await client.linear_amend_order({
		'currency':'USD',
		'instrument_id': 'XRP-USD-PERPETUAL',
		'order_id': '58317173',
		'price': '0.3'
	})

	# batch amend orders
	await client.linear_amend_batch({
		'currency':'USD',
		'orders_data': [
			{
				'instrument_id': 'XRP-USD-PERPETUAL',
				'order_id': '58317172',
				'price': '0.32'
			},
			{
				'instrument_id': 'XRP-USD-PERPETUAL',
				'order_id': '58317173',
				'price': '0.33'
			}
		]
	})
