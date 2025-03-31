import json
import logging
import socket
import ssl
import subprocess
import threading
import os

retry_times = 0
browser_list = ['chrome.exe', 'msedge.exe']


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
        self._headers = {}

        self.resp_headers = None
        self.resp_content = b''
        self.resp_finished = False
        self.is_stopped = False
        self.is_paused = False

    def get(self, url, headers=None):
        self.url = url
        self._headers = headers

        self.nr = self.rev()

        return self

    def get_content_progress(self) -> float:
        if self.resp_finished:
            return 1
        if self.resp_headers:
            try:
                if int(self.resp_headers['Content-Length']) > 0:
                    return len(self.resp_content) / int(self.resp_headers['Content-Length'])
            except KeyError:
                return 0
        return 0

    @property
    def headers(self):
        if self.nr:
            while not self.resp_headers:
                self.resp_headers, _, _ = next(self.nr)
            return self.resp_headers
        else:
            logging.warning('还未建立连接')
            return None

    @property
    def text(self):
        text = self.content
        if text:
            return text.decode('utf-8', 'replace')
        return None

    @property
    def json(self):
        text = self.text
        if text:
            logging.debug(json.loads(text))
            return json.loads(text)

    @property
    def content(self):
        if not self.nr is None:
            while not self.resp_finished:
                self.resp_headers, self.resp_content, self.resp_finished = next(self.nr)
            logging.debug(self.resp_headers)
            if not self.resp_headers.get('Content-Length'):
                logging.debug(f'分块传输方式')
                all_data = self.resp_content
                reconstructed_data = b''
                index = 0
                while index < len(all_data):
                    # 查找下一个块大小描述部分的结束位置（即 \r\n 的位置）
                    end_of_size = all_data.find(b'\r\n', index)
                    if end_of_size == -1:
                        break
                    # 获取块大小描述部分的十六进制字符串，并转换为十进制整数
                    chunk_size_hex = all_data[index:end_of_size].decode('utf-8')
                    chunk_size = int(chunk_size_hex, 16)
                    if chunk_size == 0:
                        break
                    # 移动到数据部分的起始位置（跳过块大小描述部分和 \r\n ）
                    index = end_of_size + 2
                    # 获取数据部分（根据块大小获取相应长度的数据）
                    data_chunk = all_data[index:index + chunk_size]
                    reconstructed_data += data_chunk
                    # 移动到下一个块的起始位置（跳过数据部分后面的 \r\n ）
                    index += chunk_size + 2
                self.resp_content = reconstructed_data
            return self.resp_content
        else:
            return None

    def pause(self):
        self.is_paused = True

    def resume(self):
        self.is_paused = False

    def stop(self):
        self.is_stopped = True
        self.conn.close()

    def rev(self):
        if self._headers is None:
            self._headers = {}
        zh = {
            'Host': 'www.pixiv.net',
            'Connection': 'close'
        }
        for z in zh.keys():
            self._headers[z] = zh.get(z)
        # 包装socket对象为SSL套接字
        logging.debug(f'{self.url} 开始连接')
        logging.debug(self.hostname)
        s2 = self.context.wrap_socket(self.conn,
                                      server_hostname=self.hostname,
                                      do_handshake_on_connect=False)
        s2.do_handshake()
        logging.debug(f'{self.url} 连接成功')

        # 构造HTTP GET请求消息
        http_request = f'GET {self.url} HTTP/1.1\r\n'
        for h in self._headers.keys():
            http_request += f'{h}: {self._headers[h]}\r\n'
        http_request += f'\r\n'

        try:
            # 通过SSL套接字发送HTTP请求消息
            s2.sendall(http_request.encode())

            # 接收服务器返回的响应数据
            response_data = b""
            has_header = False
            headers = None
            while True:
                if self.is_stopped:
                    logging.debug(f'{self.url} 连接已被终止')
                    s2.close()
                    return
                if self.is_paused:
                    time.sleep(0.5)
                    yield headers, response_data, False
                    continue
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

                        logging.debug(f'{self.url} 获取到请求头 {headers}')
                logging.debug(response_data)
                yield headers, response_data, False
            while True:
                yield headers, response_data, True

        finally:
            # 关闭SSL套接字连接，释放资源
            s2.close()


class ConnectMain(ConnectParent):
    def __init__(self):
        super().__init__()
        self.conn = socket.create_connection(('210.140.139.155', 443), 10)

        self.hostname = '210.140.139.155'


class ConnectImg(ConnectParent):
    def __init__(self):
        super().__init__()
        self.conn = socket.create_connection(('210.140.139.133', 443), 10)

        self.hostname = '210.140.139.133'


def connect(url, headers=None):
    if 'pixiv.net' in url or 'fanbox.cc' in url:
        return ConnectMain().get(url, headers)
    if 'pximg.net' in url:
        return ConnectImg().get(url, headers)

def exec_cmd(cmd):
    return subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def open_pixiv(path):
    if not path:
        logging.warning('路径未填写')
        return None
    browser = os.path.basename(path)
    if browser not in browser_list:
        logging.warning('暂不支持该浏览器')
        return None
    exec_cmd(f'taskkill /F /IM {browser}').communicate()
    pram = '--start-url https://www.pixiv.net --host-rules="MAP api.fanbox.cc api.fanbox.cc,MAP *pixiv.net pixivision.net,MAP *fanbox.cc pixivision.net,MAP *pximg.net U4" --host-resolver-rules="MAP api.fanbox.cc 172.64.146.116,MAP pixivision.net 210.140.139.155,MAP U4 210.140.139.133" --test-type --ignore-certificate-errors'
    return exec_cmd(f'"{path}" {pram}')

