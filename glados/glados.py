# encoding=utf8
import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def create_session():
    try:
        import cloudscraper
        return cloudscraper.create_scraper()
    except ImportError:
        import requests
        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )
        })
        return session


def parse_cookies(cookie_string):
    if cookie_string.startswith("cookie:"):
        cookie_string = cookie_string[len("cookie:"):]
    cookies = {}
    for item in cookie_string.split(";"):
        item = item.strip()
        if "=" in item:
            name, value = item.split("=", 1)
            cookies[name.strip()] = value.strip()
    return cookies


def glados(cookie_string):
    session = create_session()
    cookies = parse_cookies(cookie_string)

    # Get old status
    try:
        status_resp = session.get(
            "https://glados.cloud/api/user/status",
            cookies=cookies,
            timeout=30,
        )
        status_json = status_resp.json()
        old_left_days = int(float(status_json["data"]["leftDays"]))
        print(f"【Status】Old left days:{old_left_days}")
    except Exception as e:
        print(f"Failed to get status: {e}")
        return -2, "Login fails, please check your cookie."

    # Do check-in
    try:
        checkin_resp = session.post(
            "https://glados.cloud/api/user/checkin",
            json={"token": "glados.network"},
            cookies=cookies,
            timeout=30,
        )
        checkin_json = checkin_resp.json()
        checkin_code = checkin_json.get("code", -1)
        checkin_message = checkin_json.get("message", "")
        print(f"【Checkin】{checkin_message}")
    except Exception as e:
        print(f"Failed to checkin: {e}")
        return 2, "Check-in network error."

    if checkin_code == -2:
        return -2, "Login fails, please check your cookie."

    # Get new status
    try:
        status_resp = session.get(
            "https://glados.cloud/api/user/status",
            cookies=cookies,
            timeout=30,
        )
        status_json = status_resp.json()
        left_days = int(float(status_json["data"]["leftDays"]))
        print(f"【Status】Left days:{left_days}")
    except Exception as e:
        print(f"Failed to get new status: {e}")
        left_days = old_left_days

    result_code = 0 if checkin_code == 0 else 2
    message = f"【Status】Left days:{left_days}"
    return result_code, message
