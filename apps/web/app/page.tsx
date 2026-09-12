"use client";

import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useState } from "react";

type Tab = "chat" | "constructor" | "calendar" | "library" | "reports" | "watchlist" | "settings";
type Appearance = "classic" | "meow";
type Citation = { message: string; url: string; document_id?: string };
type Message = { id: string; role: "user" | "assistant"; content: string; citations?: Citation[]; created_at?: string };
type ThreadItem = { id: string; title: string; created_at: string; updated_at: string };
type RunEvent = { type: string; payload: Record<string, unknown> };
type CalendarEvent = { id: string; title: string; starts_at: string; status: string; event_type: string; bank_name?: string; source_url?: string };
type DocumentItem = { id: string; title: string; document_type: string; reporting_standard?: string; status: string; created_at: string; source_url?: string; source_tier: string; mime_type?: string; size_bytes?: number; previewable: boolean };
type ReportItem = { id: string; title: string; report_kind: string; status: string; summary?: string; created_at: string; artifacts?: { id: string; format: string }[] };
type WatchItem = { cbr_reg_number: string; bank_name: string; enabled: boolean };
type SystemStatus = { model_configured: boolean; model_key_present: boolean; model_provider: string; model_error: string; orchestrator_model: string; finance_model: string };
type SkillItem = { id: string; version: string; title: string; description: string; category: string; transport: "local" | "service" | "mcp"; side_effects: string; permissions: string[]; timeout_seconds: number; model_policy?: { primary: string; fallback?: string } };
type WorkflowNodeItem = { id: string; skill_id: string; depends_on: string[]; optional: boolean; note?: string };
type WorkflowItem = { id: string; version: string; title: string; description: string; trigger_hints: string[]; nodes: WorkflowNodeItem[]; editable: boolean };

const welcomeMessage: Message = {
  id: "welcome",
  role: "assistant",
  content: "Назовите банк, отчетный период или тему. Я найду первоисточники, покажу ход работы и отделю факты от интерпретации.",
};
const activeThreadStorageKey = "bank-reporter-active-thread";
const appearanceStorageKey = "bank-reporter-appearance";

const tabs: { id: Tab; label: string; symbol: string }[] = [
  { id: "chat", label: "Чат", symbol: "↗" },
  { id: "constructor", label: "Конструктор", symbol: "◇" },
  { id: "calendar", label: "Календарь", symbol: "□" },
  { id: "library", label: "Библиотека", symbol: "≡" },
  { id: "reports", label: "Отчеты", symbol: "◫" },
  { id: "watchlist", label: "Наблюдение", symbol: "◎" },
  { id: "settings", label: "Настройки", symbol: "⚙" },
];

async function api<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function Status({ value }: { value: string }) {
  return <span className={`status status-${value}`}>{value}</span>;
}

function safeExternalUrl(value: string) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : undefined;
  } catch { return undefined; }
}

function inlineMarkdown(value: string, keyPrefix: string): ReactNode[] {
  const tokens = value.split(/(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^\s)]+\))/g);
  return tokens.filter(Boolean).map((token, index) => {
    const key = `${keyPrefix}-${index}`;
    if (token.startsWith("**") && token.endsWith("**")) return <strong key={key}>{token.slice(2, -2)}</strong>;
    if (token.startsWith("`") && token.endsWith("`")) return <code key={key}>{token.slice(1, -1)}</code>;
    const link = token.match(/^\[([^\]]+)]\((https?:\/\/[^\s)]+)\)$/);
    const href = link ? safeExternalUrl(link[2]) : undefined;
    if (link && href) return <a key={key} href={href} target="_blank" rel="noreferrer">{link[1]} ↗</a>;
    return token;
  });
}

function tableCells(line: string) {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}

function isTableSeparator(line: string) {
  const cells = tableCells(line);
  return cells.length > 1 && cells.every((cell) => /^:?-{2,}:?$/.test(cell));
}

function MarkdownMessage({ content }: { content: string }) {
  const lines = content
    .replace(/[\u200B-\u200D\uFEFF]/g, "")
    .replace(/\r\n/g, "\n")
    .replace(/^\s*(#{1,4})([^#\s])/gm, "$1 $2")
    .split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) { index += 1; continue; }
    if (line.includes("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
      const headers = tableCells(line);
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        rows.push(tableCells(lines[index])); index += 1;
      }
      blocks.push(<div className="markdown-table-wrap" key={`table-${index}`}><table><thead><tr>{headers.map((cell, i) => <th key={i}>{inlineMarkdown(cell, `th-${index}-${i}`)}</th>)}</tr></thead><tbody>{rows.map((row, r) => <tr key={r}>{headers.map((_, c) => <td key={c}>{inlineMarkdown(row[c] ?? "", `td-${index}-${r}-${c}`)}</td>)}</tr>)}</tbody></table></div>);
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      const children = inlineMarkdown(heading[2], `h-${index}`);
      blocks.push(level <= 2 ? <h3 key={index}>{children}</h3> : <h4 key={index}>{children}</h4>);
      index += 1; continue;
    }
    if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) { items.push(lines[index].trim().replace(/^[-*]\s+/, "")); index += 1; }
      blocks.push(<ul key={`ul-${index}`}>{items.map((item, i) => <li key={i}>{inlineMarkdown(item, `li-${index}-${i}`)}</li>)}</ul>); continue;
    }
    if (/^\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\d+[.)]\s+/.test(lines[index].trim())) { items.push(lines[index].trim().replace(/^\d+[.)]\s+/, "")); index += 1; }
      blocks.push(<ol key={`ol-${index}`}>{items.map((item, i) => <li key={i}>{inlineMarkdown(item, `oli-${index}-${i}`)}</li>)}</ol>); continue;
    }
    const paragraph = [line]; index += 1;
    while (index < lines.length && lines[index].trim() && !/^(#{1,4})\s+|^[-*]\s+|^\d+[.)]\s+/.test(lines[index].trim()) && !(lines[index].includes("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1]))) {
      paragraph.push(lines[index].trim()); index += 1;
    }
    blocks.push(<p key={`p-${index}`}>{inlineMarkdown(paragraph.join(" "), `p-${index}`)}</p>);
  }
  return <div className="markdown">{blocks}</div>;
}

function Sources({ citations = [] }: { citations?: Citation[] }) {
  const unique = citations.filter((item, index) => safeExternalUrl(item.url) && citations.findIndex((candidate) => candidate.url === item.url) === index);
  if (!unique.length) return null;
  return <details className="message-sources"><summary>Источники <span>{unique.length}</span></summary><ol>{unique.map((item) => <li key={item.url}><a href={safeExternalUrl(item.url)} target="_blank" rel="noreferrer"><b>{item.message || new URL(item.url).hostname}</b><small>{new URL(item.url).hostname} ↗</small></a></li>)}</ol></details>;
}

export default function Home() {
  const [tab, setTab] = useState<Tab>("chat");
  const [appearance, setAppearance] = useState<Appearance>("classic");
  const [threadId, setThreadId] = useState<string>();
  const [threads, setThreads] = useState<ThreadItem[]>([]);
  const [messages, setMessages] = useState<Message[]>([welcomeMessage]);
  const [threadLoading, setThreadLoading] = useState(true);
  const [prompt, setPrompt] = useState("");
  const [progress, setProgress] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [calendar, setCalendar] = useState<CalendarEvent[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [previewReport, setPreviewReport] = useState<ReportItem>();
  const [previewDocument, setPreviewDocument] = useState<DocumentItem>();
  const [analysisDocumentId, setAnalysisDocumentId] = useState<string>();
  const [rebuildingReportId, setRebuildingReportId] = useState<string>();
  const [deletingId, setDeletingId] = useState<string>();
  const [watchlist, setWatchlist] = useState<WatchItem[]>([]);
  const [systemStatus, setSystemStatus] = useState<SystemStatus>();
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowItem[]>([]);

  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("theme");
    if (requested === "classic" || requested === "meow") {
      setAppearance(requested);
      window.localStorage.setItem(appearanceStorageKey, requested);
      return;
    }
    const saved = window.localStorage.getItem(appearanceStorageKey);
    if (saved === "classic" || saved === "meow") setAppearance(saved);
  }, []);

  const toggleAppearance = useCallback(() => {
    setAppearance((current) => {
      const next: Appearance = current === "classic" ? "meow" : "classic";
      window.localStorage.setItem(appearanceStorageKey, next);
      return next;
    });
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [c, d, r, w, s, skillItems, workflowItems] = await Promise.all([
        api<CalendarEvent[]>("/api/calendar"),
        api<DocumentItem[]>("/api/documents"),
        api<ReportItem[]>("/api/reports"),
        api<WatchItem[]>("/api/watchlist"),
        api<SystemStatus>("/api/settings/status"),
        api<SkillItem[]>("/api/skills"),
        api<WorkflowItem[]>("/api/workflows"),
      ]);
      setCalendar(c); setDocuments(d); setReports(r); setWatchlist(w); setSystemStatus(s); setSkills(skillItems); setWorkflows(workflowItems);
    } catch { /* API may still be starting. */ }
  }, []);

  const refreshThreads = useCallback(async () => {
    const items = await api<ThreadItem[]>("/api/threads");
    setThreads(items);
    return items;
  }, []);

  const openThread = useCallback(async (id: string) => {
    setThreadLoading(true); setError(""); setProgress([]);
    try {
      const savedMessages = await api<Message[]>(`/api/threads/${id}/messages`);
      setThreadId(id);
      setMessages(savedMessages.length ? savedMessages : [welcomeMessage]);
      window.localStorage.setItem(activeThreadStorageKey, id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось открыть сохраненный чат");
    } finally { setThreadLoading(false); }
  }, []);

  const newThread = useCallback(() => {
    setThreadId(undefined); setMessages([welcomeMessage]); setPrompt(""); setProgress([]); setError("");
    window.localStorage.removeItem(activeThreadStorageKey);
  }, []);

  const deleteThreadItem = useCallback(async (thread: ThreadItem) => {
    if (!window.confirm(`Удалить чат «${thread.title}» и все сообщения в нем?`)) return;
    setDeletingId(thread.id); setError("");
    try {
      await api<void>(`/api/threads/${thread.id}`, { method: "DELETE" });
      const remaining = await refreshThreads();
      if (thread.id === threadId) {
        const next = remaining[0];
        if (next) await openThread(next.id);
        else newThread();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось удалить чат");
    } finally { setDeletingId(undefined); }
  }, [newThread, openThread, refreshThreads, threadId]);

  useEffect(() => {
    void refresh();
    void (async () => {
      try {
        const items = await refreshThreads();
        const savedId = window.localStorage.getItem(activeThreadStorageKey);
        const target = items.find((item) => item.id === savedId)?.id ?? items[0]?.id;
        if (target) await openThread(target);
        else setThreadLoading(false);
      } catch { setThreadLoading(false); }
    })();
  }, [openThread, refresh, refreshThreads]);

  useEffect(() => {
    if (!reports.some((item) => ["queued", "processing"].includes(item.status))) return;
    const timer = window.setTimeout(() => void refresh(), 3000);
    return () => window.clearTimeout(timer);
  }, [reports, refresh]);

  const analyzeDocument = async (item: DocumentItem) => {
    setError(""); setAnalysisDocumentId(item.id);
    try {
      await api<ReportItem>("/api/reports", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({
          title: `Анализ · ${item.title}`,
          document_ids: [item.id],
          report_kind: "financial",
          question: "Проанализируй ключевые финансовые показатели, динамику доступных периодов, риски и ограничения. Каждое число свяжи с первоисточником.",
          output_formats: ["html", "pdf", "png", "xlsx", "csv"],
        }),
      });
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось запустить анализ"); }
    finally { setAnalysisDocumentId(undefined); }
  };

  const deleteReportItem = async (item: ReportItem) => {
    if (!window.confirm(`Удалить аналитический отчет «${item.title}» и все его выгрузки?`)) return;
    setDeletingId(item.id); setError("");
    try {
      await api<void>(`/api/reports/${item.id}`, { method: "DELETE" });
      if (previewReport?.id === item.id) setPreviewReport(undefined);
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось удалить отчет"); }
    finally { setDeletingId(undefined); }
  };

  const rebuildReport = async (item: ReportItem) => {
    setError(""); setRebuildingReportId(item.id);
    if (previewReport?.id === item.id) setPreviewReport(undefined);
    try {
      await api<ReportItem>(`/api/reports/${item.id}/rebuild`, { method: "POST" });
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось пересобрать отчет"); }
    finally { setRebuildingReportId(undefined); }
  };

  const deleteDocumentItem = async (item: DocumentItem) => {
    if (!window.confirm(`Удалить оригинал «${item.title}» и все извлеченные из него факты?`)) return;
    setDeletingId(item.id); setError("");
    try {
      await api<void>(`/api/documents/${item.id}`, { method: "DELETE" });
      if (previewDocument?.id === item.id) setPreviewDocument(undefined);
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось удалить документ"); }
    finally { setDeletingId(undefined); }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const text = prompt.trim();
    if (!text || busy) return;
    setPrompt(""); setError(""); setProgress([]); setBusy(true);
    setMessages((m) => [...m, { id: crypto.randomUUID(), role: "user", content: text }]);
    try {
      let activeThread = threadId;
      if (!activeThread) {
        const thread = await api<ThreadItem>("/api/threads", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: text.slice(0, 80) }) });
        activeThread = thread.id; setThreadId(activeThread); window.localStorage.setItem(activeThreadStorageKey, activeThread);
      }
      const run = await api<{ run_id: string }>(`/api/threads/${activeThread}/messages`, {
        method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify({ content: text }),
      });
      void refreshThreads();
      const runCitations: Citation[] = [];
      const stream = new EventSource(`/api/runs/${run.run_id}/events`);
      stream.onmessage = (e) => {
        const item = JSON.parse(e.data) as RunEvent;
        if (["status", "tool_started", "citation", "artifact_ready"].includes(item.type)) {
          const label = String(item.payload.message ?? item.payload.name ?? item.type);
          setProgress((p) => [...p.slice(-7), label]);
        }
        if (item.type === "citation" && typeof item.payload.url === "string" && !runCitations.some((source) => source.url === item.payload.url)) {
          runCitations.push({ message: String(item.payload.message ?? "Источник"), url: item.payload.url, document_id: typeof item.payload.document_id === "string" ? item.payload.document_id : undefined });
        }
        if (item.type === "completed") {
          const content = String(item.payload.answer ?? "Готово.");
          const completedCitations = Array.isArray(item.payload.citations) ? item.payload.citations as Citation[] : runCitations;
          setMessages((m) => [...m, { id: crypto.randomUUID(), role: "assistant", content, citations: completedCitations }]);
          setBusy(false); setProgress([]); stream.close(); void refresh(); void refreshThreads();
        }
        if (item.type === "failed") {
          setError(String(item.payload.error ?? "Задание завершилось с ошибкой"));
          setBusy(false); stream.close();
        }
      };
      stream.onerror = () => { setError("Поток событий прерван. Результат сохранен в истории."); setBusy(false); stream.close(); };
    } catch (e) { setError(e instanceof Error ? e.message : "Ошибка"); setBusy(false); }
  };

  const title = useMemo(() => tabs.find((item) => item.id === tab)?.label, [tab]);

  return (
    <main className="shell" data-theme={appearance}>
      <aside className="sidebar">
        <div className="brand"><div className="mark" aria-hidden="true">{appearance === "meow" ? "🐱" : "BR"}</div><div><strong>Bank Reporter</strong><small>{appearance === "meow" ? "пушистый корреспондент" : "корреспондент-агент"}</small></div></div>
        <nav>{tabs.map((item) => <button key={item.id} className={tab === item.id ? "active" : ""} onClick={() => setTab(item.id)}><span>{item.symbol}</span>{item.label}</button>)}</nav>
        <div className="sidebar-foot"><span className="pulse" /> локальный контур<small>{appearance === "meow" ? "Данные под защитой котиков и кроликов" : "Данные остаются на устройстве"}</small></div>
      </aside>

      <section className="workspace">
        <header><div><p className="eyebrow">BANKING INTELLIGENCE / {new Date().toLocaleDateString("ru-RU", { timeZone: "Europe/Moscow" })}</p><h1>{title}</h1></div><div className="header-actions"><button className="theme-toggle" type="button" aria-pressed={appearance === "meow"} aria-label={appearance === "meow" ? "Включить деловую тему" : "Включить розовую тему с котиками и кроликами"} onClick={toggleAppearance}><span aria-hidden="true">{appearance === "meow" ? "🐱🐰" : "◐"}</span>{appearance === "meow" ? "Котики и кролики" : "Деловая"}</button><button className="refresh" onClick={() => void refresh()}>Обновить данные</button></div></header>

        {tab === "chat" && <div className="chat-layout">
          <div className="chat-card">
            <div className="messages">{threadLoading ? <div className="chat-loading">Загружаю историю…</div> : messages.map((message) => <article key={message.id} className={`message ${message.role}`}><span>{message.role === "assistant" ? "BR" : "ВЫ"}</span><div>{message.role === "assistant" ? <><MarkdownMessage content={message.content} /><Sources citations={message.citations} /></> : message.content}</div></article>)}</div>
            {progress.length > 0 && <div className="progress"><b>Ход исследования</b>{progress.map((line, i) => <div key={`${line}-${i}`}><i />{line}</div>)}</div>}
            {error && <div className="error">{error}</div>}
            <form onSubmit={submit}><textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Например: найди МСФО ВТБ за I полугодие и сравни прибыль год к году" /><button disabled={busy}>{busy ? "Исследую…" : "Отправить"}</button></form>
            <p className="disclaimer">Не является инвестиционной рекомендацией · Все выводы должны содержать ссылки на первоисточники</p>
          </div>
          <aside className="context">
            <div className="chat-history-head"><h3>Сохраненные чаты</h3><button disabled={busy} onClick={newThread}>+ Новый</button></div>
            <div className="chat-history">{threads.length ? threads.map((thread) => <div key={thread.id} className={`chat-history-item ${thread.id === threadId ? "active" : ""}`}><button className="chat-history-open" disabled={busy || threadLoading} onClick={() => void openThread(thread.id)}><b>{thread.title}</b><small>{new Date(thread.updated_at).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</small></button><button className="chat-history-delete" disabled={busy || threadLoading || deletingId === thread.id} title="Удалить чат" aria-label={`Удалить чат ${thread.title}`} onClick={() => void deleteThreadItem(thread)}>{deletingId === thread.id ? "…" : "Удалить"}</button></div>) : <p>История появится после первого запроса.</p>}</div>
            <h3>Быстрый старт</h3>{["Найди последнюю МСФО Сбера", "Что изменилось в ставке ЦБ?", "Статьи о качестве кредитов", "Сравни два отчетных периода"].map((q) => <button key={q} onClick={() => setPrompt(q)}>{q}</button>)}<h3>Состояние</h3><dl><div><dt>Документы</dt><dd>{documents.length}</dd></div><div><dt>Отчеты</dt><dd>{reports.length}</dd></div><div><dt>События</dt><dd>{calendar.length}</dd></div></dl>
          </aside>
        </div>}

        {tab === "constructor" && <WorkflowConstructor skills={skills} workflows={workflows} onChanged={refresh} />}

        {tab === "calendar" && <Panel title="Календарь банковских событий" action={<a href="/api/calendar.ics">Экспортировать ICS</a>}><CalendarMonth events={calendar} /></Panel>}

        {tab === "library" && <Panel title="Оригиналы и извлеченные данные"><Upload onDone={refresh} /><div className="table">{documents.length ? documents.map((item) => <div className="row" key={item.id}><div className="file-icon">{item.document_type.slice(0, 3).toUpperCase()}</div><div><b>{item.title}</b><small>{new Date(item.created_at).toLocaleString("ru-RU")}</small></div><Status value={item.status} /><div className="row-actions"><a href={`/api/documents/${item.id}/download`}>Скачать</a><button className="delete-link" disabled={deletingId === item.id} onClick={() => void deleteDocumentItem(item)}>{deletingId === item.id ? "Удаляю…" : "Удалить"}</button></div></div>) : <Empty text="Загрузите PDF/XLSX/CSV или попросите агента найти отчет." />}</div></Panel>}

        {tab === "reports" && <Panel title="Отчеты">
          {error && <div className="error">{error}</div>}
          <section className="report-section"><div className="report-section-head"><div><p className="eyebrow">ОРИГИНАЛЫ</p><h3>Найденные PDF-отчеты</h3></div><span>Анализ запускается только по вашему запросу</span></div><div className="cards">{documents.filter((item) => item.previewable).length ? documents.filter((item) => item.previewable).map((item) => <article className="report-card source-report-card" key={item.id}><p>PDF / {item.reporting_standard ?? item.document_type} / {new Date(item.created_at).toLocaleDateString("ru-RU")}</p><h3>{item.title}</h3><span className="report-summary">Оригинал сохранен без изменений · {item.size_bytes ? formatBytes(item.size_bytes) : "размер уточняется"}</span><Status value={item.status} /><div className="report-actions"><button onClick={() => setPreviewDocument(item)}>Предпросмотр</button><button className="analyze-button" disabled={analysisDocumentId === item.id} onClick={() => void analyzeDocument(item)}>{analysisDocumentId === item.id ? "Запускаю…" : "Проанализировать"}</button><a href={`/api/documents/${item.id}/download`}>Скачать PDF</a><button className="delete-button" disabled={deletingId === item.id} onClick={() => void deleteDocumentItem(item)}>{deletingId === item.id ? "Удаляю…" : "Удалить"}</button></div>{item.source_url && <details className="card-source"><summary>Первоисточник</summary><a href={safeExternalUrl(item.source_url)} target="_blank" rel="noreferrer">Открыть официальный источник ↗</a></details>}</article>) : <Empty text="Попросите агента найти отчет или загрузите PDF в библиотеке." />}</div></section>
          <section className="report-section"><div className="report-section-head"><div><p className="eyebrow">АНАЛИТИКА</p><h3>Подготовленные аналитические отчеты</h3></div><span>HTML-предпросмотр и выгрузки</span></div><div className="cards">{reports.length ? reports.map((item) => { const hasPreview = item.artifacts?.some((artifact) => artifact.format === "html"); const processing = item.status === "queued" || item.status === "processing"; return <article className="report-card" key={item.id}><p>ANALYSIS / {new Date(item.created_at).toLocaleDateString("ru-RU")}</p><h3>{item.title}</h3>{item.summary && <span className="report-summary">{item.summary}</span>}<Status value={item.status} /><div className="report-actions"><button disabled={!hasPreview || processing} onClick={() => setPreviewReport(item)}>{processing ? "Готовится…" : "Предпросмотр"}</button><button className="analyze-button" disabled={processing || rebuildingReportId === item.id} onClick={() => void rebuildReport(item)}>{rebuildingReportId === item.id ? "Запускаю…" : "Пересобрать"}</button><span>Скачать:</span>{item.artifacts?.filter((artifact) => artifact.format !== "html").map((artifact) => <a key={artifact.id} href={`/api/artifacts/${artifact.id}/download`}>{artifact.format.toUpperCase()}</a>)}<button className="delete-button" disabled={processing || deletingId === item.id} title={processing ? "Удаление доступно после завершения" : "Удалить отчет"} onClick={() => void deleteReportItem(item)}>{deletingId === item.id ? "Удаляю…" : "Удалить"}</button></div></article>; }) : <Empty text="Выберите PDF выше и нажмите «Проанализировать» или попросите об анализе в чате." />}</div></section>
          {previewReport && <ReportPreview report={previewReport} onClose={() => setPreviewReport(undefined)} />}{previewDocument && <DocumentPreview document={previewDocument} onClose={() => setPreviewDocument(undefined)} />}
        </Panel>}

        {tab === "watchlist" && <Panel title="Банки под наблюдением"><BankSearch onAdded={refresh} /><div className="table">{watchlist.length ? watchlist.map((item) => <div className="row" key={item.cbr_reg_number}><div className="file-icon">{item.bank_name.slice(0, 2)}</div><div><b>{item.bank_name}</b><small>Рег. № {item.cbr_reg_number}</small></div><Status value={item.enabled ? "active" : "paused"} /></div>) : <Empty text="Найдите банк и включите наблюдение — поиск в чате работает и без подписки." />}</div></Panel>}

        {tab === "settings" && <Panel title="Настройки запуска"><div className="settings-grid"><Setting title={systemStatus?.model_provider ?? "Провайдер моделей"} state={systemStatus?.model_configured ? "Настроен" : systemStatus?.model_key_present ? "Проверьте ключ" : "Не настроен"} stateOk={systemStatus?.model_configured} text={systemStatus?.model_error || `Основной агент — ${systemStatus?.orchestrator_model ?? "DeepSeek V4.1 Flash"}, финансовый — ${systemStatus?.finance_model ?? "Ling 3.0 Flash Fin"}. Ключ и адрес API читаются из корневого .env.`} /><Setting title="Telegram" text="Укажите TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID для дайджестов и срочных уведомлений." /><Setting title="Хранилище" text="Оригиналы и версии сохраняются в локальном Docker volume до ручного удаления." /><Setting title="Безопасность" text="Только публичный read-only веб, без входа, CAPTCHA, платежей и отправки форм." /></div></Panel>}
      </section>
    </main>
  );
}

function Panel({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) { return <section className="panel"><div className="panel-head"><h2>{title}</h2>{action}</div>{children}</section>; }
function Empty({ text }: { text: string }) { return <div className="empty"><span>∅</span><p>{text}</p></div>; }
function Setting({ title, text, state, stateOk }: { title: string; text: string; state?: string; stateOk?: boolean }) { return <article className="setting"><div className="setting-title"><p>{title}</p>{state && <span className={stateOk ? "config-ok" : "config-bad"}>{state}</span>}</div><span>{text}</span></article>; }

function formatBytes(value: number) {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} КБ`;
  return `${(value / 1024 / 1024).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} МБ`;
}

function DocumentPreview({ document, onClose }: { document: DocumentItem; onClose: () => void }) {
  return <div className="preview-backdrop" role="dialog" aria-modal="true" aria-label={`Предпросмотр: ${document.title}`} onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="preview-window"><div className="preview-toolbar"><div><span>Оригинальный PDF</span><b>{document.title}</b></div><div><a href={`/api/documents/${document.id}/preview`} target="_blank" rel="noreferrer">Открыть отдельно ↗</a><a href={`/api/documents/${document.id}/download`}>Скачать</a><button onClick={onClose} aria-label="Закрыть предпросмотр">Закрыть</button></div></div><iframe src={`/api/documents/${document.id}/preview`} title={`PDF ${document.title}`} /></section>
  </div>;
}

function ReportPreview({ report, onClose }: { report: ReportItem; onClose: () => void }) {
  return <div className="preview-backdrop" role="dialog" aria-modal="true" aria-label={`Предпросмотр: ${report.title}`} onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="preview-window"><div className="preview-toolbar"><div><span>Предпросмотр отчета</span><b>{report.title}</b></div><div><a href={`/api/reports/${report.id}/preview`} target="_blank" rel="noreferrer">Открыть отдельно ↗</a><button onClick={onClose} aria-label="Закрыть предпросмотр">Закрыть</button></div></div><iframe src={`/api/reports/${report.id}/preview`} title={`Отчет ${report.title}`} sandbox="allow-popups allow-popups-to-escape-sandbox" /></section>
  </div>;
}

function WorkflowConstructor({ skills, workflows, onChanged }: { skills: SkillItem[]; workflows: WorkflowItem[]; onChanged: () => Promise<void> }) {
  const [selectedId, setSelectedId] = useState("");
  const [draft, setDraft] = useState<WorkflowNodeItem[]>([]);
  const [name, setName] = useState("");
  const [hints, setHints] = useState("");
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const selected = workflows.find((item) => item.id === selectedId);

  useEffect(() => {
    if (!selectedId && workflows[0]) setSelectedId(workflows[0].id);
  }, [selectedId, workflows]);

  useEffect(() => {
    const workflow = workflows.find((item) => item.id === selectedId);
    if (!workflow) return;
    setDraft(workflow.nodes.map((node) => ({ ...node, depends_on: [...node.depends_on] })));
    setName(workflow.title);
    setHints(workflow.trigger_hints.join(", "));
    setNotice("");
  }, [selectedId, workflows]);

  const linearize = (nodes: WorkflowNodeItem[]) => nodes.map((node, index) => ({ ...node, depends_on: index ? [nodes[index - 1].id] : [] }));
  const addSkill = (skill: SkillItem) => {
    let nodeId = skill.id;
    let suffix = 2;
    while (draft.some((node) => node.id === nodeId)) nodeId = `${skill.id}_${suffix++}`;
    setDraft(linearize([...draft, { id: nodeId, skill_id: skill.id, depends_on: [], optional: false }]));
    setNotice("");
  };
  const removeNode = (index: number) => setDraft(linearize(draft.filter((_, itemIndex) => itemIndex !== index)));
  const moveNode = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= draft.length) return;
    const next = [...draft];
    [next[index], next[target]] = [next[target], next[index]];
    setDraft(linearize(next));
  };
  const save = async () => {
    if (!name.trim() || !draft.length) { setNotice("Добавьте название и хотя бы один skill."); return; }
    setSaving(true); setNotice("");
    const id = selected?.editable ? selected.id : `custom_${crypto.randomUUID().replaceAll("-", "")}`;
    const payload: WorkflowItem = {
      id, version: "1.0.0", title: name.trim(),
      description: `Пользовательская цепочка из ${draft.length} skills`,
      trigger_hints: hints.split(",").map((item) => item.trim()).filter(Boolean),
      nodes: linearize(draft), editable: true,
    };
    try {
      await api("/api/workflows/validate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      await api(`/api/workflows/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      await onChanged(); setSelectedId(id); setNotice("Workflow сохранён и доступен оркестратору.");
    } catch (e) { setNotice(e instanceof Error ? e.message : "Не удалось сохранить workflow"); }
    finally { setSaving(false); }
  };
  const removeWorkflow = async () => {
    if (!selected?.editable || !window.confirm(`Удалить workflow «${selected.title}»?`)) return;
    setSaving(true);
    try { await api(`/api/workflows/${selected.id}`, { method: "DELETE" }); setSelectedId(workflows.find((item) => !item.editable)?.id ?? ""); await onChanged(); }
    catch (e) { setNotice(e instanceof Error ? e.message : "Не удалось удалить workflow"); }
    finally { setSaving(false); }
  };

  return <section className="constructor-layout">
    <aside className="workflow-library">
      <div className="constructor-heading"><p className="eyebrow">WORKFLOWS</p><h2>Готовые сценарии</h2><span>{workflows.length}</span></div>
      <div className="workflow-list">{workflows.map((workflow) => <button key={workflow.id} className={workflow.id === selectedId ? "active" : ""} onClick={() => setSelectedId(workflow.id)}><span>{workflow.editable ? "CUSTOM" : "BUILT-IN"}</span><b>{workflow.title}</b><small>{workflow.nodes.length} узлов</small></button>)}</div>
    </aside>
    <div className="workflow-canvas">
      <div className="constructor-heading canvas-head"><div><p className="eyebrow">КОМПОЗИЦИЯ</p><input aria-label="Название workflow" value={name} onChange={(event) => setName(event.target.value)} /></div><div className="constructor-actions"><button disabled={saving || !draft.length} onClick={() => void save()}>{saving ? "Сохраняю…" : selected?.editable ? "Сохранить" : "Сохранить копию"}</button>{selected?.editable && <button className="danger" disabled={saving} onClick={() => void removeWorkflow()}>Удалить</button>}</div></div>
      <label className="workflow-hints"><span>Фразы-триггеры</span><input value={hints} onChange={(event) => setHints(event.target.value)} placeholder="например: кредитный риск, сравни банки" /></label>
      <div className="pipeline" aria-label="Цепочка skills">{draft.length ? draft.map((node, index) => { const skill = skills.find((item) => item.id === node.skill_id); return <div className="pipeline-step" key={node.id}>{index > 0 && <i className="pipeline-link">→</i>}<article><div><span>{skill?.category ?? "skill"}</span><em>{skill?.transport ?? "local"}</em></div><b>{skill?.title ?? node.skill_id}</b><small>{node.skill_id}</small><footer><button title="Переместить влево" disabled={!index} onClick={() => moveNode(index, -1)}>←</button><button title="Переместить вправо" disabled={index === draft.length - 1} onClick={() => moveNode(index, 1)}>→</button><button className="remove-node" title="Удалить узел" onClick={() => removeNode(index)}>×</button></footer></article></div>; }) : <Empty text="Добавьте skills из палитры справа." />}</div>
      {notice && <p className="constructor-notice">{notice}</p>}
      <div className="workflow-explainer"><b>Как исполняется схема</b><span>Оркестратор передаёт между узлами типизированные результаты. Локальные расчёты остаются внутри worker, внешние источники подключаются через service/MCP-адаптеры.</span></div>
    </div>
    <aside className="skill-palette">
      <div className="constructor-heading"><p className="eyebrow">SKILL REGISTRY</p><h2>Доступные skills</h2><span>{skills.length}</span></div>
      <div className="skill-list">{skills.map((skill) => <article key={skill.id}><div><span className={`transport transport-${skill.transport}`}>{skill.transport}</span><small>{skill.version}</small></div><b>{skill.title}</b><p>{skill.description}</p>{skill.model_policy && <small className="model-route">{skill.model_policy.primary.split("/").at(-1)} → {skill.model_policy.fallback?.split("/").at(-1)}</small>}<button onClick={() => addSkill(skill)}>+ Добавить</button></article>)}</div>
    </aside>
  </section>;
}

const monthFormatter = new Intl.DateTimeFormat("ru-RU", { month: "long", year: "numeric" });
const dayKeyFormatter = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Moscow", year: "numeric", month: "2-digit", day: "2-digit" });
const weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const statusLabels: Record<string, string> = { confirmed: "подтверждено", forecast: "прогноз", published: "опубликовано", changed: "изменено", cancelled: "отменено" };

function dateKey(value: string | Date) {
  const parts = dayKeyFormatter.formatToParts(typeof value === "string" ? new Date(value) : value);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

function CalendarMonth({ events }: { events: CalendarEvent[] }) {
  const [cursor, setCursor] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1, 12));
  const [status, setStatus] = useState("all");
  const [eventType, setEventType] = useState("all");
  const [selectedDay, setSelectedDay] = useState(() => dateKey(new Date()));
  const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1, 12);
  const offset = (first.getDay() + 6) % 7;
  const gridStart = new Date(first); gridStart.setDate(first.getDate() - offset);
  const days = Array.from({ length: 42 }, (_, index) => { const day = new Date(gridStart); day.setDate(gridStart.getDate() + index); return day; });
  const eventTypes = Array.from(new Set(events.map((item) => item.event_type))).sort();
  const filtered = events.filter((item) => (status === "all" || item.status === status) && (eventType === "all" || item.event_type === eventType));
  const byDay = filtered.reduce<Record<string, CalendarEvent[]>>((acc, item) => { (acc[dateKey(item.starts_at)] ??= []).push(item); return acc; }, {});
  const selectedEvents = (byDay[selectedDay] ?? []).sort((a, b) => a.starts_at.localeCompare(b.starts_at));
  const move = (delta: number) => { const next = new Date(cursor.getFullYear(), cursor.getMonth() + delta, 1, 12); setCursor(next); setSelectedDay(dateKey(next)); };
  const today = () => { const now = new Date(); setCursor(new Date(now.getFullYear(), now.getMonth(), 1, 12)); setSelectedDay(dateKey(now)); };

  return <div className="calendar-view">
    <div className="calendar-toolbar">
      <div className="month-navigation"><button aria-label="Предыдущий месяц" onClick={() => move(-1)}>←</button><h3>{monthFormatter.format(cursor)}</h3><button aria-label="Следующий месяц" onClick={() => move(1)}>→</button><button className="today-button" onClick={today}>Сегодня</button></div>
      <div className="calendar-filters"><select aria-label="Тип события" value={eventType} onChange={(e) => setEventType(e.target.value)}><option value="all">Все типы</option>{eventTypes.map((type) => <option key={type} value={type}>{type}</option>)}</select><select aria-label="Статус" value={status} onChange={(e) => setStatus(e.target.value)}><option value="all">Все статусы</option>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
    </div>
    <div className="month-grid">{weekdays.map((day) => <div className="weekday" key={day}>{day}</div>)}{days.map((day) => { const key = dateKey(day); const dayEvents = byDay[key] ?? []; const outside = day.getMonth() !== cursor.getMonth(); return <div key={key} className={`day-cell ${outside ? "other-month" : ""} ${key === selectedDay ? "selected" : ""} ${key === dateKey(new Date()) ? "today" : ""}`}><button className="day-select" aria-label={`Выбрать ${day.toLocaleDateString("ru-RU")}`} onClick={() => setSelectedDay(key)} /><span className="day-number">{day.getDate()}</span><span className="day-events">{dayEvents.slice(0, 3).map((item) => item.status === "published" && item.source_url ? <a key={item.id} href={item.source_url} target="_blank" rel="noreferrer" className={`event-pill event-${item.status} event-link`} title={`Открыть: ${item.title}`}><i />{item.title}<em>↗</em></a> : <button key={item.id} type="button" className={`event-pill event-${item.status}`} title={item.title} onClick={() => setSelectedDay(key)}><i />{item.title}</button>)}{dayEvents.length > 3 && <span className="more-events">+{dayEvents.length - 3}</span>}</span></div>; })}</div>
    <div className="calendar-detail"><div><p className="detail-date">{new Date(`${selectedDay}T12:00:00`).toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" })}</p><h3>{selectedEvents.length ? `События: ${selectedEvents.length}` : "Событий нет"}</h3></div><div className="detail-events">{selectedEvents.map((item) => { const publishedLink = item.status === "published" && item.source_url; return <article key={item.id}><time>{new Date(item.starts_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Moscow" })}</time><div>{publishedLink ? <a className="event-source-link" href={item.source_url} target="_blank" rel="noreferrer"><b>{item.title}</b><span>Открыть публикацию ↗</span></a> : <b>{item.title}</b>}<small>{item.bank_name ?? item.event_type}{!publishedLink && item.status !== "cancelled" ? " · ссылка появится после публикации" : ""}</small></div><Status value={item.status} /></article>; })}</div></div>
    <div className="calendar-legend">{Object.entries(statusLabels).map(([value, label]) => <span key={value}><i className={`event-${value}`} />{label}</span>)}</div>
  </div>;
}

function Upload({ onDone }: { onDone: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  return <label className="upload"><input type="file" accept=".pdf,.xlsx,.csv" disabled={busy} onChange={async (e) => { const file = e.target.files?.[0]; if (!file) return; setBusy(true); const body = new FormData(); body.append("file", file); try { await api("/api/documents/upload", { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body }); await onDone(); } finally { setBusy(false); e.target.value = ""; } }} />{busy ? "Обрабатываем файл…" : "+ Загрузить PDF, XLSX или CSV"}</label>;
}

function BankSearch({ onAdded }: { onAdded: () => Promise<void> }) {
  const [query, setQuery] = useState(""); const [found, setFound] = useState<{ cbr_reg_number: string; name: string }[]>([]);
  return <div className="bank-search"><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Название банка" /><button onClick={async () => setFound(await api(`/api/banks/search?q=${encodeURIComponent(query)}`))}>Найти</button>{found.map((bank) => <button className="bank-result" key={bank.cbr_reg_number} onClick={async () => { await api(`/api/watchlist/${bank.cbr_reg_number}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ bank_name: bank.name }) }); setFound([]); await onAdded(); }}>+ {bank.name}</button>)}</div>;
}
