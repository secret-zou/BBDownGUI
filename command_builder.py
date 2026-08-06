#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""command_builder.py - UI options -> BBDown CLI arguments"""

import os, sys, shlex
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import normalize_bilibili_url

# 编码单选列表（用户只选一个，自动补全回退链）
ENCODING_ORDER = ["hevc", "av1", "avc"]

# 画质阶梯（从高到低）
DFN_LADDER = [
    "8K 超高清", "杜比视界", "HDR 真彩", "4K 超清",
    "1080P 高码率", "1080P 高清", "720P 高清",
    "480P 清晰", "360P 流畅",
    "杜比全景声",
]


class CommandBuilder:
    """将 UI 选项转换为 BBDown CLI 参数列表"""

    VALID_ENCODINGS = ENCODING_ORDER
    VALID_DFNS     = DFN_LADDER

    def __init__(self, config):
        self.config = config

    # ── 单选 → 自动降级链 ──
    @classmethod
    def build_encoding_chain(cls, choice: str) -> list:
        c = (choice or "").strip().lower()
        if c not in cls.VALID_ENCODINGS:
            return []
        return [c] + [e for e in cls.VALID_ENCODINGS if e != c]

    @classmethod
    def build_dfn_chain(cls, choice: str) -> list:
        c = (choice or "").strip()
        if c not in cls.VALID_DFNS:
            return []
        idx = cls.VALID_DFNS.index(c)
        chain = cls.VALID_DFNS[idx:]
        if c != "杜比全景声":
            chain = [d for d in chain if d != "杜比全景声"]
        return chain

    # ── 主构建方法 ──
    def build(self, options: dict, with_url: bool = True) -> list:
        cmd, cfg = [], self.config

        bbdown = (cfg.get("bbdown_path") or "").strip()
        cmd.append(bbdown if bbdown else "BBDown")

        url = normalize_bilibili_url(options.get("url", ""))
        if with_url:
            if not url:
                raise ValueError("视频地址不能为空")
            cmd.append(url)

        # API 模式
        mode = (options.get("api_mode") or "web").lower()
        api_flag = {
            "tv":   "--use-tv-api",
            "app":  "--use-app-api",
            "intl": "--use-intl-api",
        }.get(mode, "")
        if api_flag:
            cmd.append(api_flag)

        # 编码 / 画质（单选 → 降级链）
        enc_chain = self.build_encoding_chain(options.get("encoding", ""))
        dfn_chain = self.build_dfn_chain(options.get("dfn", ""))
        if enc_chain:
            cmd += ["--encoding-priority", ",".join(enc_chain)]
        if dfn_chain:
            cmd += ["--dfn-priority", ",".join(dfn_chain)]

        # 布尔开关
        flags = [
            ("only_show_info",    "--only-show-info"),
            ("show_all",         "--show-all"),
            ("video_only",       "--video-only"),
            ("audio_only",       "--audio-only"),
            ("danmaku_only",     "--danmaku-only"),
            ("sub_only",         "--sub-only"),
            ("cover_only",       "--cover-only"),
            ("download_danmaku", "--download-danmaku"),
            ("skip_mux",         "--skip-mux"),
            ("skip_subtitle",    "--skip-subtitle"),
            ("skip_cover",      "--skip-cover"),
            ("skip_ai",         "--skip-ai"),
            ("use_aria2c",      "--use-aria2c"),
            ("use_mp4box",      "--use-mp4box"),
            ("hide_streams",     "--hide-streams"),
            ("multi_thread",    "--multi-thread"),
            ("video_ascending",  "--video-ascending"),
            ("audio_ascending",  "--audio-ascending"),
            ("allow_pcdn",      "--allow-pcdn"),
            ("force_http",      "--force-http"),
            ("debug",            "--debug"),
            ("interactive",      "-ia"),
        ]
        for key, flag in flags:
            if options.get(key):
                cmd.append(flag)

        # 键值对（优先 options，回落 config）
        kv_pairs = [
            ("select_page",      "--select-page"),
            ("cookie",          "--cookie"),
            ("access_token",     "--access-token"),
            ("user_agent",      "--user-agent"),
            ("work_dir",        "--work-dir"),
            ("ffmpeg_path",     "--ffmpeg-path"),
            ("mp4box_path",     "--mp4box-path"),
            ("aria2c_path",     "--aria2c-path"),
            ("upos_host",       "--upos-host"),
            ("language",        "--language"),
            ("delay_per_page",  "--delay-per-page"),
            ("aria2c_args",     "--aria2c-args"),
            ("file_pattern",    "--file-pattern"),
            ("multi_file_pattern","--multi-file-pattern"),
            ("host",            "--host"),
            ("ep_host",         "--ep-host"),
            ("area",            "--area"),
            ("config_file",     "--config-file"),
        ]
        for key, flag in kv_pairs:
            val = (options.get(key) or cfg.get(key) or "").strip()
            if val:
                cmd += [flag, val]

        if options.get("force_replace_host"):
            cmd.append("--force-replace-host")

        return cmd
