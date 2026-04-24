const GENDER_OPTIONS = ["男", "女", "其他"];
const RELATION_OPTIONS = ["婚姻", "亲子", "事业", "朋友", "家人"];
const ACTIVITY_OPTIONS = ["嫁娶", "开业", "出行", "签约"];
const ZIWEI_SCHOOL_OPTIONS = ["sanhe", "feixing"];
const ZIWEI_TRANSFORM_SCOPE_OPTIONS = ["year", "full"];
const STORAGE_KEY_FORMS = "fatemaster_forms_v1";
const STORAGE_KEY_PROFILES = "fatemaster_profiles_v1";

function personFields(prefix, title, full = false, options = {}) {
  const requireBirthTime = options.requireBirthTime !== false;
  return [
    { key: `${prefix}_title`, type: "section", label: title, full: true },
    { key: `${prefix}_picker`, type: "profile_picker", label: "使用历史档案", prefix, full: true },
    { key: `${prefix}_name`, label: "姓名", type: "text", full },
    { key: `${prefix}_birth_place`, label: "出生地", type: "text", full: true, placeholder: "如：北京 / 上海 / 纽约（用于自动推断时区）", required: false },
    { key: `${prefix}_birthday`, label: "生日", type: "date", full: false },
    { key: `${prefix}_birth_time`, label: "出生时间", type: "time", full: false, required: requireBirthTime },
    { key: `${prefix}_gender`, label: "性别", type: "select", options: GENDER_OPTIONS, full: false },
  ];
}

function buildPersonPayload(v, prefix) {
  return {
    name: v[`${prefix}_name`],
    birth_place: v[`${prefix}_birth_place`] || "",
    birthday: v[`${prefix}_birthday`],
    birth_time: v[`${prefix}_birth_time`] || null,
    gender: v[`${prefix}_gender`],
  };
}

function buildPairPayload(v, leftPrefix = "left", rightPrefix = "right") {
  return {
    left: buildPersonPayload(v, leftPrefix),
    right: buildPersonPayload(v, rightPrefix),
  };
}

const modules = [
  {
    id: "bazi",
    name: "八字分析命盘解析",
    tag: "八字",
    endpoint: "/api/bazi/analyze",
    desc: "只输入基础信息，自动推演五行结构并交给 AI 解读。",
    personPrefixes: ["profile"],
    fields: personFields("profile", "个人信息", true, { requireBirthTime: false }),
    example: { profile_name: "张三", profile_birth_place: "北京", profile_birthday: "1995-08-12", profile_birth_time: "", profile_gender: "男" },
    payloadBuilder: v => ({ profile: buildPersonPayload(v, "profile") }),
  },
  {
    id: "daily",
    name: "每日运势",
    tag: "运势",
    endpoint: "/api/fortune/daily",
    desc: "根据个人基础信息 + 日期，给出当日策略建议。",
    fields: [
      {
        key: "daily_picker",
        label: "使用历史档案",
        type: "profile_picker",
        full: true,
        mapping: { name: "name", birthday: "birthday" },
      },
      { key: "name", label: "姓名", type: "text" },
      { key: "birthday", label: "生日", type: "date" },
      { key: "date", label: "查询日期", type: "date" },
    ],
    example: { name: "张三", birthday: "1995-08-12", date: "2026-04-22" },
    payloadBuilder: v => v,
  },
  {
    id: "marriage",
    name: "合婚分析",
    tag: "关系",
    endpoint: "/api/marriage/analyze",
    desc: "双方输入基础信息即可完成匹配与 AI 关系建议。",
    personPrefixes: ["left", "right"],
    fields: [...personFields("left", "对象 A", false, { requireBirthTime: false }), ...personFields("right", "对象 B", false, { requireBirthTime: false })],
    example: {
      left_name: "甲方",
      left_birthday: "1994-01-01",
      left_birth_time: "06:00",
      left_gender: "男",
      right_name: "乙方",
      right_birthday: "1996-10-20",
      right_birth_time: "18:30",
      right_gender: "女",
    },
    payloadBuilder: v => buildPairPayload(v),
  },
  {
    id: "cooperation",
    name: "事业合作",
    tag: "关系",
    endpoint: "/api/cooperation/analyze",
    desc: "用于合伙人/搭档协作潜力分析。",
    personPrefixes: ["left", "right"],
    fields: [...personFields("left", "成员 A", false, { requireBirthTime: false }), ...personFields("right", "成员 B", false, { requireBirthTime: false })],
    example: {
      left_name: "创始人A",
      left_birthday: "1990-01-03",
      left_birth_time: "09:12",
      left_gender: "男",
      right_name: "合伙人B",
      right_birthday: "1988-06-21",
      right_birth_time: "13:40",
      right_gender: "女",
    },
    payloadBuilder: v => buildPairPayload(v),
  },
  {
    id: "mother",
    name: "婆媳关系",
    tag: "关系",
    endpoint: "/api/mother-in-law/analyze",
    desc: "用于代际关系观察与沟通建议。",
    personPrefixes: ["left", "right"],
    fields: [...personFields("left", "婆婆", false, { requireBirthTime: false }), ...personFields("right", "儿媳", false, { requireBirthTime: false })],
    example: {
      left_name: "婆婆",
      left_birthday: "1968-03-11",
      left_birth_time: "07:40",
      left_gender: "女",
      right_name: "儿媳",
      right_birthday: "1998-05-09",
      right_birth_time: "21:10",
      right_gender: "女",
    },
    payloadBuilder: v => buildPairPayload(v),
  },
  {
    id: "friend",
    name: "知己分析",
    tag: "关系",
    endpoint: "/api/friend/analyze",
    desc: "用于朋友关系契合度与互动建议。",
    personPrefixes: ["left", "right"],
    fields: [...personFields("left", "朋友 A", false, { requireBirthTime: false }), ...personFields("right", "朋友 B", false, { requireBirthTime: false })],
    example: {
      left_name: "朋友A",
      left_birthday: "1992-12-12",
      left_birth_time: "11:10",
      left_gender: "男",
      right_name: "朋友B",
      right_birthday: "1993-04-18",
      right_birth_time: "15:50",
      right_gender: "女",
    },
    payloadBuilder: v => buildPairPayload(v),
  },
  {
    id: "graph",
    name: "八字关系图谱",
    tag: "图谱",
    endpoint: "/api/relationship/graph",
    desc: "输入一个核心人物与四个关系对象，自动生成关系图评分。",
    fields: [
      { key: "center_name", label: "核心人物姓名", type: "text", full: true },
      { key: "r1_name", label: "关系对象 1", type: "text" },
      { key: "r1_type", label: "关系类型 1", type: "select", options: RELATION_OPTIONS },
      { key: "r2_name", label: "关系对象 2", type: "text" },
      { key: "r2_type", label: "关系类型 2", type: "select", options: RELATION_OPTIONS },
      { key: "r3_name", label: "关系对象 3", type: "text" },
      { key: "r3_type", label: "关系类型 3", type: "select", options: RELATION_OPTIONS },
      { key: "r4_name", label: "关系对象 4", type: "text" },
      { key: "r4_type", label: "关系类型 4", type: "select", options: RELATION_OPTIONS },
    ],
    example: { center_name: "我", r1_name: "伴侣", r1_type: "婚姻", r2_name: "孩子", r2_type: "亲子", r3_name: "合伙人", r3_type: "事业", r4_name: "挚友", r4_type: "朋友" },
    payloadBuilder: v => ({
      center_name: v.center_name,
      relations: [
        { name: v.r1_name, relation_type: v.r1_type },
        { name: v.r2_name, relation_type: v.r2_type },
        { name: v.r3_name, relation_type: v.r3_type },
        { name: v.r4_name, relation_type: v.r4_type },
      ].filter(item => item.name),
    }),
  },
  {
    id: "meihua",
    name: "梅花易数每日决策",
    tag: "易数",
    endpoint: "/api/meihua/daily-decision",
    desc: "输入你的问题，系统结合当天节律给出决策方向。",
    fields: [{ key: "question", label: "你当前的问题", type: "textarea", full: true }, { key: "date", label: "日期", type: "date" }],
    example: { question: "是否本月启动新项目？", date: "2026-04-22" },
    payloadBuilder: v => v,
  },
  {
    id: "liuyao",
    name: "六爻占卜",
    tag: "占卜",
    endpoint: "/api/liuyao/divine",
    desc: "输入问题与日期，自动给出变化线与策略。",
    fields: [{ key: "question", label: "你当前的问题", type: "textarea", full: true }, { key: "date", label: "日期", type: "date" }],
    example: { question: "是否适合更换工作方向？", date: "2026-04-22" },
    payloadBuilder: v => v,
  },
  {
    id: "tarot",
    name: "塔罗占卜",
    tag: "占卜",
    endpoint: "/api/tarot/divine",
    desc: "输入问题后自动抽牌，并由 AI 解释行动方向。",
    fields: [{ key: "question", label: "你当前的问题", type: "textarea", full: true }, { key: "date", label: "日期", type: "date" }],
    example: { question: "目前关系是否需要推进？", date: "2026-04-22" },
    payloadBuilder: v => v,
  },
  {
    id: "ziwei-chart",
    name: "紫微斗数排盘",
    tag: "紫微",
    endpoint: "/api/ziwei/chart",
    desc: "输入基础信息自动排盘，再交由 AI 做宫位解读。",
    personPrefixes: ["profile"],
    fields: [
      ...personFields("profile", "个人信息", true),
      { key: "profile_ziwei_school", label: "紫微流派", type: "select", options: ZIWEI_SCHOOL_OPTIONS, full: false },
      { key: "profile_ziwei_transform_scope", label: "四化范围", type: "select", options: ZIWEI_TRANSFORM_SCOPE_OPTIONS, full: false },
    ],
    example: {
      profile_name: "李四",
      profile_birth_place: "上海",
      profile_birthday: "1991-09-03",
      profile_birth_time: "10:15",
      profile_gender: "女",
      profile_ziwei_school: "sanhe",
      profile_ziwei_transform_scope: "year",
    },
    payloadBuilder: v => ({
      profile: {
        ...buildPersonPayload(v, "profile"),
        ziwei_school: v.profile_ziwei_school || "sanhe",
        ziwei_transform_scope: v.profile_ziwei_transform_scope || "year",
      },
    }),
  },
  {
    id: "ziwei-marriage",
    name: "紫微合婚",
    tag: "紫微",
    endpoint: "/api/ziwei/marriage",
    desc: "双人基础信息输入后自动完成对照分析。",
    personPrefixes: ["left", "right"],
    fields: [...personFields("left", "对象 A"), ...personFields("right", "对象 B")],
    example: {
      left_name: "甲",
      left_birthday: "1989-02-11",
      left_birth_time: "03:30",
      left_gender: "男",
      right_name: "乙",
      right_birthday: "1991-08-29",
      right_birth_time: "22:20",
      right_gender: "女",
    },
    payloadBuilder: v => buildPairPayload(v),
  },
  {
    id: "huangli",
    name: "黄历查询",
    tag: "黄历",
    endpoint: "/api/huangli",
    desc: "选择活动类型，查看当日宜忌与 AI 建议。",
    fields: [{ key: "date", label: "日期", type: "date" }, { key: "activity", label: "活动类型", type: "select", options: ACTIVITY_OPTIONS }],
    example: { date: "2026-04-22", activity: "签约" },
    payloadBuilder: v => v,
  },
];

const moduleMap = new Map(modules.map(m => [m.id, m]));

function parseJson(key, fallbackValue) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallbackValue;
  } catch {
    return fallbackValue;
  }
}

const state = {
  selected: modules[0],
  forms: parseJson(STORAGE_KEY_FORMS, {}),
  profiles: parseJson(STORAGE_KEY_PROFILES, []),
};

const moduleList = document.getElementById("module-list");
const titleEl = document.getElementById("module-title");
const descEl = document.getElementById("module-desc");
const formEl = document.getElementById("dynamic-form");
const resultEl = document.getElementById("result");
const submitBtn = document.getElementById("submit-btn");
const exportPdfBtn = document.getElementById("export-pdf-btn");
const resetBtn = document.getElementById("reset-btn");
const moduleCountEl = document.getElementById("module-count");
const activeApiEl = document.getElementById("active-module-api");

function saveForms() {
  localStorage.setItem(STORAGE_KEY_FORMS, JSON.stringify(state.forms));
}

function saveProfiles() {
  localStorage.setItem(STORAGE_KEY_PROFILES, JSON.stringify(state.profiles));
}

function moduleIdFromPath() {
  const match = window.location.pathname.match(/^\/service\/([^/]+)$/);
  if (!match) return null;
  return decodeURIComponent(match[1]);
}

function selectModuleById(moduleId) {
  state.selected = moduleMap.get(moduleId) || modules[0];
}

function profileLabel(profile) {
  const place = profile.birth_place ? ` | ${profile.birth_place}` : "";
  return `${profile.name} | ${profile.birthday} ${profile.birth_time || "时辰未知"} | ${profile.gender}${place}`;
}

function fillProfile(prefix, profile) {
  const set = (suffix, value) => {
    const el = document.getElementById(`${prefix}_${suffix}`);
    if (el) el.value = value || "";
  };
  set("name", profile.name);
  set("birth_place", profile.birth_place);
  set("birthday", profile.birthday);
  set("birth_time", profile.birth_time);
  set("gender", profile.gender);
}

function fillProfileByMapping(mapping, profile) {
  Object.entries(mapping).forEach(([from, to]) => {
    const el = document.getElementById(to);
    if (el) el.value = profile[from] || "";
  });
}

function getProfileFromValues(prefix, values) {
  const name = (values[`${prefix}_name`] || "").trim();
  const birth_place = (values[`${prefix}_birth_place`] || "").trim();
  const birthday = (values[`${prefix}_birthday`] || "").trim();
  const birth_time = (values[`${prefix}_birth_time`] || "").trim();
  const gender = (values[`${prefix}_gender`] || "").trim() || "其他";
  if (!name || !birthday) return null;
  return { name, birth_place, birthday, birth_time, gender };
}

function upsertProfile(profile) {
  const key = `${profile.name}|${profile.birthday}|${profile.birth_time}|${profile.gender}`;
  const idx = state.profiles.findIndex(p => `${p.name}|${p.birthday}|${p.birth_time}|${p.gender}` === key);
  if (idx >= 0) {
    const existing = state.profiles[idx];
    state.profiles.splice(idx, 1);
    state.profiles.unshift({ ...existing, last_used_at: new Date().toISOString() });
  } else {
    state.profiles.unshift({ ...profile, created_at: new Date().toISOString(), last_used_at: new Date().toISOString() });
    if (state.profiles.length > 30) state.profiles = state.profiles.slice(0, 30);
  }
}

function extractProfiles(moduleConfig, values) {
  if (!moduleConfig.personPrefixes || !moduleConfig.personPrefixes.length) return [];
  return moduleConfig.personPrefixes.map(prefix => getProfileFromValues(prefix, values)).filter(Boolean);
}

function renderModules() {
  moduleCountEl.textContent = String(modules.length);
  moduleList.innerHTML = "";
  modules.forEach(m => {
    const item = document.createElement("a");
    item.href = `/service/${encodeURIComponent(m.id)}`;
    item.className = `module-item ${m.id === state.selected.id ? "active" : ""}`;
    item.innerHTML = `
      <div class="tag">${m.tag || "模块"}</div>
      <div class="name">${m.name}</div>
      <div class="desc">${m.desc}</div>
    `;
    moduleList.appendChild(item);
  });
}

function renderForm() {
  const selected = state.selected;
  const restored = state.forms[selected.id] || {};
  const formValues = { ...selected.example, ...restored };
  titleEl.textContent = selected.name;
  descEl.textContent = selected.desc;
  activeApiEl.textContent = selected.endpoint;
  formEl.innerHTML = "";
  
  if (selected.id === "marriage") {
    exportPdfBtn.style.display = "inline-block";
  } else {
    exportPdfBtn.style.display = "none";
  }

  selected.fields.forEach(field => {
    if (field.type === "section") {
      const section = document.createElement("div");
      section.className = "form-section full";
      section.textContent = field.label;
      formEl.appendChild(section);
      return;
    }

    const wrap = document.createElement("div");
    wrap.className = `field ${field.full ? "full" : ""}`;
    const label = document.createElement("label");
    label.setAttribute("for", field.key);
    label.textContent = field.label;
    wrap.appendChild(label);

    if (field.type === "profile_picker") {
      const picker = document.createElement("select");
      picker.id = field.key;
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "选择已保存生辰档案";
      picker.appendChild(placeholder);
      state.profiles.forEach((profile, index) => {
        const opt = document.createElement("option");
        opt.value = String(index);
        opt.textContent = profileLabel(profile);
        picker.appendChild(opt);
      });
      picker.addEventListener("change", () => {
        if (!picker.value) return;
        const profile = state.profiles[Number(picker.value)];
        if (!profile) return;
        if (field.mapping) {
          fillProfileByMapping(field.mapping, profile);
        } else {
          fillProfile(field.prefix, profile);
        }
      });
      wrap.appendChild(picker);
    } else if (field.type === "select") {
      const select = document.createElement("select");
      select.id = field.key;
      (field.options || []).forEach(optionText => {
        const opt = document.createElement("option");
        opt.value = optionText;
        opt.textContent = optionText;
        select.appendChild(opt);
      });
      if (formValues[field.key]) {
        select.value = formValues[field.key];
      }
      wrap.appendChild(select);
    } else if (field.type === "textarea") {
      const input = document.createElement("textarea");
      input.id = field.key;
      input.placeholder = field.placeholder || "";
      input.value = formValues[field.key] || "";
      wrap.appendChild(input);
    } else {
      const input = document.createElement("input");
      input.id = field.key;
      input.type = field.type || "text";
      input.placeholder = field.placeholder || "";
      input.value = formValues[field.key] || "";
      wrap.appendChild(input);
    }
    formEl.appendChild(wrap);
  });
}

function collectValues() {
  const values = {};
  for (const field of state.selected.fields) {
    if (field.type === "section" || field.type === "profile_picker") continue;
    const el = document.getElementById(field.key);
    if (!el) continue;
    values[field.key] = (el.value || "").trim();
  }
  return values;
}

function isValidDateStr(v) {
  return /^\d{4}-\d{2}-\d{2}$/.test(v);
}

function isValidTimeStr(v) {
  return /^\d{2}:\d{2}$/.test(v);
}

function validateValues(values) {
  const errors = [];
  for (const field of state.selected.fields) {
    if (field.type === "section" || field.type === "profile_picker") continue;
    const value = values[field.key] || "";
    const required = field.required !== false;
    if (required && !value) {
      errors.push(`${field.label} 不能为空`);
      continue;
    }
    if (field.type === "date" && value && !isValidDateStr(value)) {
      errors.push(`${field.label} 格式应为 YYYY-MM-DD`);
    }
    if (field.type === "time" && value && !isValidTimeStr(value)) {
      errors.push(`${field.label} 格式应为 HH:MM`);
    }
    if (/name|姓名/i.test(field.key) && value.length > 32) {
      errors.push(`${field.label} 长度不能超过 32`);
    }
  }
  return errors;
}

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function inlineMarkdownToHtml(text) {
  let v = escapeHtml(text);
  v = v.replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1");
  v = v.replace(/`([^`]+)`/g, "<code>$1</code>");
  v = v.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  v = v.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  return v;
}

function markdownToReadableHtml(markdown) {
  // Simple markdown to HTML converter for paragraphs, lists, bold, and tables
  const lines = String(markdown || "").split(/\r?\n/);
  const html = [];
  let inList = false;
  let inTable = false;

  const closeList = () => {
    if (inList) {
      html.push("</ul>");
      inList = false;
    }
  };

  const closeTable = () => {
    if (inTable) {
      html.push("</tbody></table>");
      inTable = false;
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const line = raw.trim();

    if (!line || line === "```") {
      closeList();
      closeTable();
      continue;
    }

    // Headers
    if (/^#{1,6}\s+/.test(line)) {
      closeList();
      closeTable();
      html.push(`<p><strong>${inlineMarkdownToHtml(line.replace(/^#{1,6}\s+/, ""))}</strong></p>`);
      continue;
    }

    // Tables
    if (line.startsWith("|") && line.endsWith("|")) {
      closeList();
      
      // Lookahead to see if next line is a separator to handle headers properly
      const isHeaderRow = !inTable && (i + 1 < lines.length && lines[i + 1].trim().startsWith("|") && lines[i + 1].trim().includes("---"));
      
      if (!inTable) {
        html.push("<table>");
        inTable = true;
        if (isHeaderRow) {
          const headers = line.split("|").filter(Boolean).map(c => c.trim());
          html.push("<thead><tr>");
          headers.forEach(h => html.push(`<th>${inlineMarkdownToHtml(h)}</th>`));
          html.push("</tr></thead><tbody>");
          i++; // Skip separator line
          continue;
        } else {
          html.push("<tbody>");
        }
      }
      
      const cells = line.split("|").filter(Boolean).map(c => c.trim());
      html.push("<tr>");
      cells.forEach(c => html.push(`<td>${inlineMarkdownToHtml(c)}</td>`));
      html.push("</tr>");
      continue;
    }

    // Lists
    if (/^[-*+]\s+/.test(line) || /^\d+\.\s+/.test(line)) {
      closeTable();
      if (!inList) {
        html.push("<ul>");
        inList = true;
      }
      html.push(`<li>${inlineMarkdownToHtml(line.replace(/^([-*+]|\d+\.)\s+/, ""))}</li>`);
      continue;
    }

    // Paragraphs
    closeList();
    closeTable();
    html.push(`<p>${inlineMarkdownToHtml(line)}</p>`);
  }
  
  closeList();
  closeTable();
  return html.join("");
}

function renderResult(data) {
  const markdown = data?.ai?.analysis_markdown
    || (Array.isArray(data?.ai?.analysis) ? data.ai.analysis.join("\n") : "");
  if (!markdown) {
    resultEl.textContent = JSON.stringify(data, null, 2);
    return;
  }
  resultEl.innerHTML = markdownToReadableHtml(markdown);
}

async function fetchWithTimeout(url, options = {}, timeoutMs = 120000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function submitCurrent() {
  resultEl.textContent = "分析中...";
  try {
    const rawValues = collectValues();
    const errors = validateValues(rawValues);
    if (errors.length) {
      resultEl.textContent = `输入校验失败：\n- ${errors.join("\n- ")}`;
      return;
    }
    state.forms[state.selected.id] = rawValues;
    saveForms();
    extractProfiles(state.selected, rawValues).forEach(upsertProfile);
    saveProfiles();
    const payload = state.selected.payloadBuilder(rawValues);
    const res = await fetchWithTimeout(state.selected.endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }, 120000);
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`HTTP ${res.status} ${res.statusText}\n${text}`);
    }
    const data = await res.json();
    renderResult(data);
    renderForm();
  } catch (err) {
    if (err.name === "AbortError") {
      resultEl.textContent = "请求超时：请检查网络或稍后重试。";
      return;
    }
    resultEl.textContent = `请求失败：${err.message}`;
  }
}

function resetCurrent() {
  delete state.forms[state.selected.id];
  saveForms();
  renderForm();
  resultEl.textContent = "等待输入...";
}

async function exportPdf() {
  if (state.selected.id !== "marriage") return;
  resultEl.textContent = "正在生成PDF报告，请稍候...";
  try {
    const rawValues = collectValues();
    const errors = validateValues(rawValues);
    if (errors.length) {
      resultEl.textContent = `输入校验失败：\n- ${errors.join("\n- ")}`;
      return;
    }
    const payload = state.selected.payloadBuilder(rawValues);
    const res = await fetchWithTimeout("/api/marriage/pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }, 120000);
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`HTTP ${res.status} ${res.statusText}\n${text}`);
    }
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `合婚报告_${payload.left.name}_${payload.right.name}.pdf`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    a.remove();
    resultEl.textContent = "PDF报告生成成功，已开始下载。";
  } catch (err) {
    if (err.name === "AbortError") {
      resultEl.textContent = "PDF导出超时：请稍后重试。";
      return;
    }
    resultEl.textContent = `PDF导出失败：${err.message}`;
  }
}

function render() {
  renderModules();
  renderForm();
}

submitBtn.addEventListener("click", submitCurrent);
exportPdfBtn.addEventListener("click", exportPdf);
resetBtn.addEventListener("click", resetCurrent);

const initialModuleId = moduleIdFromPath();
if (initialModuleId && moduleMap.has(initialModuleId)) {
  selectModuleById(initialModuleId);
} else {
  selectModuleById(modules[0].id);
}
render();
