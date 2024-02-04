class WrongPasswordError(Exception):
    pass


class AuthFailedError(Exception):
    pass


class NoChannelInFeedError(Exception):
    pass


class NoTranscriptsUrlError(Exception):
    pass


class OpmlFetchError(Exception):
    def __init__(self, headers: dict) -> None:
        self.headers = headers
        super().__init__("Failed to fetch OPML from Overcast")

    def __str__(self: "OpmlFetchError") -> str:
        return repr(self.headers)
