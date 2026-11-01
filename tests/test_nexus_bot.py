import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import nexus_bot


ET = ZoneInfo("America/New_York")


def bar(hour, minute, open_, high, low, close):
    stamp = datetime(2026, 11, 2, hour, minute, tzinfo=ET).isoformat()
    return {"t": stamp, "o": open_, "h": high, "l": low, "c": close, "v": 10000}


class NexusBotTests(unittest.TestCase):
    def test_position_size_never_exceeds_one_dollar_risk_or_100_notional(self):
        qty, risk = nexus_bot.size_position(10.00, 9.50)
        self.assertEqual(qty, 2)
        self.assertLessEqual(risk, 1.00)
        self.assertLessEqual(qty * 10.00, 100.00)

    def test_position_is_skipped_when_one_share_exceeds_risk_budget(self):
        qty, risk = nexus_bot.size_position(50.00, 48.00)
        self.assertEqual(qty, 0)
        self.assertEqual(risk, 0.00)

    def test_position_is_skipped_when_stop_is_not_below_entry(self):
        qty, risk = nexus_bot.size_position(10.00, 10.10)
        self.assertEqual(qty, 0)
        self.assertEqual(risk, 0.00)

    def test_orb_signal_requires_three_opening_bars_and_confirmed_breakout(self):
        bars = [
            bar(9, 30, 10.00, 10.20, 9.90, 10.10),
            bar(9, 35, 10.10, 10.15, 9.80, 10.00),
            bar(9, 40, 10.00, 10.10, 9.85, 10.05),
            bar(9, 45, 10.05, 10.35, 10.02, 10.30),
        ]
        now = datetime(2026, 11, 2, 9, 55, tzinfo=ET)
        signal = nexus_bot.orb_signal(bars, now)
        self.assertIsNotNone(signal)
        self.assertGreater(signal["entry"], signal["or_high"])
        self.assertLess(signal["stop"], signal["entry"])
        self.assertAlmostEqual(
            signal["target"] - signal["entry"],
            2 * signal["risk_per_share"],
        )

    def test_orb_signal_ignores_unconfirmed_current_bar(self):
        bars = [
            bar(9, 30, 10.00, 10.20, 9.90, 10.10),
            bar(9, 35, 10.10, 10.15, 9.80, 10.00),
            bar(9, 40, 10.00, 10.10, 9.85, 10.05),
            bar(9, 45, 10.05, 10.35, 10.02, 10.30),
        ]
        now = datetime(2026, 11, 2, 9, 49, tzinfo=ET)
        self.assertIsNone(nexus_bot.orb_signal(bars, now))


if __name__ == "__main__":
    unittest.main()
