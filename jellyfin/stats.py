import json
import logging
from abc import abstractmethod

import requests

from misc import get_hours_of_today, normalize_user_id, build_auth_headers

logger = logging.getLogger('watchwise')


class AggregatedStatsSource:
    @abstractmethod
    def get_total_time_sec(self, user_id, date_start, date_end):
        pass


class PlaytimeReporting(AggregatedStatsSource):
    def __init__(self, server, token):
        self.server = server.rstrip('/')
        self.token = token
        self.headers = build_auth_headers(self.token)
        self.decoder = json.JSONDecoder()

    def get_total_time_sec(self, user_id, date_start, date_end):
        # Jellyfin >=10.7 returns D-format ids (with dashes) while
        # PlaybackReporting DB stores N-format (no dashes, lowercase).
        # Match both formats so an update of Jellyfin/linuxserver image
        # does not silently reset every counter to 0.
        uid_plain = normalize_user_id(user_id)
        uid_dashed = str(user_id)
        # Explicit day boundaries; DB stores 'yyyy-MM-dd HH:mm:ss'.
        start_ts = f'{date_start} 00:00:00'
        end_ts = f'{date_end} 00:00:00'
        sql = (
            "SELECT SUM(PlayDuration) AS TotalTime FROM PlaybackActivity "
            f"WHERE (REPLACE(LOWER(UserId), '-', '') = '{uid_plain}' "
            f"OR UserId IN ('{uid_dashed}', '{uid_plain}')) "
            f"AND DateCreated >= '{start_ts}' AND DateCreated < '{end_ts}'"
        )
        payload = {'CustomQueryString': sql}
        try:
            r = requests.post(f"{self.server}/user_usage_stats/submit_custom_query",
                              headers=self.headers, data=json.dumps(payload), timeout=15)
        except requests.RequestException as exc:
            logger.error(f'PlaybackReporting query failed (network): {exc}')
            return 0
        if r.status_code != 200:
            logger.error(f'PlaybackReporting query failed: HTTP {r.status_code} {r.text[:300]}. '
                         f'Check that the Playback Reporting plugin version matches your '
                         f'Jellyfin version (v17 for 10.11, v19 for 12.x) and the API key is valid.')
            return 0
        try:
            data = self.decoder.decode(r.text)
        except (ValueError, KeyError) as exc:
            logger.error(f'PlaybackReporting bad response: {exc} body={r.text[:300]}')
            return 0
        # Newer plugin versions may return an error message instead of rows.
        message = data.get('message') if isinstance(data, dict) else None
        results = data.get('results', []) if isinstance(data, dict) else []
        if message and not results:
            # Normal empty-day response: "Query executed, no data returned."
            if 'error' in str(message).lower():
                logger.error(f'PlaybackReporting SQL error: {message} sql={sql}')
            else:
                logger.debug(f'PlaybackReporting no data: {message}')
            return 0
        try:
            if not results or not results[0]:
                return 0
            result_text = results[0][0]
            if result_text in (None, '', 'None'):
                return 0
            return int(float(result_text))
        except (ValueError, TypeError, IndexError, KeyError) as exc:
            logger.error(f'PlaybackReporting parse error: {exc} body={r.text[:300]}')
            return 0


class JellyStats(AggregatedStatsSource):
    def __init__(self, server, token):
        self.server = server.rstrip('/')
        self.token = token
        self.headers = {'accept': 'application/json',
                        'content-Type': 'application/json',
                        'x-api-token': f'{self.token}'}
        self.decoder = json.JSONDecoder()

    def get_total_time_sec(self, user_id, date_start, date_end):
        hours = get_hours_of_today()
        payload = {
            'hours': f'{hours}',
            'userid': f'{user_id}'
        }
        try:
            r = requests.post(f"{self.server}/stats/getGlobalUserStats", headers=self.headers,
                              data=json.dumps(payload), timeout=15)
        except requests.RequestException as exc:
            logger.error(f'Jellystat query failed (network): {exc}')
            return 0
        time_sec = 0
        if r.status_code == 200:
            if not r.text:  # version 1.1.1 returns inconsistent results - empty string instead of reporting 0 plays
                return 0
            try:
                result_text = self.decoder.decode(r.text).get("total_playback_duration")
            except ValueError as exc:
                logger.error(f'Jellystat bad response: {exc} body={r.text[:300]}')
                return 0
            if result_text:
                try:
                    time_sec = int(float(result_text))
                except (ValueError, TypeError):
                    time_sec = 0
        else:
            logger.error(f'Jellystat query failed: HTTP {r.status_code} {r.text[:300]}')
        return time_sec
