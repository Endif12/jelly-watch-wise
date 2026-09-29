import json

import requests

from config import logger
from jellyfin.stats import AggregatedStatsSource
from misc import build_auth_headers


class ServerApi:
    def __init__(self, server, token, stats: AggregatedStatsSource):
        self.server = server.rstrip('/')
        self.token = token
        self.headers = build_auth_headers(self.token)
        self.decoder = json.JSONDecoder()
        self.stats = stats

    def get_users(self):
        users = {}
        try:
            r = requests.get(f'{self.server}/Users', headers=self.headers, timeout=15)
        except requests.RequestException as exc:
            logger.error(f'GET /Users failed (network): {exc}')
            return users
        if r.status_code == 200:
            try:
                users = self.decoder.decode(r.text)
            except ValueError as exc:
                logger.error(f'GET /Users bad JSON: {exc}')
                return {}
            users = {x["Id"]: x["Name"] for x in users}
        else:
            logger.error(f'GET /Users failed: HTTP {r.status_code} {r.text[:300]}. '
                         f'Check server host, API key and Jellyfin version compatibility.')
        return users

    def get_total_time_sec(self, user_id, date_start, date_end):
        return self.stats.get_total_time_sec(user_id, date_start, date_end)

    def get_user_policy(self, user_id):
        try:
            user = requests.get(f'{self.server}/Users/{user_id}', headers=self.headers, timeout=15)
        except requests.RequestException as exc:
            logger.error(f'GET /Users/{user_id} failed (network): {exc}')
            return None
        if user.status_code != 200:
            logger.error(f'GET /Users/{user_id} failed: HTTP {user.status_code} {user.text[:300]}')
            return None
        try:
            return self.decoder.decode(user.text)["Policy"]
        except (ValueError, KeyError) as exc:
            logger.error(f'GET /Users/{user_id} bad response: {exc}')
            return None

    def set_user_policy(self, user_id, policy):
        try:
            r = requests.post(f'{self.server}/Users/{user_id}/Policy', headers=self.headers,
                              data=json.dumps(policy), timeout=15)
        except requests.RequestException as exc:
            logger.error(f'POST /Users/{user_id}/Policy failed (network): {exc}')
            return
        if r.status_code != 204:
            logger.error(f'POST /Users/{user_id}/Policy failed: HTTP {r.status_code} {r.text[:500]}')

    def disable_user(self, user_id, is_disabled: bool):
        policy = self.get_user_policy(user_id)
        if policy is None:
            return
        policy["IsDisabled"] = is_disabled
        self.set_user_policy(user_id, policy)

    def is_user_disabled(self, user_id):
        policy = self.get_user_policy(user_id)
        if policy is None:
            return False
        return policy.get("IsDisabled", False)

    def get_enabled_folders(self, user_id):
        policy = self.get_user_policy(user_id)
        if policy is None:
            return []
        return policy.get("EnabledFolders", [])

    def set_enabled_folders(self, user_id, folders):
        policy = self.get_user_policy(user_id)
        if policy is None:
            return
        policy["EnabledFolders"] = folders
        self.set_user_policy(user_id, policy)
