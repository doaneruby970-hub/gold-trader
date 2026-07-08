# -*- coding: utf-8 -*-
"""
V6 网格 EA - 长期稳定版
核心改进：
1. 只做多（黄金长期牛市，空单是主要亏损来源）
2. RSI14替代RSI5（减少噪音信号）
3. 追踪止盈：激活后只用峰值回撤，不被RSI提前踢出
4. 最小盈亏比保护：盈利未达止损×1.5不允许RSI平仓
5. 冷却期：平仓后等待，避免连续亏损
"""
import backtrader as bt
import pandas as pd
import os


class V6Config:
    INITIAL_CAPITAL = 100_000

    EMA_PERIOD = 200
    RSI_PERIOD = 14
    RSI_BUY = 40            # 最优参数
    ATR_PERIOD = 14

    GRID_STEP_ATR = 2.0
    GRID_LEVELS = 3
    INITIAL_SIZE = 0.01
    GRID_MULTIPLIER = 1.5

    SL_ATR = 2.5
    TRAIL_ATR_ACTIVATE = 3.0
    TRAIL_PULLBACK = 0.35

    MIN_RR = 2.0

    COOLDOWN_BARS = 3

    COMMISSION = 0.0003


class V6GridEA(bt.Strategy):

    def __init__(self):
        self.ema200 = bt.ind.EMA(period=V6Config.EMA_PERIOD)
        self.rsi = bt.ind.RSI(period=V6Config.RSI_PERIOD)
        self.atr = bt.ind.ATR(period=V6Config.ATR_PERIOD)

        self.grid_pos = []
        self.trade_log = []
        self.order_count = 0
        self.cooldown = 0
        self.trail_active = False
        self.trail_peak = 0

    def log(self, msg):
        dt = self.data.datetime.datetime(0).strftime("%Y-%m-%d %H:%M")
        print(f'{dt} | {msg}')

    def get_size(self, level):
        return round(V6Config.INITIAL_SIZE * (V6Config.GRID_MULTIPLIER ** level), 4)

    def unrealized_pnl(self):
        p = self.data.close[0]
        return sum((p - e) * s * 100 for e, s, _ in self.grid_pos)

    def sl_price(self):
        return self.grid_pos[-1][0] - self.atr[0] * V6Config.SL_ATR

    def min_profit_for_rsi_exit(self):
        """RSI平仓需要的最低盈利 = 止损金额 × MIN_RR"""
        sl_loss = sum((e - self.sl_price()) * s * 100 for e, s, _ in self.grid_pos)
        return sl_loss * V6Config.MIN_RR

    def close_all(self, reason):
        pnl = self.unrealized_pnl()
        self.log(f'CLOSE: {reason} | PnL: ${pnl:.2f} | L{len(self.grid_pos)}')
        self.trade_log.append(pnl)
        self.grid_pos = []
        self.trail_active = False
        self.trail_peak = 0
        self.cooldown = V6Config.COOLDOWN_BARS

    def next(self):
        if len(self) < V6Config.EMA_PERIOD:
            return
        if self.cooldown > 0:
            self.cooldown -= 1
            return

        price = self.data.close[0]
        atr = self.atr[0]
        trend_up = price > self.ema200[0]

        # ===== 入场（只做多）=====
        if not self.grid_pos:
            if trend_up and self.rsi[0] < V6Config.RSI_BUY:
                self.grid_pos.append((price, self.get_size(0), 0))
                self.order_count += 1
                self.log(f'BUY_L0: ${price:.2f} RSI:{self.rsi[0]:.1f} ATR:{atr:.2f}')
            return

        # ===== 持仓管理 =====
        pnl = self.unrealized_pnl()
        sl = self.sl_price()

        # 1. 止损
        if price <= sl:
            self.close_all(f'SL ${price:.2f}<${sl:.2f}')
            return

        # 2. 追踪止盈（加仓越多，激活门槛越高）
        activate = atr * V6Config.TRAIL_ATR_ACTIVATE * len(self.grid_pos)
        if not self.trail_active and pnl >= activate:
            self.trail_active = True
            self.trail_peak = pnl
            self.log(f'TRAIL_ON: ${pnl:.2f}')

        if self.trail_active:
            if pnl > self.trail_peak:
                self.trail_peak = pnl
            if pnl < self.trail_peak * (1 - V6Config.TRAIL_PULLBACK):
                self.close_all(f'TRAIL +${pnl:.2f} peak:${self.trail_peak:.2f}')
                return

        # 3. RSI超买平仓（需满足最低盈亏比）
        if self.rsi[0] > 70:
            min_profit = self.min_profit_for_rsi_exit()
            if pnl >= min_profit:
                self.close_all(f'RSI_EXIT RSI:{self.rsi[0]:.1f} +${pnl:.2f}')
                return

        # 4. 趋势破坏止损（价格跌破EMA200）
        if not trend_up and len(self.grid_pos) >= 2:
            self.close_all(f'TREND_BREAK ${price:.2f}<EMA${self.ema200[0]:.2f}')
            return

        # 5. 网格加仓（趋势仍向上）
        if len(self.grid_pos) < V6Config.GRID_LEVELS and trend_up:
            last_entry = self.grid_pos[-1][0]
            if price <= last_entry - atr * V6Config.GRID_STEP_ATR:
                level = len(self.grid_pos)
                size = self.get_size(level)
                self.grid_pos.append((price, size, level))
                self.order_count += 1
                self.log(f'ADD_L{level}: ${price:.2f} SL:${self.sl_price():.2f}')

    def stop(self):
        wins = [t for t in self.trade_log if t > 0]
        losses = [t for t in self.trade_log if t <= 0]
        total = sum(self.trade_log)
        win_rate = len(wins) / max(len(self.trade_log), 1) * 100
        pf = sum(wins) / abs(sum(losses)) if losses else float('inf')
        avg_w = sum(wins) / len(wins) if wins else 0
        avg_l = abs(sum(losses) / len(losses)) if losses else 0
        rr = avg_w / avg_l if avg_l else 0

        ecn_cost = len(self.trade_log) * ((0.2 * 0.015 * 100) + (5.0 * 0.015 * 2))

        self.log('=' * 60)
        self.log('V6 GRID EA - 长期稳定版')
        self.log('=' * 60)
        self.log(f'ORDERS:{self.order_count} TRADES:{len(self.trade_log)} WIN_RATE:{win_rate:.1f}%')
        self.log(f'AVG_WIN:${avg_w:.2f} AVG_LOSS:${avg_l:.2f} RR:{rr:.2f}')
        self.log(f'GROSS_PROFIT:${sum(wins):.2f} GROSS_LOSS:${sum(losses):.2f}')
        self.log(f'NET_PROFIT:${total:.2f} PROFIT_FACTOR:{pf:.2f}')
        self.log(f'ECN_COST:${ecn_cost:.2f} NET_ECN:${total - ecn_cost:.2f}')
        self.log('=' * 60)


def run():
    data_path = "GOLD_M5_202103100105_202603092005.csv"
    if not os.path.exists(data_path):
        print("[ERROR] Data not found!")
        return

    df = pd.read_csv(data_path, sep='\t')
    df.columns = [c.strip('<>') for c in df.columns]
    df.index = pd.to_datetime(df['DATE'] + ' ' + df['TIME'])
    df = df.rename(columns={'OPEN': 'Open', 'HIGH': 'High', 'LOW': 'Low', 'CLOSE': 'Close', 'TICKVOL': 'Volume'})
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()

    print(f"[Data] {len(df)} bars | {df.index[0]} ~ {df.index[-1]}")
    print(f"[Price] ${df['Close'].min():.2f} - ${df['Close'].max():.2f}")

    cerebro = bt.Cerebro()
    cerebro.broker.setcash(V6Config.INITIAL_CAPITAL)
    cerebro.broker.setcommission(commission=V6Config.COMMISSION)
    cerebro.adddata(bt.feeds.PandasData(dataname=df))
    cerebro.addstrategy(V6GridEA)

    print(f"[Start] ${cerebro.broker.getvalue():.2f}")
    cerebro.run()
    print(f"[End] ${cerebro.broker.getvalue():.2f}")


if __name__ == '__main__':
    run()
