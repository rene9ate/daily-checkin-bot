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

# 签到接口的返回码语义（2026-10-21 对 glados.cloud 实测）：
#   0  本次签到成功，points 为本次获得的积分
#   1  今天已经签过，幂等成功，points=0
#      原文 "Today's observation logged. Return tomorrow for more points."
#  -2  未登录 / cookie 失效（"没有权限"）
# 其余值一律视为「无法确认签到结果」，按失败上报。
# 注意：checkin_json.get("code", -1) 拿不到 code 时默认是 -1，
# 旧写法 `0 if checkin_code != -2 else -2` 会把 -1 也映射成 0（成功），
# 于是接口改版 / 返回结构异常时 Actions 变绿，实际一次都没签到。
SUCCESS_CODES = (0, 1)

# 未预期的返回码。main.py 里只有 0/1 算成功，其余都会让 job 失败。
CODE_UNEXPECTED = 4


def parse_cookies(cookie_string):
    # 原写法只认小写 "cookie:"。从 DevTools「Copy as cURL」或某些导出工具
    # 拿到的是大写 "Cookie:"，匹配不上会让第一个 cookie 的名字变成
    # "Cookie:gld:sess"，服务端认不出来，直接回 {"code":-2,"message":"没有权限"}。
    if cookie_string[:7].lower() == "cookie:":
        cookie_string = cookie_string[7:]
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
        checkin_points = checkin_json.get("points", None)
        checkin_message = checkin_json.get("message", "")
        print(f"【Checkin】{checkin_message}")
        print(f"【Checkin】code={checkin_code} points={checkin_points}")
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

    # 只有 0 / 1 才算「确认签到成功」。其余返回码（含拿不到 code 时的 -1、
    # 以及将来站点新增的错误码）一律上报失败，不再静默当成成功。
    if checkin_code not in SUCCESS_CODES:
        return CODE_UNEXPECTED, (
            "【异常返回】签到接口返回了未预期的 code，无法确认是否发放积分。\n"
            f"【原文】code={checkin_code} points={checkin_points} message={checkin_message}\n"
            "【处置】多半是站点接口改版或风控换了话术，先手动登录网页确认，"
            "再对照本文件的 SUCCESS_CODES / RISK_CONTROL_MARKERS 更新判定规则。"
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

    # 保留站点原始返回码：0 = 本次新签到并发了积分，1 = 今天已经签过。
    # main.py 两者都认，返回原值比统一压成 0 更有信息量。
    message = f"【Status】Left days:{left_days}"
    return checkin_code, message
