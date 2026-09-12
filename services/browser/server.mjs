import http from "node:http";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { stat } from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import dns from "node:dns/promises";
import net from "node:net";

const exec = promisify(execFile);
const port = Number(process.env.PORT ?? 8787);
const dataDir = path.resolve(process.env.DATA_DIR ?? "/data");
const binary = path.resolve("node_modules/.bin/agent-browser");

function json(res, status, value) {
  res.writeHead(status, { "content-type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(value));
}

async function body(req) {
  let raw = "";
  for await (const chunk of req) {
    raw += chunk;
    if (raw.length > 1_000_000) throw new Error("body_too_large");
  }
  return raw ? JSON.parse(raw) : {};
}

function safeDataPath(candidate) {
  const resolved = path.resolve(candidate);
  if (resolved !== dataDir && !resolved.startsWith(`${dataDir}${path.sep}`)) throw new Error("unsafe_path");
  return resolved;
}

function privateIp(value) {
  if (net.isIPv4(value)) {
    const parts = value.split(".").map(Number);
    return parts[0] === 10 || parts[0] === 127 || parts[0] === 0 ||
      (parts[0] === 169 && parts[1] === 254) || (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) ||
      (parts[0] === 192 && parts[1] === 168) || parts[0] >= 224;
  }
  if (net.isIPv6(value)) {
    const ip = value.toLowerCase();
    return ip === "::1" || ip === "::" || ip.startsWith("fe8") || ip.startsWith("fe9") ||
      ip.startsWith("fea") || ip.startsWith("feb") || ip.startsWith("fc") || ip.startsWith("fd");
  }
  return true;
}

async function publicUrl(value) {
  const parsed = new URL(value);
  if (!["http:", "https:"].includes(parsed.protocol)) throw new Error("unsupported_protocol");
  if (["localhost", "127.0.0.1", "::1"].includes(parsed.hostname)) throw new Error("local_url_denied");
  const addresses = await dns.lookup(parsed.hostname, { all: true });
  if (!addresses.length || addresses.some(({ address }) => privateIp(address))) throw new Error("private_dns_denied");
  return parsed;
}

async function run(args, timeout = 120_000) {
  const { stdout, stderr } = await exec(binary, args, { timeout, maxBuffer: 2_000_000, env: process.env });
  return { stdout, stderr };
}

async function readPage(payload) {
  const url = await publicUrl(payload.url);
  const session = `br-${crypto.randomUUID()}`;
  const allowed = [url.hostname, ...(payload.allowed_domains ?? [])].join(",");
  try {
    const result = await run([
      "--namespace", session, "--json", "--content-boundaries", "--max-output", "100000",
      "--allowed-domains", allowed, "--action-policy", path.resolve("action-policy.json"), "read", url.href,
    ]);
    return { url: url.href, content: result.stdout, diagnostics: result.stderr };
  } finally {
    await run(["--namespace", session, "--action-policy", path.resolve("action-policy.json"), "close"], 15_000).catch(() => undefined);
  }
}

async function search(payload) {
  const query = String(payload.query ?? "").slice(0, 500);
  const engine = payload.engine === "bing" ? "bing" : "yandex";
  const url = engine === "yandex"
    ? `https://yandex.ru/search/?text=${encodeURIComponent(query)}`
    // RSS contains exact result URLs as inert XML. The browser remains locked
    // to bing.com and never navigates to a result while collecting the list.
    : `https://www.bing.com/news/search?format=rss&q=${encodeURIComponent(query)}&setlang=ru-ru&cc=RU&mkt=ru-RU`;
  return { engine, ...(await readPage({
    url,
    allowed_domains: engine === "yandex" ? ["yandex.ru", "yandex.com"] : ["bing.com"],
  })) };
}

async function render(payload) {
  const html = safeDataPath(payload.html_path);
  const pdf = payload.pdf_path ? safeDataPath(payload.pdf_path) : null;
  const png = payload.png_path ? safeDataPath(payload.png_path) : null;
  await stat(html);
  const session = `render-${crypto.randomUUID()}`;
  const localArgs = [
    "--namespace", session, "--action-policy", path.resolve("action-policy.json"), "--allow-file-access",
  ];
  try {
    await run([...localArgs, "open", `file://${html}`]);
    await run([...localArgs, "wait", "1000"]);
    if (pdf) await run([...localArgs, "pdf", pdf]);
    if (png) await run([...localArgs, "screenshot", "--full", png]);
    return { pdf, png };
  } finally {
    await run([...localArgs, "close"], 15_000).catch(() => undefined);
  }
}

const server = http.createServer(async (req, res) => {
  try {
    if (req.method === "GET" && req.url === "/health") return json(res, 200, { status: "ok" });
    if (req.method !== "POST") return json(res, 404, { error: "not_found" });
    const payload = await body(req);
    if (req.url === "/read") return json(res, 200, await readPage(payload));
    if (req.url === "/search") return json(res, 200, await search(payload));
    if (req.url === "/render") return json(res, 200, await render(payload));
    return json(res, 404, { error: "not_found" });
  } catch (error) {
    return json(res, 400, { error: error instanceof Error ? error.message : String(error) });
  }
});

server.listen(port, "0.0.0.0", () => process.stdout.write(`browser-service:${port}\n`));
