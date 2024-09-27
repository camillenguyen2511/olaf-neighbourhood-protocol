import logging
import sys
import json
import asyncio
import websockets
import websockets.asyncio.server as websocket_server
from typing import List, Optional

import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.exceptions import InvalidSignature


from neighbourhood import Neighbourhood

logging.basicConfig(format="%(levelname)s:\t%(message)s", level=logging.INFO)


class Server:
    def __init__(self, url: str = "localhost:80") -> None:
        self._websocket_server: Optional[websocket_server.Server] = None

        self.url = url

        self.neighbour_servers = []
        self.neighbour_websockets = {}  # Websocket (ServerConnection): Neighbour URL
        self.neighbourhood = Neighbourhood(self.url)

        # maybe change client to dict?? stores # Fingerprint: {websocket, counter}
        # {websocket: {public_key, fingerprint, counter}}
        self.clients = {}  # List of clients connecting to this server

    def add_neighbour_servers(self, server_urls: List[str]):
        for url in server_urls:
            if url not in self.neighbour_servers:
                self.neighbour_servers.append(url)

    async def connect_to_neighbourhood(self):
        """Create client connections for every neighbour servers"""
        for neighbour_url in self.neighbour_servers:
            await self.connect_to_neighbour(neighbour_url)

    async def connect_to_neighbour(self, neighbour_url):
        """
        Create a client connection to the neighbour server to send requests
        if the neighbour server hasn't already in the list of active servers
        """
        if neighbour_url in self.neighbourhood.active_servers.values():
            return

        try:
            websocket = await websockets.connect(f"ws://{neighbour_url}")
            await self.neighbourhood.add_active_server(neighbour_url, websocket)
            logging.debug(f"{self.url} connect to neighbour {neighbour_url}")
        except Exception as e:
            logging.error(f"{self.url} failed to connect to neighbour {neighbour_url}")

    async def start(self):
        """
        Start the server which listens for message on the specified address and port
        """
        address, port = self.url.split(":")
        self._websocket_server = await websocket_server.serve(
            self.listen, address, port
        )
        await self.connect_to_neighbourhood()
        await self.request_client_update()
        await self._websocket_server.wait_closed()

    async def stop(self):
        logging.info(f"Closing {self.url}")
        self.clients = {}
        await self.request_client_update()
        self._websocket_server.close()

    async def listen(self, websocket):
        """
        Listen and handle messages of type: signed_data, client_list_request,
        client_update_request, chat, hello, and public_chat
        """
        while True:
            try:
                message = await websocket.recv()
                await self.handle_message(websocket, message)
            except websockets.ConnectionClosed:
                break

    async def handle_message(
        self, websocket: websocket_server.ServerConnection, message
    ):
        """
        Handle messages of type: signed_data, client_list_request,
        client_update_request, chat, hello, and public_chat
        """
        message = json.loads(message)

        message_type = message.get("type", None)

        if message_type == "client_list_request":
            await self.send_client_list(websocket)
        elif message_type == "client_update_request":
            await self.send_client_update(websocket)
        elif message_type == "client_update":
            self.receive_client_update(websocket, message)
        elif message_type == "signed_data":
            # TODO: Handle counter and signature
            counter = message.get("counter", None)
            signature = message.get("signature", None)

            data = message.get("data", None)
            if data is None:
                logging.error(
                    f"{self.url}: Type and data not found for this message: {message}"
                )
                return

            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except json.JSONDecodeError as e:
                    print(f"Error converting to JSON: {e}")

            # Handle chats
            message_type = data.get("type", None)
            logging.info(f"{self.url} receives {message_type} message")
            if message_type == "chat":
                await self.receive_chat(websocket, message)
            elif message_type == "hello":
                await self.receive_hello(websocket, data)
            elif message_type == "public_chat":
                await self.receive_public_chat(websocket, message)
            elif message_type == "server_hello":
                await self.receive_server_hello(websocket, data)
            else:
                logging.error(f"{self.url}: Type not found for this message: {message}")
        else:
            logging.error(f"{self.url}: Type not found for this message: {message}")

    async def send_response(
        self, websocket: websocket_server.ServerConnection, message
    ):
        try:
            await websocket.send(json.dumps(message))
        except Exception as e:
            if websocket in self.clients:
                self.clients.pop(websocket)
                logging.info(f"{self.url} disconnects with client")

            elif websocket in self.neighbour_websockets:
                neighbour_url = self.neighbour_websockets[websocket]
                self.neighbourhood.remove_active_server(neighbour_url)
                logging.info(f"{self.url} disconnects with neighbour {neighbour_url}")

            else:
                logging.error(f"{self.url} failed to send response: {e}")

    async def receive_server_hello(self, websocket, data):
        neighbour_url = data["sender"]
        self.neighbour_websockets[websocket] = neighbour_url

        # Connect to neighbour in case the neighbour server starts after this server
        await self.connect_to_neighbour(neighbour_url)

    async def receive_chat(self, websocket, message):
        logging.info(f"{self.url} receives chat from client:\n{message}")
        pass

    async def receive_hello(self, websocket, message):
        """Save client's public key and send client update to other servers"""
        client_public_key = message["public_key"]
        logging.info(f"{self.url} receives hello from client")
        self.clients[websocket] = {
            "public_key": client_public_key,
        }
        await self.send_client_update()

    # receive public chats and braodcast to connected clients and other neighbourhoods if valid message
    async def receive_public_chat(self, websocket, request):
        logging.info(f"{self.url} received public chat message")

        fingerprint = request["data"].get("sender", None)
        message = request["data"].get("message", None)
        if fingerprint is None or message is None:
            logging.error(f"{self.url} received an invalid public_chat message")
            return

        # Save client fingerprint - ignore if it comes from other neighbour servers
        sender = self.clients.get(websocket, None)
        if websocket not in self.neighbour_websockets:
            if sender is None:
                logging.error(f"{self.url} can't find the client for public_chat")
                return

            sender["fingerprint"] = fingerprint

        # send to clients in the server
        for client in self.clients:
            if client == websocket:
                continue

            await self.send_response(client, request)

        # request neighborhoods broadcast message
        if sender:
            await self.neighbourhood.broadcast_request(request)

    async def send_client_list(self, websocket):
        """(Between server and client) Provide the client the client list on all servers"""
        logging.info(f"{self.url} sends client list")

        all_clients = self.neighbourhood.clients_across_servers
        # Reformat the each server's client list
        servers = []
        for server_address, clients in all_clients.items():
            servers.append(
                {
                    "address": server_address,
                    "clients": clients,
                }
            )

        response = {
            "type": "client_list",
            "servers": servers,
        }
        await self.send_response(websocket, response)

    async def send_client_update(self, websocket=None):
        """
        (Between servers) If websocket is None, send client update to all active servers
        when a client sends `hello` or disconnects.
        Otherwise, send to the specified websocket
        """
        public_keys = [client["public_key"] for client in self.clients.values()]

        response = {
            "type": "client_update",
            "clients": public_keys,
        }

        if websocket is None:
            logging.info(f"{self.url} sends client update to all servers")
            await self.neighbourhood.broadcast_request(response)
        else:
            neighbour_url = self.neighbour_websockets[websocket]
            logging.info(f"{self.url} sends client update to {neighbour_url}")
            await self.send_response(websocket, response)

    async def request_client_update(self):
        """
        (Between servers) Send request client update to all servers.
        Expect to receive an updated client list for each server.
        """
        logging.info(f"{self.url} requests client update from all servers")

        request = {
            "type": "client_update_request",
        }
        responses = await self.neighbourhood.broadcast_request(request, True)

        # Receive client_update response from other servers
        for websocket, message in responses.items():
            self.receive_client_update(websocket, message)

    def receive_client_update(self, websocket, message):
        clients = message["clients"]
        if isinstance(websocket, websocket_server.ServerConnection):
            neighbour_url = self.neighbour_websockets[websocket]
        else:
            neighbour_url = self.neighbourhood.active_servers[websocket]
        logging.info(f"{self.url} receives client update from {neighbour_url}")
        self.neighbourhood.save_clients(neighbour_url, clients)


if __name__ == "__main__":
    # Arguments: server_url num_neighbours neighbour1_url neighbour2_url ...
    # Example: localhost:8080 2 localhost:8081 localhost:8081
    server_url = sys.argv[1]
    num_neighbours = int(sys.argv[2])
    neighbours = []
    for i in range(num_neighbours):
        neighbours.append(sys.argv[3 + i])

    # Start server
    server = Server(server_url)
    server.add_neighbour_servers(neighbours)
    asyncio.run(server.start())
