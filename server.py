"""
大乐透数据下载 - 本地代理服务器
启动后，手机和电脑连同一WiFi，手机浏览器访问 http://电脑IP:8080 即可
"""
import http.server
import urllib.request
import urllib.error
import socket
import os
import re

PORT = 8080
API_BASE = 'https://webapi.sporttery.cn/gateway/lottery/'


class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # API 代理：/api/xxx → https://webapi.sporttery.cn/gateway/lottery/xxx
        if self.path.startswith('/api/'):
            api_path = self.path[4:]
            url = API_BASE + api_path
            try:
                req = urllib.request.Request(url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': 'https://www.lottery.gov.cn/',
                })
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = resp.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(data)
            except urllib.error.HTTPError as e:
                self.send_response(e.code)
                self.end_headers()
            except Exception as e:
                self.send_response(502)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(f'Proxy error: {e}'.encode())
        else:
            # 默认：提供静态文件
            super().do_GET()

    def log_message(self, format, *args):
        # 简洁日志
        print(f"  {args[0]}")


def get_local_ip():
    """获取本机局域网 IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('114.114.114.114', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    local_ip = get_local_ip()

    print('=' * 50)
    print('  大乐透数据下载 - 本地服务器已启动')
    print('=' * 50)
    print()
    print(f'  电脑访问:  http://localhost:{PORT}')
    if local_ip != '127.0.0.1':
        print(f'  手机访问:  http://{local_ip}:{PORT}')
    print()
    print('  ⚠ 手机和电脑必须连同一个 WiFi')
    print('  ⚠ 按 Ctrl+C 停止服务器')
    print()

    server = http.server.HTTPServer(('0.0.0.0', PORT), ProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n服务器已停止')
        server.server_close()
