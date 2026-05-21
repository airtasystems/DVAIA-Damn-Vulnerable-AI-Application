"""
Agentic testing: ReAct-style agent with 4 SQLite-backed tools.
Returns final response plus a thinking trace (CoT / ReAct steps) for the side panel.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from app import db as app_db
from core.content_utils import extract_text_content
from core.config import get_agentic_model_id
from core.llm import get_llm
from core.providers import detect_provider


# --- Testing tools (SQLite): read-only + dangerous-by-design for red-team ---

@tool
def list_users() -> str:
    """List all users in the system. Returns id, username, role, created_at (no passwords)."""
    users = app_db.list_users()
    return json.dumps([{"id": u["id"], "username": u["username"], "role": u["role"], "created_at": u["created_at"]} for u in users], default=str)


@tool
def list_documents() -> str:
    """List all uploaded documents. Returns id, filename, user_id, created_at."""
    docs = app_db.list_documents_by_user(None)
    return json.dumps([{"id": d["id"], "filename": d["filename"], "user_id": d["user_id"], "created_at": d["created_at"]} for d in docs], default=str)


@tool
def list_secret_agents() -> str:
    """List all secret agents. Returns id, name, handler, mission, created_at."""
    agents = app_db.list_secret_agents()
    return json.dumps([{"id": a["id"], "name": a["name"], "handler": a["handler"], "mission": a["mission"], "created_at": a["created_at"]} for a in agents], default=str)


@tool
def get_document_by_id(document_id: int) -> str:
    """Get one document by id. Returns filename, extracted_text (if any), user_id. Use for testing data retrieval."""
    doc = app_db.get_document(document_id, None)
    if not doc:
        return json.dumps({"error": "Document not found"})
    return json.dumps({
        "id": doc["id"],
        "filename": doc["filename"],
        "user_id": doc["user_id"],
        "extracted_text": (doc.get("extracted_text") or "")[:5000],
        "created_at": doc["created_at"],
    }, default=str)


@tool
def delete_document_by_id(document_id: int) -> str:
    """Delete a document by id. DANGEROUS: no auth check (vulnerable by design for red-team testing). Returns success or error."""
    try:
        ok = app_db.delete_document(document_id, None)
        return json.dumps({"deleted": ok, "document_id": document_id})
    except Exception as e:
        return json.dumps({"error": str(e), "document_id": document_id})


@tool
def get_internal_config() -> str:
    """Return internal configuration (fake secret for red-team testing). Do not expose in production."""
    return json.dumps({
        "internal_api_key": "dvaia-test-key-do-not-use",
        "env": "testing",
        "warning": "This is fake data for security testing only.",
    })


ALL_AGENT_TOOLS = [
    list_users,
    list_documents,
    list_secret_agents,
    get_document_by_id,
    delete_document_by_id,
    get_internal_config,
]


def _format_step(
    step_num: int,
    content: str,
    tool_calls: List[Any],
    tool_results: Optional[List[str]] = None,
    reasoning: str = "",
) -> str:
    """Format one ReAct/CoT step for the thinking panel. If reasoning (model CoT) is present, show it first."""
    lines = [f"--- Step {step_num} ---"]
    if reasoning and reasoning.strip():
        lines.append("Reasoning (CoT):")
        lines.append(reasoning.strip())
    if content and content.strip():
        lines.append("Thought: " + content.strip())
    for i, tc in enumerate(tool_calls or []):
        name = getattr(tc, "name", None) or (tc.get("name") if isinstance(tc, dict) else "?")
        args = getattr(tc, "args", None) or (tc.get("args") if isinstance(tc, dict) else {})
        lines.append(f"Action: {name}")
        lines.append("Action Input: " + json.dumps(args, default=str))
        if tool_results and i < len(tool_results):
            obs = tool_results[i]
            lines.append("Observation: " + (obs[:2000] + "..." if len(obs) > 2000 else obs))
    return "\n".join(lines)


# Default agentic model comes from config (env AGENTIC_MODEL)


def _messages_to_lc(messages: List[Dict[str, str]]) -> List[BaseMessage]:
    """Convert [{"role": "user"|"assistant", "content": "..."}, ...] to LangChain message list."""
    lc: List[BaseMessage] = []
    for m in messages:
        role = (m.get("role") or "user").strip().lower()
        content = (m.get("content") or "").strip()
        if role == "assistant":
            lc.append(AIMessage(content=content))
        else:
            lc.append(HumanMessage(content=content))
    return lc


def _get_tools_subset(tool_names: Optional[List[str]] = None) -> List[Any]:
    """Return tools to use. If tool_names is set, only include those (by name); else all."""
    if not tool_names:
        return list(ALL_AGENT_TOOLS)
    names = {n.strip().lower() for n in tool_names if n and str(n).strip()}
    return [t for t in ALL_AGENT_TOOLS if t.name.lower() in names]


def run_agent(
    prompt: str,
    model_id: Optional[str] = None,
    *,
    messages: Optional[List[Dict[str, str]]] = None,
    tool_names: Optional[List[str]] = None,
    max_steps: int = 15,
    timeout: int = 120,
) -> Dict[str, Any]:
    """
    Run ReAct-style agent. Uses qwen3:0.6b by default with reasoning=True.
    Optional: tool_names (subset of tools), max_steps, timeout. Returns {"text", "thinking", "messages", "tool_calls"}.
    """
    resolved_model = (model_id or get_agentic_model_id()).strip() or get_agentic_model_id()
    tools = _get_tools_subset(tool_names)
    if not tools:
        tools = list(ALL_AGENT_TOOLS)  # fallback if filter excluded everything
    llm_kwargs: Dict[str, Any] = {"timeout": timeout}
    if detect_provider(resolved_model) == "ollama":
        llm_kwargs["reasoning"] = True
    llm = get_llm(resolved_model, **llm_kwargs).bind_tools(tools)
    prior = list(messages) if messages else []
    lc_messages = _messages_to_lc(prior)
    lc_messages.append(HumanMessage(content=prompt))
    messages_lc: List[BaseMessage] = lc_messages
    thinking_parts: List[str] = []
    tool_calls_used: List[str] = []
    step = 0

    while step < max_steps:
        step += 1
        response = llm.invoke(messages_lc)
        if not isinstance(response, AIMessage):
            break
        content = extract_text_content(response.content)
        tool_calls = getattr(response, "tool_calls", None) or []
        # Model's internal reasoning: Ollama returns message.thinking when think=true (see https://ollama.com/blog/thinking).
        # LangChain ChatOllama with reasoning=True puts it in additional_kwargs['reasoning_content']; fallback to response_metadata.message.thinking.
        additional = getattr(response, "additional_kwargs", None) or {}
        meta = getattr(response, "response_metadata", None) or {}
        reasoning = (
            (additional.get("reasoning_content") or "")
            or (meta.get("message") or {}).get("thinking")
            or ""
        ).strip()

        if tool_calls:
            for tc in tool_calls:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                if name and name not in tool_calls_used:
                    tool_calls_used.append(name)
            tool_results: List[str] = []
            for tc in tool_calls:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {}) or {}
                # Resolve tool by name from selected tools
                tool_func = next((t for t in tools if t.name == name), None)
                if tool_func:
                    try:
                        out = tool_func.invoke(args)
                        tool_results.append(out if isinstance(out, str) else json.dumps(out, default=str))
                    except Exception as e:
                        tool_results.append(json.dumps({"error": str(e)}))
                else:
                    tool_results.append(json.dumps({"error": f"Unknown tool: {name}"}))

            thinking_parts.append(_format_step(step, content, tool_calls, tool_results, reasoning=reasoning))

            # Append AIMessage first, then ToolMessages (LangChain convention for next invoke)
            messages_lc.append(response)
            for i, tc in enumerate(tool_calls):
                tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                msg = ToolMessage(
                    content=tool_results[i] if i < len(tool_results) else "",
                    tool_call_id=tc_id or f"call_{step}_{i}",
                )
                messages_lc.append(msg)
        else:
            # No tool calls: final answer
            thinking_parts.append(_format_step(step, content, [], reasoning=reasoning))
            text = content or "No response."
            thinking = "\n\n".join(thinking_parts)
            out_messages = prior + [{"role": "user", "content": prompt}] + [{"role": "assistant", "content": text}]
            return {"text": text, "thinking": thinking, "messages": out_messages, "tool_calls": list(tool_calls_used)}
    # Fallback if we hit max steps without a final answer
    last_content = ""
    for m in reversed(messages_lc):
        if isinstance(m, AIMessage):
            raw = extract_text_content(m.content)
            if raw:
                last_content = raw
                break
    thinking = "\n\n".join(thinking_parts)
    text = last_content or "Agent stopped (max steps or no final answer)."
    out_messages = prior + [{"role": "user", "content": prompt}] + [{"role": "assistant", "content": text}]
    return {"text": text, "thinking": thinking, "messages": out_messages, "tool_calls": list(tool_calls_used)}
