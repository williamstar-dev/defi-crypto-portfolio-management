from abc import ABC, abstractmethod

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