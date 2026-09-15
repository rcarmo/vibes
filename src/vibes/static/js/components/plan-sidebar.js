// Adapted from Piclaw plan-sidebar web/index.ts, Copyright (c) 2026 Rui Carmo.
// MIT: ../vendor/licenses/PICLAW-MIT.txt. Native session API + revision guards.
const STORAGE_OPEN = "piclaw:plan-sidebar:open";
const STORAGE_WIDTH = "piclaw:plan-sidebar:width";
const DEFAULT_CHAT_JID = "default";

export function beginPlanRequest(state) {
  return { epoch: ++state.requestEpoch, chatJid: state.chatJid, editRevision: state.editRevision };
}

export function invalidatePlanRequests(state) {
  state.requestEpoch += 1;
}

export function isCurrentPlanRequest(state, request) {
  return request.epoch === state.requestEpoch && request.chatJid === state.chatJid;
}

export function canApplyPlanResponse(state, request, preserveDirty = false) {
  return isCurrentPlanRequest(state, request)
    && request.editRevision === state.editRevision
    && (!preserveDirty || !state.dirty);
}

export function installPlanSidebar() {
  if (globalThis.__vibesPlanSidebarInstalled) return;
  globalThis.__vibesPlanSidebarInstalled = true;
  if (typeof document === "undefined") return;

  const state = {
    open: localStorage.getItem(STORAGE_OPEN) === "true",
    width: clampWidth(Number(localStorage.getItem(STORAGE_WIDTH)) || 380),
    chatJid: getCurrentChatJid(),
    markdown: "",
    updatedAt: null,
    revision: 0,
    drafts: new Map(),
    dirty: false,
    loading: false,
    editorView: null,
    cm: null,
    editorLoadPromise: null,
    editorThemeCompartment: null,
    themeObserver: null,
    fallbackTextarea: null,
    livePreviewHost: null,
    resizeStart: null,
    pendingRemoteRefresh: false,
    pendingRemoteLabel: "remote",
    pendingRemoteRevision: 0,
    requestEpoch: 0,
    editRevision: 0,
    applyingEditorValue: false,
  };

  injectStyles();

  const root = document.createElement("div");
  root.className = "plan-sidebar-root";
  root.innerHTML = `
    <button class="plan-sidebar-toggle" type="button" aria-label="Show plan" title="Show plan">
      <span class="plan-sidebar-toggle-meter" aria-hidden="true"><span class="plan-sidebar-toggle-meter-fill"></span></span>
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="10 3 5 8 10 13" /></svg>
      <span class="plan-sidebar-toggle-progress plan-sidebar-sr-only"></span>
    </button>
    <aside class="plan-sidebar-panel" aria-label="Session plan">
      <div class="plan-sidebar-resizer" role="separator" aria-label="Resize plan sidebar" aria-orientation="vertical" tabindex="0" title="Resize plan sidebar"></div>
      <header class="plan-sidebar-header">
        <div class="plan-sidebar-title">Plan</div>
        <div class="plan-sidebar-subtitle"></div>
      </header>
      <div class="plan-sidebar-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
        <div class="plan-sidebar-progress-meta">
          <span class="plan-sidebar-progress-label">No checklist items</span>
          <span class="plan-sidebar-progress-percent">0%</span>
        </div>
        <div class="plan-sidebar-progress-track"><div class="plan-sidebar-progress-fill"></div></div>
      </div>
      <div class="plan-sidebar-editor" role="region" aria-label="Markdown checklist editor"></div>
      <footer class="plan-sidebar-footer">
        <div class="plan-sidebar-status" aria-live="polite"></div>
        <div class="plan-sidebar-actions">
          <button class="plan-sidebar-refresh" type="button">Refresh</button>
          <button class="plan-sidebar-reset" type="button">Reset</button>
          <button class="plan-sidebar-save" type="button">Save</button>
          <button class="plan-sidebar-submit" type="button">Submit to model</button>
        </div>
      </footer>
    </aside>
  `;
  document.body.appendChild(root);

  const toggle = root.querySelector(".plan-sidebar-toggle");
  const panel = root.querySelector(".plan-sidebar-panel");
  const subtitle = root.querySelector(".plan-sidebar-subtitle");
  const progress = root.querySelector(".plan-sidebar-progress");
  const progressLabel = root.querySelector(".plan-sidebar-progress-label");
  const progressPercent = root.querySelector(".plan-sidebar-progress-percent");
  const progressFill = root.querySelector(".plan-sidebar-progress-fill");
  const toggleMeterFill = root.querySelector(".plan-sidebar-toggle-meter-fill");
  const toggleProgress = root.querySelector(".plan-sidebar-toggle-progress");
  const editorHost = root.querySelector(".plan-sidebar-editor");
  const status = root.querySelector(".plan-sidebar-status");
  const refreshButton = root.querySelector(".plan-sidebar-refresh");
  const resetButton = root.querySelector(".plan-sidebar-reset");
  const saveButton = root.querySelector(".plan-sidebar-save");
  const submitButton = root.querySelector(".plan-sidebar-submit");
  const resizer = root.querySelector(".plan-sidebar-resizer");

  function renderChrome() {
    const currentMarkdown = state.editorView ? state.editorView.state.doc.toString() : state.fallbackTextarea?.value || state.markdown || "";
    const currentProgress = getPlanProgress(currentMarkdown);
    root.classList.toggle("open", state.open);
    root.classList.toggle("has-checklist", currentProgress.total > 0);
    root.style.setProperty("--plan-sidebar-width", `${state.width}px`);
    panel.style.width = `${state.width}px`;
    panel.inert = !state.open;
    toggle.title = state.open ? "Hide plan" : `Show plan • ${formatProgressText(currentProgress)}`;
    toggle.setAttribute("aria-label", state.open ? "Hide plan" : `Show plan. ${formatProgressText(currentProgress)}.`);
    toggle.classList.toggle("open", state.open);
    subtitle.textContent = `${state.chatJid}${state.dirty ? " • unsaved" : ""}`;
    renderProgress(currentProgress);
    saveButton.disabled = state.loading || !state.dirty;
    submitButton.disabled = state.loading;
    refreshButton.disabled = state.loading;
    resetButton.disabled = state.loading;
  }

  function renderProgress(planProgress) {
    const text = formatProgressText(planProgress);
    progress.setAttribute("aria-valuenow", String(planProgress.percent));
    progress.setAttribute("aria-valuetext", text);
    progressLabel.textContent = planProgress.total ? `${planProgress.complete}/${planProgress.total} items complete` : "No checklist items";
    progressPercent.textContent = `${planProgress.percent}%`;
    progressFill.style.width = `${planProgress.percent}%`;
    toggleMeterFill.style.height = `${planProgress.percent}%`;
    toggleProgress.textContent = text;
  }

  function setStatus(message, kind = "info") {
    status.textContent = message || "";
    status.dataset.kind = kind;
  }

  function setOpen(next) {
    state.open = Boolean(next);
    localStorage.setItem(STORAGE_OPEN, state.open ? "true" : "false");
    renderChrome();
    if (state.open) {
      ensureEditor().then(() => loadPlan({ preserveDirty: true })).catch((error) => setStatus(String(error?.message || error), "error"));
      setTimeout(() => focusEditor(), 80);
    }
  }

  async function closeSidebar({ autosave = false } = {}) {
    if (!state.open) return;
    if (autosave && state.dirty) {
      try {
        await savePlan();
        if (state.dirty) return;
      } catch {
        return;
      }
    }
    setOpen(false);
  }

  function getEditorValue() {
    if (state.editorView) return state.editorView.state.doc.toString();
    return state.fallbackTextarea?.value || state.markdown || "";
  }

  function setEditorValue(value) {
    const next = String(value || "");
    state.markdown = next;
    if (state.editorView) {
      const current = state.editorView.state.doc.toString();
      if (current !== next) {
        state.applyingEditorValue = true;
        try {
          state.editorView.dispatch({ changes: { from: 0, to: current.length, insert: next } });
        } finally {
          state.applyingEditorValue = false;
        }
      }
    } else if (state.fallbackTextarea && state.fallbackTextarea.value !== next) {
      state.fallbackTextarea.value = next;
    }
  }

  function clearDisplayedPlan() {
    state.updatedAt = null;
    state.revision = 0;
    setEditorValue("");
  }

  function markDirty(next = true) {
    state.dirty = Boolean(next);
    if (!state.dirty) state.drafts.delete(state.chatJid);
    renderChrome();
  }

  async function ensureEditor() {
    if (state.editorView || state.fallbackTextarea) return;
    if (state.editorLoadPromise) return state.editorLoadPromise;
    state.editorLoadPromise = createCodeMirrorEditor().catch((error) => {
      console.warn("[plan-sidebar] Falling back to textarea editor", error);
      createTextareaEditor();
    }).finally(() => {
      state.editorLoadPromise = null;
    });
    return state.editorLoadPromise;
  }

  async function createCodeMirrorEditor() {
    const cm = await import("../vendor/codemirror.js");
    state.cm = cm;
    state.editorThemeCompartment = new cm.Compartment();
    editorHost.textContent = "";
    const extensions = [
      cm.minimalSetup,
      cm.markdown?.() || [],
      cm.EditorState.tabSize.of(2),
      cm.EditorView.lineWrapping,
      state.editorThemeCompartment.of(buildEditorThemeExtensions(cm)),
      buildPlanDecorationsExtension(cm),
      cm.EditorView.updateListener.of((update) => {
        if (!update.docChanged || state.applyingEditorValue) return;
        state.markdown = update.state.doc.toString();
        state.editRevision += 1;
        markDirty(true);
      }),
    ];
    state.editorView = new cm.EditorView({
      state: cm.EditorState.create({ doc: state.markdown || "", extensions }),
      parent: editorHost,
    });
    ensureThemeObserver();
  }

  function createTextareaEditor() {
    if (state.fallbackTextarea) return;
    editorHost.textContent = "";
    const textarea = document.createElement("textarea");
    textarea.className = "plan-sidebar-textarea plan-sidebar-markdown-source";
    textarea.spellcheck = false;
    textarea.wrap = "soft";
    textarea.value = state.markdown || "";
    textarea.addEventListener("input", () => {
      state.markdown = textarea.value;
      state.editRevision += 1;
      markDirty(true);
    });
    editorHost.appendChild(textarea);
    state.fallbackTextarea = textarea;
    state.livePreviewHost = null;
  }

  function buildPlanDecorationsExtension(cm) {
    const checklistRe = /^(\s*(?:[-*+]|\d+[.)])\s+)(\[([ xX-])\])(\s*)(.*)$/;
    function buildDecorations(view) {
      const builder = new cm.RangeSetBuilder();
      const visible = view.visibleRanges?.length ? view.visibleRanges : [{ from: 0, to: view.state.doc.length }];
      for (const range of visible) {
        const fromLine = view.state.doc.lineAt(range.from);
        const toLine = view.state.doc.lineAt(Math.max(range.from, range.to));
        for (let lineNo = fromLine.number; lineNo <= toLine.number; lineNo += 1) {
          const line = view.state.doc.line(lineNo);
          const match = line.text.match(checklistRe);
          if (!match) continue;
          const marker = match[3];
          const status = marker.toLowerCase() === "x" ? "completed" : marker === "-" ? "current" : "pending";
          const markerFrom = line.from + match[1].length;
          const markerTo = markerFrom + match[2].length;
          const textFrom = markerTo + match[4].length;
          builder.add(line.from, line.from, cm.Decoration.line({ class: `plan-sidebar-cm-line plan-sidebar-cm-line-${status}` }));
          builder.add(markerFrom, markerTo, cm.Decoration.mark({ class: `plan-sidebar-cm-checkbox plan-sidebar-cm-checkbox-${status}` }));
          if (textFrom < line.to) builder.add(textFrom, line.to, cm.Decoration.mark({ class: `plan-sidebar-cm-text plan-sidebar-cm-text-${status}` }));
        }
      }
      return builder.finish();
    }
    return cm.ViewPlugin.fromClass(class {
      constructor(view) { this.decorations = buildDecorations(view); }
      update(update) {
        if (update.docChanged || update.viewportChanged || update.selectionSet) this.decorations = buildDecorations(update.view);
      }
    }, { decorations: (value) => value.decorations });
  }

  function focusEditor() {
    if (state.editorView) state.editorView.focus();
    else state.fallbackTextarea?.focus();
  }

  function buildEditorThemeExtensions(cm) {
    const mode = getThemeMode();
    const accent = readCssVar("--accent-color", "#1d9bf0");
    const rgb = colorToRgb(accent) || "29, 155, 240";
    const baseTheme = (mode === "light" ? cm.githubLight : cm.githubDark) || [];
    return [
      baseTheme,
      cm.EditorView.theme({
        "&": {
          height: "100%",
          background: "var(--bg-primary,#0b1020)",
          color: "var(--text-primary,#e5e7eb)",
          fontSize: "13px",
        },
        ".cm-scroller": {
          fontFamily: "var(--font-mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace)",
          lineHeight: "1.45",
          background: "var(--bg-primary,#0b1020)",
        },
        ".cm-content": {
          padding: "12px",
          caretColor: accent,
        },
        ".cm-gutters": { display: "none" },
        ".cm-line": {
          color: "var(--text-primary,#e5e7eb)",
          padding: "1px 8px",
          borderLeft: "3px solid transparent",
          borderRadius: "6px",
        },
        ".cm-lineWrapping .cm-line": {
          overflowWrap: "anywhere",
        },
        ".cm-cursor, .cm-dropCursor": {
          borderLeftColor: accent,
          borderLeftWidth: "2px",
        },
        "&.cm-focused .cm-cursor": {
          borderLeftColor: accent,
          borderLeftWidth: "2px",
        },
        "&.cm-focused .cm-selectionBackground, .cm-selectionBackground": {
          backgroundColor: `rgba(${rgb}, 0.22) !important`,
        },
        ".cm-activeLine": { backgroundColor: `rgba(${rgb}, 0.07)` },
        ".cm-selectionMatch": { backgroundColor: `rgba(${rgb}, 0.16)` },
        ".cm-focused": { outline: "none" },
      }),
    ];
  }

  function applyEditorTheme() {
    if (!state.editorView || !state.cm || !state.editorThemeCompartment) return;
    state.editorView.dispatch({
      effects: state.editorThemeCompartment.reconfigure(buildEditorThemeExtensions(state.cm)),
    });
  }

  function ensureThemeObserver() {
    if (state.themeObserver || typeof MutationObserver === "undefined") return;
    const observer = new MutationObserver(() => applyEditorTheme());
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme", "data-color-theme", "style"] });
    if (document.body) observer.observe(document.body, { attributes: true, attributeFilter: ["class", "data-theme"] });
    state.themeObserver = observer;
  }

  async function apiJson(url, options) {
    const response = await fetch(url, { credentials: "same-origin", ...options });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload?.ok === false) throw new Error(payload?.error || `${response.status} ${response.statusText}`);
    return payload;
  }

  function planUrl(chatJid = state.chatJid) {
    return `/sessions/${encodeURIComponent(chatJid)}/plan`;
  }

  function beginRequest() {
    const request = beginPlanRequest(state);
    state.loading = true;
    renderChrome();
    return request;
  }

  function isCurrentRequest(request) {
    return isCurrentPlanRequest(state, request);
  }

  function drainPendingRemoteRefresh() {
    const hadPendingRemoteRefresh = state.pendingRemoteRefresh && state.pendingRemoteRevision > state.revision;
    const remoteLabel = state.pendingRemoteLabel;
    state.pendingRemoteRefresh = false;
    state.pendingRemoteLabel = "remote";
    if (hadPendingRemoteRefresh && state.dirty) {
      setStatus("Plan changed remotely; save or refresh to update.", "warning");
    }
    renderChrome();
    if (hadPendingRemoteRefresh && !state.dirty) {
      void loadPlan({ preserveDirty: true, remote: true, remoteLabel });
    }
  }

  function finishRequest(request, { drainPending = true } = {}) {
    if (!isCurrentRequest(request)) return false;
    state.loading = false;
    if (drainPending) drainPendingRemoteRefresh();
    else renderChrome();
    return true;
  }

  async function loadPlan({ preserveDirty = false, remote = false, remoteLabel = "remote" } = {}) {
    if (state.loading) {
      if (remote) {
        state.pendingRemoteRefresh = true;
        state.pendingRemoteLabel = remoteLabel;
      }
      return;
    }
    if (preserveDirty && state.dirty) {
      if (remote) setStatus("Plan changed remotely; save or refresh to update.", "warning");
      return;
    }
    const request = beginRequest();
    try {
      const plan = await apiJson(planUrl(request.chatJid));
      if (!canApplyPlanResponse(state, request, preserveDirty)) {
        if (isCurrentRequest(request) && remote) setStatus("Plan changed remotely; save or refresh to update.", "warning");
        return;
      }
      state.updatedAt = plan.updated_at || null;
      state.revision = plan.revision;
      setEditorValue(plan.markdown || "");
      markDirty(false);
      const loadedAt = formatTime(state.updatedAt);
      setStatus(remote
        ? `Updated from ${remoteLabel}${loadedAt ? ` ${loadedAt}` : ""}`
        : state.updatedAt ? `Loaded ${loadedAt}` : "Loaded default plan");
    } catch (error) {
      if (isCurrentRequest(request)) setStatus(String(error?.message || error), "error");
    } finally {
      finishRequest(request);
    }
  }

  function handleRemotePlanUpdate(event) {
    const payload = event?.detail || {};
    const chatJid = normalizeChatJid(payload.session_id);
    if (chatJid !== state.chatJid || !Number.isInteger(payload.revision) || payload.revision <= state.revision) return;
    state.pendingRemoteRevision = Math.max(state.pendingRemoteRevision, payload.revision);
    const remoteLabel = payload.source === "tool" ? "model" : payload.action === "reset" ? "reset" : "remote";
    void loadPlan({ preserveDirty: true, remote: true, remoteLabel });
  }

  async function resetPlan() {
    if (state.loading || !confirm("Reset this chat plan to an empty checklist?")) return null;
    const request = beginRequest();
    try {
      const payload = await apiJson(planUrl(request.chatJid), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ markdown: '', expected_revision: state.revision }),
      });
      if (!isCurrentRequest(request)) return null;
      const plan = payload.plan || payload;
      state.updatedAt = plan.updated_at || null;
      state.revision = plan.revision;
      if (canApplyPlanResponse(state, request)) {
        setEditorValue(plan.markdown || "");
        markDirty(false);
        setStatus(`Reset ${formatTime(state.updatedAt)}`, "ok");
      } else {
        setStatus("Reset completed; newer edits are unsaved.", "warning");
      }
      return plan;
    } catch (error) {
      if (isCurrentRequest(request)) setStatus(String(error?.message || error), "error");
      throw error;
    } finally {
      finishRequest(request);
    }
  }

  async function savePlan({ drainPending = true } = {}) {
    if (state.loading) throw new Error('Plan request already in progress');
    const markdown = getEditorValue();
    const revision = state.revision;
    const request = beginRequest();
    try {
      const payload = await apiJson(planUrl(request.chatJid), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ markdown, expected_revision: revision }),
      });
      if (!isCurrentRequest(request)) return null;
      const plan = payload.plan || payload;
      state.updatedAt = plan.updated_at || null;
      state.revision = plan.revision;
      if (getEditorValue() === markdown) {
        setEditorValue(plan.markdown ?? markdown);
        markDirty(false);
        setStatus(`Saved ${formatTime(state.updatedAt)}`, "ok");
      } else {
        setStatus("Saved previous edits; newer changes are unsaved.", "warning");
      }
      return plan;
    } catch (error) {
      if (isCurrentRequest(request)) setStatus(String(error?.message || error), "error");
      throw error;
    } finally {
      finishRequest(request, { drainPending });
    }
  }

  function buildPlanSubmissionPrompt(markdown) {
    return [
      "Use the shared session Plan tool checklist as the working plan (vibes_plan in Pi, plan over MCP). Read the latest revision before changing it.",
      "",
      "- Continue with the next relevant item.",
      "- Update the plan as work changes or completes.",
      "- Prefer `plan` `action=update` with structured items for full-plan updates.",
      "- Use `action=edit` with exact whole-line replacements for small checklist updates.",
      "- Use `action=write` only for a full raw Markdown rewrite.",
      "- Keep at most one item in progress (`[-]`).",
      "- Report periodically on progress and next steps.",
      "",
      "```markdown",
      markdown,
      "```",
    ].join("\n");
  }

  async function submitToModel() {
    const chatJid = state.chatJid;
    let plan;
    try {
      plan = await savePlan({ drainPending: false });
    } catch (error) {
      drainPendingRemoteRefresh();
      throw error;
    }
    if (!plan || chatJid !== state.chatJid) {
      drainPendingRemoteRefresh();
      return;
    }
    const markdown = plan.markdown || "";
    if (!markdown.trim()) {
      drainPendingRemoteRefresh();
      setStatus("Plan is empty; nothing to submit.", "error");
      return;
    }
    const request = beginRequest();
    try {
      const content = buildPlanSubmissionPrompt(markdown);
      await apiJson('/agent/default/message', {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, mode: "auto", session_id: request.chatJid }),
      });
      if (isCurrentRequest(request)) setStatus("Submitted to model.", "ok");
    } catch (error) {
      if (isCurrentRequest(request)) setStatus(String(error?.message || error), "error");
    } finally {
      finishRequest(request);
    }
  }

  function updateChatJid() {
    const next = getCurrentChatJid();
    if (next === state.chatJid) return;
    invalidatePlanRequests(state);
    if (state.dirty) state.drafts.set(state.chatJid, { markdown: getEditorValue(), revision: state.revision, updatedAt: state.updatedAt });
    else state.drafts.delete(state.chatJid);
    state.chatJid = next;
    state.editRevision += 1;
    state.dirty = false;
    state.loading = false;
    state.pendingRemoteRefresh = false;
    state.pendingRemoteLabel = "remote";
    clearDisplayedPlan();
    const draft = state.drafts.get(next);
    if (draft) {
      state.revision = draft.revision;
      state.updatedAt = draft.updatedAt;
      setEditorValue(draft.markdown);
      state.dirty = true;
      setStatus('Restored unsaved plan edits.', 'warning');
    } else setStatus('');
    renderChrome();
    loadPlan({ preserveDirty: true });
  }

  toggle.addEventListener("click", () => {
    if (state.open) closeSidebar({ autosave: true }).catch(() => undefined);
    else setOpen(true);
  });
  refreshButton.addEventListener("click", () => {
    if (state.dirty && !confirm('Discard unsaved Plan edits and load the current shared Plan?')) return;
    loadPlan();
  });
  resetButton.addEventListener("click", () => resetPlan().catch(() => undefined));
  saveButton.addEventListener("click", () => savePlan().catch(() => undefined));
  submitButton.addEventListener("click", () => submitToModel().catch(() => undefined));

  resizer.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    state.width = clampWidth(state.width + (event.key === 'ArrowLeft' ? 20 : -20));
    localStorage.setItem(STORAGE_WIDTH, String(state.width));
    renderChrome();
  });
  resizer.addEventListener('pointerdown', event => {
    event.preventDefault();
    state.resizeStart = { x: event.clientX, width: state.width, pointerId: event.pointerId };
    resizer.setPointerCapture?.(event.pointerId);
    document.body.classList.add('plan-sidebar-resizing');
  });
  resizer.addEventListener('pointermove', event => {
    if (!state.resizeStart || event.pointerId !== state.resizeStart.pointerId) return;
    state.width = clampWidth(state.resizeStart.width + (state.resizeStart.x - event.clientX));
    localStorage.setItem(STORAGE_WIDTH, String(state.width));
    renderChrome();
  });
  const finishResize = event => {
    if (!state.resizeStart || event.pointerId !== state.resizeStart.pointerId) return;
    state.resizeStart = null;
    document.body.classList.remove('plan-sidebar-resizing');
  };
  resizer.addEventListener('pointerup', finishResize);
  resizer.addEventListener('pointercancel', finishResize);

  window.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !state.open) return;
    event.preventDefault();
    event.stopPropagation();
    closeSidebar({ autosave: true }).catch(() => undefined);
  }, true);
  window.addEventListener("vibes:session-changed", updateChatJid);
  window.addEventListener("popstate", updateChatJid);
  window.addEventListener("vibes:plan-updated", handleRemotePlanUpdate);
  window.addEventListener('beforeunload', event => {
    if (state.dirty || state.drafts.size) { event.preventDefault(); event.returnValue = ''; }
  });
  window.addEventListener('vibes:reconnected', () => loadPlan({ preserveDirty: true, remote: true }));

  renderChrome();
  if (state.open) setOpen(true);
  else loadPlan({ preserveDirty: true });
}

function getPlanProgress(markdown) {
  const lines = String(markdown || "").split(/\r?\n/);
  let total = 0;
  let complete = 0;
  let inProgress = 0;
  for (const line of lines) {
    const match = line.match(/^\s*(?:[-*+]|\d+[.)])\s+\[([ xX-])\](?:\s|$)/);
    if (!match) continue;
    total += 1;
    if (match[1].toLowerCase() === "x") complete += 1;
    if (match[1] === "-") inProgress += 1;
  }
  return {
    total,
    complete,
    inProgress,
    percent: total ? Math.round((complete / total) * 100) : 0,
  };
}

function formatProgressText(progress) {
  if (!progress?.total) return "No checklist items";
  const suffix = progress.inProgress ? ` • ${progress.inProgress} in progress` : "";
  return `${progress.complete}/${progress.total} items complete (${progress.percent}%)${suffix}`;
}

function getCurrentChatJid() {
  return normalizeChatJid(globalThis.__vibesCurrentSession);
}

function normalizeChatJid(value) {
  const trimmed = typeof value === "string" ? value.trim() : "";
  return trimmed || DEFAULT_CHAT_JID;
}

function clampWidth(value) {
  return Math.max(300, Math.min(620, Math.trunc(value || 380)));
}

function formatTime(value) {
  if (!value) return "";
  try { return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); }
  catch { return String(value); }
}

function getThemeMode() {
  const root = document.documentElement;
  const body = document.body;
  const explicit = root?.getAttribute?.("data-theme")?.toLowerCase?.() || body?.getAttribute?.("data-theme")?.toLowerCase?.() || "";
  if (explicit === "light" || explicit === "dark") return explicit;
  if (root?.classList?.contains("light") || body?.classList?.contains("light")) return "light";
  if (root?.classList?.contains("dark") || body?.classList?.contains("dark")) return "dark";
  return globalThis.matchMedia?.("(prefers-color-scheme: light)")?.matches ? "light" : "dark";
}

function readCssVar(name, fallback) {
  try {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  } catch {
    return fallback;
  }
}

function colorToRgb(value) {
  const text = String(value || "").trim();
  const hex = text.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i)?.[1];
  if (hex) {
    const full = hex.length === 3 ? hex.split("").map((ch) => ch + ch).join("") : hex;
    return `${parseInt(full.slice(0, 2), 16)}, ${parseInt(full.slice(2, 4), 16)}, ${parseInt(full.slice(4, 6), 16)}`;
  }
  const rgb = text.match(/^rgba?\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i);
  return rgb ? `${rgb[1]}, ${rgb[2]}, ${rgb[3]}` : null;
}

function injectStyles() {
  if (document.getElementById("plan-sidebar-styles")) return;
  const style = document.createElement("style");
  style.id = "plan-sidebar-styles";
  style.textContent = `
    .plan-sidebar-toggle {
      display: flex;
      position: fixed;
      right: 0;
      top: 50%;
      transform: translateY(-50%);
      z-index: 120;
      background: var(--bg-secondary,#111827);
      border: 1px solid var(--border-color, rgba(148,163,184,.35));
      border-right: 0;
      color: var(--text-secondary,#cbd5e1);
      padding: 0;
      width: var(--workspace-tab-width, 20px);
      height: 52px;
      border-radius: var(--radius-md, 8px) 0 0 var(--radius-md, 8px);
      box-shadow: none;
      cursor: pointer;
      align-items: center;
      justify-content: center;
      transition: right var(--ui-transition-fast, .18s), background-color var(--ui-transition-fast, .18s), color var(--ui-transition-fast, .18s), border-color var(--ui-transition-fast, .18s);
    }
    .plan-sidebar-toggle:hover { color: var(--text-primary,#f8fafc); border-color: var(--accent-color,#2563eb); }
    .plan-sidebar-toggle svg { width: 12px; height: 12px; flex-shrink: 0; transition: transform var(--ui-transition-fast, .18s); }
    .plan-sidebar-toggle-meter {
      position: absolute;
      left: 3px;
      top: 8px;
      bottom: 8px;
      width: 3px;
      border-radius: 999px;
      overflow: hidden;
      background: color-mix(in srgb, var(--border-color, rgba(148,163,184,.45)) 72%, transparent);
      opacity: .95;
    }
    .plan-sidebar-toggle-meter-fill {
      position: absolute;
      left: 0;
      right: 0;
      bottom: 0;
      height: 0%;
      border-radius: 999px;
      background: var(--accent-color,#2563eb);
      transition: height var(--ui-transition-fast, .18s);
    }
    .plan-sidebar-root:not(.has-checklist) .plan-sidebar-toggle-meter { opacity: .35; }
    .plan-sidebar-root.open .plan-sidebar-toggle-meter { display: none; }
    .plan-sidebar-sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
    .plan-sidebar-root.open .plan-sidebar-toggle {
      right: var(--plan-sidebar-width, 380px);
      background: var(--bg-primary,#0b1020);
      color: var(--text-primary,#f8fafc);
      border-color: var(--border-color, rgba(148,163,184,.28));
      border-right: 0;
    }
    .plan-sidebar-root.open .plan-sidebar-toggle svg { transform: rotate(180deg); }
    .plan-sidebar-panel {
      --plan-sidebar-width: 380px;
      position: fixed;
      top: 0;
      right: 0;
      bottom: 0;
      z-index: 119;
      width: 380px;
      transform: translateX(100%);
      transition: transform .18s ease;
      background: var(--bg-primary,#0b1020);
      border-left: 1px solid var(--border-color, rgba(148,163,184,.28));
      box-shadow: none;
      display: flex;
      flex-direction: column;
      color: var(--text-primary,#e5e7eb);
    }
    .plan-sidebar-panel::before {
      content: "";
      position: absolute;
      top: 0;
      bottom: 0;
      left: -18px;
      width: 18px;
      pointer-events: none;
      opacity: 0;
      background: linear-gradient(to left, rgba(0,0,0,.16), rgba(0,0,0,0));
      transition: opacity .18s ease;
    }
    .plan-sidebar-root.open .plan-sidebar-panel { transform: translateX(0); }
    .plan-sidebar-root.open .plan-sidebar-panel::before { opacity: 1; }
    .plan-sidebar-header {
      min-height: 34px;
      padding: 5px 10px;
      border-bottom: 1px solid var(--border-color, rgba(148,163,184,.25));
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .plan-sidebar-title { flex: 0 0 auto; font-weight: 650; font-size: 12px; letter-spacing: .01em; }
    .plan-sidebar-subtitle { color: var(--text-secondary,#94a3b8); font-size: 10px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .plan-sidebar-progress {
      border-bottom: 1px solid var(--border-color, rgba(148,163,184,.2));
      padding: 8px 10px 9px;
      background: var(--bg-secondary,#111827);
      display: grid;
      gap: 6px;
    }
    .plan-sidebar-progress-meta {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      color: var(--text-secondary,#94a3b8);
      font-size: 10px;
      line-height: 1.2;
    }
    .plan-sidebar-progress-label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .plan-sidebar-progress-percent { flex: 0 0 auto; font-variant-numeric: tabular-nums; color: var(--text-primary,#e5e7eb); }
    .plan-sidebar-progress-track {
      height: 6px;
      border-radius: 999px;
      overflow: hidden;
      background: color-mix(in srgb, var(--border-color, rgba(148,163,184,.35)) 72%, transparent);
    }
    .plan-sidebar-progress-fill {
      width: 0%;
      height: 100%;
      border-radius: inherit;
      background: var(--accent-color,#2563eb);
      transition: width var(--ui-transition-fast, .18s);
    }
    .plan-sidebar-editor { flex: 1; min-height: 0; overflow: hidden; display: flex; }
    .plan-sidebar-editor .cm-editor {
      width: 100%;
      height: 100%;
      flex: 1 1 auto;
      min-width: 0;
      min-height: 0;
    }
    .plan-sidebar-editor .cm-scroller { overflow: auto; }
    .plan-sidebar-editor .cm-line.plan-sidebar-cm-line-current {
      background: color-mix(in srgb, var(--accent-color,#2563eb) 12%, transparent);
      border-left-color: var(--accent-color,#2563eb);
    }
    .plan-sidebar-editor .cm-line.plan-sidebar-cm-line-completed { opacity: .76; }
    .plan-sidebar-cm-checkbox {
      display: inline-block;
      min-width: 3ch;
      text-align: center;
      border-radius: 5px;
      font-weight: 700;
      color: var(--text-secondary,#94a3b8);
      background: color-mix(in srgb, var(--border-color, rgba(148,163,184,.45)) 36%, transparent);
    }
    .plan-sidebar-cm-checkbox-completed {
      color: var(--success-color,#22c55e);
      background: color-mix(in srgb, var(--success-color,#22c55e) 15%, transparent);
    }
    .plan-sidebar-cm-checkbox-current {
      color: var(--accent-color,#60a5fa);
      background: color-mix(in srgb, var(--accent-color,#60a5fa) 18%, transparent);
    }
    .plan-sidebar-cm-text-completed { text-decoration: line-through; color: var(--text-secondary,#94a3b8); }
    .plan-sidebar-cm-text-current { color: var(--text-primary,#f8fafc); font-weight: 650; }
    .plan-sidebar-markdown-source { display: block; }
    .plan-sidebar-textarea {
      width: 100%;
      height: 100%;
      flex: 1 1 auto;
      min-height: 0;
      border: 0;
      resize: none;
      outline: none;
      padding: 12px;
      box-sizing: border-box;
      overflow: auto;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      tab-size: 2;
      background: var(--bg-primary,#0b1020);
      color: var(--text-primary,#e5e7eb);
      caret-color: var(--accent-color,#1d9bf0);
      font: 13px/1.45 var(--font-mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace);
    }
    .plan-sidebar-footer {
      border-top: 1px solid var(--border-color, rgba(148,163,184,.25));
      padding: 10px 12px;
      display: grid;
      gap: 8px;
      background: var(--bg-secondary,#111827);
    }
    .plan-sidebar-status { min-height: 16px; color: var(--text-secondary,#94a3b8); font-size: 11px; }
    .plan-sidebar-status[data-kind="ok"] { color: var(--accent-color,#60a5fa); }
    .plan-sidebar-status[data-kind="error"] { color: var(--danger-color,#f87171); }
    .plan-sidebar-actions { display: flex; gap: 8px; justify-content: flex-end; flex-wrap: wrap; }
    .plan-sidebar-actions button {
      border: 1px solid var(--border-color, rgba(148,163,184,.28));
      border-radius: 8px;
      padding: 6px 10px;
      background: var(--bg-primary,#0b1020);
      color: var(--text-primary,#e5e7eb);
      cursor: pointer;
      font-size: 12px;
    }
    .plan-sidebar-actions button:disabled { opacity: .45; cursor: default; }
    .plan-sidebar-submit { background: var(--accent-color,#2563eb) !important; border-color: var(--accent-color,#2563eb) !important; color: white !important; }
    .plan-sidebar-resizer { position: absolute; top: 0; bottom: 0; left: -4px; width: 8px; cursor: ew-resize; }
    .plan-sidebar-resizing, .plan-sidebar-resizing * { cursor: ew-resize !important; user-select: none !important; }
    @media (max-width: 760px) {
      .plan-sidebar-panel { width: min(92vw, 420px) !important; }
      .plan-sidebar-root.open .plan-sidebar-toggle { right: min(92vw, 420px); }
    }
  `;
  document.head.appendChild(style);
}
