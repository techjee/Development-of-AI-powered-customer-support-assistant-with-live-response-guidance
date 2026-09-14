# AI-Powered Customer Support Assistant with Live Response Guidance

An AI-powered customer support platform that helps human support agents analyze customer issues, retrieve relevant historical cases and company policies, generate contextual responses, and receive real-time coaching before responding to customers.

The system combines **NLP, Large Language Models, Case-Based Reasoning (CBR), Policy RAG, PostgreSQL, and agent coaching** into a single support workflow.

---

## Overview

Customer support agents often need to make decisions quickly while handling multiple conversations simultaneously.

A customer message may require the agent to understand:

- What the customer is asking about
- Whether the customer is frustrated or satisfied
- What type of issue is involved
- Whether the issue should be routed to another department
- How similar cases were resolved previously
- Which company policy applies
- How the agent should respond appropriately

This project provides an AI-assisted workflow for these tasks.

Instead of simply generating an answer using an LLM, the system combines:

**Customer Message → NLP Analysis → Historical Case Retrieval → Policy Retrieval → AI Reasoning → Suggested Response → Agent Coaching → Human Decision**

The final response is always reviewed and controlled by the human agent.

---

# Key Features

## 1. AI Customer Message Analysis

The system analyzes incoming customer messages to identify important support signals.

The analysis includes:

- Customer sentiment
- Customer intent
- Key issue
- Urgency
- Escalation risk
- Priority
- Recommended next step
- Department routing

The NLP layer uses **Hugging Face Transformers** for sentiment and intent classification where the required model assets are available.

The LLM is then used for contextual reasoning and response synthesis rather than being the sole source of basic sentiment/intent classification.

---

## 2. Hugging Face NLP

The project incorporates the NLP approach used in the original project prototype.

### Sentiment Analysis

A Hugging Face `sentiment-analysis` pipeline is used to classify customer sentiment.

The application normalizes sentiment into:

- Positive
- Neutral
- Negative

For example:

```text
Customer:
"I'm extremely disappointed. My refund has been delayed for days."

Sentiment:
Negative
