(function () {
  const API_URL = "http://127.0.0.1:8765/api/greeting";
  const RESUME_API_URL = "http://127.0.0.1:8765/api/resume-polish";
  const PANEL_ID = "boss-agent-greeting-panel";
  const MINI_ID = "boss-agent-greeting-mini";
  const AUTO_PANEL_ID = "boss-agent-auto-panel";

  const isListPage = location.pathname === "/web/geek/jobs";
  const isDetailPage = location.pathname.startsWith("/job_detail/");
  const isChatPage = location.pathname === "/web/geek/chat";

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function normalizeText(text) {
    return (text || "").replace(/\s+/g, " ").trim();
  }

  function isVisible(element) {
    if (!element) {
      return false;
    }
    const rect = element.getBoundingClientRect();
    const style = window.getComputedStyle(element);
    return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
  }

  function textOf(selector, root = document) {
    const node = root.querySelector(selector);
    return normalizeText(node ? node.textContent : "");
  }

  function findTextBySelectors(selectors) {
    for (const selector of selectors) {
      const value = textOf(selector);
      if (value) {
        return value;
      }
    }
    return "";
  }

  function runtimeMessage(message) {
    return new Promise((resolve) => {
      if (!chrome?.runtime?.sendMessage) {
        resolve({ ok: false, error: "Chrome runtime is unavailable." });
        return;
      }
      chrome.runtime.sendMessage(message, (response) => {
        if (chrome.runtime.lastError) {
          resolve({ ok: false, error: chrome.runtime.lastError.message });
          return;
        }
        resolve(response || { ok: false, error: "Empty runtime response." });
      });
    });
  }

  function extractCompany() {
    const candidates = [
      ".company-info .name",
      ".company-name",
      "[class*='company'] [class*='name']",
      "[ka='job-detail-company']"
    ];
    const company = findTextBySelectors(candidates);
    if (company && company.length <= 80) {
      return company;
    }

    const text = normalizeText(document.body.textContent);
    const match = text.match(/公司基本信息\s+(.+?)\s+(?:[A-D]轮|未融资|已上市|不需要融资)/);
    return match ? match[1] : "";
  }

  function extractJobTitle() {
    const title = findTextBySelectors([
      ".job-title",
      ".name h1",
      "h1",
      "[class*='job-title']",
      "[class*='jobName']"
    ]);
    if (title) {
      return title.replace(/\s+\d+[Kk].*$/, "").trim();
    }
    return normalizeText(document.title.split("-")[0] || "");
  }

  function elementLooksLikeHeading(element) {
    const text = normalizeText(element.textContent);
    return text === "职位描述" || text.startsWith("职位描述 ");
  }

  function getDescriptionFromHeading(heading) {
    let current = heading;
    for (let depth = 0; current && depth < 6; depth += 1) {
      const text = normalizeText(current.textContent);
      if (
        text.includes("职位描述") &&
        text.length > 120 &&
        text.length < 12000 &&
        !text.includes("公司基本信息")
      ) {
        return text.replace(/^职位描述\s*/, "").trim();
      }
      current = current.parentElement;
    }
    return "";
  }

  function extractDescription() {
    const knownContainers = [
      ".job-sec-text",
      ".job-detail-section",
      ".job-detail",
      "[class*='job-sec']",
      "[class*='description']"
    ];
    for (const selector of knownContainers) {
      const value = textOf(selector);
      if (value.length > 120 && value.length < 12000) {
        return value.replace(/^职位描述\s*/, "").trim();
      }
    }

    const nodes = Array.from(document.querySelectorAll("h2,h3,div,section"));
    const heading = nodes.find(elementLooksLikeHeading);
    if (heading) {
      const fromHeading = getDescriptionFromHeading(heading);
      if (fromHeading) {
        return fromHeading;
      }
    }

    const pageText = normalizeText(document.body.textContent);
    const start = pageText.indexOf("职位描述");
    if (start >= 0) {
      const endMarkers = ["公司基本信息", "工商信息", "职位发布者", "相似职位", "推荐职位"];
      const afterStart = pageText.slice(start + "职位描述".length);
      const end = endMarkers
        .map((marker) => afterStart.indexOf(marker))
        .filter((index) => index > 0)
        .sort((a, b) => a - b)[0];
      return normalizeText(end ? afterStart.slice(0, end) : afterStart.slice(0, 6000));
    }
    return "";
  }

  function extractJobData() {
    return {
      job_title: extractJobTitle(),
      company: extractCompany(),
      description: extractDescription()
    };
  }

  async function waitForJobData(timeoutMs = 9000) {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      const data = extractJobData();
      if (data.description && data.description.length >= 20) {
        return data;
      }
      await sleep(450);
    }
    return extractJobData();
  }

  async function fetchGreeting(jobData, resumeProfile) {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...jobData,
        resume_profile: resumeProfile || "auto"
      })
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || `HTTP ${response.status}`);
    }
    return data;
  }

  function createPanel() {
    const panel = document.createElement("div");
    panel.id = PANEL_ID;
    panel.className = "boss-agent-panel";
    panel.innerHTML = `
      <div class="boss-agent-header">
        <span>BOSS 招呼助手</span>
        <button class="boss-agent-close" type="button" title="收起">×</button>
      </div>
      <div class="boss-agent-body">
        <select class="boss-agent-select" title="简历倾向">
          <option value="auto">自动选择简历</option>
          <option value="agent">Agent 开发简历</option>
          <option value="fde">FDE / 交付简历</option>
        </select>
        <div class="boss-agent-row">
          <button class="boss-agent-primary" type="button">生成招呼</button>
          <button class="boss-agent-polish" type="button">润色简历</button>
          <button class="boss-agent-secondary" type="button" disabled>复制</button>
        </div>
        <div class="boss-agent-row boss-agent-auto-actions" hidden>
          <button class="boss-agent-done" type="button">已发送并关闭</button>
          <button class="boss-agent-skip" type="button">跳过并关闭</button>
        </div>
        <textarea class="boss-agent-textarea" placeholder="生成结果会出现在这里"></textarea>
        <div class="boss-agent-status"></div>
      </div>
    `;
    document.body.appendChild(panel);
    return panel;
  }

  function createMiniButton() {
    const button = document.createElement("button");
    button.id = MINI_ID;
    button.className = "boss-agent-mini";
    button.type = "button";
    button.textContent = "招呼助手";
    button.addEventListener("click", () => {
      button.remove();
      wireDetailPanel(createPanel());
    });
    document.body.appendChild(button);
  }

  function setStatus(panel, message, tone) {
    const status = panel.querySelector(".boss-agent-status");
    status.textContent = message || "";
    status.dataset.tone = tone || "";
  }

  async function generate(panel) {
    const primary = panel.querySelector(".boss-agent-primary");
    const polish = panel.querySelector(".boss-agent-polish");
    const copy = panel.querySelector(".boss-agent-secondary");
    const output = panel.querySelector(".boss-agent-textarea");
    const select = panel.querySelector(".boss-agent-select");
    const jobData = extractJobData();

    if (!jobData.description || jobData.description.length < 20) {
      setStatus(panel, "没有识别到职位描述，可以刷新页面后重试。", "error");
      return "";
    }

    primary.disabled = true;
    polish.disabled = true;
    copy.disabled = true;
    setStatus(panel, "正在生成...");
    output.value = "";

    try {
      const data = await fetchGreeting(jobData, select.value);
      output.value = data.greeting;
      copy.disabled = !data.greeting;
      setStatus(panel, `已生成，使用 ${data.resume_profile === "agent" ? "Agent" : "FDE"} 简历。`);
      return data.greeting;
    } catch (error) {
      setStatus(panel, `生成失败：${error.message}`, "error");
      return "";
    } finally {
      primary.disabled = false;
      polish.disabled = false;
    }
  }

  async function polishResume(panel) {
    const primary = panel.querySelector(".boss-agent-primary");
    const polish = panel.querySelector(".boss-agent-polish");
    const copy = panel.querySelector(".boss-agent-secondary");
    const output = panel.querySelector(".boss-agent-textarea");
    const select = panel.querySelector(".boss-agent-select");
    const jobData = extractJobData();

    if (!jobData.description || jobData.description.length < 20) {
      setStatus(panel, "没有识别到职位描述，可以刷新页面后重试。", "error");
      return;
    }

    primary.disabled = true;
    polish.disabled = true;
    copy.disabled = true;
    setStatus(panel, "正在润色简历，通常需要十几秒...");
    output.value = "";

    try {
      const response = await fetch(RESUME_API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...jobData,
          resume_profile: select.value
        })
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || `HTTP ${response.status}`);
      }
      output.value = data.file_path;
      copy.disabled = false;
      setStatus(panel, `已生成 ${data.resume_profile === "agent" ? "Agent" : "FDE"} 定制简历。`);
    } catch (error) {
      setStatus(panel, `润色失败：${error.message}`, "error");
    } finally {
      primary.disabled = false;
      polish.disabled = false;
    }
  }

  async function copyResult(panel) {
    const output = panel.querySelector(".boss-agent-textarea");
    if (!output.value) {
      return;
    }
    await navigator.clipboard.writeText(output.value);
    setStatus(panel, "已复制。");
  }

  function isInsideAgentPanel(node) {
    return Boolean(node.closest(`#${PANEL_ID},#${AUTO_PANEL_ID},#${MINI_ID}`));
  }

  function clickableTargetFor(node) {
    if (!node || isInsideAgentPanel(node)) {
      return null;
    }
    const target = node.matches("button,a,[role='button'],.btn,[class*='btn']")
      ? node
      : node.closest("button,a,[role='button'],.btn,[class*='btn']");
    if (!target || isInsideAgentPanel(target) || !isVisible(target)) {
      return null;
    }
    if (target.disabled || target.classList.contains("disabled") || target.getAttribute("aria-disabled") === "true") {
      return null;
    }
    return target;
  }

  function findClickableByText(texts, root = document) {
    const expected = Array.isArray(texts) ? texts : [texts];
    const nodes = Array.from(root.querySelectorAll("button,a,[role='button'],.btn,[class*='btn'],span,div"));
    const matches = [];
    for (const node of nodes) {
      const text = normalizeText(node.textContent);
      if (!text || !expected.some((value) => text === value || text.includes(value))) {
        continue;
      }
      const target = clickableTargetFor(node);
      if (target) {
        matches.push(target);
      }
    }
    matches.sort((a, b) => {
      const aText = normalizeText(a.textContent);
      const bText = normalizeText(b.textContent);
      const aExact = expected.some((value) => aText === value) ? 0 : 1;
      const bExact = expected.some((value) => bText === value) ? 0 : 1;
      return aExact - bExact || aText.length - bText.length;
    });
    return matches[0] || null;
  }

  function clickElement(element) {
    if (!element) {
      return false;
    }
    element.scrollIntoView({ block: "center", inline: "center" });
    const rect = element.getBoundingClientRect();
    const eventOptions = {
      bubbles: true,
      cancelable: true,
      view: window,
      clientX: rect.left + rect.width / 2,
      clientY: rect.top + rect.height / 2
    };
    for (const type of ["pointerover", "mouseover", "pointerdown", "mousedown", "pointerup", "mouseup"]) {
      const EventClass = type.startsWith("pointer") ? PointerEvent : MouseEvent;
      element.dispatchEvent(new EventClass(type, eventOptions));
    }
    element.click();
    return true;
  }

  async function waitForChatInput(timeoutMs = 12000) {
    const selectors = [
      "#chat-input[contenteditable='true']",
      "textarea",
      "[contenteditable='true']",
      "[class*='chat'] textarea",
      "[class*='input'] textarea",
      "[class*='editor'] [contenteditable='true']"
    ];
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      for (const selector of selectors) {
        const nodes = Array.from(document.querySelectorAll(selector));
        const node = nodes.find(
          (candidate) => !isInsideAgentPanel(candidate) && isVisible(candidate) && !candidate.disabled
        );
        if (node) {
          return node;
        }
      }
      await sleep(400);
    }
    return null;
  }

  function fillInput(input, value) {
    input.focus();
    if (input.isContentEditable) {
      document.execCommand("selectAll", false, null);
      document.execCommand("delete", false, null);
      const inserted = document.execCommand("insertText", false, value);
      if (!inserted) {
        input.textContent = value;
      }
      input.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return;
    }

    const prototype = input instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
    if (descriptor?.set) {
      descriptor.set.call(input, value);
    } else {
      input.value = value;
    }
    input.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  async function waitForSendButton(timeoutMs = 5000) {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      const sendButton = findClickableByText(["发送"]);
      if (sendButton && !sendButton.classList.contains("disabled")) {
        return sendButton;
      }
      await sleep(250);
    }
    return findClickableByText(["发送"]);
  }

  async function sendGreeting(panel) {
    const sendButton = await waitForSendButton();
    if (!sendButton) {
      throw new Error("没有找到发送按钮，请手动发送。");
    }
    if (sendButton.classList.contains("disabled")) {
      throw new Error("发送按钮仍处于禁用状态，请手动检查输入框。");
    }
    clickElement(sendButton);
    await sleep(900);
    setStatus(panel, "已尝试发送。");
  }

  async function clickDialogContinue(timeoutMs = 5000) {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      const dialogButton = document.querySelector(".dialog-wrap [ka='dialog_confirm'], .dialog-wrap .btn-sure");
      if (dialogButton && isVisible(dialogButton) && normalizeText(dialogButton.textContent).includes("继续沟通")) {
        clickElement(dialogButton);
        return true;
      }
      await sleep(250);
    }
    return false;
  }

  async function openCommunication(panel) {
    setStatus(panel, "正在点击沟通入口...");
    const communicate = document.querySelector("a.btn-startchat") || findClickableByText(["立即沟通", "继续沟通"]);
    if (!communicate) {
      throw new Error("没有找到“立即沟通”按钮。");
    }
    clickElement(communicate);
    setStatus(panel, "已点击沟通入口，等待跳转聊天页...");
    await clickDialogContinue();
    const redirectUrl = communicate.getAttribute("redirect-url");
    if (redirectUrl && location.pathname !== "/web/geek/chat") {
      setTimeout(() => {
        if (location.pathname !== "/web/geek/chat") {
          location.href = new URL(redirectUrl, location.origin).href;
        }
      }, 1200);
    }
  }

  async function fillChat(panel, greeting, options) {
    const input = await waitForChatInput();
    if (!input) {
      throw new Error("没有找到聊天输入框。");
    }
    fillInput(input, greeting);
    panel.querySelector(".boss-agent-textarea").value = greeting;
    panel.querySelector(".boss-agent-secondary").disabled = false;
    if (options.autoSend) {
      setStatus(panel, "聊天页已填入，正在发送...");
      await sendGreeting(panel);
      await runtimeMessage({ type: "DETAIL_DONE", detail: "已在聊天页发送招呼。" });
      return;
    }
    setStatus(panel, "已填入聊天框。请确认内容后手动发送，再点“已发送并关闭”。");
  }

  async function runAutoDetailTask(panel, task, options) {
    const actions = panel.querySelector(".boss-agent-auto-actions");
    const output = panel.querySelector(".boss-agent-textarea");
    const select = panel.querySelector(".boss-agent-select");
    select.value = options.resumeProfile || "auto";
    actions.hidden = false;

    try {
      setStatus(panel, `自动任务：识别 ${task.title || "岗位"}...`);
      const jobData = await waitForJobData();
      if (!jobData.description || jobData.description.length < 20) {
        throw new Error("没有识别到职位描述。");
      }

      setStatus(panel, "自动任务：正在生成招呼...");
      const data = await fetchGreeting(jobData, select.value);
      output.value = data.greeting;
      panel.querySelector(".boss-agent-secondary").disabled = false;
      await runtimeMessage({
        type: "SET_CURRENT_GREETING",
        greeting: data.greeting,
        jobData
      });
      await openCommunication(panel);
      setStatus(panel, "已生成招呼，正在进入聊天页。");
    } catch (error) {
      setStatus(panel, `自动任务暂停：${error.message}`, "error");
      actions.hidden = false;
    }
  }

  function wireDetailPanel(panel) {
    panel.querySelector(".boss-agent-primary").addEventListener("click", () => generate(panel));
    panel.querySelector(".boss-agent-polish").addEventListener("click", () => polishResume(panel));
    panel.querySelector(".boss-agent-secondary").addEventListener("click", () => copyResult(panel));
    panel.querySelector(".boss-agent-close").addEventListener("click", () => {
      panel.remove();
      createMiniButton();
    });
    panel.querySelector(".boss-agent-done").addEventListener("click", async () => {
      setStatus(panel, "已标记完成，正在关闭标签页...");
      await runtimeMessage({ type: "DETAIL_DONE", detail: "用户确认已发送。" });
    });
    panel.querySelector(".boss-agent-skip").addEventListener("click", async () => {
      setStatus(panel, "已跳过，正在关闭标签页...");
      await runtimeMessage({ type: "DETAIL_SKIP", detail: "用户跳过该岗位。" });
    });

    const data = extractJobData();
    if (data.description) {
      setStatus(panel, `已识别职位描述约 ${data.description.length} 字。`);
    } else {
      setStatus(panel, "等待岗位详情加载完成。");
      setTimeout(() => {
        const retry = extractJobData();
        if (retry.description) {
          setStatus(panel, `已识别职位描述约 ${retry.description.length} 字。`);
        }
      }, 1200);
    }
  }

  function jobKeyFromUrl(url) {
    try {
      const parsed = new URL(url, location.origin);
      const match = parsed.pathname.match(/\/job_detail\/([^/]+?)(?:\.html)?$/);
      if (match) {
        return match[1].replace(/\.html$/, "");
      }
      return parsed.href;
    } catch (_) {
      return url;
    }
  }

  function jobTitleFromNode(node) {
    const card = node.closest("li,[class*='job'],[class*='card'],[class*='item']") || node;
    const candidates = [
      node,
      card.querySelector("[class*='name']"),
      card.querySelector("[class*='title']"),
      card.querySelector("h3"),
      card.querySelector("h2")
    ].filter(Boolean);
    for (const candidate of candidates) {
      const text = normalizeText(candidate.textContent);
      if (text && text.length <= 80 && !text.includes("查看更多")) {
        return text.replace(/\s+\d+[Kk].*$/, "").trim();
      }
    }
    return "未知岗位";
  }

  function collectJobLinks() {
    const jobs = new Map();
    const anchors = Array.from(document.querySelectorAll("a[href*='/job_detail/']"));
    for (const anchor of anchors) {
      const href = anchor.getAttribute("href");
      if (!href || href.includes("javascript:")) {
        continue;
      }
      const url = new URL(href, location.origin).href;
      const key = jobKeyFromUrl(url);
      if (!key || jobs.has(key)) {
        continue;
      }
      jobs.set(key, {
        key,
        url,
        title: jobTitleFromNode(anchor)
      });
    }
    return Array.from(jobs.values());
  }

  function findScrollableJobList() {
    const selectors = [
      ".job-list-box",
      ".search-job-result",
      ".job-list",
      "[class*='job-list']",
      "[class*='search-job']",
      "[class*='list']"
    ];
    const candidates = selectors
      .flatMap((selector) => Array.from(document.querySelectorAll(selector)))
      .filter((element) => element.scrollHeight > element.clientHeight + 80 && isVisible(element));

    candidates.sort((a, b) => {
      const aJobs = a.querySelectorAll("a[href*='/job_detail/']").length;
      const bJobs = b.querySelectorAll("a[href*='/job_detail/']").length;
      return bJobs - aJobs;
    });
    return candidates[0] || document.scrollingElement || document.documentElement;
  }

  function scrollJobList() {
    const target = findScrollableJobList();
    const amount = Math.max(520, Math.floor((target.clientHeight || window.innerHeight) * 0.75));
    if (target === document.scrollingElement || target === document.documentElement || target === document.body) {
      window.scrollBy({ top: amount, behavior: "smooth" });
      return;
    }
    target.scrollBy({ top: amount, behavior: "smooth" });
  }

  let harvestTimer = null;

  function setAutoStatus(panel, message, tone) {
    const status = panel.querySelector(".boss-agent-status");
    status.textContent = message || "";
    status.dataset.tone = tone || "";
  }

  function renderAutoState(panel, state) {
    if (!state) {
      return;
    }
    const stats = state.stats || {};
    panel.querySelector(".boss-agent-auto-count").textContent =
      `队列 ${state.queueLength || 0} / 打开 ${stats.opened || 0} / 完成 ${stats.completed || 0} / 失败 ${stats.failed || 0}`;
    panel.querySelector(".boss-agent-start").disabled = Boolean(state.running);
    panel.querySelector(".boss-agent-stop").disabled = !state.running;
    setAutoStatus(panel, state.lastMessage || (state.running ? "运行中。" : "未启动。"));
  }

  function startHarvesting(panel) {
    if (harvestTimer) {
      clearInterval(harvestTimer);
    }
    harvestTimer = setInterval(async () => {
      const response = await runtimeMessage({ type: "GET_STATE" });
      if (!response.ok || !response.state?.running) {
        clearInterval(harvestTimer);
        harvestTimer = null;
        return;
      }
      const jobs = collectJobLinks();
      if (jobs.length) {
        const append = await runtimeMessage({ type: "APPEND_JOBS", jobs });
        if (append.ok) {
          renderAutoState(panel, append.state);
        }
      }
      scrollJobList();
    }, 2600);
  }

  function createAutoPanel() {
    const panel = document.createElement("div");
    panel.id = AUTO_PANEL_ID;
    panel.className = "boss-agent-panel boss-agent-auto-panel";
    panel.innerHTML = `
      <div class="boss-agent-header">
        <span>BOSS 自动投递</span>
      </div>
      <div class="boss-agent-body">
        <select class="boss-agent-select boss-agent-auto-resume" title="简历倾向">
          <option value="auto">自动选择简历</option>
          <option value="agent">Agent 开发简历</option>
          <option value="fde">FDE / 交付简历</option>
        </select>
        <div class="boss-agent-grid">
          <label>
            <span>本轮上限</span>
            <input class="boss-agent-input boss-agent-auto-max" type="number" min="1" max="50" value="10" />
          </label>
          <label class="boss-agent-check">
            <input class="boss-agent-auto-send" type="checkbox" />
            <span>自动发送</span>
          </label>
        </div>
        <div class="boss-agent-row">
          <button class="boss-agent-primary boss-agent-start" type="button">开始</button>
          <button class="boss-agent-secondary boss-agent-stop" type="button" disabled>停止</button>
        </div>
        <div class="boss-agent-auto-count">队列 0 / 打开 0 / 完成 0 / 失败 0</div>
        <div class="boss-agent-status"></div>
      </div>
    `;
    document.body.appendChild(panel);
    return panel;
  }

  function wireAutoPanel(panel) {
    panel.querySelector(".boss-agent-start").addEventListener("click", async () => {
      const jobs = collectJobLinks();
      if (!jobs.length) {
        setAutoStatus(panel, "当前页面没有扫描到详情链接。先滚动一下列表或打开一个岗位后再试。", "error");
        return;
      }
      const options = {
        resumeProfile: panel.querySelector(".boss-agent-auto-resume").value,
        autoSend: panel.querySelector(".boss-agent-auto-send").checked,
        maxJobs: Number(panel.querySelector(".boss-agent-auto-max").value || 10)
      };
      const response = await runtimeMessage({ type: "START_QUEUE", jobs, options });
      if (!response.ok) {
        setAutoStatus(panel, `启动失败：${response.error}`, "error");
        return;
      }
      renderAutoState(panel, response.state);
      startHarvesting(panel);
    });

    panel.querySelector(".boss-agent-stop").addEventListener("click", async () => {
      const response = await runtimeMessage({ type: "STOP_AUTO" });
      if (response.ok) {
        renderAutoState(panel, response.state);
      }
      if (harvestTimer) {
        clearInterval(harvestTimer);
        harvestTimer = null;
      }
    });

    runtimeMessage({ type: "GET_STATE" }).then((response) => {
      if (response.ok) {
        renderAutoState(panel, response.state);
        if (response.state.running) {
          startHarvesting(panel);
        }
      }
    });

    chrome.runtime.onMessage.addListener((message) => {
      if (message.type === "AUTO_STATE") {
        renderAutoState(panel, message.state);
      }
    });
  }

  async function initDetailPage() {
    if (document.getElementById(PANEL_ID) || document.getElementById(MINI_ID)) {
      return;
    }
    const panel = createPanel();
    wireDetailPanel(panel);

    const taskResponse = await runtimeMessage({
      type: "GET_DETAIL_TASK",
      jobKey: jobKeyFromUrl(location.href)
    });
    if (taskResponse.ok && taskResponse.task) {
      runAutoDetailTask(panel, taskResponse.task, taskResponse.options || {});
    }
  }

  async function initChatPage() {
    if (document.getElementById(PANEL_ID) || document.getElementById(MINI_ID)) {
      return;
    }
    const panel = createPanel();
    wireDetailPanel(panel);
    panel.querySelector(".boss-agent-auto-actions").hidden = false;
    setStatus(panel, "聊天页已加载，正在检查自动任务...");

    const taskResponse = await runtimeMessage({
      type: "GET_DETAIL_TASK",
      jobKey: ""
    });
    if (!taskResponse.ok || !taskResponse.task?.greeting) {
      setStatus(panel, "没有待发送的自动任务。");
      return;
    }
    try {
      await fillChat(panel, taskResponse.task.greeting, taskResponse.options || {});
    } catch (error) {
      setStatus(panel, `聊天页自动任务暂停：${error.message}`, "error");
    }
  }

  function initListPage() {
    if (document.getElementById(AUTO_PANEL_ID)) {
      return;
    }
    wireAutoPanel(createAutoPanel());
  }

  if (isDetailPage) {
    initDetailPage();
  } else if (isChatPage) {
    initChatPage();
  } else if (isListPage) {
    initListPage();
  }
})();
