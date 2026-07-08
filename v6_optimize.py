# -*- coding: utf-8 -*-
"""参数优化扫描"""
import backtrader as bt
import pandas as pd
import itertools

# 加载数据
df = pd.read_csv("GOLD_M5_202103100105_202603092005.csv", sep='\t')
df.columns = [c.strip('<>') for c in df.columns]
df.index = pd.to_datetime(df['DATE'] + ' ' + df['TIME'])
df = df.rename(columns={'OPEN':'Open','HIGH':'High','LOW':'Low','CLOSE':'Close','TICKVOL':'Volume'})
df = df[['Open','High','Low','Close','Volume']].dropna()

class GridEA(bt.Strategy):
    params = (('sl', 2.0), ('trail_act', 3.0), ('trail_pb', 0.25), ('rsi_buy', 35))

    def __init__(self):
        self.ema = bt.ind.EMA(period=200)
        self.rsi = bt.ind.RSI(period=14)
        self.atr = bt.ind.ATR(period=14)
        self.grid_pos = []
        self.trade_log = []
        self.cooldown = 0
        self.trail_active = False
        self.trail_peak = 0

    def unrealized_pnl(self):
        p = self.data.close[0]
        return sum((p - e) * s * 100 for e, s, _ in self.grid_pos)

    def sl_price(self):
        return self.grid_pos[-1][0] - self.atr[0] * self.p.sl

    def close_all(self):
        self.trade_log.append(self.unrealized_pnl())
        self.grid_pos = []
        self.trail_active = False
        self.trail_peak = 0
        self.cooldown = 3

    def next(self):
        if len(self) < 200: return
        if self.cooldown > 0:
            self.cooldown -= 1
            return
        price = self.data.close[0]
        atr = self.atr[0]
        trend_up = price > self.ema[0]

        if not self.grid_pos:
            if trend_up and self.rsi[0] < self.p.rsi_buy:
                self.grid_pos.append((price, 0.01, 0))
            return

        pnl = self.unrealized_pnl()
        if price <= self.sl_price():
            self.close_all(); return

        if not self.trail_active and pnl >= atr * self.p.trail_act:
            self.trail_active = True
            self.trail_peak = pnl
        if self.trail_active:
            if pnl > self.trail_peak: self.trail_peak = pnl
            if pnl < self.trail_peak * (1 - self.p.trail_pb):
                self.close_all(); return

        if self.rsi[0] > 70 and pnl >= self.sl_price() and len(self.grid_pos) == 1:
            sl_loss = (self.grid_pos[0][0] - self.sl_price()) * 0.01 * 100
            if pnl >= sl_loss * 2:
                self.close_all(); return

        if len(self.grid_pos) < 3 and trend_up:
            last = self.grid_pos[-1][0]
            if price <= last - atr * 2.0:
                self.grid_pos.append((price, 0.01 * (1.5 ** len(self.grid_pos)), len(self.grid_pos)))

    def stop(self):
        wins = [t for t in self.trade_log if t > 0]
        losses = [t for t in self.trade_log if t <= 0]
        total = sum(self.trade_log)
        ecn = len(self.trade_log) * 0.45
        net = total - ecn
        wr = len(wins)/max(len(self.trade_log),1)*100
        pf = sum(wins)/abs(sum(losses)) if losses else 999
        rr = (sum(wins)/len(wins) if wins else 0) / (abs(sum(losses)/len(losses)) if losses else 1)
        print(f"SL={self.p.sl} TRAIL_ACT={self.p.trail_act} TRAIL_PB={self.p.trail_pb} RSI={self.p.rsi_buy} | "
              f"trades={len(self.trade_log)} WR={wr:.0f}% RR={rr:.2f} PF={pf:.2f} NET=${total:.0f} NET_ECN=${net:.0f}")

results = []
for sl, trail_act, trail_pb, rsi_buy in itertools.product(
    [1.5, 2.0, 2.5],
    [2.5, 3.0, 4.0],
    [0.25, 0.35],
    [30, 35, 40]
):
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(100000)
    cerebro.broker.setcommission(0.0003)
    cerebro.adddata(bt.feeds.PandasData(dataname=df))
    cerebro.addstrategy(GridEA, sl=sl, trail_act=trail_act, trail_pb=trail_pb, rsi_buy=rsi_buy)
    cerebro.run()
