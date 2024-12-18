from abc import ABC, abstractmethod

# from abc import ABC, abstractmethod
from numerapi import CryptoAPI
import pandas as pd
import numpy as np
from datetime import datetime, timezone, date, timedelta

import json
import os
import requests
from websocket import create_connection


# Generic Oracle Interface
class OracleInterface(ABC):
    @abstractmethod
    def fetch_portfolio_weights(self, timestamp: str) -> dict:
        """Fetch portfolio weights for the given timestamp."""
        pass

    @abstractmethod
    def validate_weights(self, weights: dict) -> bool:
        """Validate the portfolio weights."""
        pass

# Mock Oracle and Dex Classes
# Oracle Implementation
class NumeraiTBNOracle(OracleInterface):
    def __init__(self, tb=3):
        self.api = CryptoAPI()
        self.api.download_dataset(
        	"crypto/v1.0/historical_meta_models.csv",
        	"historical_meta_models.csv"
        )
        
        #load historical MM
        self.mm = pd.read_csv('historical_meta_models.csv')
        self.mm['date'] = pd.to_datetime( self.mm['date'] )

        self.tb = tb
        
    import numpy as np

    def get_risk_for_date(self, timestamp, tradable_universe: list):
        x = self.mm.loc[
            ( self.mm['date'] == pd.to_datetime( timestamp.date() ) ) & ( self.mm['symbol'].isin( tradable_universe ) ), ['symbol', 'meta_model']].set_index('symbol')
        return x.to_dict()

    def fetch_portfolio_weights(self, timestamp, tradable_universe: list, lags: int) -> dict:
        print(f"[Oracle] Computing portfolio weights for timestamp {timestamp}.")
        portfolio_dates = sorted( self.mm['date'].unique()[ self.mm['date'].dt.date.unique() <= timestamp.date() ] )[-lags:]
        print(f"[Oracle] Portfolio Date: {portfolio_dates[-1]}")
        x = self.mm.loc[ self.mm['date'].isin( portfolio_dates ), ['symbol','meta_model'] ]

        #only keep tradable universe
        x = x.loc[ x['symbol'].isin( tradable_universe ) ]
        
        # Group by symbol and sum meta_model across dates
        x = x.groupby('symbol', as_index=False).agg({'meta_model': 'sum'})
        
        # Sort by meta_model and drop duplicates to keep unique symbols
        top_symbols = (
            x.sort_values(by='meta_model', ascending=False)
            .head(self.tb)
        )
        bottom_symbols = (
            x.sort_values(by='meta_model', ascending=True)
            .head(self.tb)
        )
        
        # Initialize weights
        x['w'] = 0
        
        # Assign weights: 1 for top symbols, -1 for bottom symbols
        x.loc[top_symbols.index, 'w'] = 1
        x.loc[bottom_symbols.index, 'w'] = -1
        x['w'] = x['w'] / x['w'].abs().sum()
        
        weights = dict(zip(x["symbol"], x["w"]))
        return weights

    def validate_weights(self, weights: dict) -> bool:
        # Ensure weights sum to 1
        valid = (np.abs( np.array( [ weights[k] for k in weights.keys() ] ) ).sum() - 1.0) < 1e-6
        if not valid:
            print("[Oracle] Weights validation failed.")
        return valid

