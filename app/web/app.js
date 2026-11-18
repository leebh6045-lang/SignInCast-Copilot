const $ = (id) => document.getElementById(id);

async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    const message = typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : `HTTP ${response.status}`;
    throw new Error(message);
  }
  return data;
}

function setStatus(text, isError = false) {
  $("status").textContent = text;
  $("status").className = isError ? "status error" : "status";
}

async function runQuery() {
  const query = $("query").value.trim();
  if (!query) return;
  $("send").disabled = true;
  setStatus("运行中…");
  $("answer").textContent = "";
  $("steps").innerHTML = "";
  $("usage").textContent = "";
  try {
    const data = await api("/api/run", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query, role: $("role").value }),
    });
    $("answer").textContent = data.answer || "(无回答)";
    data.steps.forEach((step) => {
      const item = document.createElement("li");
      const tools = step.tool_calls.join(", ") || "-";
      item.textContent = `step ${step.index}: ${tools}`;
      $("steps").appendChild(item);
    });
    $("usage").textContent = `tokens=${data.usage.total_tokens} · 估算成本 $${data.cost_usd} · run_id=${data.run_id}`;
    if (data.error_code) setStatus(`错误：${data.error_code} - ${data.error_message}`, true);
    else setStatus("完成");
  } catch (error) {
    setStatus(`请求失败：${error.message}`, true);
  } finally {
    $("send").disabled = false;
  }
}

function actionCard(action) {
  const card = document.createElement("div");
  card.className = "action";
  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = `${action.action_id} · ${action.tool_name} · ${action.created_at}`;
  const summary = document.createElement("div");
  summary.className = "summary";
  summary.textContent = action.summary;
  const row = document.createElement("div");
  row.className = "row";
  const confirmButton = document.createElement("button");
  confirmButton.textContent = "确认";
  const executeButton = document.createElement("button");
  executeButton.textContent = "执行";
  const result = document.createElement("div");
  result.className = "result";
  confirmButton.onclick = () => act(card, action.action_id, "confirm", result);
  executeButton.onclick = () => act(card, action.action_id, "execute", result);
  row.append(confirmButton, executeButton);
  card.append(meta, summary, row, result);
  return card;
}

async function act(card, actionId, kind, resultNode) {
  resultNode.textContent = "处理中…";
  try {
    const detail = await api(`/api/actions/${actionId}`);
    const data = await api(`/api/actions/${actionId}/${kind}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ confirm_token: detail.confirm_token }),
    });
    resultNode.textContent = `${kind}: ${data.status || "ok"}`;
    refreshActions();
  } catch (error) {
    resultNode.textContent = `失败：${error.message}`;
  }
}

async function refreshActions() {
  try {
    const data = await api("/api/actions?status=pending");
    const list = $("action-list");
    list.innerHTML = "";
    if (!data.count) {
      list.textContent = "没有待确认动作";
      return;
    }
    data.actions.forEach((action) => list.appendChild(actionCard(action)));
  } catch (error) {
    $("action-list").textContent = `加载失败：${error.message}`;
  }
}

$("send").onclick = runQuery;
$("query").addEventListener("keydown", (event) => { if (event.key === "Enter") runQuery(); });
$("refresh").onclick = refreshActions;
refreshActions();
