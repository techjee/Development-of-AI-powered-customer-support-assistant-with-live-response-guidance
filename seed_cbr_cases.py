"""
seed_cbr_cases.py

Seeds 500 realistic, successfully resolved historical customer-support cases
for the CBR system.

500 cases = 50 scenario families x 10 variants.

Uses the existing project services and the existing 5-table PostgreSQL schema.
No new tables are created.
No Gemini / LLM calls are made.

Run:
    .\venv\Scripts\python.exe seed_cbr_cases.py
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from database import SessionLocal, ensure_auth_schema
from models import User
from services import (
    add_message,
    create_case,
    create_case_event_once,
    create_customer,
    get_case,
    resolve_case,
    update_case,
)


# ---------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------

TOTAL_CASES = 500
VARIANTS_PER_SCENARIO = 10
START_CASE_NUMBER = 2001

SEED_AGENT_EMAIL = "agent@infosys.com"

random.seed(42)


# ---------------------------------------------------------------------
# 10 DIFFERENT CUSTOMER MESSAGE STYLES
# ---------------------------------------------------------------------

MESSAGE_WRAPPERS = [
    "Hi, I need help with this issue: {issue}",
    "Hello, I'm facing the following problem: {issue}",
    "I am contacting support because {issue}",
    "Could you please help me? {issue}",
    "I need assistance regarding this: {issue}",
    "I'm having an issue with my order/account. {issue}",
    "Please help me resolve this problem. {issue}",
    "I have been trying to resolve this but {issue}",
    "Can you look into this for me? {issue}",
    "This problem is still unresolved. {issue}",
]


# ---------------------------------------------------------------------
# 50 SCENARIO FAMILIES
# ---------------------------------------------------------------------
#
# 10 categories x 5 scenarios = 50 scenario families.
#
# Financial cases -> Accounts
# Normal support/product/technical cases -> Support
# ---------------------------------------------------------------------

SCENARIOS = [
    # ================================================================
    # REFUND — 5
    # ================================================================

    {
        "name": "refund_delayed",
        "intent": "Refund",
        "department": "Accounts",
        "key_issue": "Refund delayed after approved refund",
        "policy": "Refund Delay Policy",
        "severity": "Medium",
        "urgency": "Medium",
        "risk": "Medium",
        "priority": "High",
        "sentiment": "Negative",
        "issues": [
            "my refund was approved but I still have not received the money",
            "the refund was processed several days ago but it has not reached my account",
            "I was told my refund was completed, but the amount is still missing",
            "my cancelled order was refunded but the money has not appeared yet",
        ],
        "responses": [
            "I checked the refund status and confirmed that it is being processed. We will continue tracking it and update you once the amount is credited.",
            "I understand the delay is frustrating. Your refund has been confirmed and we are monitoring the processing status.",
        ],
    },
    {
        "name": "refund_not_received",
        "intent": "Refund",
        "department": "Accounts",
        "key_issue": "Refund not received",
        "policy": "Refund Policy",
        "severity": "Medium",
        "urgency": "Medium",
        "risk": "Medium",
        "priority": "High",
        "sentiment": "Negative",
        "issues": [
            "I requested a refund but have not received anything",
            "the refund was promised but the amount is still not credited",
            "I returned the order and I am still waiting for my refund",
            "my refund request shows approved but there is no credit in my account",
        ],
        "responses": [
            "I have verified the refund request and will track the credit until it reaches your original payment method.",
            "Your refund request is recorded. I have checked the status and will ensure the refund is followed through.",
        ],
    },
    {
        "name": "partial_refund",
        "intent": "Refund",
        "department": "Accounts",
        "key_issue": "Partial refund amount received",
        "policy": "Refund Policy",
        "severity": "Medium",
        "urgency": "Medium",
        "risk": "Medium",
        "priority": "High",
        "sentiment": "Negative",
        "issues": [
            "I received only part of the refund amount",
            "the refund credited to me is lower than what I was expecting",
            "only a portion of my payment has been refunded",
            "my refund amount does not match the amount that was approved",
        ],
        "responses": [
            "I reviewed the refund details and identified the amount credited. I will verify the remaining eligible amount and have it addressed.",
            "I understand the difference in the refund amount. I have checked the case and will follow up on the remaining eligible amount.",
        ],
    },
    {
        "name": "refund_after_return",
        "intent": "Refund",
        "department": "Accounts",
        "key_issue": "Refund pending after product return",
        "policy": "Refund Policy",
        "severity": "Medium",
        "urgency": "Medium",
        "risk": "Medium",
        "priority": "High",
        "sentiment": "Negative",
        "issues": [
            "I returned the product but the refund has not arrived",
            "the returned item was received but my refund is still pending",
            "my return was accepted and I am waiting for the money back",
            "the product has been returned successfully but I have not received the refund",
        ],
        "responses": [
            "I confirmed the return status and will track the associated refund through completion.",
            "Your return has been recorded successfully. I will follow the refund status and ensure the pending amount is addressed.",
        ],
    },
    {
        "name": "refund_after_cancellation",
        "intent": "Refund",
        "department": "Accounts",
        "key_issue": "Refund pending after cancellation",
        "policy": "Cancellation Policy",
        "severity": "Medium",
        "urgency": "Medium",
        "risk": "Medium",
        "priority": "High",
        "sentiment": "Negative",
        "issues": [
            "I cancelled my order and I am waiting for the refund",
            "the cancellation was confirmed but my payment has not been refunded",
            "my cancelled order still shows no refund",
            "I received cancellation confirmation but the money has not come back",
        ],
        "responses": [
            "I confirmed the cancellation and will track the refund associated with the cancelled order.",
            "The cancellation is recorded. I will verify the refund status and make sure the eligible amount is processed.",
        ],
    },

    # ================================================================
    # PAYMENT — 5
    # ================================================================

    {
        "name": "duplicate_charge",
        "intent": "Payment Issue",
        "department": "Accounts",
        "key_issue": "Duplicate payment charge",
        "policy": "Payment & Billing Policy",
        "severity": "High",
        "urgency": "High",
        "risk": "High",
        "priority": "Critical",
        "sentiment": "Negative",
        "issues": [
            "I was charged twice for the same order",
            "the same payment appears twice on my statement",
            "I see two charges for one purchase",
            "my account was debited twice for a single transaction",
        ],
        "responses": [
            "I confirmed the duplicate transaction and will have the additional charge reviewed for reversal.",
            "I understand the concern. The duplicate charge has been identified and I will track the correction.",
        ],
    },
    {
        "name": "failed_but_charged",
        "intent": "Payment Issue",
        "department": "Accounts",
        "key_issue": "Payment failed but amount was deducted",
        "policy": "Payment & Billing Policy",
        "severity": "High",
        "urgency": "High",
        "risk": "High",
        "priority": "Critical",
        "sentiment": "Negative",
        "issues": [
            "my payment failed but the money was deducted",
            "the order failed even though my bank account was charged",
            "the transaction showed failed but the amount was taken",
            "payment did not complete but I can see the debit in my account",
        ],
        "responses": [
            "I verified the failed transaction and will track the deducted amount through the payment reversal process.",
            "The payment did not complete successfully. I will ensure the deducted amount is monitored for reversal.",
        ],
    },
    {
        "name": "payment_pending",
        "intent": "Payment Issue",
        "department": "Accounts",
        "key_issue": "Payment transaction pending",
        "policy": "Payment & Billing Policy",
        "severity": "Medium",
        "urgency": "Medium",
        "risk": "Medium",
        "priority": "High",
        "sentiment": "Neutral",
        "issues": [
            "my payment has been pending for a long time",
            "the transaction still shows as pending",
            "my payment status has not changed from pending",
            "the amount is blocked but the payment is still pending",
        ],
        "responses": [
            "I checked the transaction status and will monitor the pending payment until the final status is confirmed.",
            "The payment is currently pending. I will track the transaction and make sure the final status is recorded.",
        ],
    },
    {
        "name": "incorrect_charge",
        "intent": "Billing Issue",
        "department": "Accounts",
        "key_issue": "Incorrect billing charge",
        "policy": "Payment & Billing Policy",
        "severity": "High",
        "urgency": "High",
        "risk": "High",
        "priority": "Critical",
        "sentiment": "Negative",
        "issues": [
            "I was charged an amount that I do not recognize",
            "the amount on my bill is incorrect",
            "my payment statement contains an unexpected charge",
            "I was billed more than the amount shown during checkout",
        ],
        "responses": [
            "I reviewed the billing concern and will verify the transaction details and correct any confirmed discrepancy.",
            "I understand the unexpected charge. I have recorded the billing issue for verification and correction.",
        ],
    },
    {
        "name": "payment_reversed",
        "intent": "Payment Issue",
        "department": "Accounts",
        "key_issue": "Payment reversed unexpectedly",
        "policy": "Payment & Billing Policy",
        "severity": "Medium",
        "urgency": "Medium",
        "risk": "Medium",
        "priority": "High",
        "sentiment": "Negative",
        "issues": [
            "my payment was reversed and I do not know why",
            "the transaction was completed and then reversed",
            "my payment initially succeeded but was later reversed",
            "the amount was returned after the payment and my order is affected",
        ],
        "responses": [
            "I checked the transaction status and recorded the reversal for payment review.",
            "The payment reversal has been identified. I will verify the transaction and guide the order through the correct payment status.",
        ],
    },

    # ================================================================
    # DELIVERY — 5
    # ================================================================

    {
        "name": "delivery_delayed",
        "intent": "Delivery Issue",
        "department": "Support",
        "key_issue": "Delivery delayed beyond expected date",
        "policy": "Delivery Delay Policy",
        "severity": "Medium",
        "urgency": "High",
        "risk": "Medium",
        "priority": "High",
        "sentiment": "Negative",
        "issues": [
            "my order is late and has not arrived on the expected date",
            "the delivery is delayed beyond the promised date",
            "my package has not arrived even though the delivery date has passed",
            "the expected delivery date has passed and I am still waiting",
        ],
        "responses": [
            "I checked the delivery status and will track the delayed shipment until the updated delivery status is confirmed.",
            "I understand the delay. I have recorded the issue and will follow up on the shipment status.",
        ],
    },
    {
        "name": "package_stuck",
        "intent": "Delivery Issue",
        "department": "Support",
        "key_issue": "Shipment stuck in transit",
        "policy": "Delivery Delay Policy",
        "severity": "Medium",
        "urgency": "Medium",
        "risk": "Medium",
        "priority": "High",
        "sentiment": "Negative",
        "issues": [
            "my package has been stuck at the same location",
            "the tracking information has not changed for several days",
            "my shipment appears to be stuck in transit",
            "the package has not moved since the last tracking update",
        ],
        "responses": [
            "I checked the shipment status and will monitor the tracking movement for the delayed package.",
            "The shipment appears to have a tracking delay. I have recorded the issue and will follow up on its movement.",
        ],
    },
    {
        "name": "delivered_missing",
        "intent": "Delivery Issue",
        "department": "Support",
        "key_issue": "Order marked delivered but customer did not receive it",
        "policy": "Missing Delivery Policy",
        "severity": "High",
        "urgency": "High",
        "risk": "High",
        "priority": "Critical",
        "sentiment": "Negative",
        "issues": [
            "my order says delivered but I never received it",
            "the tracking shows delivered but the package is missing",
            "my shipment was marked delivered even though nothing arrived",
            "the courier says delivered but I cannot find the package",
        ],
        "responses": [
            "I recorded the missing-delivery issue and will verify the delivery details and next steps.",
            "I understand that the package is not with you despite the delivered status. I will have the delivery record checked.",
        ],
    },
    {
        "name": "wrong_delivery",
        "intent": "Delivery Issue",
        "department": "Support",
        "key_issue": "Order delivered to wrong location",
        "policy": "Delivery Policy",
        "severity": "High",
        "urgency": "High",
        "risk": "High",
        "priority": "Critical",
        "sentiment": "Negative",
        "issues": [
            "my package appears to have been delivered to the wrong address",
            "the delivery location is incorrect",
            "my order was sent to a different address",
            "the shipment was delivered somewhere other than my address",
        ],
        "responses": [
            "I have recorded the incorrect-delivery issue and will verify the shipment destination and delivery details.",
            "I understand the delivery location is incorrect. I will have the shipment details reviewed for resolution.",
        ],
    },
    {
        "name": "missing_package",
        "intent": "Delivery Issue",
        "department": "Support",
        "key_issue": "Package missing during delivery",
        "policy": "Missing Delivery Policy",
        "severity": "High",
        "urgency": "High",
        "risk": "High",
        "priority": "Critical",
        "sentiment": "Negative",
        "issues": [
            "my package is missing and I cannot locate it",
            "the shipment has disappeared from the expected delivery route",
            "I have not received my package and there is no useful tracking update",
            "my order is missing and I need help locating it",
        ],
        "responses": [
            "I have recorded the missing-package issue and will verify the latest shipment information.",
            "I understand the package cannot be located. I will have the delivery status investigated.",
        ],
    },

    # ================================================================
    # PRODUCT / RETURN — 5
    # ================================================================

    {
        "name": "return_request",
        "intent": "Return",
        "department": "Support",
        "key_issue": "Customer requesting product return",
        "policy": "Return Policy",
        "severity": "Medium",
        "urgency": "Medium",
        "risk": "Low",
        "priority": "Normal",
        "sentiment": "Neutral",
        "issues": [
            "I want to return the product I received",
            "I would like to start a return for my order",
            "I need help returning an item",
            "I want to send the product back and need the return process",
        ],
        "responses": [
            "I have recorded your return request and will guide you through the applicable return process.",
            "Your return request has been noted. I will help you with the next required step.",
        ],
    },
    {
        "name": "damaged_product",
        "intent": "Product Issue",
        "department": "Support",
        "key_issue": "Product received damaged",
        "policy": "Damaged / Defective Product Policy",
        "severity": "High",
        "urgency": "High",
        "risk": "High",
        "priority": "Critical",
        "sentiment": "Negative",
        "issues": [
            "the product arrived damaged",
            "the item was broken when I opened the package",
            "my order arrived with visible damage",
            "the product has physical damage from delivery",
        ],
        "responses": [
            "I have recorded the damaged-product issue and will guide you through the replacement or return process.",
            "I am sorry the item arrived damaged. The issue has been recorded for the appropriate resolution.",
        ],
    },
    {
        "name": "defective_product",
        "intent": "Product Issue",
        "department": "Support",
        "key_issue": "Product is defective or not functioning",
        "policy": "Damaged / Defective Product Policy",
        "severity": "High",
        "urgency": "High",
        "risk": "Medium",
        "priority": "High",
        "sentiment": "Negative",
        "issues": [
            "the product is defective and does not work",
            "the item stopped working shortly after delivery",
            "the product has a manufacturing issue",
            "the device is not functioning as expected",
        ],
        "responses": [
            "I have recorded the product defect and will guide you through the eligible replacement or return option.",
            "I understand the product is not functioning correctly. The defect has been recorded for resolution.",
        ],
    },
    {
        "name": "wrong_product",
        "intent": "Product Issue",
        "department": "Support",
        "key_issue": "Wrong product received",
        "policy": "Return Policy",
        "severity": "High",
        "urgency": "High",
        "risk": "Medium",
        "priority": "High",
        "sentiment": "Negative",
        "issues": [
            "I received a different product from what I ordered",
            "the item delivered is not the product I purchased",
            "my package contains the wrong item",
            "I received the incorrect product and need a replacement",
        ],
        "responses": [
            "I recorded the incorrect-product issue and will guide you through the replacement or return process.",
            "I understand that the delivered item does not match your order. I will have the issue handled through the applicable return process.",
        ],
    },
    {
        "name": "replacement_request",
        "intent": "Replacement",
        "department": "Support",
        "key_issue": "Customer requesting product replacement",
        "policy": "Damaged / Defective Product Policy",
        "severity": "Medium",
        "urgency": "Medium",
        "risk": "Medium",
        "priority": "High",
        "sentiment": "Negative",
        "issues": [
            "I need a replacement for the product",
            "I would like to replace the defective item",
            "can you arrange a replacement for my order",
            "I want the damaged product replaced",
        ],
        "responses": [
            "I have recorded your replacement request and will guide it through the applicable replacement process.",
            "Your replacement request is noted. I will proceed with the appropriate resolution steps.",
        ],
    },

    # ================================================================
    # TECHNICAL — 5
    # ================================================================

    {
        "name": "app_crash",
        "intent": "Technical Issue",
        "department": "Support",
        "key_issue": "Application crashes during use",
        "policy": "Technical Support Policy",
        "severity": "Medium",
        "urgency": "Medium",
        "risk": "Medium",
        "priority": "High",
        "sentiment": "Negative",
        "issues": [
            "the app keeps crashing when I try to use it",
            "the application closes unexpectedly",
            "I cannot use the app because it crashes repeatedly",
            "the app crashes whenever I open the affected feature",
        ],
        "responses": [
            "I recorded the application issue and will guide you through the supported troubleshooting steps.",
            "I understand the app is crashing repeatedly. The technical issue has been recorded for troubleshooting.",
        ],
    },
    {
        "name": "login_failure",
        "intent": "Technical Issue",
        "department": "Support",
        "key_issue": "Customer unable to log in",
        "policy": "Account & Login Policy",
        "severity": "Medium",
        "urgency": "High",
        "risk": "Medium",
        "priority": "High",
        "sentiment": "Negative",
        "issues": [
            "I cannot log in to my account",
            "my login keeps failing even with the correct credentials",
            "I am unable to access my account",
            "the login page is not allowing me to sign in",
        ],
        "responses": [
            "I have recorded the login issue and will guide you through the supported account recovery steps.",
            "I understand you cannot access the account. I will help you follow the appropriate login recovery process.",
        ],
    },
    {
        "name": "checkout_error",
        "intent": "Technical Issue",
        "department": "Support",
        "key_issue": "Checkout fails due to technical error",
        "policy": "Technical Support Policy",
        "severity": "High",
        "urgency": "High",
        "risk": "Medium",
        "priority": "High",
        "sentiment": "Negative",
        "issues": [
            "checkout fails whenever I try to place the order",
            "I get an error during checkout",
            "the checkout page is not completing my order",
            "I cannot finish checkout because of a technical error",
        ],
        "responses": [
            "I recorded the checkout issue and will guide you through the supported troubleshooting steps.",
            "The checkout error has been recorded. I will help you proceed through the appropriate technical checks.",
        ],
    },
    {
        "name": "sync_failure",
        "intent": "Technical Issue",
        "department": "Support",
        "key_issue": "Data or order information not syncing",
        "policy": "Technical Support Policy",
        "severity": "Medium",
        "urgency": "Medium",
        "risk": "Medium",
        "priority": "High",
        "sentiment": "Negative",
        "issues": [
            "my account information is not syncing correctly",
            "the latest order information is not appearing",
            "the app is showing old information instead of the latest update",
            "my account data is not synchronizing",
        ],
        "responses": [
            "I recorded the synchronization issue and will guide you through the applicable troubleshooting steps.",
            "The sync problem has been noted. I will help verify the affected account information.",
        ],
    },
    {
        "name": "api_integration",
        "intent": "Technical Issue",
        "department": "Support",
        "key_issue": "API or integration error",
        "policy": "Technical Support Policy",
        "severity": "High",
        "urgency": "High",
        "risk": "Medium",
        "priority": "High",
        "sentiment": "Negative",
        "issues": [
            "our integration is returning an API error",
            "the API request is failing repeatedly",
            "our system cannot connect to the support integration",
            "the integration stopped working after the latest update",
        ],
        "responses": [
            "I recorded the integration issue and will guide the case through the supported technical investigation.",
            "The API integration problem has been recorded for technical review and troubleshooting.",
        ],
    },

    # ================================================================
    # ACCOUNT — 5
    # ================================================================

    {
        "name": "password_reset",
        "intent": "Account Issue",
        "department": "Support",
        "key_issue": "Customer needs password reset",
        "policy": "Account & Login Policy",
        "severity": "Low",
        "urgency": "Medium",
        "risk": "Low",
        "priority": "Normal",
        "sentiment": "Neutral",
        "issues": [
            "I forgot my password and need to reset it",
            "I cannot remember my account password",
            "I need help changing my forgotten password",
            "the password reset process is not working for me",
        ],
        "responses": [
            "I will guide you through the supported password reset process.",
            "I have recorded the password issue and will help you complete the account recovery steps.",
        ],
    },
    {
        "name": "account_locked",
        "intent": "Account Issue",
        "department": "Support",
        "key_issue": "Customer account locked",
        "policy": "Account & Login Policy",
        "severity": "Medium",
        "urgency": "High",
        "risk": "Medium",
        "priority": "High",
        "sentiment": "Negative",
        "issues": [
            "my account has been locked",
            "I am locked out after several login attempts",
            "the system has blocked access to my account",
            "I cannot access my account because it is locked",
        ],
        "responses": [
            "I have recorded the account-lock issue and will guide you through the supported account recovery process.",
            "I understand the account is locked. I will help you follow the appropriate recovery steps.",
        ],
    },
    {
        "name": "profile_update",
        "intent": "Account Issue",
        "department": "Support",
        "key_issue": "Customer needs profile information updated",
        "policy": "Account & Login Policy",
        "severity": "Low",
        "urgency": "Low",
        "risk": "Low",
        "priority": "Normal",
        "sentiment": "Neutral",
        "issues": [
            "I need to update my account information",
            "my profile details are outdated",
            "I want to change the information on my account",
            "I need help updating my registered details",
        ],
        "responses": [
            "I have recorded the profile update request and will guide you through the supported account update process.",
            "Your profile update request is noted. I will help with the applicable account steps.",
        ],
    },
    {
        "name": "verification_issue",
        "intent": "Account Issue",
        "department": "Support",
        "key_issue": "Account verification problem",
        "policy": "Account & Login Policy",
        "severity": "Medium",
        "urgency": "Medium",
        "risk": "Medium",
        "priority": "High",
        "sentiment": "Negative",
        "issues": [
            "I cannot complete account verification",
            "the verification step keeps failing",
            "my account verification is not going through",
            "I am unable to verify my account",
        ],
        "responses": [
            "I recorded the verification issue and will guide you through the supported verification steps.",
            "The verification problem has been noted and will be handled through the account support process.",
        ],
    },
    {
        "name": "account_access",
        "intent": "Account Issue",
        "department": "Support",
        "key_issue": "Customer cannot access account",
        "policy": "Account & Login Policy",
        "severity": "Medium",
        "urgency": "High",
        "risk": "Medium",
        "priority": "High",
        "sentiment": "Negative",
        "issues": [
            "I cannot access my account at all",
            "my account is inaccessible",
            "I am unable to get into my account",
            "I have lost access to my customer account",
        ],
        "responses": [
            "I have recorded the account-access issue and will guide you through the supported recovery process.",
            "I understand the access problem. I will help you follow the appropriate account recovery steps.",
        ],
    },

    # ================================================================
    # CANCELLATION — 5
    # ================================================================

    {
        "name": "order_cancellation",
        "intent": "Cancellation",
        "department": "Support",
        "key_issue": "Customer requesting order cancellation",
        "policy": "Cancellation Policy",
        "severity": "Medium",
        "urgency": "High",
        "risk": "Medium",
        "priority": "High",
        "sentiment": "Neutral",
        "issues": [
            "I want to cancel my order",
            "please help me cancel the order",
            "I no longer want the order and need to cancel it",
            "I need to stop my order before it is processed",
        ],
        "responses": [
            "I have recorded the cancellation request and will check the order status against the cancellation policy.",
            "Your cancellation request is noted. I will verify whether the order is still eligible for cancellation.",
        ],
    },
    {
        "name": "subscription_cancellation",
        "intent": "Cancellation",
        "department": "Support",
        "key_issue": "Customer requesting subscription cancellation",
        "policy": "Cancellation Policy",
        "severity": "Medium",
        "urgency": "Medium",
        "risk": "Medium",
        "priority": "High",
        "sentiment": "Neutral",
        "issues": [
            "I want to cancel my subscription",
            "please cancel my current subscription",
            "I no longer want the subscription service",
            "I need to stop my recurring subscription",
        ],
        "responses": [
            "I have recorded your subscription cancellation request and will guide it through the applicable cancellation process.",
            "Your cancellation request is noted and will be handled according to the subscription policy.",
        ],
    },
    {
        "name": "cancellation_confirmation",
        "intent": "Cancellation",
        "department": "Support",
        "key_issue": "Customer requesting cancellation confirmation",
        "policy": "Cancellation Policy",
        "severity": "Low",
        "urgency": "Medium",
        "risk": "Low",
        "priority": "Normal",
        "sentiment": "Neutral",
        "issues": [
            "I cancelled my order and need confirmation",
            "can you confirm whether my cancellation was successful",
            "I want to verify that the order has been cancelled",
            "please confirm the cancellation status",
        ],
        "responses": [
            "I checked the cancellation status and confirmed the current status for the order.",
            "I have verified the cancellation record and confirmed the status of the request.",
        ],
    },
    {
        "name": "cancellation_fee",
        "intent": "Cancellation",
        "department": "Support",
        "key_issue": "Customer asking about cancellation fee",
        "policy": "Cancellation Policy",
        "severity": "Medium",
        "urgency": "Medium",
        "risk": "Medium",
        "priority": "High",
        "sentiment": "Neutral",
        "issues": [
            "will I be charged a fee for cancelling my order",
            "I want to know whether cancellation has a fee",
            "is there any cancellation charge for this order",
            "please explain the fee associated with cancelling",
        ],
        "responses": [
            "I have recorded your question and will explain the applicable cancellation terms based on the order status.",
            "I will check the cancellation policy against the order details and clarify any applicable fee.",
        ],
    },
    {
        "name": "cancellation_refund",
        "intent": "Refund",
        "department": "Accounts",
        "key_issue": "Refund required after cancellation",
        "policy": "Cancellation Policy",
        "severity": "High",
        "urgency": "High",
        "risk": "High",
        "priority": "Critical",
        "sentiment": "Negative",
        "issues": [
            "I cancelled the order and need the payment refunded",
            "my cancellation was confirmed but I need my money returned",
            "the order is cancelled but the refund has not been processed",
            "I cancelled the purchase and am waiting for the refund",
        ],
        "responses": [
            "I confirmed the cancellation and will track the eligible refund through the Accounts process.",
            "The cancellation is recorded. I will verify and follow the associated refund status.",
        ],
    },

    # ================================================================
    # COMPLAINTS — 5
    # ================================================================

    {
        "name": "rude_agent",
        "intent": "Complaint",
        "department": "Support",
        "key_issue": "Complaint about rude agent behavior",
        "policy": "Bad Service / Agent Conduct Policy",
        "severity": "High",
        "urgency": "High",
        "risk": "High",
        "priority": "Critical",
        "sentiment": "Very Negative",
        "issues": [
            "the previous support agent was rude to me",
            "I was treated disrespectfully by an agent",
            "the agent's behavior was unacceptable",
            "I had a very unpleasant interaction with customer support",
        ],
        "responses": [
            "I am sorry about the experience. I have recorded your complaint and will ensure it is reviewed appropriately.",
            "I understand your concern regarding the interaction. Your complaint has been documented for review.",
        ],
    },
    {
        "name": "repeated_unresolved",
        "intent": "Complaint",
        "department": "Support",
        "key_issue": "Complaint repeatedly unresolved",
        "policy": "Customer Complaint Policy",
        "severity": "High",
        "urgency": "High",
        "risk": "High",
        "priority": "Critical",
        "sentiment": "Very Negative",
        "issues": [
            "I have contacted support multiple times and the issue is still unresolved",
            "this is my third time contacting support about the same problem",
            "I keep getting responses but nobody has solved the issue",
            "I have repeatedly reported this issue without a resolution",
        ],
        "responses": [
            "I understand the repeated inconvenience. I have consolidated the complaint and will ensure the unresolved issue receives focused attention.",
            "I am sorry that the issue remains unresolved. I have recorded the repeated-contact complaint for appropriate handling.",
        ],
    },
    {
        "name": "poor_support",
        "intent": "Complaint",
        "department": "Support",
        "key_issue": "Complaint about poor support experience",
        "policy": "Customer Complaint Policy",
        "severity": "High",
        "urgency": "High",
        "risk": "High",
        "priority": "Critical",
        "sentiment": "Very Negative",
        "issues": [
            "the support experience has been very poor",
            "I am unhappy with the support I received",
            "the customer service process has been disappointing",
            "I expected much better support for this issue",
        ],
        "responses": [
            "I am sorry the support experience did not meet expectations. I have documented the complaint and will ensure it is addressed.",
            "I understand your dissatisfaction. The service complaint has been recorded for review.",
        ],
    },
    {
        "name": "complaint_followup",
        "intent": "Complaint",
        "department": "Support",
        "key_issue": "Customer following up on unresolved complaint",
        "policy": "Customer Complaint Policy",
        "severity": "High",
        "urgency": "High",
        "risk": "High",
        "priority": "Critical",
        "sentiment": "Very Negative",
        "issues": [
            "I am following up because nobody responded to my complaint",
            "I submitted a complaint earlier and have not received a resolution",
            "I am still waiting for someone to address my complaint",
            "my previous complaint has not been followed up",
        ],
        "responses": [
            "I have reviewed the complaint follow-up and recorded the pending response for appropriate handling.",
            "I understand you are still waiting for an update. I have documented the follow-up and will ensure it is addressed.",
        ],
    },
    {
        "name": "service_dissatisfaction",
        "intent": "Complaint",
        "department": "Support",
        "key_issue": "Customer dissatisfied with service",
        "policy": "Bad Service / Agent Conduct Policy",
        "severity": "Medium",
        "urgency": "High",
        "risk": "High",
        "priority": "High",
        "sentiment": "Very Negative",
        "issues": [
            "I am dissatisfied with the way my issue was handled",
            "the service I received was not acceptable",
            "I am unhappy with the way support handled my request",
            "the support process has left me dissatisfied",
        ],
        "responses": [
            "I understand your dissatisfaction and have documented the service concern for review.",
            "I am sorry the experience was not satisfactory. Your concern has been recorded for appropriate handling.",
        ],
    },

    # ================================================================
    # ESCALATION / PRIORITY — 5
    # ================================================================

    {
        "name": "supervisor_request",
        "intent": "Escalation",
        "department": "Support",
        "key_issue": "Customer requesting supervisor escalation",
        "policy": "Escalation Policy",
        "severity": "High",
        "urgency": "High",
        "risk": "High",
        "priority": "Critical",
        "sentiment": "Negative",
        "issues": [
            "I want this issue escalated to a supervisor",
            "please connect me with a senior support person",
            "I need a supervisor to review this case",
            "I would like this complaint escalated",
        ],
        "responses": [
            "I have recorded your escalation request and routed the case for the appropriate review.",
            "Your supervisor request has been documented and the case has been escalated for review.",
        ],
    },
    {
        "name": "urgent_business_impact",
        "intent": "Escalation",
        "department": "Support",
        "key_issue": "Issue causing urgent business impact",
        "policy": "Priority Handling Policy",
        "severity": "Critical",
        "urgency": "Critical",
        "risk": "High",
        "priority": "Critical",
        "sentiment": "Very Negative",
        "issues": [
            "this issue is blocking an important business activity",
            "the problem is causing a major operational impact",
            "our business process is blocked because of this issue",
            "we need urgent support because this problem is affecting operations",
        ],
        "responses": [
            "I have marked the case as urgent and routed it for priority handling based on the reported business impact.",
            "I understand the operational impact. The case has been prioritized for appropriate review.",
        ],
    },
    {
        "name": "repeated_transfer",
        "intent": "Escalation",
        "department": "Support",
        "key_issue": "Customer repeatedly transferred without resolution",
        "policy": "Escalation Policy",
        "severity": "High",
        "urgency": "High",
        "risk": "High",
        "priority": "Critical",
        "sentiment": "Very Negative",
        "issues": [
            "I have been transferred between agents without getting a solution",
            "support keeps moving me to different teams",
            "I have spoken to several agents and the issue is still unresolved",
            "I keep getting transferred instead of receiving a solution",
        ],
        "responses": [
            "I am sorry for the repeated transfers. I have consolidated the issue and escalated it for focused handling.",
            "I understand the frustration caused by repeated transfers. The case has been documented for escalation.",
        ],
    },
    {
        "name": "policy_exception",
        "intent": "Escalation",
        "department": "Support",
        "key_issue": "Customer requesting policy exception",
        "policy": "Escalation Policy",
        "severity": "High",
        "urgency": "High",
        "risk": "High",
        "priority": "Critical",
        "sentiment": "Negative",
        "issues": [
            "I need an exception to the normal policy because of my situation",
            "can this case be reviewed as a policy exception",
            "my situation is unusual and I need special approval",
            "I need a supervisor to consider an exception",
        ],
        "responses": [
            "I have documented the exception request and routed it for the required review and approval.",
            "The policy-exception request has been recorded and escalated for appropriate review.",
        ],
    },
    {
        "name": "high_value_customer",
        "intent": "Priority Escalation",
        "department": "Support",
        "key_issue": "High-value customer requiring priority handling",
        "policy": "Priority Handling Policy",
        "severity": "High",
        "urgency": "High",
        "risk": "High",
        "priority": "Critical",
        "sentiment": "Negative",
        "issues": [
            "this issue is affecting an important customer relationship and needs priority attention",
            "we need this customer issue handled urgently",
            "this case has significant customer impact and requires quick attention",
            "please prioritize this issue because of its customer impact",
        ],
        "responses": [
            "I have recorded the customer impact and prioritized the case for appropriate handling.",
            "The case has been marked for priority attention based on the reported customer impact.",
        ],
    },

    # ================================================================
    # GENERAL — 5
    # ================================================================

    {
        "name": "order_status",
        "intent": "Order Status",
        "department": "Support",
        "key_issue": "Customer requesting order status",
        "policy": "Delivery Policy",
        "severity": "Low",
        "urgency": "Low",
        "risk": "Low",
        "priority": "Normal",
        "sentiment": "Neutral",
        "issues": [
            "I want to know the current status of my order",
            "can you tell me where my order is",
            "I need an update on my order",
            "please check the latest status of my purchase",
        ],
        "responses": [
            "I checked the available order information and provided the current status and next step.",
            "I have reviewed the order status and recorded the appropriate update.",
        ],
    },
    {
        "name": "product_information",
        "intent": "Product Inquiry",
        "department": "Support",
        "key_issue": "Customer requesting product information",
        "policy": "Customer Communication Guidelines",
        "severity": "Low",
        "urgency": "Low",
        "risk": "Low",
        "priority": "Normal",
        "sentiment": "Neutral",
        "issues": [
            "I need more information about a product",
            "can you explain the available product details",
            "I want to know more about the product before buying",
            "please provide more information about this item",
        ],
        "responses": [
            "I have provided the available product information and clarified the relevant details.",
            "I checked the product information and provided the requested details.",
        ],
    },
    {
        "name": "billing_receipt",
        "intent": "Billing Issue",
        "department": "Accounts",
        "key_issue": "Customer requesting billing receipt",
        "policy": "Payment & Billing Policy",
        "severity": "Low",
        "urgency": "Low",
        "risk": "Low",
        "priority": "Normal",
        "sentiment": "Neutral",
        "issues": [
            "I need a copy of my billing receipt",
            "please provide the receipt for my purchase",
            "I need the invoice or payment receipt for my order",
            "can you help me get the billing receipt",
        ],
        "responses": [
            "I have recorded the receipt request and provided the applicable billing information.",
            "The billing receipt request has been recorded and handled through the Accounts process.",
        ],
    },
    {
        "name": "address_update",
        "intent": "Account Issue",
        "department": "Support",
        "key_issue": "Customer requesting address update",
        "policy": "Customer Communication Guidelines",
        "severity": "Low",
        "urgency": "Medium",
        "risk": "Low",
        "priority": "Normal",
        "sentiment": "Neutral",
        "issues": [
            "I need to update my delivery address",
            "my address has changed and I want to update it",
            "please help me change the address on my account",
            "I need to correct my registered address",
        ],
        "responses": [
            "I have recorded the address-update request and will guide you through the applicable account process.",
            "Your address update request has been noted and will be handled through the supported account process.",
        ],
    },
    {
        "name": "general_inquiry",
        "intent": "General Support",
        "department": "Support",
        "key_issue": "General customer support inquiry",
        "policy": "Customer Communication Guidelines",
        "severity": "Low",
        "urgency": "Low",
        "risk": "Low",
        "priority": "Normal",
        "sentiment": "Neutral",
        "issues": [
            "I have a general question about my account and order",
            "I need some help understanding the support process",
            "I have a question and would like assistance",
            "can someone help me with a general service question",
        ],
        "responses": [
            "I have recorded the inquiry and provided the appropriate support information.",
            "I reviewed the request and provided the relevant guidance.",
        ],
    },
]


# ---------------------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------------------

if len(SCENARIOS) != 50:
    raise RuntimeError(
        f"Expected exactly 50 scenario families, found {len(SCENARIOS)}."
    )

if len(SCENARIOS) * VARIANTS_PER_SCENARIO != TOTAL_CASES:
    raise RuntimeError(
        "Scenario count does not produce exactly 500 cases."
    )


# ---------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------

def make_order_id(case_number: int) -> str:
    return f"ORD-{700000 + case_number}"


def make_customer_id(case_number: int) -> str:
    return f"CBR-CUST-{case_number}"


def make_customer_name(case_number: int) -> str:
    first_names = [
        "Aarav",
        "Ananya",
        "Rahul",
        "Priya",
        "Arjun",
        "Sneha",
        "Vikram",
        "Kavya",
        "Rohan",
        "Meera",
    ]

    last_names = [
        "Sharma",
        "Patel",
        "Reddy",
        "Iyer",
        "Nair",
        "Kumar",
        "Gupta",
        "Rao",
        "Singh",
        "Joshi",
    ]

    return (
        first_names[case_number % len(first_names)]
        + " "
        + last_names[(case_number // 10) % len(last_names)]
    )


def make_customer_message(
    scenario: dict,
    variant: int,
    case_number: int,
) -> str:
    issue = scenario["issues"][variant % len(scenario["issues"])]

    order_id = make_order_id(case_number)

    # Add deterministic realistic details without changing the core issue.
    details = [
        f"The related order is {order_id}.",
        f"My order reference is {order_id}.",
        f"This concerns order {order_id}.",
        f"The case is regarding {order_id}.",
        f"I need this checked for {order_id}.",
    ]

    detail = details[variant % len(details)]

    wrapper = MESSAGE_WRAPPERS[variant]

    return f"{wrapper.format(issue=issue)} {detail}"


def make_agent_response(
    scenario: dict,
    variant: int,
) -> str:
    return scenario["responses"][variant % len(scenario["responses"])]


def choose_sentiment(
    scenario: dict,
    variant: int,
) -> str:
    base = scenario["sentiment"]

    if base == "Negative" and variant in (3, 7):
        return "Very Negative"

    if base == "Neutral" and variant in (4, 8):
        return "Negative"

    return base


def choose_priority(
    scenario: dict,
    variant: int,
) -> str:
    priority = scenario["priority"]

    if priority == "Normal" and variant == 7:
        return "High"

    return priority


def build_routing_reason(scenario: dict) -> str:
    if scenario["department"] == "Accounts":
        return (
            "Financial/refund/payment/billing issue routed to Accounts "
            "for financial handling."
        )

    return "Non-financial customer support issue routed to Support."


def build_resolution_summary(
    scenario: dict,
    variant: int,
) -> str:
    return (
        f"Successfully resolved {scenario['key_issue'].lower()}. "
        f"Handled according to {scenario['policy']}. "
        f"Historical successful response variant {variant + 1}."
    )


# ---------------------------------------------------------------------
# SEED ONE CASE
# ---------------------------------------------------------------------

def seed_case(
    session,
    *,
    case_number: int,
    scenario: dict,
    variant: int,
    agent_id: int | None,
) -> None:

    case_id = f"CASE-{case_number}"
    customer_id = make_customer_id(case_number)

    # --------------------------------------------------------------
    # Idempotency: never overwrite an existing case.
    # --------------------------------------------------------------

    existing_case = get_case(session, case_id)

    if existing_case is not None:
        return

    # --------------------------------------------------------------
    # Historical timestamp
    # --------------------------------------------------------------

    days_ago = 10 + (case_number % 170)
    created_at = (
        datetime.now(timezone.utc)
        - timedelta(days=days_ago)
        - timedelta(hours=case_number % 12)
    )

    first_response_delay = 5 + (variant * 4)
    resolution_minutes = 35 + (variant * 13)

    customer_message_time = created_at + timedelta(minutes=1)

    agent_response_time = created_at + timedelta(
        minutes=first_response_delay
    )

    resolved_at = created_at + timedelta(
        minutes=resolution_minutes
    )

    # --------------------------------------------------------------
    # Customer
    # --------------------------------------------------------------

    customer_name = make_customer_name(case_number)
    customer_email = (
        f"cbr.customer.{case_number}@example.com"
    )

    try:
        create_customer(
            session,
            customer_id=customer_id,
            name=customer_name,
            email=customer_email,
            language="en",
            customer_tier=(
                "Premium"
                if variant in (2, 6)
                else "Standard"
            ),
        )
    except Exception:
        # If customer creation races with an existing customer,
        # continue only if the customer is already present.
        session.rollback()

    # --------------------------------------------------------------
    # Case fields
    # --------------------------------------------------------------

    sentiment = choose_sentiment(scenario, variant)
    priority = choose_priority(scenario, variant)

    customer_message = make_customer_message(
        scenario,
        variant,
        case_number,
    )

    agent_response = make_agent_response(
        scenario,
        variant,
    )

    resolution_summary = build_resolution_summary(
        scenario,
        variant,
    )

    routing_reason = build_routing_reason(scenario)

    # Approximately 15% of historical cases were escalated and
    # subsequently resolved successfully.
    was_escalated = (
        scenario["risk"] in ("High", "Very High")
        and variant in (2, 7)
    )

    escalation_reason = None

    if was_escalated:
        escalation_reason = (
            "Historical case required additional review because "
            "of elevated customer impact or escalation risk."
        )

    # --------------------------------------------------------------
    # Create case
    # --------------------------------------------------------------

    case = create_case(
        session,
        case_id=case_id,
        customer_id=customer_id,
        assigned_agent_id=agent_id,
        status="OPEN",
        department=scenario["department"],
        intent=scenario["intent"],
        sentiment=sentiment,
        urgency=scenario["urgency"],
        severity=scenario["severity"],
        escalation_risk=scenario["risk"],
        priority_label=priority,
        key_issue=scenario["key_issue"],
        routing_reason=routing_reason,
        resolution_status="IN_PROGRESS",
        ai_assisted=True,
        ai_recommendation_used=True,
        ai_recommendation_rejected=False,
        ai_escalation=False,
    )

    # Make the case genuinely historical.
    case.created_at = created_at
    session.commit()

    # --------------------------------------------------------------
    # First response time
    # --------------------------------------------------------------

    update_case(
        session,
        case_id,
        first_response_at=agent_response_time,
    )

    # --------------------------------------------------------------
    # Routing event
    # --------------------------------------------------------------

    create_case_event_once(
        session,
        case_id=case_id,
        actor_type="system",
        event_type="DEPARTMENT_ROUTED",
        actor_id=None,
        event_details={
            "department": scenario["department"],
            "reason": routing_reason,
        },
        timestamp=created_at + timedelta(minutes=2),
    )

    # --------------------------------------------------------------
    # Customer message
    # --------------------------------------------------------------

    add_message(
        session,
        case_id=case_id,
        sender_type="customer",
        sender_id=None,
        message=customer_message,
        language="en",
        timestamp=customer_message_time,
    )

    # --------------------------------------------------------------
    # AI analysis event
    # --------------------------------------------------------------

    create_case_event_once(
        session,
        case_id=case_id,
        actor_type="ai",
        event_type="AI_ANALYSIS",
        actor_id=None,
        event_details={
            "intent": scenario["intent"],
            "sentiment": sentiment,
            "urgency": scenario["urgency"],
            "severity": scenario["severity"],
            "escalation_risk": scenario["risk"],
            "priority_label": priority,
            "key_issue": scenario["key_issue"],
            "department": scenario["department"],
            "routing_reason": routing_reason,
            "related_policy": scenario["policy"],
            "historical_seed": True,
        },
        timestamp=created_at + timedelta(minutes=3),
    )

    # --------------------------------------------------------------
    # Optional escalation event
    # --------------------------------------------------------------

    if was_escalated:
        update_case(
            session,
            case_id,
            escalation_status="ESCALATED",
            escalation_reason=escalation_reason,
            escalated_at=created_at + timedelta(minutes=8),
            ai_escalation=False,
        )

        create_case_event_once(
            session,
            case_id=case_id,
            actor_type="human_agent",
            event_type="CASE_ESCALATED",
            actor_id=agent_id,
            event_details={
                "reason": escalation_reason,
                "historical_seed": True,
            },
            timestamp=created_at + timedelta(minutes=8),
        )

    # --------------------------------------------------------------
    # Successful agent response
    # --------------------------------------------------------------

    add_message(
        session,
        case_id=case_id,
        sender_type="human_agent",
        sender_id=agent_id,
        message=agent_response,
        language="en",
        timestamp=agent_response_time,
    )

    # --------------------------------------------------------------
    # AI recommendation used
    # --------------------------------------------------------------

    create_case_event_once(
        session,
        case_id=case_id,
        actor_type="human_agent",
        event_type="AI_RECOMMENDATION_USED",
        actor_id=agent_id,
        event_details={
            "recommendation": agent_response,
            "source": "historical_successful_case",
            "historical_seed": True,
        },
        timestamp=agent_response_time,
    )

    # --------------------------------------------------------------
    # Resolve
    # --------------------------------------------------------------

    resolved_case = resolve_case(
        session,
        case_id,
        resolution_summary=resolution_summary,
    )

    if resolved_case is not None:
        # Preserve realistic historical resolution timestamp.
        resolved_case.resolved_at = resolved_at
        resolved_case.resolution_time = (
            resolved_at - created_at
        )

        resolved_case.updated_at = resolved_at

        if was_escalated:
            resolved_case.escalation_status = "RESOLVED"

        session.commit()

    # --------------------------------------------------------------
    # Resolution event
    # --------------------------------------------------------------

    create_case_event_once(
        session,
        case_id=case_id,
        actor_type="human_agent",
        event_type="CASE_RESOLVED",
        actor_id=agent_id,
        event_details={
            "resolution_summary": resolution_summary,
            "successfully_resolved": True,
            "historical_seed": True,
        },
        timestamp=resolved_at,
    )


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------

def main() -> None:

    print("=" * 70)
    print("CBR HISTORICAL CASE SEED")
    print("=" * 70)

    print("\nChecking database schema...")
    ensure_auth_schema()

    # --------------------------------------------------------------
    # Find an existing human agent, if available.
    # --------------------------------------------------------------

    agent_id = None

    with SessionLocal() as session:

        agent = session.scalar(
            select(User)
            .where(User.role == "human_agent")
            .where(User.is_active.is_(True))
            .order_by(User.user_id)
        )

        if agent is not None:
            agent_id = agent.user_id
            print(
                f"Using existing human agent: "
                f"{agent.email} (ID {agent.user_id})"
            )
        else:
            print(
                "No active human agent found. "
                "Historical cases will remain unassigned."
            )

    # --------------------------------------------------------------
    # Generate 500 cases.
    # --------------------------------------------------------------

    created = 0
    skipped = 0

    with SessionLocal() as session:

        for scenario_index, scenario in enumerate(SCENARIOS):

            for variant in range(VARIANTS_PER_SCENARIO):

                case_number = (
                    START_CASE_NUMBER
                    + scenario_index * VARIANTS_PER_SCENARIO
                    + variant
                )

                case_id = f"CASE-{case_number}"

                if get_case(session, case_id) is not None:
                    skipped += 1
                    continue

                seed_case(
                    session,
                    case_number=case_number,
                    scenario=scenario,
                    variant=variant,
                    agent_id=agent_id,
                )

                created += 1

                if created % 25 == 0:
                    print(
                        f"Progress: {created}/{TOTAL_CASES} "
                        "new historical cases created..."
                    )

    # --------------------------------------------------------------
    # Final result
    # --------------------------------------------------------------

    print("\n" + "=" * 70)
    print("SEED COMPLETE")
    print("=" * 70)

    print(f"Scenario families : {len(SCENARIOS)}")
    print(f"Variants/family   : {VARIANTS_PER_SCENARIO}")
    print(f"Expected cases    : {TOTAL_CASES}")
    print(f"Created           : {created}")
    print(f"Skipped existing  : {skipped}")
    print("=" * 70)

    print(
        "\nThese cases are resolved historical cases and include:"
        "\n  - customer records"
        "\n  - persisted customer messages"
        "\n  - persisted agent responses"
        "\n  - AI analysis events"
        "\n  - department routing"
        "\n  - AI recommendation-used events"
        "\n  - resolution events"
        "\n  - realistic historical timestamps"
        "\n  - policy references"
        "\n\nNo Gemini/LLM calls were made during seeding."
    )


if __name__ == "__main__":
    main()