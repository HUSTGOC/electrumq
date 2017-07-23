# -*- coding: utf-8 -*-
from PyQt4 import QtCore
from PyQt4.QtGui import *

from UI.component import AccountIcon, AddressView, BalanceView, \
    FuncList, TxFilterView, TxTableView
from UI.layout.borderlayout import BorderLayout

__author__ = 'zhouqi'

try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    def _fromUtf8(s):
        return s

try:
    _encoding = QApplication.UnicodeUTF8


    def _translate(context, text, disambig):
        return QApplication.translate(context, text, disambig, _encoding)
except AttributeError:
    def _translate(context, text, disambig):
        return QApplication.translate(context, text, disambig)

DEFAULT_FONT = QFont('SansSerif', 10)
DEFAULT_TITLE = 'ElectrumQ'
DEFAULT_MAIN_SIZE = (800, 600)


class EQApplication(QApplication):
    pass


class EQMainWindow(QMainWindow):
    def __init__(self, **kwargs):
        super(EQMainWindow, self).__init__()
        self.view = MainController()
        self.setObjectName(_fromUtf8("MainWindow"))
        self.resize(*DEFAULT_MAIN_SIZE)
        self.setCentralWidget(self.view)


class MainController(QWidget):
    def __init__(self):
        super(MainController, self).__init__()
        # !!! note: !!!
        # Because BorderLayout doesn't call its super-class addWidget() it
        # doesn't take ownership of the widgets until setLayout() is called.
        # Therefore we keep a local reference to each label to prevent it being
        # garbage collected too soon.

        layout = BorderLayout()
        self.account_ctr = AccountController()
        layout.addWidget(self.account_ctr, BorderLayout.West)

        self.nav_ctr = NavController()
        self.nav_ctr.parent_controller = self
        self.nav_ctr.init_event()
        layout.addWidget(self.nav_ctr, BorderLayout.West)

        self.detail_ctr = DetailController()
        layout.addWidget(self.detail_ctr, BorderLayout.Center)

        self.setLayout(layout)
        self.setWindowTitle("ElectrumQ")

    def show_tab(self):
        self.detail_ctr.show_tab()
        print 'show tab'

    def show_receive(self):
        self.detail_ctr.show_receive()
        print 'show receive'

    def show_send(self):
        self.detail_ctr.show_send()
        print 'show send'


class AccountController(QWidget):
    def __init__(self):
        super(AccountController, self).__init__()

        layout = QVBoxLayout()
        accounts = ['btc', 'hd']
        for account in accounts:
            layout.addWidget(AccountIcon(account))
        layout.addItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))
        self.setLayout(layout)

    def add_account(self, account_name):
        pass


class NavController(QWidget):
    def __init__(self):
        super(NavController, self).__init__()
        self.parent_controller = None
        layout = QVBoxLayout()
        layout.addWidget(AddressView())
        layout.addWidget(BalanceView())
        func_list = FuncList()
        layout.addWidget(func_list)
        layout.addItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))
        self.setLayout(layout)

        self.tx_log_btn = func_list.tx_log_btn
        self.receive_btn = func_list.receive_btn
        self.send_btn = func_list.send_btn

    def init_event(self):
        self.tx_log_btn.clicked.connect(self.parent_controller.show_tab)
        self.receive_btn.clicked.connect(self.parent_controller.show_receive)
        self.send_btn.clicked.connect(self.parent_controller.show_send)


class DetailController(QWidget):
    def __init__(self):
        super(DetailController, self).__init__()
        layout = QVBoxLayout()
        self.tab_ctr = TabController()
        self.send_ctr = SendController()
        self.receive_ctl = ReceiveController()
        layout.addWidget(self.tab_ctr)
        layout.addWidget(self.send_ctr)
        layout.addWidget(self.receive_ctl)
        self.ctl_list = [self.tab_ctr, self.send_ctr, self.receive_ctl]
        for c in self.ctl_list:
            c.setVisible(False)
        self.show_ctl(self.tab_ctr)
        self.setLayout(layout)

    def show_ctl(self, ctl):
        for c in self.ctl_list:
            if c is not ctl and c.isVisible():
                c.setVisible(False)
        if not ctl.isVisible():
            ctl.setVisible(True)

    def show_tab(self):
        self.show_ctl(self.tab_ctr)
        print 'show tab'

    def show_receive(self):
        self.show_ctl(self.receive_ctl)
        print 'show receive'

    def show_send(self):
        self.show_ctl(self.send_ctr)
        print 'show send'


class TabController(QWidget):
    def __init__(self):
        super(TabController, self).__init__()
        layout = QVBoxLayout()
        layout.addWidget(TxFilterView())
        layout.addWidget(TxTableView())
        self.setLayout(layout)


class SendController(QWidget):
    def __init__(self):
        super(SendController, self).__init__()
        layout = QVBoxLayout()
        layout.addWidget(TxFilterView())
        layout.addWidget(AddressView())
        self.setLayout(layout)


class ReceiveController(QWidget):
    pass
