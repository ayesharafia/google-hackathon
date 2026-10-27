# AI foundation and MCP connection

PhysiCore exposes a versioned action catalog for saved project work. A compatible MCP host can discover and call the same actions through the stdio adapter; PhysiCore does not choose or host a language model. The first release covers project inspection, selected draft edits, revisions, studies, comparison, exact result export and hosted job actions. Discover current availability in the workbench or catalog. Geometry, source authoring, additional input groups and application development are future adapters. The local workbench also includes a Groq chat using these same actions.

## Connect

1. Start an authenticated PhysiCore workspace and open a saved project. Public demo mode does not issue AI credentials.
2. In **AI client access and action review**, name the connection and choose its lifetime. The default permits reads and proposals. Enable reviewed changes and studies only when needed. Create the connection and copy the credential once.
3. Store the credential in a private file owned by the current user with permissions `600` on POSIX systems, or use a protected environment variable. Never commit it or share it in conversation. The credential is distinct from the workspace login and is limited to one project, parent authority, expiry and call count. Revoke it in the workbench when finished.
4. Install the application with its optional MCP extra (`physimesh-drone[mcp]`), or use the repository's `requirements-mcp.lock` with hash verification in the intended environment. Configure the MCP host to run `python -m physimesh.agent.mcp`, with `PHYSICORE_API_URL` set to the authenticated application origin and `PHYSICORE_AGENT_TOKEN_FILE` set to the private file. The workbench can download a configuration template without the credential. Alternatively supply `PHYSICORE_AGENT_TOKEN` through the host's protected environment. File permission checks require POSIX; use protected environment storage on other systems.

The adapter accepts HTTPS origins or loopback HTTP, rejects redirects and does not accept arbitrary file paths or URLs from model calls. It speaks stdio locally; this release does not expose a hosted MCP transport. The MCP host and its model provider are separate products and may have their own configuration and costs.

## Review and results

The client discovers tools and prepares an action. A project user reviews the exact change or operation in the workbench and approves or rejects it. A client cannot approve its own request. For retries reuse the same request ID and identical arguments; a completed call returns its recorded receipt. A change is applied only to the matching saved draft version, and undo is available only while the applied version is still current. Save or discard other unsaved browser edits before applying.

Receipts record what the system actually did. If an operation was interrupted after admission, its outcome may be **uncertain**; inspect retained studies or job history before deciding what to do next. Hosted jobs report their recorded state rather than an estimated completion time. Exact exports remain subject to project permissions. Credential and parent-session authority are checked on each call.

This interface does not certify a simulation or aircraft. Existing scientific evidence and qualified human review requirements still apply.

## Groq chat

Open an authenticated saved project over HTTPS or loopback, enter a Groq API key and a tool-capable model ID in **Ask PhysiCore**, then send a message. The key is held in the current page and sent to the application for each run; clear it with the button or by switching project, signing out or closing the page. Prompts and relevant action results are sent to Groq and usage may be charged by Groq. Do not enter the key into the conversation itself.

The assistant can use only currently available actions and current project permissions. Save or discard unsaved edits before approving changes. The workbench shows the proposed values and exact review details; approve or reject, then select Continue. The actual receipt is retained independently of the model's explanation. Stop requests prevent subsequent tool calls after a current provider call or action returns; that in-flight work may complete.

Conversation state is held in the browser as a signed, project-bound token, expires after 15 minutes and is lost on reload. A server restart invalidates it. The signing key and stop coordination are process-local; this implementation has not been qualified for multi-worker or load-balanced hosting. Provider requests have a 15-second socket timeout and the coordinator checks a 60-second deadline between steps, not a guarantee that an in-flight operation stops at that exact time. Live Groq behavior has not been tested.
