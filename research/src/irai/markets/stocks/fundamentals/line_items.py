"""Nomes canônicos de linha de demonstração.

Toda fonte (CVM, SEC XBRL, yfinance) é traduzida para ESTE vocabulário antes
de entrar no banco. É o que permite comparar uma empresa brasileira com uma
americana sem depender do plano de contas de origem.
"""

from __future__ import annotations

# --- DRE ---------------------------------------------------------------
REVENUE = "revenue"
COST_OF_REVENUE = "cost_of_revenue"
GROSS_PROFIT = "gross_profit"
OPERATING_INCOME = "operating_income"
EBITDA = "ebitda"
DEPRECIATION_AMORTIZATION = "depreciation_amortization"
INTEREST_EXPENSE = "interest_expense"
PRETAX_INCOME = "pretax_income"
INCOME_TAX = "income_tax"
NET_INCOME = "net_income"
EPS_DILUTED = "eps_diluted"
SHARES_DILUTED = "shares_diluted"

# --- Balanço -----------------------------------------------------------
TOTAL_ASSETS = "total_assets"
CURRENT_ASSETS = "current_assets"
CASH_AND_EQUIVALENTS = "cash_and_equivalents"
TOTAL_LIABILITIES = "total_liabilities"
CURRENT_LIABILITIES = "current_liabilities"
TOTAL_DEBT = "total_debt"
TOTAL_EQUITY = "total_equity"
SHARES_OUTSTANDING = "shares_outstanding"

# --- Fluxo de caixa ----------------------------------------------------
OPERATING_CASH_FLOW = "operating_cash_flow"
CAPEX = "capex"
DIVIDENDS_PAID = "dividends_paid"
BUYBACKS = "buybacks"

INCOME_ITEMS = frozenset({
    REVENUE, COST_OF_REVENUE, GROSS_PROFIT, OPERATING_INCOME, EBITDA,
    DEPRECIATION_AMORTIZATION, INTEREST_EXPENSE, PRETAX_INCOME, INCOME_TAX,
    NET_INCOME, EPS_DILUTED, SHARES_DILUTED,
})
BALANCE_ITEMS = frozenset({
    TOTAL_ASSETS, CURRENT_ASSETS, CASH_AND_EQUIVALENTS, TOTAL_LIABILITIES,
    CURRENT_LIABILITIES, TOTAL_DEBT, TOTAL_EQUITY, SHARES_OUTSTANDING,
})
CASHFLOW_ITEMS = frozenset({OPERATING_CASH_FLOW, CAPEX, DIVIDENDS_PAID, BUYBACKS})

ALL_ITEMS = INCOME_ITEMS | BALANCE_ITEMS | CASHFLOW_ITEMS

# Itens de FLUXO somam ao longo do tempo (receita, lucro). Itens de ESTOQUE
# são fotos numa data (ativo, dívida). A distinção decide como calcular TTM e
# como fazer média — confundir as duas é erro clássico de cálculo de ROE.
FLOW_ITEMS = INCOME_ITEMS | CASHFLOW_ITEMS - {EPS_DILUTED, SHARES_DILUTED}
STOCK_ITEMS = BALANCE_ITEMS | {SHARES_DILUTED}


def is_flow(item: str) -> bool:
    return item in FLOW_ITEMS


def is_stock(item: str) -> bool:
    return item in STOCK_ITEMS
