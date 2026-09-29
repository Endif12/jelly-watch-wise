from datetime import datetime

import i18n


def setup_language(language_code):
    i18n.load_path.append('lang')
    i18n.set('file_format', 'json')
    i18n.set('filename_format', '{locale}.{format}')
    i18n.set('locale', language_code)
    i18n.set('fallback', 'en')


def clip(val, min_, max_):
    return min_ if val < min_ else max_ if val > max_ else val


def get_today():
    return datetime.today().strftime('%Y-%m-%d')


today = get_today()


def has_new_day_begun():
    global today
    if today != get_today():
        today = get_today()
        return True
    return False


def get_hours_of_today():
    return int(datetime.today().strftime('%-H'))


def normalize_user_id(user_id):
    """Normalize Jellyfin user GUID to N format (32 lowercase hex, no dashes).

    Jellyfin <=10.6 returned N format, newer versions (>=10.7, 10.11, 12.x)
    return D format (with dashes). PlaybackReporting DB always stores
    N format (session.UserId.ToString("N")). Normalizing both sides
    keeps old config files working after a Jellyfin update.
    """
    if user_id is None:
        return None
    return str(user_id).replace('-', '').lower()


def build_auth_headers(token):
    """Modern Jellyfin Authorization header.

    Works on 10.8-10.10, 10.11 (EnableLegacyAuthorization true/false)
    and 12.x where legacy X-Emby-* headers and unquoted tokens are rejected.
    Quotes around Token are required by the spec; Client/Device/DeviceId/
    Version identify the app in the dashboard.
    """
    return {
        'Authorization': f'MediaBrowser Client="JellyWatchWise", Device="JellyWatchWise", '
                         f'DeviceId="jelly-watch-wise", Version="1.0", Token="{token}"',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }
