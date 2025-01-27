"""Contains the `ServerAsClient` class

*****
Group 25
- Hoang Bao Chau Nguyen - a1874801
- Thi Tu Linh Nguyen - a1835497
- Joanne Xue Ping Su - a1875646
- Brooke Egret Luxi Wang - a1828458
"""

import json
import logging
from typing import List

from websockets import WebSocketClientProtocol, ConnectionClosed

from .utils import crypto

logging.basicConfig(format="%(levelname)s:\t%(message)s", level=logging.INFO)


class ServerAsClient:
    """
    Server as a client to receive messages from other servers 
    through websocket's `ClientProtocol`
    """

    def __init__(self, server) -> None:
        self.server = server
        self.server_url = server.url

        # List of all connected clients on all servers.
        # Format: {server_url1: ["RSA1", "RSA2"], server_url2: ["RSA3"]}
        self.clients_across_servers = {}

        # Format: Websocket (ClientProtocol): neighbour URL
        self.active_servers = {}

    async def add_active_server(
        self, server_url: str, websocket: WebSocketClientProtocol
    ):
        """Store the server websocket and url in the neighbourhood and send server_hello"""
        self.active_servers[websocket] = server_url
        await self.send_server_hello(websocket)

    def remove_active_server(self, server_url: str):
        """Remove a server from the active servers list"""
        websocket = self.find_active_server(server_url)
        if websocket is None:
            logging.error("Cannot find neighbour %s", server_url)
        else:
            self.active_servers.pop(websocket)

    def find_active_server(self, server_url) -> WebSocketClientProtocol:
        """Find the websocket from the server's URL"""
        for websocket, url in self.active_servers.items():
            if url == server_url:
                return websocket

        return None

    def save_clients(self, server_url: str, client_list: List[str]):
        """Save the online clients from a specific server"""
        self.clients_across_servers[server_url] = client_list

    async def send_request(
        self,
        receiver_websocket: WebSocketClientProtocol,
        message,
        wait_for_response: bool = False,
    ):
        """Send request to a specific websocket"""
        response = None
        try:
            await receiver_websocket.send(json.dumps(message))
            if wait_for_response is True:
                response = await receiver_websocket.recv()
                response = json.loads(response)

        except (ConnectionClosed, TypeError) as e:
            logging.error("%s failed to send request: %s", self.server_url, e)

        return response

    async def broadcast_request(self, message, wait_for_response: bool = False):
        """Broadcast the specified request to all active servers"""
        responses = {}
        for websocket in self.active_servers:
            response = await self.send_request(websocket, message, wait_for_response)
            responses[websocket] = response

        return responses

    async def send_server_hello(self, websocket: WebSocketClientProtocol):
        """Send `server_hello` message type to all online servers"""
        logging.info("%s sends server_hello", self.server_url)
        data = {
            "type": "server_hello",
            "sender": self.server_url,
        }

        self.server.counter += 1

        request = {
            "type": "signed_data",
            "data": json.dumps(data),
            "counter": self.server.counter,
            "signature": crypto.sign_message(
                json.dumps(data), self.server.counter, self.server.private_key
            ),
        }

        await self.send_request(websocket, request)
