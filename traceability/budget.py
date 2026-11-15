"""Estimate API spend from token usage and stop a run at a dollar cap.

The estimate is a guard, not a bill. Cache writes are counted at twice the input rate so the
estimate errs high. Check the provider's invoice for the real figure.
"""

# US dollars per million tokens: input, output, cache read. Recorded 2026-11-03.
PRICES = {"claude-opus-5-5": (4.00, 20.00, 0.20)}


class Budget:
    def __init__(self, model, max_usd=None, prices=None):
        rates = prices or PRICES.get(model)
        if max_usd is not None and rates is None:
            raise ValueError(f"No price is recorded for {model}. Pass --usd-per-mtok INPUT OUTPUT CACHE_READ with --max-usd")
        if max_usd is not None and max_usd <= 0:
            raise ValueError("--max-usd must be positive")
        self.rates, self.max_usd, self.spent = rates, max_usd, 0.0

    def add(self, usage):
        if self.rates is None:
            return
        count = lambda key: usage.get(key) if isinstance(usage.get(key), int) else 0
        into, out, read = self.rates
        self.spent += (count("input_tokens") * into + count("cache_creation_input_tokens") * into * 2
                       + count("cache_read_input_tokens") * read + count("output_tokens") * out) / 1_000_000

    def exhausted(self):
        return self.max_usd is not None and self.spent >= self.max_usd

    def report(self):
        return {"estimated_usd": round(self.spent, 4) if self.rates else None, "max_usd": self.max_usd}


def add_arguments(parser):
    parser.add_argument("--max-usd", type=float, help="Stop before the next component once estimated spend reaches this amount")
    parser.add_argument("--usd-per-mtok", type=float, nargs=3, metavar=("INPUT", "OUTPUT", "CACHE_READ"),
                        help="Prices per million tokens, for a model with no recorded price")
