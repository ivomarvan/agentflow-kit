# Homework Assignments: AI Agent Orchestration

This document contains two homework assignments designed to help you practice AI agent orchestration. Based on the provided examples in the project (such as `examples/agents/06_smart_home.py` which demonstrates a similar concept), you can try to implement these scenarios yourself. These exercises are great for mastering state graphs, tool calling, and multi-agent coordination.

---

## Scenario 1: Voice Banking Assistant and Budget Monitor (FinTech)

### Scenario Context

A client calls their bank's customer service line to quickly check their account balance, transfer money, or calculate if they can afford a purchase. Because this involves real money, every operation proposed by the Worker agent must be approved by a strict Judge agent that checks financial logic and limits.

### Graph Architecture (4 Nodes)

1. **`Call_Inbound_Router`**: Receives the audio transcript, performs basic entity analysis (identifies amounts, currencies, names), and initializes the session state.
2. **`Transaction_Worker`**: (*Powered by a cheaper LLM*). Calls banking tools based on the client's request. Prepares a transaction proposal or an answer to a financial query.
3. **`Compliance_Judge`**: (*Powered by a more expensive LLM*). Reviews the Worker's output. Verifies if the transaction makes sense (e.g., checks currency conversion, ensures the client isn't sending a negative amount, and verifies daily limits are not exceeded). If the Judge finds a discrepancy, it rejects the proposal and sends instructions back to the Worker to fix it.
4. **`Audio_Response_Composer`**: Converts dry financial data and approved transactions into an empathetic voice response (e.g., instead of "Transaction ID 456 approved", it says "All set, I have just deducted the money from your account").

### Deterministic Tools (4)

* `get_balance(account_type)` – Returns the current balance of a checking or savings account.
* `convert_currency(amount, from_currency, to_currency)` – Performs a mathematical conversion based on current exchange rates.
* `check_daily_limits(amount)` – Returns `True` or `False` depending on whether the requested amount is within the daily limit.
* `log_pending_transaction(target_account, amount)` – Logs the transaction in a temporary registry before the final submission.

---

## Scenario 2: Voice Assistant for Corporate Logistics and Purchasing (Operations)

### Scenario Context

A warehouse worker or field technician speaks into a phone app to order a courier, check part availability in the warehouse, or calculate shipping costs for a customer. The system must operate quickly, but a Judge agent is required to monitor corporate policy and budget rules.

### Graph Architecture (5 Nodes)

1. **`Audio_Input_Cleaner`**: Receives text from voice input, which might contain operational noise (slips of the tongue, background noise). Cleans the text and extracts key data (product codes, addresses).
2. **`Logistics_Worker`**: (*Powered by a cheaper LLM*). Searches for information in internal systems using tools and creates a logistics plan (e.g., price calculation or material reservation).
3. **`Policy_Judge`**: (*Powered by a more expensive LLM*). Checks if the plan complies with internal guidelines (e.g., ensures the purchase doesn't exceed the employee's limit, or that an overly expensive shipping method wasn't selected). If it doesn't pass, it returns the state to the Worker with a justification.
4. **`State_Consolidator`**: Combines approved data from previous steps, finalizes the state in the database, and prepares clean data for dispatch.
5. **`Voice_Brief_Generator`**: Creates a very short, punchy report for the worker's earpiece (e.g., "Ordered. Courier arrives at 14:00. 5 pieces left in stock.").

### Deterministic Tools (3)

* `check_stock(item_id)` – Returns the number of items in stock and their warehouse location.
* `calculate_shipping_cost(weight_kg, distance_km)` – Calculates a fixed shipping price based on the given parameters.
* `get_user_permission_level(user_id)` – Returns the financial limit and authorization level of the given worker.
