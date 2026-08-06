#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BrowsePathCtrl - 带浏览按钮的路径输入框

核心技巧：GDI 对象（wx.Colour / wx.Font）延迟到首次使用时才创建，
避免模块导入时 "wx.App must be created first" 错误。
"""

import os
import wx

# 占位提示文字映射
HINT_MAP = {
    "bbdown_path":   "（未设置）点击右侧「浏览」选择 BBDown.exe",
    "ffmpeg_path":   "（未设置）点击右侧「浏览」选择 ffmpeg.exe",
    "mp4box_path":   "（未设置）点击右侧「浏览」选择 mp4box.exe",
    "aria2c_path":   "（未设置）点击右侧「浏览」选择 aria2c.exe",
    "work_dir":      "（未设置）点击右侧「浏览」选择下载目录",
}


class BrowsePathCtrl(wx.Panel):
    """
    复合控件：TextCtrl + 浏览按钮
    - 空值时显示灰色占位提示
    - 焦点进入时清空占位
    - 焦点离开时恢复占位
    - 路径变化时回调通知主窗口
    """

    # 类级缓存（延迟初始化，避免 wx.App 问题）
    _NORMAL_FONT = None
    _BOLD_FONT   = None
    _GREY        = None
    _BLACK       = None
    _INITED      = False

    @classmethod
    def _ensure_init(cls):
        """首次使用时才创建 GDI 对象"""
        if cls._INITED:
            return
        cls._NORMAL_FONT = wx.Font(
            9, wx.FONTFAMILY_DEFAULT,
            wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL
        )
        cls._BOLD_FONT = wx.Font(
            9, wx.FONTFAMILY_DEFAULT,
            wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD
        )
        cls._GREY  = wx.Colour(130, 130, 130)
        cls._BLACK = wx.Colour(0, 0, 0)
        cls._INITED = True

    def __init__(self, parent, key="", dialog_title="",
                 is_dir=False,
                 wildcard="可执行文件 (*.exe)|*.exe|所有文件 (*.*)|*.*"):
        super().__init__(parent)
        self.key = key
        self.dialog_title = dialog_title
        self.is_dir = is_dir
        self.wildcard = wildcard
        self._value = ""
        self._hint_text = HINT_MAP.get(key, "（未设置）")
        self._notify_cb = None

        sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.text_ctrl = wx.TextCtrl(self, size=(420, -1))
        self.text_ctrl.SetMinSize((420, -1))
        self._show_placeholder()

        self.btn_browse = wx.Button(self, label="浏览...", size=(90, -1))
        # ✅ 正确：Bind 大写 B
        self.btn_browse.Bind(wx.EVT_BUTTON, self._on_browse)

        sizer.Add(self.text_ctrl, 1, wx.EXPAND | wx.RIGHT, 5)
        sizer.Add(self.btn_browse, 0)
        self.SetSizer(sizer)

        # ✅ 正确：Bind 大写 B
        self.text_ctrl.Bind(wx.EVT_SET_FOCUS, self._on_focus_in)
        self.text_ctrl.Bind(wx.EVT_KILL_FOCUS, self._on_focus_out)
        self.text_ctrl.Bind(wx.EVT_TEXT, self._on_text_change)

    # ─── 占位提示逻辑 ───
    def _show_placeholder(self):
        self._ensure_init()
        self.text_ctrl.SetValue(self._hint_text)
        self.text_ctrl.SetForegroundColour(self._GREY)
        self.text_ctrl.SetFont(self._NORMAL_FONT)

    def _show_normal(self, text=""):
        self._ensure_init()
        self.text_ctrl.SetValue(text)
        self.text_ctrl.SetForegroundColour(self._BLACK)
        self.text_ctrl.SetFont(self._NORMAL_FONT)

    def _on_focus_in(self, event):
        val = self.text_ctrl.GetValue()
        if val == self._hint_text:
            self._show_normal("")
        event.Skip()

    def _on_focus_out(self, event):
        val = self.text_ctrl.GetValue().strip()
        if not val:
            self._show_placeholder()
        event.Skip()

    def _on_text_change(self, event):
        val = self.text_ctrl.GetValue()
        if val and val != self._hint_text:
            self._ensure_init()
            self.text_ctrl.SetForegroundColour(self._BLACK)
            self.text_ctrl.SetFont(self._NORMAL_FONT)
            if self._notify_cb:
                try:
                    self._notify_cb(val.strip())
                except Exception:
                    pass

    def _on_browse(self, event):
        current = self.text_ctrl.GetValue().strip()
        if self.is_dir:
            dlg = wx.DirDialog(
                self, self.dialog_title,
                defaultPath=current if current and os.path.isdir(current) else ""
            )
            if dlg.ShowModal() == wx.ID_OK:
                self.SetValue(dlg.GetPath())
            dlg.Destroy()
        else:
            dlg = wx.FileDialog(
                self, self.dialog_title,
                defaultDir=os.path.dirname(current) if current else "",
                defaultFile=os.path.basename(current) if current else "",
                wildcard=self.wildcard, style=wx.FD_OPEN
            )
            if dlg.ShowModal() == wx.ID_OK:
                self.SetValue(dlg.GetPath())
            dlg.Destroy()

    # ─── 公共接口 ───
    def GetValue(self):
        val = self.text_ctrl.GetValue()
        if val == self._hint_text:
            return ""
        return val.strip()

    def SetValue(self, val):
        if val and val.strip():
            self._show_normal(val.strip())
        else:
            self._show_placeholder()

    def set_notify_callback(self, callback):
        """设置路径变化时的通知回调"""
        self._notify_cb = callback

    def Bind(self, event_type, handler):
        """透传到内部 TextCtrl"""
        self.text_ctrl.Bind(event_type, handler)
