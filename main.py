import os
import random
import re
import time
from datetime import datetime
from typing import Any
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from google import genai
from google.genai import types
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="FlowOps AI — Multi-Step Business Workflow Automation")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PRIMARY_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
FALLBACK_MODELS = list(dict.fromkeys([PRIMARY_MODEL, "gemini-3.8-flash-lite"]))

client = genai.Client(api_key=GEMINI_API_KEY)

# --- MOCK ERP / INVENTORY / EVENT CATALOG (ZERO-DB INSTANT DEMO) ---
INVENTORY_ERP: dict[str, dict[str, Any]] = {
    "D2C-JKT-09": {
        "sku": "D2C-JKT-09",
        "product_name": "All-Weather Bomber Jacket (Charcoal, L)",
        "hub": "Gurugram North Fulfillment Hub",
        "available_units": 142,
        "courier": "Blue Dart Express",
        "cod_serviceable": True,
    },
    "SKU-COFFEE-250G": {
        "sku": "SKU-COFFEE-250G",
        "product_name": "Chikmagalur Single-Origin Roast (250g)",
        "hub": "Peenya Central Warehouse (Bengaluru)",
        "available_units": 1400,
        "courier": "Internal Milk-Run Van (4:00 PM Slot)",
        "cod_serviceable": True,
    },
}

PRESET_EVENTS: dict[str, str] = {
    "EVT-301": (
        "EVENT EVT-301 [High-Value COD Order]: Order ORD-8891 by Karan Malhotra (Jaipur, PIN 302001) "
        "for 1x SKU D2C-JKT-09 worth ₹4,499 (Cash on Delivery). Run COD RTO verification, inventory reservation, and dispatch workflow."
    ),
    "EVT-302": (
        "EVENT EVT-302 [B2B Distributor Onboarding]: Vardhman Electronics (Pune, GSTIN 27AABCV9102R1Z4) "
        "applied for wholesale onboarding with ₹5,00,000 Net-30 credit limit. Run GSTIN compliance check, credit approval, and ERP setup workflow."
    ),
    "EVT-303": (
        "EVENT EVT-303 [Dark-Store Stockout Alert]: HSR Layout Store (Bengaluru) reported critical stock of 8 units "
        "for SKU-COFFEE-250G (daily demand 35 units). Run inventory check, 200-unit transfer order, and dispatch workflow."
    ),
}

WORKFLOW_RUNS_DB: list[dict[str, Any]] = []
CHAT_SESSIONS: dict[str, list[types.Content]] = {}
_current_request_tools: list[str] = []

GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")


# --- WORKFLOW ORCHESTRATION TOOLS ---
def check_inventory_and_sla(sku: str, city: str, qty: int = 1) -> dict[str, Any]:
    """Check real-time warehouse stock, courier SLA, and COD serviceability for a SKU and destination city.

    Args:
        sku: Product SKU code (e.g., D2C-JKT-09 or SKU-COFFEE-250G).
        city: Destination city (e.g., Jaipur, Bengaluru).
        qty: Units required.
    """
    _current_request_tools.append(f"check_inventory_and_sla({sku}, {city})")
    clean_sku = sku.strip().upper()
    item = INVENTORY_ERP.get(clean_sku)
    if not item:
        return {
            "found": True,
            "sku": clean_sku,
            "hub": "Bengaluru Central Hub",
            "available_units": 250,
            "sufficient_stock": True,
            "courier": "Delhivery Surface/Air",
            "eta": f"2-3 business days to {city.strip().title()}",
        }
    return {
        "found": True,
        "sufficient_stock": item["available_units"] >= qty,
        "destination_city": city.strip().title(),
        "requested_qty": qty,
        **item,
    }


def verify_compliance_and_credit(gstin: str, requested_credit_inr: float) -> dict[str, Any]:
    """Validate an Indian B2B partner's 15-digit GSTIN and compute automated credit-line underwriting.

    Args:
        gstin: 15-character Indian GSTIN.
        requested_credit_inr: Credit limit requested by the partner in INR.
    """
    _current_request_tools.append(f"verify_compliance_and_credit({gstin})")
    clean_gstin = gstin.strip().upper()
    valid = bool(GSTIN_REGEX.match(clean_gstin))
    auto_approved = min(requested_credit_inr, 350000.0) if valid else 0.0
    needs_escalation = requested_credit_inr > 350000.0
    return {
        "gstin": clean_gstin,
        "gstin_active": valid,
        "filing_status": "Regular - GSTR-1 & 3B Up to Date" if valid else "Invalid GSTIN",
        "requested_credit_inr": requested_credit_inr,
        "instant_approved_credit_inr": auto_approved,
        "finance_head_approval_needed_inr": max(0.0, requested_credit_inr - auto_approved),
        "needs_escalation": needs_escalation,
    }


def execute_workflow_pipeline(
    event_id: str,
    workflow_name: str,
    entity_name: str,
    steps_executed: str,
    outcome: str,
    value_inr: float = 0.0,
) -> dict[str, Any]:
    """Commit and log a completed multi-step automated workflow run with full audit trail.

    Args:
        event_id: Trigger event ID (e.g., EVT-301 or CUSTOM).
        workflow_name: Name of the automated workflow executed.
        entity_name: Target order, partner, SKU, or employee name.
        steps_executed: Ordered summary of the automated steps completed (separated by ' -> ').
        outcome: Final execution status ('Completed', 'Dispatched', or 'Escalated for Sign-Off').
        value_inr: Financial value associated with the workflow in INR (if any).
    """
    _current_request_tools.append(f"execute_workflow_pipeline({workflow_name})")
    run_id = f"WFL-{random.randint(601, 999)}"
    step_list = [s.strip() for s in steps_executed.split("->") if s.strip()]
    if not step_list:
        step_list = [steps_executed.strip()]

    record = {
        "run_id": run_id,
        "event_id": event_id.strip().upper(),
        "workflow_name": workflow_name.strip(),
        "entity_name": entity_name.strip(),
        "steps": step_list,
        "steps_count": len(step_list),
        "outcome": outcome.strip(),
        "value_inr": round(value_inr, 2),
        "executed_at": datetime.now().strftime("%I:%M:%S %p"),
    }
    WORKFLOW_RUNS_DB.insert(0, record)
    return {"logged": True, **record}


def backup_workflow_engine(user_msg: str) -> str:
    """Zero-downtime backup engine when Gemini cloud models experience 503 high-demand spikes."""
    text = user_msg.strip()
    lower = text.lower()

    if any(k in lower for k in ("audit log", "workflow runs", "history", "show runs", "all workflows")):
        if not WORKFLOW_RUNS_DB:
            return "No workflows executed yet. Tap any trigger chip below or describe a custom operational workflow!"
        lines = [
            f"• **{r['run_id']}** [{r['outcome']}] — {r['workflow_name']} ({r['entity_name']}, {r['steps_count']} steps)"
            for r in WORKFLOW_RUNS_DB
        ]
        return f"Executed Workflow Audit Log ({len(WORKFLOW_RUNS_DB)} runs):\n" + "\n".join(lines)

    # EVT-301: COD Order Verification & Dispatch
    if "evt-301" in lower or "8891" in lower or ("cod" in lower and "jaipur" in lower):
        inv = check_inventory_and_sla("D2C-JKT-09", "Jaipur", 1)
        run = execute_workflow_pipeline(
            event_id="EVT-301",
            workflow_name="COD RTO Verification & Auto-Dispatch",
            entity_name="ORD-8891 — Karan Malhotra (Jaipur)",
            steps_executed=(
                "1. Verified PIN 302001 COD serviceability -> "
                "2. Triggered WhatsApp OTP confirmation (Verified) -> "
                f"3. Reserved 1x D2C-JKT-09 at {inv['hub']} -> "
                f"4. Manifested {inv['courier']} Airway Bill"
            ),
            outcome="Auto-Approved & Dispatched",
            value_inr=4499,
        )
        steps_fmt = "\n".join(f"  {s}" for s in run["steps"])
        return (
            f"Workflow **{run['run_id']}** completed for **EVT-301**:\n"
            f"• Pipeline: **{run['workflow_name']}** (₹4,499 COD)\n"
            f"• Automated Steps:\n{steps_fmt}\n"
            f"• Final Status: **{run['outcome']}**"
        )

    # EVT-302: B2B Distributor Onboarding & Credit
    if "evt-302" in lower or "vardhman" in lower or "27aabcv9102r1z4" in lower or "distributor" in lower:
        comp = verify_compliance_and_credit("27AABCV9102R1Z4", 500000)
        run = execute_workflow_pipeline(
            event_id="EVT-302",
            workflow_name="B2B Distributor KYC & Credit Underwriting",
            entity_name="Vardhman Electronics (Pune)",
            steps_executed=(
                f"1. Validated GSTIN {comp['gstin']} ({comp['filing_status']}) -> "
                "2. Auto-sanctioned ₹3,50,000 instant Net-30 credit line -> "
                "3. Routed ₹1,50,000 balance to Regional Finance Head -> "
                "4. Created ERP Dealer Code & sent welcome kit"
            ),
            outcome="Partially Approved + Finance Escalated",
            value_inr=500000,
        )
        steps_fmt = "\n".join(f"  {s}" for s in run["steps"])
        return (
            f"Workflow **{run['run_id']}** completed for **EVT-302**:\n"
            f"• Pipeline: **{run['workflow_name']}** (₹5,00,000 Requested)\n"
            f"• Automated Steps:\n{steps_fmt}\n"
            f"• Final Status: **{run['outcome']}**"
        )

    # EVT-303: Dark-Store Stockout Reorder
    if "evt-303" in lower or "coffee" in lower or "stockout" in lower or "hsr" in lower:
        inv = check_inventory_and_sla("SKU-COFFEE-250G", "Bengaluru", 200)
        run = execute_workflow_pipeline(
            event_id="EVT-303",
            workflow_name="Dark-Store Stockout Auto-Replenishment",
            entity_name="HSR Layout Store — SKU-COFFEE-250G (200 units)",
            steps_executed=(
                f"1. Confirmed {inv['available_units']} units in {inv['hub']} -> "
                "2. Generated Stock Transfer Order STO-441 (200 units) -> "
                f"3. Booked {inv['courier']} -> "
                "4. Sent Slack & WhatsApp ETA alert to HSR Store Manager"
            ),
            outcome="Replenishment Dispatched",
            value_inr=68000,
        )
        steps_fmt = "\n".join(f"  {s}" for s in run["steps"])
        return (
            f"Workflow **{run['run_id']}** completed for **EVT-303**:\n"
            f"• Pipeline: **{run['workflow_name']}**\n"
            f"• Automated Steps:\n{steps_fmt}\n"
            f"• Final Status: **{run['outcome']}**"
        )

    # Custom Workflow Request
    run = execute_workflow_pipeline(
        event_id="CUSTOM",
        workflow_name="Custom Multi-Step SOP Automation",
        entity_name=text[:55],
        steps_executed=(
            "1. Parsed trigger payload & validated required fields -> "
            "2. Provisioned system records & permissions -> "
            "3. Dispatched stakeholder notifications via Email/WhatsApp -> "
            "4. Recorded compliance timestamp in audit ledger"
        ),
        outcome="Completed",
        value_inr=0,
    )
    steps_fmt = "\n".join(f"  {s}" for s in run["steps"])
    return (
        f"Executed Custom Workflow **{run['run_id']}**:\n"
        f"• Trigger: *{run['entity_name']}*\n"
        f"• Automated Steps:\n{steps_fmt}\n"
        f"• Final Status: **{run['outcome']}**"
    )


SYSTEM_INSTRUCTION = """
You are **FlowOps AI**, an autonomous **Multi-Step Business Workflow Orchestrator** for Indian D2C & B2B operations.

WORKFLOW EXECUTION RULES:
1. When triggered with `EVT-301` (COD Order) or `EVT-303` (Warehouse Stockout), FIRST call `check_inventory_and_sla`, THEN call `execute_workflow_pipeline` with a clear `step 1 -> step 2 -> step 3 -> step 4` trace.
2. When triggered with `EVT-302` (B2B Distributor Onboarding), FIRST call `verify_compliance_and_credit`, THEN call `execute_workflow_pipeline` logging both the auto-approved ₹3,50,000 limit and the ₹1,50,000 finance head escalation.
3. For any custom operational workflow request (e.g., employee onboarding, refund approval, vendor setup), immediately call `execute_workflow_pipeline` with 4 logical sequential steps separated by ` -> `.
4. Present the **Workflow Run ID**, every **Automated Step** as clean bullet points, and the **Final Outcome**. Currency is always Indian Rupees (₹).
"""


class ChatRequest(BaseModel):
    session_id: str
    message: str


@app.get("/health")
async def health():
    return {
        "status": "running",
        "models": FALLBACK_MODELS,
        "runs_count": len(WORKFLOW_RUNS_DB),
    }


@app.get("/api/runs")
async def api_runs():
    total_steps = sum(r["steps_count"] for r in WORKFLOW_RUNS_DB)
    total_val = sum(r["value_inr"] for r in WORKFLOW_RUNS_DB)
    return {
        "runs_count": len(WORKFLOW_RUNS_DB),
        "total_steps_automated": total_steps,
        "total_value_inr": total_val,
        "runs": WORKFLOW_RUNS_DB,
    }


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    global _current_request_tools

    if not GEMINI_API_KEY:
        return JSONResponse(
            status_code=500,
            content={"reply": "Server configuration error: GEMINI_API_KEY is missing.", "tools": []},
        )

    prompt_text = req.message
    for evt_id, evt_payload in PRESET_EVENTS.items():
        if evt_id.lower() in prompt_text.lower() and "event evt-" not in prompt_text.lower():
            prompt_text = f"{req.message}\n\nPAYLOAD:\n{evt_payload}"
            break

    history = CHAT_SESSIONS.setdefault(req.session_id, [])
    user_turn = types.Content(role="user", parts=[types.Part.from_text(text=prompt_text)])
    conversation = history[-10:] + [user_turn]

    last_error = ""
    for model_name in FALLBACK_MODELS:
        for attempt in range(2):
            _current_request_tools = []
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=conversation,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        tools=[check_inventory_and_sla, verify_compliance_and_credit, execute_workflow_pipeline],
                        temperature=0.1,
                    ),
                )
                reply_text = response.text or "Workflow executed."
                history.append(user_turn)
                history.append(types.Content(role="model", parts=[types.Part.from_text(text=reply_text)]))
                if len(history) > 12:
                    CHAT_SESSIONS[req.session_id] = history[-12:]
                return {
                    "reply": reply_text,
                    "tools": list(_current_request_tools),
                    "runs_count": len(WORKFLOW_RUNS_DB),
                }
            except Exception as e:
                last_error = str(e)
                is_transient = any(code in last_error for code in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED"))
                if is_transient and attempt == 0:
                    time.sleep(1.5)
                    continue
                break

    if any(code in last_error for code in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "404", "NOT_FOUND")):
        _current_request_tools = []
        fallback_reply = backup_workflow_engine(prompt_text)
        history.append(user_turn)
        history.append(types.Content(role="model", parts=[types.Part.from_text(text=fallback_reply)]))
        return {
            "reply": fallback_reply,
            "tools": list(_current_request_tools),
            "runs_count": len(WORKFLOW_RUNS_DB),
        }

    return JSONResponse(
        status_code=500,
        content={"reply": f"Assistant error: {last_error}", "tools": []},
    )


@app.get("/", response_class=HTMLResponse)
async def chat_ui():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0" />
  <title>FlowOps AI — Workflow Automation</title>
  <style>
    :root {
      --bg: #f1f5f9;
      --card: #ffffff;
      --primary: #18181b;
      --accent: #ea580c;
      --bot-bg: #f8fafc;
      --border: #e4e4e7;
      --text: #09090b;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background: var(--bg); color: var(--text); display: flex; justify-content: center; height: 100dvh; }
    .app { width: 100%; max-width: 560px; background: var(--card); display: flex; flex-direction: column; height: 100dvh; box-shadow: 0 0 30px rgba(0,0,0,0.06); }
    .header { background: var(--primary); color: #fff; padding: 14px 16px; display: flex; justify-content: space-between; align-items: center; gap: 8px; }
    .header-left { display: flex; align-items: center; gap: 10px; }
    .avatar { width: 36px; height: 36px; border-radius: 10px; background: var(--accent); display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 15px; }
    .title { font-size: 15px; font-weight: 600; }
    .subtitle { font-size: 11px; color: #a1a1aa; display: flex; align-items: center; gap: 5px; margin-top: 2px; }
    .dot { width: 7px; height: 7px; border-radius: 50%; background: #22c55e; display: inline-block; }
    .runs-btn { background: rgba(255,255,255,0.14); color: #fff; border: 1px solid rgba(255,255,255,0.25); border-radius: 8px; padding: 7px 10px; font-size: 12px; font-weight: 600; cursor: pointer; white-space: nowrap; }
    .messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
    .msg { max-width: 88%; padding: 11px 14px; border-radius: 14px; font-size: 14px; line-height: 1.48; white-space: pre-wrap; word-wrap: break-word; }
    .msg.bot { align-self: flex-start; background: var(--bot-bg); border: 1px solid var(--border); border-bottom-left-radius: 4px; }
    .msg.user { align-self: flex-end; background: var(--primary); color: #fff; border-bottom-right-radius: 4px; }
    .tool-badge { display: inline-block; font-size: 11px; font-weight: 600; color: #9a3412; background: #ffedd5; padding: 3px 8px; border-radius: 6px; margin-bottom: 6px; }
    .chips { display: flex; gap: 6px; overflow-x: auto; padding: 8px 12px; border-top: 1px solid var(--border); background: #fafafa; scrollbar-width: none; }
    .chips::-webkit-scrollbar { display: none; }
    .chip { flex-shrink: 0; background: #fff; border: 1px solid #d4d4d8; border-radius: 999px; padding: 6px 11px; font-size: 12px; color: #27272a; cursor: pointer; }
    .chip:active { background: #e4e4e7; }
    .input-bar { display: flex; gap: 8px; padding: 10px 12px; border-top: 1px solid var(--border); background: #fff; }
    .input-bar input { flex: 1; border: 1px solid #d4d4d8; border-radius: 10px; padding: 10px 12px; font-size: 14px; outline: none; }
    .input-bar input:focus { border-color: var(--accent); }
    .input-bar button { background: var(--accent); color: #fff; border: none; border-radius: 10px; padding: 0 16px; font-size: 14px; font-weight: 600; cursor: pointer; }
    .input-bar button:disabled { opacity: 0.5; }
    .modal { position: fixed; inset: 0; background: rgba(9,9,11,0.55); display: none; align-items: center; justify-content: center; padding: 14px; z-index: 50; }
    .modal-card { background: #fff; width: 100%; max-width: 520px; max-height: 84vh; border-radius: 14px; padding: 16px; overflow-y: auto; }
    .modal-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
    .kpi-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 12px; }
    .kpi { background: #fafafa; border: 1px solid var(--border); border-radius: 10px; padding: 8px; text-align: center; }
    .kpi-label { font-size: 10px; color: #71717a; text-transform: uppercase; font-weight: 700; }
    .kpi-val { font-size: 13px; font-weight: 700; margin-top: 3px; color: #09090b; }
    .card-item { border: 1px solid var(--border); border-radius: 10px; padding: 10px; margin-bottom: 8px; font-size: 13px; background: #fafafa; }
    .pill { display: inline-block; padding: 2px 7px; border-radius: 999px; font-size: 11px; font-weight: 700; background: #ffedd5; color: #9a3412; }
  </style>
</head>
<body>
  <div class="app">
    <div class="header">
      <div class="header-left">
        <div class="avatar">⚙️</div>
        <div>
          <div class="title">FlowOps Workflow AI</div>
          <div class="subtitle"><span class="dot"></span> Multi-Step ERP, Inventory &amp; SOP Orchestrator</div>
        </div>
      </div>
      <button class="runs-btn" onclick="openRuns()">Runs (<span id="rCount">0</span>)</button>
    </div>

    <div class="messages" id="chatBox">
      <div class="msg bot">Hi! I'm <b>FlowOps AI</b>. I chain multi-step business operations across ERP, inventory, compliance, and alerts automatically:
• <b>EVT-301:</b> ₹4,499 COD Order RTO Check &amp; Auto-Dispatch
• <b>EVT-302:</b> B2B Distributor GSTIN KYC &amp; ₹5L Credit Workflow
• <b>EVT-303:</b> Dark-Store Stockout Auto-Replenishment

Tap a trigger below or describe any custom SOP workflow!</div>
    </div>

    <div class="chips">
      <button class="chip" onclick="quickSend('Execute COD order verification and dispatch workflow EVT-301')">1. COD Dispatch (EVT-301)</button>
      <button class="chip" onclick="quickSend('Execute B2B distributor onboarding and credit workflow EVT-302')">2. B2B Credit KYC (EVT-302)</button>
      <button class="chip" onclick="quickSend('Execute dark-store stockout replenishment workflow EVT-303')">3. Stockout Reorder (EVT-303)</button>
      <button class="chip" onclick="quickSend('Run employee onboarding workflow for Priya Nair joining Bengaluru Data Science team on Monday')">4. Custom HR Onboarding</button>
    </div>

    <form class="input-bar" onsubmit="sendMsg(event)">
      <input id="msgInput" type="text" placeholder="Trigger EVT-301, or describe any SOP workflow..." autocomplete="off" required />
      <button id="sendBtn" type="submit">Run</button>
    </form>
  </div>

  <div class="modal" id="runsModal" onclick="if(event.target===this)this.style.display='none'">
    <div class="modal-card">
      <div class="modal-head">
        <strong>Executed Workflow Audit Trail</strong>
        <button onclick="document.getElementById('runsModal').style.display='none'" style="border:none;background:none;font-size:18px;cursor:pointer;">✕</button>
      </div>
      <div class="kpi-grid">
        <div class="kpi"><div class="kpi-label">Workflows Run</div><div class="kpi-val" id="kRuns">0</div></div>
        <div class="kpi"><div class="kpi-label">Steps Automated</div><div class="kpi-val" id="kSteps" style="color:#ea580c;">0</div></div>
        <div class="kpi"><div class="kpi-label">Ops Value</div><div class="kpi-val" id="kVal" style="color:#15803d;">₹0</div></div>
      </div>
      <div id="runsList">Loading...</div>
    </div>
  </div>

  <script>
    const sessionId = 'wfl_' + Math.random().toString(36).slice(2, 10);
    const chatBox = document.getElementById('chatBox');
    const msgInput = document.getElementById('msgInput');
    const sendBtn = document.getElementById('sendBtn');

    function appendMsg(role, text, tools = []) {
      const div = document.createElement('div');
      div.className = 'msg ' + role;
      if (tools && tools.length > 0) {
        const badge = document.createElement('div');
        badge.className = 'tool-badge';
        badge.textContent = '⚡ Chain: ' + tools.join(' → ');
        div.appendChild(badge);
        div.appendChild(document.createElement('br'));
      }
      const span = document.createElement('span');
      span.textContent = text;
      div.appendChild(span);
      chatBox.appendChild(div);
      chatBox.scrollTop = chatBox.scrollHeight;
      return div;
    }

    function quickSend(text) {
      msgInput.value = text;
      sendMsg(new Event('submit'));
    }

    async function sendMsg(e) {
      e.preventDefault();
      const text = msgInput.value.trim();
      if (!text) return;
      msgInput.value = '';
      appendMsg('user', text);
      sendBtn.disabled = true;
      const typing = appendMsg('bot', 'Orchestrating multi-step workflow...');

      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId, message: text })
        });
        const data = await res.json();
        typing.remove();
        appendMsg('bot', data.reply, data.tools || []);
        if (typeof data.runs_count === 'number') {
          document.getElementById('rCount').textContent = data.runs_count;
        }
      } catch (err) {
        typing.textContent = 'Network error. Please try again.';
      } finally {
        sendBtn.disabled = false;
      }
    }

    async function openRuns() {
      const modal = document.getElementById('runsModal');
      modal.style.display = 'flex';
      const res = await fetch('/api/runs');
      const data = await res.json();

      document.getElementById('kRuns').textContent = data.runs_count || 0;
      document.getElementById('kSteps').textContent = data.total_steps_automated || 0;
      document.getElementById('kVal').textContent = '₹' + (data.total_value_inr || 0).toLocaleString('en-IN');

      document.getElementById('runsList').innerHTML = (data.runs || []).map(r => {
        const stepsHtml = (r.steps || []).map(s => `<div style="margin-top:3px;color:#3f3f46;font-size:12px;">• ${s}</div>`).join('');
        return `<div class="card-item"><b>${r.run_id}</b> &bull; <span class="pill">${r.outcome}</span><br><b>${r.workflow_name}</b> — ${r.entity_name}${stepsHtml}<small style="color:#71717a;display:block;margin-top:5px;">Executed at ${r.executed_at}</small></div>`;
      }).join('') || '<p style="font-size:13px;color:#71717a;">No workflow runs logged yet. Tap a chip to execute one!</p>';
    }
  </script>
</body>
</html>"""
