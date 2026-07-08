# -*- coding: utf-8 -*-
"""
V5 网格 EA - 终极进化版
修复V4三大暗伤：
1. 删除固定止盈，追踪止盈真正生效
2. 止损锚定最后一单而非均价
3. RSI智能分级平仓
4. 动态追踪激活 (ATR×1.5)
"""
import backtrader as bt
import pandas as pd
import os

class V5Config:
    SYMBOL = "GC=F"
    INITIAL_CAPITAL = 100000
    
    # 网格参数
    GRID_STEP_ATR = 1.5       # 网格间距 = ATR×1.5
    GRID_LEVELS = 4            
    INITIAL_SIZE = 0.01      
    GRID_MULTIPLIER = 1.4      # 仓位乘数
    
    # 追踪止盈 (V5修复：不再用固定$8)
    TRAIL_ATR_MULT = 1.5       # 激活：盈利 ≥ ATR×1.5
    TRAIL_PULLBACK_ATR = 0.5   # 回撤：ATR×0.5 平仓
    
    # 止损 (V5修复：锚定最后一单)
    SL_ATR_MULT = 2.0          # 止损 = 最后入场价 ± ATR×2
    
    # 趋势过滤
    EMA_PERIOD = 200           
    RSI_PERIOD = 5
    RSI_CLOSE_LONG = 68        # 多单超买平仓
    RSI_CLOSE_SHORT = 32       # 空单超卖平仓
    
    # RSI分级平仓阈值
    RSI_PROFIT_THRESHOLD = 15   # 盈利>$15时，RSI平仓需更严格
    
    ATR_PERIOD = 14
    COMMISSION = 0.0003

class V5GridEA(bt.Strategy):
    params = (
        ('grid_step_atr', V5Config.GRID_STEP_ATR),
        ('grid_levels', V5Config.GRID_LEVELS),
        ('init_size', V5Config.INITIAL_SIZE),
        ('grid_mult', V5Config.GRID_MULTIPLIER),
    )

    def __init__(self):
        # 指标
        self.ema200 = bt.ind.EMA(self.data.close, period=V5Config.EMA_PERIOD)
        self.rsi = bt.ind.RSI(self.data.close, period=V5Config.RSI_PERIOD)
        self.atr = bt.ind.ATR(self.data, period=V5Config.ATR_PERIOD)
        
        # 持仓
        self.grid_positions = []
        self.total_size = 0
        self.avg_price = 0
        self.position_type = 0  # 1=多，-1=空
        
        # 交易记录
        self.trade_log = []
        self.order_count = 0
        
        # 追踪止盈 (V5修复)
        self.trail_activated = False
        self.trail_stop = 0
        self.trail_peak = 0
        self.trail_activate_level = 0  # 激活价格

    def log(self, msg):
        dt = self.data.datetime.datetime(0).strftime("%Y-%m-%d %H:%M:%S")
        print(f'{dt} | {msg}')

    def get_grid_step(self):
        return self.atr[0] * V5Config.GRID_STEP_ATR

    def get_position_size(self, level):
        return self.p.init_size * (self.p.grid_mult ** level)

    def calc_unrealized_pnl(self):
        if not self.grid_positions:
            return 0
        current_price = self.data.close[0]
        pnl = sum((current_price - entry) * size * 100 
                  for entry, size, _ in self.grid_positions)
        return pnl

    def get_trail_activate_pnl(self):
        """V5修复：动态追踪激活"""
        return self.atr[0] * V5Config.TRAIL_ATR_MULT

    def get_trail_pullback(self):
        """V5修复：动态回撤"""
        return self.atr[0] * V5Config.TRAIL_PULLBACK_ATR

    def get_last_entry_price(self):
        """V5修复：获取最后一单入场价"""
        if self.grid_positions:
            return self.grid_positions[-1][0]
        return 0

    def get_sl_price(self):
        """V5修复：锚定最后一单的止损"""
        last_entry = self.get_last_entry_price()
        atr_sl = self.atr[0] * V5Config.SL_ATR_MULT
        if self.position_type == 1:  # 多单
            return last_entry - atr_sl
        else:  # 空单
            return last_entry + atr_sl

    def calc_sl_pnl(self):
        sl_price = self.get_sl_price()
        pnl = sum((sl_price - entry) * size * 100 
                  for entry, size, _ in self.grid_positions)
        return abs(pnl)

    def close_all(self, reason=""):
        if not self.grid_positions:
            return
        pnl = self.calc_unrealized_pnl()
        self.log(f'CLOSE: {reason} | PnL: ${pnl:.2f} | Levels: {len(self.grid_positions)}')
        self.trade_log.append(pnl)
        self.grid_positions = []
        self.total_size = 0
        self.avg_price = 0
        self.position_type = 0
        self.trail_activated = False
        self.trail_stop = 0
        self.trail_peak = 0
        self.trail_activate_level = 0

    def next(self):
        if len(self) < V5Config.EMA_PERIOD:
            return
            
        current_price = self.data.close[0]
        grid_step = self.get_grid_step()
        
        # 判断趋势
        trend_up = current_price > self.ema200[0]
        
        # ==================== 入场 ====================
        if not self.grid_positions:
            # 做多: 上涨趋势 + RSI超卖
            if trend_up and self.rsi < 32:
                size = self.get_position_size(0)
                self.grid_positions.append((current_price, size, 0))
                self.total_size = size
                self.avg_price = current_price
                self.position_type = 1
                self.order_count += 1
                self.log(f'BUY_L0: ${current_price:.2f} | Size: {size:.4f} | RSI: {self.rsi[0]:.1f} | ATR: {self.atr[0]:.2f}')
            
            # 做空: 下跌趋势 + RSI超买
            elif not trend_up and self.rsi > 68:
                size = self.get_position_size(0)
                self.grid_positions.append((current_price, size, 0))
                self.total_size = size
                self.avg_price = current_price
                self.position_type = -1
                self.order_count += 1
                self.log(f'SELL_L0: ${current_price:.2f} | Size: {size:.4f} | RSI: {self.rsi[0]:.1f} | ATR: {self.atr[0]:.2f}')
        
        # ==================== 持仓管理 ====================
        else:
            unrealized_pnl = self.calc_unrealized_pnl()
            sl_pnl = self.calc_sl_pnl()
            
            # 1. V5修复：追踪止盈激活 (不再用固定$8)
            if not self.trail_activated and unrealized_pnl >= self.get_trail_activate_pnl():
                self.trail_activated = True
                self.trail_peak = unrealized_pnl
                self.trail_stop = unrealized_pnl - self.get_trail_pullback()
                self.trail_activate_level = len(self.grid_positions)
                self.log(f'TRAIL_ON: ${unrealized_pnl:.2f} ATR:{self.atr[0]:.2f} -> stop ${self.trail_stop:.2f} (pullback ${self.get_trail_pullback():.2f})')
            
            # 2. 更新追踪止盈
            if self.trail_activated:
                if unrealized_pnl > self.trail_peak:
                    self.trail_peak = unrealized_pnl
                    self.trail_stop = self.trail_peak - self.get_trail_pullback()
            
            # 3. 追踪止损触发 (V5：删除固定止盈，让追踪真正生效)
            if self.trail_activated and unrealized_pnl <= self.trail_stop:
                self.close_all(f'TRAIL_SL +${unrealized_pnl:.2f} | peak: ${self.trail_peak:.2f}')
                return
            
            # 4. V5修复：锚定最后一单的止损
            if self.position_type == 1:  # 多单
                if current_price <= self.get_sl_price():
                    self.close_all(f'DYN_SL -${sl_pnl:.2f} | Price: ${current_price:.2f} < SL: ${self.get_sl_price():.2f}')
                    return
            else:  # 空单
                if current_price >= self.get_sl_price():
                    self.close_all(f'DYN_SL -${sl_pnl:.2f} | Price: ${current_price:.2f} > SL: ${self.get_sl_price():.2f}')
                    return
            
            # 5. V5修复：智能RSI分级平仓
            # 情景A：亏损或微利+已加网格 → RSI反转立刻跑
            # 情景B：大幅盈利+只有L0 → RSI超买可能是逼空，不跑
            rsi_exit = False
            if self.position_type == 1 and self.rsi > V5Config.RSI_CLOSE_LONG:
                # 只有L0且大幅盈利 → 放宽RSI条件
                if len(self.grid_positions) == 1 and unrealized_pnl > V5Config.RSI_PROFIT_THRESHOLD:
                    if self.rsi > 75:  # 更严格
                        rsi_exit = True
                else:
                    rsi_exit = True
            elif self.position_type == -1 and self.rsi < V5Config.RSI_CLOSE_SHORT:
                if len(self.grid_positions) == 1 and unrealized_pnl > V5Config.RSI_PROFIT_THRESHOLD:
                    if self.rsi < 25:  # 更严格
                        rsi_exit = True
                else:
                    rsi_exit = True
            
            if rsi_exit:
                self.close_all(f'RSI_CLOSE +${unrealized_pnl:.2f} | RSI: {self.rsi[0]:.1f} | L{len(self.grid_positions)-1}')
                return
            
            # 6. 网格加仓 (动态间距)
            last_entry = self.grid_positions[-1][0]
            
            # 多头: 价格下跌超过动态间距
            if self.position_type == 1 and current_price <= last_entry - grid_step:
                if len(self.grid_positions) < self.p.grid_levels:
                    level = len(self.grid_positions)
                    size = self.get_position_size(level)
                    self.grid_positions.append((current_price, size, level))
                    self.total_size += size
                    total_cost = sum(p * s for p, s, _ in self.grid_positions)
                    self.avg_price = total_cost / self.total_size
                    self.order_count += 1
                    self.log(f'ADD_L{level}: ${current_price:.2f} | Size: {size:.4f} | ATR: {grid_step:.2f} | SL: ${self.get_sl_price():.2f}')
            
            # 空头: 价格上涨超过动态间距
            elif self.position_type == -1 and current_price >= last_entry + grid_step:
                if len(self.grid_positions) < self.p.grid_levels:
                    level = len(self.grid_positions)
                    size = self.get_position_size(level)
                    self.grid_positions.append((current_price, size, level))
                    self.total_size += size
                    total_cost = sum(p * s for p, s, _ in self.grid_positions)
                    self.avg_price = total_cost / self.total_size
                    self.order_count += 1
                    self.log(f'ADD_L{level}: ${current_price:.2f} | Size: {size:.4f} | ATR: {grid_step:.2f} | SL: ${self.get_sl_price():.2f}')

    def stop(self):
        wins = [t for t in self.trade_log if t > 0]
        losses = [t for t in self.trade_log if t < 0]
        
        win_rate = len(wins) / max(len(self.trade_log), 1) * 100
        
        self.log('='*70)
        self.log('V5 GRID EA - 终极进化版')
        self.log('='*70)
        self.log(f'TOTAL_ORDERS: {self.order_count}')
        self.log(f'TOTAL_TRADES: {len(self.trade_log)}')
        self.log(f'WINS: {len(wins)} | LOSSES: {len(losses)}')
        self.log(f'WIN_RATE: {win_rate:.1f}%')
        
        if self.trade_log:
            avg_win = sum(wins)/len(wins) if wins else 0
            avg_loss = abs(sum(losses)/len(losses)) if losses else 0
            total_wins = sum(wins)
            total_losses = sum(losses)
            profit_factor = abs(total_wins/total_losses) if total_losses != 0 else float('inf')
            
            self.log(f'AVG_WIN: ${avg_win:.2f} | AVG_LOSS: ${avg_loss:.2f}')
            self.log(f'GROSS_PROFIT: ${total_wins:.2f}')
            self.log(f'GROSS_LOSS: ${total_losses:.2f}')
            self.log(f'NET_PROFIT: ${sum(self.trade_log):.2f}')
            self.log(f'PROFIT_FACTOR: {profit_factor:.2f}')
            
            # ECN成本
            ecn_spread = 0.2
            ecn_comm = 5.0
            avg_size = 0.02
            cost_per_trade = (ecn_spread * avg_size * 100) + (ecn_comm * avg_size * 2)
            total_cost = len(self.trade_log) * cost_per_trade
            net_profit_ecn = sum(self.trade_log) - total_cost
            
            self.log('='*70)
            self.log('ECN ACCOUNT')
            self.log('='*70)
            self.log(f'TOTAL_COST: ${total_cost:.2f}')
            self.log(f'NET_PROFIT_ECN: ${net_profit_ecn:.2f}')
            self.log('='*70)

def run():
    print("="*70)
    print(" V5 GRID EA - 终极进化版回测 ".center(70, "="))
    print("="*70)
    
    local_data_path = "GOLD_M5_202103100105_202603092005.csv"
    
    if not os.path.exists(local_data_path):
        print("[ERROR] Data not found!")
        return
    
    df = pd.read_csv(local_data_path, sep='\t')
    df.columns = [c.strip('<>') for c in df.columns]
    df.index = pd.to_datetime(df['DATE'] + ' ' + df['TIME'])
    df = df.rename(columns={'OPEN':'Open','HIGH':'High','LOW':'Low','CLOSE':'Close','TICKVOL':'Volume'})
    df = df[['Open','High','Low','Close','Volume']].dropna()
    print(f"[Data] {len(df)} bars")
    print(f"[Period] {df.index[0]} ~ {df.index[-1]}")
    print(f"[Price] ${df['Close'].min():.2f} - ${df['Close'].max():.2f}")
    
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(V5Config.INITIAL_CAPITAL)
    cerebro.broker.setcommission(commission=V5Config.COMMISSION)
    
    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)
    cerebro.addstrategy(V5GridEA)
    
    print(f"\n[Start] ${cerebro.broker.getvalue():.2f}")
    cerebro.run()
    print(f"[End] ${cerebro.broker.getvalue():.2f}")

if __name__ == '__main__':
    run()
