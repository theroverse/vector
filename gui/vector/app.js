/* Vector GUI — wizard de auditoria + limpeza (fase 1: dados de exemplo).
   Mesma arquitetura do genesis/gui/wizard/app.js: estado global + render()
   por tela, dual-mode WebView2 (window.chrome.webview) vs preview direto
   no navegador. Fase 2 troca VECTOR_MOCK pelos eventos do bridge. */

const STEPS = [
  { id: "welcome", label: "Início" },
  { id: "scan", label: "Varredura" },
  { id: "evidence", label: "Evidências" },
  { id: "clean", label: "Limpeza" },
  { id: "done", label: "Concluído" },
];

const KIND_LABEL = { folder: "DIR", registry: "REG", service: "SVC", task: "TASK" };
const CONF_ORDER = { HIGH: 3, MEDIUM: 2, LOW: 1 };

const state = {
  step: "welcome",
  doneSteps: [],
  target: "",
  minConfidence: "LOW",
  verbose: false,
  report: null,
  cleanQueue: [],
  cleanIndex: 0,
  cleanLog: [],
  removed: 0,
  skipped: 0,
  awaitingConfirm: false,
  // Fase 2 (bridge com o motor Python real):
  engineAvailable: false, // definido pelo host em 'host-ready'
  phase: "mock", // 'engine' | 'mock'
  scanning: false, // varredura em andamento (aguardando scan-result)
  scanError: "", // ultima falha de varredura, se houver
  awaitingHost: false, // aguardando remove-result do motor
};

const $ = (sel) => document.querySelector(sel);

function isHosted() {
  return !!(window.chrome && window.chrome.webview);
}

function sendToHost(type, payload) {
  if (!isHosted()) return false;
  // JSON.stringify obrigatorio: o host le com TryGetWebMessageAsString(),
  // que devolve null pra objeto cru (padrao provado no genesis/app.js).
  window.chrome.webview.postMessage(JSON.stringify({ type: type, payload: payload }));
  return true;
}

function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/* ---------------- shell ---------------- */

function renderSidebar() {
  const order = STEPS.map(function (s) { return s.id; });
  const currentIdx = order.indexOf(state.step);
  $("#sidebar").innerHTML = '<div class="side-group">' +
    '<div class="side-group-title">Vector</div>' +
    STEPS.map(function (s, i) {
      const cls = (i < currentIdx || state.doneSteps.indexOf(s.id) >= 0)
        ? "side-item is-done"
        : (i === currentIdx ? "side-item is-current" : "side-item is-locked");
      return '<div class="' + cls + '"><span class="dot"></span><span>' +
        s.label + "</span></div>";
    }).join("") + "</div>";
}

function setStatus(text) {
  $("#navbar-status").textContent = text;
}

function go(step) {
  const order = STEPS.map(function (s) { return s.id; });
  if (order.indexOf(step) > order.indexOf(state.step)) {
    if (state.doneSteps.indexOf(state.step) < 0) state.doneSteps.push(state.step);
  }
  state.step = step;
  state.awaitingConfirm = false;
  state.awaitingHost = false;
  render();
  $("#content").scrollTop = 0;
}

function render() {
  renderSidebar();
  const screens = {
    welcome: renderWelcome,
    scan: renderScanSetup,
    evidence: renderEvidence,
    clean: renderClean,
    done: renderDone,
  };
  const host = $("#content");
  host.innerHTML = "";
  if (state.scanning) { renderScanning(host); renderNav(); return; }
  screens[state.step](host);
  renderNav();
}

function renderScanning(root) {
  const el = document.createElement("div");
  el.className = "screen";
  const alvo = state.target.trim();
  el.innerHTML =
    '<h1 class="screen-title">Varre<span class="hl">endo</span> o sistema</h1>' +
    '<p class="screen-lede">Cruzando Program Files, AppData, ProgramData, Temp, ' +
    "Registro, servicos e tarefas" +
    (alvo ? ' com o alvo "' + escapeHtml(alvo) + '"' : " (varredura completa)") +
    '. Um momento&hellip;</p>' +
    '<div class="scan-spinner" aria-hidden="true"></div>';
  root.appendChild(el);
  setStatus("varredura em andamento · o motor esta lendo o sistema");
}

function renderNav() {
  const order = STEPS.map(function (s) { return s.id; });
  const idx = order.indexOf(state.step);
  const back = $("#btn-back");
  const next = $("#btn-next");
  const done = state.step === "done";
  back.style.display = done ? "none" : "";
  next.style.display = done ? "none" : "";
  if (state.scanning) {
    back.disabled = true;
    next.disabled = true;
    next.textContent = "Varrendo...";
    return;
  }
  next.disabled = false;
  back.disabled = idx === 0 || state.step === "clean";
  const labels = {
    welcome: "Iniciar varredura",
    scan: "Ver evidências",
    evidence: "Ir para limpeza",
    clean: "Concluir",
  };
  next.textContent = labels[state.step] || "Avançar";
  back.onclick = function () { if (idx > 0) go(order[idx - 1]); };
  next.onclick = function () {
    if (state.step === "welcome") runScan();
    else if (state.step === "scan") go("evidence");
    else if (state.step === "evidence") startClean();
    else if (state.step === "clean") go("done");
  };
}

/* ---------------- helpers de evidência ---------------- */

function metaLine(c) {
  const parts = [];
  if (c.kind === "folder") {
    parts.push(c.sizeHuman || "tamanho n/d");
    if (c.ageDays !== null && c.ageDays !== undefined) parts.push(c.ageDays + " dias parado");
  } else {
    const kindLabel = { registry: "chave de registro", service: "serviço", task: "tarefa agendada" };
    parts.push(kindLabel[c.kind] || c.kind);
  }
  if (c.sensitive) parts.push("POSSÍVEL DADO SENSÍVEL");
  return parts.join(" · ");
}

function evidenceCard(c) {
  const card = document.createElement("div");
  card.className = "ev-card";
  const rows = c.evidences.map(function (e) {
    return '<div class="ev-row"><span class="ev-weight">+' + e.weight + "</span>" +
      "<span>" + escapeHtml(e.description.replace(/^\+\d+\s*/, "")) + "</span>" +
      (state.verbose ? '<span class="ev-src">' + escapeHtml(e.source) + "</span>" : "") +
      "</div>";
  }).join("");
  card.innerHTML =
    '<div class="ev-card-head"><span class="conf conf-' + c.confidence.toLowerCase() + '">' +
    c.confidence + "</span>" +
    '<span class="ev-kind">' + (KIND_LABEL[c.kind] || c.kind) + "</span>" +
    '<span class="ev-score">score <strong>' + c.score + "</strong></span></div>" +
    '<div class="ev-path">' + escapeHtml(c.path) + "</div>" +
    '<div class="ev-meta">' + escapeHtml(metaLine(c)) + "</div>" +
    '<div class="ev-rows">' + rows + "</div>" +
    (c.sensitive
      ? '<div class="ev-alert"><strong>[!] ALERTA: possível DADO SENSÍVEL</strong> ' +
        "neste caminho. Remover pode causar PERDA IRREVERSÍVEL. Confira o conteúdo antes.</div>"
      : "") +
    (c.manualCommand
      ? '<div class="ev-manual"><span>manual — o Vector nunca remove sozinho:</span><br/>' +
        escapeHtml(c.manualCommand) + "</div>"
      : "");
  return card;
}

function filteredCandidates() {
  if (!state.report) return [];
  const threshold = CONF_ORDER[state.minConfidence] || 1;
  const wanted = state.target.trim().toLowerCase();
  return state.report.candidates.filter(function (c) {
    if ((CONF_ORDER[c.confidence] || 0) < threshold) return false;
    if (wanted &&
        c.label.toLowerCase().indexOf(wanted) < 0 &&
        c.path.toLowerCase().indexOf(wanted) < 0) return false;
    return true;
  });
}

/* ---------------- telas: welcome + scan ---------------- */

function renderWelcome(root) {
  const el = document.createElement("div");
  el.className = "screen";
  el.innerHTML =
    '<h1 class="screen-title">Limpeza <span class="hl">cirúrgica</span>,<br/>nunca no susto.</h1>' +
    '<p class="screen-lede">O Vector investiga Program Files, AppData, ProgramData, ' +
    "Temp, o Registro, serviços e tarefas agendadas — e monta uma árvore de " +
    "evidências com nível de confiança para cada resto órfão. " +
    "Auditoria primeiro, deleção depois — e só com a sua confirmação explícita.</p>" +
    '<div class="panel"><h2 class="panel-title">Como funciona</h2>' +
    '<p class="panel-sub">1) Varredura cruzada contra os programas instalados. ' +
    "2) Pontuação transparente de evidências (HIGH / MEDIUM / LOW). " +
    "3) Limpeza item a item, com alerta de dados sensíveis. " +
    "LOW nunca é oferecido; Registro, serviços e tarefas nunca são removidos sozinhos.</p></div>" +
    '<div class="panel"><h2 class="panel-title">Regras de segurança</h2>' +
    '<p class="panel-sub">Caminhos de sistema estão na allowlist e nunca são sugeridos. ' +
    "Pastas com possível dado sensível disparam alerta explícito. " +
    "PermissionError é reportado com elegância — rode como admin para cobertura total.</p></div>";
  root.appendChild(el);
  setStatus(state.engineAvailable
    ? "vector.exe · motor real (src/vector) pronto"
    : "vector.exe · modo auditoria · dados de exemplo");
}

function renderScanSetup(root) {
  const el = document.createElement("div");
  el.className = "screen";
  el.innerHTML =
    '<h1 class="screen-title">Configurar <span class="hl">varredura</span></h1>' +
    '<p class="screen-lede">Equivale a <b>vector-cli.py --scan</b>. A auditoria nunca apaga nada.</p>' +
    '<div class="panel"><div class="field"><label for="f-target">Programa alvo ' +
    "(vazio = varrer tudo)</label>" +
    '<input type="text" id="f-target" placeholder="ex.: Notion" value="" /></div>' +
    '<div class="field"><label>Confiança mínima</label><div class="seg" id="seg-conf">' +
    ["LOW", "MEDIUM", "HIGH"].map(function (c) {
      return '<button class="seg-btn' + (state.minConfidence === c ? " is-active" : "") +
        '" data-conf="' + c + '">' + c + "</button>";
    }).join("") + "</div></div>" +
    '<div class="field"><label class="check-line"><input type="checkbox" id="f-verbose" /> ' +
    "Modo verbose — mostrar a fonte (scanner) de cada evidência</label></div></div>";
  root.appendChild(el);
  $("#f-target").addEventListener("input", function (e) { state.target = e.target.value; });
  $("#seg-conf").addEventListener("click", function (e) {
    const btn = e.target.closest("[data-conf]");
    if (!btn) return;
    state.minConfidence = btn.dataset.conf;
    el.querySelectorAll(".seg-btn").forEach(function (b) {
      b.classList.toggle("is-active", b.dataset.conf === state.minConfidence);
    });
  });
  $("#f-verbose").addEventListener("change", function (e) { state.verbose = e.target.checked; });
  setStatus("auditoria textual · nada será apagado");
}

function runScan() {
  state.scanError = "";
  if (isHosted() && state.engineAvailable) {
    // Fase 2: pede ao VectorHost.ps1 para rodar engine.run_scan() e devolver
    // o ScanReport por 'scan-result' (onBridgeMessage). A tela de progresso
    // aparece ja que o WebView2 renderiza fora da thread de UI do host.
    state.scanning = true;
    render();
    sendToHost("start-scan", {
      target: state.target.trim() || null,
      minConfidence: state.minConfidence,
      verbose: state.verbose,
    });
    return;
  }
  // Fallback: preview no navegador ou motor indisponivel -> dados de exemplo.
  state.report = JSON.parse(JSON.stringify(VECTOR_MOCK));
  if (state.doneSteps.indexOf("scan") < 0) state.doneSteps.push("scan");
  go("evidence");
}


/* ---------------- tela: evidence ---------------- */

function renderEvidence(root) {
  const el = document.createElement("div");
  el.className = "screen screen-wide";

  if (!state.report) {
    el.innerHTML =
      '<h1 class="screen-title">Árvore de <span class="hl">evidências</span></h1>' +
      '<div class="ev-empty ev-error">[!] A varredura falhou no motor.' +
      (state.scanError ? "<br/>" + escapeHtml(state.scanError) : "") +
      "<br/>Volte e tente de novo, ou verifique se o Vector roda como admin.</div>";
    root.appendChild(el);
    setStatus("varredura com erro · nada foi apagado");
    return;
  }

  const items = filteredCandidates();
  const groups = ["HIGH", "MEDIUM", "LOW"].map(function (conf) {
    return {
      conf: conf,
      items: items.filter(function (c) { return c.confidence === conf; }),
    };
  }).filter(function (g) { return g.items.length > 0; });

  el.innerHTML =
    '<h1 class="screen-title">Árvore de <span class="hl">evidências</span></h1>' +
    '<p class="screen-lede">' + state.report.installedCount + " programas instalados · " +
    items.length + " candidato(s) · filtro: " + state.minConfidence +
    (state.target.trim() ? ' · alvo: "' + escapeHtml(state.target.trim()) + '"' : "") + "</p>";

  if (items.length === 0) {
    const empty = document.createElement("div");
    empty.className = "ev-empty";
    empty.textContent = "Nenhum resíduo para os critérios atuais. " +
      "Ajuste o filtro de confiança ou rode sem programa alvo.";
    el.appendChild(empty);
  }

  groups.forEach(function (g) {
    const title = document.createElement("div");
    title.className = "ev-group-title";
    title.innerHTML = g.conf + ' <span class="ev-count">' + g.items.length + "</span>";
    el.appendChild(title);
    g.items.forEach(function (c) { el.appendChild(evidenceCard(c)); });
  });

  const foot = document.createElement("div");
  foot.className = "ev-footnote";
  foot.innerHTML = "[!] Sem permissão em " + state.report.accessDenied.length +
    " caminho(s) (rode como admin p/ cobertura total)<br/>" +
    state.report.accessDenied.map(escapeHtml).join("<br/>");
  el.appendChild(foot);

  root.appendChild(el);
  setStatus(items.length + " candidato(s) · auditoria concluída · nada foi apagado");
}

/* ---------------- tela: clean ---------------- */

function cleanableItems() {
  return filteredCandidates().filter(function (c) {
    return (CONF_ORDER[c.confidence] || 0) >= 2;
  });
}

function manualOnly() {
  return cleanableItems().filter(function (c) { return c.kind !== "folder"; });
}

function feedLine(kind, text) {
  state.cleanLog.push({ kind: kind, text: text });
}

function startClean() {
  state.cleanQueue = cleanableItems().filter(function (c) { return c.kind === "folder"; });
  state.cleanIndex = 0;
  state.cleanLog = [];
  state.removed = 0;
  state.skipped = 0;
  go("clean");
}

function renderClean(root) {
  const el = document.createElement("div");
  el.className = "screen screen-wide";
  const manuals = manualOnly();
  const current = state.cleanQueue[state.cleanIndex];
  const expected = "REMOVER " + (state.cleanIndex + 1);

  el.innerHTML =
    '<h1 class="screen-title">Limpeza <span class="hl">interativa</span></h1>' +
    '<p class="screen-lede">Uma pasta por vez. Digite <b>' + expected + "</b> e confirme — " +
    "Enter vazio sempre pula. Candidatos LOW nunca são oferecidos.</p>";

  if (manuals.length > 0) {
    const panel = document.createElement("div");
    panel.className = "panel";
    panel.innerHTML = '<h2 class="panel-title">Nunca removidos sozinhos (' +
      manuals.length + ")</h2>" +
      '<p class="panel-sub">Registro, serviços e tarefas agendadas: execute o comando ' +
      "manual se desejar.</p>" +
      manuals.map(function (c) {
        return '<div class="ev-manual"><span>' + escapeHtml(c.label) + " —</span><br/>" +
          escapeHtml(c.manualCommand || c.path) + "</div>";
      }).join("");
    el.appendChild(panel);
  }

  if (!current) {
    const empty = document.createElement("div");
    empty.className = "ev-empty";
    empty.textContent = state.cleanQueue.length === 0
      ? "Nenhuma pasta HIGH/MEDIUM para remover. Nada a fazer."
      : "Fila concluída — avance para ver o resumo da sessão.";
    el.appendChild(empty);
  } else {
    const box = document.createElement("div");
    box.className = "clean-current";
    const progress = document.createElement("div");
    progress.className = "clean-progress";
    progress.textContent = "item " + (state.cleanIndex + 1) + " de " +
      state.cleanQueue.length + " · Enter vazio = pular";
    box.appendChild(progress);
    box.appendChild(evidenceCard(current));
    box.insertAdjacentHTML("beforeend",
      '<div class="clean-transcribe"><input type="text" id="f-transcribe" placeholder=\'Digite "' +
      expected + '" para continuar\' /></div>' +
      (state.awaitingHost
        ? '<div class="clean-confirm"><p><strong>Removendo pelo motor&hellip;</strong> ' +
          'o Vector esta revalidando e apagando este item.</p></div>'
        : state.awaitingConfirm
        ? '<div class="clean-confirm"><p><strong>Remoção definitiva.</strong> Tem certeza?</p>' +
          '<div class="clean-row-actions">' +
          '<button class="btn btn-danger" id="btn-confirm-yes">Sim, remover</button>' +
          '<button class="btn btn-ghost" id="btn-confirm-no">Não, pular</button></div></div>'
        : '<div class="clean-row-actions" style="margin-top:16px">' +
          '<button class="btn btn-primary" id="btn-transcribe-ok">Continuar</button>' +
          '<button class="clean-skip" id="btn-skip">pular (Enter)</button></div>'));
    el.appendChild(box);
  }

  if (state.cleanLog.length > 0) {
    const feed = document.createElement("div");
    feed.className = "clean-feed";
    feed.innerHTML = state.cleanLog.map(function (l) {
      return '<div class="' + l.kind + '">' + escapeHtml(l.text) + "</div>";
    }).join("");
    el.appendChild(feed);
  }

  root.appendChild(el);
  wireClean(el, current, expected);
  setStatus("limpeza item " + Math.min(state.cleanIndex + 1, state.cleanQueue.length) +
    "/" + state.cleanQueue.length + " · nada é apagado sem confirmar");
}


function wireClean(el, current, expected) {
  if (!current) return;
  if (state.awaitingHost) return; // aguardando remove-result: nada clicavel
  const input = $("#f-transcribe");

  function doSkip(reason) {
    feedLine("skip", "[PULADO] " + current.path + (reason ? " (" + reason + ")" : ""));
    state.skipped += 1;
    state.cleanIndex += 1;
    state.awaitingConfirm = false;
    render();
  }

  function tryContinue(value) {
    if (value === expected) { state.awaitingConfirm = true; render(); }
    else if (value === "") doSkip("");
    else doSkip("texto diferente de " + expected);
  }

  const skipBtn = $("#btn-skip");
  if (skipBtn) skipBtn.onclick = function () { doSkip(""); };

  const okBtn = $("#btn-transcribe-ok");
  if (okBtn) okBtn.onclick = function () { tryContinue(input.value.trim()); };

  if (input) {
    input.focus();
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") tryContinue(input.value.trim());
    });
  }

  const noBtn = $("#btn-confirm-no");
  if (noBtn) noBtn.onclick = function () { doSkip("sem confirmação"); };

  const yesBtn = $("#btn-confirm-yes");
  if (yesBtn) yesBtn.onclick = function () {
    if (isHosted() && state.engineAvailable) {
      // Fase 2: o motor revalida (HIGH/MEDIUM, so pasta, nao-allowlisted) e
      // apaga. A resposta chega em onBridgeMessage -> applyRemoveResult.
      state.awaitingHost = true;
      render();
      sendToHost("remove-folder", { path: current.path });
      return;
    }
    // Preview no navegador / sem motor: apenas simula, nada e tocado.
    feedLine("ok", "[REMOVIDO] " + current.path + " (simulado)");
    state.removed += 1;
    state.cleanIndex += 1;
    state.awaitingConfirm = false;
    render();
  };
}

function applyRemoveResult(p) {
  const current = state.cleanQueue[state.cleanIndex];
  state.awaitingHost = false;
  state.awaitingConfirm = false;
  if (!current) { render(); return; }
  if (p && p.removed) {
    feedLine("ok", "[REMOVIDO] " + current.path +
      (p.detail ? " (" + p.detail + ")" : ""));
    state.removed += 1;
  } else {
    feedLine("skip", "[FALHA] " + current.path +
      " (" + ((p && p.detail) || "nao removido") + ")");
    state.skipped += 1;
  }
  state.cleanIndex += 1;
  render();
}

/* ---------------- tela: done ---------------- */

function renderDone(root) {
  const el = document.createElement("div");
  el.className = "screen";
  const manuals = manualOnly();
  el.innerHTML =
    '<h1 class="screen-title">Limpeza <span class="hl">concluída</span></h1>' +
    '<p class="screen-lede">Resumo da sessão — dados de exemplo, nada foi tocado de verdade.</p>' +
    '<div class="done-stats">' +
    '<div class="done-stat removed"><b>' + state.removed + "</b><span>removidas</span></div>" +
    '<div class="done-stat skipped"><b>' + state.skipped + "</b><span>puladas</span></div>" +
    '<div class="done-stat manual"><b>' + manuals.length + "</b><span>manuais</span></div></div>" +
    (state.cleanLog.length > 0
      ? '<div class="panel"><h2 class="panel-title">Log da sessão</h2>' +
        '<div class="clean-feed">' + state.cleanLog.map(function (l) {
          return '<div class="' + l.kind + '">' + escapeHtml(l.text) + "</div>";
        }).join("") + "</div></div>"
      : "") +
    '<div class="panel"><h2 class="panel-title">Arquivo de log</h2>' +
    '<p class="panel-sub">Na versão ligada ao motor: %USERPROFILE%\\.vector\\vector-clean.log</p>' +
    "</div>";
  root.appendChild(el);
  setStatus("sessão concluída · " + state.removed + " removida(s), " +
    state.skipped + " pulada(s)");
}

/* ---------------- bridge + boot ---------------- */

function updatePhaseBadge() {
  const badge = $("#titlebar-phase");
  if (!badge) return;
  badge.textContent = state.engineAvailable
    ? "auditoria — motor real"
    : "auditoria — dados de exemplo";
}

function onBridgeMessage(event) {
  // O VectorHost.ps1 envia {type, payload} por aqui. Cada tipo move a maquina
  // de estados: host-ready define o modo; scan-result/remove-result sao as
  // respostas as duas unicas acoes que falam com o motor real.
  const msg = event && event.data;
  if (!msg || !msg.type) return;
  const p = msg.payload || {};

  if (msg.type === "host-ready") {
    state.engineAvailable = !!p.engineAvailable;
    state.phase = p.phase || (state.engineAvailable ? "engine" : "mock");
    updatePhaseBadge();
    if (state.step === "welcome") render();
    return;
  }
  if (msg.type === "scan-result") {
    state.scanning = false;
    state.scanError = "";
    state.report = p;
    if (state.doneSteps.indexOf("scan") < 0) state.doneSteps.push("scan");
    go("evidence");
    return;
  }
  if (msg.type === "scan-error") {
    state.scanning = false;
    state.scanError = p.error || "falha desconhecida na varredura";
    state.report = null;
    go("evidence");
    return;
  }
  if (msg.type === "remove-result") {
    applyRemoveResult(p);
    return;
  }
  // 'not-implemented' / 'bridge-error' de versoes antigas do host: ignora com
  // seguranca (a interface segue em mock).
}

if (isHosted()) {
  window.chrome.webview.addEventListener("message", onBridgeMessage);
  sendToHost("ready", { app: "vector", phase: "mock" });
}

$("#btn-min").addEventListener("click", function () { sendToHost("window-minimize", {}); });
$("#btn-close").addEventListener("click", function () { sendToHost("window-close", {}); });
$("#titlebar").addEventListener("mousedown", function (e) {
  if (e.target.closest(".titlebar-actions")) return;
  sendToHost("window-drag", {});
});

render();

