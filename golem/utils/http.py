import aiohttp

# TODO: Implement Port/Adapter pattern and make aiohttp dependency optional for http requests for
#   more decoupling


async def make_http_get_request(url: str, raise_exceptions: bool = False) -> str:
    async with aiohttp.ClientSession() as client:
        response = await client.get(url)

        if response.status != 200 and raise_exceptions:
            response.raise_for_status()

        return await response.text()


async def make_http_head_request(url: str, raise_exceptions: bool = False) -> None:
    async with aiohttp.ClientSession() as client:
        response = await client.head(url, allow_redirects=True)

        if response.status != 200 and raise_exceptions:
            response.raise_for_status()
