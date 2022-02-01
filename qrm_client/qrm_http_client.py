import requests

from qrm_server.resource_definition import ResourcesRequest
from qrm_server.qrm_http_server import URL_POST_CANCEL_TOKEN
#from urllib import request, parse
import logging
import json
import requests


def read_url(full_url: str) -> requests.Response or None:
    logging.info(f'send to url {full_url}')
    try:
        resp = requests.get(full_url)
    except Exception as e:
        logging.critical(f'e')
        return

    if resp.status_code == 200:
        return resp
    else:
        logging.critical(f'there is an critical error: {str(resp)}')
        return


class QrmClient(object):
    def __init__(self, server_ip: str,
                 server_port: str,
                 user_name: str,
                 token: str = '',
                 user_password: str = ''):
        self.server_ip: str = server_ip
        self.server_port: str = server_port
        self.user_name: str = user_name
        self.token: str = token
        self.user_password: str = user_password
        self.init_log_massage()

    def full_url(self, relative_url: str) -> str:
        return f'http://{self.server_ip}:{self.server_port}{relative_url}'

    def init_log_massage(self):
        logging.info(f"""init new qrm client with parms:
                qrm server ip: {self.server_ip}
                qrm server port: {self.server_port}
                user name: {self.user_name}
                token: {self.token}
                """)

    def _send_cancel(self) -> requests.Response:
        rr = ResourcesRequest()
        rr.token = self.token
        full_url = self.full_url(URL_POST_CANCEL_TOKEN)
        logging.info(f'send cancel ion token = {self.token} to url {full_url}')
        json_as_dict = rr.as_dict()
        resp = requests.post(full_url, json=json_as_dict)
        return resp

    def send_cancel(self) -> bool:
        res = self._send_cancel()
        if res.status_code == 200:
            return True
        else:
            logging.critical(res)
            return False

    def get_root_url(self) -> requests.Response:
        full_url = self.full_url('/')
        return read_url(full_url=full_url)


if __name__ == '__main__':
    qrm_client = QrmClient(server_ip='127.0.0.1',
                           server_port=5555,
                           user_name='ronsh',
                           token='1234')
    qrm_client.get_root_url()
