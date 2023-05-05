class BitAPIException(Exception):
    """Exception class to handle general API Exceptions

    `code` values

    `message` format

    """

    def __init__(self, uri, params, response, data):
        self.uri = uri
        self.params = params
        self.response = response
        self.data = data

    def __str__(self):  # pragma: no cover
        return "BitAPIException {}?{}: {}".format(self.uri, self.params, self.data)


class SubscribeException(BitAPIException):
    def __init__(self, code, message):
        super().__init__('websocket', '', code, message)
