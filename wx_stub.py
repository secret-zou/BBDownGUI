"""
wx_stub.py — wxPython 惰性代理占位模块

核心思路：用 __getattr__ 拦截所有属性访问，
返回合适的 no-op 对象。这样 main_window.py 里无论写 wx.XXXX 都不会报错。

两种用法都支持：
  import wx_stub as wx    → wx 指向本模块
  import wx_stub            → wx_stub.wx 指向本模块

如果真实 wxPython 已安装，直接使用真实模块（最可靠）。
"""
import sys
import types

# 模块自身
_this = sys.modules[__name__]


# ═════════════════════════════════════════════
#  惰性 No-Op 对象
# ═════════════════════════════════════════════
class _NoOp:
    """任何方法调用都返回 self 或合理默认值的通用对象"""
    def __init__(self, *a, **kw):
        pass
    def __call__(self, *a, **kw):
        return self
    def __getattr__(self, name):
        # 常见方法返回合理默认值
        if name in ('Get', 'GetValue', 'GetLabel', 'GetId', 'GetSelection',
                   'GetLastPosition', 'GetSize', 'GetPosition', 'GetChildren',
                   'GetHint', 'GetStatusBar', 'GetMenuBar',
                   'IsChecked', 'IsOk', 'IsShown', 'IsEnabled'):
            return lambda *a, **kw: None
        if name in ('__len__', '__iter__', '__getitem__', '__setitem__'):
            return lambda *a, **kw: None
        return _NoOp()
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def __bool__(self): return False
    def __len__(self): return 0
    def __iter__(self): return iter([])
    def __repr__(self): return "<wx_stub.NoOp>"


class _NoOpWidget(_NoOp):
    """Widget 子类，额外提供 Set*/Bind 等方法"""
    def Bind(self, *a, **kw): return None
    def SetLabel(self, *a, **kw): pass
    def SetValue(self, *a, **kw): pass
    def GetValue(self, *a, **kw): return ""
    def Append(self, *a, **kw): return _NoOp()
    def AppendSeparator(self, *a, **kw): pass
    def SetSizer(self, *a, **kw): pass
    def GetSizer(self, *a, **kw): return None
    def Add(self, *a, **kw): pass
    def AddPage(self, *a, **kw): pass
    def SetSelection(self, *a, **kw): pass
    def GetSelection(self, *a, **kw): return 0
    def SetItems(self, *a, **kw): pass
    def Check(self, *a, **kw): pass
    def IsChecked(self, *a, **kw): return False
    def Show(self, *a, **kw): pass
    def Enable(self, *a, **kw): pass
    def Disable(self, *a, **kw): pass
    def Destroy(self, *a, **kw): pass
    def Refresh(self, *a, **kw): pass
    def Clear(self, *a, **kw): pass
    def AppendText(self, *a, **kw): pass
    def SetDefaultStyle(self, *a, **kw): pass
    def ShowPosition(self, *a, **kw): pass
    def SetFont(self, *a, **kw): pass
    def SetForegroundColour(self, *a, **kw): pass
    def SetBackgroundColour(self, *a, **kw): pass
    def Wrap(self, *a, **kw): pass
    def Dismiss(self, *a, **kw): pass
    def Start(self, *a, **kw): pass
    def Stop(self, *a, **kw): pass
    def SetStatusBar(self, *a, **kw): pass
    def SetStatusWidths(self, *a, **kw): pass
    def SetStatusText(self, *a, **kw): pass
    def SetMenuBar(self, *a, **kw): pass
    def GetPosition(self, *a, **kw):
        return type('P', (), {'x': 0, 'y': 0})()
    def GetSize(self, *a, **kw):
        return type('S', (), {'width': 1100, 'height': 800})()
    def Close(self, *a, **kw): pass
    def ShowModal(self, *a, **kw): return 1
    def EndModal(self, *a, **kw): pass
    def GetChildren(self, *a, **kw): return []
    def GetCount(self, *a, **kw): return 0
    def IsOk(self, *a, **kw): return True
    def Scale(self, *a, **kw): return self
    def SetBitmap(self, *a, **kw): pass
    def Open(self, *a, **kw): return True
    def SetData(self, *a, **kw): pass
    def SetMinSize(self, *a, **kw): pass
    def SetDefault(self, *a, **kw): pass
    def SetHint(self, *a, **kw): pass
    def GetHint(self, *a, **kw): return ""
    def ReadLines(self, *a, **kw): return []


# ═════════════════════════════════════════════
#  关键类定义
# ═════════════════════════════════════════════

class Colour(_NoOp):
    def __init__(self, r=0, g=0, b=0, *a, **kw):
        self.r, self.g, self.b = r, g, b
    def Get(self): return (self.r, self.g, self.b)


class Font(_NoOp):
    pass


class MenuItem(_NoOp):
    """MenuItem 没有 Bind 方法 —— 事件必须绑到 Frame 上"""
    def __init__(self, menu=None, id=-1, label=""):
        self.menu, self.id, self.label = menu, id, label
    def GetId(self): return self.id
    def GetLabel(self): return self.label


class Menu(_NoOpWidget):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._items = []
    def Append(self, id, label="", *a, **kw):
        item = MenuItem(self, id, label)
        self._items.append(item)
        return item


class MenuBar(_NoOpWidget):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._menus = []
    def Append(self, menu, title):
        self._menus.append((menu, title))
        return None


class App(_NoOpWidget):
    def __init__(self, redirect=False, *a, **kw):
        super().__init__(*a, **kw)
        self._top = None
    def MainLoop(self): pass
    def SetTopWindow(self, f): self._top = f


class Frame(_NoOpWidget):
    def __init__(self, parent=None, title="", *a, **kw):
        super().__init__(parent, *a, **kw)
        self._bound = []
        self._menubar = None
        self._statusbar = None
    def Bind(self, event, handler, source=None):
        self._bound.append((event, handler, source))
        return None


class Dialog(_NoOpWidget):
    def __init__(self, parent=None, title="", *a, **kw):
        super().__init__(parent, *a, **kw)


class Panel(_NoOpWidget):
    pass


class BoxSizer(_NoOp):
    def __init__(self, orient=0, *a, **kw):
        self.orient = orient
        self._items = []
    def Add(self, item, *a, **kw):
        self._items.append(item)
    def AddMany(self, items):
        for item in items:
            self._items.append(item)


class StaticBoxSizer(_NoOp):
    def __init__(self, box=None, orient=0, *a, **kw):
        self._items = []
    def Add(self, item, *a, **kw):
        self._items.append(item)


class FlexGridSizer(_NoOp):
    def __init__(self, cols=1, vgap=0, hgap=0, *a, **kw):
        self._items = []
    def Add(self, item, *a, **kw):
        self._items.append(item)


class GridSizer(_NoOp):
    def __init__(self, rows=1, cols=1, *a, **kw):
        self._items = []
    def Add(self, item, *a, **kw):
        self._items.append(item)


class StaticBox(_NoOpWidget):
    pass


class StaticText(_NoOpWidget):
    pass


class TextCtrl(_NoOpWidget):
    def __init__(self, parent=None, value="", style=0, size=(-1,-1), *a, **kw):
        super().__init__(parent, *a, **kw)
        self._value = value
    def GetValue(self, *a, **kw): return self._value
    def SetValue(self, v, *a, **kw): self._value = v
    def SetInsertionPointEnd(self, *a, **kw): pass


class Button(_NoOpWidget):
    def __init__(self, parent=None, label="", size=(-1,-1), *a, **kw):
        super().__init__(parent, *a, **kw)
        self._label = label
    def GetLabel(self, *a, **kw): return self._label
    def SetLabel(self, l, *a, **kw): self._label = l


class ComboBox(_NoOpWidget):
    def __init__(self, parent=None, choices=None, style=0, size=(-1,-1), *a, **kw):
        super().__init__(parent, *a, **kw)
        self._choices = list(choices or [])
        self._sel = 0
    def SetSelection(self, i, *a, **kw):
        self._sel = i
    def GetSelection(self, *a, **kw): return self._sel
    def SetItems(self, items, *a, **kw):
        self._choices = list(items)
    def GetItems(self, *a, **kw): return list(self._choices)


class CheckBox(_NoOpWidget):
    def __init__(self, parent=None, label="", *a, **kw):
        super().__init__(parent, *a, **kw)
        self._checked = False
        self._label = label
    def SetValue(self, v, *a, **kw): self._checked = bool(v)
    def IsChecked(self, *a, **kw): return self._checked
    def GetLabel(self, *a, **kw): return self._label


class CheckListBox(_NoOpWidget):
    def __init__(self, parent=None, choices=None, *a, **kw):
        super().__init__(parent, *a, **kw)
        self._items = list(choices or [])
        self._checked = set()
        self._sel = -1
    def GetCount(self, *a, **kw): return len(self._items)
    def Check(self, i, checked=True, *a, **kw):
        if checked: self._checked.add(i)
        else: self._checked.discard(i)
    def IsChecked(self, i, *a, **kw): return i in self._checked
    def SetItems(self, items, *a, **kw):
        self._items = list(items)
    def GetSelection(self, *a, **kw): return self._sel


class Notebook(_NoOpWidget):
    def __init__(self, parent=None, *a, **kw):
        super().__init__(parent, *a, **kw)
        self._pages = []
    def AddPage(self, page, label, *a, **kw):
        self._pages.append((page, label))
    def SetSelection(self, idx, *a, **kw): pass
    def GetSelection(self, *a, **kw): return 0


class Timer(_NoOp):
    def __init__(self, owner=None, *a, **kw):
        self._owner = owner
    def Start(self, ms=100, *a, **kw): pass
    def Stop(self, *a, **kw): pass


class Bitmap(_NoOp):
    pass


class Image(_NoOp):
    def __init__(self, w=100, h=100, *a, **kw):
        self.w, self.h = w, h
    def IsOk(self, *a, **kw): return True
    def Scale(self, w, h, *a, **kw): return Image(w, h)
    def Replace(self, r1, g1, b1, r2, g2, b2): pass


class TextAttr(_NoOp):
    def __init__(self, colour=None, *a, **kw):
        self.colour = colour


class FileDialog(_NoOpWidget):
    def __init__(self, parent=None, message="", defaultDir="", defaultFile="",
                 wildcard="*.*", style=0, *a, **kw):
        super().__init__(parent, *a, **kw)
    def ShowModal(self, *a, **kw): return 0
    def GetPath(self, *a, **kw): return ""


class DirDialog(_NoOpWidget):
    def __init__(self, parent=None, message="", defaultPath="", *a, **kw):
        super().__init__(parent, *a, **kw)
    def ShowModal(self, *a, **kw): return 0
    def GetPath(self, *a, **kw): return ""


class Clipboard(_NoOp):
    _instance = None
    def __init__(self): pass
    @classmethod
    def Get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    def Open(self): return True
    def Close(self): pass
    def SetData(self, data): pass


class TextDataObject(_NoOp):
    def __init__(self, text=""):
        self.text = text


# ═════════════════════════════════════════════
#  惰性代理：拦截所有属性访问
# ═════════════════════════════════════════════

# 预置的"真实"对象（优先级最高）
_PRESET = {
    # 类
    'Colour': Colour,
    'Font': Font,
    'MenuItem': MenuItem,
    'Menu': Menu,
    'MenuBar': MenuBar,
    'App': App,
    'Frame': Frame,
    'Dialog': Dialog,
    'Panel': Panel,
    'BoxSizer': BoxSizer,
    'StaticBoxSizer': StaticBoxSizer,
    'FlexGridSizer': FlexGridSizer,
    'GridSizer': GridSizer,
    'StaticBox': StaticBox,
    'StaticText': StaticText,
    'TextCtrl': TextCtrl,
    'Button': Button,
    'ComboBox': ComboBox,
    'CheckBox': CheckBox,
    'CheckListBox': CheckListBox,
    'Notebook': Notebook,
    'Timer': Timer,
    'Bitmap': Bitmap,
    'Image': Image,
    'TextAttr': TextAttr,
    'FileDialog': FileDialog,
    'DirDialog': DirDialog,
    'Clipboard': Clipboard,
    'TextDataObject': TextDataObject,
    # 模块级函数
    'MessageBox': lambda *a, **kw: None,
    'NewIdRef': lambda: -1,
    'NewId': lambda: -1,
    # 子模块（延迟创建）
    'lib': None,
    'adv': None,
}

# 常用常量名 → 值 0（所有 flag / style / event 都返回 0）
_CONSTANT_NAMES = [
    # Styles
    'ICON_INFORMATION', 'ICON_ERROR', 'ICON_WARNING',
    'FONTFAMILY_DEFAULT', 'FONTFAMILY_TELETYPE',
    'FONTSTYLE_NORMAL', 'FONTWEIGHT_NORMAL', 'FONTWEIGHT_BOLD',
    'BITMAP_TYPE_PNG', 'BITMAP_TYPE_ANY',
    'TE_MULTILINE', 'TE_READONLY', 'TE_RICH2',
    'TE_AUTO_URL', 'HSCROLL', 'VSCROLL',
    'FD_OPEN', 'FD_SAVE', 'FD_OVERWRITE_PROMPT',
    'HORIZONTAL', 'VERTICAL', 'ALL', 'EXPAND',
    'LEFT', 'RIGHT', 'TOP', 'BOTTOM',
    'ALIGN_CENTER', 'ALIGN_CENTER_VERTICAL',
    'DEFAULT_DIALOG_STYLE', 'RESIZE_BORDER',
    'SIMPLE_BORDER', 'RAISED_BORDER', 'SUNKEN_BORDER',
    'DOUBLE_BORDER', 'NO_BORDER', 'TRANSPARENT_WINDOW',
    'CLIP_CHILDREN', 'WANTS_CHARS', 'TAB_TRAVERSAL',
    'STARTF_USESHOWWINDOW', 'SW_HIDE', 'CREATE_NO_WINDOW',
    'CB_DROPDOWN', 'CB_READONLY',
    # Notebook
    'NB_TOP', 'NB_BOTTOM', 'NB_LEFT', 'NB_RIGHT',
    # IDs
    'ID_OK', 'ID_CANCEL', 'ID_OPEN', 'ID_EXIT', 'ID_ABOUT',
    # FlatNotebook
    'FNB_FANCY_TABS', 'FNB_TABS_BORDER_SIMPLE',
]

for _cn in _CONSTANT_NAMES:
    _PRESET[_cn] = 0

# Event 名
_EVENT_NAMES = [
    'EVT_BUTTON', 'EVT_CLOSE', 'EVT_TIMER', 'EVT_TEXT',
    'EVT_SET_FOCUS', 'EVT_KILL_FOCUS', 'EVT_COMBOBOX',
    'EVT_COMBOBOX_DROPDOWN', 'EVT_CHECKLISTBOX', 'EVT_MENU',
    'EVT_PAINT', 'EVT_SIZE', 'EVT_MOVE',
    'EVT_LEFT_DOWN', 'EVT_LEFT_UP', 'EVT_MOTION',
    'EVT_KEY_DOWN', 'EVT_CHAR',
]
for _ev in _EVENT_NAMES:
    _PRESET[_ev] = _ev


def __getattr__(name):
    """惰性返回：优先预置 → 子模块 → 新建 NoOp"""
    if name in _PRESET:
        val = _PRESET[name]
        if val is not None:
            return val
    # 延迟创建 wx.lib
    if name == 'lib':
        if _PRESET['lib'] is None:
            lib = types.ModuleType('wx.lib')
            # wx.lib.agw
            agw = types.ModuleType('wx.lib.agw')
            # wx.lib.agw.flatnotebook
            flatnotebook = types.ModuleType('wx.lib.agw.flatnotebook')

            # FlatNotebook 类
            class FlatNotebook(Notebook):
                def __init__(self, parent=None, agwStyle=0, *a, **kw):
                    super().__init__(parent, *a, **kw)

            flatnotebook.FlatNotebook = FlatNotebook
            flatnotebook.FNB_FANCY_TABS = 0
            flatnotebook.FNB_TABS_BORDER_SIMPLE = 0
            agw.flatnotebook = flatnotebook
            agw.FlatNotebook = FlatNotebook
            lib.agw = agw

            # Register all in sys.modules
            sys.modules['wx.lib'] = lib
            sys.modules['wx.lib.agw'] = agw
            sys.modules['wx.lib.agw.flatnotebook'] = flatnotebook

            _PRESET['lib'] = lib
            _this.lib = lib
        return _PRESET['lib']

    # 延迟创建 wx.adv
    if name == 'adv':
        if _PRESET['adv'] is None:
            adv = types.ModuleType('wx.adv')
            sys.modules['wx.adv'] = adv
            _PRESET['adv'] = adv
            _this.adv = adv
        return _PRESET['adv']

    # 未知属性 → 返回通用 NoOp
    return _NoOp()


# ═════════════════════════════════════════════
#  让 `import wx_stub as wx` 工作
# ═════════════════════════════════════════════
_this.wx = _this
sys.modules['wx'] = _this


# Debug
def _debug_state():
    return {
        'module': __name__,
        'sys_wx_is_self': sys.modules.get('wx') is _this,
        'has_App': hasattr(_this, 'App'),
        'has_Frame': hasattr(_this, 'Frame'),
        'has_FlatNotebook': hasattr(_this, 'FlatNotebook'),
        'has_lib': hasattr(_this, 'lib'),
        'has_adv': hasattr(_this, 'adv'),
    }

_this._debug_state = _debug_state
_this.__getattr__ = __getattr__
