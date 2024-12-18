from abc import ABC, abstractmethod
# from abc import ABC, abstractmethod
import pandas as pd
import numpy as np
from datetime import datetime, timezone, date, timedelta

import json
import os
import requests
from websocket import create_connection

import eth_account
from eth_account.signers.local import LocalAccount

from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils.constants import MAINNET_API_URL, TESTNET_API_URL

# Generic DEX Interface
class DEXInterface(ABC):
    @abstractmethod
    def get_universe(self) -> list:
        """Get the tradable assets from the DEX."""
        pass

    @abstractmethod
    def set_portfolio_weights(self, weights: dict) -> dict:
        """Fetch the current position for the given symbol."""
        pass

# HyperLiquid DEX Implementation
class HyperLiquidDEX(DEXInterface):
    def __init__(self, which_net="testnet"):
        if which_net == "testnet":
            self.base_url = TESTNET_API_URL
        elif which_net == "mainnet":
            self.base_url = MAINNET_API_URL

        #present working directory for config file (maybe don't need this)
        self.pwd = "" 
        
        #get universe
        self.universe = None
        self.set_universe()

        #setup credentials
        self.address, self.info, self.exchange, self.net_liq = self.setup()
        
        #get current positions
        self.positions = None
        self.update_current_positions()
        
        
    def setup(self, skip_ws=False):
        config_path = os.path.join(os.path.dirname(self.pwd), "hyperliquid_config.json")
        with open(config_path) as f:
            config = json.load(f)
        account: LocalAccount = eth_account.Account.from_key(config["secret_key"])
        address = config["account_address"]
        if address == "":
            address = account.address
        print("[DEX] Running with account address:", address)
        if address != account.address:
            print("[DEX] Running with agent address:", account.address)
        info = Info(self.base_url, skip_ws)
        user_state = info.user_state(address)
        spot_user_state = info.spot_user_state(address)
        margin_summary = user_state["marginSummary"]
        # if float(margin_summary["accountValue"]) == 0 and len(spot_user_state["balances"]) == 0:
        #     print("[DEX] Not running because the provided account has no equity.")
        #     url = info.base_url.split(".", 1)[1]
        #     error_string = f"No accountValue:\nIf you think this is a mistake, make sure that {address} has a balance on {url}.\nIf address shown is your API wallet address, update the config to specify the address of your account, not the address of the API wallet."
        #     raise Exception(error_string)
        exchange = Exchange(account, self.base_url, account_address=address)
        return address, info, exchange, float(margin_summary["accountValue"])

    def get_universe(self) -> list:
        """Get the tradable assets from the DEX."""
        return self.universe.index.to_list()

    def set_universe(self):
        if self.base_url == MAINNET_API_URL:
            url = "https://api.hyperliquid.xyz/info"
        else:
            url = "https://api.hyperliquid-testnet.xyz/info"
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "type": "meta"
        }

        response = requests.post(url, headers=headers, json=data)

        if response.status_code == 200:
            self.universe = pd.DataFrame( response.json()['universe'] ).set_index('name')
            print("[DEX] Universe Set Successfully.")
        else:
            print(f"[DEX] Request failed with status code {response.status_code}")
            print(response.text)  # Print the error message if any

    def set_portfolio_weights(self, weights: dict):
        """Fetch the current position for the given symbol."""
        self.address, self.info, self.exchange, self.net_liq = self.setup() #update info
        self.cancel_open_orders() #cancel open orders
        self.update_current_positions()

        #set each portfolio weight, 1 at a time
        for symbol in weights.keys():
            dollar_weight = weights[symbol] * self.net_liq
            if symbol in self.positions.keys():
                dollar_weight = dollar_weight - self.positions[symbol]
            if abs( dollar_weight ) > 0:
                print(f'[DEX] setting weight {symbol}: {dollar_weight}')
                order_result = self.add_new_order( symbol, dollar_weight )

        for symbol in self.positions.keys():
            if symbol not in weights.keys():
                dollar_weight = - self.positions[symbol]
                print(f'[DEX] setting weight (closing) {symbol}')
                order_result = self.add_new_order( symbol, dollar_weight )

    def update_current_positions(self):
        # Get the user state and print out position information
        user_state = self.info.user_state(self.address)
        positions = {}
        for position in user_state["assetPositions"]:
            pos = position["position"]
            positions[ pos['coin'] ] = float( pos['positionValue'] ) * np.sign( float( pos['szi'] ) )
            
        if len(positions) > 0:
            print("[DEX] Getting Positions.")
            for k in positions.keys():
                print(f"[DEX] {k}: {positions[k]}")
        else:
            print("[DEX] No Open Positions")
        self.positions = positions

    def get_bid_ask(self, symbol: str ) -> (float, float):
        # WebSocket URI
        if self.base_url == MAINNET_API_URL:
            uri = "wss://api.hyperliquid.xyz/ws"
        else:
            uri = "wss://api.hyperliquid-testnet.xyz/ws"
        
        # Payload
        payload = {
            "method": "post",
            "id": 123,
            "request": {
                "type": "info",
                "payload": {
                    "type": "l2Book",
                    "coin": symbol,
                    "mantissa": None
                }
            }
        }
    
        best_bid, best_ask = None, None
        
        # Connect to the WebSocket server
        try:
            ws = create_connection(uri)
            print(f"[DEX] Connected to WebSocket getting Bid/Ask for {symbol}.")
        
            # Send the payload
            ws.send(json.dumps(payload))
            print(f"Sent: {json.dumps(payload)}")
        
            # Receive response
            response = ws.recv()
    
            resp = json.loads( response )
            print(resp)
            levels = resp['data']['response']['payload']['data']['levels']
            best_bid = float( levels[0][0]['px'] )
            best_ask = float( levels[1][0]['px'] )
            
            # Close connection
            ws.close()
            print("[DEX] Connection closed")
        except Exception as e:
            print(f"Error: {e}")
    
        return best_bid, best_ask

    def get_open_orders(self, symbol: str) -> list:
        pass

    def cancel_open_orders(self) -> bool:
        open_orders = self.info.open_orders(self.address)
        for open_order in open_orders:
            print(f"[DEX] Cancelling order {open_order}")
            self.exchange.cancel(open_order["coin"], open_order["oid"])
        return True

    def add_new_order(self, symbol: str, dollar_weight: float) -> bool:
        if abs( dollar_weight ) < 12:
            print('[DEX] Dollar Weight too small, not sending order')
            return False
            
        best_bid, best_ask = self.get_bid_ask( symbol )
        if best_bid is None or best_ask is None:
            print('[DEX] no price data for ', symbol)
            return False
            
        if dollar_weight > 0:
            size = round( dollar_weight / best_ask, self.universe.loc[symbol, 'szDecimals'] )
            order_result = self.exchange.order(symbol, True, size, best_ask, {"limit": {"tif": "Gtc"}})
        else:
            size = round( abs( dollar_weight ) / best_bid, self.universe.loc[symbol, 'szDecimals'] )
            order_result = self.exchange.order(symbol, False, size, best_bid, {"limit": {"tif": "Gtc"}})
        
        # Query the order status by oid
        if order_result["status"] == "ok":
            return True
        else:
            print("[DEX] Problem with order.")
            print(order_result)
            return False