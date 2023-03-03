import asyncio
import os

WS_URL = "ws://127.0.0.1:7465/net-api/v1/net/14633057457c401890ddec549932c02e/tcp/192.168.0.2/5000"
LOCAL_ADDRESS = "127.0.0.1"
LOCAL_PORT = 5000
YAGNA_APPKEY = os.environ["YAGNA_APPKEY"]


from yapapi.contrib.service.socket_proxy import ProxyServer


class Proxy:
    def __init__(self, ws_url, local_address, local_port, yagna_appkey):
        self.ws_url = ws_url
        self.local_address = local_address
        self.local_port = local_port
        self.yagna_appkey = yagna_appkey

    async def start(self):
        class ProxyServerWrapper(ProxyServer):
            @property
            def app_key(other_self):
                return self.yagna_appkey

            @property
            def instance_ws(other_self):
                return self.ws_url

        proxy_server = ProxyServerWrapper(None, None, None, self.local_address, self.local_port)
        await proxy_server.run()


async def main():
    proxy = Proxy(WS_URL, LOCAL_ADDRESS, LOCAL_PORT, YAGNA_APPKEY)
    await proxy.start()


if __name__ == '__main__':
    asyncio.run(main())
