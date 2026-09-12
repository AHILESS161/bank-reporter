"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type Tab = "chat" | "calendar" | "library" | "reports" | "watchlist" | "settings";
type Message = { id: string; role: "user" | "assistant"; content: string; created_at?: string };
type RunEvent = { type: string; payload: Record<string, unknown> };
type CalendarEvent = { id: string; title: string; starts_at: string; status: string; event_type: string; bank_name?: string; source_url?: string };
type DocumentItem = { id: string; title: string; document_type: string; status: string; created_at: string; source_url?: string };
type ReportItem = { id: string; title: string; report_kind: string; status: string; summary?: string; created_at: string; artifacts?: { id: string; format: string }[] };
type WatchItem = { cbr_reg_number: string; bank_name: string; enabled: boolean };
type SystemStatus = { model_configured: boolean; model_key_present: boolean; model_provider: string; model_error: string; orchestrator_model: string; finance_model: string };

const tabs: { id: Tab; label: string; symbol: string }[] = [
  { id: "chat", label: "Чат", symbol: "↗" },
  { id: "calendar", label: "Календарь", symbol: "□" },
  { id: "library", label: "Библиотека", symbol: "≡" },
  { id: "reports", label: "Отчеты", symbol: "◫" },
  { id: "watchlist", label: "Наблюдение", symbol: "◎" },
  { id: "settings", label: "Настройки", symbol: "⚙" },
];

async function api<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

function Status({ value }: { value: string }) {
  return <span className={`status status-${value}`}>{value}</span>;
}

export default function Home() {
  const [tab, setTab] = useState<Tab>("chat");
  const [threadId, setThreadId] = useState<string>();
  const [messages, setMessages] = useState<Message[]>([
    { id: "welcome", role: "assistant", content: "Назовите банк, отчетный период или тему. Я найду первоисточники, покажу ход работы и отделю факты от интерпретации." },
  ]);
  const [prompt, setPrompt] = useState("");
  const [progress, setProgress] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [calendar, setCalendar] = useState<CalendarEvent[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [previewReport, setPreviewReport] = useState<ReportItem>();
  const [watchlist, setWatchlist] = useState<WatchItem[]>([]);
  const [systemStatus, setSystemStatus] = useState<SystemStatus>();

  const refresh = useCallback(async () => {
    try {
      const [c, d, r, w, s] = await Promise.all([
        api<CalendarEvent[]>("/api/calendar"),
        api<DocumentItem[]>("/api/documents"),
        api<ReportItem[]>("/api/reports"),
        api<WatchItem[]>("/api/watchlist"),
        api<SystemStatus>("/api/settings/status"),
      ]);
      setCalendar(c); setDocuments(d); setReports(r); setWatchlist(w); setSystemStatus(s);
    } catch { /* API may still be starting. */ }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const text = prompt.trim();
    if (!text || busy) return;
    setPrompt(""); setError(""); setProgress([]); setBusy(true);
    setMessages((m) => [...m, { id: crypto.randomUUID(), role: "user", content: text }]);
    try {
      let activeThread = threadId;
      if (!activeThread) {
        const thread = await api<{ id: string }>("/api/threads", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: text.slice(0, 80) }) });
        activeThread = thread.id; setThreadId(activeThread);
      }
      const run = await api<{ run_id: string }>(`/api/threads/${activeThread}/messages`, {
        method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify({ content: text }),
      });
      const stream = new EventSource(`/api/runs/${run.run_id}/events`);
      stream.onmessage = (e) => {
        const item = JSON.parse(e.data) as RunEvent;
        if (["status", "tool_started", "citation", "artifact_ready"].includes(item.type)) {
          const label = String(item.payload.message ?? item.payload.name ?? item.type);
          setProgress((p) => [...p.slice(-7), label]);
        }
        if (item.type === "completed") {
          const content = String(item.payload.answer ?? "Готово.");
          setMessages((m) => [...m, { id: crypto.randomUUID(), role: "assistant", content }]);
          setBusy(false); stream.close(); void refresh();
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
    <main className="shell">
      <aside className="sidebar">
        <div className="brand"><div className="mark">BR</div><div><strong>Bank Reporter</strong><small>корреспондент-агент</small></div></div>
        <nav>{tabs.map((item) => <button key={item.id} className={tab === item.id ? "active" : ""} onClick={() => setTab(item.id)}><span>{item.symbol}</span>{item.label}</button>)}</nav>
        <div className="sidebar-foot"><span className="pulse" /> локальный контур<small>Данные остаются на устройстве</small></div>
      </aside>

      <section className="workspace">
        <header><div><p className="eyebrow">BANKING INTELLIGENCE / {new Date().toLocaleDateString("ru-RU")}</p><h1>{title}</h1></div><button className="refresh" onClick={() => void refresh()}>Обновить данные</button></header>

        {tab === "chat" && <div className="chat-layout">
          <div className="chat-card">
            <div className="messages">{messages.map((message) => <article key={message.id} className={`message ${message.role}`}><span>{message.role === "assistant" ? "BR" : "ВЫ"}</span><div>{message.content}</div></article>)}</div>
            {progress.length > 0 && <div className="progress"><b>Ход исследования</b>{progress.map((line, i) => <div key={`${line}-${i}`}><i />{line}</div>)}</div>}
            {error && <div className="error">{error}</div>}
            <form onSubmit={submit}><textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Например: найди МСФО ВТБ за I полугодие и сравни прибыль год к году" /><button disabled={busy}>{busy ? "Исследую…" : "Отправить"}</button></form>
            <p className="disclaimer">Не является инвестиционной рекомендацией · Все выводы должны содержать ссылки на первоисточники</p>
          </div>
          <aside className="context"><h3>Быстрый старт</h3>{["Найди последнюю МСФО Сбера", "Что изменилось в ставке ЦБ?", "Статьи о качестве кредитов", "Сравни два отчетных периода"].map((q) => <button key={q} onClick={() => setPrompt(q)}>{q}</button>)}<h3>Состояние</h3><dl><div><dt>Документы</dt><dd>{documents.length}</dd></div><div><dt>Отчеты</dt><dd>{reports.length}</dd></div><div><dt>События</dt><dd>{calendar.length}</dd></div></dl></aside>
        </div>}

        {tab === "calendar" && <Panel title="Календарь банковских событий" action={<a href="/api/calendar.ics">Экспортировать ICS</a>}><CalendarMonth events={calendar} /></Panel>}

        {tab === "library" && <Panel title="Оригиналы и извлеченные данные"><Upload onDone={refresh} /><div className="table">{documents.length ? documents.map((item) => <div className="row" key={item.id}><div className="file-icon">{item.document_type.slice(0, 3).toUpperCase()}</div><div><b>{item.title}</b><small>{new Date(item.created_at).toLocaleString("ru-RU")}</small></div><Status value={item.status} /><a href={`/api/documents/${item.id}/download`}>Скачать</a></div>) : <Empty text="Загрузите PDF/XLSX/CSV или попросите агента найти отчет." />}</div></Panel>}

        {tab === "reports" && <Panel title="Готовые материалы"><div className="cards">{reports.length ? reports.map((item) => { const hasPreview = item.artifacts?.some((artifact) => artifact.format === "html"); return <article className="report-card" key={item.id}><p>REPORT / {new Date(item.created_at).toLocaleDateString("ru-RU")}</p><h3>{item.title}</h3>{item.summary && <span className="report-summary">{item.summary}</span>}<Status value={item.status} /><div className="report-actions"><button disabled={!hasPreview} onClick={() => setPreviewReport(item)}>Предпросмотр</button><span>Скачать:</span>{item.artifacts?.filter((artifact) => artifact.format !== "html").map((artifact) => <a key={artifact.id} href={`/api/artifacts/${artifact.id}/download`}>{artifact.format.toUpperCase()}</a>)}</div></article>; }) : <Empty text="Отчеты создаются из чата или выбранных документов." />}</div>{previewReport && <ReportPreview report={previewReport} onClose={() => setPreviewReport(undefined)} />}</Panel>}

        {tab === "watchlist" && <Panel title="Банки под наблюдением"><BankSearch onAdded={refresh} /><div className="table">{watchlist.length ? watchlist.map((item) => <div className="row" key={item.cbr_reg_number}><div className="file-icon">{item.bank_name.slice(0, 2)}</div><div><b>{item.bank_name}</b><small>Рег. № {item.cbr_reg_number}</small></div><Status value={item.enabled ? "active" : "paused"} /></div>) : <Empty text="Найдите банк и включите наблюдение — поиск в чате работает и без подписки." />}</div></Panel>}

        {tab === "settings" && <Panel title="Настройки запуска"><div className="settings-grid"><Setting title={systemStatus?.model_provider ?? "Провайдер моделей"} state={systemStatus?.model_configured ? "Настроен" : systemStatus?.model_key_present ? "Проверьте ключ" : "Не настроен"} stateOk={systemStatus?.model_configured} text={systemStatus?.model_error || `Основной агент — ${systemStatus?.orchestrator_model ?? "DeepSeek V4.1 Flash"}, финансовый — ${systemStatus?.finance_model ?? "Ling 3.0 Flash Fin"}. Ключ и адрес API читаются из корневого .env.`} /><Setting title="Telegram" text="Укажите TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID для дайджестов и срочных уведомлений." /><Setting title="Хранилище" text="Оригиналы и версии сохраняются в локальном Docker volume до ручного удаления." /><Setting title="Безопасность" text="Только публичный read-only веб, без входа, CAPTCHA, платежей и отправки форм." /></div></Panel>}
      </section>
    </main>
  );
}

function Panel({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) { return <section className="panel"><div className="panel-head"><h2>{title}</h2>{action}</div>{children}</section>; }
function Empty({ text }: { text: string }) { return <div className="empty"><span>∅</span><p>{text}</p></div>; }
function Setting({ title, text, state, stateOk }: { title: string; text: string; state?: string; stateOk?: boolean }) { return <article className="setting"><div className="setting-title"><p>{title}</p>{state && <span className={stateOk ? "config-ok" : "config-bad"}>{state}</span>}</div><span>{text}</span></article>; }

function ReportPreview({ report, onClose }: { report: ReportItem; onClose: () => void }) {
  return <div className="preview-backdrop" role="dialog" aria-modal="true" aria-label={`Предпросмотр: ${report.title}`} onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="preview-window"><div className="preview-toolbar"><div><span>Предпросмотр отчета</span><b>{report.title}</b></div><div><a href={`/api/reports/${report.id}/preview`} target="_blank" rel="noreferrer">Открыть отдельно ↗</a><button onClick={onClose} aria-label="Закрыть предпросмотр">Закрыть</button></div></div><iframe src={`/api/reports/${report.id}/preview`} title={`Отчет ${report.title}`} sandbox="allow-popups allow-popups-to-escape-sandbox" /></section>
  </div>;
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
