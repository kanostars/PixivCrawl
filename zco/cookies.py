import logging


class Cookies:
    def __init__(self):
        self.cookies = []

    def __str__(self):
        return '; '.join([str(cookie) for cookie in self.cookies])

    def add_cookies(self, cookie):
        cookie_jar = CookieJar(cookie)
        for cookie in self.cookies:
            if cookie.cookie['name'] == cookie_jar.cookie['name']:
                cookie.set_cookie(cookie_jar)
                return
        self.cookies.append(CookieJar(cookie))


class CookieJar:
    def __init__(self, cookie=None):
        self.cookie = {
            'name': '',
            'value': '',
            'domain': '',
            'path': '',
            'expires': '',
            'max-age': '',
            'version': '',
            'secure': False,
            'http-only': False,
        }
        if cookie:
            self.set_cookie(cookie)

    def __str__(self):
        return f'{self.cookie["name"]}={self.cookie["value"]}'

    def set_cookie(self, cookie):
        if isinstance(cookie, CookieJar):
            self.cookie = cookie.cookie
        elif isinstance(cookie, str):
            sp_cookie = cookie.split(';')
            for cookie in sp_cookie:
                cookie = cookie.strip()
                if cookie:
                    if '=' in cookie:
                        cookie = cookie.split('=', 1)
                        cookie[0] = cookie[0].lower()
                        if cookie[0] in self.cookie:
                            self.cookie[cookie[0]] = cookie[1]
                        else:
                            if self.cookie['name']:
                                logging.warning(f'存在多个无法解析的值，{self.cookie["name"]}, {cookie[0]}')
                            else:
                                self.cookie['name'] = cookie[0]
                                self.cookie['value'] = cookie[1]
                    else:
                        if cookie[0] in self.cookie:
                            self.cookie[cookie] = True
