(function () {
  const API_URL = "http://127.0.0.1:8765/api/greeting";
  const RESUME_API_URL = "http://127.0.0.1:8765/api/resume-polish";
  const PANEL_ID = "boss-agent-greeting-panel";
  const MINI_ID = "boss-agent-greeting-mini";

  if (document.getElementById(PANEL_ID) || document.getElementById(MINI_ID)) {
    return;
  }

  function normalizeText(text) {
    return (text || "").replace(/\s+/g, " ").trim();
  }

  function textOf(selector) {
    const node = document.querySelector(selector);
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
      wirePanel(createPanel());
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
      return;
    }

    primary.disabled = true;
    polish.disabled = true;
    copy.disabled = true;
    setStatus(panel, "正在生成...");
    output.value = "";

    try {
      const response = await fetch(API_URL, {
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
      output.value = data.greeting;
      copy.disabled = !data.greeting;
      setStatus(panel, `已生成，使用 ${data.resume_profile === "agent" ? "Agent" : "FDE"} 简历。`);
    } catch (error) {
      setStatus(panel, `生成失败：${error.message}`, "error");
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

  function wirePanel(panel) {
    panel.querySelector(".boss-agent-primary").addEventListener("click", () => generate(panel));
    panel.querySelector(".boss-agent-polish").addEventListener("click", () => polishResume(panel));
    panel.querySelector(".boss-agent-secondary").addEventListener("click", () => copyResult(panel));
    panel.querySelector(".boss-agent-close").addEventListener("click", () => {
      panel.remove();
      createMiniButton();
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

  wirePanel(createPanel());
})();
