#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dialogs.py - 二维码登录 / 分P选择 / 下载确认 对话框

修复记录 v3.9:
  - 登录对话框：优先在 BBDown.exe 所在目录运行（qrcode.png 生成位置）
  - 启动时立即检查已有 qrcode.png（避免错过刚生成的二维码）
  - 凭据文件搜索增加 .NET tools 目录
  - 登录成功判定增加更多关键词覆盖
  - 进程退出码 0 + 凭据文件存在 → 明确成功
"""

import os
import sys
import re
import time
import threading
import queue
import subprocess

# 纯绝对导入 —— 由 main.py 保证 sys.path 正确
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as C  # noqa: E402
from utils import detect_login_status, cmd_quote_win  # noqa: E402

import wx  # noqa: E402


# ═══════════════════════════════════════
#  二维码登录对话框（增强版 v3.9）
# ═══════════════════════════════════════
class QRCodeLoginDialog(wx.Dialog):
    """
    静默启动 BBDown login / logintv，监控登录状态。

    登录成功判定（三信号任一即确认）：
      1. stdout 出现 "登录成功" / "login success" 等关键词
      2. 凭据文件（BBDown.data / BBDownTV.data）mtime 变化
      3. 进程正常退出（returncode == 0）且凭据文件存在

    关键修复：
      - cwd 设为 BBDown.exe 所在目录（qrcode.png 生成位置）
      - 启动时先检查是否已有 qrcode.png
      - 搜索目录增加 .NET tools 路径
    """

    # 成功关键词（兼容中英文和标点符号）
    SUCCESS_KW = [
        "登录成功", "登录成功!", "登录成功。",
        "login success", "login successful", "loginsuccess",
        "已登录", "已成功登录", "登录完成",
        "cookie saved", "cookiesaved", "saved",
        "扫码成功", "验证通过",
    ]
    # 失败关键词
    FAIL_KW = [
        "失败", "error", "expired", "过期",
        "登录超时", "timeout", "timed out",
        "cancel", "取消", "abort",
    ]

    def __init__(self, parent, config, mode="web"):
        title = "扫码登录 WEB 账号" if mode == "web" else "扫码登录 TV 账号"
        super().__init__(
            parent, title=title, size=(460, 620),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.config = config
        self.mode = mode
        self._proc = None
        self._done = False
        self._qr_found = False
        self._last_mtime = {}  # 改为 dict，记录每个凭据文件的 mtime
        self._out_q = queue.Queue()
        self._reader_stop = threading.Event()

        self._init_ui()
        # 短暂延迟后启动，确保 UI 先渲染
        wx.CallLater(100, self._start_login)

    # ─── UI ───
    def _init_ui(self):
        p = wx.Panel(self)
        s = wx.BoxSizer(wx.VERTICAL)

        # 提示文字
        tip = wx.StaticText(p, label="请使用哔哩哔哩手机客户端扫描下方二维码")
        tip.Wrap(420)
        s.Add(tip, 0, wx.ALL | wx.ALIGN_CENTER, 15)

        # 二维码位图
        self.bmp = wx.StaticBitmap(p, bitmap=wx.Bitmap(300, 300))
        self._set_placeholder()
        s.Add(self.bmp, 0, wx.ALIGN_CENTER | wx.ALL, 10)

        # 状态文字
        self.status = wx.StaticText(p, label="正在启动登录流程...")
        self.status.SetFont(
            wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        )
        s.Add(self.status, 0, wx.ALL | wx.ALIGN_CENTER, 5)

        # 路径提示
        self.path_hint = wx.StaticText(p, label="")
        self.path_hint.SetForegroundColour(wx.Colour(255, 150, 50))
        self.path_hint.Wrap(420)
        s.Add(self.path_hint, 0, wx.ALL | wx.ALIGN_CENTER, 5)

        # 日志区
        self.log = wx.TextCtrl(
            p, style=wx.TE_MULTILINE | wx.TE_READONLY,
            size=(-1, 130),
        )
        self.log.SetFont(
            wx.Font(8, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        )
        s.Add(self.log, 1, wx.EXPAND | wx.ALL, 10)

        # 按钮行
        bs = wx.BoxSizer(wx.HORIZONTAL)
        for label, handler in [
            ("刷新二维码", self._on_refresh),
            ("手动查找二维码...", self._on_browse),
            ("关闭", self._on_close_clicked),
        ]:
            btn = wx.Button(p, label=label)
            btn.Bind(wx.EVT_BUTTON, handler)
            bs.Add(btn, 0, wx.RIGHT, 5)
        s.Add(bs, 0, wx.ALIGN_CENTER | wx.ALL, 10)

        p.SetSizer(s)
        self.Bind(wx.EVT_CLOSE, self._on_close_event)

    def _set_placeholder(self):
        """绘制灰色占位图"""
        bmp = wx.Bitmap(300, 300)
        dc = wx.MemoryDC(bmp)
        dc.SetBrush(wx.Brush(wx.Colour(240, 240, 240)))
        dc.SetPen(wx.Pen(wx.Colour(200, 200, 200)))
        dc.DrawRectangle(0, 0, 300, 300)
        dc.SetTextForeground(wx.Colour(160, 160, 160))
        dc.SetFont(
            wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        )
        for i, t in enumerate(["等待二维码生成...", "若长时间无响应", "请点击「手动查找」"]):
            dc.DrawText(t, 80, 140 + i * 25)
        dc.SelectObject(wx.NullBitmap)
        self.bmp.SetBitmap(bmp)

    # ─── 路径搜索 ───
    def _search_dirs(self):
        """返回搜索目录列表（去重保序）"""
        dirs = []
        bbdown = (self.config.get("bbdown_path") or "").strip()
        work_dir = (self.config.get("work_dir") or "").strip()

        # 优先 BBDown 所在目录（qrcode.png 生成位置）
        if bbdown:
            bd = os.path.dirname(os.path.abspath(bbdown))
            if bd not in dirs:
                dirs.append(bd)
        # .NET tools 目录
        for d in [
            os.path.expandvars(r"%USERPROFILE%\.dotnet\tools"),
            os.path.expandvars(r"%USERPROFILE%\.dotnet\tools\BBDown"),
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\dotnet\tools"),
        ]:
            if d and os.path.isdir(d) and d not in dirs:
                dirs.append(d)
        # 工作目录
        if work_dir and os.path.isdir(work_dir) and work_dir not in dirs:
            dirs.append(work_dir)
        # 当前目录
        cwd = os.getcwd()
        if cwd not in dirs:
            dirs.append(cwd)
        return dirs

    def _qr_paths(self):
        """返回 qrcode.png 的完整搜索路径列表"""
        paths = []
        for d in self._search_dirs():
            p = os.path.join(d, C.QRCODE_FILE)
            if p not in paths:
                paths.append(p)
        return paths

    def _credential_paths(self):
        """返回所有已知凭据文件的搜索路径"""
        files = []
        for d in self._search_dirs():
            for fname in [C.LOGIN_DATA_FILE, "BBDownTV.data", "BBDownApp.data"]:
                p = os.path.join(d, fname)
                if p not in files:
                    files.append(p)
        return files

    # ─── 启动登录进程 ───
    def _start_login(self):
        bbdown = (self.config.get("bbdown_path") or "").strip() or "BBDown"
        sub = "login" if self.mode == "web" else "logintv"
        cmd = [bbdown, sub]

        self.log.AppendText(f"[CMD] {' '.join(cmd)}\n")
        self.log.AppendText("[INFO] 以静默模式启动（无 CMD 窗口）\n")

        # 检查 BBDown 是否可用
        if bbdown != "BBDown" and not os.path.exists(bbdown):
            self.log.AppendText(f"[ERROR] BBDown 文件不存在: {bbdown}\n")
            self.log.AppendText(f"[INFO] 请到「路径设置」页重新选择 BBDown.exe\n")
            self.status.SetLabel("❌ BBDown 路径无效")
            self.path_hint.SetLabel(
                f"找不到：{bbdown}\n请到「路径设置」页重新选择 BBDown.exe"
            )
            return

        # 关键修复：cwd 设为 BBDown.exe 所在目录
        # qrcode.png 会生成在 BBDown 进程的 cwd 中
        if bbdown != "BBDown":
            cwd = os.path.dirname(os.path.abspath(bbdown))
        else:
            cwd = os.getcwd()

        self.log.AppendText(f"[INFO] 工作目录: {cwd}\n")

        # 清除旧的 qrcode.png（避免显示过期的二维码）
        for p in self._qr_paths():
            if os.path.exists(p):
                try:
                    os.remove(p)
                    self.log.AppendText(f"[INFO] 已清除旧二维码: {p}\n")
                except Exception:
                    pass

        # 重置状态
        self._last_mtime = {}
        self._qr_found = False

        try:
            si, cf = self._win_silent()
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                cwd=cwd,
                startupinfo=si,
                creationflags=cf,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            self.log.AppendText("[INFO] 登录进程已启动 ✓\n")
        except FileNotFoundError:
            self.log.AppendText(f"[ERROR] 找不到可执行文件: {bbdown}\n")
            self.log.AppendText("[INFO] 请确认 BBDown 路径正确\n")
            self.status.SetLabel("❌ 启动失败")
            self.path_hint.SetLabel("请到「路径设置」页选择 BBDown.exe")
            return
        except Exception as e:
            self.log.AppendText(f"[ERROR] 启动失败: {e}\n")
            self.status.SetLabel("❌ 启动失败")
            return

        # 后台读线程
        self._reader_stop.clear()
        proc = self._proc
        out_q = self._out_q

        def _reader():
            try:
                for line in iter(proc.stdout.readline, ""):
                    if self._reader_stop.is_set():
                        break
                    out_q.put(line.rstrip("\r\n"))
            except Exception as e:
                out_q.put(f"[ERROR] 读取进程输出失败: {e}")
            finally:
                out_q.put(None)  # EOF 哨兵

        threading.Thread(target=_reader, daemon=True).start()

        # UI 定时器（非阻塞轮询）
        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_timer)
        self._timer.Start(1500)
        self._elapsed = 0

        # 关键修复：启动时立即检查是否已有 qrcode.png
        # （有些版本的 BBDown 生成二维码极快）
        wx.CallLater(500, self._check_qrcode_immediate)

    def _check_qrcode_immediate(self):
        """启动后 500ms 立即检查一次二维码"""
        for p in self._qr_paths():
            if os.path.exists(p):
                self.log.AppendText(f"[INFO] 启动即发现二维码: {p}\n")
                break

    # ─── 定时器：检查二维码 + 进程输出 + 凭据文件 ───
    def _on_timer(self, event):
        self._elapsed += 1.5

        # 0) 先检查凭据文件（最可靠的登录成功信号，优先于输出分析）
        cred_found = False
        for p in self._credential_paths():
            if os.path.exists(p):
                try:
                    mt = os.path.getmtime(p)
                    sz = os.path.getsize(p)
                except OSError:
                    continue
                # 文件存在且非空 且 是新写入的（mtime 在进程启动后）
                if sz > 0:
                    prev = self._last_mtime.get(p)
                    if prev is None or prev != mt:
                        self._last_mtime[p] = mt
                        self.log.AppendText(f"[INFO] 检测到凭据文件: {p} ({sz} bytes)\n")
                        # 验证文件内容确实包含登录信息
                        try:
                            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                                content = f.read(4096)
                            if any(k in content.lower() for k in
                                   ["sessdata", "access_key", "token", "cookie"]):
                                cred_found = True
                                self.log.AppendText(f"[INFO] 凭据文件内容有效 ✓\n")
                        except Exception:
                            pass

        if cred_found and not self._done:
            self._on_login_success()
            return

        # 1) 非阻塞读取进程输出
        while True:
            try:
                line = self._out_q.get_nowait()
            except queue.Empty:
                break
            if line is None:
                continue
            self.log.AppendText(line + "\n")
            lo = line.lower()

            # 成功关键词
            if any(k.lower() in lo for k in self.SUCCESS_KW):
                self.log.AppendText("[INFO] 检测到登录成功关键词 ✓\n")
                self._on_login_success()
                return
            # 失败关键词
            elif any(k.lower() in lo for k in self.FAIL_KW):
                self.status.SetLabel("⚠️ 可能已过期，可刷新")
                self.log.AppendText("[WARN] 检测到失败关键词\n")

        # 2) 查找二维码图片
        qr = None
        for p in self._qr_paths():
            if os.path.exists(p):
                qr = p
                break

        if qr:
            try:
                img = wx.Image(qr, wx.BITMAP_TYPE_PNG)
                if img.IsOk():
                    self.bmp.SetBitmap(wx.Bitmap(img.Scale(300, 300, wx.IMAGE_QUALITY_HIGH)))
                    self.bmp.Refresh()
                    if not self._qr_found:
                        self._qr_found = True
                        self.status.SetLabel("📱 请扫码登录")
                        self.log.AppendText(f"[INFO] 二维码已加载: {qr}\n")
                        self.path_hint.SetLabel("")
            except Exception as e:
                self.log.AppendText(f"[WARN] 读取二维码失败: {e}\n")
        else:
            if self._elapsed < 12:
                self.status.SetLabel(f"⏳ 等待二维码生成... ({int(self._elapsed)}s)")
            elif self._elapsed < 30:
                self.status.SetLabel("⚠️ 仍未检测到 qrcode.png")
                hint = "已搜索以下位置：\n" + "\n".join(
                    f"  • {x}" for x in self._qr_paths()
                )
                self.path_hint.SetLabel(hint)
                self.log.AppendText("[WARN] 未找到 qrcode.png\n")
            else:
                self.status.SetLabel("❌ 超时，请手动查找或重试")
                self.log.AppendText("[ERROR] 等待超时\n")
                self.log.AppendText("[INFO] 可尝试：\n")
                self.log.AppendText("  1. 确认 BBDown 版本 >= 1.6.0\n")
                self.log.AppendText("  2. 手动查找 qrcode.png 并扫码\n")
                self.log.AppendText("  3. 使用浏览器 Cookie 方式登录\n")
                self._timer.Stop()

        # 3) 进程结束但未成功
        if self._proc and self._proc.poll() is not None and not self._done:
            rc = self._proc.returncode
            self.log.AppendText(f"[INFO] 登录进程已退出 (code={rc})\n")

            # 进程退出后最后检查一次凭据文件
            for p in self._credential_paths():
                if os.path.exists(p) and os.path.getsize(p) > 0:
                    try:
                        with open(p, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read(4096)
                        if any(k in content.lower() for k in
                               ["sessdata", "access_key", "token"]):
                            self.log.AppendText(f"[INFO] 进程退出后找到有效凭据: {p}\n")
                            self._on_login_success()
                            return
                    except Exception:
                        pass

            if rc == 0:
                self.log.AppendText("[WARN] 进程正常退出但未找到凭据文件\n")
                self.log.AppendText("[INFO] 请检查 BBDown 版本是否支持扫码登录\n")
                self.status.SetLabel("⚠️ 登录未完成")
            else:
                self.status.SetLabel(f"进程已结束 (code={rc})")
            self._timer.Stop()

    # ─── 登录成功 ───
    def _on_login_success(self):
        if self._done:
            return
        self._done = True
        self.status.SetLabel("✅ 登录成功！")
        self.log.AppendText("[INFO] 登录成功 - 800ms 后关闭窗口\n")
        if hasattr(self, "_timer"):
            self._timer.Stop()
        # 延迟关闭，让用户看到成功状态
        wx.CallLater(800, self._finalize_close)

    def _finalize_close(self):
        """清理二维码 + 弹成功提示 + 关闭窗口"""
        # 删除所有 qrcode.png
        for p in self._qr_paths():
            if os.path.exists(p):
                try:
                    os.remove(p)
                    self.log.AppendText(f"[INFO] 已删除: {p}\n")
                except Exception:
                    pass
        # 弹成功提示
        wx.MessageBox(
            "✅ 登录成功！\n\n凭据已保存，可以开始下载了。",
            "成功", wx.ICON_INFORMATION,
        )
        self.EndModal(wx.ID_OK)
        self.Destroy()

    # ─── 按钮事件 ───
    def _on_browse(self, event):
        """手动查找二维码文件"""
        dlg = wx.FileDialog(
            self, "请选择 qrcode.png 文件",
            wildcard="PNG 图片 (*.png)|*.png|所有文件 (*.*)|*.*",
            style=wx.FD_OPEN,
        )
        if dlg.ShowModal() == wx.ID_OK:
            try:
                img = wx.Image(dlg.GetPath(), wx.BITMAP_TYPE_PNG)
                if img.IsOk():
                    self.bmp.SetBitmap(wx.Bitmap(img.Scale(300, 300, wx.IMAGE_QUALITY_HIGH)))
                    self.status.SetLabel("📱 已手动加载二维码，请扫码")
                    self.path_hint.SetLabel("")
                    self.log.AppendText(f"[INFO] 手动加载: {dlg.GetPath()}\n")
                else:
                    wx.MessageBox("该文件不是有效的 PNG 图片", "错误", wx.ICON_ERROR)
            except Exception as e:
                wx.MessageBox(f"加载失败: {e}", "错误", wx.ICON_ERROR)
        dlg.Destroy()

    def _on_refresh(self, event):
        """重新启动登录流程"""
        self.log.AppendText("\n" + "─" * 40 + "\n")
        self.log.AppendText("[INFO] 重新启动登录流程...\n")
        self._done = False
        self._qr_found = False
        self._last_mtime = {}

        if hasattr(self, "_timer"):
            self._timer.Stop()
        self._reader_stop.set()
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass

        # 删除旧二维码
        for p in self._qr_paths():
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

        self._set_placeholder()
        self._elapsed = 0
        # 等待旧进程完全退出后再启动新进程
        wx.CallLater(500, self._start_login)

    def _on_close_clicked(self, event):
        self._cleanup_and_close()

    def _on_close_event(self, event):
        self._cleanup_and_close()

    def _cleanup_and_close(self):
        """清理资源并关闭"""
        if hasattr(self, "_timer"):
            self._timer.Stop()
        self._reader_stop.set()
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass
        # 删除二维码
        for p in self._qr_paths():
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
        self.EndModal(wx.ID_OK if self._done else wx.ID_CANCEL)
        self.Destroy()

    # ─── Windows 静默启动 ───
    @staticmethod
    def _win_silent():
        si, cf = None, 0
        if sys.platform == "win32":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            cf = subprocess.CREATE_NO_WINDOW
        return si, cf


# ═══════════════════════════════════════
#  分P选择对话框（单击即显示标题）
# ═══════════════════════════════════════
class PageSelectDialog(wx.Dialog):
    """多选分P对话框 —— 单击分P即显示该分P的完整标题"""

    QUICK = [
        "（请选择快捷操作）", "全选", "全不选", "反选",
        "仅选奇数分P", "仅选偶数分P", "自定义范围...",
    ]

    def __init__(self, parent, pages, video_title, title_callback=None):
        super().__init__(
            parent, title=f"选择分P — {video_title[:50]}",
            size=(580, 540),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.pages = pages
        self.selected = []
        self.title_callback = title_callback
        self._init_ui()
        # Pull 模式：定时刷新标题
        self._pull_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_pull_timer)
        self._pull_timer.Start(2000)

    def _init_ui(self):
        p = wx.Panel(self)
        s = wx.BoxSizer(wx.VERTICAL)

        s.Add(
            wx.StaticText(p, label=f"共 {len(self.pages)} 个分P，请选择要下载的分P："),
            0, wx.ALL, 10,
        )

        main = wx.BoxSizer(wx.HORIZONTAL)

        # 左侧分P列表
        self.clb = wx.CheckListBox(
            p, choices=[f"P{x['index']} — {x['title']}" for x in self.pages],
        )
        self.clb.Bind(wx.EVT_LISTBOX, self._on_clb_click)
        self.clb.Bind(wx.EVT_CHECKLISTBOX, self._update_preview)
        main.Add(self.clb, 1, wx.EXPAND | wx.RIGHT, 8)

        # 右侧分P详情面板
        dp = wx.Panel(p)
        dp.SetBackgroundColour(wx.Colour(245, 245, 245))
        ds = wx.BoxSizer(wx.VERTICAL)
        ds.Add(wx.StaticText(dp, label="分P详情："), 0, wx.ALL, 5)
        self.detail_title = wx.StaticText(dp, label="← 单击分P查看标题")
        self.detail_title.Wrap(180)
        self.detail_title.SetFont(
            wx.Font(9, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_BOLD, wx.FONTWEIGHT_NORMAL)
        )
        ds.Add(self.detail_title, 1, wx.EXPAND | wx.ALL, 5)
        self.detail_idx = wx.StaticText(dp, label="")
        ds.Add(self.detail_idx, 0, wx.ALL, 5)
        dp.SetSizer(ds)
        main.Add(dp, 0, wx.EXPAND)
        s.Add(main, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # 快捷操作
        qs = wx.BoxSizer(wx.HORIZONTAL)
        qs.Add(
            wx.StaticText(p, label="快捷操作 ▼"),
            0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5,
        )
        self.cb_q = wx.ComboBox(p, choices=self.QUICK, style=wx.CB_READONLY, size=(200, -1))
        self.cb_q.SetSelection(0)
        self.cb_q.Bind(wx.EVT_COMBOBOX, self._on_quick)
        qs.Add(self.cb_q, 0)
        s.Add(qs, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # 按钮行
        bs = wx.BoxSizer(wx.HORIZONTAL)
        for label, handler in [
            ("全选", self._on_all),
            ("全不选", self._on_none),
            ("反选", self._on_invert),
            ("指定范围...", self._on_range),
        ]:
            b = wx.Button(p, label=label)
            b.Bind(wx.EVT_BUTTON, handler)
            bs.Add(b, 0, wx.RIGHT, 5)
        s.Add(bs, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # 已选预览
        s.Add(wx.StaticText(p, label="已选分P："), 0, wx.LEFT | wx.RIGHT, 10)
        self.preview = wx.TextCtrl(p, style=wx.TE_READONLY, size=(-1, 30))
        s.Add(self.preview, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # 确认/取消
        bs2 = wx.BoxSizer(wx.HORIZONTAL)
        ok = wx.Button(p, label="✅ 确认下载")
        ok.SetDefault()
        ok.Bind(wx.EVT_BUTTON, self._on_ok)
        cancel = wx.Button(p, label="取消")
        cancel.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CANCEL))
        bs2.Add(ok, 0, wx.RIGHT, 10)
        bs2.Add(cancel, 0)
        s.Add(bs2, 0, wx.ALIGN_CENTER | wx.ALL, 15)

        p.SetSizer(s)
        self._update_preview(None)

    def _on_clb_click(self, event):
        """单击分P → 右侧立即显示完整标题"""
        i = event.GetSelection()
        if i < 0 or i >= len(self.pages):
            return
        pg = self.pages[i]
        self.detail_idx.SetLabel(f"P{pg['index']}")
        self.detail_title.SetLabel(pg["title"])
        # 通知外部刷新标题
        if self.title_callback:
            try:
                self.title_callback()
            except Exception:
                pass

    def _on_pull_timer(self, event):
        """定时拉取最新标题（Pull 模式兜底）"""
        if self.title_callback:
            try:
                self.title_callback()
            except Exception:
                pass

    def _on_quick(self, event):
        idx = self.cb_q.GetSelection()
        if idx == 1:
            self._on_all(None)
        elif idx == 2:
            self._on_none(None)
        elif idx == 3:
            self._on_invert(None)
        elif idx == 4:
            for i in range(self.clb.GetCount()):
                self.clb.Check(i, (i + 1) % 2 == 1)
            self._update_preview(None)
        elif idx == 5:
            for i in range(self.clb.GetCount()):
                self.clb.Check(i, (i + 1) % 2 == 0)
            self._update_preview(None)
        elif idx == 6:
            self._on_range(None)
        self.cb_q.SetSelection(0)

    def _on_all(self, event):
        for i in range(self.clb.GetCount()):
            self.clb.Check(i, True)
        self._update_preview(None)

    def _on_none(self, event):
        for i in range(self.clb.GetCount()):
            self.clb.Check(i, False)
        self._update_preview(None)

    def _on_invert(self, event):
        for i in range(self.clb.GetCount()):
            self.clb.Check(i, not self.clb.IsChecked(i))
        self._update_preview(None)

    def _on_range(self, event):
        dlg = wx.TextEntryDialog(
            self, "输入分P（例: 1,3,5 或 2-7 或 1,3-5,8）：", "指定范围",
        )
        if dlg.ShowModal() == wx.ID_OK:
            sel = self._parse_range(dlg.GetValue(), len(self.pages))
            for i in range(self.clb.GetCount()):
                self.clb.Check(i, (i + 1) in sel)
            self._update_preview(None)
        dlg.Destroy()

    @staticmethod
    def _parse_range(text, max_n):
        result = set()
        for part in (text or "").split(","):
            part = part.strip()
            if "-" in part:
                try:
                    a, b = part.split("-", 1)
                    for n in range(int(a), min(int(b), max_n) + 1):
                        result.add(n)
                except Exception:
                    pass
            elif part.isdigit():
                n = int(part)
                if 1 <= n <= max_n:
                    result.add(n)
        return result

    def _update_preview(self, event):
        checked = [str(i + 1) for i in range(self.clb.GetCount()) if self.clb.IsChecked(i)]
        self.preview.SetValue(",".join(checked) if checked else "（未选择）")
        self.selected = [i + 1 for i in range(self.clb.GetCount()) if self.clb.IsChecked(i)]

    def _on_ok(self, event):
        self._update_preview(None)
        if not self.selected:
            wx.MessageBox("请至少选择一个分P", "提示", wx.ICON_INFORMATION)
            return
        self.EndModal(wx.ID_OK)

    def push_title_update(self, pages):
        """外部推送：从 API 获取最新标题后刷新列表"""
        if not pages:
            return
        changed = False
        for p in pages:
            idx = p.get("index")
            t = p.get("title", "")
            for i, op in enumerate(self.pages):
                if op["index"] == idx and t and t != op["title"]:
                    self.pages[i]["title"] = t
                    changed = True
        if changed:
            self.clb.SetItems([f"P{x['index']} — {x['title']}" for x in self.pages])
            for i in range(self.clb.GetCount()):
                if self.pages[i]["index"] in self.selected:
                    self.clb.Check(i, True)
            sel = self.clb.GetSelection()
            if sel >= 0:
                pg = self.pages[sel]
                self.detail_idx.SetLabel(f"P{pg['index']}")
                self.detail_title.SetLabel(pg["title"])


# ═══════════════════════════════════════
#  下载确认对话框（内嵌登录状态）
# ═══════════════════════════════════════
class DownloadConfirmDialog(wx.Dialog):
    """
    下载前二次确认 —— 内嵌登录状态（不弹额外窗口）
    顶部横幅显示登录状态，无需额外弹窗打断流程
    """

    def __init__(self, parent, video_title, pages_info,
                 options_summary, cmd_preview, login_status="未登录"):
        super().__init__(
            parent, title="⚠ 确认下载", size=(700, 640),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        p = wx.Panel(self)
        s = wx.BoxSizer(wx.VERTICAL)

        # ── 登录状态横幅（内嵌） ──
        lb = wx.Panel(p, size=(-1, 36))
        if "已登录" in login_status or "Logged" in login_status:
            lb.SetBackgroundColour(wx.Colour(200, 240, 200))
        else:
            lb.SetBackgroundColour(wx.Colour(255, 240, 200))
        ls = wx.BoxSizer(wx.HORIZONTAL)
        ls.Add(
            wx.StaticText(lb, label=f"  🔑 登录状态：{login_status}"),
            0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 8,
        )
        lb.SetSizer(ls)
        s.Add(lb, 0, wx.EXPAND | wx.ALL, 10)

        # ── 警告横幅 ──
        wb = wx.Panel(p, size=(-1, 36))
        wb.SetBackgroundColour(wx.Colour(255, 240, 200))
        ws = wx.BoxSizer(wx.HORIZONTAL)
        ws.Add(
            wx.StaticText(wb, label="  ⚠ 请仔细确认以下下载信息，确认后将开始下载"),
            0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 8,
        )
        wb.SetSizer(ws)
        s.Add(wb, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # ── 视频标题 ──
        s.Add(wx.StaticText(p, label="视频标题："), 0, wx.LEFT | wx.RIGHT, 10)
        tc = wx.TextCtrl(p, value=video_title, style=wx.TE_READONLY, size=(-1, 36))
        tc.SetFont(
            wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        )
        s.Add(tc, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # ── 分P ──
        s.Add(wx.StaticText(p, label="分P选择："), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        pc = wx.TextCtrl(
            p, value=pages_info,
            style=wx.TE_READONLY | wx.TE_MULTILINE, size=(-1, 60),
        )
        s.Add(pc, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # ── 选项摘要 ──
        s.Add(wx.StaticText(p, label="下载选项："), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        oc = wx.TextCtrl(
            p, value=options_summary,
            style=wx.TE_READONLY | wx.TE_MULTILINE, size=(-1, 60),
        )
        s.Add(oc, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # ── 命令预览 ──
        s.Add(wx.StaticText(p, label="命令预览："), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        cc = wx.TextCtrl(
            p, value=cmd_preview,
            style=wx.TE_READONLY | wx.TE_MULTILINE, size=(-1, 100),
        )
        cc.SetFont(
            wx.Font(8, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        )
        s.Add(cc, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # ── 按钮 ──
        bs = wx.BoxSizer(wx.HORIZONTAL)
        yes = wx.Button(p, label="✅ 确认下载")
        yes.SetBackgroundColour(wx.Colour(0, 150, 136))
        yes.SetForegroundColour(wx.WHITE)
        yes.SetFont(
            wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        )
        yes.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_OK))
        no = wx.Button(p, label="❌ 取消")
        no.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CANCEL))
        bs.Add(yes, 0, wx.RIGHT, 10)
        bs.Add(no, 0)
        s.Add(bs, 0, wx.ALIGN_CENTER | wx.ALL, 15)

        p.SetSizer(s)
