#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main_window.py - 主窗口（精简，声明式配置）

新增/删除选项：只需修改下方声明列表即可。
build() 方法自动处理 --flag 逻辑。

元组约定（用索引访问，杜绝解包错误）：
  CHECKBOXES[i]  = (attr, label, default, group_key, hint)
  CHECKBOX_GROUPS[i] = (key, title, columns)
  PATH_FIELDS[i]  = (label, key, dialog_title, is_dir, wildcard)
  ADV_FIELDS[i]  = (key, label, hint)
"""

import os, sys, re, time, shlex, subprocess, logging
from datetime import datetime

import wx
import wx.lib.agw.flatnotebook as FNB

# 纯绝对导入 —— 由 main.py 保证 sys.path 正确
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
from config import ConfigManager, APP_NAME, APP_VERSION, HINT, DEFAULTS
from utils import (normalize_bilibili_url, detect_login_status,
                  diagnose_bbdown, cmd_quote_win)
from command_builder import CommandBuilder, ENCODING_ORDER, DFN_LADDER
from threads import LogQueue, DownloadThread, InfoParseThread, TitleFetchThread
from widgets import BrowsePathCtrl
from dialogs import QRCodeLoginDialog, PageSelectDialog, DownloadConfirmDialog

log = logging.getLogger("BBDownGUI")

# ═════════════════════════════════════════
#  声明式配置 —— 只需修改这些列表
#  元组元素位置固定，用索引访问，永不解包出错
# ═════════════════════════════════════════

# CHECKBOXES: (attr_name, label, default_value, group_key, hint_text)
# 索引:         0          1       2            3          4
CHECKBOXES = [
    # 输出类型
    ("video_only",        "仅视频",      False, "output",  "(--video-only)"),
    ("audio_only",        "仅音频",      False, "output",  "(--audio-only)"),
    ("danmaku_only",      "仅弹幕",      False, "output",  "(--danmaku-only)"),
    ("sub_only",          "仅字幕",      False, "output",  "(--sub-only)"),
    ("cover_only",        "仅封面",      False, "output",  "(--cover-only)"),
    # 下载内容
    ("download_danmaku",  "下载弹幕",    False, "content", "(--download-danmaku)"),
    # 处理流程
    ("skip_mux",          "跳过混流",    False, "process", "(--skip-mux)"),
    ("skip_subtitle",     "跳过字幕",    False, "process", "(--skip-subtitle)"),
    ("skip_cover",       "跳过封面",    False, "process", "(--skip-cover)"),
    ("skip_ai",          "跳过AI字幕",  True,  "process", "(--skip-ai)"),
    # 外部工具
    ("use_aria2c",       "使用 aria2c",  False, "tools",   "(--use-aria2c)"),
    ("use_mp4box",       "使用 MP4Box", False, "tools",   "(--use-mp4box)"),
    # 排序方式
    ("video_ascending",   "视频升序",    False, "sort",    "(--video-ascending)"),
    ("audio_ascending",   "音频升序",    False, "sort",    "(--audio-ascending)"),
    # 网络选项
    ("allow_pcdn",        "允许 PCDN",   False, "network", "(--allow-pcdn)"),
    ("force_http",        "强制 HTTP",   True,  "network", "(--force-http)"),
    # 信息与调试
    ("only_show_info",    "仅解析信息",  False, "info",    "(--only-show-info)"),
    ("show_all",          "显示全部分P", False, "info",    "(--show-all)"),
    ("hide_streams",      "隐藏流信息",  False, "info",    "(--hide-streams)"),
    ("multi_thread",      "多线程",      True,  "info",    "(--multi-thread)"),
    ("interactive",       "交互式选择",  False, "info",    "(-ia)"),
    ("debug",             "调试模式",    False, "info",    "(--debug)"),
]

# CHECKBOX_GROUPS: (group_key, display_title, column_count)
# 索引:             0          1               2
CHECKBOX_GROUPS = [
    ("output",   "输出类型",   5),
    ("content",  "下载内容",   5),
    ("process",  "处理流程",   4),
    ("tools",    "外部工具",   4),
    ("sort",     "排序方式",   4),
    ("network",  "网络选项",   4),
    ("info",     "信息与调试", 5),
]

# PATH_FIELDS: (label, config_key, dialog_title, is_directory, wildcard)
# 索引:         0       1            2               3               4
PATH_FIELDS = [
    ("BBDown:",    "bbdown_path",  "选择 BBDown.exe",        False, "可执行文件 (*.exe)|*.exe|所有文件 (*.*)|*.*"),
    ("FFmpeg:",    "ffmpeg_path",  "选择 ffmpeg.exe",        False, "可执行文件 (*.exe)|*.exe|所有文件 (*.*)|*.*"),
    ("MP4Box:",    "mp4box_path",  "选择 mp4box.exe",        False, "可执行文件 (*.exe)|*.exe|所有文件 (*.*)|*.*"),
    ("aria2c:",    "aria2c_path",  "选择 aria2c.exe",        False, "可执行文件 (*.exe)|*.exe|所有文件 (*.*)|*.*"),
    ("工作目录:",  "work_dir",     "选择下载目录",              True,  ""),
]

# ADV_FIELDS: (config_key, label, hint_text)
# 索引:         0            1        2
ADV_FIELDS = [
    ("user_agent",      "User-Agent:",    HINT["user_agent"]),
    ("upos_host",       "UPOS Host:",     HINT["upos_host"]),
    ("language",        "语言代码:",      HINT["language"]),
    ("delay_per_page",  "分P延迟(秒):",  HINT["delay_per_page"]),
    ("aria2c_args",     "aria2c 参数:",   HINT["aria2c_args"]),
    ("host",            "BiliPlus Host:", HINT["host"]),
    ("ep_host",         "BiliPlus EP:",   HINT["ep_host"]),
    ("area",            "BiliPlus Area:", HINT["area"]),
    ("config_file",     "配置文件:",      HINT["config_file"]),
]

# API / 编码 / 画质选项
API_CHOICES     = ["WEB (默认)", "TV (无水印)", "APP", "国际版 (INTL)"]
API_MAP         = {"0": "web", "1": "tv", "2": "app", "3": "intl"}
ENCODING_CHOICES = CommandBuilder.VALID_ENCODINGS
DFN_CHOICES     = CommandBuilder.VALID_DFNS

# ═════════════════════════════════════════
#  主窗口
# ═════════════════════════════════════════
class MainWindow(wx.Frame):

    def __init__(self, config):
        super().__init__(None, title=f"{APP_NAME} v{APP_VERSION}",
                         size=(config.get("window_w", 1100), config.get("window_h", 800)),
                         pos=(config.get("window_x", 100), config.get("window_y", 100)))

        self.config = config
        self.log_queue = LogQueue()
        self._dl_thread = None
        self._info_thread = None
        self._title_thread = None
        self._video_info = None
        self._pending_options = None

        self.path_widgets = {}
        self.adv_widgets = {}
        self.checkbox_widgets = {}

        self._init_ui()
        self._init_menu()
        self._init_timer()
        self._load_config_to_ui()
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self._welcome_log()
        self._refresh_login_banner()

    # ─── UI 构建 ───
    def _init_ui(self):
        # ═══ 登录状态条（始终可见） ═══
        self.login_banner = wx.Panel(self, size=(-1, 40))
        self.login_banner.SetBackgroundColour(wx.Colour(240, 240, 240))
        lb_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.login_label = wx.StaticText(self.login_banner, label="检测中...")
        self.login_label.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT,
                                        wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.btn_refresh_login = wx.Button(self.login_banner, label="刷新", size=(70, -1))
        self.btn_refresh_login.Bind(wx.EVT_BUTTON, lambda e: self._refresh_login_banner())
        lb_sizer.Add(self.login_label, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 8)
        lb_sizer.Add(self.btn_refresh_login, 0, wx.ALL, 5)
        self.login_banner.SetSizer(lb_sizer)

        # ═══ URL 输入区 ═══
        link_panel = wx.Panel(self)
        ls = wx.BoxSizer(wx.VERTICAL)

        url_row = wx.BoxSizer(wx.HORIZONTAL)
        url_row.Add(wx.StaticText(link_panel, label="视频地址："), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.tc_url = wx.TextCtrl(link_panel)
        self.tc_url.SetHint("粘贴B站视频/番剧地址 或 av/bv/ep/ss 编号")
        self.tc_url.SetMinSize((500, -1))
        btn_parse = wx.Button(link_panel, label="🔍 解析信息")
        btn_parse.Bind(wx.EVT_BUTTON, self._on_parse_info)
        url_row.Add(self.tc_url, 1, wx.EXPAND | wx.RIGHT, 5)
        url_row.Add(btn_parse, 0)
        ls.Add(url_row, 0, wx.EXPAND | wx.ALL, 8)

        info_row = wx.BoxSizer(wx.HORIZONTAL)
        info_row.Add(wx.StaticText(link_panel, label="视频信息："), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.tc_video_info = wx.TextCtrl(link_panel, style=wx.TE_READONLY, size=(-1, 30))
        self.tc_video_info.SetHint("点击「解析信息」获取视频标题和分P列表")
        info_row.Add(self.tc_video_info, 1, wx.EXPAND)
        ls.Add(info_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        page_row = wx.BoxSizer(wx.HORIZONTAL)
        page_row.Add(wx.StaticText(link_panel, label="分P选择："), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.tc_page = wx.ComboBox(link_panel, style=wx.CB_DROPDOWN, size=(220, -1))
        self.tc_page.SetHint("如: 1,2,5 或 3-7 或 ALL")
        self.tc_page.Disable()
        self.tc_page.Bind(wx.EVT_COMBOBOX_DROPDOWN, self._on_page_dropdown)
        self.btn_page_pick = wx.Button(link_panel, label="多选 ▼")
        self.btn_page_pick.Bind(wx.EVT_BUTTON, self._on_pick_pages)
        self.btn_page_pick.Disable()
        page_row.Add(self.tc_page, 0, wx.RIGHT, 5)
        page_row.Add(self.btn_page_pick, 0)
        page_row.Add(wx.StaticText(link_panel, label="（留空=全部）"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)
        ls.Add(page_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        link_panel.SetSizer(ls)

        # ═══ 笔记本 ═══
        self.notebook = FNB.FlatNotebook(self, agwStyle=FNB.FNB_FANCY_TABS | FNB.FNB_TABS_BORDER_SIMPLE)
        self.notebook.AddPage(self._build_main_page(),    "下载选项")
        self.notebook.AddPage(self._build_settings_page(), "路径设置")
        self.notebook.AddPage(self._build_advanced_page(), "高级选项")
        self.notebook.AddPage(self._build_log_page(),     "运行日志")

        # ═══ 底部按钮 ═══
        bottom = wx.Panel(self)
        bs = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_preview = wx.Button(bottom, label="👁 预览命令")
        self.btn_preview.Bind(wx.EVT_BUTTON, self._on_preview_cmd)
        self.btn_download = wx.Button(bottom, label="⬇ 开始下载")
        self.btn_download.SetBackgroundColour(wx.Colour(0, 150, 136))
        self.btn_download.SetForegroundColour(wx.WHITE)
        self.btn_download.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.btn_download.Bind(wx.EVT_BUTTON, self._on_start_download)
        self.btn_stop = wx.Button(bottom, label="■ 停止")
        self.btn_stop.SetBackgroundColour(wx.Colour(220, 60, 60))
        self.btn_stop.SetForegroundColour(wx.WHITE)
        self.btn_stop.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.btn_stop.Disable()
        self.btn_stop.Bind(wx.EVT_BUTTON, self._on_stop_download)
        bs.Add(self.btn_preview, 0, wx.RIGHT, 10)
        bs.Add(self.btn_download, 1, wx.EXPAND | wx.RIGHT, 10)
        bs.Add(self.btn_stop, 0)
        bottom.SetSizer(bs)

        # ═══ 主布局 ═══
        main = wx.BoxSizer(wx.VERTICAL)
        main.Add(self.login_banner, 0, wx.EXPAND)
        main.Add(link_panel, 0, wx.EXPAND)
        main.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 5)
        main.Add(bottom, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizer(main)

    # ─── 登录状态条 ───
    def _refresh_login_banner(self):
        status, detail, _mtime = detect_login_status(self.config)
        self.login_label.SetLabel(f"🔑 登录状态：{status}")
        if "已登录" in status or "Logged" in status:
            self.login_banner.SetBackgroundColour(wx.Colour(200, 240, 200))
            self.login_label.SetForegroundColour(wx.Colour(0, 100, 0))
        else:
            self.login_banner.SetBackgroundColour(wx.Colour(255, 240, 200))
            self.login_label.SetForegroundColour(wx.Colour(150, 100, 0))
        self.login_banner.Refresh()

    # ─── 下载选项页（声明式复选框） ───
    def _build_main_page(self):
        panel = wx.Panel(self.notebook)
        s = wx.BoxSizer(wx.VERTICAL)

        # API + 编码 + 画质
        grp1 = wx.StaticBoxSizer(wx.StaticBox(panel, label="解析与画质"), wx.VERTICAL)
        r1 = wx.BoxSizer(wx.HORIZONTAL)
        r1.Add(wx.StaticText(panel, label="解析模式："), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.cb_api = wx.ComboBox(panel, choices=API_CHOICES, style=wx.CB_READONLY, size=(200, -1))
        self.cb_api.SetSelection(0)
        r1.Add(self.cb_api, 0, wx.RIGHT, 20)
        r1.Add(wx.StaticText(panel, label="编码选择："), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.cb_encoding = wx.ComboBox(panel, choices=ENCODING_CHOICES, style=wx.CB_READONLY, size=(120, -1))
        self.cb_encoding.SetSelection(0)
        r1.Add(self.cb_encoding, 0, wx.RIGHT, 10)
        t = wx.StaticText(panel, label="（无此编码时自动回退其它编码）")
        t.SetForegroundColour(wx.Colour(120, 120, 120))
        r1.Add(t, 0, wx.ALIGN_CENTER_VERTICAL)
        grp1.Add(r1, 0, wx.ALL, 8)

        r2 = wx.BoxSizer(wx.HORIZONTAL)
        r2.Add(wx.StaticText(panel, label="画质选择："), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.cb_dfn = wx.ComboBox(panel, choices=DFN_CHOICES, style=wx.CB_READONLY, size=(180, -1))
        idx = DFN_CHOICES.index("1080P 高清") if "1080P 高清" in DFN_CHOICES else 0
        self.cb_dfn.SetSelection(idx)
        r2.Add(self.cb_dfn, 0, wx.RIGHT, 10)
        t2 = wx.StaticText(panel, label="（目标画质不存在时自动逐级降级）")
        t2.SetForegroundColour(wx.Colour(120, 120, 120))
        r2.Add(t2, 0, wx.ALIGN_CENTER_VERTICAL)
        grp1.Add(r2, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        s.Add(grp1, 0, wx.EXPAND | wx.ALL, 8)

        # 声明式复选框分组 —— 用索引访问，永不解包出错
        for g in CHECKBOX_GROUPS:
            gkey, gtitle, cols = g[0], g[1], g[2]
            s.Add(self._build_checkbox_group(panel, gkey, gtitle, cols),
                  0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        panel.SetSizer(s)
        return panel

    def _build_checkbox_group(self, parent, gkey, gtitle, cols):
        box = wx.StaticBoxSizer(wx.StaticBox(parent, label=gtitle), wx.VERTICAL)
        grid = wx.FlexGridSizer(cols=cols, vgap=6, hgap=12)
        for cb_data in CHECKBOXES:
            if cb_data[3] != gkey:
                continue
            attr, label, default, _group, hint = cb_data[0], cb_data[1], cb_data[2], cb_data[3], cb_data[4]
            cb = wx.CheckBox(parent, label=f"{label}  {hint}")
            cb.SetValue(default)
            self.checkbox_widgets[attr] = cb
            grid.Add(cb, 0)
        box.Add(grid, 0, wx.EXPAND | wx.ALL, 8)
        return box

    # ─── 路径设置页 ───
    def _build_settings_page(self):
        panel = wx.Panel(self.notebook)
        s = wx.BoxSizer(wx.VERTICAL)

        grp = wx.StaticBoxSizer(wx.StaticBox(panel, label="程序路径（点击「浏览」选择，空值显示灰色提示）"), wx.VERTICAL)
        for pf in PATH_FIELDS:
            label, key, title, is_dir, wc = pf[0], pf[1], pf[2], pf[3], pf[4]
            row = wx.BoxSizer(wx.HORIZONTAL)
            st = wx.StaticText(panel, label=label)
            st.SetMinSize((80, -1))
            row.Add(st, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
            ctrl = BrowsePathCtrl(panel, key=key, dialog_title=title, is_dir=is_dir, wildcard=wc)
            ctrl.set_notify_callback(self._on_path_field_changed)
            row.Add(ctrl, 1, wx.EXPAND)
            grp.Add(row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
            self.path_widgets[key] = ctrl
        s.Add(grp, 0, wx.EXPAND | wx.ALL, 8)

        # 文件名模式
        grp2 = wx.StaticBoxSizer(wx.StaticBox(panel, label="文件名模式"), wx.VERTICAL)
        r = wx.BoxSizer(wx.HORIZONTAL)
        r.Add(wx.StaticText(panel, label="单P："), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.tc_file_pattern = wx.TextCtrl(panel, size=(350, -1))
        self.tc_file_pattern.SetHint(HINT["file_pattern"])
        r.Add(self.tc_file_pattern, 1, wx.RIGHT, 15)
        r.Add(wx.StaticText(panel, label="多P："), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.tc_multi_pattern = wx.TextCtrl(panel, size=(350, -1))
        self.tc_multi_pattern.SetHint(HINT["multi_file_pattern"])
        r.Add(self.tc_multi_pattern, 1)
        grp2.Add(r, 0, wx.EXPAND | wx.ALL, 8)
        s.Add(grp2, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # 鉴权
        grp3 = wx.StaticBoxSizer(wx.StaticBox(panel, label="账号鉴权（可选，留空则不设置）"), wx.VERTICAL)
        r2 = wx.BoxSizer(wx.HORIZONTAL)
        r2.Add(wx.StaticText(panel, label="Cookie："), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.tc_cookie = wx.TextCtrl(panel, size=(300, -1))
        self.tc_cookie.SetHint(HINT["cookie"])
        r2.Add(self.tc_cookie, 1, wx.RIGHT, 15)
        r2.Add(wx.StaticText(panel, label="Token："), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.tc_token = wx.TextCtrl(panel, size=(300, -1))
        self.tc_token.SetHint(HINT["token"])
        r2.Add(self.tc_token, 1)
        grp3.Add(r2, 0, wx.EXPAND | wx.ALL, 8)
        s.Add(grp3, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        panel.SetSizer(s)
        return panel

    # ─── 高级选项页 ───
    def _build_advanced_page(self):
        panel = wx.Panel(self.notebook)
        s = wx.BoxSizer(wx.VERTICAL)
        grp = wx.StaticBoxSizer(wx.StaticBox(panel, label="高级参数（留空则使用默认值）"), wx.VERTICAL)
        for af in ADV_FIELDS:
            key, label, hint = af[0], af[1], af[2]
            row = wx.BoxSizer(wx.HORIZONTAL)
            st = wx.StaticText(panel, label=label)
            st.SetMinSize((100, -1))
            row.Add(st, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
            tc = wx.TextCtrl(panel, size=(450, -1))
            tc.SetHint(hint)
            row.Add(tc, 1, wx.EXPAND)
            grp.Add(row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
            self.adv_widgets[key] = tc
        s.Add(grp, 0, wx.EXPAND | wx.ALL, 8)
        panel.SetSizer(s)
        return panel

    # ─── 日志页 ───
    def _build_log_page(self):
        panel = wx.Panel(self.notebook)
        s = wx.BoxSizer(wx.VERTICAL)

        ib = wx.Panel(panel, size=(-1, 30))
        ib.SetBackgroundColour(wx.Colour(230, 240, 255))
        ibs = wx.BoxSizer(wx.HORIZONTAL)
        ibs.Add(wx.StaticText(ib, label="📋 运行日志 — Python GUI 通过 subprocess 原生调用 CMD 子进程，实时读取输出"),
                0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        ib.SetSizer(ibs)
        s.Add(ib, 0, wx.EXPAND | wx.ALL, 2)

        ts = wx.BoxSizer(wx.HORIZONTAL)
        for label, handler in [("清空日志", self._on_clear_log),
                                ("保存日志", self._on_save_log),
                                ("复制全部", self._on_copy_log),
                                ("在 CMD 中运行", self._on_open_in_cmd)]:
            b = wx.Button(panel, label=label)
            b.Bind(wx.EVT_BUTTON, handler)
            ts.Add(b, 0, wx.RIGHT, 5)
        s.Add(ts, 0, wx.ALL, 5)

        self.log_text = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.TE_AUTO_URL | wx.HSCROLL)
        self.log_text.SetFont(wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, faceName="Consolas"))
        s.Add(self.log_text, 1, wx.EXPAND | wx.ALL, 5)
        panel.SetSizer(s)
        return panel

    # ─── 菜单 ───
    def _init_menu(self):
        """
        菜单创建 — 安全写法。
        关键规则：
          ❌ item.Bind(...)     ← MenuItem 没有 Bind 方法
          ✅ self.Bind(..., item) ← 必须绑到 Frame 上
        """
        mb = wx.MenuBar()

        m_file = wx.Menu()
        item_open = m_file.Append(wx.ID_OPEN, "打开下载目录")
        m_file.AppendSeparator()
        item_exit = m_file.Append(wx.ID_EXIT, "退出")
        mb.Append(m_file, "文件")

        m_acc = wx.Menu()
        item_login_web = m_acc.Append(wx.NewIdRef(), "扫码登录 WEB 账号")
        item_login_tv  = m_acc.Append(wx.NewIdRef(), "扫码登录 TV 账号")
        m_acc.AppendSeparator()
        item_view_status = m_acc.Append(wx.NewIdRef(), "查看登录状态")
        item_clear_auth  = m_acc.Append(wx.NewIdRef(), "清除鉴权信息（并删除登录凭据）")
        mb.Append(m_acc, "账号")

        m_tools = wx.Menu()
        item_open_cfg = m_tools.Append(wx.NewIdRef(), "打开配置文件")
        item_open_wd   = m_tools.Append(wx.NewIdRef(), "打开工作目录")
        mb.Append(m_tools, "工具")

        m_help = wx.Menu()
        item_about = m_help.Append(wx.ID_ABOUT, "关于")
        mb.Append(m_help, "帮助")

        self.SetMenuBar(mb)

        # 全部绑到 Frame，绝不绑到 MenuItem
        self.Bind(wx.EVT_MENU, self._on_open_work_dir,    item_open)
        self.Bind(wx.EVT_MENU, lambda e: self.Close(),   item_exit)
        self.Bind(wx.EVT_MENU, self._on_login_web,        item_login_web)
        self.Bind(wx.EVT_MENU, self._on_login_tv,         item_login_tv)
        self.Bind(wx.EVT_MENU, self._on_view_login_status,  item_view_status)
        self.Bind(wx.EVT_MENU, self._on_clear_auth,        item_clear_auth)
        self.Bind(wx.EVT_MENU, self._on_open_config,       item_open_cfg)
        self.Bind(wx.EVT_MENU, self._on_open_work_dir,    item_open_wd)
        self.Bind(wx.EVT_MENU, self._on_about,             item_about)

    # ─── 定时器 ───
    def _init_timer(self):
        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_timer_tick)
        self._timer.Start(150)

    def _on_timer_tick(self, e):
        while True:
            entry = self.log_queue.get_nowait()
            if entry is None:
                break
            level, text = entry[0], entry[1]
            self._append_log(level, text)

    def _append_log(self, level, text):
        color_map = {
            "INFO":    (200, 200, 200),
            "WARN":    (255, 200, 50),
            "ERROR":   (255, 80, 80),
            "SUCCESS": (80, 220, 120),
            "DEBUG":   (120, 160, 255),
        }
        color = color_map.get(level, (255, 255, 255))
        ts = datetime.now().strftime("%H:%M:%S")
        tc = self.log_text
        tc.SetDefaultStyle(wx.TextAttr(wx.Colour(*color)))
        tc.AppendText(f"[{ts}][{level}] {text}\n")
        tc.ShowPosition(tc.GetLastPosition())

    # ─── 配置加载/保存 ───
    def _load_config_to_ui(self):
        for key, w in self.path_widgets.items():
            v = self.config.get(key, "")
            if v:
                w.SetValue(v)
        for key, tc in self.adv_widgets.items():
            v = self.config.get(key, "")
            if v:
                tc.SetValue(v)
        if self.config.get("file_pattern"):
            self.tc_file_pattern.SetValue(self.config.get("file_pattern"))
        if self.config.get("multi_file_pattern"):
            self.tc_multi_pattern.SetValue(self.config.get("multi_file_pattern"))
        if self.config.get("cookie"):
            self.tc_cookie.SetValue(self.config.get("cookie"))
        if self.config.get("access_token"):
            self.tc_token.SetValue(self.config.get("access_token"))

    def _save_ui_to_config(self):
        for key, w in self.path_widgets.items():
            self.config.set(key, w.GetValue().strip())
        for key, tc in self.adv_widgets.items():
            self.config.set(key, tc.GetValue().strip())
        self.config.set("file_pattern", self.tc_file_pattern.GetValue().strip())
        self.config.set("multi_file_pattern", self.tc_multi_pattern.GetValue().strip())
        self.config.set("cookie", self.tc_cookie.GetValue().strip())
        self.config.set("access_token", self.tc_token.GetValue().strip())
        pos = self.GetPosition()
        size = self.GetSize()
        for k, v in [("window_x", pos.x), ("window_y", pos.y),
                     ("window_w", size.width), ("window_h", size.height)]:
            self.config.set(k, v)
        self.config.save()
        self._refresh_login_banner()

    # ─── 路径变化 → 自动刷新登录状态 ───
    def _on_path_field_changed(self, new_value):
        self._refresh_login_banner()

    # ─── 解析信息 ───
    def _on_parse_info(self, e):
        url = normalize_bilibili_url(self.tc_url.GetValue())
        if not url:
            wx.MessageBox("请先输入视频地址", "提示", wx.ICON_INFORMATION)
            return
        if url != self.tc_url.GetValue().strip():
            self.tc_url.SetValue(url)

        self._set_parse_buttons(False)
        self._append_log("INFO", f"[解析] 正在解析: {url}")

        # API 线程（主要标题来源）
        self._title_thread = TitleFetchThread(url, self._on_title_result, self.log_queue.put)
        self._title_thread.start()

        # BBDown 解析线程
        try:
            builder = CommandBuilder(self.config)
            opts = self._collect_options()
            base_cmd = builder.build({**opts, "only_show_info": False, "show_all": False}, with_url=False)
        except Exception as ex:
            wx.MessageBox(f"命令构建失败: {ex}", "错误", wx.ICON_ERROR)
            self._set_parse_buttons(True)
            return

        work_dir = self.config.get("work_dir", "").strip() or os.getcwd()
        self._info_thread = InfoParseThread(
            base_cmd, url, work_dir,
            lambda info: wx.CallAfter(self._on_info_result, info),
            self.log_queue.put)
        self._info_thread.start()

    def _on_title_result(self, info):
        """API 标题回调（Push 模式）"""
        if not info or not info.get("title"):
            return
        title = info["title"]
        pages = info.get("pages", [])
        if not self._video_info:
            self._video_info = {
                "title": title,
                "pages": pages,
                "url": self.tc_url.GetValue().strip(),
                "source": "api"
            }
        else:
            self._video_info["title"] = title
            if pages:
                self._video_info["pages"] = pages
            self._video_info["source"] = "api"

        pages = self._video_info["pages"]
        self.tc_video_info.SetValue(f"{title}  （共 {len(pages)} 个分P）")
        self.tc_page.Enable()
        if len(pages) > 1:
            self.btn_page_pick.Enable()
            choices = ["ALL（全部）", "LAST（最后一个）"]
            for p in pages:
                choices.append(f"P{p['index']} — {p['title']}")
            self.tc_page.SetItems(choices)
        self._append_log("SUCCESS", f"[标题] 已更新: {title}")

    def _on_info_result(self, info):
        self._set_parse_buttons(True)
        if not info:
            self._handle_parse_failure()
            return

        title = info.get("title", "")
        pages = info.get("pages", [])

        if self._video_info and self._video_info.get("title"):
            # API 标题优先，不被 BBDown 覆盖
            title = self._video_info["title"]
            if pages and self._video_info.get("pages"):
                pass  # API pages 已是最新
            self._video_info["pages"] = self._video_info.get("pages") or pages
        else:
            if not pages:
                pages = [{"index": 1, "title": title}] if title else []
            self._video_info = {
                "title": title,
                "pages": pages,
                "url": normalize_bilibili_url(self.tc_url.GetValue()),
                "source": "bbdown"
            }

        info = self._video_info
        self.tc_video_info.SetValue(f"{info['title']}  （共 {len(info['pages'])} 个分P）")
        self.tc_page.Enable()
        if len(info["pages"]) > 1:
            self.btn_page_pick.Enable()
            choices = ["ALL（全部）", "LAST（最后一个）"]
            for p in info["pages"]:
                choices.append(f"P{p['index']} — {p['title']}")
            self.tc_page.SetItems(choices)
            for p in info["pages"][:5]:
                self._append_log("INFO", f"  P{p['index']}: {p['title']}")
        self._append_log("SUCCESS", f"[解析] 成功: {info['title']}")

    def _handle_parse_failure(self):
        """BBDown 失败 → 尝试 API 兜底"""
        self._append_log("ERROR", "[解析] BBDown 失败")
        if self._video_info and self._video_info.get("title"):
            info = self._video_info
            self.tc_video_info.SetValue(f"{info['title']}  （共 {len(info['pages'])} 个分P）")
            self.tc_page.Enable()
            if len(info["pages"]) > 1:
                self.btn_page_pick.Enable()
                choices = ["ALL（全部）", "LAST（最后一个）"]
                for p in info["pages"]:
                    choices.append(f"P{p['index']} — {p['title']}")
                self.tc_page.SetItems(choices)
            self._append_log("SUCCESS", f"[解析] 已通过 API 恢复: {info['title']}")
            wx.MessageBox(
                f"✅ 已通过 B站接口获取\n\n标题: {info['title']}\n分P数: {len(info['pages'])}",
                "成功（API 兜底）", wx.ICON_INFORMATION)
        else:
            self._show_parse_error_dialog()

    def _show_parse_error_dialog(self):
        """弹出通俗诊断对话框"""
        bbdown = (self.config.get("bbdown_path") or "").strip()
        diag = diagnose_bbdown(bbdown)
        if diag["ok"]:
            wx.MessageBox(
                "BBDown 正常但无法解析此视频。\n\n可能原因：\n  1. 视频已被删除或设为私密\n  2. 需要登录后才能访问\n  3. 网络连接异常",
                "解析失败", wx.ICON_WARNING)
        else:
            msg = f"{diag['error']}\n\n{diag.get('detail', '')}\n\n"
            if diag["suggestions"]:
                msg += "建议操作：\n" + "\n".join(
                    f"  {i+1}. {s}" for i, s in enumerate(diag["suggestions"]))
            else:
                msg += "请到「路径设置」页重新选择 BBDown.exe"
            wx.MessageBox(msg, "解析失败", wx.ICON_ERROR)

    # ─── 分P 选择 ───
    def _on_pick_pages(self, e):
        if not self._video_info:
            return
        self._open_page_picker()

    def _on_page_dropdown(self, e):
        if not self._video_info:
            wx.MessageBox("请先解析视频信息", "提示", wx.ICON_INFORMATION)
            self.tc_page.Dismiss()
            return
        self.tc_page.Dismiss()
        self._open_page_picker()

    def _open_page_picker(self):
        info = self._video_info
        dlg = PageSelectDialog(
            self, info["pages"], info["title"],
            title_callback=self._refresh_title_from_api)
        dlg.selected = self._parse_page_selection(self.tc_page.GetValue())
        for i, p in enumerate(info["pages"]):
            if p["index"] in dlg.selected:
                dlg.clb.Check(i, True)
        if dlg.ShowModal() == wx.ID_OK:
            self.tc_page.SetValue(",".join(str(s) for s in dlg.selected))
            self._append_log("INFO", f"[分P] 已选择: {self.tc_page.GetValue()}")
        dlg.Destroy()

    def _parse_page_selection(self, text):
        result = set()
        for part in (text or "").split(","):
            part = part.strip()
            if "-" in part:
                try:
                    a, b = part.split("-", 1)
                    for n in range(int(a), int(b) + 1):
                        result.add(n)
                except Exception:
                    pass
            elif part.isdigit():
                result.add(int(part))
        return result

    def _refresh_title_from_api(self):
        url = normalize_bilibili_url(self.tc_url.GetValue())
        if not url:
            return
        self._title_thread = TitleFetchThread(url, self._on_title_result, self.log_queue.put)
        self._title_thread.start()

    # ─── 预览命令 ───
    def _on_preview_cmd(self, e):
        try:
            opts = self._collect_options()
            cmd = CommandBuilder(self.config).build(opts)
            preview = " ".join(shlex.quote(c) for c in cmd)
            dlg = wx.Dialog(self, title="命令预览", size=(700, 400))
            p = wx.Panel(dlg)
            s = wx.BoxSizer(wx.VERTICAL)
            tc = wx.TextCtrl(p, value=preview, style=wx.TE_MULTILINE | wx.TE_READONLY)
            tc.SetFont(wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
            s.Add(tc, 1, wx.EXPAND | wx.ALL, 10)
            bs = wx.BoxSizer(wx.HORIZONTAL)
            btn_copy = wx.Button(p, label="复制到剪贴板")
            btn_copy.Bind(wx.EVT_BUTTON, lambda e: (
                wx.Clipboard.Get().Open(),
                wx.Clipboard.Get().SetData(wx.TextDataObject(preview)),
                wx.Clipboard.Get().Close()))
            bs.Add(btn_copy, 0, wx.RIGHT, 10)
            btn_close = wx.Button(p, label="关闭")
            btn_close.Bind(wx.EVT_BUTTON, lambda e: dlg.Destroy())
            bs.Add(btn_close, 0)
            s.Add(bs, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)
            p.SetSizer(s)
            dlg.ShowModal()
        except Exception as ex:
            wx.MessageBox(f"构建命令失败: {ex}", "错误", wx.ICON_ERROR)

    # ─── 开始下载 ───
    def _on_start_download(self, e):
        url = normalize_bilibili_url(self.tc_url.GetValue())
        if not url:
            wx.MessageBox("请先输入视频地址", "提示", wx.ICON_INFORMATION)
            return
        if url != self.tc_url.GetValue().strip():
            self.tc_url.SetValue(url)

        try:
            opts = self._collect_options()
        except Exception as ex:
            wx.MessageBox(f"选项收集失败: {ex}", "错误", wx.ICON_ERROR)
            return

        self._save_ui_to_config()

        if self._video_info and self._video_info.get("url") != url:
            self._video_info = None

        # 未解析 → 先解析再确认
        if not self._video_info:
            self._append_log("INFO", "[流程] 未解析视频信息，先进行解析...")
            self._pending_options = opts
            self._set_parse_buttons(False)
            try:
                base_cmd = CommandBuilder(self.config).build(
                    {**opts, "only_show_info": False, "show_all": False}, with_url=False)
            except Exception as ex:
                wx.MessageBox(f"命令构建失败: {ex}", "错误", wx.ICON_ERROR)
                self._set_parse_buttons(True)
                return

            work_dir = self.config.get("work_dir", "").strip() or os.getcwd()

            def on_info_then(info):
                self._set_parse_buttons(True)
                if not info and (not self._video_info or not self._video_info.get("title")):
                    self._handle_parse_failure()
                    return
                info = self._video_info or info
                if not info:
                    self._handle_parse_failure()
                    return
                if not info.get("pages"):
                    info["pages"] = [{"index": 1, "title": info.get("title", "")}]
                info["url"] = url
                self._video_info = info
                self.tc_video_info.SetValue(f"{info['title']}  （共 {len(info['pages'])} 个分P）")
                if len(info["pages"]) > 1:
                    self._open_page_picker_and_confirm(opts, info)
                else:
                    self._show_confirm_dialog(opts, info)

            self._info_thread = InfoParseThread(
                base_cmd, url, work_dir,
                lambda info: wx.CallAfter(on_info_then, info),
                self.log_queue.put)
            self._title_thread = TitleFetchThread(url, self._on_title_result, self.log_queue.put)
            self._title_thread.start()
            self._info_thread.start()
            return

        # 已解析
        if len(self._video_info.get("pages", [])) > 1 and not self.tc_page.GetValue().strip():
            self._open_page_picker_and_confirm(opts, self._video_info)
        else:
            self._show_confirm_dialog(opts, self._video_info)

    def _open_page_picker_and_confirm(self, opts, info):
        dlg = PageSelectDialog(
            self, info["pages"], info["title"],
            title_callback=self._refresh_title_from_api)
        if dlg.ShowModal() == wx.ID_OK:
            self.tc_page.SetValue(",".join(str(s) for s in dlg.selected))
            opts["select_page"] = self.tc_page.GetValue().strip()
            self._show_confirm_dialog(opts, info)
        dlg.Destroy()

    def _show_confirm_dialog(self, opts, info):
        """二次确认（内嵌登录状态，不弹额外窗口）"""
        summary = []
        api_map = {"web": "WEB", "tv": "TV", "app": "APP", "intl": "INTL"}
        summary.append(f"解析模式: {api_map.get(opts.get('api_mode', 'web'), 'WEB')}")

        mode = "视频+音频混流"
        for k, v in [("video_only", "仅视频"), ("audio_only", "仅音频"),
                       ("danmaku_only", "仅弹幕"), ("sub_only", "仅字幕"),
                       ("cover_only", "仅封面")]:
            if opts.get(k):
                mode = v
        summary.append(mode)

        if opts.get("use_aria2c"):
            summary.append("aria2c加速")
        if opts.get("download_danmaku"):
            summary.append("含弹幕")
        if opts.get("skip_mux"):
            summary.append("跳过混流")
        if opts.get("encoding"):
            summary.append(f"编码: {opts['encoding']}")
        if opts.get("dfn"):
            summary.append(f"画质: {opts['dfn']}（无则自动降级）")

        pages_text = self.tc_page.GetValue().strip() or f"全部 ({len(info['pages'])} 个)"
        pages_detail = pages_text
        if len(info["pages"]) <= 20:
            pages_detail = pages_text + "\n" + "\n".join(
                f"  P{p['index']}: {p['title']}" for p in info["pages"])

        try:
            cmd = CommandBuilder(self.config).build(opts)
            cmd_text = " ".join(shlex.quote(c) for c in cmd)
        except Exception as ex:
            cmd_text = f"(命令构建失败: {ex})"

        login_status, _, _ = detect_login_status(self.config)

        dlg = DownloadConfirmDialog(
            self, info["title"], pages_detail,
            " | ".join(summary), cmd_text, login_status)
        if dlg.ShowModal() == wx.ID_OK:
            self._actually_start_download(opts)
        dlg.Destroy()

    def _actually_start_download(self, opts):
        try:
            cmd = CommandBuilder(self.config).build(opts)
        except Exception as ex:
            wx.MessageBox(f"命令构建失败: {ex}", "错误", wx.ICON_ERROR)
            return
        work_dir = self.config.get("work_dir", "").strip() or os.getcwd()
        self.notebook.SetSelection(3)
        self._append_log("INFO", "═" * 60)
        self._append_log("INFO", f"[下载] ▶ 开始下载: {self._video_info['title']}")
        self._dl_thread = DownloadThread(cmd, work_dir, self.log_queue.put, self._on_download_finish)
        self._dl_thread.start()
        self.btn_download.Disable()
        self.btn_stop.Enable()

    def _on_download_finish(self, ok):
        wx.CallAfter(self._on_download_finish_ui, ok)

    def _on_download_finish_ui(self, ok):
        self.btn_download.Enable()
        self.btn_stop.Disable()
        self._append_log("SUCCESS" if ok else "ERROR",
                        "🎉 下载完成！" if ok else "❌ 下载失败！")
        if ok:
            wx.MessageBox("下载完成！", "成功", wx.ICON_INFORMATION)
        self._dl_thread = None

    def _on_stop_download(self, e):
        if self._dl_thread:
            self._append_log("WARN", "[用户] 请求停止下载...")
            self._dl_thread.stop()
            self.btn_stop.Disable()
            self.btn_download.Enable()

    # ─── 菜单事件 ───
    def _on_login_web(self, e):
        dlg = QRCodeLoginDialog(self, self.config, "web")
        dlg.ShowModal()
        dlg.Destroy()
        self._refresh_login_banner()

    def _on_login_tv(self, e):
        dlg = QRCodeLoginDialog(self, self.config, "tv")
        dlg.ShowModal()
        dlg.Destroy()
        self._refresh_login_banner()

    def _on_view_login_status(self, e):
        self._save_ui_to_config()
        status, detail, _ = detect_login_status(self.config)
        self._refresh_login_banner()
        wx.MessageBox(f"当前登录状态：{status}\n\n{detail}", "登录状态", wx.ICON_INFORMATION)

    def _on_clear_auth(self, e):
        self.config.set("cookie", "")
        self.config.set("access_token", "")
        self.config.save()
        self.tc_cookie.SetValue("")
        self.tc_token.SetValue("")
        for d in set([
            os.path.dirname(os.path.abspath(self.config.get("bbdown_path") or "")),
            self.config.get("work_dir") or "",
            os.getcwd(),
        ]):
            p = os.path.join(d, C.LOGIN_DATA_FILE)
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
        self._refresh_login_banner()
        self._append_log("INFO", "[鉴权] 已清除 Cookie 和 Token")

    def _on_open_work_dir(self, e):
        d = self.config.get("work_dir", "").strip() or os.getcwd()
        self._open_path(d)

    def _on_open_config(self, e):
        self._open_path(os.path.join(os.getcwd(), C.CONFIG_FILE))

    def _open_path(self, path):
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as ex:
            wx.MessageBox(f"打开失败: {ex}", "错误", wx.ICON_ERROR)

    def _on_about(self, e):
        wx.MessageBox(
            f"{APP_NAME} v{APP_VERSION}\n\n"
            f"BBDown 哔哩哔哩视频下载工具 · 图形前端\n\n"
            f"架构：\n"
            f"  • GUI 层：Python + wxPython\n"
            f"  • 执行层：subprocess 原生调用 CMD 子进程\n"
            f"  • 可对接 C/C++/Rust/Go/Java 等任意 CLI 工具\n\n"
            f"设计理念：\n"
            f"  GUI 只是壳，真正干活的是 CMD 里的原生程序\n\n"
            f"(c) 2026  BBDown GUI",
            "关于", wx.ICON_INFORMATION)

    # ─── 日志操作 ───
    def _on_clear_log(self, e):
        self.log_text.Clear()

    def _on_save_log(self, e):
        dlg = wx.FileDialog(self, "保存日志", wildcard="文本文件 (*.txt)|*.txt|所有文件 (*.*)|*.*",
                             style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() == wx.ID_OK:
            try:
                with open(dlg.GetPath(), "w", encoding="utf-8") as f:
                    f.write(self.log_text.GetValue())
                wx.MessageBox(f"日志已保存到: {dlg.GetPath()}", "成功", wx.ICON_INFORMATION)
            except Exception as ex:
                wx.MessageBox(f"保存失败: {ex}", "错误", wx.ICON_ERROR)
        dlg.Destroy()

    def _on_copy_log(self, e):
        if wx.Clipboard.Get().Open():
            wx.Clipboard.Get().SetData(wx.TextDataObject(self.log_text.GetValue()))
            wx.Clipboard.Get().Close()
            wx.MessageBox("日志已复制到剪贴板", "提示", wx.ICON_INFORMATION)

    def _on_open_in_cmd(self, e):
        try:
            opts = self._collect_options()
        except Exception as ex:
            wx.MessageBox(f"选项收集失败: {ex}", "错误", wx.ICON_ERROR)
            return
        try:
            cmd = CommandBuilder(self.config).build(opts)
        except Exception as ex:
            wx.MessageBox(f"命令构建失败: {ex}", "错误", wx.ICON_ERROR)
            return

        work_dir = self.config.get("work_dir", "").strip() or os.getcwd()
        cmd_str = " ".join(cmd_quote_win(c) for c in cmd)
        bat = os.path.join(work_dir, "_bbdown_run.bat")
        try:
            with open(bat, "w", encoding="utf-8") as f:
                f.write(f"@echo off\ncd /d \"{work_dir}\"\n")
                f.write(f"echo [BBDown GUI] {cmd_str}\npause\n")
        except Exception as ex:
            wx.MessageBox(f"写入失败: {ex}", "错误", wx.ICON_ERROR)
            return
        try:
            if sys.platform == "win32":
                subprocess.Popen(f'start "BBDown CMD" cmd /k "{bat}"', shell=True)
                self._append_log("INFO", f"[CMD] 已在独立窗口启动: {cmd_str[:120]}")
        except Exception as ex:
            wx.MessageBox(f"启动失败: {ex}", "错误", wx.ICON_ERROR)

    # ─── 收集选项（核心：用索引访问，永不解包出错） ───
    def _collect_options(self):
        opts = {
            "url": self.tc_url.GetValue().strip(),
            "api_mode": API_MAP.get(str(self.cb_api.GetSelection()), "web"),
            "encoding": self.cb_encoding.GetValue().strip(),
            "dfn": self.cb_dfn.GetValue().strip(),
            "select_page": self.tc_page.GetValue().strip(),
        }
        # 复选框：用索引访问 CHECKBOXES 元组
        for cb_data in CHECKBOXES:
            attr = cb_data[0]
            w = self.checkbox_widgets.get(attr)
            if w:
                opts[attr] = w.IsChecked()
        # 高级字段：用索引访问 ADV_FIELDS 元组
        for af in ADV_FIELDS:
            key = af[0]
            w = self.adv_widgets.get(key)
            if w:
                opts[key] = w.GetValue().strip()
        # 路径字段：用索引访问 PATH_FIELDS 元组
        for pf in PATH_FIELDS:
            key = pf[1]
            w = self.path_widgets.get(key)
            if w:
                opts[key] = w.GetValue().strip()

        opts["cookie"] = self.tc_cookie.GetValue().strip()
        opts["access_token"] = self.tc_token.GetValue().strip()
        opts["file_pattern"] = self.tc_file_pattern.GetValue().strip()
        opts["multi_file_pattern"] = self.tc_multi_pattern.GetValue().strip()
        return opts

    # ─── 关闭 ───
    def _on_close(self, e):
        if self._dl_thread:
            self._dl_thread.stop()
        self._save_ui_to_config()
        e.Skip()

    def _welcome_log(self):
        for t in [
            f"╔{'═' * 50}╗",
            f"║  {APP_NAME} v{APP_VERSION}                        ║",
            f"║  GUI=Python  │  执行层=原生CMD子进程          ║",
            f"╚{'═' * 50}╝",
        ]:
            self._append_log("INFO", t)
        self._append_log("INFO", f"[配置] BBDown: {self.config.get('bbdown_path') or 'BBDown (系统PATH)'}")
        self._append_log("INFO", f"[配置] 工作目录: {self.config.get('work_dir') or os.getcwd()}")
        st, _, _ = detect_login_status(self.config)
        self._append_log("INFO", f"[登录] 当前状态：{st}")
        self._append_log("INFO", "[提示] 粘贴地址 → 解析信息 → 确认下载")

    def _set_parse_buttons(self, enabled):
        for child in self.GetChildren():
            if isinstance(child, wx.Panel):
                for w in child.GetChildren():
                    if isinstance(w, wx.Button) and w.GetLabel().startswith("🔍"):
                        w.Enable(enabled)
