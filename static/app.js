// CarChat page logic. Plain JavaScript, no build step.
//
// Everything that comes from the server or the model is put on the page with
// textContent, never innerHTML, so it is always shown as text and can never
// run as HTML or script.

const EXAMPLES = {
  sales: [
    "How many vehicles are available right now?",
    "Which five vehicles have been in stock the longest?",
    "What is the average list price of new SUVs at each store?",
    "Do we have any red sedans?",
  ],
  gm: [
    "Which vehicle has the best margin?",
    "What did we pay for stock number KG10482?",
    "What is the average margin by store?",
    "Which vehicles over 90 days on the lot are priced below cost?",
  ],
};

const $ = (id) => document.getElementById(id);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function api(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "same-origin",
  });
  let data = {};
  try { data = await response.json(); } catch (_) { /* empty or non-JSON body */ }
  return { ok: response.ok, status: response.status, data };
}

// --- Views

function showSignIn() {
  $("chat-view").hidden = true;
  $("session").hidden = true;
  $("sign-in-view").hidden = false;
  $("passcode").value = "";
  $("passcode").focus();
}

function showChat(session) {
  $("sign-in-view").hidden = true;
  $("chat-view").hidden = false;
  $("session").hidden = false;
  $("role-badge").textContent = "Signed in as " + session.title;
  $("messages").replaceChildren();
  $("intro").hidden = false;

  const examples = $("examples");
  examples.replaceChildren();
  for (const question of EXAMPLES[session.role] || EXAMPLES.sales) {
    const chip = el("button", "chip", question);
    chip.type = "button";
    chip.addEventListener("click", () => ask(question));
    examples.append(chip);
  }
  $("question").focus();
}

// --- Rendering one exchange

function formatCell(value) {
  if (value === null || value === undefined) return "";
  return String(value);
}

function renderTable(columns, rows) {
  const wrapper = el("div", "table-wrap");
  const table = el("table");
  const headRow = el("tr");
  for (const column of columns) headRow.append(el("th", null, column));
  const thead = el("thead");
  thead.append(headRow);
  const tbody = el("tbody");
  for (const row of rows) {
    const tr = el("tr");
    for (const value of row) {
      const td = el("td", typeof value === "number" ? "num" : null, formatCell(value));
      tr.append(td);
    }
    tbody.append(tr);
  }
  table.append(thead, tbody);
  wrapper.append(table);
  return wrapper;
}

function renderAnswer(card, result) {
  card.replaceChildren();
  card.classList.toggle("refused", result.refused);
  card.append(el("p", "answer-text", result.answer));
  if (!result.sql) return;

  const evidence = el("div", "evidence");
  evidence.append(el("h3", null, "Query that produced this answer"));
  evidence.append(el("pre", "sql", result.sql));
  const count = result.rows.length;
  evidence.append(el("h3", null, "Rows returned (" + count + (count === 200 ? ", capped at 200" : "") + ")"));
  evidence.append(renderTable(result.columns, result.rows));
  card.append(evidence);
}

async function ask(question) {
  question = question.trim();
  if (!question) return;
  $("intro").hidden = true;
  $("question").value = "";
  $("ask-button").disabled = true;

  const exchange = el("article", "exchange");
  exchange.append(el("p", "question-text", question));
  const card = el("div", "answer card");
  card.append(el("p", "muted", "Querying the inventory…"));
  exchange.append(card);
  $("messages").append(exchange);
  exchange.scrollIntoView({ behavior: "smooth", block: "start" });

  try {
    const { ok, status, data } = await api("/api/chat", { question });
    if (status === 401) { showSignIn(); return; }
    if (ok) {
      renderAnswer(card, data);
    } else {
      const detail = typeof data.detail === "string" ? data.detail : "Something went wrong. Please try again.";
      renderAnswer(card, { answer: detail, refused: true, sql: null });
    }
  } catch (_) {
    renderAnswer(card, { answer: "Could not reach the server. Check your connection and try again.", refused: true, sql: null });
  } finally {
    $("ask-button").disabled = false;
    $("question").focus();
  }
}

// --- Wiring

$("sign-in-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const error = $("sign-in-error");
  error.hidden = true;
  const { ok, data } = await api("/api/login", { passcode: $("passcode").value });
  if (ok) {
    showChat(data);
  } else {
    error.textContent = typeof data.detail === "string" ? data.detail : "Could not sign in.";
    error.hidden = false;
  }
});

$("sign-out").addEventListener("click", async () => {
  await api("/api/logout", {});
  showSignIn();
});

$("ask-form").addEventListener("submit", (event) => {
  event.preventDefault();
  ask($("question").value);
});

// On load: go straight to the chat if there is already a valid session.
api("/api/me").then(({ ok, data }) => (ok ? showChat(data) : showSignIn()));
