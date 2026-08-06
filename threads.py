#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""threads.py - 日志队列 + 下载线程 + 解析线程 + 标题获取线程"""

import os, re, time, json, threading, subprocess, queue, logging

log = logging.getLogger("BBDownGUI")

HTTP_TIMEOUT = 8
MAX_RETRY   = 2
USER_AGENT  = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

API_VIEW   = "https://api.bilibili.com/x/web-interface/view"
API_SEASON = "https://api.bilibili.com/pgc/view/web/season"


# ═════════════════════════════════════════
#  日志队列
# ═════════════════════════════════════════
class LogQueue:
    """线程安全日志队列（内存 buffer + queue.Queue）"""

    def __init__(self, max_size=5000):
        self._q = queue.Queue()
        self.max_size = max_size
        self._buffer = []

    def put(self, level, text):
        entry = (level, text, time.time())
        self._buffer.append(entry)
        if len(self._buffer) > self.max_size:
            self._buffer = self._buffer[-self.max_size:]
        self._q.put(entry)

    def get_nowait(self):
        try:
            return self._q.get_nowait()
        except queue.Empty:
            return None

    def get_all(self):
        return list(self._buffer)


# ═════════════════════════════════════════
#  下载线程
# ═════════════════════════════════════════
class DownloadThread(threading.Thread):
    """
    后台启动 BBDown 子进程（原生 CMD 调用），
    实时读取 stdout/stderr 并通过回调推送到 UI。
    """

    def __init__(self, cmd, work_dir, log_cb, finish_cb):
        super().__init__(daemon=True)
        self.cmd = cmd
        self.work_dir = work_dir
        self.log_cb = log_cb
        self.finish_cb = finish_cb
        self._proc = None
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def run(self):
        try:
            self.log_cb("INFO", f"[CMD] {' '.join(self.cmd)}")
            self.log_cb("INFO", f"[WORKDIR] {self.work_dir}")
            self.log_cb("INFO", "─" * 60)

            si, cf = _win_silent()
            self._proc = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                cwd=self.work_dir if self.work_dir else None,
                startupinfo=si, creationflags=cf,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
            )

            for line in iter(self._proc.stdout.readline, ""):
                if self._stop.is_set():
                    break
                line = line.rstrip("\r\n")
                if not line:
                    continue
                self.log_cb(_classify(line), line)

            self._proc.wait(timeout=5)
            rc = self._proc.returncode
            self.log_cb("INFO", "─" * 60)
            if rc == 0:
                self.log_cb("SUCCESS", f"[完成] 进程正常退出 (code={rc})")
            else:
                self.log_cb("ERROR", f"[异常] 进程退出码: {rc}")
            self.finish_cb(rc == 0)

        except FileNotFoundError:
            self.log_cb("ERROR", f"找不到可执行文件: {self.cmd[0]}")
            self.log_cb("ERROR", "请确认 BBDown 路径正确，或在「路径设置」中重新浏览选择")
            self.finish_cb(False)
        except Exception as e:
            self.log_cb("ERROR", f"线程异常: {e}")
            self.finish_cb(False)

    @staticmethod
    def _classify(line: str) -> str:
        lo = line.lower()
        if any(k in lo for k in ["error", "失败", "异常", "fatal", "traceback"]):
            return "ERROR"
        if any(k in lo for k in ["warn", "警告"]):
            return "WARN"
        if any(k in lo for k in ["success", "完成", "合并", "下载完成", "merged"]):
            return "SUCCESS"
        if any(k in lo for k in ["debug", "dbg"]):
            return "DEBUG"
        return "INFO"


# ═════════════════════════════════════════
#  视频信息解析线程
# ═════════════════════════════════════════
class InfoParseThread(threading.Thread):
    """调用 BBDown --only-show-info 解析视频信息"""

    def __init__(self, base_cmd, url, work_dir, result_cb, log_cb):
        super().__init__(daemon=True)
        self.cmd = base_cmd + [url, "--only-show-info", "--show-all"]
        self.work_dir = work_dir
        self.result_cb = result_cb
        self.log_cb = log_cb

    def run(self):
        try:
            self.log_cb("INFO", f"[解析] 开始解析视频信息...")
            si, cf = _win_silent()
            proc = subprocess.run(
                self.cmd,
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                cwd=self.work_dir if self.work_dir else None,
                startupinfo=si, creationflags=cf,
                timeout=60,
            )
            output = proc.stdout + "\n" + proc.stderr
            self.log_cb("INFO", f"[解析] 收到 {len(output)} 字符输出")

            title = self._extract_title(output)
            pages = self._extract_pages(output)
            self.result_cb({
                "title": title,
                "pages": pages,
                "raw_output": output[:2000],
            })
        except subprocess.TimeoutExpired:
            self.log_cb("ERROR", "[解析] 超时（60秒）")
            self.result_cb(None)
        except Exception as e:
            self.log_cb("ERROR", f"[解析] 异常: {e}")
            self.result_cb(None)

    @staticmethod
    def _extract_title(text: str) -> str:
        for pat in [r"视频标题[：:]\s*(.+)", r"Title[：:]\s*(.+)", r"标题[：:]\s*(.+)"]:
            m = re.search(pat, text)
            if m:
                return m.group(1).strip()[:120]
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("[") and len(line) > 2:
                return line[:120]
        return "未知标题"

    @staticmethod
    def _extract_pages(text: str) -> list:
        pages, seen = [], set()
        patterns = [
            r"^\s*\[P(\d+)\]\s*(.+)$",
            r"^\s*P(\d+)\s*[:：]\s*(.+)$",
            r"^\s*(\d+)[\.、]\s*(.+)$",
        ]
        for pat in patterns:
            for m in re.finditer(pat, text, re.MULTILINE):
                idx = int(m.group(1))
                if not (1 <= idx <= 999) or idx in seen:
                    continue
                raw = m.group(2).strip()
                leftover = re.sub(r"\[[^\]]*\]", "", raw).strip()
                title = leftover or raw
                if not title:
                    brackets = re.findall(r"\[([^\]]*)\]", raw)
                    title = brackets[-1].strip() if brackets else raw
                title = title or f"P{idx}"
                seen.add(idx)
                pages.append({"index": idx, "title": title[:100]})
            if pages:
                break
        if not pages:
            m = re.search(r"共[计有]?\s*(\d+)\s*个分\s*P", text, re.I)
            if m:
                for i in range(1, int(m.group(1)) + 1):
                    pages.append({"index": i, "title": f"P{i}"})
        pages.sort(key=lambda p: p["index"])
        return pages


# ═════════════════════════════════════════
#  B 站 API 标题获取线程
# ═════════════════════════════════════════
class TitleFetchThread(threading.Thread):
    """
    从 B站开放 API 获取真实标题 + 分P列表。
    主路径：Python urllib；备选：Node.js / curl。
    """

    def __init__(self, url, result_cb, log_cb):
        super().__init__(daemon=True)
        self.url = url
        self.result_cb = result_cb
        self.log_cb = log_cb

    def run(self):
        self.log_cb("INFO", "[标题] 正在从 B站 API 获取真实视频标题...")
        try:
            info = self._fetch(self.url)
            if info and info.get("title"):
                self.log_cb("SUCCESS", f"[标题] 获取成功: {info['title']}")
                self.result_cb(info)
            else:
                self.log_cb("WARN", "[标题] API 未返回有效数据，尝试备选方案...")
                self.result_cb(None)
        except Exception as e:
            self.log_cb("ERROR", f"[标题] 异常: {e}")
            self.result_cb(None)

    def _fetch(self, url):
        # 1) 提取 ID
        bvid = aid = epid = ssid = None
        m = re.search(r"BV[0-9A-Za-z]{10}", url or "")
        if m: bvid = m.group(0)
        m = re.search(r"\bav(\d+)", url or "", re.I)
        if m: aid = m.group(1)
        m = re.search(r"\bep(\d+)", url or "", re.I)
        if m: epid = m.group(1)
        m = re.search(r"\bss(\d+)", url or "", re.I)
        if m: ssid = m.group(1)

        # 2) 番剧
        if epid or ssid:
            params = f"?ep_id={epid}" if epid else f"?season_id={ssid}"
            data = _api_get(API_SEASON + params)
            if data and data.get("result"):
                r = data["result"]
                title = r.get("title") or (r.get("episodes") or [{}])[0].get("long_title") or ""
                pages = []
                for i, ep in enumerate(r.get("episodes") or []):
                    t = ep.get("long_title") or ep.get("title") or f"P{i+1}"
                    pages.append({"index": ep.get("i", i+1), "title": t})
                return {"title": title, "pages": pages, "type": "bangumi"}

        # 3) 普通视频
        if bvid or aid:
            params = f"?bvid={bvid}" if bvid else f"?aid={aid}"
            data = _api_get(API_VIEW + params)
            if data and data.get("data"):
                d = data["data"]
                pages = []
                for i, p in enumerate(d.get("pages") or []):
                    t = p.get("part") or p.get("title") or f"P{i+1}"
                    pages.append({"index": p.get("page", i+1), "title": t})
                return {"title": d.get("title", ""), "pages": pages, "type": "video"}

        # 4) 尝试从网页抓取
        if url.startswith("http"):
            try:
                req = urllib_request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib_request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
                m = re.search(r"BV[0-9A-Za-z]{10}", html)
                if m:
                    return self._fetch("https://www.bilibili.com/video/" + m.group(0))
            except Exception:
                pass

        return {"title": "", "pages": [], "type": "unknown"}


# ═════════════════════════════════════════
#  工具函数
# ═════════════════════════════════════════
def _win_silent():
    si, cf = None, 0
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        cf = subprocess.CREATE_NO_WINDOW
    return si, cf


def _api_get(url: str) -> dict:
    import urllib.request as ulib
    for attempt in range(MAX_RETRY + 1):
        try:
            req = ulib.Request(url, headers={"User-Agent": USER_AGENT})
            with ulib.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            log.warning(f"[API] request failed (attempt {attempt+1}): {e}")
            time.sleep(0.5)
    return {}
