class BitAPIException(Exception):
    def __init__(self, uri, params, response, code, message):
        self.uri = uri
        self.params = params
        self.response = response
        self.code = code
        self.message = message

    def __str__(self):  # pragma: no cover
        return "BitAPIException on {}: {} {}".format(self.uri, self.code, self.message)


class SubscribeException(BitAPIException):
    def __init__(self, code, message):
        super().__init__('websocket', '', None, code, message)
