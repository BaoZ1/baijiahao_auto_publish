from selenium import webdriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pypandoc
import requests
import json
import time
import os
from copy import copy
from pathlib import Path
from typing import overload, Sequence, Callable, Any
from PIL import Image
from io import BytesIO
import base64
from difflib import SequenceMatcher
import inquirer
import toml
import logging
from selenium.webdriver.remote.remote_connection import LOGGER
import shutil
import zipfile
import math
import random

# pyinstaller main.py --onefile --copy-metadata readchar


try:
    config = toml.load("config.toml")

    TOOLS_PATH = Path(config["tools_path"])
    CHROME_DRIVER_PATH = TOOLS_PATH / "chromedriver.exe"
    assert CHROME_DRIVER_PATH.exists()

    PANDOC_PATH = TOOLS_PATH / "pandoc.exe"
    assert PANDOC_PATH.exists()
    os.environ["PYPANDOC_PANDOC"] = str(PANDOC_PATH)

    DEBUG = config["debug"]

    BJH_URL = "https://baijiahao.baidu.com"
    BJH_NEW_EDIT_URL = "https://baijiahao.baidu.com/builder/rc/edit?type=news"
    BJH_CONTENT_URL = "https://baijiahao.baidu.com/builder/rc/content"

    FRONTEND_URL = config["frontend_url"]

    DETAYUN_KEY = config["detayun_key"]

    COOKIE_FOLDER = Path(config["cookie_folder"])
    if not COOKIE_FOLDER.exists():
        COOKIE_FOLDER.mkdir()

    TEMP_FOLDER = Path(config["temp_folder"])
    if not TEMP_FOLDER.exists():
        TEMP_FOLDER.mkdir()

    SHOW_WINDOW = config["show_window"]
except Exception as e:
    print(f"初始化失败：{e}")
    os.system("pause")
    exit()

driver: webdriver.Chrome | None = None
main_window_handle: str | None = None


class FindElementGenericTimeoutException(Exception):
    def __repr__(self) -> str:
        return "目标元素长时间未找到"


def find_element(
    by: By, value: str, root: WebElement | None = None, timeout: float | None = None
):
    t = time.time()
    while True:
        try:
            res = (root or driver).find_element(by, value)
        except:
            if DEBUG:
                print(f"element not found: {value} by {by} in {root}")
            if timeout is not None and (timeout == 0 or time.time() - t >= timeout):
                return None
            if timeout is None and time.time() - time > 20:
                raise FindElementGenericTimeoutException()
            time.sleep(0.5)
        else:
            if DEBUG:
                print(f"element {res} found: {value} by {by} in {root}")
            return res


def find_elements(
    by: By, value: str, root: WebElement | None = None, timeout: float | None = None
):
    t = time.time()
    while True:
        res = (root or driver).find_elements(by, value)
        if len(res) == 0:
            if DEBUG:
                print(f"element not found: {value} by {by} in {root}")
            if timeout is not None and (timeout == 0 or time.time() - t >= timeout):
                return None
            if timeout is None and time.time() - time > 20:
                raise FindElementGenericTimeoutException()
            time.sleep(0.5)
        else:
            if DEBUG:
                print(f"element {res} found: {value} by {by} in {root}")
            return res


def find_element_options(
    options: Sequence[tuple[By, str] | tuple[By, str, WebElement]],
    timeout: float | None = None,
):
    t = time.time()
    while True:
        for i, option in enumerate(options):
            res = find_element(*option, timeout=0)
            if res:
                return i, res
        if timeout is not None and (timeout == 0 or time.time() - t >= timeout):
            return None
        time.sleep(0.5)


@overload
def click_element(
    by: By, value: str, *, scroll: bool = True, timeout: float | None = None
) -> None: ...
@overload
def click_element(
    element: WebElement, *, scroll: bool = True, timeout: float | None = None
) -> None: ...


def click_element(*args, **kwargs) -> None:
    element = args[0] if isinstance(args[0], WebElement) else find_element(*args)
    kwargs.setdefault("scroll", True)
    kwargs.setdefault("timeout", None)
    if kwargs["timeout"]:
        WebDriverWait(driver, kwargs["timeout"]).until(
            EC.element_to_be_clickable(element)
        )
    while True:
        try:
            if kwargs["scroll"]:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'})", element
                )
            element.click()
        except:
            time.sleep(0.5)
        else:
            if DEBUG:
                print(f"element clicked: {element}")
            time.sleep(0.5)
            return


class Driver:
    def __init__(self, driver: webdriver.Chrome):
        self.__driver = driver

    def __enter__(self):
        global driver
        driver = self.__driver

    def __exit__(self, type, value, traceback):
        global driver
        driver = None
        self.__driver.quit()

    def content(self):
        return self.__driver


def create_driver(headless: bool = True, remain_browser: bool = False):
    # 禁止将日志消息输出到控制台
    LOGGER.setLevel(logging.CRITICAL)
    logging.disable(logging.CRITICAL)
    options = webdriver.ChromeOptions()
    options.page_load_strategy = "eager"
    if headless:
        options.add_argument("--headless")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-infobars")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--ignore-ssl-errors")
    options.add_argument("--log-level=3")
    options.add_argument("--disable-logging")
    options.add_argument("--disable-crash-reporter")
    options.add_argument("--output=/dev/null")
    options.add_experimental_option(
        "excludeSwitches",
        ["enable-automation", "enable-remote-debugging"],
    )
    if remain_browser:
        options.add_experimental_option("detach", True)

    service = webdriver.ChromeService(CHROME_DRIVER_PATH, log_output=os.devnull)
    _driver = webdriver.Chrome(options, service)
    # _driver.execute_cdp_cmd(
    #     "Page.addScriptToEvaluateOnNewDocument",
    #     {"source": open("stealth.min.js").read()},
    # )
    return Driver(_driver)


def get_cookies(username: str):
    driver.get(BJH_URL)
    find_element(By.CLASS_NAME, "btnlogin--bI826").click()
    find_element(By.CLASS_NAME, "author-avatar")
    cookie_file = COOKIE_FOLDER / username
    if not cookie_file.exists():
        cookie_file.touch()
    json.dump(driver.get_cookies(), cookie_file.open("w"))


class CookieExpiredException(Exception):
    pass


def login(cookie_file: Path):
    if not cookie_file.exists():
        print(f"cookie file: {cookie_file.name} not found")
        exit()
    driver.get(BJH_URL)
    for cookie in json.load(open(cookie_file, "r")):
        driver.add_cookie(cookie)
    driver.get(BJH_URL)
    # time.sleep(2)
    if (
        find_element_options(
            [
                (By.CLASS_NAME, "btnlogin--bI826"),
                (By.CLASS_NAME, "author-avatar"),
            ]
        )[0]
        == 0
    ):
        raise CookieExpiredException()


def upload_img(img_url: str):
    find_element(By.CLASS_NAME, "edui-for-insertimage").click()
    find_element(
        By.CSS_SELECTOR, "[data-urlkey='news-点击-localUpload-pv/uv']"
    ).send_keys(img_url)
    time.sleep(1)
    find_element(By.XPATH, "//button[span[text()='确 认']]").click()


def get_article(username: str) -> tuple[dict, dict]:
    response = requests.get(
        f"{FRONTEND_URL}/api/articleInfo/getSingleArticle",
        params={"id": username},
    ).json()
    data = response["data"]
    if response["code"] in (1,):
        print(response["msg"])
    return data["article"], data["temp"]


def filter_file_name(s: str):
    return "".join(filter(lambda c: c not in '/\\:*?"<>|', s))


def compress_docx_img(docx_path: Path):
    temp_folder = TEMP_FOLDER / "temp_docx_content"
    file = zipfile.ZipFile(docx_path)
    file.extractall(temp_folder)
    img_folder = temp_folder / "word" / "media"
    for img_file in img_folder.glob("*"):
        try:
            img = Image.open(img_file)
        except Exception as e:
            print(f"无法解析：{e}")
            continue
        w, h = img.size
        if w <= 400 or h <= 300:
            continue
        ratio = w / h
        if ratio > 400 / 300:
            img = img.resize((math.ceil(ratio * 300), 300))
        else:
            img = img.resize((400, math.ceil(400 / ratio)))
        img.save(img_file)
    with zipfile.ZipFile(docx_path, "w") as zf:
        for f in temp_folder.rglob("*"):
            zf.write(f, f.relative_to(temp_folder))
    shutil.rmtree(temp_folder)


def save_docx(article: dict):
    file_name = filter_file_name(article["title"])
    html_file = TEMP_FOLDER / f"{file_name}.html"
    docx_file = TEMP_FOLDER / f"{file_name}.docx"
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(article["content"].replace("/api", f"{FRONTEND_URL}/api"))
    try:
        pypandoc.convert_file(html_file, "docx", outputfile=docx_file)
    except RuntimeError:
        raise Exception(f"wrong html file: {html_file}")
    except OSError:
        raise Exception("pandoc not found")
    else:
        if (docx_size := docx_file.stat().st_size) > 1e7:
            print(f"docx文档过大({docx_size}Byte)，压缩图片中...")
            compress_docx_img(docx_file)
        article["path"] = str(docx_file.resolve())


def clean_temp_folder():
    for file_path in TEMP_FOLDER.glob("*.*"):
        os.remove(file_path)


def select_covers(covers_idx: list[int], main_cover_idx: int):
    three_cover_radio = find_element(
        By.CSS_SELECTOR, '.cheetah-radio-input[value="three"]'
    )

    click_element(three_cover_radio)
    img_views = driver.find_elements(By.CLASS_NAME, "bjh-image-view")

    click_element(img_views[0])
    img_items = driver.find_elements(By.CLASS_NAME, "item")
    for idx in covers_idx:
        click_element(img_items[idx])
    click_element(By.XPATH, "//button[span[text()='确 认']]")

    print("等待竖版封面生成...")
    find_element(By.CSS_SELECTOR, ".cover-list-one .bjh-image-box")
    if len(covers_idx) == 0 or main_cover_idx != covers_idx[0]:
        click_element(
            By.XPATH, "//div[contains(@class, 'cover-list-one')]//span[text()='更换']"
        )
        click_element(driver.find_elements(By.CLASS_NAME, "item")[main_cover_idx])
        click_element(By.XPATH, "//button[span[text()='确 认']]")


def PIL_base64(img: Image.Image, coding="utf-8"):
    img_format = img.format or "JPEG"

    format_str = "JPEG"
    if "png" == img_format.lower():
        format_str = "PNG"
    if "gif" == img_format.lower():
        format_str = "gif"

    if img.mode == "P":
        img = img.convert("RGB")
    if img.mode == "RGBA":
        format_str = "PNG"
        img_format = "PNG"

    output_buffer = BytesIO()
    img.save(output_buffer, quality=100, format=format_str)
    byte_data = output_buffer.getvalue()
    base64_str = (
        "data:image/"
        + img_format.lower()
        + ";base64,"
        + base64.b64encode(byte_data).decode(coding)
    )

    return base64_str


def handle_spiner():
    print("正在处理验证码...")
    img_link = find_element(By.CLASS_NAME, "passMod_spin-background").get_attribute(
        "src"
    )
    img_data = requests.get(
        img_link,
        headers={
            "Host": "passport.baidu.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:72.0) Gecko/20100101 Firefox/72.0",
            "Accept": "image/webp,*/*",
            "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Referer": "https://wappass.baidu.com/static/captcha/tuxing.html?&ak=c27bbc89afca0463650ac9bde68ebe06&backurl=https%3A%2F%2Fwww.baidu.com%2Fs%3Fcl%3D3%26tn%3Dbaidutop10%26fr%3Dtop1000%26wd%3D%25E6%25B6%2588%25E9%2598%25B2%25E6%2588%2598%25E5%25A3%25AB%25E8%25BF%259E%25E5%25A4%259C%25E7%25AD%2591%25E5%259D%259D%25E5%25BA%2594%25E5%25AF%25B9%25E6%25B4%25AA%25E5%25B3%25B0%25E8%25BF%2587%25E5%25A2%2583%26rsv_idx%3D2%26rsv_dl%3Dfyb_n_homepage%26hisfilter%3D1&logid=8309940529500911554&signature=4bce59041938b160b7c24423bde0b518&timestamp=1624535702",
            "Cookie": "BAIDUID=A0621DC238F4D936B38F699B70A7E41F:SL=0:NR=10:FG=1; BIDUPSID=A0621DC238F4D9360CD42C9C31352635; PSTM=1667351865; HOSUPPORT=1; UBI=fi_PncwhpxZ%7ETaKAanh2ue0vFk6vHMY02DgvigILJIFul8Z1nzMr9do3SYLtjAUqHSpUz7LvOKV27cIr18-YJryP0Q8j92oo93%7E6hGa0CLdraAlaHUZG-0PW9QrpZkW7MTyUn-yrAq7OmSRBIJ7%7E8gM9pv-; USERNAMETYPE=2; SAVEUSERID=3cd458184c56c2fe28174e594101f074d63463446d; HISTORY=0ece87e30ec8ecccd52ff3d5c42f98002a893bfb73ff358893; BDUSS_BFESS=NOcWd6YWJRbmFVUVBBaWVkaHJNSm5tRUpUaUVMaTNHOHcwZVVaVDdsYXlLZmxrSVFBQUFBJCQAAAAAAAAAAAEAAAC13Mct0KHQwl9keHkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAALKc0WSynNFkRD; H_WISE_SIDS=219946_216846_213346_219942_213039_230178_204909_230288_110085_236307_243888_244730_245412_243706_232281_249910_247148_250889_249892_252577_234296_253427_253705_240590_254471_179345_254689_254884_254864_253213_255713_254765_255939_255959_255982_107317_256062_256093_256083_255803_253993_256257_255661_256025_256223_256439_256446_254831_253151_256252_256196_256726_256739_251973_256230_256611_256996_257068_257079_257047_254075_257110_257208_251196_254144_257290_251068_256095_257287_254317_251059_251133_254299_257454_257302_255317_255907_255324_257481_244258_257582_257542_257503_255177_257745_257786_257937_257167_257904_197096_257586_257402_255231_257790_258193_258248_258165_8000084_8000115_8000114_8000126_8000140_8000149_8000166_8000172_8000178_8000181_8000185_8000204; ZFY=SxMcCdU3pSsmienZSgA2BTmHLR9S6caVmiP5Ic:Awuz0:C; BAIDUID_BFESS=A0621DC238F4D936B38F699B70A7E41F:SL=0:NR=10:FG=1; Hm_lvt_90056b3f84f90da57dc0f40150f005d5=1690961642,1692328306; STOKEN=01dbff3d6ff696219b39c9fb730c31c34e032c0eebff4fe535d2f1dde0c7b45b; BDUSS=NOcWd6YWJRbmFVUVBBaWVkaHJNSm5tRUpUaUVMaTNHOHcwZVVaVDdsYXlLZmxrSVFBQUFBJCQAAAAAAAAAAAEAAAC13Mct0KHQwl9keHkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAALKc0WSynNFkRD; PTOKEN=92e828db8120372a7baa2557ea4ec476; MAWEBCUID=web_VYfxPuQDaKjEzVgXMFgoHouACkpXyjcDpcWwhATKqELuuwEtNy; __bid_n=18a4ab547aa11525d249ea",
        },
    ).content
    img = Image.open(BytesIO(img_data))
    res = requests.post(
        "http://www.detayun.cn/openapi/verify_code_identify/",
        json={
            "key": DETAYUN_KEY,
            "verify_idf_id": "26",
            "img_base64": PIL_base64(img),
            "img_byte": None,
            "words": "",
        },
        headers={"Content-Type": "application/json"},
    )

    degree = int(
        res.json()["data"]["res_str"].replace("顺时针旋转", "").replace("度", "")
    )
    btn = find_element(By.CLASS_NAME, "passMod_slide-btn")
    action = webdriver.ActionChains(driver)
    action.click_and_hold(btn).perform()
    action.move_by_offset(degree * 0.661, 0).perform()
    action.release().perform()


def clean_editor():
    title_textarea = find_element(
        By.CSS_SELECTOR, ".client_pages_edit_components_titleInput textarea"
    )
    WebDriverWait(driver, 999).until(EC.element_to_be_clickable(title_textarea))
    title_textarea.click()
    title_textarea.send_keys(Keys.CONTROL, "a")
    title_textarea.send_keys(Keys.DELETE)

    content_body = find_element(By.ID, "ueditor_0")
    content_body.click()
    content_body.send_keys(Keys.CONTROL, "a")
    content_body.send_keys(Keys.DELETE)

    while remove_btn := find_element(
        By.CSS_SELECTOR, ".bjh-image-box .op-remove", timeout=0
    ):
        driver.execute_script("arguments[0].style='display: block'", remove_btn)
        click_element(remove_btn)
        time.sleep(2)

    click_element(By.CSS_SELECTOR, ".abstract-row .cheetah-input-clear-icon")


class PostLimitedException(Exception):
    pass


def post_article(
    docx_path: str,
    title: str,
    covers_idx: list[int],
    main_cover_idx: int,
    is_modifying: bool = False,
):
    publish_btn = find_element(By.XPATH, "//div[div[text()='发布']]//button")
    if not is_modifying:
        if not publish_btn.is_enabled():
            raise PostLimitedException("发布按钮不可用")

    import_btn = find_element(By.CSS_SELECTOR, ".edui-for-importdoc.edui-button")

    driver.execute_script("arguments[0].scrollIntoView()", import_btn)
    click_element(import_btn)
    time.sleep(1)
    print(f"上传文档：{docx_path}")
    while True:
        find_element(By.CSS_SELECTOR, ".import-doc-modal input").send_keys(docx_path)
        if find_element(
            By.XPATH,
            "//span[contains(@class, 'cheetah-upload')]//*[contains(text(), '上传中')]",
            timeout=1,
        ):
            break

    print("修改标题...")
    title_textarea = find_element(
        By.CSS_SELECTOR, ".client_pages_edit_components_titleInput textarea"
    )

    WebDriverWait(driver, 999).until(EC.element_to_be_clickable(title_textarea))
    click_element(title_textarea)
    time.sleep(1)
    title_textarea.send_keys(Keys.CONTROL, "a")
    title_textarea.send_keys(Keys.DELETE)
    title_textarea.send_keys(title)

    print("设置封面...")
    select_covers(covers_idx, main_cover_idx)
    print("封面设置完成")

    while True:
        if random.randint(0, 1):
            driver.execute_script("arguments[0].click()", publish_btn)
        else:
            click_element(publish_btn)
        # click_element(publish_btn)
        while msg := find_element(
            By.XPATH,
            "//div[@class='cheetah-message']//span[2][not(text()='文章发布成功')]",
            timeout=1,
        ):
            print(f"发布被拦截，消息：{msg.text}")
            if "请勿修改过多内容" in msg.text:
                raise Exception("被制裁辣！！")
            time.sleep(15)
            click_element(publish_btn)

        if find_element_options(
            [(By.CLASS_NAME, "view-status"), (By.CLASS_NAME, "passMod_slide-btn")],
            timeout=3,
        ):
            break

    while True:
        idx, ele = find_element_options(
            [(By.CLASS_NAME, "view-status"), (By.CLASS_NAME, "passMod_slide-btn")]
        )
        if idx == 0:
            print("无验证码")
            break
        else:
            handle_spiner()
            time.sleep(5)

    click_element(By.CLASS_NAME, "view-status", timeout=2)


def get_article_content_item(title: str):
    while not (items := find_elements(By.CLASS_NAME, "article-info", timeout=8)):
        driver.get(BJH_CONTENT_URL)

    for item in items:
        item_title = find_element(By.XPATH, f".//div/div/a", item).text
        if SequenceMatcher(None, title, item_title).ratio() > 0.7:
            return item
    raise Exception("target_item not found")


def check_article_status(title: str) -> bool:
    target_item = get_article_content_item(title)
    tag = find_element(
        By.CLASS_NAME,
        "client_pages_content_v2_components_articleTags_createTag",
        target_item,
    )
    match tag.text:
        case "审核中":
            # print(f"《{title}》审核中...")
            return False
        case "已发布":
            # print(f"《{title}》已发布")
            return True
        case tag_text:
            raise Exception(f"《{title}》状态异常（{tag_text}）")


def withdraw_and_into_editor(article: dict):
    driver.get(BJH_CONTENT_URL)
    target_item = get_article_content_item(article["title"])

    while not find_element(By.XPATH, "//button[span[text()='确 定']]", timeout=0):
        print("正在执行撤回操作...")
        while not find_element(By.CLASS_NAME, "withDropDown-popover", timeout=0):
            print("弹出菜单...")
            webdriver.ActionChains(driver).move_to_element(
                find_element(
                    By.CLASS_NAME,
                    "client_pages_content_v2_components_data2action_actions_withDropDown",
                    target_item,
                )
            ).pause(1).move_by_offset(-500, 0).perform()
        popup = find_element(By.CLASS_NAME, "withDropDown-popover")
        time.sleep(2)
        driver.execute_script(
            "arguments[0].style = 'left: 467px; top: 60px; transform-origin: 50% -4px; display: block'",
            popup,
        )
        time.sleep(0.5)
        click_element(
            find_element(
                By.CLASS_NAME,
                "client_pages_content_v2_components_data2action_actions_withdraw",
                popup,
            )
        )
        time.sleep(0.5)

    click_element(By.XPATH, "//button[span[text()='确 定']]")
    print(f"《{article['title']}》已撤回")
    requests.put(
        f"{FRONTEND_URL}/api/tempArticle/tempArticleWithdrawn",
        params={"article": article["ID"]},
    )
    click_element(
        By.XPATH,
        f"//div[contains(@class, 'article-info')][div/div/a[text()='{article['title']}']]//span[text()='修改']",
    )
    WebDriverWait(driver, 30).until(EC.number_of_windows_to_be(2))
    for handle in driver.window_handles:
        if handle != driver.current_window_handle:
            driver.close()
            driver.switch_to.window(handle)


def withdraw(title: str):
    driver.get(BJH_CONTENT_URL)
    target_item = get_article_content_item(title)

    while not find_element(By.XPATH, "//button[span[text()='确 定']]", timeout=0):
        print("正在执行撤回操作...")
        while not find_element(By.CLASS_NAME, "withDropDown-popover", timeout=0):
            print("弹出菜单...")
            webdriver.ActionChains(driver).move_to_element(
                find_element(
                    By.CLASS_NAME,
                    "client_pages_content_v2_components_data2action_actions_withDropDown",
                    target_item,
                )
            ).pause(1).move_by_offset(-500, 0).perform()
        popup = find_element(By.CLASS_NAME, "withDropDown-popover")
        time.sleep(2)
        driver.execute_script(
            "arguments[0].style = 'left: 467px; top: 60px; transform-origin: 50% -4px; display: block'",
            popup,
        )
        time.sleep(0.5)

        click_element(
            find_element(
                By.CLASS_NAME,
                "client_pages_content_v2_components_data2action_actions_withdraw",
                popup,
            ),
            timeout=5,
        )
        time.sleep(0.5)

    click_element(By.XPATH, "//button[span[text()='确 定']]")


def into_modify(title: str):
    driver.get(BJH_CONTENT_URL)
    target_item = get_article_content_item(title)
    click_element(find_element(By.XPATH, ".//span[text()='修改']", target_item))
    WebDriverWait(driver, 30).until(EC.number_of_windows_to_be(2))
    for handle in driver.window_handles:
        if handle != driver.current_window_handle:
            driver.close()
            driver.switch_to.window(handle)


current_temp_id = None


def set_using_temp(temp_id: int):
    global current_temp_id
    current_temp_id = temp_id


def free_using_temp():
    global current_temp_id
    if current_temp_id:
        requests.put(
            f"{FRONTEND_URL}/api/tempArticle/tempArticleWithdrawn",
            params={"article": current_temp_id},
        )
        current_temp_id = None


def single_post_workflow(username, article, temp):
    print(f"正在发布临时文章：《{temp['title']}》...")
    while True:
        driver.get(BJH_NEW_EDIT_URL)
        try:
            post_article(
                temp["path"],
                temp["title"],
                temp["covers"],
                temp["mainCover"],
            )
        except PostLimitedException as e:
            free_using_temp()
            raise e
        except Exception as e:
            print(f"发布失败:{e}")
            print("正在重试...")
        else:
            break

    print(f"临时文章《{temp['title']}》发布成功")

    driver.get(BJH_CONTENT_URL)
    print(f"等待审核...", end="")
    while not check_article_status(temp["title"]):
        print(".", end="")
        time.sleep(5)
        driver.get(BJH_CONTENT_URL)
    print(f"\n已通过审核")

    # withdraw_and_into_editor(temp)
    while True:
        try:
            withdraw(temp["title"])
        except Exception as e:
            print(f"撤回失败：{e}")
            print(f"正在重试...")
        else:
            break
    print(f"《{temp['title']}》已撤回")
    requests.put(
        f"{FRONTEND_URL}/api/tempArticle/tempArticleWithdrawn",
        params={"article": article["ID"]},
    )

    print("开始修改...")
    while True:
        try:
            into_modify(temp["title"])

            clean_editor()
            print("已清空")

            post_article(
                article["path"],
                article["title"],
                article["covers"],
                article["mainCover"],
                is_modifying=True,
            )
        except Exception:
            print("修改文章失败，正在重试...")
        else:
            break
    free_using_temp()
    print(f"成功修改至《{article['title']}》")

    return True


def main_workflow():
    check_list: dict[str, list[str]] = {}
    fail_list: dict[str, Any] = {}
    finished_usernames = []

    while True:
        finished = True
        for cookie_file in filter(
            lambda p: p.suffix != ".expired", COOKIE_FOLDER.glob("*")
        ):
            username = cookie_file.name
            if username in finished_usernames:
                continue

            try:
                login(cookie_file)
            except CookieExpiredException:
                print(f"账号“{username}”cookie已过期")
                fail_list.setdefault(username, []).append("cookie已过期")
                finished_usernames.append(username)
                cookie_file.rename(cookie_file.with_name(f"{username}.expired"))
                continue

            print(f"\n\n已登录账号“{username}”\n\n")

            (article, temp) = get_article(username)

            if not (article and temp):
                print("无可发布文章")
                finished_usernames.append(username)
                continue

            finished = False

            set_using_temp(temp["ID"])

            save_docx(article)
            save_docx(temp)
            print(f"已获取文章《{article['title']}》与临时文章《{temp['title']}》")

            try:
                single_post_workflow(username, article, temp)
            except PostLimitedException as e:
                print(f"账号今日发布数达到上限，提示：{e}")
                fail_list.setdefault(username, []).append(str(e))
                finished_usernames.append(username)
                continue
            except Exception as e:
                print(f"发布失败：{e}")
                fail_list.setdefault(username, []).append((article["title"], str(e)))
                continue
            else:
                requests.put(
                    f"{FRONTEND_URL}/api/articleInfo/articleUsed",
                    params={"article": article["ID"], "id": username},
                )
                check_list.setdefault(username, []).append(article["title"])
        if finished:
            break

    print("等待已发布文章审核...")
    while len(check_list):
        for username, to_checks in copy(check_list).items():
            if len(to_checks):
                login(COOKIE_FOLDER / username)
                print(f"查看“{username}”...")
                driver.get(BJH_CONTENT_URL)
                for reviewing_article in copy(to_checks):
                    status = check_article_status(reviewing_article)
                    if status is True:
                        to_checks.remove(reviewing_article)
                    elif isinstance(status, str):
                        print(f"《{reviewing_article}》发布失败，当前状态：{status}")
                        fail_list.setdefault(username, []).append(
                            (reviewing_article, status)
                        )
                time.sleep(3)
            else:
                del check_list[username]

    print(f"任务结束")
    print(fail_list)


try:
    while True:
        choices = ["发布文章", "添加账号", "退出"]
        expired_usernames = [
            file.name.rsplit(".", 1)[0] for file in COOKIE_FOLDER.glob("*.expired")
        ]
        if len(expired_usernames):
            choices.insert(1, "更新cookie")

        match inquirer.list_input("选择任务", choices=choices):
            case "发布文章":
                with create_driver(headless=not SHOW_WINDOW):
                    main_workflow()
            case "更新cookie":
                username = inquirer.list_input("选择账号", choices=expired_usernames)
                with create_driver(headless=False):
                    get_cookies(username)
                if (COOKIE_FOLDER / username).exists():
                    os.remove(COOKIE_FOLDER / f"{username}.expired")
            case "添加账号":
                username = input("请输入账号：")
                with create_driver(headless=False):
                    get_cookies(username)
            case "退出":
                break

except Exception as e:
    print(f"发生错误，任务终止：{e}")
finally:
    free_using_temp()
