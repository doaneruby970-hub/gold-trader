# -*- coding: utf-8 -*-
import backtrader as bt
import pandas as pd
import os

DATA_PATH = "GOLD_M5_202103100105_202603092005.csv"
ECN_PER_TRADE = (0.2 * 0.015 * 100) + (5.0 * 0.015 * 2)  # ~$0.45


class EA(bt.Strategy):
    params = (('breakout_n', 288), ('adx_min', 25), ('trail_atr', 2.5), ('sl_atr', 3.0))

    def __init__(self):
        self.ema_fast = bt.ind.EMA(period=50)
        self.ema_slow = bt.ind.EMA(period=200)
        self.atr      = bt.ind.ATR(period=14)
        self.adx      = bt.ind.DirectionalMovementIndex(period=14)
        self.highest  = bt.ind.Highest(self.data.high, period=self.p.breakout_n)
        self.pos = None
        self.log = []

    def pnl(self):
        return (self.data.close[0] - self.pos[0]) * 0.01 * 100

    def close(self, r):
        self.log.append(self.pnl())
        self.pos = None

    def next(self):
        if len(self) < self.p.breakout_n + 200:
            return
        price = self.data.close[0]
        bull  = self.ema_fast[0] > self.ema_slow[0]

        if not self.pos:
            if bull and self.adx.adx[0] > self.p.adx_min and price > self.highest[-1]:
                self.pos = [price, self.atr[0] * self.p.sl_atr]
            return

        new_trail = price - self.atr[0] * self.p.trail_atr
        if new_trail > self.pos[0] - self.pos[1]:
            self.pos[1] = price - new_trail  # 更新追踪距离
        if price <= self.pos[0] - self.pos[1]:
            self.close('SL')
            return
        if not bull:
            self.close('TREND')

    def stop(self):
        wins   = [t for t in self.log if t > 0]
        losses = [t for t in self.log if t <= 0]
        total  = sum(self.log)
        ecn    = len(self.log) * ECN_PER_TRADE
        pf     = sum(wins) / abs(sum(losses)) if losses else 0
        print(f"BN={self.p.breakout_n:4d} ADX={self.p.adx_min:2d} "
              f"TRAIL={self.p.trail_atr} SL={self.p.sl_atr} | "
              f"T={len(self.log):4d} WR={len(wins)/max(len(self.log),1)*100:4.1f}% "
              f"PF={pf:.2f} NET=${total:.0f} ECN=${ecn:.0f} NET_ECN=${total-ecn:.0f}")


def main():
    df = pd.read_csv(DATA_PATH, sep='\t')
    df.columns = [c.strip('<>') for c in df.columns]
    df.index = pd.to_datetime(df['DATE'] + ' ' + df['TIME'])
    df = df.rename(columns={'OPEN':'Open','HIGH':'High','LOW':'Low','CLOSE':'Close','TICKVOL':'Volume'})
    df = df[['Open','High','Low','Close','Volume']].dropna()

    for bn in [288, 576, 864, 1152]:
        for adx in [20, 25, 30]:
            for trail in [2.0, 2.5, 3.0]:
                cerebro = bt.Cerebro()
                cerebro.broker.setcash(100_000)
                cerebro.adddata(bt.feeds.PandasData(dataname=df))
                cerebro.addstrategy(EA, breakout_n=bn, adx_min=adx, trail_atr=trail)
                cerebro.run()


if __name__ == '__main__':
    main()
