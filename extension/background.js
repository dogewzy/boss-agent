const DEFAULT_STATE = {
  running: false,
  sourceTabId: null,
  activeTabId: null,
  currentJob: null,
  queue: [],
  processed: {},
  options: {
    resumeProfile: "auto",
    autoSend: false,
    maxJobs: 10,
    delayMs: 1800
  },
  stats: {
    queued: 0,
    opened: 0,
    completed: 0,
    failed: 0
  },
  lastMessage: ""
};

let state = structuredClone(DEFAULT_STATE);
let loaded = false;

async function loadState() {
  if (loaded) {
    return;
  }
  const data = await chrome.storage.local.get("bossAgentAutoState");
  state = {
    ...structuredClone(DEFAULT_STATE),
    ...(data.bossAgentAutoState || {})
  };
  state.activeTabId = null;
  state.currentJob = null;
  loaded = true;
}

async function saveState() {
  await chrome.storage.local.set({ bossAgentAutoState: state });
}

function publicState() {
  return {
    running: state.running,
    activeTabId: state.activeTabId,
    currentJob: state.currentJob,
    queueLength: state.queue.length,
    options: state.options,
    stats: state.stats,
    lastMessage: state.lastMessage
  };
}

function mergeJobs(jobs) {
  let added = 0;
  const known = new Set([
    ...state.queue.map((job) => job.key),
    ...Object.keys(state.processed)
  ]);
  if (state.currentJob) {
    known.add(state.currentJob.key);
  }

  for (const job of jobs || []) {
    if (!job || !job.url || !job.key || known.has(job.key)) {
      continue;
    }
    state.queue.push(job);
    known.add(job.key);
    added += 1;
  }
  state.stats.queued += added;
  return added;
}

async function notifySource() {
  if (!state.sourceTabId) {
    return;
  }
  try {
    await chrome.tabs.sendMessage(state.sourceTabId, {
      type: "AUTO_STATE",
      state: publicState()
    });
  } catch (_) {
    // The list tab may be closed or not ready. The stored state is still enough.
  }
}

async function processNext() {
  await loadState();
  if (!state.running || state.activeTabId || state.currentJob) {
    await notifySource();
    return;
  }

  const maxJobs = Number(state.options.maxJobs || 0);
  if (maxJobs > 0 && state.stats.opened >= maxJobs) {
    state.running = false;
    state.lastMessage = `已达到本轮上限 ${maxJobs} 个岗位。`;
    await saveState();
    await notifySource();
    return;
  }

  let nextJob = null;
  while (state.queue.length) {
    const candidate = state.queue.shift();
    if (!state.processed[candidate.key]) {
      nextJob = candidate;
      break;
    }
  }

  if (!nextJob) {
    state.lastMessage = "队列已空，等待列表页继续加载岗位。";
    await saveState();
    await notifySource();
    return;
  }

  try {
    const createOptions = {
      url: nextJob.url,
      active: true
    };
    if (state.sourceTabId) {
      createOptions.openerTabId = state.sourceTabId;
    }
    const tab = await chrome.tabs.create(createOptions);
    state.activeTabId = tab.id;
    state.currentJob = nextJob;
    state.stats.opened += 1;
    state.lastMessage = `正在处理：${nextJob.title || nextJob.key}`;
  } catch (error) {
    state.processed[nextJob.key] = {
      status: "open_failed",
      at: Date.now(),
      error: error.message
    };
    state.stats.failed += 1;
    state.lastMessage = `打开失败：${error.message}`;
  }

  await saveState();
  await notifySource();
  if (!state.activeTabId) {
    setTimeout(processNext, state.options.delayMs);
  }
}

async function finishCurrent(status, detail, tabId) {
  const job = state.currentJob;
  if (job) {
    state.processed[job.key] = {
      status,
      detail: detail || "",
      at: Date.now()
    };
  }
  if (status === "done") {
    state.stats.completed += 1;
  } else {
    state.stats.failed += 1;
  }
  state.lastMessage = detail || (status === "done" ? "岗位已完成。" : "岗位已跳过。");

  const closeTabId = tabId || state.activeTabId;
  state.activeTabId = null;
  state.currentJob = null;
  await saveState();
  await notifySource();

  if (closeTabId) {
    try {
      await chrome.tabs.remove(closeTabId);
    } catch (_) {
      // The tab may already have been closed by the user.
    }
  }
  setTimeout(processNext, state.options.delayMs);
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    await loadState();
    switch (message.type) {
      case "GET_STATE": {
        sendResponse({ ok: true, state: publicState() });
        break;
      }
      case "START_QUEUE": {
        state = {
          ...state,
          running: true,
          sourceTabId: sender.tab?.id || state.sourceTabId,
          activeTabId: null,
          currentJob: null,
          queue: [],
          options: {
            ...state.options,
            ...(message.options || {})
          },
          stats: {
            queued: 0,
            opened: 0,
            completed: 0,
            failed: 0
          },
          lastMessage: "自动投递已启动。"
        };
        const added = mergeJobs(message.jobs || []);
        state.lastMessage = `自动投递已启动，已加入 ${added} 个岗位。`;
        await saveState();
        sendResponse({ ok: true, state: publicState(), added });
        processNext();
        break;
      }
      case "APPEND_JOBS": {
        const added = mergeJobs(message.jobs || []);
        if (added) {
          state.lastMessage = `新增 ${added} 个岗位到队列。`;
        }
        await saveState();
        sendResponse({ ok: true, state: publicState(), added });
        processNext();
        break;
      }
      case "STOP_AUTO": {
        state.running = false;
        state.queue = [];
        state.lastMessage = "自动投递已停止。";
        await saveState();
        sendResponse({ ok: true, state: publicState() });
        await notifySource();
        break;
      }
      case "GET_DETAIL_TASK": {
        const tabId = sender.tab?.id;
        const current = state.currentJob;
        const isActiveTask = Boolean(
          state.running &&
            current &&
            (tabId === state.activeTabId || message.jobKey === current.key)
        );
        sendResponse({
          ok: true,
          task: isActiveTask ? current : null,
          options: state.options,
          state: publicState()
        });
        break;
      }
      case "SET_CURRENT_GREETING": {
        if (state.currentJob) {
          state.currentJob = {
            ...state.currentJob,
            greeting: message.greeting || "",
            historyId: message.historyId || "",
            jobData: message.jobData || null
          };
          state.lastMessage = "招呼已生成，等待进入聊天页。";
          await saveState();
          await notifySource();
        }
        sendResponse({ ok: true, state: publicState() });
        break;
      }
      case "DETAIL_DONE": {
        await finishCurrent("done", message.detail || "岗位已完成。", sender.tab?.id);
        sendResponse({ ok: true, state: publicState() });
        break;
      }
      case "DETAIL_SKIP": {
        await finishCurrent("skipped", message.detail || "岗位已跳过。", sender.tab?.id);
        sendResponse({ ok: true, state: publicState() });
        break;
      }
      default:
        sendResponse({ ok: false, error: `Unknown message type: ${message.type}` });
    }
  })().catch((error) => {
    sendResponse({ ok: false, error: error.message });
  });
  return true;
});

chrome.tabs.onRemoved.addListener((tabId) => {
  (async () => {
    await loadState();
    if (tabId !== state.activeTabId) {
      return;
    }
    if (state.currentJob) {
      state.processed[state.currentJob.key] = {
        status: "closed",
        at: Date.now(),
        detail: "详情页被关闭。"
      };
      state.stats.failed += 1;
    }
    state.activeTabId = null;
    state.currentJob = null;
    await saveState();
    await notifySource();
    setTimeout(processNext, state.options.delayMs);
  })();
});
