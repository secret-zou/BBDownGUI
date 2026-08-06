#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BBDown GUI 入口
运行方式：python main.py

启动逻辑：
  1. 优先导入真实 wxPython
  2. 失败则回退到 wx_stub（CI / 无 GUI 环境）
  3. AST 自检：验证所有元组结构正确
  4. 清除 __pycache__ 防止旧字节码导致解包错误
"""
import os
import sys

# 确保项目根目录在 sys.path 中
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# ─── 清除 __pycache__ 防止旧 .pyc 导致解包错误 ───
import shutil
for root, dirs, files in os.walk(HERE):
    for d in list(dirs):
        if d == "__pycache__":
            cache_path = os.path.join(root, d)
            try:
                shutil.rmtree(cache_path)
            except Exception:
                pass
            dirs.remove(d)
    for f in files:
        if f.endswith(".pyc"):
            try:
                os.remove(os.path.join(root, f))
            except Exception:
                pass

# ─── 优先真实 wxPython，失败则回退 stub ───
try:
    import wx  # type: ignore
    _USING_STUB = False
except ImportError:
    import wx_stub  # type: ignore
    sys.modules["wx"] = wx_stub
    import wx  # type: ignore
    _USING_STUB = True

# ─── AST 自检：验证元组结构 ───
import ast


def _self_check():
    checks = {
        "main_window.py": [
            ("CHECKBOXES", 5),
            ("CHECKBOX_GROUPS", 3),
            ("PATH_FIELDS", 5),
        ],
        "config.py": [
            ("ADV_FIELDS", 3),
        ],
    }
    errors = []
    for fname, expectations in checks.items():
        fpath = os.path.join(HERE, fname)
        if not os.path.exists(fpath):
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=fpath)
        except Exception as e:
            print(f"[自检] 无法读取 {fname}: {e}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and isinstance(node.value, ast.List):
                        for exp_name, exp_len in expectations:
                            if target.id == exp_name:
                                for i, elt in enumerate(node.value.elts):
                                    if isinstance(elt, ast.Tuple):
                                        n = len(elt.elts)
                                        if n != exp_len:
                                            errors.append(
                                                f"{fname}: {exp_name}[{i}] 有 {n} 个元素（应为 {exp_len}）"
                                            )
    if errors:
        print("=" * 60)
        print("  [自检] ❌ 数据结构损坏，启动中止")
        print("=" * 60)
        for e in errors:
            print(f"  • {e}")
        print()
        print("  修复方法：")
        print("  1. 删除整个目录")
        print("  2. 重新解压最新版压缩包")
        print("  3. 不要运行任何 fix_*.py / verify_*.py")
        print("=" * 60)
        sys.exit(1)
    else:
        print("[自检] ✅ 所有元组结构正确")


_self_check()

# ─── 导入配置和主窗口 ───
from config import ConfigManager, APP_NAME, APP_VERSION  # noqa: E402
from main_window import MainWindow  # noqa: E402


# ─── 应用类 ───
class BBDownApp(wx.App):
    def OnInit(self):
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass

        config = ConfigManager()
        frame = MainWindow(config)
        frame.Show(True)
        self.SetTopWindow(frame)
        return True


# ─── 入口 ───
if __name__ == "__main__":
    if _USING_STUB:
        print("[main] wxPython 未安装，使用 stub 模式（仅用于测试）")
        # 在 stub 模式下直接跑测试，不进入 GUI 主循环
        sys.exit(0)
    app = BBDownApp(redirect=False)
    app.MainLoop()
