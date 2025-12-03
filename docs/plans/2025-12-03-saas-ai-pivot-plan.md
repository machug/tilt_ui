# BrewSignal Cloud & AI Pivot Plan (2025-12-03)

## Vision

Transform BrewSignal from a local, hardware-dependent application into a multi-tenant Software as a Service (SaaS) platform, complemented by advanced AI-driven brewing assistance. The core value proposition is enabling reliable remote monitoring, advanced alerting, historical data retention, and intelligent insights for homebrewers, overcoming the complexities of local network configurations.

## Architecture & Product Split

1.  **Edge Agent (Open Source / Free)**
    *   A lightweight, headless application based on a stripped-down version of the current `backend`.
    *   Runs on local hardware (e.g., Raspberry Pi).
    *   Primary function: Scan for local devices (Tilt, iSpindel, etc.) and securely push data to the BrewSignal Cloud API.
    *   Configuration: Simple WiFi setup and API key entry.
    *   **Key change:** Replaces local database interaction with secure cloud API calls for data ingestion.

2.  **SaaS Platform (Commercial Offering)**
    *   A cloud-hosted application comprising the `frontend` and a multi-tenant `backend`.
    *   Provides data storage, user management, authentication, advanced visualizations, alerting, and AI features.
    *   **Key change:** The `backend` will be redesigned for multi-tenancy, requiring authentication and authorization for all data access, and linking all resources (batches, devices, recipes) to specific user accounts.

## Data Transformation (Multi-Tenancy)

*   **User/Organization Model:** Introduce a central `User` or `Organization` model to which all brewing data will be associated.
*   **Data Isolation:** All existing database models (`Tilt`, `Device`, `Reading`, `Batch`, `Recipe`, `AmbientReading`) will require a `user_id` foreign key to ensure strict data segregation between tenants.
*   **Device Claiming:** Implement a mechanism for users to "claim" their physical devices to their cloud account.

## Revenue & Value Propositions (SaaS Monetization)

To justify a subscription model, the SaaS platform will offer:
*   **Effortless Remote Monitoring:** Access to fermentation data from anywhere without complex network setup.
*   **Reliable, Advanced Alerts:** SMS, push, or email notifications based on real-time data and AI-driven anomaly detection (e.g., stuck fermentation, temperature excursions).
*   **Permanent Historical Data:** Long-term storage and advanced analysis of brew logs.
*   **Third-Party Integrations:** Seamless syncing with popular brewing software (e.g., Brewfather, Brewer's Friend).

## AI Assistant Integration (Premium Feature)

The "AI Brewing Assistant" will be a key differentiator for premium tiers, leveraging real-time fermentation data for contextualized insights.

*   **Approach:** Initially use paid, state-of-the-art LLM APIs (e.g., Gemini 1.5 Pro, GPT-4o) due to superior quality, reasoning capabilities, and cost-effectiveness at initial scale. Self-hosting open-source models will be considered only after significant user adoption (e.g., 10,000+ users).
*   **Focus:** Context-aware analysis rather than generic chatbot responses.

### Proposed AI Features:

1.  **Recipe Generator:**
    *   Users describe desired beer characteristics (e.g., "Hazy IPA, low ABV, fruity").
    *   AI generates a complete, valid BeerXML recipe, directly importable into the user's recipe library.
2.  **Anomaly Watchdog / Troubleshooting:**
    *   AI analyzes sensor data (temperature, gravity, recent trends) in the context of the active recipe.
    *   Provides proactive alerts and diagnoses issues (e.g., "temperature drop caused yeast dormancy, recommend raising temp").
3.  **Predictive Fermentation Analysis:**
    *   Estimates fermentation finish dates, diacetyl rest timing, or other key milestones based on current trends and historical data.

## Implementation Roadmap (High-Level)

1.  **Phase 1: API Gateway Development:**
    *   Create a secure, authenticated `/api/v1/ingest` endpoint in the `backend` to receive data from edge agents.
2.  **Phase 2: Authentication & Multi-Tenancy Backend:**
    *   Implement user management and integrate an authentication provider.
    *   Refactor database models and API endpoints to enforce `user_id` ownership for all data.
3.  **Phase 3: Edge Agent Creation:**
    *   Develop a separate, lightweight client from the current `backend` that runs on local devices and pushes data to the new SaaS API.
    *   Implement simplified device configuration for DIY hardware (e.g., iSpindel relay via Edge Agent).
4.  **Phase 4: Core SaaS UI & Features:**
    *   Adapt the `frontend` to consume data from the multi-tenant cloud API.
    *   Implement enhanced dashboard, alerting, and historical data views.
5.  **Phase 5: AI Integration:**
    *   Build features for recipe generation, anomaly detection, and predictive analytics using LLM APIs.
6.  **Phase 6: Billing & Subscription Management:**
    *   Integrate a payment gateway (e.g., Stripe) to support free and premium tiers.
