from zco.cookies import Cookies


class Session:
    def __init__(self):
        self.headers = {}
        self.cookies = Cookies()

    def get(self, url, headers=None):
        pass
