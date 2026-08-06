#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
utils.py - URL 规范化 / 登录状态检测 / B站 API 标题获取 / BBDown 诊断

修复记录 v3.9:
  - B站 API 的 User-Agent 改为完整 Chrome UA（原 Mozilla UA 被 403 拒绝）
  - 增加 Referer 和 Accept 头，模拟真实浏览器请求
  - detect_login_status 增加 .NET 凭据目录搜索
  - 登录凭据文件检测增加更多文件名变体
"""

import os
import re
import time
import json
import logging
import urllib.request

log = logging.getLogger("BBDownGUI")

# ── B 站 API 端点 ──
API_VIEW    = "https://api.bilibili.com/x/web-interface/view"
API_SEASON  = "https://api.bilibili.com/pgc/view/web/season"

HTTP_TIMEOUT = 10
MAX_RETRY    = 3

# ⚠️ 关键修复：B站 API 会拒绝非浏览器 UA（返回 403）
# 必须使用完整 Chrome UA 才能正常获取
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# 登录凭据文件名（BBDown 生成的各种变体）
LOGIN_FILES = [
    "BBDown.data",       # WEB 登录（BBDown login）
    "BBDownTV.data",    # TV 登录（BBDown logintv）
    "BBDownApp.data",   # APP 登录
    "cookies.json",      # 手动导入的 Cookie
]

# .NET 工具目录（dotnet tool install 安装位置）
DOTNET_TOOLS_DIRS = [
    os.path.expandvars(r"%USERPROFILE%\.dotnet\tools"),
    os.path.expandvars(r"%USERPROFILE%\.dotnet\tools\BBDown"),
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\dotnet\tools"),
]

# ═════════════════════════════════════════
#  URL 规范化
# ═════════════════════════════════════════
def normalize_bilibili_url(url: str) -> str:
    """
    规范化用户粘贴的 B站地址：
    - 去首尾空白
    - 提取 BV / av / ep / ss 编号并重建干净链接
    - 丢弃 spm_id_from、vd_source 等含 & 的跟踪参数
    """
    u = (url or "").strip()
    if not u:
        return u
    # BV 号（大小写敏感，10 位字母数字）
    m = re.search(r"BV[0-9A-Za-z]{10}", u)
    if m:
        return f"https://www.bilibili.com/video/{m.group(0)}"
    # av 号
    m = re.search(r"\bav(\d+)", u, re.I)
    if m:
        return f"https://www.bilibili.com/video/av{m.group(1)}"
    # ep / ss 番剧
    m = re.search(r"\b(ep|ss)(\d+)\b", u, re.I)
    if m:
        return f"https://www.bilibili.com/bangumi/play/{m.group(1).lower()}{m.group(2)}"
    return u


# ═════════════════════════════════════════
#  登录状态检测（增强版 v3.9）
# ═════════════════════════════════════════
def detect_login_status(config) -> tuple:
    """
    返回 (status_summary, detail_text, mtime_or_None)

    检测顺序：
      1. 扫码凭据文件（BBDown.data / BBDownTV.data / BBDownApp.data）
         搜索目录：BBDown 所在目录 → 工作目录 → 当前目录 → .NET tools 目录
      2. 配置里手动填写的 Cookie / access_token
      3. 都没 → 未登录
    """
    dirs = set()
    bbdown = (config.get("bbdown_path") or "").strip()
    work_dir = (config.get("work_dir") or "").strip()

    # 基础搜索目录
    for d in [
        os.path.dirname(os.path.abspath(bbdown)) if bbdown else "",
        work_dir,
        os.getcwd(),
    ]:
        if d and os.path.isdir(d):
            dirs.add(d)

    # .NET tools 目录（dotnet tool install 安装的 BBDown 会把凭据写在这里）
    for d in DOTNET_TOOLS_DIRS:
        if os.path.isdir(d):
            dirs.add(d)
            # 也搜索子目录
            try:
                for sub in os.listdir(d):
                    sub_path = os.path.join(d, sub)
                    if os.path.isdir(sub_path):
                        dirs.add(sub_path)
            except Exception:
                pass

    # 1) 扫描所有已知凭据文件
    for d in sorted(dirs):
        for fname in LOGIN_FILES:
            p = os.path.join(d, fname)
            try:
                if os.path.exists(p) and os.path.getsize(p) > 0:
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read(8192)
                    # 检查各种凭据标记
                    has_cred = any(k in content.lower() for k in
                                  ["sessdata", "access_key", "token", "cookie"])
                    if not has_cred:
                        continue

                    uid = ""
                    m = re.search(r"DedeUserID[=:]?\s*(\d+)", content)
                    if m:
                        uid = f"(UID:{m.group(1)})"

                    # 判断登录类型
                    cl = content.lower()
                    if "tv" in fname.lower() or "tv" in cl[:200]:
                        ltype = "TV"
                    elif "app" in fname.lower() or "app" in cl[:200]:
                        ltype = "APP"
                    else:
                        ltype = "WEB"

                    mt = time.strftime("%Y-%m-%d %H:%M",
                                     time.localtime(os.path.getmtime(p)))
                    return (
                        f"已登录（{ltype}扫码）{uid}",
                        f"凭据文件：{p}\n最近更新：{mt}",
                        os.path.getmtime(p),
                    )
            except Exception:
                continue

    # 2) 手动鉴权
    cookie = (config.get("cookie") or "").strip()
    token  = (config.get("access_token") or "").strip()
    if cookie or token:
        detail = []
        if cookie:
            masked = cookie[:20] + "..." if len(cookie) > 20 else cookie
            detail.append(f"Cookie: {masked}")
        if token:
            masked = token[:10] + "..." if len(token) > 10 else token
            detail.append(f"Token: {masked}")
        return ("已配置鉴权（手动）",
                "使用「路径设置」页中填写的 " + " / ".join(detail),
                None)

    # 3) 未登录
    return ("未登录",
            "可通过「账号」菜单扫码登录，或在「路径设置」页填写 Cookie / Token",
            None)


# ═════════════════════════════════════════
#  B 站 API — 真实标题 + 分 P 列表
# ═════════════════════════════════════════
def fetch_bilibili_info(url: str) -> dict:
    """
    一站式获取：(大标题, 各分P标题列表, 类型)
    大标题 = data.title（视频总标题，始终不变）
    分P标题 = data.pages[].part 或 episodes[].title
    返回 {"title": str, "pages": [{"index","title"}], "type": "video|bangumi|unknown"}
    """
    result = {"title": "", "pages": [], "type": "unknown"}

    ep_id = _extract_ep_id(url)
    ss_id = _extract_season_id(url)

    # 1) 番剧 / 课程
    if ep_id or ss_id:
        params = f"?ep_id={ep_id}" if ep_id else f"?season_id={ss_id}"
        data = _api_get(API_SEASON + params)
        if data and data.get("result"):
            r = data["result"]
            title = r.get("title") or ""
            if not title and (r.get("episodes") or []):
                title = (r["episodes"][0].get("long_title") or
                         r["episodes"][0].get("title") or "")
            result["title"] = title
            result["type"] = "bangumi"
            for i, ep in enumerate(r.get("episodes") or []):
                idx = ep.get("i", i + 1)
                t = ep.get("long_title") or ep.get("title") or f"P{idx}"
                result["pages"].append({"index": idx, "title": t})
            return result

    # 2) 普通视频 / 多 P
    bvid = _extract_bvid(url) or _bv_from_web(url)
    aid  = _extract_aid(url)
    if bvid or aid:
        params = f"?bvid={bvid}" if bvid else f"?aid={aid}"
        data = _api_get(API_VIEW + params)
        if data and data.get("data"):
            d = data["data"]
            result["title"] = d.get("title") or ""
            result["type"] = "video"
            for i, p in enumerate(d.get("pages") or []):
                idx = p.get("page", i + 1)
                t = p.get("part") or p.get("title") or f"P{idx}"
                result["pages"].append({"index": idx, "title": t})
            return result

    return result


def _extract_bvid(url: str) -> str:
    m = re.search(r"BV[0-9A-Za-z]{10}", url or "")
    return m.group(0) if m else ""

def _extract_aid(url: str) -> str:
    m = re.search(r"\bav(\d+)", url or "", re.I)
    return m.group(1) if m else ""

def _extract_ep_id(url: str) -> str:
    m = re.search(r"\bep(\d+)", url or "", re.I)
    return m.group(1) if m else ""

def _extract_season_id(url: str) -> str:
    m = re.search(r"\bss(\d+)", url or "", re.I)
    return m.group(1) if m else ""


def _bv_from_web(url: str) -> str:
    """b23.tv 短链或网页 → 抓取 BV 号"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        m = re.search(r"BV[0-9A-Za-z]{10}", html)
        return m.group(0) if m else ""
    except Exception:
        return ""


def _api_get(url: str) -> dict:
    """GET JSON，带重试 + 完整浏览器头"""
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://www.bilibili.com",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Origin": "https://www.bilibili.com",
    }
    for attempt in range(MAX_RETRY + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                # B站 API 返回 code != 0 表示业务错误
                if isinstance(data, dict) and data.get("code", 0) != 0:
                    log.warning(f"[API] business code={data.get('code')} msg={data.get('message','')}")
                    if attempt < MAX_RETRY:
                        time.sleep(0.5)
                        continue
                return data
        except Exception as e:
            log.warning(f"[API] request failed (attempt {attempt+1}): {e}")
            time.sleep(0.5)
    return {}


# ═════════════════════════════════════════
#  BBDown 路径诊断
# ═════════════════════════════════════════
def diagnose_bbdown(path: str) -> dict:
    """诊断 BBDown 路径问题，返回结构化结果"""
    r = {"ok": False, "error": "", "detail": "", "suggestions": []}

    if not path:
        r["error"] = "BBDown 路径还没有设置"
        r["detail"] = "请到「路径设置」页面，点击浏览按钮选择 BBDown.exe"
        r["suggestions"] = [
            "下载 BBDown: https://github.com/nilaoda/BBDown/releases",
            "解压到任意目录（如 D:\\Tools\\BBDown\\）",
            "在「路径设置」页点击浏览，选择 BBDown.exe",
        ]
        return r

    if not os.path.exists(path):
        r["error"] = f"BBDown 文件找不到：{path}"
        r["detail"] = "请确认路径是否正确，或文件是否被移动/删除"
        found = _find_in_path("BBDown.exe")
        if found:
            r["suggestions"].append(f"在系统 PATH 中找到：{found}")
        r["suggestions"].append("请到「路径设置」页重新浏览选择 BBDown.exe")
        return r

    if not path.lower().endswith(".exe"):
        r["error"] = "BBDown 路径指向的不是 .exe 文件"
        r["detail"] = f"当前路径：{path}"
        return r

    # 验证 PE 头
    try:
        with open(path, "rb") as f:
            head = f.read(2)
        if head != b"MZ":
            r["error"] = "文件头不匹配（缺少 MZ 标识）"
            r["detail"] = "这个文件看起来不是真正的 BBDown.exe"
            return r
    except PermissionError:
        r["error"] = "没有权限访问该文件"
        r["suggestions"].append("尝试以管理员身份运行本程序")
        return r
    except Exception as e:
        r["error"] = f"读取文件失败: {e}"
        return r

    r["ok"] = True
    return r


def _find_in_path(exe: str) -> str:
    for p in os.environ.get("PATH", "").split(os.pathsep):
        cand = os.path.join(p.strip(), exe)
        if os.path.exists(cand):
            return cand
    return ""


# ═════════════════════════════════════════
#  Windows CMD 参数转义
# ═════════════════════════════════════════
def cmd_quote_win(s: str) -> str:
    """Windows CMD 参数转义（cmd.exe 不认 shlex 的单引号）"""
    if re.search(r'[\s&|<>^"]', s):
        return '"' + s.replace('"', '\\"') + '"'
    return s
