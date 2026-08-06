================================================================================
  BBDown GUI v3.7.1 — 哔哩哔哩视频下载工具 · 图形前端
================================================================================

【项目结构】
  BBDownGUI_clean/
  ├── __init__.py               包标识
  ├── main.py                   入口（python main.py 直接运行）
  ├── config.py                 常量 + 配置管理
  ├── utils.py                  URL规范化 / 登录检测 / B站API / 诊断
  ├── command_builder.py        UI选项 → CLI参数构建
  ├── threads.py                日志队列 + 下载/解析/标题线程
  ├── dialogs.py               二维码登录 / 分P选择 / 下载确认
  ├── main_window.py           主窗口 + 事件 + 下载流程
  ├── widgets/
  │   ├── __init__.py          导出 BrowsePathCtrl
  │   └── browse_path_ctrl.py 路径浏览自定义控件
  ├── wx_stub.py              无GUI环境占位（CI/测试用）
  ├── cleanup.py               清理 __pycache__ 脚本
  ├── test_import_chain.py     导入链验证
  ├── test_end_to_end.py       端到端测试（90项）
  └── README.txt               本文件

【安装依赖】
  pip install wxPython>=4.2.0

【启动方式】
  方式一（推荐）：  python main.py
  方式二（模块）：  python -m BBDownGUI_clean.main

  首次运行前建议先执行：
  python cleanup.py

【常见问题排查】

  问题1: ImportError: attempted relative import with no known parent package
  → 原因：直接从子目录运行了某个模块文件
  → 解决：始终从项目根目录运行 `python main.py`

  问题2: ImportError: cannot import name 'BrowsePathCtrl' from 'widgets'
  → 原因：widgets/__init__.py 为空或被覆盖
  → 解决：确认 widgets/__init__.py 内容为：
            from .browse_path_ctrl import BrowsePathCtrl

  问题3: ValueError: too many values to unpack (expected N, got M)
  → 原因：运行了旧版 fix_*.py / verify_*.py 脚本改坏了元组
  → 解决：删除整个目录 → 重新解压 → 不要运行任何 fix/verify 脚本

  问题4: [WinError 2] 系统找不到指定的文件
  → 原因：BBDown 路径未设置或路径错误
  → 解决：到「路径设置」页点击「浏览」选择 BBDown.exe
  → 下载地址：https://github.com/nilaoda/BBDown/releases

  问题5: MenuItem object has no attribute 'Bind'
  → 原因：代码用了小写 .bind() 或 self.bind()
  → 解决：确保用的是大写 .Bind() 且绑到 Frame 上

【不要做的事情】
  ❌ 不要运行 fix_*.py / apply_*.py / verify_*.py
  ❌ 不要从旧版本复制 .py 文件覆盖
  ❌ 不要手动修改 CHECKBOXES 等元组的内容

【版本历史】
  v3.7.1  修复导入链：widgets/__init__.py 导出、main.py 包路径初始化
  v3.7.0  导入链重构，支持 python main.py 和 python -m 两种方式
  v3.6.0  中文界面 + 登录状态内嵌确认对话框
  v3.5.0  模块化拆分（10个文件）
  v3.2.0  B站API获取真实标题 + 分P小标题
  v2.2.0  画质降级链 + 登录状态检测

【测试验证】
  python test_import_chain.py    → 27项导入链测试
  python test_end_to_end.py     → 90项端到端测试

================================================================================
