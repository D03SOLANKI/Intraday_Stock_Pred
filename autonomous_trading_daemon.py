"""
Autonomous Trading System Daemon
Runs 24/7 in the background with Auto-Boot Startup & Resume.
Automatically starts on PC boot/logon, manages pre-market scanning,
opening execution at 09:30 AM, real-time position ratcheting, and 15:15 PM square-off.
"""

import os
import sys
import time
import json
import logging
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# Set working directory to project root
WORKSPACE_DIR = r"E:\stock_predictor\stock_predictor"
os.chdir(WORKSPACE_DIR)
sys.path.append(WORKSPACE_DIR)

# Single Instance Lock Mechanism
LOCK_FILE = os.path.join(WORKSPACE_DIR, "daemon.lock")

def acquire_single_instance_lock():
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                content = f.read().strip()
                if content:
                    pid = int(content)
                    import psutil
                    if psutil.pid_exists(pid):
                        proc = psutil.Process(pid)
                        if "python" in proc.name().lower():
                            # Process already running
                            sys.exit(0)
        except Exception:
            pass
    # Write current PID
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))

acquire_single_instance_lock()

from strategy.dynamic_compounding_strategy import DynamicCompoundingStrategy
from live_scanner import run_scanner
from order_manager import OrderManager

LOG_DIR = os.path.join(WORKSPACE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

def setup_logger():
    today_str = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(LOG_DIR, f"trading_daemon_{today_str}.log")
    
    logger = logging.getLogger("AutonomousDaemon")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    
    return logger

STATE_FILE = os.path.join(WORKSPACE_DIR, "daemon_state.json")

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"date": None, "scanner_run": False, "square_off_done": False}

def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass

def run_daemon():
    logger = setup_logger()
    logger.info("=" * 80)
    logger.info("AUTONOMOUS TRADING DAEMON ONLINE (AUTO-BOOT RESUME ACTIVE)")
    logger.info(f"PID: {os.getpid()} | Workspace: {WORKSPACE_DIR}")
    logger.info("=" * 80)
    
    order_mgr = None
    
    while True:
        try:
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            weekday = now.weekday() # 0 = Mon, ..., 6 = Sun
            curr_time = now.time()
            
            state = load_state()
            if state.get("date") != today_str:
                state = {"date": today_str, "scanner_run": False, "square_off_done": False}
                save_state(state)
                logger = setup_logger()
                order_mgr = None
                
            # 1. Weekend Sleep Mode
            if weekday >= 5:
                logger.info(f"Weekend mode active ({'Saturday' if weekday==5 else 'Sunday'}). Markets closed. Sleeping...")
                time.sleep(3600)
                continue
                
            time_0914 = datetime.strptime("09:14:00", "%H:%M:%S").time()
            time_0930 = datetime.strptime("09:30:05", "%H:%M:%S").time()
            time_1515 = datetime.strptime("15:15:00", "%H:%M:%S").time()
            time_1530 = datetime.strptime("15:30:00", "%H:%M:%S").time()
            
            # 2. Before Market Open (< 09:14 AM)
            if curr_time < time_0914:
                secs_until_premarket = (datetime.combine(now.date(), time_0914) - now).total_seconds()
                sleep_secs = min(300, max(10, secs_until_premarket))
                logger.info(f"Pre-market waiting: {int(secs_until_premarket/60)}m until 09:14 AM scan. Sleeping {int(sleep_secs)}s...")
                time.sleep(sleep_secs)
                continue
                
            # 3. Pre-Market Window (09:14 - 09:30 AM)
            if time_0914 <= curr_time < time_0930:
                secs_until_open = (datetime.combine(now.date(), time_0930) - now).total_seconds()
                logger.info(f"Pre-market active. {int(secs_until_open)}s until 09:30 AM execution trigger.")
                time.sleep(min(10, max(1, secs_until_open)))
                continue
                
            # 4. Opening Trigger (09:30 AM IST)
            if curr_time >= time_0930 and not state.get("scanner_run"):
                logger.info(">>> 09:30 AM: EXECUTING POINT-IN-TIME MID-CAP SCANNER <<<")
                try:
                    orders_df = run_scanner(trading_date=None, active_equity=10_000_000.0)
                    state["scanner_run"] = True
                    save_state(state)
                    logger.info(f"Scanner completed. {len(orders_df) if orders_df is not None else 0} actionable orders generated.")
                    order_mgr = OrderManager()
                except Exception as e:
                    logger.error(f"Scanner error: {e}", exc_info=True)
                    time.sleep(10)
                    continue

            # 5. Intraday Active Monitoring (09:30 - 15:15 IST)
            if time_0930 <= curr_time < time_1515:
                if order_mgr is None:
                    logger.info("Mid-day boot/restart detected. Recovering active positions into Order Manager...")
                    order_mgr = OrderManager()
                    
                open_positions = [p for p in order_mgr.positions if p['status'] == 'OPEN']
                if not open_positions:
                    logger.info(f"Intraday heartbeat [{curr_time.strftime('%H:%M:%S')} IST]: All positions closed/flat. Standing by.")
                    time.sleep(30)
                    continue
                    
                # Poll real-time market prices for active open positions
                try:
                    import yfinance as yf
                    symbols_ns = [f"{p['symbol']}.NS" for p in open_positions]
                    yf_data = yf.download(symbols_ns, period="1d", interval="1m", progress=False)
                    live_px = {}
                    if not yf_data.empty and 'Close' in yf_data:
                        if isinstance(yf_data['Close'], pd.DataFrame):
                            for p in open_positions:
                                t = f"{p['symbol']}.NS"
                                if t in yf_data['Close'] and not pd.isna(yf_data['Close'][t].iloc[-1]):
                                    live_px[p['symbol']] = float(yf_data['Close'][t].iloc[-1])
                        elif isinstance(yf_data['Close'], pd.Series):
                            live_px[open_positions[0]['symbol']] = float(yf_data['Close'].iloc[-1])
                            
                    if live_px:
                        target_hit = order_mgr.process_portfolio_ticks(live_px)
                        if target_hit:
                            logger.info("Portfolio profit target triggered and all positions locked in profit!")
                except Exception as tick_err:
                    logger.warning(f"Live tick polling error: {tick_err}")
                    
                logger.info(f"Intraday heartbeat [{curr_time.strftime('%H:%M:%S')} IST]: Tracking {len([p for p in order_mgr.positions if p['status'] == 'OPEN'])} active positions.")
                time.sleep(30)
                continue

            # 6. Intraday Auto-Square-Off (15:15 IST)
            if curr_time >= time_1515 and not state.get("square_off_done"):
                logger.info(">>> 15:15 IST: EXECUTING INTRADAY AUTO-SQUARE-OFF <<<")
                if order_mgr is None:
                    order_mgr = OrderManager()
                try:
                    # Download REAL market prices for fair square-off
                    open_positions = [p for p in order_mgr.positions if p['status'] == 'OPEN']
                    real_mkt_px = {}
                    if open_positions:
                        try:
                            import yfinance as yf
                            symbols_ns = [f"{p['symbol']}.NS" for p in open_positions]
                            yf_data = yf.download(symbols_ns, period="1d", interval="5m", progress=False)
                            if not yf_data.empty and 'Close' in yf_data:
                                if isinstance(yf_data['Close'], pd.DataFrame):
                                    for p in open_positions:
                                        t = f"{p['symbol']}.NS"
                                        if t in yf_data['Close'] and not pd.isna(yf_data['Close'][t].iloc[-1]):
                                            real_mkt_px[p['symbol']] = float(yf_data['Close'][t].iloc[-1])
                                elif isinstance(yf_data['Close'], pd.Series):
                                    real_mkt_px[open_positions[0]['symbol']] = float(yf_data['Close'].iloc[-1])
                        except Exception:
                            pass
                    for p in open_positions:
                        if p['symbol'] not in real_mkt_px:
                            real_mkt_px[p['symbol']] = p['entry_price']
                            
                    summary_df = order_mgr.square_off_at_eod(real_mkt_px, reason="INTRADAY SQUARE OFF (15:15 IST)")
                    state["square_off_done"] = True
                    save_state(state)
                    logger.info("Square-off execution completed.")
                except Exception as e:
                    logger.error(f"Square-off error: {e}", exc_info=True)
                    
            # 7. Post-Market Close (> 15:30 IST)
            if curr_time >= time_1530:
                tomorrow_0830 = datetime.combine(now.date() + timedelta(days=1), datetime.strptime("08:30:00", "%H:%M:%S").time())
                secs_until_tomorrow = (tomorrow_0830 - now).total_seconds()
                logger.info(f"Market closed. Sleeping until tomorrow 08:30 AM ({int(secs_until_tomorrow/3600)}h {int((secs_until_tomorrow%3600)/60)}m)...")
                time.sleep(min(3600, secs_until_tomorrow))
                continue
                
            time.sleep(10)

        except Exception as e:
            logger.error(f"Daemon error: {e}", exc_info=True)
            time.sleep(15)

if __name__ == "__main__":
    run_daemon()
