import { mkdir, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";

const baseUrl = process.env.BLANK_UI_REVIEW_URL ?? "http://127.0.0.1:5173";
const chromeBin = process.env.CHROME_BIN ?? "google-chrome";
const outputDir = process.env.BLANK_UI_REVIEW_OUT ?? "/tmp/blank-ui-review";

const commonAccessibilityExpression = `(() => {
  const isVisible = (element) => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  };
  const accessibleName = (element) => {
    const labelledBy = element.getAttribute('aria-labelledby');
    const labelText = labelledBy
      ? labelledBy.split(/\\s+/).map((id) => document.getElementById(id)?.textContent?.trim() ?? '').filter(Boolean).join(' ')
      : '';
    const id = element.getAttribute('id');
    const explicitLabel = id ? document.querySelector(\`label[for="\${CSS.escape(id)}"]\`)?.textContent?.trim() ?? '' : '';
    const wrappingLabel = element.closest('label')?.textContent?.trim() ?? '';
    return [
      element.getAttribute('aria-label'),
      labelText,
      explicitLabel,
      wrappingLabel,
      element.getAttribute('title'),
      element.getAttribute('placeholder'),
      element.textContent,
    ].find((value) => value && value.trim())?.trim() ?? '';
  };
  const controls = [...document.querySelectorAll('button, a[href], input, select, textarea, [role="button"], [tabindex]:not([tabindex="-1"])')]
    .filter((element) => !element.disabled && element.getAttribute('aria-hidden') !== 'true' && isVisible(element));
  const unnamedControls = controls
    .filter((element) => !accessibleName(element))
    .map((element) => element.outerHTML.slice(0, 140));
  const badTabIndex = controls
    .filter((element) => Number(element.getAttribute('tabindex') ?? 0) > 0)
    .map((element) => element.outerHTML.slice(0, 140));
  const duplicateIds = [...document.querySelectorAll('[id]')]
    .map((element) => element.id)
    .filter((id, index, ids) => ids.indexOf(id) !== index);
  return JSON.stringify({
    overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    focusableCount: controls.length,
    unnamedControls,
    badTabIndex,
    duplicateIds: [...new Set(duplicateIds)],
    htmlLang: document.documentElement.lang || '',
  });
})()`;

const reducedMotionExpression = `(() => {
  const animated = [...document.querySelectorAll('*')].filter((element) => {
    const style = getComputedStyle(element);
    const animationDuration = parseFloat(style.animationDuration || '0');
    const transitionDuration = parseFloat(style.transitionDuration || '0');
    const animationCount = style.animationIterationCount;
    return animationDuration > 0.01 || transitionDuration > 0.01 || animationCount === 'infinite';
  });
  return JSON.stringify({
    reduced: matchMedia('(prefers-reduced-motion: reduce)').matches,
    animatedCount: animated.length,
    overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  });
})()`;

const checks = [
  {
    name: "canvas",
    url: `${baseUrl}/?ui-review=canvas`,
    expression: `JSON.stringify({
      canvas: Boolean(document.querySelector('.canvas-layout')),
      topicInput: Boolean(document.querySelector('.topic-form textarea')),
      topicSubmit: document.querySelector('.topic-form .primary-button')?.textContent?.includes('生成学习路径') ?? false,
      topicSubmitDisabled: document.querySelector('.topic-form .primary-button')?.disabled ?? false,
      emptyUpload: document.querySelector('.upload-zone')?.textContent?.includes('拖拽或选择材料') ?? false,
      noInjectedNodes: document.body.textContent.includes('0/0 已掌握'),
      mapDisabled: document.querySelector('.process-board .primary-button')?.disabled ?? false,
      overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth
    })`,
    assert: (value) => value.canvas && value.topicInput && value.topicSubmit && value.topicSubmitDisabled && value.emptyUpload && value.noInjectedNodes && value.mapDisabled && !value.overflowX,
    keyboardTargets: [".topic-form textarea", ".upload-zone input", ".rail-button.active", ".process-board .primary-button"],
  },
  {
    name: "canvas-parsing",
    url: `${baseUrl}/?ui-review=canvas&ui-review-state=parsing`,
    expression: `JSON.stringify({
      parsingTopic: document.querySelector('.topic-form.parsing')?.textContent?.includes('当前任务解析完成前不能创建新学习任务') ?? false,
      topicDisabled: document.querySelector('.topic-form textarea')?.disabled ?? false,
      topicSubmitDisabled: document.querySelector('.topic-form .primary-button')?.disabled ?? false,
      parsingUpload: document.querySelector('.upload-zone.parsing')?.textContent?.includes('解析完成前不能上传其他文档') ?? false,
      fileDisabled: document.querySelector('.upload-zone input')?.disabled ?? false,
      progress: document.querySelector('.progress-meta')?.textContent?.includes('54%') ?? false,
      overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth
    })`,
    assert: (value) => value.parsingTopic && value.topicDisabled && value.topicSubmitDisabled && value.parsingUpload && value.fileDisabled && value.progress && !value.overflowX,
    keyboardTargets: [".rail-button.active", ".icon-button", ".secondary-button.compact"],
  },
  {
    name: "map",
    url: `${baseUrl}/?ui-review=map`,
    expression: `JSON.stringify({
      mapStage: Boolean(document.querySelector('.map-layout')),
      noOverlayEvidence: !document.querySelector('.map-evidence-card'),
      sideEvidence: document.querySelector('.node-evidence-board')?.textContent?.includes('选中节点证据') ?? false,
      evidenceBelowHistory: (() => {
        const history = document.querySelector('.history-panel')?.getBoundingClientRect();
        const evidence = document.querySelector('.node-evidence-board')?.getBoundingClientRect();
        return Boolean(history && evidence && evidence.top >= history.bottom);
      })(),
      evidenceScrollReady: (() => {
        const scroll = document.querySelector('.node-evidence-scroll');
        if (!scroll) return false;
        const style = getComputedStyle(scroll);
        return ['auto', 'scroll'].includes(style.overflowY);
      })(),
      nodeEvidencePanel: document.querySelector('.node-evidence-panel')?.textContent?.includes('复杂度原因') ?? false,
      mapFormulaRendered: document.querySelectorAll('.node-evidence-board .math-display, .node-evidence-panel .math-display').length > 0,
      overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth
    })`,
    assert: (value) => value.mapStage && value.noOverlayEvidence && value.sideEvidence && value.evidenceBelowHistory && value.evidenceScrollReady && value.nodeEvidencePanel && value.mapFormulaRendered && !value.overflowX,
    keyboardTargets: [".knowledge-node.selected", ".node-row.selected", ".node-inspector .primary-button"],
  },
  {
    name: "flow",
    url: `${baseUrl}/?ui-review=flow`,
    expression: `JSON.stringify({
      flow: Boolean(document.querySelector('.flow-layout')),
      noChallengeStrip: !document.querySelector('.challenge-strip'),
      noChatHeader: !document.querySelector('.chat-header'),
      noTopbarStyleDuplicate: ![...document.querySelectorAll('.topbar button')].some((button) => ['简明', '生动', '学术'].includes(button.textContent.trim())),
      personaInLeftPanel: Boolean(document.querySelector('.learning-card > .learning-persona .persona-switcher')),
      personaNotInChatPanel: !document.querySelector('.chat-panel .persona-box'),
      learningRoute: Boolean(document.querySelector('.learning-route')),
      agentPanel: Boolean(document.querySelector('.agent-workflow-panel')),
      agentCollapsed: document.querySelector('.agent-workflow-panel')?.classList.contains('collapsed') ?? false,
      agentCompact: document.querySelector('.agent-workflow-compact')?.textContent?.includes('工作流完成') ?? false,
      agentCompactScore: /步|待命/.test(document.querySelector('.agent-compact-score')?.textContent ?? ''),
      agentNodes: document.querySelectorAll('.agent-node').length,
      agentEvents: document.querySelectorAll('.agent-event').length,
      graphActive: document.querySelector('.agent-workflow-panel')?.textContent?.includes('本轮工作流完成') ?? false,
      mission: document.querySelector('.flow-mission')?.textContent?.includes('本轮任务') ?? false,
      messageStage: document.querySelector('.message-kicker')?.textContent?.includes('机制拆解') ?? false,
      formulaRendered: document.querySelectorAll('.message.mentor .math-display').length > 0,
      composer: Boolean(document.querySelector('.composer input')),
      confuseAction: document.querySelector('.flow-actions')?.textContent?.includes('我听不懂') ?? false,
      feynmanAction: document.querySelector('.flow-actions')?.textContent?.includes('进入费曼舞台') ?? false,
      memoryNoFake: document.querySelector('.memory-board')?.textContent?.includes('系统不会展示预估记录') ?? false,
      memoryVisible: (() => {
        const rect = document.querySelector('.memory-board')?.getBoundingClientRect();
        return Boolean(rect && rect.height > 0 && rect.bottom <= window.innerHeight);
      })(),
      overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth
    })`,
    assert: (value) => value.flow && value.noChallengeStrip && value.noChatHeader && value.noTopbarStyleDuplicate && value.personaInLeftPanel && value.personaNotInChatPanel && value.learningRoute && value.agentPanel && value.agentCollapsed && value.agentCompact && value.agentCompactScore && value.agentNodes === 0 && value.agentEvents === 0 && value.graphActive && value.mission && value.messageStage && value.formulaRendered && value.composer && value.confuseAction && value.feynmanAction && value.memoryNoFake && value.memoryVisible && !value.overflowX,
    keyboardTargets: [".persona-switcher .active", ".composer input", ".flow-actions .secondary-button", ".flow-actions .primary-button"],
  },
  {
    name: "feynman",
    url: `${baseUrl}/?ui-review=feynman`,
    expression: `JSON.stringify({
      recorder: Boolean(document.querySelector('.recorder-studio .record-button')),
      textarea: Boolean(document.querySelector('.answer-studio textarea')),
      sidePanelVisible: Boolean(document.querySelector('.side-panel')),
      overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth
    })`,
    assert: (value) => value.recorder && value.textarea && !value.sidePanelVisible && !value.overflowX,
    keyboardTargets: [".record-button", ".answer-studio textarea", ".flow-actions .primary-button"],
  },
  {
    name: "mastery",
    url: `${baseUrl}/?ui-review=mastery`,
    expression: `JSON.stringify({
      resultBrief: Boolean(document.querySelector('.result-brief')),
      evidenceCollapsed: Boolean(document.querySelector('.evidence-details:not([open])')),
      evidenceScrollReady: (() => {
        const details = document.querySelector('.evidence-details');
        details?.setAttribute('open', '');
        const list = document.querySelector('.evidence-list');
        if (!list) return false;
        const style = getComputedStyle(list);
        return ['auto', 'scroll'].includes(style.overflowY) && style.maxHeight !== 'none';
      })(),
      sidePanelVisible: Boolean(document.querySelector('.side-panel')),
      overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth
    })`,
    assert: (value) => value.resultBrief && value.evidenceCollapsed && value.evidenceScrollReady && !value.sidePanelVisible && !value.overflowX,
    keyboardTargets: [".evidence-details summary", ".rail-button.active"],
  },
  {
    name: "evidence",
    url: `${baseUrl}/?ui-review=evidence`,
    expression: `JSON.stringify({
      dashboard: Boolean(document.querySelector('.evidence-layout')),
      cards: document.querySelectorAll('.evidence-card').length,
      radar: Boolean(document.querySelector('.mastery-radar-panel .radar-chart')),
      radarAxes: document.querySelectorAll('.radar-axis-list > div').length,
      radarContained: (() => {
        const panel = document.querySelector('.mastery-radar-panel')?.getBoundingClientRect();
        const chart = document.querySelector('.radar-chart')?.getBoundingClientRect();
        const list = document.querySelector('.radar-axis-list')?.getBoundingClientRect();
        return Boolean(panel && chart && list && panel.height >= 220 && chart.top >= panel.top - 1 && chart.bottom <= panel.bottom + 1 && list.top >= panel.top - 1 && list.bottom <= panel.bottom + 1);
      })(),
      confusionStats: document.body.textContent.includes('我听不懂 2 次') && document.body.textContent.includes('模型判断解决 1 次'),
      noFakeCopy: document.body.textContent.includes('没有发生的数据不会显示成预估值'),
      overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth
    })`,
    assert: (value) => value.dashboard && value.cards === 4 && value.radar && value.radarAxes === 6 && value.radarContained && value.confusionStats && value.noFakeCopy && !value.overflowX,
    keyboardTargets: [".rail-button.active", ".icon-button", ".secondary-button.compact"],
  },
  {
    name: "evidence-empty",
    url: `${baseUrl}/?ui-review=evidence&ui-review-state=empty`,
    expression: `JSON.stringify({
      empty: document.querySelector('.evidence-empty')?.textContent?.includes('暂无费曼评分证据') ?? false,
      noWeakScore: !(document.body.textContent.includes('最低分项：')),
      overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth
    })`,
    assert: (value) => value.empty && value.noWeakScore && !value.overflowX,
    keyboardTargets: [".rail-button.active", ".icon-button", ".secondary-button.compact"],
  },
  {
    name: "admin",
    url: `${baseUrl}/?ui-review=admin`,
    expression: `JSON.stringify({
      admin: Boolean(document.querySelector('.admin-layout')),
      statusStrip: document.querySelector('.admin-status-strip')?.textContent?.includes('未执行连通性测试时不显示模型健康结论') ?? false,
      configCount: document.querySelector('.admin-list-panel')?.textContent?.includes('API 配置') ?? false,
      userCount: document.querySelector('.admin-list-panel + .admin-list-panel')?.textContent?.includes('用户与权限') ?? false,
      activeProvider: document.body.textContent.includes('gpt-4.1-mini'),
      tokenUsage: document.body.textContent.includes('今日 Token') && document.body.textContent.includes('总 token') && document.body.textContent.includes('今日 token'),
      overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth
    })`,
    assert: (value) => value.admin && value.statusStrip && value.configCount && value.userCount && value.activeProvider && value.tokenUsage && !value.overflowX,
    keyboardTargets: [".admin-form select", ".admin-form input", ".admin-form .primary-button"],
  },
  {
    name: "research",
    url: `${baseUrl}/?ui-review=research`,
    expression: `JSON.stringify({
      research: Boolean(document.querySelector('.research-layout')),
      heading: document.querySelector('.research-overview')?.textContent?.includes('教师端 / 研究端') ?? false,
      metrics: document.querySelectorAll('.research-metric-card').length,
      weakPoints: document.querySelector('.research-rank-list')?.textContent?.includes('transfer') ?? false,
      distribution: document.querySelectorAll('.distribution-row').length === 4,
      materialQuality: document.querySelector('.material-quality-list')?.textContent?.includes('条件概率讲义') ?? false,
      memories: document.querySelector('.memory-category-list')?.textContent?.includes('认知卡点') ?? false,
      experiments: document.querySelector('.experiment-summary-list')?.textContent?.includes('ChatGPT') ?? false,
      agreement: document.querySelector('.agreement-grid')?.textContent?.includes('相关系数') ?? false,
      importBox: Boolean(document.querySelector('.research-import-body textarea')),
      exportButton: document.querySelector('.research-actions')?.textContent?.includes('匿名导出') ?? false,
      blindExport: document.querySelector('.research-actions')?.textContent?.includes('盲评答卷') ?? false,
      records: document.querySelector('.experiment-record-list')?.textContent?.includes('p001') ?? false,
      overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth
    })`,
    assert: (value) => value.research && value.heading && value.metrics >= 6 && value.weakPoints && value.distribution && value.materialQuality && value.memories && value.experiments && value.agreement && value.importBox && value.exportButton && value.blindExport && value.records && !value.overflowX,
    keyboardTargets: [".rail-button.active", ".research-heading-row .secondary-button", ".research-import-body textarea", ".research-import-body .primary-button", ".icon-button"],
  },
];

await mkdir(outputDir, { recursive: true });

const results = [];
for (const [index, check] of checks.entries()) {
  const result = await runCheck(check, 9701 + index);
  results.push({ name: check.name, ...result });
  if (!check.assert(result.value)) {
    throw new Error(`UI review check failed for ${check.name}: ${JSON.stringify(result.value)}`);
  }
}

console.log(JSON.stringify(results, null, 2));

async function runCheck(check, port) {
  const chrome = spawn(
    chromeBin,
    [
      "--headless=new",
      "--no-sandbox",
      "--disable-gpu",
      `--remote-debugging-port=${port}`,
      "--window-size=1440,900",
      check.url,
    ],
    { stdio: ["ignore", "ignore", "ignore"] },
  );

  try {
    await delay(900);
    const devtools = await connectToPage(port);
    const evaluation = await devtools.call("Runtime.evaluate", { expression: check.expression, returnByValue: true });
    const value = JSON.parse(evaluation.result.value);
    const accessibilityEvaluation = await devtools.call("Runtime.evaluate", {
      expression: commonAccessibilityExpression,
      returnByValue: true,
    });
    const accessibility = JSON.parse(accessibilityEvaluation.result.value);
    assertCommonAccessibility(check.name, accessibility);
    const keyboard = await verifyKeyboardTargets(devtools, check.keyboardTargets ?? []);
    await devtools.call("Emulation.setEmulatedMedia", {
      features: [{ name: "prefers-reduced-motion", value: "reduce" }],
    });
    const reducedMotionEvaluation = await devtools.call("Runtime.evaluate", {
      expression: reducedMotionExpression,
      returnByValue: true,
    });
    const reducedMotion = JSON.parse(reducedMotionEvaluation.result.value);
    assertReducedMotion(check.name, reducedMotion);
    const screenshot = await devtools.call("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    await writeFile(`${outputDir}/${check.name}-ui-review.png`, Buffer.from(screenshot.data, "base64"));
    devtools.close();
    return { value, accessibility, keyboard, reducedMotion, screenshot: `${outputDir}/${check.name}-ui-review.png` };
  } finally {
    chrome.kill("SIGTERM");
  }
}

async function verifyKeyboardTargets(devtools, selectors) {
  const visited = [];
  for (let step = 0; step < 40; step += 1) {
    const evaluation = await devtools.call("Runtime.evaluate", {
      expression: `(() => {
        const element = document.activeElement;
        if (!element) return '';
        if (element.matches?.('body')) return 'body';
        return element.matches?.('[aria-label]') ? element.getAttribute('aria-label') : element.outerHTML.slice(0, 120);
      })()`,
      returnByValue: true,
    });
    visited.push(evaluation.result.value ?? "");
    await devtools.call("Input.dispatchKeyEvent", { type: "keyDown", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
    await devtools.call("Input.dispatchKeyEvent", { type: "keyUp", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
    await delay(20);
  }

  const targetResults = [];
  for (const selector of selectors) {
    const evaluation = await devtools.call("Runtime.evaluate", {
      expression: `(() => {
        const target = document.querySelector(${JSON.stringify(selector)});
        if (!target) return { selector: ${JSON.stringify(selector)}, exists: false, reached: false };
        target.focus();
        return {
          selector: ${JSON.stringify(selector)},
          exists: true,
          reached: document.activeElement === target || target.contains(document.activeElement),
          disabled: Boolean(target.disabled),
          tag: target.tagName,
        };
      })()`,
      returnByValue: true,
    });
    targetResults.push(evaluation.result.value);
  }

  const missingTargets = targetResults.filter((item) => !item.exists);
  const unreachableTargets = targetResults.filter((item) => item.exists && !item.disabled && !item.reached);
  if (missingTargets.length > 0 || unreachableTargets.length > 0) {
    throw new Error(`Keyboard target check failed: ${JSON.stringify({ missingTargets, unreachableTargets, visited: visited.slice(0, 12) })}`);
  }
  return { targetResults, visitedCount: visited.filter(Boolean).length };
}

function assertCommonAccessibility(name, accessibility) {
  const failures = [];
  if (accessibility.overflowX) failures.push("horizontal overflow");
  if (accessibility.focusableCount <= 0) failures.push("no focusable controls");
  if (accessibility.unnamedControls.length > 0) failures.push(`unnamed controls: ${accessibility.unnamedControls.join(" | ")}`);
  if (accessibility.badTabIndex.length > 0) failures.push(`positive tabindex: ${accessibility.badTabIndex.join(" | ")}`);
  if (accessibility.duplicateIds.length > 0) failures.push(`duplicate ids: ${accessibility.duplicateIds.join(", ")}`);
  if (!accessibility.htmlLang.toLowerCase().startsWith("zh")) failures.push(`html lang is ${accessibility.htmlLang || "empty"}`);
  if (failures.length > 0) {
    throw new Error(`Common accessibility check failed for ${name}: ${failures.join("; ")}`);
  }
}

function assertReducedMotion(name, reducedMotion) {
  const failures = [];
  if (!reducedMotion.reduced) failures.push("reduced motion media query was not emulated");
  if (reducedMotion.overflowX) failures.push("horizontal overflow");
  if (reducedMotion.animatedCount > 0) failures.push(`${reducedMotion.animatedCount} elements still animate or transition`);
  if (failures.length > 0) {
    throw new Error(`Reduced motion check failed for ${name}: ${failures.join("; ")}`);
  }
}

async function connectToPage(port) {
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const target = targets.find((item) => item.type === "page") ?? targets[0];
  if (!target) {
    throw new Error(`Chrome DevTools page not found on port ${port}`);
  }
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  let id = 0;
  const pending = new Map();
  ws.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (!message.id || !pending.has(message.id)) return;
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    message.error ? reject(new Error(message.error.message)) : resolve(message.result);
  });
  await new Promise((resolve) => ws.addEventListener("open", resolve, { once: true }));
  return {
    call(method, params = {}) {
      return new Promise((resolve, reject) => {
        const callId = ++id;
        pending.set(callId, { resolve, reject });
        ws.send(JSON.stringify({ id: callId, method, params }));
      });
    },
    close() {
      ws.close();
    },
  };
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
