import functools
import base64
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets
import bubblesub.ui.editor
import bubblesub.ui.subs_grid
import bubblesub.ui.util
import bubblesub.ui.audio
import bubblesub.ui.video
import bubblesub.ui.statusbar


def _load_splitter_state(widget, data):
    widget.restoreState(base64.b64decode(data))


def _get_splitter_state(widget):
    return base64.b64encode(widget.saveState()).decode('ascii')


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, api):
        super().__init__()
        self._api = api
        self._update_title()

        api.gui.quit_requested.connect(self.close)
        api.gui.begin_update_requested.connect(
            lambda: self.setUpdatesEnabled(False))
        api.gui.end_update_requested.connect(
            lambda: self.setUpdatesEnabled(True))
        api.subs.loaded.connect(self._update_title)
        api.cmd.plugins_loaded.connect(self._setup_plugins_menu)

        self.video = bubblesub.ui.video.Video(api, self)
        self.audio = bubblesub.ui.audio.Audio(api, self)
        self.editor = bubblesub.ui.editor.Editor(api, self)
        self.console = QtWidgets.QPlainTextEdit(self, readOnly=True)
        self.subs_grid = bubblesub.ui.subs_grid.SubsGrid(api, self)
        self.status_bar = bubblesub.ui.statusbar.StatusBar(api, self)

        self.editor_splitter = QtWidgets.QSplitter(self)
        self.editor_splitter.setOrientation(QtCore.Qt.Vertical)
        self.editor_splitter.addWidget(self.audio)
        self.editor_splitter.addWidget(self.editor)
        self.editor_splitter.setStretchFactor(0, 4)
        self.editor_splitter.setStretchFactor(1, 1)

        self.top_bar = QtWidgets.QSplitter(self)
        self.top_bar.setOrientation(QtCore.Qt.Horizontal)
        self.top_bar.addWidget(self.video)
        self.top_bar.addWidget(self.editor_splitter)
        self.top_bar.setStretchFactor(0, 1)
        self.top_bar.setStretchFactor(1, 1)

        self.console_splitter = QtWidgets.QSplitter(self)
        self.console_splitter.setOrientation(QtCore.Qt.Horizontal)
        self.console_splitter.addWidget(self.subs_grid)
        self.console_splitter.addWidget(self.console)
        self.console_splitter.setStretchFactor(0, 2)
        self.console_splitter.setStretchFactor(1, 1)

        self.main_splitter = QtWidgets.QSplitter(self)
        self.main_splitter.setOrientation(QtCore.Qt.Vertical)
        self.main_splitter.addWidget(self.top_bar)
        self.main_splitter.addWidget(self.console_splitter)
        self.main_splitter.setContentsMargins(8, 8, 8, 8)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 5)

        action_map = self._setup_menu()
        self._setup_hotkeys(action_map)
        self._setup_plugins_menu()

        self.setCentralWidget(self.main_splitter)
        self.setStatusBar(self.status_bar)

        api.log.logged.connect(self._logged)

        self.apply_palette(api.opt.general['current_palette'])

        self.subs_grid.setFocus()
        self._restore_splitters()

    def closeEvent(self, event):
        self._store_splitters()
        if self._api.undo.needs_save and not bubblesub.ui.util.ask(
                'There are unsaved changes. '
                'Are you sure you want to exit the program?'):
            event.ignore()
        else:
            self.video.shutdown()
            event.accept()

    def apply_palette(self, palette_name):
        palette_def = self._api.opt.general['palettes'][palette_name]
        palette = QtGui.QPalette()
        for color_type, (red, green, blue) in palette_def.items():
            if '+' in color_type:
                group_name, role_name = color_type.split('+')
            else:
                group_name = ''
                role_name = color_type
            target_group = getattr(QtGui.QPalette, group_name, None)
            target_role = getattr(QtGui.QPalette, role_name, None)
            if target_group is not None and target_role is not None:
                palette.setColor(
                    target_group, target_role, QtGui.QColor(red, green, blue))
            elif target_role is not None:
                palette.setColor(target_role, QtGui.QColor(red, green, blue))
        self.setPalette(palette)
        self.update()

    def _logged(self, level, text):
        line = '[{}] {}\n'.format(level.name.lower(), text)
        print(line, end='')
        if level.name.lower() != 'debug':
            self.console.moveCursor(QtGui.QTextCursor.End)
            self.console.insertPlainText(line)

    def _setup_menu(self):
        return bubblesub.ui.util.setup_cmd_menu(
            self._api, self.menuBar(), self._api.opt.main_menu)

    def _setup_plugins_menu(self):
        plugins_menu_def = [['misc/reload-plugins'], None]
        for plugin_name in sorted(self._api.cmd.plugin_registry):
            plugins_menu_def.append((plugin_name, plugin_name))
        for action in self.menuBar().children():
            if action.objectName() == 'plugins-menu':
                self.menuBar().removeAction(action.menuAction())
        plugins_menu = self.menuBar().addMenu('Pl&ugins')
        plugins_menu.setObjectName('plugins-menu')
        bubblesub.ui.util.setup_cmd_menu(
            self._api, plugins_menu, plugins_menu_def)

    def _setup_hotkeys(self, action_map):
        shortcuts = {}

        def resolve_ambiguity(keys):
            widget = QtWidgets.QApplication.focusWidget()
            while widget:
                if widget == self.audio:
                    shortcuts[keys].activated.emit()
                widget = widget.parent()

        for context, items in self._api.opt.hotkeys.items():
            for item in items:
                keys, cmd_name, *cmd_args = item

                action = action_map.get((cmd_name, *cmd_args))
                if action and context == 'global':
                    # add shortcut hint text to the buttons in the menu
                    action.setShortcut(QtGui.QKeySequence(keys))
                    # prevent the action from triggering any signal on pressing
                    # its shortcut. (the action is parent of the main window,
                    # and the main window widget can never have focus by
                    # itself.)
                    # basically, all hotkey triggers are to be handled by the
                    # QShortcut below.
                    action.setShortcutContext(QtCore.Qt.WidgetShortcut)

                shortcut = QtWidgets.QShortcut(QtGui.QKeySequence(keys), self)
                shortcuts[keys] = shortcut

                shortcut.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
                shortcut.activated.connect(functools.partial(
                    self._api.cmd.run,
                    self._api.cmd.get(cmd_name, cmd_args)))
                if context == 'audio':
                    shortcut.setParent(self.audio)
                elif context != 'global':
                    raise RuntimeError('Invalid shortcut context')

                # when the user focuses some widget X or its child, and presses
                # a hotkey that's defined both for widget X and for the window,
                # qt doesn't know whether the user meant to use global hotkey
                # or the widget X hotkey since the focused widget is a
                # descendant of both the widget X and the main window.
                #
                # in case a shortcut is ambiguous, qt invokes the ambiguous
                # signals in turns each time user presses given shortcut.
                if context == 'global':
                    # since ambiguous keypress happens only if user has
                    # actually focused an ambiguous widget X, in case when it
                    # is the main window that receives ambiguous trigger, the
                    # main window must pass the event to the widget X.
                    shortcut.activatedAmbiguously.connect(
                        functools.partial(resolve_ambiguity, keys))
                else:
                    # in case where it is the ambiguous widget X that receives
                    # ambiguous trigger, it can just carry on with execution.
                    shortcut.activatedAmbiguously.connect(
                        shortcut.activated.emit)

    def _restore_splitters(self):
        splitter_cfg = self._api.opt.general.get('splitters', None)
        if not splitter_cfg:
            return
        _load_splitter_state(self.top_bar, splitter_cfg['top'])
        _load_splitter_state(self.editor_splitter, splitter_cfg['editor'])
        _load_splitter_state(self.main_splitter, splitter_cfg['main'])
        _load_splitter_state(self.console_splitter, splitter_cfg['console'])

    def _store_splitters(self):
        self._api.opt.general['splitters'] = {
            'top': _get_splitter_state(self.top_bar),
            'editor': _get_splitter_state(self.editor_splitter),
            'main': _get_splitter_state(self.main_splitter),
            'console': _get_splitter_state(self.console_splitter),
        }

    def _update_title(self):
        self.setWindowTitle(
            'bubblesub - {}'.format(self._api.subs.path)
            if self._api.subs.path else
            'bubblesub')
