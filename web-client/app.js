"use strict";

// order-fulfillment-platform's own gateway - this repo never modifies that
// project, so login happens by calling its /auth/login directly from the
// browser. Running the joint demo requires that gateway's
// orderplatform.cors.allowed-origin be set to wherever THIS web-client is
// actually served from (see infra/docker-compose.yml's comment and this
// repo's README) - its CORS is locked to one configured origin, and
// changing which origin that is is a config/env-var change on the sibling
// repo, not a code change, so it doesn't violate "never modify the sibling".
const GATEWAY_URL = "http://localhost:8080";

// This repo's own FastAPI app serves this file itself (see app/main.py's
// StaticFiles mount), so /chat and /docs_corpus are same-origin - no CORS
// concern at all for those, unlike the cross-origin login call above.
const CHAT_URL = "/chat";
const DOCS_BASE_URL = "/docs_corpus";
const DOC_FILENAMES = [
  "fulfillment-sla.md",
  "return-policy.md",
  "backorder-cancellation-explainer.md",
  "cancellation-policy.md",
  "faq.md",
];

const loginPanel = document.getElementById("login-panel");
const appSection = document.getElementById("app");
const customerSelect = document.getElementById("customer-select");
const loginBtn = document.getElementById("login-btn");
const loginStatus = document.getElementById("login-status");
const currentCustomerEl = document.getElementById("current-customer");
const logoutBtn = document.getElementById("logout-btn");
const chatLog = document.getElementById("chat-log");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const traceLog = document.getElementById("trace-log");
const docList = document.getElementById("doc-list");
const docViewer = document.getElementById("doc-viewer");

function getSession() {
  const token = sessionStorage.getItem("token");
  const customerId = sessionStorage.getItem("customerId");
  const threadId = sessionStorage.getItem("threadId");
  return token && customerId && threadId ? { token, customerId, threadId } : null;
}

function resetSessionUiState() {
  // Same lesson the sibling repo's own web-client learned the hard way
  // (see order-fulfillment-platform/CLAUDE.md's "stale-UI-state gotcha"):
  // a correctly-scoped backend is not the same thing as a correctly-reset
  // UI. Clearing storage alone isn't enough if the DOM still shows the
  // previous customer's chat/trace - so this is called on both logout and
  // a 401, not just one of them.
  chatLog.innerHTML = "";
  traceLog.innerHTML = "";
  docViewer.innerHTML = "";
}

async function login(customerId) {
  loginStatus.textContent = "Logging in...";
  let response;
  try {
    response = await fetch(`${GATEWAY_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ customerId }),
    });
  } catch (err) {
    loginStatus.textContent =
      "Could not reach order-fulfillment-platform's gateway at " +
      GATEWAY_URL +
      " - is it running, and is its CORS origin set to this page's origin?";
    return;
  }
  if (!response.ok) {
    loginStatus.textContent = `Login failed (${response.status})`;
    return;
  }
  const body = await response.json();
  sessionStorage.setItem("token", body.token);
  sessionStorage.setItem("customerId", body.customerId);
  sessionStorage.setItem("threadId", crypto.randomUUID());
  showApp();
}

function logout() {
  sessionStorage.clear();
  resetSessionUiState();
  appSection.hidden = true;
  loginPanel.hidden = false;
  loginStatus.textContent = "";
}

function showApp() {
  const session = getSession();
  if (!session) {
    logout();
    return;
  }
  loginPanel.hidden = true;
  appSection.hidden = false;
  currentCustomerEl.textContent = session.customerId;
  resetSessionUiState();
  loadHelpCenter();
}

function appendChatMessage(role, text) {
  const el = document.createElement("div");
  el.className = `chat-message ${role}`;
  el.textContent = text;
  chatLog.appendChild(el);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function appendTraceLine(text) {
  const el = document.createElement("div");
  el.className = "trace-line";
  el.textContent = text;
  traceLog.appendChild(el);
  traceLog.scrollTop = traceLog.scrollHeight;
}

// Summarizes one node_update SSE event into a single readable trace line.
// Deliberately per-node-shape, not a generic JSON dump - the whole point
// of this panel is showing *what the graph decided*, not raw state.
function describeNodeUpdate(node, output) {
  switch (node) {
    case "scope_check":
      return output.is_out_of_scope_action
        ? "Scope check: declined (action request, no LLM call made)"
        : "Scope check: in scope, continuing";
    case "router":
      return `Router: needs_retrieval=${output.needs_retrieval}, needs_tools=${output.needs_tools}`;
    case "retrieve": {
      const docs = output.retrieved_docs || [];
      const list = docs.map((d) => `${d.source_file} (score ${d.score.toFixed(3)})`).join(", ");
      return `Retrieved ${docs.length} doc chunk(s): ${list || "none"}`;
    }
    case "tools": {
      const messages = output.messages || [];
      const toolMsgs = messages.filter((m) => m.type === "ToolMessage");
      if (toolMsgs.length === 0) return "Tools: model needed no further tool calls";
      return toolMsgs.map((m) => `Tool result: ${m.content}`).join(" | ");
    }
    case "critique":
      return `Critique verdict: ${output.critique_verdict}`;
    case "mark_retry":
      return "Critique said ungrounded - retrying once";
    case "answer":
      // The actual text is already shown as its own chat bubble via the
      // "answer" SSE event (see handleSseEvent) - this trace line is just
      // marking that the step happened, not repeating the content.
      return "Answer synthesized from the context above";
    default:
      return `${node}: ${JSON.stringify(output)}`;
  }
}

async function sendMessage(question) {
  const session = getSession();
  if (!session) {
    logout();
    return;
  }

  appendChatMessage("user", question);
  traceLog.innerHTML = "";
  chatInput.disabled = true;

  let response;
  try {
    response = await fetch(CHAT_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.token}`,
      },
      body: JSON.stringify({ question, thread_id: session.threadId }),
    });
  } catch (err) {
    appendChatMessage("error", "Could not reach the assistant service.");
    chatInput.disabled = false;
    return;
  }

  if (response.status === 401) {
    logout();
    return;
  }
  if (!response.ok || !response.body) {
    appendChatMessage("error", `Request failed (${response.status})`);
    chatInput.disabled = false;
    return;
  }

  await consumeSseStream(response.body);
  chatInput.disabled = false;
  chatInput.focus();
}

// fetch()'s response body doesn't give us the browser's native EventSource
// parsing (EventSource also can't do POST or set an Authorization header
// at all, which /chat needs) - so SSE framing (event:/data: lines,
// blank-line-terminated) is parsed by hand here instead.
async function consumeSseStream(body) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      handleSseEvent(rawEvent);
    }
  }
}

function handleSseEvent(rawEvent) {
  let eventName = "message";
  let dataLine = "";
  for (const line of rawEvent.split("\n")) {
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLine = line.slice(5).trim();
  }
  if (!dataLine) return;

  const data = JSON.parse(dataLine);
  if (eventName === "node_update") {
    appendTraceLine(describeNodeUpdate(data.node, data.output));
  } else if (eventName === "cache_hit") {
    appendTraceLine("(served from semantic cache - graph did not run)");
    appendChatMessage("assistant", data.answer);
  } else if (eventName === "answer") {
    appendChatMessage("assistant", data.answer);
  }
  // "done" carries no payload worth rendering.
}

// --- Help center: fetches docs_corpus/*.md (served statically alongside
// this app, see app/main.py) and renders them with a small hand-written
// markdown-to-HTML converter - just enough for this repo's own docs
// (headings, bold, inline code, bullet lists, paragraphs), not a general
// markdown library, to keep this a genuinely build-step-free static page.

function renderMarkdown(md) {
  const lines = md
    .replace(/^---\n[\s\S]*?\n---\n/, "") // strip YAML frontmatter
    .split("\n");
  let html = "";
  let inList = false;
  let paragraphLines = [];

  // Consecutive non-blank plain-text lines are ONE paragraph in markdown
  // (a source line-wrap isn't a paragraph break, a blank line is) - this
  // buffers them and only flushes a <p> once the paragraph actually ends,
  // rather than wrapping every wrapped source line in its own <p> (which
  // is what a naive one-line-at-a-time version did - verified live in the
  // browser before this fix, every line of the return-policy doc's wrapped
  // prose rendered as its own choppy paragraph instead of flowing text).
  function flushParagraph() {
    if (paragraphLines.length > 0) {
      html += `<p>${inlineMarkdown(paragraphLines.join(" "))}</p>`;
      paragraphLines = [];
    }
  }

  for (const line of lines) {
    const heading2 = line.match(/^##\s+(.*)/);
    const heading1 = line.match(/^#\s+(.*)/);
    const listItem = line.match(/^-\s+(.*)/);

    if (listItem) {
      flushParagraph();
      if (!inList) {
        html += "<ul>";
        inList = true;
      }
      html += `<li>${inlineMarkdown(listItem[1])}</li>`;
      continue;
    }
    if (inList) {
      html += "</ul>";
      inList = false;
    }

    if (heading2) {
      flushParagraph();
      html += `<h3>${inlineMarkdown(heading2[1])}</h3>`;
    } else if (heading1) {
      flushParagraph();
      html += `<h2>${inlineMarkdown(heading1[1])}</h2>`;
    } else if (line.trim() === "") {
      flushParagraph();
    } else {
      paragraphLines.push(line);
    }
  }
  flushParagraph();
  if (inList) html += "</ul>";
  return html;
}

function inlineMarkdown(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`(.+?)`/g, "<code>$1</code>");
}

function loadHelpCenter() {
  docList.innerHTML = "";
  for (const filename of DOC_FILENAMES) {
    const btn = document.createElement("button");
    btn.className = "doc-list-item";
    btn.textContent = filename;
    btn.addEventListener("click", () => viewDoc(filename));
    docList.appendChild(btn);
  }
}

async function viewDoc(filename) {
  docViewer.innerHTML = "Loading...";
  try {
    const response = await fetch(`${DOCS_BASE_URL}/${filename}`);
    if (!response.ok) throw new Error(String(response.status));
    const text = await response.text();
    docViewer.innerHTML = renderMarkdown(text);
  } catch (err) {
    docViewer.textContent = `Could not load ${filename}.`;
  }
}

loginBtn.addEventListener("click", () => login(customerSelect.value));
logoutBtn.addEventListener("click", logout);
chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const question = chatInput.value.trim();
  if (!question) return;
  chatInput.value = "";
  sendMessage(question);
});

if (getSession()) {
  showApp();
} else {
  loginPanel.hidden = false;
}
