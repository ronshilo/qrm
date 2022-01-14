import aioredis
import asyncio
import json
import logging
from qrm_server import resource_definition
from qrm_server.resource_definition import Resource, ALLOWED_SERVER_STATUSES, ResourcesRequest, ResourcesRequestResponse
from qrm_db import QrmBaseDB
from typing import Dict, List

PARTIAL_FILL_REQUESTS = 'fill_requests'
OPEN_REQUESTS = 'open_requests'
ALL_RESOURCES = 'all_resources'
SERVER_STATUS_IN_DB = 'qrm_status'
ACTIVE_STATUS = 'active'
TOKEN_DICT = 'token_dict'


class RedisDB(QrmBaseDB):
    def __init__(self, redis_port: int = 6379):
        self.redis = aioredis.from_url(
            f"redis://localhost:{redis_port}", encoding="utf-8", decode_responses=True
        )

    def init_params_blocking(self) -> None:
        asyncio.ensure_future(self.set_qrm_status(status=ACTIVE_STATUS))
        return

    async def init_default_params(self) -> None:
        # TODO: validate if redis db already exists on server before init parameters
        await self.set_qrm_status(status=ACTIVE_STATUS)

    async def wait_for_db_status(self, status: str) -> None:
        while await self.get_qrm_status() != status:
            await asyncio.sleep(1)
        return

    async def get_all_keys_by_pattern(self, pattern: str = None) -> List[Resource]:
        result = []
        async for key in self.redis.scan_iter(pattern):
            result.append(key)
        return result

    async def get_all_resources(self) -> List[Resource]:
        # return await self.get_all_keys_by_pattern(f'{RESOURCE_NAME_PREFIX}*')
        resources_list = []
        try:
            all_db_resources = await self.redis.hgetall(ALL_RESOURCES)
            for resource in all_db_resources.values():
                resources_list.append(resource_definition.resource_from_json(resource))
        except ValueError as e:
            if 'too many values to unpack' in e.args[0]:
                pass
            else:
                raise e
        return resources_list

    async def get_all_resources_dict(self) -> Dict[str, Resource]:
        """
        return: {resource_name1: Resource, resource_name2: resource)}
        """
        ret_dict = {}
        all_resources = await self.redis.hgetall(ALL_RESOURCES)
        for res_name, res_json in all_resources.items():
            ret_dict[res_name] = resource_definition.resource_from_json(res_json)
        return ret_dict

    async def add_resource(self, resource: Resource) -> bool:
        all_resources = await self.get_all_resources()
        if all_resources:
            if resource in all_resources:
                logging.warning(f'resource {resource.name} already exists')
                return False
        await self.redis.hset(ALL_RESOURCES, resource.name, resource.as_json())
        await self.redis.rpush(resource.db_name(), json.dumps({}))
        return True

    async def get_resource_by_name(self, resource_name: str) -> Resource or None:
        resource_as_json = await self.redis.hget(ALL_RESOURCES, resource_name)
        if resource_as_json:
            return resource_definition.resource_from_json(resource_as_json)
        return None

    async def get_resources_by_names(self, resources_names: List[str]) -> List[Resource]:
        ret_list = []
        for res_name in resources_names:
            resource = await self.get_resource_by_name(res_name)
            if resource:
                ret_list.append(resource)
            else:
                logging.error(f'resource: {res_name} is not in DB')
        return ret_list

    async def remove_resource(self, resource: Resource) -> bool:
        if await self.redis.delete(resource.db_name()) and await self.redis.hdel(ALL_RESOURCES, resource.name):
            return True
        logging.error(f'resource: {resource.name} doesn\'t exists in db')
        return False

    async def set_resource_status(self, resource: Resource, status: str) -> bool:
        all_resources_dict = await self.get_all_resources_dict()
        if all_resources_dict.get(resource.name):
            resource_json = await self.redis.hget(ALL_RESOURCES, resource.name)
            resource_obj = resource_definition.resource_from_json(resource_json)
            resource_obj.status = status
            return not await self.redis.hset(ALL_RESOURCES, resource.name, resource_obj.as_json())
        else:
            return False

    async def get_resource_status(self, resource: Resource) -> str:
        resource_json = await self.redis.hget(ALL_RESOURCES, resource.name)
        resource_obj = resource_definition.resource_from_json(resource_json)
        return resource_obj.status

    async def add_job_to_resource(self, resource: Resource, job: dict) -> bool:
        return await self.redis.lpush(resource.db_name(), json.dumps(job))

    async def get_resource_jobs(self, resource: Resource) -> List[Dict]:
        all_jobs = await self.redis.lrange(resource.db_name(), 0, -1)
        return self.build_resource_jobs_as_dicts(all_jobs)

    async def set_qrm_status(self, status: str) -> bool:
        if not self.validate_allowed_server_status(status):
            return False
        return await self.redis.set(SERVER_STATUS_IN_DB, status)

    async def get_qrm_status(self) -> str:
        return await self.redis.get(SERVER_STATUS_IN_DB)

    async def is_resource_exists(self, resource: Resource) -> bool:
        return resource in await self.get_all_resources()

    async def remove_job(self, job_id: str, resources_list: List[Resource] = None) -> None:
        """
        this method remove job by it's id from list of resources or from all the resources in the DB
        :param job_id: the unique job id
        :param resources_list: list of all resources names to remove the job from.
        if this param is None, the job will be removed from all resources in the DB
        :return: True if
        """
        if not resources_list:  # in this case remove the job from all the resources
            resources_list = await self.get_all_resources()
        for resource in resources_list:
            job = await self.get_job_for_resource_by_id(resource, job_id)
            if not job:
                continue
            else:
                await self.redis.lrem(resource.db_name(), 1, job)
        return

    async def get_job_for_resource_by_id(self, resource: Resource, job_id: str) -> str:
        resource_jobs = await self.get_resource_jobs(resource)
        for job in resource_jobs:
            if job.get('id') == job_id:
                return json.dumps(job)
        return ''

    async def get_active_job(self, resource: Resource) -> dict:
        active_job = await self.redis.lindex(resource.db_name(), -2)
        if active_job:
            return json.loads(active_job)
        else:
            return {}

    async def set_token_for_resource(self, token: str, resource: Resource) -> None:
        resource_from_db = await self.get_resource_by_name(resource.name)
        if resource_from_db:
            resource_from_db.token = token
            await self.redis.hset(ALL_RESOURCES, resource.name, resource_from_db.as_json())
        else:
            logging.error(f'resource {resource.name} is not in DB, so can\'t add token to it')

    async def generate_token(self, token: str, resources: List[Resource]) -> bool:
        if await self.redis.hget(TOKEN_DICT, token):
            logging.error(f'token {token} already exists in DB, can\'t generate it again')
            return False
        resources_list = []
        for resource in resources:
            resources_list.append(resource.as_json())
        return await self.redis.hset(TOKEN_DICT, token, json.dumps(resources_list))

    async def get_token_resources(self, token: str) -> List[Resource]:
        resources_list = []
        token_json = await self.redis.hget(TOKEN_DICT, token)
        if not token_json:
            logging.error(f'token {token} does not exists in db')
            return []
        for resource_json in json.loads(token_json):
            resources_list.append(resource_definition.resource_from_json(resource_json))
        return resources_list

    async def add_resources_request(self, resources_req: ResourcesRequest) -> None:
        await self.redis.hset(OPEN_REQUESTS, resources_req.token, resources_req.as_json())

    async def get_open_requests(self) -> Dict[str, ResourcesRequest]:
        open_requests = await self.redis.hgetall(OPEN_REQUESTS)
        ret_dict = {}
        for token, req in open_requests.items():
            ret_dict[token] = resource_definition.resource_request_from_json(req)
        return ret_dict

    async def get_open_request_by_token(self, token: str) -> ResourcesRequest:
        # use this method if you know the token request since it's much faster than get_open_requests
        open_req = await self.redis.hget(OPEN_REQUESTS, token)
        if open_req:
            return resource_definition.resource_request_from_json(open_req)
        else:
            return ResourcesRequest()

    async def update_open_request(self, token: str, updated_request: ResourcesRequest) -> bool:
        if await self.redis.hget(OPEN_REQUESTS, token):
            await self.redis.hset(OPEN_REQUESTS, token, updated_request.as_json())
            return True
        else:
            logging.error(f'request with token {token} is not in DB!')
            return False

    async def remove_open_request(self, token: str) -> None:
        if await self.redis.hget(OPEN_REQUESTS, token):
            await self.redis.hdel(OPEN_REQUESTS, token)
        else:
            logging.warning(f'request with token {token} is not in DB!')

    async def partial_fill_request(self, token: str, resource: Resource) -> None:
        partial_fill_req = await self.redis.hget(PARTIAL_FILL_REQUESTS, token)
        if partial_fill_req:
            partial_fill_list = json.loads(partial_fill_req)
            if resource.name in partial_fill_list:
                return
            partial_fill_list.append(resource.name)
            await self.redis.hset(PARTIAL_FILL_REQUESTS, token, json.dumps(partial_fill_list))
        else:
            await self.redis.hset(PARTIAL_FILL_REQUESTS, token, json.dumps([resource.name]))

    async def get_partial_fill(self, token: str) -> ResourcesRequestResponse:
        partial_fill_req = await self.redis.hget(PARTIAL_FILL_REQUESTS, token)
        if partial_fill_req:
            return ResourcesRequestResponse(json.loads(partial_fill_req), token)
        else:
            return ResourcesRequestResponse()

    async def remove_partially_fill_request(self, token: str) -> None:
        await self.redis.hdel(PARTIAL_FILL_REQUESTS, token)

    async def is_request_filled(self, token: str) -> bool:
        if await self.redis.hget(TOKEN_DICT, token) and not await self.redis.hget(OPEN_REQUESTS, token):
            return True
        return False

    @staticmethod
    def validate_allowed_server_status(status: str) -> bool:
        if status not in ALLOWED_SERVER_STATUSES:
            logging.error(f'can\'t update qrm_server to status: {status}, '
                          f'allowed statuses are: {ALLOWED_SERVER_STATUSES}')
            return False
        return True

    @staticmethod
    def build_resource_jobs_as_dicts(jobs_list: List[str]) -> List[Dict]:
        ret_list = []
        for job in jobs_list:
            ret_list.append(json.loads(job))
        return ret_list

    # def __del__(self):
    #     self.redis.close()
