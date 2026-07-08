# -*- coding: utf-8 -*-
import backtrader as bt
import pandas as pd
import os


class V8Config:
    INITIAL_CAPITAL = 100_000

    EMA_FAST    = 50
    EMA_SLOW    = 200
    ATR_PERIOD  = 14
    ADX_PERIOD  = 14

    BREAKOUT_N  = 288         # 24小时高点突破
    ADX_MIN     = 25

    INITIAL_SIZE = 0.1        # 1%风险/笔（0.01手时平均亏损$11，0.1手≈$110≈账户0.11%）

    SL_ATR      = 3.0
    TRAIL_ATR   = 2.0         # 追踪止损距离

    COMMISSION  = 0.0003


class V8GridEA(bt.Strategy):

    def __init__(self):
        self.ema_fast = bt.ind.EMA(period=V8Config.EMA_FAST)
        self.ema_slow = bt.ind.EMA(period=V8Config.EMA_SLOW)
        self.atr      = bt.ind.ATR(period=V8Config.ATR_PERIOD)
        self.adx      = bt.ind.DirectionalMovementIndex(period=V8Config.ADX_PERIOD)
        self.highest  = bt.ind.Highest(self.data.high, period=V8Config.BREAKOUT_N)

        self.entry      = None   # entry price
        self.trail_stop = None
        self.trade_log  = []
        self.order_count= 0

    def log(self, msg):
        dt = self.data.datetime.datetime(0).strftime("%Y-%m-%d %H:%M")
        print(f'{dt} | {msg}')

    def pnl(self):
        return (self.data.close[0] - self.entry) * V8Config.INITIAL_SIZE * 100

    def close_pos(self, reason):
        p = self.pnl()
        self.log(f'CLOSE: {reason} | PnL: ${p:.2f}')
        self.trade_log.append(p)
        self.entry      = None
        self.trail_stop = None

    def next(self):
        if len(self) < V8Config.BREAKOUT_N + V8Config.EMA_SLOW:
            return

        price     = self.data.close[0]
        atr       = self.atr[0]
        bull_trend= self.ema_fast[0] > self.ema_slow[0]

        if self.entry is None:
            if bull_trend and self.adx.adx[0] > V8Config.ADX_MIN and price > self.highest[-1]:
                self.entry      = price
                self.trail_stop = price - atr * V8Config.SL_ATR
                self.order_count += 1
                self.log(f'BUY: ${price:.2f} ADX:{self.adx.adx[0]:.1f} SL:${self.trail_stop:.2f}')
            return

        # 移动止损：始终跟随当前价格，距离为ATR×TRAIL_ATR
        self.trail_stop = price - atr * V8Config.TRAIL_ATR

        if price <= self.trail_stop:
            self.close_pos(f'TRAIL_SL ${price:.2f}<${self.trail_stop:.2f}')
            return

        if not bull_trend:
            self.close_pos(f'TREND_END')

    def stop(self):
        wins   = [t for t in self.trade_log if t > 0]
        losses = [t for t in self.trade_log if t <= 0]
        total  = sum(self.trade_log)
        win_rate = len(wins) / max(len(self.trade_log), 1) * 100
        pf     = sum(wins) / abs(sum(losses)) if losses else float('inf')
        avg_w  = sum(wins) / len(wins) if wins else 0
        avg_l  = abs(sum(losses) / len(losses)) if losses else 0
        ecn    = len(self.trade_log) * ((0.2 * 0.015 * 100) + (5.0 * 0.015 * 2))

        self.log('=' * 60)
        self.log('V8 突破趋势跟踪 EA  BN=288 ADX=25 TRAIL=2.0')
        self.log('=' * 60)
        self.log(f'ORDERS:{self.order_count} TRADES:{len(self.trade_log)} WIN_RATE:{win_rate:.1f}%')
        self.log(f'AVG_WIN:${avg_w:.2f} AVG_LOSS:${avg_l:.2f} RR:{avg_w/avg_l if avg_l else 0:.2f}')
        self.log(f'GROSS_PROFIT:${sum(wins):.2f} GROSS_LOSS:${sum(losses):.2f}')
        self.log(f'NET_PROFIT:${total:.2f} PROFIT_FACTOR:{pf:.2f}')
        self.log(f'ECN_COST:${ecn:.2f} NET_ECN:${total - ecn:.2f}')
        self.log('=' * 60)


def run():
    data_path = "GOLD_M5_202103100105_202603092005.csv"
    if not os.path.exists(data_path):
        print("[ERROR] Data not found!")
        return

    df = pd.read_csv(data_path, sep='\t')
    df.columns = [c.strip('<>') for c in df.columns]
    df.index = pd.to_datetime(df['DATE'] + ' ' + df['TIME'])
    df = df.rename(columns={'OPEN':'Open','HIGH':'High','LOW':'Low','CLOSE':'Close','TICKVOL':'Volume'})
    df = df[['Open','High','Low','Close','Volume']].dropna()

    print(f"[Data] {len(df)} bars | {df.index[0]} ~ {df.index[-1]}")

    cerebro = bt.Cerebro()
    cerebro.broker.setcash(V8Config.INITIAL_CAPITAL)
    cerebro.broker.setcommission(commission=V8Config.COMMISSION)
    cerebro.adddata(bt.feeds.PandasData(dataname=df))
    cerebro.addstrategy(V8GridEA)

    print(f"[Start] ${cerebro.broker.getvalue():.2f}")
    cerebro.run()
    print(f"[End] ${cerebro.broker.getvalue():.2f}")


if __name__ == '__main__':
    run()
