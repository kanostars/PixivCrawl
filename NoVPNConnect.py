import socket
import ssl

class ConnectParent:
    def __init__(self):
        # 创建SSL上下文，禁用主机名检查
        self.context = ssl.create_default_context()
        self.context.check_hostname = False
        self.context.verify_mode = ssl.CERT_NONE

        self.hostname = socket.gethostname()
        self.conn = None

        self.nr = None
        self.url = ''
        self.headers = {}

    def get(self, url, headers=None):
        self.url = url
        self.headers = headers

        self.nr = self.rev()

        return self

    def get_headers(self):
        if not self.nr is None:
            headers = None
            while not headers:
                headers, _, _ = next(self.nr)
            return headers
        else:
            return None

    def get_text(self):
        if not self.get_content() is None:
            return self.get_content().decode()
        return None

    def get_content(self):
        if not self.nr is None:
            is_finish = False
            content = b''
            while not is_finish:
                headers, content, is_finish = next(self.nr)
            return content
        else:
            return None

    def rev(self):
        if self.headers is None:
            self.headers = {}
        zh = {
            'Host': 'www.pixiv.net',
            'Connection': 'close'
        }
        for z in zh.keys():
            self.headers[z] = zh.get(z)
        # 包装socket对象为SSL套接字，并提供伪造的SNI
        s2 = self.context.wrap_socket(self.conn, server_hostname=self.hostname)

        # 构造一个简单的HTTP GET请求消息示例（你可以根据实际需求调整请求内容）
        http_request = f'GET {self.url} HTTP/1.1\r\n'
        for h in self.headers.keys():
            http_request += f'{h}: {self.headers[h]}\r\n'
        http_request += f'\r\n'

        try:
            # 通过SSL套接字发送HTTP请求消息
            s2.sendall(http_request.encode())

            # 接收服务器返回的响应数据
            response_data = b""
            has_header = False
            headers = None
            while True:
                chunk = s2.recv(4096)
                if not chunk:
                    break
                response_data += chunk
                if not has_header:
                    header_end_index = response_data.find(b"\r\n\r\n")
                    if header_end_index != -1:
                        headers = response_data[:header_end_index].decode('utf-8')
                        response_data = response_data[header_end_index + 4:]
                        hs = headers.split('\r\n')
                        headers = {}
                        for h in hs:
                            t = h.split(': ')
                            if len(t) == 2:
                                headers[t[0]] = t[1]
                        has_header = True
                yield headers, response_data, False
            while True:
                yield headers, response_data, True

        finally:
            # 关闭SSL套接字连接，释放资源
            s2.close()




class ConnectMain(ConnectParent):
    def __init__(self):
        super().__init__()
        self.conn = socket.create_connection(('pixivision.net', 443), 10)

        self.hostname = '210.140.139.155'


class ConnectImg(ConnectParent):
    def __init__(self):
        super().__init__()
        self.conn = socket.create_connection(('210.140.139.133', 443), 10)

        self.hostname = '210.140.139.133'

class ConnectHelper:
    def __init__(self):
        self.conn_main = ConnectMain()
        self.conn_img = ConnectImg()

    def get(self, url, headers=None):
        if 'pixiv.net' in url or 'fanbox.cc' in url:
            return self.conn_main.get(url, headers)
        if 'pximg.net' in url:
            return self.conn_img.get(url, headers)



if __name__ == '__main__':
    conn = ConnectHelper()
    resp = conn.get('https://i.pximg.net/img-original/img/2024/12/28/00/00/36/125608955_p0.png', headers={
        'Referer': 'https://www.pixiv.net/',
    })
    print(resp.get_headers())
    # with open('cs2.png', 'wb') as f:
    #     f.write(resp.get_content())
