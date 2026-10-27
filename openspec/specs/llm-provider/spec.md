# llm-provider Specification

## Purpose

Generates structured JSON documents through an external LLM Provider. Model and provider are selected by configuration, so the callers (Script generation now, Goal Analysis and Programs later) stay provider-agnostic.

## Requirements

### Requirement: Structured generation
The system SHALL send a system prompt, a user prompt and a target JSON schema to the configured LLM Provider. It SHALL return the parsed document only if the document validates against the schema. Output that cannot be parsed or does not validate SHALL be reported as an invalid-output error that includes the raw output.

#### Scenario: Valid structured output
- **WHEN** the provider returns JSON that matches the target schema
- **THEN** the caller receives the parsed document

#### Scenario: Output does not match schema
- **WHEN** the provider returns JSON that is missing a required field of the target schema
- **THEN** an invalid-output error is raised that names the schema violation and carries the raw output

### Requirement: Model selection by configuration
The provider and model SHALL be selected by one configured model identifier that names the provider, e.g. `anthropic/claude-opus-5-5` or `openai/<model>`. The default SHALL be `litellm_proxy/glm` (the `glm` model on a self-hosted LiteLLM proxy). A separate model identifier MAY be configured for the Suggestion Review and SHALL default to the generation model.

#### Scenario: Switching provider
- **WHEN** the configured model is changed from an Anthropic model to an OpenAI model
- **THEN** generation calls go to OpenAI without any code change

#### Scenario: LiteLLM proxy without base URL
- **WHEN** the configured model is a `litellm_proxy/` model and `LITELLM_PROXY_API_BASE` is not set
- **THEN** generation fails before any request with an error naming `LITELLM_PROXY_API_BASE`, and no request is sent to any other provider

#### Scenario: Review model defaults to generation model
- **WHEN** no review model is configured
- **THEN** the Suggestion Review uses the generation model

### Requirement: Credentials from environment only
API keys SHALL be read from the environment and SHALL NOT be accepted from the config file. Keys SHALL never appear in logs, error messages, generation records or CLI output.

#### Scenario: Missing API key
- **WHEN** generation starts and no API key for the configured provider is set
- **THEN** it fails before any request with an error naming the provider and the expected environment variable

#### Scenario: API key in config file
- **WHEN** `anchor.toml` contains an API key under `[llm]`
- **THEN** loading the configuration fails with an error telling the user to set the key in the environment instead

### Requirement: Transient error handling
Rate limits, timeouts, connection errors and server errors (HTTP 5xx) SHALL be retried with exponential backoff up to a configured number of retries. Client errors (HTTP 4xx other than 429) SHALL NOT be retried. A final failure SHALL name the provider, the model and the cause.

#### Scenario: Server error then success
- **WHEN** the provider answers once with HTTP 500 and then with a valid response
- **THEN** the call succeeds and the caller receives the parsed document

#### Scenario: Invalid request is not retried
- **WHEN** the provider answers with HTTP 400
- **THEN** the call fails after one request with an error naming provider, model and the provider's message

### Requirement: Refusal handling
A response in which the provider declines the request SHALL be reported as a refusal error, distinct from invalid output. It SHALL NOT be passed on as a document.

#### Scenario: Provider declines
- **WHEN** the provider ends the response with a refusal
- **THEN** a refusal error is raised and no document is returned

### Requirement: No sampling parameters
Requests SHALL NOT send sampling parameters (`temperature`, `top_p`, `top_k`), since current models reject them. Variation between generations SHALL come from the prompt and the request content alone.

#### Scenario: Request without sampling parameters
- **WHEN** any structured generation request is sent
- **THEN** it contains none of `temperature`, `top_p`, `top_k`

### Requirement: Usage reporting
Every call SHALL report the model actually used, the input and output token counts and the duration. Callers can record this data.

#### Scenario: Usage on success
- **WHEN** a structured generation call succeeds
- **THEN** its result carries the model, input tokens, output tokens and duration
