from qrm_server.resource_definition import ResourcesRequest, ResourcesByName
from qrm_server.qrm_http_server import URL_POST_CANCEL_TOKEN, URL_GET_ROOT, URL_POST_NEW_REQUEST, URL_GET_TOKEN_STATUS
import logging
import json
import requests
import time


def post_to_url(full_url: str, data_json: dict or str, *args, **kwargs) -> requests.Response or None:
    logging.info(f'post {data_json} to url {full_url}')
    try:
        resp = requests.post(url=full_url, json=data_json)
    except Exception as e:
        logging.critical(f'{e}')
        return

    if resp.status_code != 200:
        logging.critical(f'there is an critical error: {str(resp)}')
    return resp


def get_from_url(full_url: str, params: dict = None, *args, **kwargs) -> requests.Response or None:
    if params is None:
        params = {}
    logging.info(f'send to url {full_url}')
    try:
        resp = requests.get(full_url, params=params)
    except Exception as e:
        logging.critical(f'{e}')
        return

    if resp.status_code != 200:
        logging.critical(f'there is an critical error: {str(resp)}')
    return resp


def return_response(res: requests.Response, *args, **kwargs) -> bool:
    # noinspection PyBroadException
    try:
        if res.status_code == 200:
            return True
        else:
            logging.critical(res)
            return False
    except Exception:
        return False


class QrmClient(object):
    def __init__(self, server_ip: str,
                 server_port: str,
                 user_name: str,
                 user_password: str = '',
                 *args,
                 **kwargs):
        self.server_ip: str = server_ip
        self.server_port: str = server_port
        self.user_name: str = user_name
        self.token: str = ''
        self.user_password: str = user_password
        self.init_log_massage()

    def full_url(self, relative_url: str, *args, **kwargs) -> str:
        # noinspection HttpUrlsUsage
        return f'http://{self.server_ip}:{self.server_port}{relative_url}'

    def init_log_massage(self, *args, **kwargs):
        logging.info(f"""init new qrm client with params:
                qrm server ip: {self.server_ip}
                qrm server port: {self.server_port}
                user name: {self.user_name}
                token: {self.token}
                """)

    def _send_cancel(self, token: str, *args, **kwargs) -> requests.Response:
        rr = ResourcesRequest()
        rr.token = token
        full_url = self.full_url(URL_POST_CANCEL_TOKEN)
        logging.info(f'send cancel ion token = {self.token} to url {full_url}')
        json_as_dict = rr.as_dict()
        post_to_url(full_url=full_url, data_json=json_as_dict)
        resp = requests.post(full_url, json=json_as_dict)
        return resp

    def send_cancel(self, token: str, *args, **kwargs) -> bool:
        res = self._send_cancel(token)
        return return_response(res)

    def get_root_url(self, *args, **kwargs) -> requests.Response:
        full_url = self.full_url(URL_GET_ROOT)
        logging.info(f'send request to root url {full_url}')
        return get_from_url(full_url=full_url)

    def _new_request(self, data_json: str, *args, **kwargs) -> requests.Response:
        full_url = self.full_url(URL_POST_NEW_REQUEST)
        logging.info(f'send new request with json = {data_json} to url {full_url}')
        resp = post_to_url(full_url=full_url, data_json=data_json)
        return resp

    def new_request(self, data_json: str, *args, **kwargs) -> str:
        resp = self._new_request(data_json=data_json)
        resp_json = resp.json()
        resp_data = json.loads(resp_json)
        return resp_data.get('token')

    def _get_token_status(self, token: str, *args, **kwargs) -> requests.Response:
        full_url = self.full_url(URL_GET_TOKEN_STATUS)
        logging.info(f'send get token status token= {token} to url {full_url}')
        resp = get_from_url(full_url=full_url, params={'token': token})
        return resp

    def get_token_status(self, token: str, *args, **kwargs) -> dict:
        resp = self._get_token_status(token)
        resp_data = resp.json()
        if isinstance(resp_data, str):
            resp_data = json.loads(resp_data)
        return resp_data

    def wait_for_token_ready(self, token: str, timeout: float = float('Inf'),  *args, **kwargs) -> dict:
        logging.info(f'token ready timeout set to {timeout}')
        resp_data = self.get_token_status(token=token)
        return self.polling_api_status(resp_data, timeout, token)

    def polling_api_status(self, resp_data: dict, timeout: float, token: str) -> dict:
        start_time = time.time()
        while not resp_data.get('request_complete'):
            time_d = int(time.time() - start_time)
            logging.info(f'waiting for token {token} to be ready. wait for {time_d} sec')
            if time_d > timeout:
                logging.warning(f'TIMEOUT! waiting from QRM server has timed out! timeout was set to {timeout}')
                return resp_data
            time.sleep(5)
            resp_data = self.get_token_status(token=token)
        return resp_data


if __name__ == '__main__':
    qrm_client = QrmClient(server_ip='127.0.0.1',
                           server_port='5556',
                           user_name='ronsh')

    qrm_client.send_cancel(token='1234_2022_02_03_15_09_36')
    exit(0)
    rr = ResourcesRequest()
    rr.token = '1234'
    rbs = ResourcesByName(names=['a1'], count=1)
    rr.names.append(rbs)
    token = qrm_client.new_request(rr.as_json())
    print(token)
    result = qrm_client.get_token_status(token)
    print(result)
