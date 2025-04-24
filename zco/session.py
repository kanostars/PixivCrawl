from zco import Request
from zco.cookies import Cookies


class Session:
    def __init__(self):
        self.headers = {}
        self.cookies = Cookies()

        self.rules = ''

    def request(self, url, method='GET', data=None, headers=None):
        cookies = headers.get('Cookie')
        if cookies:
            self.cookies.add_cookies(cookies)
        for header in headers:
            self.headers[header] = headers[header]
        headers['Cookie'] = str(self.cookies)

        request = Request()
        if self.rules:
            request.set_rules(self.rules)
        return request.request(url, method=method, headers=headers, data=data)

    def get(self, url, headers=None):
        return self.request(url, method='GET', headers=headers)

    def post(self, url, data=None, headers=None):
        return self.request(url, method='POST', data=data, headers=headers)

    def put(self, url, data=None, headers=None):
        return self.request(url, method='PUT', data=data, headers=headers)

    def delete(self, url, data=None, headers=None):
        return self.request(url, method='DELETE', data=data, headers=headers)



