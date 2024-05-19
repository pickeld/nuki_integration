import logging
import random
from datetime import datetime, timedelta

import aiohttp

logger = logging.getLogger(__name__)

API_TOKEN = None
API_URL = None
OPT_USERNAME = None
NUKI_NAME = None
OTP_LIFETIME_HOURS = 0


def initialize(api_token, api_url, otp_username, nuki_name, otp_lifetime_hours):
    global API_TOKEN, API_URL, OPT_USERNAME, NUKI_NAME, OTP_LIFETIME_HOURS
    API_TOKEN = api_token
    API_URL = api_url
    OPT_USERNAME = otp_username
    NUKI_NAME = nuki_name
    OTP_LIFETIME_HOURS = otp_lifetime_hours


async def get_auth() -> list[dict]:
    auths = []
    results = await request(uri=f'smartlock/auth?type=13')
    for auth in results:
        if auth.get('name').startswith('OTP'):
            auths.append(auth)
    return auths


async def set_auth():
    start_date, end_date = get_time_range()
    smartlock: dict = await get_smartlock()
    code = genetate_otp_code()
    data = {
        "name": "OTP_code",
        "start_date": str(start_date),
        "end_date": str(end_date),
        "allowedWeekDays": 127,
        "allowedFromTime": 0,
        "allowedUntilTime": 0,
        "smartlockIds": [smartlock['smartlockId']],
        "remoteAllowed": True,
        "smartActionsEnabled": False,
        "type": 13,
        "code": code
    }
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {API_TOKEN}"
    }

    async with aiohttp.ClientSession() as session:
        async with session.put(url=f'{API_URL}/smartlock/auth', headers=headers, json=data) as response:
            text_response = await response.text()
            if response.status == 204:
                result = {
                    "start": str(start_date),
                    "end": str(end_date),
                    "smartlockId": smartlock['smartlockId'],
                    "code": code
                }
                logger.info(f'auths created: (response code: {response.status}): {result}')
                return True
            else:
                logger.error(f'unable to create auth: (response code: {response.status}): {text_response}')
                return False


async def del_auths(auths: list):
    headers = {"accept": "application/json",
               "authorization": f"Bearer {API_TOKEN}"}
    ids = [i['id'] for i in auths]
    async with aiohttp.ClientSession() as session:
        async with session.delete(url=f'{API_URL}/smartlock/auth', headers=headers, json=ids) as response:
            text_response = await response.text()
            if response.status == 204:
                logger.info(f'auths ({ids}) deleted: (response code: {response.status})')
            else:
                logger.error(f'unable to delete auths ({ids}): (response code: {response.status}) {text_response}')


async def request(uri) -> list:
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Accept": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url=f'{API_URL}/{uri}', headers=headers) as response:
            text_response = await response.json()
            if response.status == 200:
                return text_response
            else:
                raise Exception(
                    f"unable to send request from '{uri}': (response code: {response.status}) {text_response}")


async def get_smartlock() -> dict:
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Accept": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url=f'{API_URL}/smartlock', headers=headers) as response:
            text_response = await response.json()
            if response.status == 200:
                locks = await response.json()
                for lock in locks:
                    if lock.get('name') == NUKI_NAME:
                        logger.debug(f"successfuly got smartlock: (return code: {response.status}) {lock}")
                        return lock
            else:
                logger.error(f"failed to get smartlock: (return code: {response.status}) {text_response}")

    return {}


async def house_keeper():
    try:
        auths: list = await get_auth()
        if not auths:
            return
        for auth in auths:
            expired: bool = await is_expired(auth)
            used: bool = await is_used(auth)
            logger.debug(f'houseleeper: {auth["name"]} - expired: {expired}, used: {used}')
            if expired or used:
                await del_auths(auths=[auth])
    except Exception as e:
        logger.exception(e)


def genetate_otp_code(length=6) -> int:
    _ = ''.join(random.choice('123456789') for _ in range(length))
    return int(_)


def get_time_range() -> tuple:
    now = datetime.utcnow()
    three_hours_from_now = now + timedelta(hours=OTP_LIFETIME_HOURS)
    start_date = now.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    end_date = three_hours_from_now.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    return start_date, end_date


async def is_expired(obj: dict) -> bool:
    try:
        creation_date = obj['creationDate']
        creation_date = datetime.strptime(creation_date, "%Y-%m-%dT%H:%M:%S.%fZ")
        lifetime = datetime.utcnow() - creation_date
        if lifetime.total_seconds() < OTP_LIFETIME_HOURS * 3600:
            return False
        logger.info(f'auth {obj.get("name")} expired')
        return True
    except KeyError:
        return False


async def is_used(obj: dict) -> bool:
    try:
        smartlock = await get_smartlock()
        actions = await request(uri=f'smartlock/{smartlock["smartlockId"]}/log?action=1&authId={obj["id"]}')
        if actions:
            logger.info(f'auth {obj.get("name")} used')
            return True
        return False
    except KeyError:
        return False


async def valid(code):
    try:
        if not code:
            return
        auths = await get_auth()
        for auth in auths:
            if int(code) == auth['code']:
                if not is_used(auth) and not is_expired(auth):
                    return dict(result=True)
        return dict(result=False)
    except Exception as e:
        logger.error(f'general error: {e}')
        return dict(result=e)
