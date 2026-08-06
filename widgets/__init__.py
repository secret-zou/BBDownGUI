# widgets/__init__.py
# 导出公共控件，让 `from widgets import BrowsePathCtrl` 能找到
import os, sys
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)
from browse_path_ctrl import BrowsePathCtrl
