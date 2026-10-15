# encoding=utf8
"""GLaDOS 签到用的 HTTP session 工厂 —— 修掉「签到设备被识别成 macOS」的根因。

【站点给出的原始报错，就是这个 bug 的指纹】

    Automated check-in detected
    Today's check-in request came from a different device/client
    than the one you signed in with:
        Signed-in device   Windows
        Check-in client    macOS
    Points were NOT awarded.

【为什么会变成 macOS】

原来的 glados/glados.py 是这么写的：

    def create_session():
        try:
            import cloudscraper
            return cloudscraper.create_scraper()
        ...

cloudscraper 在没显式传 browser / platform 时，内部会执行
（cloudscraper/user_agent/__init__.py）：

    self.platforms = ['linux', 'windows', 'darwin', 'android', 'ios']
    ...
    if not self.platform:
        self.platform = random.SystemRandom().choice(self.platforms)
    ...
    self.headers['User-Agent'] = random.SystemRandom().choice(filteredAgents[self.browser])

**每次新建 session，平台、浏览器、UA 全是随机抽的。**
darwin 就是 macOS。本地实测 40 次的分布：

    darwin (macOS)   12/40
    android           9/40
    linux             8/40
    windows           6/40
    ios               5/40

你在 Win11 浏览器上取的 cookie，配上脚本随机自称 macOS 的请求，
站点一比对就是「设备突变」，于是判定为脚本、不给分。

【这个文件做四件事】

1. 首选 curl_cffi：复刻真实 Chrome 的 TLS(JA3/JA4) + HTTP/2 + 头部顺序指纹。
   glados.cloud 挂在 Cloudflare 后面（响应头 Server: cloudflare），
   Cloudflare Bot Management 恰恰靠这些指纹识别脚本。
   注意：换 runner 的操作系统**改不了这一层**，因为 Python 的 TLS 栈没变。
2. 把 UA 钉死成 Windows，并让 Sec-Ch-Ua-Platform 跟着 UA 自动同步。
   curl_cffi 的 impersonate="chrome" 默认发的是 **macOS 的 UA**，
   而且 Sec-Ch-Ua-Platform 也是 "macOS"，两个都必须改掉 ——
   否则 Windows 的 UA 配 macOS 的 Client Hints，矛盾比不改还明显。
3. 兜底闸门：如果最终 UA 又被解析成 macOS / Linux / Android / iOS，
   直接抛错让任务失败，避免重蹈覆辙（宁可当天不签到，也别再被标记一次）。
4. 剔除 cf_clearance 这类跟「生成时的 IP」绑定的 Cloudflare cookie。

【关于 GLADOS_UA：默认不要设】

  设计原则是「UA 的版本号永远跟着 TLS 指纹的版本走」，所以 GLADOS_UA
  只用来告诉脚本你在哪个平台、用哪个浏览器，版本号交给 curl_cffi 决定。

  为什么不让它写死完整 UA：curl_cffi 的 impersonate 决定了 TLS 指纹是哪个
  Chrome 版本。如果你把 UA 写成 Chrome/141 而 TLS 伪装的是 Chrome/150，
  就制造出「UA 说 141、Client Hints 说 150」的新矛盾 —— 比不改更糟。

  所以：能匹配到 curl_cffi 支持的版本就精确匹配；匹配不到就就近降级，
  并把 UA 的版本号一起改掉，保证 UA / Client Hints / TLS 三者始终自洽。

  用法（可选）：
      本地:            set GLADOS_UA=<浏览器 F12 里复制的 UA>
      GitHub Actions:  secrets 里加 GLADOS_UA，workflow 的 env 里传进去

【怎么接进现有代码】

  requirements.txt 加一行：   curl_cffi

  glados/glados.py：
      删掉原来的 create_session() 整个函数，改成：
          from session import create_session

  glados/main.py：
      在 `for idx, cookie in enumerate(cookie_string):` 循环体第一行加：
          cookie = strip_ip_bound_cookies(cookie)

  自检：  python session.py
"""

from __future__ import annotations

import os
import re

# --------------------------------------------------------------------------
# 钉死的浏览器指纹
# --------------------------------------------------------------------------
ACCEPT_LANGUAGE = "zh-CN,zh;q=0.9,en;q=0.8"

# 只用于「没有 curl_cffi」时的兜底
FALLBACK_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)

# 会让站点把你判定成「换了设备」的平台关键字。
# 出现这些说明又退回了随机 UA 的老路，必须让任务失败而不是硬着头皮签到。
BAD_PLATFORM_MARKERS = {
    "macos": ("macintosh", "mac os x"),
    "linux": ("x11; linux",),
    "android": ("android",),
    "ios": ("iphone", "ipad"),
}

# Cloudflare 下发的、与生成时 IP 绑定的 cookie。
# 换个出口 IP 再用，轻则无效重则触发验证，必须丢掉。
IP_BOUND_COOKIES = frozenset({
    "cf_clearance",
    "__cf_bm",
    "_cfuvid",
    "cf_chl_2",
    "cf_chl_prog",
    "cf_chl_seq",
})


def platform_from_ua(ua: str):
    """从 UA 里推断平台名，用来填 Sec-Ch-Ua-Platform。"""
    u = (ua or "").lower()
    if "windows" in u:
        return "Windows"
    if "android" in u:                 # Android 的 UA 里也含 "linux"，必须先判
        return "Android"
    if "iphone" in u or "ipad" in u:   # iOS 的 UA 里含 "like Mac OS X"，也要先判
        return "iOS"
    if "macintosh" in u or "mac os x" in u:
        return "macOS"
    if "linux" in u:
        return "Linux"
    return None


def _chrome_major(ua: str):
    m = re.search(r"Chrome/(\d+)", ua or "")
    return m.group(1) if m else None


def _windows_chrome_ua(major: str) -> str:
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
    )


def _supported_chrome_targets():
    """curl_cffi 支持的 chromeNN 目标，返回 {主版本号: 目标名}。"""
    try:
        from curl_cffi.requests.impersonate import BrowserType
    except ImportError:
        return {}
    out = {}
    for e in BrowserType:
        v = e.value
        suffix = v[len("chrome"):]
        if v.startswith("chrome") and suffix.isdigit():
            out[int(suffix)] = v
    return out


def _pick_target(requested_major):
    """挑一个 curl_cffi 支持的 impersonate 目标，尽量贴近请求的版本号。

    返回 (目标名, 该目标的主版本号, 降级说明或 None)。
    """
    targets = _supported_chrome_targets()
    if not targets:
        return "chrome", None, None

    if requested_major is None:
        # 没指定就跟随 curl_cffi 的默认（当前 chrome150）
        from curl_cffi.requests.impersonate import DEFAULT_CHROME
        name = DEFAULT_CHROME
    else:
        n = int(requested_major)
        if n in targets:
            name = targets[n]
        else:
            lower = [k for k in targets if k <= n]
            name = targets[max(lower)] if lower else "chrome"

    actual = "".join(c for c in name if c.isdigit())
    note = None
    if requested_major is not None and actual and actual != str(requested_major):
        note = f"curl_cffi 没有 chrome{requested_major}，就近降级到 {name}"
    return name, actual, note


def strip_ip_bound_cookies(cookie_string: str) -> str:
    """去掉与 IP 绑定的 Cloudflare cookie，其余 cookie 原样保留。"""
    kept = []
    for item in cookie_string.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        name = item.split("=", 1)[0].strip()
        if name in IP_BOUND_COOKIES:
            print(f"[session] 丢弃 IP 绑定 cookie: {name}")
            continue
        kept.append(item)
    return "; ".join(kept)


def _guard(ua: str) -> None:
    """兜底闸门：UA 一旦被解析成非 Windows，直接失败，别再被站点标记一次。"""
    u = (ua or "").lower()
    for plat, markers in BAD_PLATFORM_MARKERS.items():
        if any(m in u for m in markers):
            raise RuntimeError(
                f"UA 被解析为 {plat}，与登录设备（Windows）不一致，"
                f"继续签到只会再吃一次「Automated check-in detected」。"
                f"实际 UA: {ua}"
            )


def create_session():
    """返回一个像真 Chrome（Windows）的 session，首选 curl_cffi。"""

    # ---- 首选：curl_cffi，能复刻 Chrome 的 TLS + HTTP/2 指纹 ----
    try:
        from curl_cffi import requests as curl_requests

        env_ua = os.environ.get("GLADOS_UA") or ""
        requested_major = _chrome_major(env_ua) if env_ua else None
        target, actual_major, note = _pick_target(requested_major)

        # UA 的版本号统一从 impersonate 目标推导，保证 UA / Client Hints / TLS
        # 三者永远说的是同一个 Chrome 版本，不会自相矛盾。
        ua = _windows_chrome_ua(actual_major or "150")

        session = curl_requests.Session(impersonate=target)
        # 这两行是关键：curl_cffi 默认发 macOS 的 UA + macOS 的 Client Hints
        session.headers["User-Agent"] = ua
        session.headers["Sec-Ch-Ua-Platform"] = '"Windows"'
        session.headers["Accept-Language"] = ACCEPT_LANGUAGE

        print(f"[session] curl_cffi impersonate={target}（TLS/h2 即 Chrome{actual_major}）")
        print(f"[session] UA     = {ua}")
        print("[session] 平台   = Windows（Client Hints 已同步）")
        if note:
            print(f"[session] 注意：{note}；UA 版本号已一起改成 {actual_major}，"
                  f"保持与 TLS 指纹一致")
        env_plat = platform_from_ua(env_ua)
        if env_plat and env_plat != "Windows":
            print(f"[session] 注意：GLADOS_UA 声明平台为 {env_plat}，"
                  f"但签到仍按 Windows 发送")

        _guard(ua)
        return session
    except ImportError:
        print("[session] 未装 curl_cffi，退化到 cloudscraper（TLS 指纹仍是 Python 的）")

    # ---- 次选：cloudscraper，但钉死 windows，禁止随机漂移 ----
    try:
        import cloudscraper

        session = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        ua = os.environ.get("GLADOS_UA") or session.headers.get("User-Agent", "")
        session.headers["User-Agent"] = ua
        session.headers["Accept-Language"] = ACCEPT_LANGUAGE
        print(f"[session] cloudscraper platform=windows, UA={ua}")
        _guard(ua)
        return session
    except ImportError:
        pass

    # ---- 兜底：纯 requests ----
    import requests

    ua = os.environ.get("GLADOS_UA") or FALLBACK_UA
    session = requests.Session()
    session.headers.update({
        "User-Agent": ua,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": ACCEPT_LANGUAGE,
    })
    print(f"[session] requests, UA={ua}")
    _guard(ua)
    return session


def _self_check() -> None:
    """打印实际发到服务端的指纹，并连跑 5 次确认不再漂移。"""
    print("=" * 68)
    print("1) 连跑 5 次，确认平台不再随机漂移")
    print("=" * 68)
    for i in range(5):
        s = create_session()
        ua = s.headers.get("User-Agent") or "(请求时装配)"
        bad = "  <-- 又是 Mac！" if "Macintosh" in ua else ""
        print(f"  #{i + 1} {ua}{bad}")

    print()
    print("=" * 68)
    print("2) 实测服务端看到的指纹 + 一致性自查（需要联网）")
    print("=" * 68)
    try:
        s = create_session()
        d = s.get("https://httpbin.org/headers", timeout=20).json()["headers"]
        for k in ("User-Agent", "Sec-Ch-Ua", "Sec-Ch-Ua-Platform",
                  "Sec-Ch-Ua-Mobile", "Accept-Language"):
            print(f"  {k}: {d.get(k)}")
        ua = d.get("User-Agent") or ""
        chu = d.get("Sec-Ch-Ua") or ""
        ua_major = _chrome_major(ua)
        m = (re.search(r'Google Chrome";v="(\d+)', chu) or
             re.search(r'Chromium";v="(\d+)', chu))
        chu_major = m.group(1) if m else None
        print()
        print(f"  一致性自查: UA 版本={ua_major} / Client Hints 版本={chu_major} / "
              f"平台={d.get('Sec-Ch-Ua-Platform')}")
        if ua_major and chu_major and ua_major != chu_major:
            print("  !! UA 与 Client Hints 版本不一致，需要修")
        else:
            print("  通过：三者说的是同一个 Chrome 版本，且平台是 Windows")
    except Exception as e:
        print(f"  联网探测跳过（{type(e).__name__}: {e}）")

    print()
    print("=" * 68)
    print("3) cookie 过滤")
    print("=" * 68)
    demo = "koa=abc; cf_clearance=xyz; __cf_bm=q1; token=keep"
    print(f"  输入: {demo}")
    print(f"  输出: {strip_ip_bound_cookies(demo)}")

    print()
    print("=" * 68)
    print("4) 兜底闸门自测（模拟随机到 macOS 的情况）")
    print("=" * 68)
    try:
        _guard("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/150.0.0.0")
        print("  闸门失效！")
    except RuntimeError as e:
        print(f"  闸门正常拦截: {str(e)[:56]}...")

    print()
    print("=" * 68)
    print("5) GLADOS_UA 版本对齐自测")
    print("=" * 68)
    for want in (None, "141", "999", "150"):
        t, a, n = _pick_target(want)
        print(f"  请求 Chrome/{want or '(默认)'} -> impersonate={t}, "
              f"UA 版本={a}, {n or '精确匹配'}")


if __name__ == "__main__":
    _self_check()
