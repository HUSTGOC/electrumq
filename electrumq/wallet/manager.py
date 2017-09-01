# -*- coding: utf-8 -*-
import logging
import ConfigParser
import os
from functools import partial

import sys
from appdirs import AppDirs

from electrumq.blockchain import BlockChain
from electrumq.db.sqlite import init
from electrumq.network import NetWorkManager
from electrumq.utils import Singleton
from electrumq.utils.configuration import log_conf_path, conf_path, dirs
from electrumq.utils.parameter import set_testnet
from electrumq.wallet import WalletConfig, EVENT_QUEUE
from electrumq.wallet.single import SimpleWallet

__author__ = 'zhouqi'


class MyConfigParser(ConfigParser.RawConfigParser):
    def get(self, section, option):
        try:
            return ConfigParser.RawConfigParser.get(self, section, option)
        except ConfigParser.NoOptionError:
            return None


class Wallet(object):
    __metaclass__ = Singleton

    def __init__(self):
        set_testnet()
        logging.config.fileConfig(log_conf_path)
        init()
        network = NetWorkManager()
        network.start()
        BlockChain().init_header()

        # todo: init from config
        self.conf = MyConfigParser()
        self.conf.read(conf_path)
        self.wallet_dict = {}
        for k, v in self.conf.items('wallet'):
            if k.startswith('wallet_name_'):
                wallet_name = k[12:]
                wallet_type = self.conf.get('wallet', 'wallet_type_' + wallet_name)
                wallet_config_file = v  # self.conf.get('wallet', k)
                self.wallet_dict[wallet_name] = self.init_wallet(wallet_type, wallet_config_file)

        self._current = self.conf.get('wallet', 'current')
        if self._current is not None:
            self.current_wallet = self.wallet_dict[self._current]
            self.current_wallet.init()
        else:
            self.current_wallet = None

    def init_wallet(self, wallet_type, wallet_config_file):
        if wallet_type == 'simple':
            return SimpleWallet(WalletConfig(store_path=dirs.user_data_dir + '/' + wallet_config_file))
        return None

    def new_wallet(self, wallet_name, wallet_type, wallet_config_file, wallet):
        self.wallet_dict[wallet_name] = wallet
        self.conf.set("wallet", "wallet_name_" + wallet_name, wallet_config_file)
        self.conf.set("wallet", "wallet_type_" + wallet_name, wallet_type)
        if self.current_wallet is None:
            self.conf.set('wallet', 'current', wallet_name)
        self.conf.write(open(conf_path, "w"))
        if len(self.new_wallet_event) > 0:
            global EVENT_QUEUE
            for event in set(self.new_wallet_event):
                EVENT_QUEUE.put(partial(event, wallet_name))
        if self.current_wallet is None:
            self.change_current_wallet(0)
        return self.wallet_dict[wallet_name]

    def change_current_wallet(self, idx):
        if idx < len(self.wallet_dict.keys()):
            self.current_wallet = self.wallet_dict[self.wallet_dict.keys()[idx]]
            global EVENT_QUEUE
            if len(self.current_wallet_changed_event) > 0:
                for event in set(self.current_wallet_changed_event):
                    EVENT_QUEUE.put(event)

    new_wallet_event = []
    current_wallet_changed_event = []

    '''
    wallet need show
    1. wallet name
    2. display address
    3. balance 
    4. tx  (tx_hash, tx_time, tx_delta for hole wallet)
    '''