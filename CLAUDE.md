# Omni-Chain Executor

You are operating in autonomous pipeline mode for financial analysis and trading.

## Rules
- Read CLAUDE_PLAN.md as your primary instruction set
- Never ask for clarification — interpret and proceed
- Use paper trading endpoints only until live mode is explicitly enabled in .env
- Log all API calls to ./logs/run_{timestamp}.log
- On error, write error details to ./logs/errors.log and halt

## Environment
- Load all credentials from .env (never hardcode keys)
- Project root: D:/Projects/omni-chain

## Alpaca Config
- Base URL: loaded from ALPACA_BASE_URL in .env
- Default to paper trading always

## Default Data Sources
- Alpaca: market data, orders, positions
- Alpha Vantage: fundamentals, earnings
- FRED: macro/economic data
- Ollama (local): reasoning and synthesis (model: tinyllama)

## Knowledge Base
- All inputs and outputs are logged to ./knowledge/
- Each session creates a new entry with timestamp, query, and result
