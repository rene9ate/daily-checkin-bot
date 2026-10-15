# encoding=utf8
import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 设备指纹统一交给 session.py 构造。
# 原来这里直接调 cloudscraper.create_scraper()，它会从
# ['linux','windows','darwin','android','ios'] 里随机抽一个平台当 UA，
# 抽到 darwin 就是 macOS —— 站点会判定「签到设备和登录设备不一致」
# （Signed-in device: Windows / Check-in client: macOS）并拒绝给分。
from session import create_session

# 站点自己的风控话术。命中说明签到被拒、没有发积分，
# 但 API 返回的 code 仍然是 0/1，原逻辑会把它当成功 ——
# 结果是 Actions 一直是绿的，实际一分没拿到。
RISK_CONTROL_MARKERS = (
    "automated check-in detected",
    "different device",
    "sign in again",
)


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

    # 风控命中：站点认定签到客户端与登录设备不一致，本次不发积分。
    # 必须当成失败返回，否则 main.py 会判定为成功、Actions 显示绿色。
    if any(m in checkin_message.lower() for m in RISK_CONTROL_MARKERS):
        return 3, (
            "【风控】站点判定签到客户端与登录设备不一致，本次未发放积分。\n"
            f"【原文】{checkin_message}\n"
            "【处置】确认 session.py 发出的 UA 平台与登录设备一致；"
            "必要时在浏览器里重新登录并更新 cookie。"
        )

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

    result_code = 0 if checkin_code != -2 else -2
    message = f"【Status】Left days:{left_days}"
    return result_code, message
