# Gold Trader - Gold Quantitative Trading Backtest System

A backtrader-based automated trading strategy backtesting and parameter optimization toolkit for gold (XAUUSD). Covers four strategy iterations from V5 to V8, spanning grid trading, trend following, breakout trading, and more.

## Features

- **V5 Grid EA (Ultimate Evolution Edition)**: Supports long/short bidirectional ATR dynamic grid trading, stop-loss anchored to the last position rather than average price, RSI intelligent tiered liquidation, dynamic trailing take-profit.
- **V6 Grid EA (Long-Term Stability Edition)**: Long-only (based on gold's secular bull thesis), RSI(14) replacing RSI(5) to reduce noise, minimum risk/reward ratio protection, cooldown mechanism to avoid consecutive losses.
- **V7 Trend-Following EA (Multi-Timeframe Edition)**: EMA50/EMA200 dual moving-average trend direction confirmation, ADX filtering for ranging markets, fixed take-profit target ATRx5, supports long/short bidirectional.
- **V8 Breakout-Tracking EA**: 24-hour high breakout entry strategy, combined with EMA trend filter and ADX strength confirmation, pure trailing stop exit.
- **Parameter Optimization Scripts**: V6/V7/V8 each come with brute-force parameter scanning scripts, grid-searching for optimal parameter combinations.
- **ECN Cost Simulation**: All strategies include built-in ECN spread + commission cost estimation.
- **Complete Statistical Output**: Win rate, profit/loss ratio, Profit Factor, average profit/loss, net return, and other backtest metrics.

## Requirements

- Python 3.7+
- backtrader
- pandas

## Installation

```bash
git clone https://github.com/doaneruby970-hub/gold-trader.git
cd gold-trader
pip install backtrader pandas
```

## Configuration

No `.env` file or environment variables required. All strategy parameters are defined as hardcoded constant classes (`V5Config` / `V6Config` / `V7Config` / `V8Config`) at the top of each strategy file and can be modified before running.

A data file is required: **GOLD_M5_202103100105_202603092005.csv** (gold 5-minute candlestick data, tab-separated, with DATE, TIME, OPEN, HIGH, LOW, CLOSE, TICKVOL columns), placed in the project root directory.

## Usage

Backtest a single strategy:

```bash
# V5 Grid EA (long/short bidirectional, RSI tiered liquidation)
python v5_grid_ea.py

# V6 Grid EA (long-only, long-term stability)
python v6_grid_ea.py

# V7 Trend-Following EA (multi-timeframe, ADX filtering)
python v7_grid_ea.py

# V8 Breakout-Tracking EA (24h high breakout + trailing stop)
python v8_grid_ea.py
```

Parameter optimization (brute-force scan, outputs all combination results):

```bash
python v6_optimize.py   # V6 parameter scan: SL / Trail activation / Trail retracement / RSI buy threshold
python v7_optimize.py   # V7 parameter scan: ADX threshold / RSI buy / TP target / SL multiplier
python v8_optimize.py   # V8 parameter scan: breakout period / ADX threshold / Trail distance
```

## Strategy Comparison

| Version | Strategy Type | Direction | Entry Signal | Exit Method | Grid Layers |
|------|---------|------|---------|---------|---------|
| V5 | Grid Trading | Long+Short | EMA200 trend + RSI(5) overbought/oversold | Trailing TP / Dynamic SL / RSI tiered liquidation | 4 |
| V6 | Grid Trading | Long-only | EMA200 trend + RSI(14) oversold | Trailing TP (retracement-only) / Fixed SL / R:R protection | 3 |
| V7 | Trend Following | Long+Short | EMA50/200 + ADX + RSI(14) | Fixed TP (ATRx5) / SL / Trailing TP | 2 |
| V8 | Breakout Trading | Long-only | 24h high breakout + EMA50/200 + ADX | ATR trailing stop / Trend breakdown | 1 (no grid) |

## Notes

1. **Backtesting only**: This project is a strategy research and backtesting tool. It includes no live trading interfaces and connects to no exchanges or brokers.
2. **Data dependency**: All scripts depend on a local CSV data file. A missing file will cause runtime failure.
3. **Install dependencies**: `pip install -r requirements.txt`
4. **Hardcoded strategy parameters**: All parameters are written directly in code as constants and class attributes. No CLI parameter interface is provided.
5. **V8 naming inaccuracy**: `v8_grid_ea.py` actually implements a breakout trend-following strategy, not a grid EA, but retains the old naming convention.
6. **Backtest assumptions**: Initial capital $100,000, commission 0.03%, ECN cost estimated at 0.2 spread + $5/lot commission.
7. **No risk control layer**: The strategies do not implement max drawdown limits, daily loss caps, or other risk management logic. Live trading would require supplementary implementation.
