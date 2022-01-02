import asyncio
import json
import logging
from redis_adapter import RedisDB
from qrm_server.resource_definition import Resource, ResourcesRequest, ResourcesRequestResponse
from typing import List

REDIS_PORT = 6379
ResourcesListType = List[Resource]


class QueueManagerBackEnd(object):
    def __init__(self, redis_port: int = REDIS_PORT):
        if redis_port:
            self.redis = RedisDB(redis_port)
        else:
            self.redis = RedisDB(REDIS_PORT)

    def found_token(self, resources_request_resp: ResourcesRequestResponse,
                    resources_with_token:  ResourcesListType) -> ResourcesRequestResponse:
        # TODO we need to refactor this as it is not exactly as specified in the design.
        for resource in resources_with_token:
            resources_request_resp.names.append(resource.name)
        return resources_request_resp

    async def new_request(self, resources_request: ResourcesRequest) -> ResourcesRequestResponse:
        resources_request_resp = ResourcesRequestResponse()
        token = resources_request.token
        all_resources_list = await self.redis.get_all_resources()
        resources_with_token = self.find_all_resources_with_token(token=token, all_resources_list=all_resources_list)
        if resources_with_token:
            resources_request_resp.token = token
            return self.found_token(resources_request_resp=resources_request_resp, resources_with_token=resources_with_token)

        return resources_request

    def find_one_resource(self, resource: Resource, all_resources_list: ResourcesListType) -> Resource or None:
        list_of_resources_with_token = self.find_all_resources_with_token(resource.token, all_resources_list)
        if len(list_of_resources_with_token) == 1:
            for one_resource in list_of_resources_with_token:
                return one_resource
        elif len(list_of_resources_with_token) == 0:
            return None
        else:
            raise NotImplemented

    @staticmethod
    def find_all_resources_with_token(token: str, all_resources_list: ResourcesListType) -> ResourcesListType:
        tmp_list = []
        for resource in all_resources_list:
            if resource.token == token:
                tmp_list.append(resource)
        return tmp_list

    async def find_resources(self, client_req_resources_list: List[ResourcesListType]) -> ResourcesListType:
        """
        find all resources that match the client_req_list
        :param client_req_resources_list: list of resources list
        example: [[a,b,c], [a,b,c], [d,e], [f]] -> must have: one of (a or b or c) and one of (a or b or c)
        and one of (d or e) and f
        :return: list of all resources that matched the client request
        """
        out_resources_list = []
        all_resources_list = await self.redis.get_all_resources()
        for resource_group in client_req_resources_list:
            if isinstance(resource_group, Resource):
                one_resource = self.find_one_resource(resource_group, all_resources_list)
                out_resources_list.append(one_resource)
            else:
                for resource in resource_group:
                    one_resource = self.find_one_resource(resource, all_resources_list)
                    out_resources_list.append(one_resource)
        return out_resources_list


class QueueManager(asyncio.Protocol):
    def __init__(self, ):
        self.transport = None
        self.client_name = ''  # type: str
        self.loop = asyncio.get_running_loop()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        peer_name = transport.get_extra_info('peername')
        logging.info('Connection from {}'.format(peer_name))
        self.transport = transport

    def data_received(self, data) -> None:
        message = data.decode()
        try:
            message_dict = json.loads(message)
            logging.debug('Data received: {!r}'.format(message_dict))
        except json.JSONDecodeError as exc:
            logging.error(f'can\'t convert message to json: {message}\n{exc}')

        logging.info('Send: {!r}'.format(message))
        self.transport.write(data)

    def connection_lost(self, exc: Exception or None) -> None:
        logging.info(f'connection closed: {exc}')
        self.transport.close()

    def get_resources(self, resources_list: list) -> list:
        return []


async def main():
    # Get a reference to the event loop as we plan to use
    # low-level APIs.
    loop = asyncio.get_running_loop()

    server = await loop.create_server(
        lambda: QueueManager(),
        '127.0.0.1', 8888)

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(module)s %(message)s')
    try:
        asyncio.run(main(), debug=True)
    except KeyboardInterrupt as e:
        logging.error(f'got keyboard interrupt: {e}')
