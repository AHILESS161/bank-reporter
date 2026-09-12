"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type Tab = "chat" | "calendar" | "library" | "reports" | "watchlist" | "settings";
type Message = { id: string; role: "user" | "assistant"; content: string; created_at?: string };
type RunEvent = { type: string; payload: Record<string, unknown> };
type CalendarEvent = { id: string; title: string; starts_at: string; status: string; event_type: string; bank_name?: string };
type DocumentItem = { id: string; title: string; document_type: string; status: string; created_at: string; source_url?: string };
type ReportItem = { id: string; title: string; status: string; created_at: string; artifacts?: { id: string; format: string }[] };
type WatchItem = { cbr_reg_number: string; bank_name: string; enabled: boolean };

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
  const [watchlist, setWatchlist] = useState<WatchItem[]>([]);

  const refresh = useCallback(async () => {
    try {
      const [c, d, r, w] = await Promise.all([
        api<CalendarEvent[]>("/api/calendar"),
        api<DocumentItem[]>("/api/documents"),
        api<ReportItem[]>("/api/reports"),
        api<WatchItem[]>("/api/watchlist"),
      ]);
      setCalendar(c); setDocuments(d); setReports(r); setWatchlist(w);
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

        {tab === "calendar" && <Panel title="Предстоящие события" action={<a href="/api/calendar.ics">Экспортировать ICS</a>}><div className="table">{calendar.length ? calendar.map((item) => <div className="row" key={item.id}><time>{new Date(item.starts_at).toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</time><div><b>{item.title}</b><small>{item.bank_name ?? item.event_type}</small></div><Status value={item.status} /></div>) : <Empty text="События появятся после синхронизации ЦБ или подписки на банк." />}</div></Panel>}

        {tab === "library" && <Panel title="Оригиналы и извлеченные данные"><Upload onDone={refresh} /><div className="table">{documents.length ? documents.map((item) => <div className="row" key={item.id}><div className="file-icon">{item.document_type.slice(0, 3).toUpperCase()}</div><div><b>{item.title}</b><small>{new Date(item.created_at).toLocaleString("ru-RU")}</small></div><Status value={item.status} /><a href={`/api/documents/${item.id}/download`}>Скачать</a></div>) : <Empty text="Загрузите PDF/XLSX/CSV или попросите агента найти отчет." />}</div></Panel>}

        {tab === "reports" && <Panel title="Готовые материалы"><div className="cards">{reports.length ? reports.map((item) => <article className="report-card" key={item.id}><p>REPORT / {new Date(item.created_at).toLocaleDateString("ru-RU")}</p><h3>{item.title}</h3><Status value={item.status} /><div>{item.artifacts?.map((a) => <a key={a.id} href={`/api/artifacts/${a.id}/download`}>{a.format.toUpperCase()}</a>)}</div></article>) : <Empty text="Отчеты создаются из чата или выбранных документов." />}</div></Panel>}

        {tab === "watchlist" && <Panel title="Банки под наблюдением"><BankSearch onAdded={refresh} /><div className="table">{watchlist.length ? watchlist.map((item) => <div className="row" key={item.cbr_reg_number}><div className="file-icon">{item.bank_name.slice(0, 2)}</div><div><b>{item.bank_name}</b><small>Рег. № {item.cbr_reg_number}</small></div><Status value={item.enabled ? "active" : "paused"} /></div>) : <Empty text="Найдите банк и включите наблюдение — поиск в чате работает и без подписки." />}</div></Panel>}

        {tab === "settings" && <Panel title="Настройки запуска"><div className="settings-grid"><Setting title="OpenRouter" text="Ключ задается через OPENROUTER_API_KEY. Основной агент — DeepSeek V4.1 Flash, финансовый — Ling 3.0 Flash Fin." /><Setting title="Telegram" text="Укажите TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID для дайджестов и срочных уведомлений." /><Setting title="Хранилище" text="Оригиналы и версии сохраняются в локальном Docker volume до ручного удаления." /><Setting title="Безопасность" text="Только публичный read-only веб, без входа, CAPTCHA, платежей и отправки форм." /></div></Panel>}
      </section>
    </main>
  );
}

function Panel({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) { return <section className="panel"><div className="panel-head"><h2>{title}</h2>{action}</div>{children}</section>; }
function Empty({ text }: { text: string }) { return <div className="empty"><span>∅</span><p>{text}</p></div>; }
function Setting({ title, text }: { title: string; text: string }) { return <article className="setting"><p>{title}</p><span>{text}</span></article>; }

function Upload({ onDone }: { onDone: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  return <label className="upload"><input type="file" accept=".pdf,.xlsx,.csv" disabled={busy} onChange={async (e) => { const file = e.target.files?.[0]; if (!file) return; setBusy(true); const body = new FormData(); body.append("file", file); try { await api("/api/documents/upload", { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body }); await onDone(); } finally { setBusy(false); e.target.value = ""; } }} />{busy ? "Обрабатываем файл…" : "+ Загрузить PDF, XLSX или CSV"}</label>;
}

function BankSearch({ onAdded }: { onAdded: () => Promise<void> }) {
  const [query, setQuery] = useState(""); const [found, setFound] = useState<{ cbr_reg_number: string; name: string }[]>([]);
  return <div className="bank-search"><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Название банка" /><button onClick={async () => setFound(await api(`/api/banks/search?q=${encodeURIComponent(query)}`))}>Найти</button>{found.map((bank) => <button className="bank-result" key={bank.cbr_reg_number} onClick={async () => { await api(`/api/watchlist/${bank.cbr_reg_number}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ bank_name: bank.name }) }); setFound([]); await onAdded(); }}>+ {bank.name}</button>)}</div>;
}
