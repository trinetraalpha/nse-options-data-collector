import os
import sys
import unittest
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from collectors.oi_collector import _extract_contract_ohlc, save_chain_snapshot
from utils.upstox_data import _build_option_side


class TestOptionsDataCollector(unittest.TestCase):
    def setUp(self):
        self.expected_columns = [
            "Timestamp", "Symbol", "Open", "High", "Low", "Close",
            "Volume", "Open_Interest", "Expiry_Date", "Strike_Price",
            "Option_Type", "Bid_Price", "Ask_Price"
        ]

    def test_sample_csv_columns(self):
        csv_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "examples", "sample_data", "option_chain_sample.csv"
        )
        self.assertTrue(os.path.isfile(csv_path), "Sample CSV file must exist")
        df = pd.read_csv(csv_path)

        for col in self.expected_columns:
            self.assertIn(col, df.columns, f"Missing required column: {col}")

        # Check option types
        self.assertTrue(set(df["Option_Type"].unique()).issubset({"CE", "PE"}))
        self.assertGreater(len(df), 0)

    def test_extract_contract_ohlc_from_market_data(self):
        # 1. When ohlc is present in market_data
        opt_data = {
            "market_data": {
                "ltp": 150.0,
                "close_price": 140.0,
                "ohlc": {
                    "open": 145.0,
                    "high": 155.0,
                    "low": 142.0,
                    "close": 150.0
                }
            }
        }
        o, h, l, c = _extract_contract_ohlc(opt_data, "KEY1", {})
        self.assertEqual(o, 145.0)
        self.assertEqual(h, 155.0)
        self.assertEqual(l, 142.0)
        self.assertEqual(c, 150.0)

    def test_extract_contract_ohlc_from_cache(self):
        # 2. When ohlc is in cache
        opt_data = {
            "market_data": {
                "ltp": 120.0,
                "close_price": 115.0
            }
        }
        cache = {
            "KEY2": {"open": 118.0, "high": 125.0, "low": 116.0, "close": 120.0}
        }
        o, h, l, c = _extract_contract_ohlc(opt_data, "KEY2", cache)
        self.assertEqual(o, 118.0)
        self.assertEqual(h, 125.0)
        self.assertEqual(l, 116.0)
        self.assertEqual(c, 120.0)

    def test_extract_contract_ohlc_fallback(self):
        # 3. Fallback to ltp/close_price when no ohlc is available
        opt_data = {
            "market_data": {
                "ltp": 200.0,
                "close_price": 195.0
            }
        }
        o, h, l, c = _extract_contract_ohlc(opt_data, "KEY3", {})
        self.assertEqual(o, 200.0)
        self.assertEqual(h, 200.0)
        self.assertEqual(l, 200.0)
        self.assertEqual(c, 200.0)

    def test_build_option_side_includes_ohlc(self):
        md = {
            "volume": 1000,
            "ohlc": {"open": 10.0, "high": 15.0, "low": 8.0, "close": 12.0}
        }
        side = _build_option_side(12.0, 11.8, 12.2, 5000, md, {"iv": 14.5}, 0.5)
        self.assertIn("open", side)
        self.assertIn("high", side)
        self.assertIn("low", side)
        self.assertIn("close", side)
        self.assertEqual(side["open"], 10.0)
        self.assertEqual(side["high"], 15.0)
        self.assertEqual(side["low"], 8.0)
        self.assertEqual(side["close"], 12.0)

    def test_save_chain_snapshot(self):
        data = [{
            "Timestamp": "2026-10-16T12:00:00+05:30",
            "Symbol": "NIFTY",
            "Open": 100.0,
            "High": 110.0,
            "Low": 95.0,
            "Close": 105.0,
            "Volume": 50000,
            "Open_Interest": 120000,
            "Expiry_Date": "2026-10-22",
            "Strike_Price": 25000,
            "Option_Type": "CE",
            "Bid_Price": 104.5,
            "Ask_Price": 105.5
        }]
        df = pd.DataFrame(data)
        save_chain_snapshot(df, save_csv=True)

        from datetime import date
        today_str = date.today().isoformat()
        chain_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "option_chain"
        )
        parquet_file = os.path.join(chain_dir, f"chain_{today_str}.parquet")
        csv_file = os.path.join(chain_dir, f"chain_{today_str}.csv")

        self.assertTrue(os.path.isfile(parquet_file))
        self.assertTrue(os.path.isfile(csv_file))

        read_df = pd.read_parquet(parquet_file)
        for col in self.expected_columns:
            self.assertIn(col, read_df.columns)


if __name__ == "__main__":
    unittest.main()
