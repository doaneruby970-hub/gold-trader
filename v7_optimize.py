# -*- coding: utf-8 -*-
"""V7参数扫描 - 找最优ADX/RSI组合"""
import backtrader as bt
import pandas as pd
import itertools

df = pd.read_csv("GOLD_M5_202103100105_202603092005.csv", sep='\t')
df.columns = [c.strip('<>') for c in df.columns]
df.index = pd.to_datetime(df['DATE'] + ' ' + df['TIME'])
df = df.rename(columns={'OPEN':'Open','HIGH':'High','LOW':'Low','CLOSE':'Close','TICKVOL':'Volume'})
df = df[['Open','High','Low','Close','Volume']].dropna()

class EA(bt.Strategy):
    params = (('adx_min',20),('rsi_buy',40),('tp_atr',5.0),('sl_atr',2.0))

    def __init__(self):
        self.ema200 = bt.ind.EMA(period=200)
        self.ema50 = bt.ind.EMA(period=50)
        self.rsi = bt.ind.RSI(period=14)
        self.atr = bt.ind.ATR(period=14)
        self.adx = bt.ind.DirectionalMovement(period=14)
        self.grid_pos = []
        self.trade_log = []
        self.pos_dir = 0
        self.tp_price = 0
        self.cooldown = 0
        self.trail_active = False
        self.trail_peak = 0

    def unrealized_pnl(self):
        p = self.data.close[0]
        return sum((p-e)*s*100*self.pos_dir for e,s,_ in self.grid_pos)

    def sl_price(self):
        last = self.grid_pos[-1][0]
        off = self.atr[0] * self.p.sl_atr
        return last - off if self.pos_dir == 1 else last + off

    def close_all(self, r):
        self.trade_log.append(self.unrealized_pnl())
        self.grid_pos = []; self.pos_dir = 0
        self.trail_active = False; self.trail_peak = 0
        self.cooldown = 6

    def next(self):
        if len(self) < 200: return
        if self.cooldown > 0: self.cooldown -= 1; return
        price = self.data.close[0]; atr = self.atr[0]
        strong = self.adx.lines.adx[0] > self.p.adx_min
        bull = self.ema50[0] > self.ema200[0] and price > self.ema50[0]
        bear = self.ema50[0] < self.ema200[0] and price < self.ema50[0]

        if not self.grid_pos:
            if bull and strong and self.rsi[0] < self.p.rsi_buy:
                self.pos_dir = 1; self.grid_pos.append((price,0.01,0))
                self.tp_price = price + atr * self.p.tp_atr
            elif bear and strong and self.rsi[0] > (100-self.p.rsi_buy):
                self.pos_dir = -1; self.grid_pos.append((price,0.01,0))
                self.tp_price = price - atr * self.p.tp_atr
            return

        pnl = self.unrealized_pnl(); sl = self.sl_price()
        if (self.pos_dir==1 and price<=sl) or (self.pos_dir==-1 and price>=sl):
            self.close_all('SL'); return
        if (self.pos_dir==1 and price>=self.tp_price) or (self.pos_dir==-1 and price<=self.tp_price):
            self.close_all('TP'); return
        act = atr * 4.0
        if not self.trail_active and pnl >= act:
            self.trail_active = True; self.trail_peak = pnl
        if self.trail_active:
            if pnl > self.trail_peak: self.trail_peak = pnl
            if pnl < self.trail_peak * 0.65: self.close_all('TRAIL'); return

    def stop(self):
        wins = [t for t in self.trade_log if t > 0]
        losses = [t for t in self.trade_log if t <= 0]
        total = sum(self.trade_log)
        ecn = len(self.trade_log) * 0.45
        wr = len(wins)/max(len(self.trade_log),1)*100
        pf = sum(wins)/abs(sum(losses)) if losses else 999
        rr = (sum(wins)/len(wins) if wins else 0)/(abs(sum(losses)/len(losses)) if losses else 1)
        print(f"ADX={self.p.adx_min} RSI_BUY={self.p.rsi_buy} TP={self.p.tp_atr} SL={self.p.sl_atr} | "
              f"n={len(self.trade_log)} WR={wr:.0f}% RR={rr:.2f} PF={pf:.2f} NET=${total:.0f} ECN=${total-ecn:.0f}")

for adx, rsi_buy, tp, sl in itertools.product(
    [20, 25, 30],
    [35, 40, 45],
    [4.0, 5.0, 6.0],
    [1.5, 2.0]
):
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(100000)
    cerebro.broker.setcommission(0.0003)
    cerebro.adddata(bt.feeds.PandasData(dataname=df))
    cerebro.addstrategy(EA, adx_min=adx, rsi_buy=rsi_buy, tp_atr=tp, sl_atr=sl)
    cerebro.run()
