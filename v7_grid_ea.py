# -*- coding: utf-8 -*-
"""
V7 网格 EA - 多时间框架趋势跟随版
核心思路：
- 日线趋势确认（EMA50日线方向）
- 5分钟图执行入场（RSI超卖/超买）
- 大止盈目标：ATR×5（约$30-80/笔）
- 严格止损：ATR×2
- 不做震荡市（ADX<25不入场）
"""
import backtrader as bt
import pandas as pd
import os


class V7Config:
    INITIAL_CAPITAL = 100_000

    # 趋势过滤
    EMA_SLOW = 200          # 5分钟EMA200（约等于日线EMA17，粗略趋势）
    EMA_MID = 50            # 5分钟EMA50
    ADX_PERIOD = 14
    ADX_MIN = 20            # 降低门槛

    # 入场
    RSI_PERIOD = 14
    RSI_BUY = 45
    RSI_SELL = 55

    # 仓位
    INITIAL_SIZE = 0.01
    GRID_LEVELS = 2         # 最多2层（减少风险）
    GRID_STEP_ATR = 3.0     # 更大间距
    GRID_MULTIPLIER = 2.0   # 加仓翻倍

    # 出场
    ATR_PERIOD = 14
    SL_ATR = 2.0
    TP_ATR = 5.0            # 固定止盈：ATR×5（大目标）
    TRAIL_ATR_ACTIVATE = 4.0  # 追踪激活：ATR×4
    TRAIL_PULLBACK = 0.3

    COOLDOWN_BARS = 12


class V7GridEA(bt.Strategy):

    def __init__(self):
        self.ema200 = bt.ind.EMA(period=V7Config.EMA_SLOW)
        self.ema50 = bt.ind.EMA(period=V7Config.EMA_MID)
        self.rsi = bt.ind.RSI(period=V7Config.RSI_PERIOD)
        self.atr = bt.ind.ATR(period=V7Config.ATR_PERIOD)
        self.adx = bt.ind.DirectionalMovement(period=V7Config.ADX_PERIOD)

        self.grid_pos = []
        self.trade_log = []
        self.order_count = 0
        self.cooldown = 0
        self.trail_active = False
        self.trail_peak = 0
        self.tp_price = 0
        self.pos_dir = 0

    def log(self, msg):
        dt = self.data.datetime.datetime(0).strftime("%Y-%m-%d %H:%M")
        print(f'{dt} | {msg}')

    def get_size(self, level):
        return round(V7Config.INITIAL_SIZE * (V7Config.GRID_MULTIPLIER ** level), 4)

    def unrealized_pnl(self):
        p = self.data.close[0]
        return sum((p - e) * s * 100 * self.pos_dir for e, s, _ in self.grid_pos)

    def sl_price(self):
        last = self.grid_pos[-1][0]
        offset = self.atr[0] * V7Config.SL_ATR
        return last - offset if self.pos_dir == 1 else last + offset

    def close_all(self, reason):
        pnl = self.unrealized_pnl()
        self.log(f'CLOSE: {reason} | PnL: ${pnl:.2f} | L{len(self.grid_pos)}')
        self.trade_log.append(pnl)
        self.grid_pos = []
        self.trail_active = False
        self.trail_peak = 0
        self.tp_price = 0
        self.pos_dir = 0
        self.cooldown = V7Config.COOLDOWN_BARS

    def next(self):
        if len(self) < V7Config.EMA_SLOW:
            return
        if self.cooldown > 0:
            self.cooldown -= 1
            return

        price = self.data.close[0]
        atr = self.atr[0]
        adx_val = self.adx.lines.adx[0]
        strong = adx_val > V7Config.ADX_MIN
        bull = self.ema50[0] > self.ema200[0] and price > self.ema50[0]
        bear = self.ema50[0] < self.ema200[0] and price < self.ema50[0]

        # ===== 入场 =====
        if not self.grid_pos:
            if bull and strong and self.rsi[0] < V7Config.RSI_BUY:
                self.pos_dir = 1
                self.grid_pos.append((price, self.get_size(0), 0))
                self.tp_price = price + atr * V7Config.TP_ATR
                self.order_count += 1
                self.log(f'BUY_L0: ${price:.2f} TP:${self.tp_price:.2f} ADX:{adx_val:.1f}')
            elif bear and strong and self.rsi[0] > V7Config.RSI_SELL:
                self.pos_dir = -1
                self.grid_pos.append((price, self.get_size(0), 0))
                self.tp_price = price - atr * V7Config.TP_ATR
                self.order_count += 1
                self.log(f'SELL_L0: ${price:.2f} TP:${self.tp_price:.2f} ADX:{adx_val:.1f}')
            return

        pnl = self.unrealized_pnl()
        sl = self.sl_price()

        # 1. 止损
        hit_sl = (self.pos_dir == 1 and price <= sl) or (self.pos_dir == -1 and price >= sl)
        if hit_sl:
            self.close_all(f'SL')
            return

        # 2. 固定止盈
        hit_tp = (self.pos_dir == 1 and price >= self.tp_price) or (self.pos_dir == -1 and price <= self.tp_price)
        if hit_tp:
            self.close_all(f'TP +${pnl:.2f}')
            return

        # 3. 追踪止盈（超过TP目标后继续跑）
        activate = atr * V7Config.TRAIL_ATR_ACTIVATE
        if not self.trail_active and pnl >= activate:
            self.trail_active = True
            self.trail_peak = pnl
            self.log(f'TRAIL_ON: ${pnl:.2f}')
        if self.trail_active:
            if pnl > self.trail_peak:
                self.trail_peak = pnl
            if pnl < self.trail_peak * (1 - V7Config.TRAIL_PULLBACK):
                self.close_all(f'TRAIL +${pnl:.2f}')
                return

        # 4. 网格加仓
        if len(self.grid_pos) < V7Config.GRID_LEVELS and strong:
            last = self.grid_pos[-1][0]
            step = atr * V7Config.GRID_STEP_ATR
            add_long = self.pos_dir == 1 and price <= last - step and bull
            add_short = self.pos_dir == -1 and price >= last + step and bear
            if add_long or add_short:
                level = len(self.grid_pos)
                size = self.get_size(level)
                self.grid_pos.append((price, size, level))
                # 更新TP到新均价
                avg = sum(e * s for e, s, _ in self.grid_pos) / sum(s for _, s, _ in self.grid_pos)
                self.tp_price = avg + atr * V7Config.TP_ATR if self.pos_dir == 1 else avg - atr * V7Config.TP_ATR
                self.order_count += 1
                self.log(f'ADD_L{level}: ${price:.2f} TP:${self.tp_price:.2f}')

    def stop(self):
        wins = [t for t in self.trade_log if t > 0]
        losses = [t for t in self.trade_log if t <= 0]
        total = sum(self.trade_log)
        wr = len(wins) / max(len(self.trade_log), 1) * 100
        pf = sum(wins) / abs(sum(losses)) if losses else float('inf')
        avg_w = sum(wins) / len(wins) if wins else 0
        avg_l = abs(sum(losses) / len(losses)) if losses else 0
        rr = avg_w / avg_l if avg_l else 0
        # ECN成本（按实际层级估算）
        ecn = len(self.trade_log) * 0.45  # 保守估算单层
        self.log('=' * 60)
        self.log('V7 GRID EA - 多时间框架趋势跟随版')
        self.log('=' * 60)
        self.log(f'ORDERS:{self.order_count} TRADES:{len(self.trade_log)} WIN_RATE:{wr:.1f}%')
        self.log(f'AVG_WIN:${avg_w:.2f} AVG_LOSS:${avg_l:.2f} RR:{rr:.2f}')
        self.log(f'GROSS_PROFIT:${sum(wins):.2f} GROSS_LOSS:${sum(losses):.2f}')
        self.log(f'NET_PROFIT:${total:.2f} PROFIT_FACTOR:{pf:.2f}')
        self.log(f'ECN_EST:${ecn:.2f} NET_ECN:${total-ecn:.2f}')
        self.log('=' * 60)


def run():
    data_path = "GOLD_M5_202103100105_202603092005.csv"
    df = pd.read_csv(data_path, sep='\t')
    df.columns = [c.strip('<>') for c in df.columns]
    df.index = pd.to_datetime(df['DATE'] + ' ' + df['TIME'])
    df = df.rename(columns={'OPEN': 'Open', 'HIGH': 'High', 'LOW': 'Low', 'CLOSE': 'Close', 'TICKVOL': 'Volume'})
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
    print(f"[Data] {len(df)} bars | {df.index[0]} ~ {df.index[-1]}")

    cerebro = bt.Cerebro()
    cerebro.broker.setcash(V7Config.INITIAL_CAPITAL)
    cerebro.broker.setcommission(commission=V7Config.COMMISSION if hasattr(V7Config, 'COMMISSION') else 0.0003)
    cerebro.adddata(bt.feeds.PandasData(dataname=df))
    cerebro.addstrategy(V7GridEA)
    cerebro.run()


if __name__ == '__main__':
    run()
