# Synthetic Order Requirements

This document is synthetic and contains no production or personal data.

## ORD-001 - Create a draft order

A signed-in customer with the `ORDER_EDIT` permission can create an order. On successful creation, the system provides a visible order reference and shows the order in `DRAFT` state.

## ORD-002 - Line quantity

For an order in `DRAFT` state, a customer can set each line quantity to an integer from 1 through 10, inclusive. A value outside this range is rejected and the existing quantity remains unchanged. No required rejection message is specified.

## ORD-003 - Submit an order

Submitting an order in `DRAFT` state changes its state to `SUBMITTED`. An order in `SUBMITTED` state cannot be edited; an edit attempt is rejected and the order data remains unchanged.

## ORD-004 - Permission

A signed-in customer without `ORDER_EDIT` cannot create or edit an order. The attempted operation is denied and no order data is changed.

## ORD-005 - Cancellation

The customer can cancel the order before invoicing.

The requirement does not define a message, internal status, HTTP status, resulting state, or side effects.

## ORD-006 - Billing service unavailable

If the billing service is unavailable while a customer submits a `DRAFT` order, submission does not complete and a retry action is made available. The requirement does not define the order state after the failed attempt or whether partial data is retained.

## ORD-007 - Processing speed

Orders should be processed quickly.

No measurable time limit, percentile, load, or start/end points are defined.

## ORD-008 - Finalize a submitted order

A customer can finalize an order in `SUBMITTED` state. Successful finalization changes the state to `FINALIZED` and shows a visible confirmation.
