/* Vector GUI — wizard de auditoria + limpeza (fase 1: dados de exemplo).
   Mesma arquitetura do genesis/gui/wizard/app.js: estado global + render()
   por tela, dual-mode WebView2 (window.chrome.webview) vs preview direto
   no navegador. Fase 2 troca VECTOR_MOCK pelos eventos do bridge. */

const STEPS = [
  { id: "welcome", label: "Início" },
  { id: "scan", label: "Varredura" },
  { id: "review", label: "Revisão" },
  { id: "plan", label: "Plano" },
  { id: "executing", label: "Execução" },
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
  report: null,          // ultimo ScanReport (payload camelCase do motor ou mock)
  selected: {},          // path -> true (o que vai para o lote)
  exec: null,            // { queue, i, ok, fail, lines, running, sealed, simulation }
  engineAvailable: false, // definido pelo host em 'host-ready'
  phase: "mock",         // 'engine' | 'mock'
  scanning: false,       // varredura em andamento (aguardando scan-result)
  scanError: "",         // ultima falha de varredura, se houver
  // Backup/quarentena (Task 7):
  utility: null,         // null | "quarantine" | "restore"
  backup: null,          // resultado de inspect: {file, external, sealedTs, items, fileBytes}
  backupSel: {},         // id -> true nas telas de restauracao
  replyIntent: null,     // roteia 'engine-reply' de inspect: 'picker' | 'quarantine' | 'restore'
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
  const currentIdx = state.utility ? -1 : order.indexOf(state.step);
  const item = function (id, label, i) {
    const cls = (i >= 0 && (i < currentIdx || state.doneSteps.indexOf(id) >= 0)) ? " is-done"
      : (i === currentIdx || state.utility === id) ? " is-current"
      : (i > currentIdx && currentIdx >= 0) ? " is-locked" : "";
    return '<div class="side-item' + cls + '" data-step="' + id + '"><span class="dot"></span><span>' +
      label + "</span></div>";
  };
  $("#sidebar").innerHTML =
    '<div class="side-group"><div class="side-group-title">Vector</div>' +
    STEPS.map(function (s, i) { return item(s.id, s.label, i); }).join("") + "</div>" +
    '<div class="side-group"><div class="side-group-title">Backup</div>' +
    '<div class="side-item' + (state.utility === "quarantine" ? " is-current" : "") +
    '" data-util="quarantine"><span class="dot"></span><span>Quarentena</span></div>' +
    '<div class="side-item" data-util="pick"><span class="dot"></span><span>Restaurar backup…</span></div>' +
    "</div>";
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
  render();
  $("#content").scrollTop = 0;
}

function render() {
  renderSidebar();
  const screens = {
    welcome: renderWelcome,
    scan: renderScanSetup,
    review: renderReview,
    plan: renderPlan,
    executing: renderExecuting,
    done: renderDone,
    quarantine: renderQuarantine,   // Task 7
    restore: renderRestore,         // Task 7
  };
  const host = $("#content");
  host.innerHTML = "";
  if (state.scanning) { renderScanning(host); renderNav(); return; }
  (screens[state.utility || state.step] || renderWelcome)(host);
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
  const busy = state.exec && state.exec.running;
  const inPlanLike = state.step === "plan" || state.step === "executing" ||
                     state.step === "done" || !!state.utility;
  if (state.scanning) {
    back.disabled = true;
    next.disabled = true;
    next.textContent = "Varrendo...";
    return;
  }
  if (busy || inPlanLike) {
    back.style.display = "none";
    next.style.display = "none";
    return;
  }
  back.style.display = "";
  next.style.display = "";
  back.disabled = idx === 0;
  const labels = { welcome: "Iniciar varredura", scan: "Revisar seleção", review: "Revisar plano →" };
  next.textContent = labels[state.step] || "Avançar";
  back.onclick = function () { if (idx > 0) go(order[idx - 1]); };
  next.onclick = function () {
    if (state.step === "welcome") runScan();
    else if (state.step === "scan") go(state.report ? "review" : "scan");
    else if (state.step === "review") go("plan");
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
  state.selected = preselect(state.report.candidates);
  go("review");
}


/* ---------------- lote: secoes de risco e selecao ---------------- */

function fmtBytes(n) {
  if (!n || n <= 0) return "tamanho n/d";
  const units = ["B", "KB", "MB", "GB"];
  let v = n, u = 0;
  while (v >= 1024 && u < 3) { v /= 1024; u++; }
  return v.toFixed(1) + " " + units[u];
}

function reviewSections() {
  const items = filteredCandidates();
  const folders = items.filter(function (c) { return c.kind === "folder"; });
  const low = folders.filter(function (c) { return c.confidence === "LOW"; });
  const cleanFolders = folders.filter(function (c) { return c.confidence !== "LOW"; });
  return [
    { id: "high", title: "Quase certamente sobra de programa desinstalado",
      sub: "Não aparecem na lista de programas do Windows. Pode marcar o grupo inteiro com confiança.",
      items: cleanFolders.filter(function (c) { return c.confidence === "HIGH" && !c.sensitive; }),
      groupable: true },
    { id: "med", title: "Provável sobra — vale conferir",
      sub: "Boas chances de ser resíduo, mas a evidência é mais fraca. Marcável em grupo.",
      items: cleanFolders.filter(function (c) { return c.confidence === "MEDIUM" && !c.sensitive; }),
      groupable: true },
    { id: "sens", title: "Pasta com dados seus",
      sub: "Configurações, conversas, saves. Fora do “marcar todos” — marque item a item, sabendo o que faz.",
      items: cleanFolders.filter(function (c) { return c.sensitive; }),
      groupable: false },
    { id: "low", title: "Confiança baixa — o Vector não oferece para remover",
      sub: "Há indícios fracos demais para uma limpeza segura; nada aqui entra no lote.",
      items: low, readonly: true },
    { id: "man", title: "O Vector não apaga — veja o passo a passo",
      sub: "Registro, serviços e tarefas: o comando sugerido abaixo resolve com segurança.",
      items: items.filter(function (c) { return c.kind !== "folder"; }),
      readonly: true },
  ].filter(function (s) { return s.items.length > 0; });
}

// Pre-selecao padrao da spec: HIGH nao-sensive marcado; MEDIUM/sensive livres.
function preselect(items) {
  const sel = {};
  items.forEach(function (c) {
    if (c.kind === "folder" && !c.sensitive && c.confidence === "HIGH") sel[c.path] = true;
  });
  return sel;
}

function selectedCandidates() {
  if (!state.report) return [];
  return state.report.candidates.filter(function (c) { return state.selected[c.path]; });
}

function selectedBytes() {
  return selectedCandidates().reduce(function (s, c) { return s + (c.sizeBytes || 0); }, 0);
}

/* ---------------- tela: review ---------------- */

function renderReview(root) {
  const el = document.createElement("div");
  el.className = "screen screen-wide";

  if (!state.report) {
    el.innerHTML =
      '<h1 class="screen-title">Rev<span class="hl">isão</span></h1>' +
      '<div class="ev-empty ev-error">[!] A varredura falhou no motor.' +
      (state.scanError ? "<br/>" + escapeHtml(state.scanError) : "") +
      "<br/>Volte e tente de novo, ou verifique se o Vector roda como admin.</div>";
    root.appendChild(el);
    setStatus("varredura com erro · nada foi movido");
    return;
  }

  const sections = reviewSections();
  el.innerHTML =
    '<h1 class="screen-title">Rev<span class="hl">isão</span> — o que vai, o que fica</h1>' +
    '<p class="screen-lede">' + state.report.installedCount + " programas instalados · " +
    filteredCandidates().length + " candidato(s). Nada é apagado agora: o que você marcar " +
    "será <b>movido para a quarentena</b> e poderá voltar de lá.</p>";

  sections.forEach(function (s) {
    const sec = document.createElement("div");
    sec.className = "bk-section";
    const groupCheck = s.groupable
      ? '<input type="checkbox" class="bk-check bk-group-check" data-group="' + s.id + '"' +
        (s.items.length && s.items.every(function (c) { return state.selected[c.path]; }) ? " checked" : "") +
        ' title="marcar o grupo inteiro" />'
      : "";
    sec.innerHTML =
      '<div class="bk-group-head">' + groupCheck +
      '<span class="bk-group-title">' + escapeHtml(s.title) + "</span>" +
      '<span class="ev-count">' + s.items.length + "</span></div>" +
      '<p class="bk-group-sub">' + escapeHtml(s.sub) + "</p>" +
      s.items.map(function (c) { return reviewRow(c, s.groupable || s.id === "sens"); }).join("");
    el.appendChild(sec);
  });

  const foot = document.createElement("div");
  foot.className = "bk-foot";
  el.appendChild(foot);
  root.appendChild(el);
  wireReview(el);
  updateReviewFoot();
  setStatus("revisão · marque os grupos que conhece");
}

function reviewRow(c, selectable) {
  return '<label class="bk-row' + (selectable ? "" : " is-locked") + '">' +
    (selectable
      ? '<input type="checkbox" class="bk-check bk-item-check" data-path="' +
        escapeHtml(c.path) + '"' + (state.selected[c.path] ? " checked" : "") + " />"
      : '<span class="bk-lock">' + (KIND_LABEL[c.kind] || c.kind) + "</span>") +
    '<span class="bk-main">' +
    '<span class="bk-name">' + escapeHtml(c.label) + "</span>" +
    '<span class="bk-path">' + escapeHtml(c.path) + "</span>" +
    '<span class="bk-why">' + escapeHtml(c.summaryPlain || "") + " · " +
    escapeHtml(metaLine(c)) + "</span></span></label>" +
    '<details class="bk-tech"><summary>detalhes técnicos</summary>' +
    evidenceInner(c) + "</details>";
}

// miolo de evidencias reaproveitado do antigo evidenceCard, agora so o interior
function evidenceInner(c) {
  const rows = c.evidences.map(function (e) {
    return '<div class="ev-row"><span class="ev-weight">+' + e.weight + "</span><span>" +
      escapeHtml(e.description.replace(/^\+\d+\s*/, "")) + "</span>" +
      (state.verbose ? '<span class="ev-src">' + escapeHtml(e.source) + "</span>" : "") +
      "</div>";
  }).join("");
  return '<div class="ev-score">score <strong>' + c.score + "</strong> · " +
    c.confidence + "</div>" + rows +
    (c.manualCommand
      ? '<div class="ev-manual"><span>manual — o Vector nunca remove sozinho:</span><br/>' +
        escapeHtml(c.manualCommand) + "</div>"
      : "");
}

function wireReview(el) {
  el.querySelectorAll(".bk-item-check").forEach(function (chk) {
    chk.addEventListener("change", function () {
      if (chk.checked) state.selected[chk.dataset.path] = true;
      else delete state.selected[chk.dataset.path];
      updateReviewFoot();
      syncGroupChecks(el);
    });
  });
  el.querySelectorAll(".bk-group-check").forEach(function (chk) {
    chk.addEventListener("change", function () {
      const s = reviewSections().filter(function (x) { return x.id === chk.dataset.group; })[0];
      if (!s) return;
      s.items.forEach(function (c) {
        if (chk.checked) state.selected[c.path] = true;
        else delete state.selected[c.path];
      });
      render();
    });
  });
}

function syncGroupChecks(el) {
  el.querySelectorAll(".bk-group-check").forEach(function (chk) {
    const s = reviewSections().filter(function (x) { return x.id === chk.dataset.group; })[0];
    chk.checked = !!(s && s.items.length && s.items.every(function (c) { return state.selected[c.path]; }));
  });
}

function updateReviewFoot() {
  const foot = document.querySelector(".bk-foot");
  if (!foot) return;
  const n = Object.keys(state.selected).length;
  foot.innerHTML =
    '<button class="btn btn-ghost" id="btn-all">Marcar todos (exceto sensíveis)</button>' +
    '<span class="bk-tally">' + n + " selecionado(s) · ~" + fmtBytes(selectedBytes()) + "</span>" +
    '<button class="btn btn-primary" id="btn-to-plan"' + (n ? "" : " disabled") + ">Revisar plano →</button>";
  foot.querySelector("#btn-all").onclick = function () {
    reviewSections().forEach(function (s) {
      if (s.groupable) s.items.forEach(function (c) { state.selected[c.path] = true; });
    });
    render();
  };
  const tp = foot.querySelector("#btn-to-plan");
  if (tp) tp.onclick = function () { go("plan"); };
}

/* ---------------- tela: plan ---------------- */

function renderPlan(root) {
  const chosen = selectedCandidates();
  const el = document.createElement("div");
  el.className = "screen";
  el.innerHTML =
    '<h1 class="screen-title">Pla<span class="hl">no</span> de limpeza</h1>' +
    '<p class="screen-lede">Uma confirmação única executa o lote inteiro.</p>' +
    '<div class="panel"><h2 class="panel-title">' + chosen.length + " item(ns) — ~" +
    fmtBytes(selectedBytes()) + "</h2>" +
    '<ul class="bk-plan">' + chosen.map(function (c) {
      return "<li><b>" + escapeHtml(c.label) + "</b><br/><span class=\"bk-path\">" +
        escapeHtml(c.path) + "</span></li>";
    }).join("") + "</ul></div>" +
    '<div class="panel"><h2 class="panel-title">Para onde vai</h2>' +
    '<p class="panel-sub">Nada é apagado. As pastas serão <b>movidas para a quarentena</b> ' +
    "do Vector — um arquivo <code>.vec</code> compactado com só a última execução. " +
    "Você pode restaurar tudo pela própria interface, ou abrir o arquivo no futuro.</p></div>" +
    '<div class="bk-actions"><button class="btn btn-ghost" id="btn-back-review">← Ajustar seleção</button>' +
    '<button class="btn btn-primary" id="btn-exec">Mover ' + chosen.length +
    " itens para a quarentena" +
    (state.engineAvailable ? "" : " (simulação — motor indisponível)") + "</button></div>";
  root.appendChild(el);
  $("#btn-back-review").onclick = function () { go("review"); };
  $("#btn-exec").onclick = startExecution;
  setStatus("plano pronto · confirme uma única vez");
}

/* ---------------- tela: executing ---------------- */

function startExecution() {
  const queue = selectedCandidates();
  state.exec = { queue: queue, i: 0, ok: 0, fail: 0, lines: [],
                 running: true, sealed: null, simulation: !state.engineAvailable };
  go("executing");
  pumpExecution();
}

function pumpExecution() {
  const ex = state.exec;
  if (!ex) return;
  if (ex.i >= ex.queue.length) {
    ex.running = false;
    if (!ex.simulation) { engineCall("quarantine-seal"); return; }
    go("done");
    return;
  }
  const c = ex.queue[ex.i];
  if (ex.simulation) {
    ex.ok++; ex.lines.push({ kind: "ok", text: c.path });
    ex.i++;
    renderExecutingInPlace();
    setTimeout(pumpExecution, 120);
    return;
  }
  renderExecutingInPlace();
  sendToHost("remove-folder", { path: c.path });
}

function applyRemoveResult(p) {
  const ex = state.exec;
  if (!ex) return;
  if (p.removed) { ex.ok++; ex.lines.push({ kind: "ok", text: p.path }); }
  else { ex.fail++; ex.lines.push({ kind: "fail", text: p.path + " — " + (p.detail || "") }); }
  ex.i++;
  pumpExecution();
}

function renderExecutingInPlace() {
  const host = $("#content");
  host.innerHTML = "";
  renderExecuting(host);
}

function renderExecuting(root) {
  const ex = state.exec || { queue: [], i: 0, ok: 0, fail: 0, lines: [] };
  const el = document.createElement("div");
  el.className = "screen";
  el.innerHTML =
    '<h1 class="screen-title">Exe<span class="hl">cutando</span></h1>' +
    '<p class="screen-lede">' + ex.i + " de " + ex.queue.length +
    (ex.simulation ? " · simulação com dados de exemplo" : " · movendo para a quarentena") + "</p>" +
    '<div class="feed" id="feed">' + ex.lines.map(function (l) {
      return '<div class="feed-line feed-' + l.kind + '">' +
        (l.kind === "ok" ? "✓ " : "✗ ") + escapeHtml(l.text) + "</div>";
    }).join("") + "</div>";
  root.appendChild(el);
  const feed = $("#feed");
  if (feed) feed.scrollTop = feed.scrollHeight;
  setStatus("execução em andamento · não feche a janela");
}

/* ---------------- tela: done ---------------- */

function renderDone(root) {
  const ex = state.exec || { ok: 0, fail: 0, simulation: true, sealed: null };
  const el = document.createElement("div");
  el.className = "screen";
  el.innerHTML =
    '<h1 class="screen-title">Limpeza <span class="hl">concluída</span></h1>' +
    '<p class="screen-lede">' + ex.ok + " item(ns) na quarentena" +
    (ex.fail ? ", " + ex.fail + " falhou(ram) — veja o relatório acima" : "") + ".</p>" +
    '<div class="panel"><h2 class="panel-title">Seu backup</h2><p class="panel-sub">' +
    (ex.simulation
      ? "Modo exemplo: nenhuma pasta real foi tocada."
      : "Guardado como <code>.vec</code> compactado (só a última execução). " +
        "Restaura pela interface a qualquer momento.") +
    "</p></div>" +
    '<div class="bk-actions">' +
    (ex.simulation ? "" :
      '<button class="btn btn-ghost" id="btn-open-q">Abrir quarentena</button>' +
      '<button class="btn btn-ghost" id="btn-export">Salvar cópia do backup…</button>') +
    '<button class="btn btn-primary" id="btn-again">Nova varredura</button></div>';
  root.appendChild(el);
  if (!ex.simulation) {
    $("#btn-open-q").onclick = openQuarantine;                 // Task 7
    $("#btn-export").onclick = function () { sendToHost("export-backup", {}); };
  }
  $("#btn-again").onclick = resetWizard;
  setStatus("concluído · nada foi apagado de verdade");
}

function resetWizard() {
  state.report = null;
  state.selected = {};
  state.exec = null;
  state.utility = null;
  state.backup = null;
  state.backupSel = {};
  state.doneSteps = [];
  go("welcome");
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
    state.selected = preselect(p.candidates || []);
    go("review");
    return;
  }
  if (msg.type === "scan-error") {
    state.scanning = false;
    state.scanError = p.error || "falha desconhecida na varredura";
    state.report = null;
    go("review");   // renderReview mostra o estado de erro quando !state.report
    return;
  }
  if (msg.type === "remove-result") {
    applyRemoveResult(p);
    return;
  }
  if (msg.type === "engine-reply") { onEngineReply(p); return; }
  if (msg.type === "backup-picked") {
    if (p.path) inspectBackup(p.path);   // cancelado -> path null, fica onde estava
    return;
  }
  if (msg.type === "open-backup") {
    inspectBackup(p.path);   // duplo-clique num .vec => cai direto na restauracao
    return;
  }
  if (msg.type === "backup-exported") {
    showNotice(p.ok ? "Cópia do backup salva em:\n" + p.detail
                    : "Não deu para salvar a cópia: " + (p.detail || p.error || "cancelado"), null);
    return;
  }
  // 'not-implemented' / 'bridge-error' de versoes antigas do host: ignora com
  // seguranca (a interface segue em mock).
}

// Passa-thru para os comandos de quarentena/backup (whitelist no host,
// guard real no motor). A resposta chega em 'engine-reply' -> onEngineReply.
function engineCall(cmd, args) {
  const req = Object.assign({ cmd: cmd }, args || {});
  sendToHost("engine-call", req);
}

// Roteia as respostas dos comandos de quarentena/backup conforme a intencao
// que originou o pedido (state.replyIntent) - um so canal para sete comandos.
function onEngineReply(p) {
  const r = p.result || {};
  if (p.cmd === "quarantine-seal") {
    if (state.exec) state.exec.sealed = r;
    go("done");
    return;
  }
  if (p.cmd === "quarantine-inspect" || p.cmd === "backup-inspect") {
    state.backup = r.file ? r : null;
    state.backupSel = {};
    if (r.corrupt) {
      showNotice("Este arquivo não é um backup do Vector válido (ou está corrompido).", null);
      state.replyIntent = null;
      render();
      return;
    }
    if (state.replyIntent === "picker") {
      state.replyIntent = null;
      showPicker(state.backup);       // modal decide o proximo passo
      return;
    }
    if (state.replyIntent === "restore") state.utility = "restore";
    else if (state.replyIntent === "quarantine") state.utility = "quarantine";
    state.replyIntent = null;
    render();
    return;
  }
  if (p.cmd === "quarantine-restore" || p.cmd === "backup-restore") {
    advanceRestore(p.ok ? r : { restored: false, detail: p.error });
    return;
  }
  if (p.cmd === "quarantine-purge") {
    state.backup = null;
    render();
    return;
  }
}

/* ---------------- quarentena / restauracao ---------------- */

function inspectBackup(path) { engineCall("backup-inspect", { path: path }); }

function openQuarantine() {
  state.replyIntent = "quarantine";
  state.exec = null;
  engineCall("quarantine-inspect");
  state.utility = "quarantine";
  render();   // tela assume "carregando..." ate o engine-reply
}

function openBackupPicker() {
  state.replyIntent = "picker";
  engineCall("quarantine-inspect");   // data/tamanho no botao primario do modal
}

function renderQuarantine(root) {
  if (!state.engineAvailable) {
    root.appendChild(noticePanel("A quarentena precisa do motor real (Python). " +
      "Sem ele a interface roda com dados de exemplo."));
    return;
  }
  if (!state.backup && !state.replyIntent) {
    root.appendChild(noticePanel("Quarentena vazia — rode uma limpeza primeiro."));
    return;
  }
  if (!state.backup) { root.appendChild(noticePanel("Carregando…")); return; }
  renderBackupView(root, {
    title: "Quar<span class=\"hl\">entena</span>",
    lede: "Última execução, guardada em <code>last.vec</code>. Restaurar devolve " +
          "cada pasta ao lugar de origem e tira do backup.",
    purge: true,
  });
}

function renderRestore(root) {
  if (!state.backup) { root.appendChild(noticePanel("Selecione um arquivo de backup.")); return; }
  renderBackupView(root, {
    title: "Restau<span class=\"hl\">ração</span>",
    lede: "Abrindo <code>" + escapeHtml(state.backup.file.split("\\").pop()) + "</code>. " +
      (state.backup.external
        ? "Este é um arquivo externo: restaurar <b>copia</b> as pastas de volta e o backup permanece intacto."
        : "Backup ativo: restaurar <b>move</b> de volta e enxuga o arquivo."),
    purge: false,
  });
}

function noticePanel(text) {
  const el = document.createElement("div");
  el.className = "screen";
  el.innerHTML = '<div class="panel"><p class="panel-sub">' + text + "</p></div>";
  return el;
}

// Uma tela para as duas telas (quarentena e restauracao): mesmos grupos,
// mesmas regras - o que muda e movido vs copiado (semantica no motor).
function renderBackupView(root, opts) {
  const b = state.backup;
  const running = state.exec && state.exec.running;
  const el = document.createElement("div");
  el.className = "screen screen-wide";
  const done = b.sealedTs ? new Date(b.sealedTs * 1000).toLocaleString("pt-BR") : "—";
  el.innerHTML =
    '<h1 class="screen-title">' + opts.title + "</h1>" +
    '<p class="screen-lede">' + opts.lede + "</p>" +
    '<p class="bk-meta-line">' + b.items.length + " item(ns) · backup de " + done +
    " · arquivo " + fmtBytes(b.fileBytes) + "</p>";
  if (running) {
    el.innerHTML += '<div class="feed" id="feed">' + state.exec.lines.map(function (l) {
      return '<div class="feed-line feed-' + l.kind + '">' +
        (l.kind === "ok" ? "✓ " : "✗ ") + escapeHtml(l.text) + "</div>";
    }).join("") + "</div>";
  } else {
    b.items.forEach(function (it) {
      const row = document.createElement("label");
      row.className = "bk-row";
      row.innerHTML =
        '<input type="checkbox" class="bk-check" data-id="' + escapeHtml(it.id) + '"' +
        (state.backupSel[it.id] ? " checked" : "") + " />" +
        '<span class="bk-main"><span class="bk-name">' + escapeHtml(it.label) +
        ' <span class="conf conf-' + (it.confidence || "low").toLowerCase() + '">' +
        (it.confidence || "?") + "</span></span>" +
        '<span class="bk-path">' + escapeHtml(it.original) + "</span>" +
        '<span class="bk-why">' + escapeHtml(it.summaryPlain || "") + " · " +
        fmtBytes(it.sizeBytes) + "</span></span>";
      el.appendChild(row);
    });
    const foot = document.createElement("div");
    foot.className = "bk-foot";
    const n = Object.keys(state.backupSel).length;
    foot.innerHTML =
      '<button class="btn btn-ghost" id="btn-bk-all">Marcar todos</button>' +
      '<span class="bk-tally">' + n + " selecionado(s)</span>" +
      '<button class="btn btn-primary" id="btn-bk-restore"' + (n ? "" : " disabled") + ">Restaurar selecionados</button>" +
      (opts.purge ? '<button class="btn btn-danger" id="btn-bk-purge">Esvaziar quarentena…</button>' : "");
    el.appendChild(foot);
  }
  root.appendChild(el);
  if (!running) wireBackupView(el, opts);
  setStatus(running ? "restauração em andamento" : "quarentena");
}

function wireBackupView(el, opts) {
  el.querySelectorAll(".bk-check[data-id]").forEach(function (chk) {
    chk.addEventListener("change", function () {
      if (chk.checked) state.backupSel[chk.dataset.id] = true;
      else delete state.backupSel[chk.dataset.id];
      const btn = el.querySelector("#btn-bk-restore");
      if (btn) btn.disabled = !Object.keys(state.backupSel).length;
      const tally = el.querySelector(".bk-tally");
      if (tally) tally.textContent = Object.keys(state.backupSel).length + " selecionado(s)";
    });
  });
  el.querySelector("#btn-bk-all").onclick = function () {
    state.backup.items.forEach(function (it) { state.backupSel[it.id] = true; });
    render();
  };
  el.querySelector("#btn-bk-restore").onclick = startRestore;
  const purge = el.querySelector("#btn-bk-purge");
  if (purge) {
    purge.onclick = function () {
      if (purge.dataset.armed) { engineCall("quarantine-purge"); return; }
      purge.dataset.armed = "1";
      purge.textContent = "Clique de novo para APAGAR o backup";
    };
  }
}

function startRestore() {
  const items = state.backup.items.filter(function (i) { return state.backupSel[i.id]; });
  state.exec = { queue: items, i: 0, ok: 0, fail: 0, lines: [], running: true,
                 external: !!state.backup.external };
  restorePump();
}

function restorePump() {
  const ex = state.exec;
  if (!ex || ex.i >= ex.queue.length) {
    if (ex) ex.running = false;
    state.backupSel = {};
    if (state.utility === "quarantine") openQuarantine();   // re-inspeciona o que sobrou
    else render();
    return;
  }
  render();
  const it = ex.queue[ex.i];
  if (state.backup && state.backup.external) engineCall("backup-restore", { path: state.backup.file, id: it.id });
  else engineCall("quarantine-restore", { id: it.id });
}

function advanceRestore(r) {
  const ex = state.exec;
  if (!ex) return;
  if (r.restored) { ex.ok++; ex.lines.push({ kind: "ok", text: r.detail }); }
  else { ex.fail++; ex.lines.push({ kind: "fail", text: (ex.queue[ex.i] || {}).original + " — " + (r.detail || "") }); }
  ex.i++;
  restorePump();
}

/* ---------------- overlay: picker de backup ---------------- */

function overlay() {
  let el = document.getElementById("overlay");
  if (!el) {
    el = document.createElement("div");
    el.id = "overlay";
    el.className = "modal-mask";
    document.getElementById("app").appendChild(el);
  }
  return el;
}

function closeOverlay() {
  const el = document.getElementById("overlay");
  if (el) el.remove();
}

function showNotice(text, after) {
  const el = overlay();
  el.innerHTML = '<div class="modal-card"><p class="modal-text">' +
    escapeHtml(text).replace(/\n/g, "<br/>") +
    '</p><button class="btn btn-primary" id="modal-ok">Entendi</button></div>';
  el.querySelector("#modal-ok").onclick = function () {
    closeOverlay();
    if (after) after();
  };
}

function showPicker(activeBackup) {
  const el = overlay();
  const has = !!(activeBackup && activeBackup.file);
  const when = has ? new Date(activeBackup.sealedTs * 1000).toLocaleString("pt-BR") : "";
  el.innerHTML =
    '<div class="modal-card"><h2 class="modal-title">Restaurar backup</h2>' +
    '<button class="btn btn-primary modal-big" id="modal-active"' + (has ? "" : " disabled") + ">" +
    "Último backup automático" +
    (has ? "<small>" + activeBackup.items.length + " item(ns) · " + when +
          " · " + fmtBytes(activeBackup.fileBytes) + "</small>"
        : "<small>nenhum backup ainda — rode uma limpeza primeiro</small>") +
    "</button>" +
    '<button class="btn btn-ghost" id="modal-other">Outro arquivo…</button>' +
    '<button class="btn btn-ghost" id="modal-x">Cancelar</button></div>';
  el.querySelector("#modal-active").onclick = function () {
    closeOverlay();
    state.replyIntent = "restore";
    render();   // state.backup ja veio do inspect do picker
  };
  el.querySelector("#modal-other").onclick = function () { showDropForm(); };
  el.querySelector("#modal-x").onclick = closeOverlay;
}

function showDropForm() {
  const el = overlay();
  el.innerHTML =
    '<div class="modal-card"><h2 class="modal-title">Selecionar backup .vec</h2>' +
    '<div class="dropzone" id="dz">Arraste o arquivo <b>.vec</b> aqui<br/>' +
    '<small>ou use o botão abaixo</small></div>' +
    '<button class="btn btn-primary" id="dz-pick">Selecionar arquivo…</button>' +
    '<button class="btn btn-ghost" id="dz-x">Cancelar</button></div>';
  const dz = el.querySelector("#dz");
  dz.addEventListener("dragover", function (e) { e.preventDefault(); dz.classList.add("is-over"); });
  dz.addEventListener("dragleave", function () { dz.classList.remove("is-over"); });
  dz.addEventListener("drop", handleBackupDrop);
  el.querySelector("#dz-pick").onclick = function () { sendToHost("pick-backup", {}); };
  el.querySelector("#dz-x").onclick = closeOverlay;
}

const DROP_MAX_BYTES = 20 * 1024 * 1024;

function handleBackupDrop(e) {
  e.preventDefault();
  const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
  if (!f) return;
  const realPath = f.path || "";          // WebView2 expoe; padrao web nao
  if (realPath) { closeOverlay(); inspectBackup(realPath); return; }
  if (f.size > DROP_MAX_BYTES) {
    // Trava da spec: fecha o aviso e ABRE o seletor nativo direto.
    showNotice("Arquivos acima de 20 MB não podem ser arrastados — selecione o arquivo.",
      function () { sendToHost("pick-backup", {}); });
    return;
  }
  const rd = new FileReader();
  rd.onload = function () {
    closeOverlay();
    sendToHost("drop-temp", { name: f.name, b64: toBase64(rd.result) });
  };
  rd.readAsArrayBuffer(f);
}

function toBase64(buf) {
  const bytes = new Uint8Array(buf);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(bin);
}

if (isHosted()) {
  window.chrome.webview.addEventListener("message", onBridgeMessage);
  sendToHost("ready", { app: "vector", phase: "mock" });
}

$("#btn-min").addEventListener("click", function () { sendToHost("window-minimize", {}); });
$("#btn-close").addEventListener("click", function () { sendToHost("window-close", {}); });
$("#sidebar").addEventListener("click", function (e) {
  // Delegacao no continador: #sidebar e reescrito a cada renderSidebar.
  const util = e.target.closest("[data-util]");
  if (util) {
    if (util.dataset.util === "quarantine") openQuarantine();
    else openBackupPicker();
    return;
  }
  const st = e.target.closest("[data-step]");
  if (st && (state.utility || st.dataset.step !== state.step)) {
    state.utility = null;
    go(st.dataset.step);
  }
});
$("#titlebar").addEventListener("mousedown", function (e) {
  if (e.target.closest(".titlebar-actions")) return;
  sendToHost("window-drag", {});
});

render();

