import enum
import bubblesub.util
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets


class ColumnType(enum.Enum):
    Start = 0
    End = 1
    Style = 2
    Actor = 3
    Text = 4
    Duration = 5
    CharactersPerSecond = 6


_CACHE_TEXT = 0
_CACHE_CPS_BK = 1

_HEADERS = {
    ColumnType.Start: 'Start',
    ColumnType.End: 'End',
    ColumnType.Style: 'Style',
    ColumnType.Actor: 'Actor',
    ColumnType.Text: 'Text',
    ColumnType.Duration: 'Duration',
    ColumnType.CharactersPerSecond: 'CPS',
}


class SubsGridModel(QtCore.QAbstractTableModel):
    def __init__(self, api, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._subtitles = api.subs.lines
        self._subtitles.item_changed.connect(self._proxy_data_changed)
        self._subtitles.items_inserted.connect(self._proxy_items_inserted)
        self._subtitles.items_removed.connect(self._proxy_items_removed)
        self._column_order = [
            ColumnType.Start,
            ColumnType.End,
            ColumnType.Style,
            ColumnType.Actor,
            ColumnType.Text,
            ColumnType.Duration,
            ColumnType.CharactersPerSecond,
        ]
        self._cache = []
        self._reset_cache()

        self._character_limit = (
            api.opt.general['subs']['max_characters_per_second'])

    def rowCount(self, _parent=QtCore.QModelIndex()):
        return len(self._subtitles)

    def columnCount(self, _parent=QtCore.QModelIndex()):
        return len(self._column_order)

    def headerData(self, idx, orientation, role=QtCore.Qt.DisplayRole):
        if orientation == QtCore.Qt.Vertical:
            if role == QtCore.Qt.DisplayRole:
                return idx + 1
            elif role == QtCore.Qt.TextAlignmentRole:
                return QtCore.Qt.AlignRight

        elif orientation == QtCore.Qt.Horizontal:
            column_type = self._column_order[idx]
            if role == QtCore.Qt.DisplayRole:
                return _HEADERS[column_type]
            elif role == QtCore.Qt.TextAlignmentRole:
                if column_type == ColumnType.Text:
                    return QtCore.Qt.AlignLeft
                return QtCore.Qt.AlignCenter

        return QtCore.QVariant()

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.DisplayRole:
            row_number = index.row()
            column_number = index.column()
            column_type = self._column_order[column_number]

            data = self._cache[row_number][_CACHE_TEXT]
            if not data:
                subtitle = self._subtitles[row_number]
                data = {
                    ColumnType.Start: bubblesub.util.ms_to_str(subtitle.start),
                    ColumnType.End: bubblesub.util.ms_to_str(subtitle.end),
                    ColumnType.Style: subtitle.style,
                    ColumnType.Actor: subtitle.actor,
                    ColumnType.Text:
                        bubblesub.util.ass_to_plaintext(subtitle.text, True),
                    ColumnType.Duration:
                        '{:.1f}'.format(subtitle.duration / 1000.0),
                    ColumnType.CharactersPerSecond: (
                        '{:.1f}'.format(
                            bubblesub.util.character_count(subtitle.text) /
                            max(1, subtitle.duration / 1000.0))
                        if subtitle.duration > 0
                        else '-')
                }
                self._cache[row_number][_CACHE_TEXT] = data
            return data[column_type]

        elif role == QtCore.Qt.BackgroundRole:
            row_number = index.row()
            column_number = index.column()
            column_type = self._column_order[column_number]

            if column_type != ColumnType.CharactersPerSecond:
                return

            data = self._cache[row_number][_CACHE_CPS_BK]
            if not data:
                subtitle = self._subtitles[row_number]
                ratio = (
                    bubblesub.util.character_count(subtitle.text) /
                    max(1, subtitle.duration / 1000.0))
                ratio -= self._character_limit
                ratio = max(0, ratio)
                ratio /= self._character_limit
                ratio = min(1, ratio)
                data = QtGui.QColor(
                    bubblesub.ui.util.blend_colors(
                        self.parent().palette().base().color(),
                        self.parent().palette().highlight().color(),
                        ratio))
                self._cache[row_number][_CACHE_CPS_BK] = data
            return data

        elif role == QtCore.Qt.TextAlignmentRole:
            column_number = index.column()
            column_type = self._column_order[column_number]
            if column_type == ColumnType.Text:
                return QtCore.Qt.AlignLeft
            return QtCore.Qt.AlignCenter

        return QtCore.QVariant()

    def flags(self, _index):
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def _proxy_data_changed(self, idx):
        self._reset_cache(idx)

        # XXX: this causes qt to call .data() for EVERY VISIBLE CELL. really.
        # self.dataChanged.emit(
        #     self.index(idx, 0),
        #     self.index(idx, self.columnCount() - 1),
        #     [QtCore.Qt.DisplayRole | QtCore.Qt.BackgroundRole])
        for i in range(self.columnCount()):
            self.dataChanged.emit(
                self.index(idx, i),
                self.index(idx, i),
                [QtCore.Qt.DisplayRole, QtCore.Qt.BackgroundRole])

    def _proxy_items_inserted(self, idx, count):
        self._reset_cache()
        if count:
            self.rowsInserted.emit(QtCore.QModelIndex(), idx, idx + count - 1)

    def _proxy_items_removed(self, idx, count):
        self._reset_cache()
        if count:
            self.rowsRemoved.emit(QtCore.QModelIndex(), idx, idx + count - 1)

    def _reset_cache(self, idx=None):
        if idx:
            self._cache[idx] = [None, None]
        else:
            self._cache = [[None, None] for i in range(len(self._subtitles))]


class SubsGrid(QtWidgets.QTableView):
    def __init__(self, api):
        super().__init__()
        self._api = api
        self.setModel(SubsGridModel(api, self))
        self.horizontalHeader().setSectionResizeMode(
            4, QtWidgets.QHeaderView.Stretch)
        self.verticalHeader().setDefaultSectionSize(24)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setTabKeyNavigation(False)

        api.subs.loaded.connect(self._subs_loaded)
        api.subs.selection_changed.connect(self._api_selection_changed)
        self.selectionModel().selectionChanged.connect(
            self._widget_selection_changed)

    def _collect_rows(self):
        rows = set()
        for index in self.selectionModel().selectedIndexes():
            rows.add(index.row())
        return list(rows)

    def _subs_loaded(self):
        self.scrollTo(
            self.model().index(0, 0),
            self.EnsureVisible | self.PositionAtTop)

    def _widget_selection_changed(self, _selected, _deselected):
        if self._collect_rows() != self._api.subs.selected_lines:
            self._api.subs.selected_lines = self._collect_rows()

    def _api_selection_changed(self):
        if self._collect_rows() == self._api.subs.selected_lines:
            return

        selection = QtCore.QItemSelection()
        for row in self._api.subs.selected_lines:
            idx = self.model().index(row, 0)
            selection.select(idx, idx)

        self.selectionModel().select(
            selection,
            QtCore.QItemSelectionModel.Clear |
            QtCore.QItemSelectionModel.Rows |
            QtCore.QItemSelectionModel.Select)

        if self._api.subs.selected_lines:
            self.scrollTo(
                self.model().index(self._api.subs.selected_lines[0], 0))
