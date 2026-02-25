import json
import time
import random
import math # Added for math.sin

# 1. Strategy Parameters (Simulated retrieval from "memory")
# In a real scenario, these would be loaded from a config file or a database.
STRATEGY_PARAMS = {
    "initial_capital": 20.0,
    "max_risk_per_trade_usd": 0.20,
    "leverage": 20,
    "atr_multiplier_sl": 1.5, # Stop-loss based on 1.5x ATR
    "risk_reward_ratio_tp": 1.5, # Take-profit based on 1.5x risk
    "rsi_entry_buy": 60, # RSI threshold for buy
    "rsi_entry_sell": 40, # RSI threshold for sell
    "rsi_exit_momentum_loss_buy": 50, # RSI drop below 50 for buy exit
    "rsi_exit_momentum_loss_sell": 50, # RSI rise above 50 for sell exit
    # MACD: assume a crossover strategy. Positive for bullish, negative for bearish.
    # We'll need MACD line and Signal line
}

# Global state for simplicity, in a real app this would be more robust
current_position = {
    "side": None, # "long" or "short"
    "entry_price": None,
    "quantity": None,
    "stop_loss": None,
    "take_profit": None
}
trade_log = []

def log_trade_event(event_type, details):
    timestamp = time.time()
    log_entry = {"timestamp": timestamp, "event_type": event_type, "details": details}
    trade_log.append(log_entry)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))}] {event_type}: {details}")
    # In a real scenario, this would write to a file or database

def get_indicator_data():
    """
    Simulates fetching indicator data from 'hms20x_monitor_sol'.
    In a real system, this would be an API call or a database query.
    """
    # For demonstration, let's hardcode some sample data.
    # In a real system, this would come from a live data feed.
    current_time_factor = time.time() / 10000 # To make values change slowly
    
    price = 150.0 + (random.uniform(-5, 5))
    atr = 1.5 + (random.uniform(-0.5, 0.5))
    
    # Simulate RSI fluctuation for entry/exit
    rsi_base = 50 + 20 * (0.5 + 0.5 * math.sin(current_time_factor * 2)) # oscillates between 30 and 70
    
    # Simulate MACD crossover
    macd_line = 0.5 * math.sin(current_time_factor * 3) + 0.1 * random.uniform(-1, 1)
    macd_signal = 0.5 * math.sin(current_time_factor * 3 - 0.5) + 0.1 * random.uniform(-1, 1)
    
    macd_crossover_status = "none"
    if macd_line > macd_signal and macd_line - macd_signal > 0.05: # Bullish crossover threshold
        macd_crossover_status = "bullish"
    elif macd_signal > macd_line and macd_signal - macd_line > 0.05: # Bearish crossover threshold
        macd_crossover_status = "bearish"

    sample_data = {
        "timestamp": time.time(),
        "symbol": "SOL",
        "interval": "1m",
        "price": price,
        "atr": max(0.1, atr), # Ensure ATR is not zero or negative
        "rsi": max(0, min(100, rsi_base)),
        "macd_line": macd_line,
        "macd_signal": macd_signal,
        "macd_crossover": macd_crossover_status
    }
    log_trade_event("DATA_FETCH", f"Fetched data: {sample_data}")
    return sample_data

def calculate_position_size(price, atr, initial_capital, max_risk_per_trade_usd, leverage):
    """
    Calculates the position size based on max risk and ATR.
    Risk per share = ATR * ATR_multiplier_sl
    Number of shares = Max Risk / Risk per share
    Leveraged value = Number of shares * Price
    Actual capital used = Leveraged value / Leverage
    """
    if atr <= 0:
        log_trade_event("ERROR", "ATR must be positive for position sizing.")
        return 0

    # Risk per unit (or per unit of the asset)
    risk_per_unit = atr * STRATEGY_PARAMS["atr_multiplier_sl"]
    if risk_per_unit == 0:
        log_trade_event("ERROR", "Calculated risk per unit is zero, cannot determine position size.")
        return 0

    # Number of units we can trade given max risk (unleveraged)
    num_units_from_risk = max_risk_per_trade_usd / risk_per_unit

    # Total value of the position with leverage based on desired risk
    total_position_value_from_risk = num_units_from_risk * price * leverage

    # Max position size based on available initial capital and leverage
    max_position_value_from_capital = initial_capital * leverage
    
    # Use the minimum of the two to ensure we don't over-leverage or over-risk
    actual_position_value = min(total_position_value_from_risk, max_position_value_from_capital)

    if actual_position_value <= 0 or price <= 0 or leverage <= 0:
        log_trade_event("ERROR", "Invalid values for position size calculation.")
        return 0

    # Calculate actual number of units
    num_units = actual_position_value / price

    log_trade_event("POSITION_SIZE_CALC", f"Calculated position size: {num_units:.4f} units for total value {actual_position_value:.2f} USD")
    return num_units

def place_order_hyperliquid(side, quantity, price, stop_loss, take_profit):
    """
    Simulates placing an order on Hyperliquid Mainnet.
    In a real scenario, this would use a Hyperliquid API client.
    """
    order_details = {
        "symbol": "SOL",
        "side": side,
        "quantity": quantity,
        "order_type": "market", # Assuming market order for simplicity
        "price": price, # Entry price
        "stop_loss": stop_loss,
        "take_profit": take_profit
    }
    log_trade_event("ORDER_PLACEMENT_SIMULATED", f"Placed {side} order: {order_details}")
    return order_details

def check_entry_conditions(data):
    """
    Checks entry conditions based on RSI and MACD.
    """
    global current_position

    price = data["price"]
    rsi = data["rsi"]
    macd_crossover = data["macd_crossover"]
    atr = data["atr"]

    if current_position["side"] is None: # Only enter if no open position
        # Long Entry Conditions
        if rsi > STRATEGY_PARAMS["rsi_entry_buy"] and macd_crossover == "bullish":
            log_trade_event("ENTRY_SIGNAL", "Long entry conditions met.")
            size = calculate_position_size(price, atr, STRATEGY_PARAMS["initial_capital"], STRATEGY_PARAMS["max_risk_per_trade_usd"], STRATEGY_PARAMS["leverage"])
            if size > 0:
                stop_loss_price = price - (atr * STRATEGY_PARAMS["atr_multiplier_sl"])
                risk_amount = price - stop_loss_price
                take_profit_price = price + (risk_amount * STRATEGY_PARAMS["risk_reward_ratio_tp"])
                
                order_info = place_order_hyperliquid("buy", size, price, stop_loss_price, take_profit_price)
                current_position.update({
                    "side": "long",
                    "entry_price": price,
                    "quantity": size,
                    "stop_loss": stop_loss_price,
                    "take_profit": take_profit_price
                })
                log_trade_event("POSITION_OPENED", f"Long position opened: {current_position}")
                return True

        # Short Entry Conditions
        elif rsi < STRATEGY_PARAMS["rsi_entry_sell"] and macd_crossover == "bearish":
            log_trade_event("ENTRY_SIGNAL", "Short entry conditions met.")
            size = calculate_position_size(price, atr, STRATEGY_PARAMS["initial_capital"], STRATEGY_PARAMS["max_risk_per_trade_usd"], STRATEGY_PARAMS["leverage"])
            if size > 0:
                stop_loss_price = price + (atr * STRATEGY_PARAMS["atr_multiplier_sl"])
                risk_amount = stop_loss_price - price
                take_profit_price = price - (risk_amount * STRATEGY_PARAMS["risk_reward_ratio_tp"])

                order_info = place_order_hyperliquid("sell", size, price, stop_loss_price, take_profit_price)
                current_position.update({
                    "side": "short",
                    "entry_price": price,
                    "quantity": size,
                    "stop_loss": stop_loss_price,
                    "take_profit": take_profit_price
                })
                log_trade_event("POSITION_OPENED", f"Short position opened: {current_position}")
                return True
    return False

def manage_open_position(data):
    """
    Manages open positions: checks for Stop-Loss, Take-Profit, or Momentum Loss.
    """
    global current_position

    if current_position["side"] is None:
        return

    price = data["price"]
    rsi = data["rsi"]
    macd_crossover = data["macd_crossover"]

    # Check Stop-Loss
    if current_position["side"] == "long" and price <= current_position["stop_loss"]:
        log_trade_event("POSITION_CLOSE_SIGNAL", f"Long position hit Stop-Loss at {price}. SL: {current_position['stop_loss']:.2f}")
        close_position("sell", price)
        return
    elif current_position["side"] == "short" and price >= current_position["stop_loss"]:
        log_trade_event("POSITION_CLOSE_SIGNAL", f"Short position hit Stop-Loss at {price}. SL: {current_position['stop_loss']:.2f}")
        close_position("buy", price)
        return

    # Check Take-Profit
    if current_position["side"] == "long" and price >= current_position["take_profit"]:
        log_trade_event("POSITION_CLOSE_SIGNAL", f"Long position hit Take-Profit at {price}. TP: {current_position['take_profit']:.2f}")
        close_position("sell", price)
        return
    elif current_position["side"] == "short" and price <= current_position["take_profit"]:
        log_trade_event("POSITION_CLOSE_SIGNAL", f"Short position hit Take-Profit at {price}. TP: {current_position['take_profit']:.2f}")
        close_position("buy", price)
        return

    # Check Momentum Loss
    if current_position["side"] == "long":
        if rsi < STRATEGY_PARAMS["rsi_exit_momentum_loss_buy"] or macd_crossover == "bearish":
            log_trade_event("POSITION_CLOSE_SIGNAL", f"Long position: Momentum loss detected (RSI={rsi:.2f}, MACD={macd_crossover}).")
            close_position("sell", price)
            return
    elif current_position["side"] == "short":
        if rsi > STRATEGY_PARAMS["rsi_exit_momentum_loss_sell"] or macd_crossover == "bullish":
            log_trade_event("POSITION_CLOSE_SIGNAL", f"Short position: Momentum loss detected (RSI={rsi:.2f}, MACD={macd_crossover}).")
            close_position("buy", price)
            return

def close_position(side, price):
    """
    Simulates closing an open position.
    """
    global current_position
    
    if current_position["quantity"] is None or current_position["quantity"] <= 0:
        log_trade_event("ERROR", "Attempted to close a position with zero or negative quantity.")
        return

    close_order_details = {
        "symbol": "SOL",
        "side": side, # Opposite of current position side
        "quantity": current_position["quantity"],
        "order_type": "market",
        "price": price # Closing price
    }
    log_trade_event("ORDER_CLOSE_SIMULATED", f"Closed position: {close_order_details}")
    
    # Reset position state
    current_position = {
        "side": None,
        "entry_price": None,
        "quantity": None,
        "stop_loss": None,
        "take_profit": None
    }
    log_trade_event("POSITION_CLOSED", "Position state reset.")

def run_strategy_iteration():
    """
    Main loop iteration for the strategy.
    """
    log_trade_event("STRATEGY_RUN", "Fetching new data...")
    data = get_indicator_data()

    if current_position["side"] is None:
        check_entry_conditions(data)
    else:
        manage_open_position(data)
    
    log_trade_event("STRATEGY_RUN", f"Current position status: {current_position}")
    # In a real scenario, this would loop at 1-minute intervals.
    # For simulation, we just run once or a few times.

if __name__ == "__main__":
    # Simulate a few iterations
    print("--- Starting Hyperliquid Momentum Strategy Simulation ---")
    for i in range(10): # Run 10 iterations to demonstrate
        run_strategy_iteration()
        time.sleep(0.5) # Simulate time passing between 1-minute intervals
    
    print("--- Trade Log ---") # Simplified this line
    for entry in trade_log:
        print(json.dumps(entry, indent=2))
