# Implementation Plan - KIS API Throttling & Exception Handling

This plan addresses the `ConnectionError` (connection aborted, remote disconnected) that occurs during the scheduled VM trading cycles (`daily_auto`).

## Findings & Root Cause Analysis

1. **Scheduled Cycle Error**: The scheduled `daily_auto` runs `src.scheduler` in `daily_auto` mode which triggers `trader.run(mode="analysis_only", include_ai_rebalance=True)`.
2. **Burst KIS Requests**: When there are multiple candidates to buy, `build_orders` in `src/strategy/seven_split.py` loops through the candidates and calls the inquiry callback `get_quote_fn` (which maps to `KIStockAPI.get_quote` in `src/trader.py`).
3. **No Throttling & No Exception Handling**: 
   - `KIStockAPI.get_quote` in `src/trader.py` bypasses `KISClient` and makes the HTTP request directly using `HTTP.get`.
   - It **does not throttle** the requests, meaning it hits KIS API in rapid succession (e.g. 20 requests within ~0.5s if `MAX_POSITIONS` is large).
   - This triggers the KIS API server to abort/disconnect the connection.
   - It also **lacks exception handling**, causing the entire trader run to crash on `ConnectionError` instead of handling it gracefully.
4. **Impact**: The connection abort bubbles up, failing the schedule cycle three times in a row, leading to automated trading failure.

## Proposed Changes

We will modify `src/trader.py`'s `KIStockAPI` methods to add safe throttling, robust exception handling, and circuit breaker logging. This keeps all existing unit tests and mocks intact while adding production safety.

### trader

#### [MODIFY] [trader.py](file:///C:/MSF-LOC/workstudy/hanstock/src/trader.py)

- **`KIStockAPI.get_balance`**: Add `_kis_order_throttle()` before calling the balance API, and update the circuit breaker state on failure.
- **`KIStockAPI.get_quote`**: Add `_kis_order_throttle()` before calling the KIS inquire-price API. Wrap the call in a `try...except` block, log a warning on exception, mark circuit failure, and return a fallback empty quote `{"current": 0.0, "ask1": 0.0, "bid1": 0.0}`.
- **`KIStockAPI.place_order`**: Wrap the HTTP post call in a `try...except` block, log a warning on exception, mark circuit failure, and return a fallback error response `{"rt_cd": "1", "msg1": str(e)}`.

## Verification Plan

### Automated Tests
We will run the existing test suite locally:
```powershell
python -m unittest discover -s tests
```
We will also run the local verification script:
```powershell
powershell -ExecutionPolicy Bypass -File tools\verify-local.ps1
```

### Manual Verification
1. We will verify the changes are logically sound.
2. We will run a dry run test locally using:
   ```powershell
   python src\trader.py
   ```
3. After committing and pushing changes, we can deploy to the VM using:
   ```powershell
   .\scripts\local\deploy-vm.ps1
   ```
4. Once deployed on the VM, we can run a dry-run test on the VM or inspect VM status to ensure it works correctly.
