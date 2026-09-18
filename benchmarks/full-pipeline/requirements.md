# Generic Reservation Requirements

- RSV-001: Confirming an eligible reservation atomically changes its state to CONFIRMED, decreases the available balance, and creates an audit entry.
- RSV-002: Cancelling an eligible reservation changes its state to CANCELLED.
- RSV-003: A malformed reservation request is rejected with HTTP 400.
