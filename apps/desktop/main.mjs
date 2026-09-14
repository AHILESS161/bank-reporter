import { app, BrowserWindow, dialog, shell } from "electron";
import { spawn } from "node:child_process";
import { createWriteStream, mkdirSync, readFileSync } from "node:fs";
import path from "node:path";

const API_PORT = 53111;
const BROWSER_PORT = 53112;
const WEB_PORT = 53113;
const children = [];
let mainWindow;

function resource(...parts) {
  return path.join(process.resourcesPath, "runtime", ...parts);
}

function startProcess(name, command, args, options, logDir) {
  const logPath = path.join(logDir, `${name}.log`);
  const log = createWriteStream(logPath, { flags: "w" });
  const child = spawn(command, args, { ...options, stdio: ["ignore", "pipe", "pipe"] });
  child.stdout.pipe(log);
  child.stderr.pipe(log);
  child.serviceName = name;
  child.logPath = logPath;
  child.startupError = null;
  child.recentOutput = "";
  const remember = (chunk) => {
    child.recentOutput = `${child.recentOutput}${chunk}`.slice(-12000);
  };
  child.stdout.on("data", remember);
  child.stderr.on("data", remember);
  child.on("error", (error) => {
    child.startupError = error;
    log.write(`\n${error.stack || error}\n`);
  });
  children.push(child);
  return child;
}

function logTail(logPath, maxLines = 35) {
  try {
    return readFileSync(logPath, "utf8").split(/\r?\n/).slice(-maxLines).join("\n").trim();
  } catch {
    return "Журнал процесса пока пуст.";
  }
}

function processDetails(child) {
  return child.recentOutput.trim() || logTail(child.logPath);
}

async function waitFor(url, child, timeoutMs = 120000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (child.startupError) {
      throw new Error(`${child.serviceName}: ${child.startupError.message}\n\n${processDetails(child)}`);
    }
    if (child.exitCode !== null) {
      throw new Error(
        `${child.serviceName}: процесс завершился с кодом ${child.exitCode}\n\n${processDetails(child)}`,
      );
    }
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 600));
  }
  throw new Error(
    `${child.serviceName}: сервис не запустился за ${Math.round(timeoutMs / 1000)} секунд\n\n`
      + processDetails(child),
  );
}

function apiExecutable() {
  const name = process.platform === "win32" ? "bank-reporter-api.exe" : "bank-reporter-api";
  return resource("api", "bank-reporter-api", name);
}

async function startApplication() {
  const userData = app.getPath("userData");
  const dataDir = path.join(userData, "data");
  const logDir = path.join(userData, "logs");
  mkdirSync(dataDir, { recursive: true });
  mkdirSync(logDir, { recursive: true });

  const common = { ...process.env, DATA_DIR: dataDir, LOG_LEVEL: "info" };
  const browser = startProcess(
    "browser",
    process.execPath,
    [resource("browser", "server.mjs")],
    {
      cwd: resource("browser"),
      env: {
        ...common,
        ELECTRON_RUN_AS_NODE: "1",
        AGENT_BROWSER_NODE_PATH: process.execPath,
        AGENT_BROWSER_NO_WEBMCP: "1",
        AGENT_BROWSER_CONTENT_BOUNDARIES: "1",
        PLAYWRIGHT_BROWSERS_PATH: resource("browsers"),
        HOST: "127.0.0.1",
        PORT: String(BROWSER_PORT),
      },
    },
    logDir,
  );
  await waitFor(`http://127.0.0.1:${BROWSER_PORT}/health`, browser);

  const api = startProcess(
    "api",
    apiExecutable(),
    [],
    {
      cwd: dataDir,
      env: {
        ...common,
        ENVIRONMENT: "desktop",
        TASK_BACKEND: "local",
        HOST: "127.0.0.1",
        PORT: String(API_PORT),
        DATABASE_URL: `sqlite:///${path.join(dataDir, "bank-reporter.sqlite3")}`,
        BROWSER_SERVICE_URL: `http://127.0.0.1:${BROWSER_PORT}`,
        LIEFLAT_DIR: resource("lieflat-charts"),
        WEB_ORIGIN: `http://127.0.0.1:${WEB_PORT}`,
      },
    },
    logDir,
  );
  await waitFor(`http://127.0.0.1:${API_PORT}/health`, api);

  const web = startProcess(
    "web",
    process.execPath,
    [resource("web", "server.js")],
    {
      cwd: resource("web"),
      env: {
        ...common,
        ELECTRON_RUN_AS_NODE: "1",
        NODE_ENV: "production",
        NODE_PATH: resource("web", "modules"),
        HOSTNAME: "127.0.0.1",
        PORT: String(WEB_PORT),
      },
    },
    logDir,
  );
  await waitFor(`http://127.0.0.1:${WEB_PORT}`, web);

  mainWindow = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 1040,
    minHeight: 720,
    title: "Bank Reporter",
    backgroundColor: "#f1f0ea",
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://") || url.startsWith("http://")) void shell.openExternal(url);
    return { action: "deny" };
  });
  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith(`http://127.0.0.1:${WEB_PORT}`)) {
      event.preventDefault();
      if (url.startsWith("https://") || url.startsWith("http://")) void shell.openExternal(url);
    }
  });
  await mainWindow.loadURL(`http://127.0.0.1:${WEB_PORT}`);
}

function stopChildren() {
  for (const child of children.splice(0)) {
    if (child.exitCode === null) child.kill("SIGTERM");
  }
}

const hasSingleInstanceLock = app.requestSingleInstanceLock();
if (!hasSingleInstanceLock) app.quit();

app.on("second-instance", () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});

app.whenReady().then(async () => {
  if (!hasSingleInstanceLock) return;
  try {
    await startApplication();
  } catch (error) {
    await dialog.showMessageBox({
      type: "error",
      title: "Bank Reporter не запустился",
      message: "Не удалось запустить локальные сервисы",
      detail: `${error}\n\nДиагностика сохранена в ${path.join(app.getPath("userData"), "logs")}`,
    });
    app.quit();
  }
});

app.on("before-quit", stopChildren);
app.on("window-all-closed", () => app.quit());
