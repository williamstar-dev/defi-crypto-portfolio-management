from abc import ABC, abstractmethod

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