"""
The original receivables screens (built on invoiced_items and Postgres-only SQL)
have been retired. Client invoices and payments are handled by apps.finance;
the Payment model in this app still stores the client payments.
"""
