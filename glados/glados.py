# encoding=utf8
import io
import sys
import json
import platform
import subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')

import undetected_chromedriver as uc
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webdriver import By

def get_driver_version():
    system = platform.system()

    if system == "Darwin":
        cmd = r'''/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --version'''
    elif system == "Windows":
        cmd = r'''powershell -command "&{(Get-Item 'C:\Program Files\Google\Chrome\Application\chrome.exe').VersionInfo.ProductVersion}"'''
    else:
        cmd = "google-chrome --version"

    try:
        out, err = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
    except IndexError as e:
        print('Check chrome version failed:{}'.format(e))
        return 0

    text = out.decode("utf-8").strip()
    if system == "Windows":
        out = text.split(".")[0]
    else:
        # Darwin / Linux: "Google Chrome 131.0.6778.264 ..."
        out = text.split(" ")[2].split(".")[0]

    return out

def glados_checkin(driver):
    checkin_url = "https://glados.cloud/api/user/checkin"
    checkin_query = """
        (function (){
        var request = new XMLHttpRequest();
        request.open("POST","%s",false);
        request.setRequestHeader('content-type', 'application/json');
        request.send('{"token": "glados.network"}');
        return request;
        })();
        """ % (checkin_url)
    checkin_query = checkin_query.replace("\n", "")
    resp = driver.execute_script("return " + checkin_query)
    resp = json.loads(resp["response"])
    return resp["code"], resp["message"]

def glados_status(driver):
    status_url = "https://glados.cloud/api/user/status"
    status_query = """
        (function (){
        var request = new XMLHttpRequest();
        request.open("GET","%s",false);
        request.send(null);
        return request;
        })();
        """ % (status_url)
    status_query = status_query.replace("\n", "")
    resp = driver.execute_script("return " + status_query)
    resp = json.loads(resp["response"])
    return resp["code"], resp["data"]

def glados(cookie_string):
    options = uc.ChromeOptions()
    options.add_argument("--disable-popup-blocking")
    if platform.system() == "Linux":
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

    version = get_driver_version()
    driver = uc.Chrome(version_main = int(version), options = options)

    # Load cookie
    driver.get("https://glados.cloud")
      
    if cookie_string.startswith("cookie:"):
        cookie_string = cookie_string[len("cookie:"):]
    cookie_dict = [ 
        {"name": x[:x.find('=')].strip(), "value": x[x.find('=')+1:].strip()} 
        for x in cookie_string.split(';')
    ]

    driver.delete_all_cookies()
    for cookie in cookie_dict:
        if cookie["name"] in ["koa:sess", "koa:sess.sig"]:
            driver.add_cookie({
                "domain": "glados.cloud",
                "name": cookie["name"],
                "value": cookie["value"],
                "path": "/",
            })
    
    driver.get("https://glados.cloud")
    WebDriverWait(driver, 240).until(
        lambda x: x.title != "Just a moment..."
    )
    
    message = str()

    # checkin_code, checkin_message = glados_checkin(driver)
    # if checkin_code == -2: checkin_message = "Login fails, please check your cookie."
    # message = f"{message}【Checkin】{checkin_message}\n"
    # print(f"【Checkin】{checkin_message}")
    status_code, status_data = glados_status(driver)
    old_left_days = int(float(status_data["leftDays"]))
    print(f"【Status】Old left days:{old_left_days}")

    driver.get("https://glados.cloud/console/checkin")
    s_checkin_button = "//div[@class='checkin-main-grid']/div[2]/div[3]/button"
    driver.find_element(By.XPATH, s_checkin_button).click()
    print("【Checkin】Clicked the button")

    s_checkin_content = "//div[@class='checkin-main-grid']/div[2]/div[3]/div[2]/span"
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, s_checkin_content))
    )
    checkin_content = driver.find_element(By.XPATH, s_checkin_content)
    print(f"【Checkin】Message content: {checkin_content.text}")

    checkin_code = 0
    if checkin_code != -2:
        status_code, status_data = glados_status(driver)
        left_days = int(float(status_data["leftDays"]))
        print(f"【Status】Left days:{left_days}")
        message = f"{message}【Status】Left days:{left_days}\n"

        if left_days != old_left_days + 1 and (not "Got" in checkin_content.text):
            checkin_code = 2 # checkin fail

    driver.close()
    driver.quit()

    return checkin_code, message
    
