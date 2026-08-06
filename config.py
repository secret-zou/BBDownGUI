#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config.py - 配置管理 + 常量 + HINT 字典
"""

import os, json

APP_NAME = "BBDown GUI"
APP_VERSION = "3.6.1"
CONFIG_FILE = "BBDownGUI.config"
QRCODE_FILE = "qrcode.png"
LOGIN_DATA_FILE = "BBDown.data"
LOG_LINES_MAX = 5000

# 模块级 DEFAULTS（供 main_window.py 直接导入）
DEFAULTS = {
    "bbdown_path": "",
    "ffmpeg_path": "",
    "mp4box_path": "",
    "aria2c_path": "",
    "work_dir": "",
    "last_save_dir": "",
    "cookie": "",
    "access_token": "",
    "user_agent": "",
    "upos_host": "",
    "language": "",
    "delay_per_page": "0",
    "aria2c_args": "-x16 -s16 -j16 -k 5M",
    "file_pattern": "<videoTitle>",
    "multi_file_pattern": "<videoTitle>/[P<pageNumberWithZero>]<pageTitle>",
    "config_file": "",
    "window_x": 100,
    "window_y": 100,
    "window_w": 1100,
    "window_h": 800,
}

# 占位提示文字（空值时的灰色提示）
HINT = {
    "bbdown_path":     "（未设置）点击右侧「浏览」选择 BBDown.exe",
    "ffmpeg_path":     "（未设置）点击右侧「浏览」选择 ffmpeg.exe",
    "mp4box_path":     "（未设置）点击右侧「浏览」选择 mp4box.exe",
    "aria2c_path":     "（未设置）点击右侧「浏览」选择 aria2c.exe",
    "work_dir":        "（未设置）点击右侧「浏览」选择下载目录",
    "file_pattern":    "<videoTitle>",
    "multi_file_pattern": "<videoTitle>/[P<pageNumberWithZero>]<pageTitle>",
    "cookie":          "SESSDATA=******（留空则不设置）",
    "token":           "access_token（留空则不设置）",
    "user_agent":      "自定义 UA（留空=随机）",
    "upos_host":       "自定义 upos 服务器（留空=默认）",
    "language":        "如 chi, jpn, eng（留空=默认）",
    "delay_per_page":  "合集分P间下载间隔秒数（0=无间隔）",
    "aria2c_args":     "-x16 -s16 -j16 -k 5M",
    "host":            "BiliPlus host（需配合 area）",
    "ep_host":         "BiliPlus EP host",
    "area":            "hk / tw / th",
    "config_file":      "BBDown 配置文件路径（留空=默认 BBDown.config）",
}


class ConfigManager:
    """读写 JSON 配置文件"""

    def __init__(self, path=CONFIG_FILE):
        self.path = path
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self.data.update(loaded)
        except Exception:
            pass

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def get(self, key, default=None):
        if key in self.data:
            return self.data[key]
        if default is not None:
            return default
        return DEFAULTS.get(key, "")

    def set(self, key, value):
        self.data[key] = value
