from trading.paper_engine import PaperEngine
from trading.ledger import Ledger
from trading.execution_router import ExecutionRouter

def run_test():
    ledger = Ledger()
    pe = PaperEngine(ledger=ledger)
    router = ExecutionRouter(mode='paper', ledger=ledger, paper_engine=pe)
    
    print('Initial Balance: $' + str(pe.balance))
    
    # 1. Test Signal Dispatch
    signal = {
        'symbol': 'BTCUSD',
        'side': 'BUY',
        'entry_price': 81400.0,
        'stop_loss': 80500.0,
        'take_profit': 82500.0,
        'strategy_name': 'TEST_STRAT',
        'rationale': 'Test breakout'
    }
    
    res = router.dispatch(signal, mark_price=81400.0)
    print('Dispatch Result:', res)
    assert res['status'] == 'FILLED', 'Dispatch failed'
    
    # 2. Test Open Positions Count
    print('Open positions count:', len(pe.open_positions))
    assert len(pe.open_positions) == 1
    
    # 3. Simulate Price Movement to Take Profit
    closed = pe.evaluate_ticks({'BTCUSD': 82600.0})
    print('Closed on TP:', closed)
    assert len(closed) == 1
    assert len(pe.open_positions) == 0
    
    # 4. Check PnL in ledger
    pnl = ledger.get_today_pnl('paper')
    print(f'Today Realized PnL: ')
    
    print('ALL PAPER TRADING PIPELINE TESTS PASSED!')

if __name__ == '__main__':
    run_test()
