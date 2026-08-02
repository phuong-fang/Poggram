let folders = [];
let files = [];
let currentFolderId = null;

window.currentFolderId = null;
let trashLoaded = false;
let settingsLoaded = false;

let externalVideoPlayerEnabled = false;

let maxParallelTransfers = 3;
let searchQuery = "";

let currentSmartView = null;

let smartSearchQuery = "";

let trashSearchQuery = "";

let transfersSearchQuery = "";

let transfersSubTab = "uploading";

let transfersSearchAllTabs = false;

let currentTrashFolderId = null;

let lastSmartContextKey = null;

let expandedFolderIds = new Set();

let selectedFolderIds = new Set();
let selectedFileIds = new Set();

let lastClickedIndex = null;

let trashSelectedFolderIds = new Set();
let trashSelectedFileIds = new Set();
let trashLastClickedIndex = null;

let smartSelectedFileIds = new Set();
let smartLastClickedIndex = null;

let dragPayload = null;

let versionUploadTargetId = null;

const views = document.querySelectorAll(".view");
const treeEl = document.getElementById("tree");
const gridEl = document.getElementById("grid");
const breadcrumbEl = document.getElementById("breadcrumb");
const countEl = document.getElementById("item-count");
const railCountEl = document.getElementById("rail-item-count");

const _SIZE_IN_TEXT = /·\s*([\d.]+)\s*(B|KB|MB|GB|TB)/;

function compactCountText(text) {
  if (!text) return "";

  const parts = text.split(" — ");
  const base = parts[0];
  const tail = parts.slice(1).join(" — ");
  const totalCount = (base.match(/^(\d+)/) || [])[1];
  if (totalCount === undefined) return text;

  const totalSize = base.match(_SIZE_IN_TEXT);
  const selCount = (tail.match(/(\d+)\s+selected/) || [])[1];
  const selSize = tail.match(_SIZE_IN_TEXT);

  const counts = selCount === undefined ? totalCount : `${selCount}/${totalCount}`;
  if (!totalSize) return counts;
  const [, totalValue, totalUnit] = totalSize;
  let sizes = `${totalValue}${totalUnit}`;
  if (selSize) {
    const [, selValue, selUnit] = selSize;

    sizes = selUnit === totalUnit ? `${selValue}/${totalValue}${totalUnit}` : `${selValue}${selUnit}/${totalValue}${totalUnit}`;
  }
  return `${counts} · ${sizes}`;
}

let _railCountFullText = "";

function renderRailCount() {
  const collapsed = railCountEl.closest(".rail")?.classList.contains("icon-only");
  railCountEl.textContent = collapsed ? compactCountText(_railCountFullText) : _railCountFullText;
  railCountEl.title = _railCountFullText;
}

function setItemCount(text) {
  countEl.textContent = text;
  mirrorRailCount(text);
}
function mirrorRailCount(text) {
  _railCountFullText = text;
  renderRailCount();
}

function appendSelectionSummary(baseText, selectedFolderIds, selectedFileIds, filesList, folderList = folders) {
  const totalSelected = selectedFolderIds.size + selectedFileIds.size;
  if (totalSelected === 0) return baseText;
  const countedFileIds = new Set();
  let selectedSize = 0;
  for (const f of filesList) {
    if (selectedFileIds.has(f.id) && !countedFileIds.has(f.id)) {
      countedFileIds.add(f.id);
      selectedSize += f.size_bytes || 0;
    }
  }
  for (const folderId of selectedFolderIds) {
    const scopeIds = new Set([folderId, ...collectDescendantIds(folderId, folderList)]);
    for (const f of filesList) {
      if (scopeIds.has(f.folder_id) && !countedFileIds.has(f.id)) {
        countedFileIds.add(f.id);
        selectedSize += f.size_bytes || 0;
      }
    }
  }
  return `${baseText} — ${totalSelected} selected${countedFileIds.size ? ` · ${formatBytes(selectedSize)}` : ""}`;
}
const trashListEl = document.getElementById("trash-list");
const trashCountEl = document.getElementById("trash-count");
const trashBreadcrumbEl = document.getElementById("trash-breadcrumb");
const contextMenuEl = document.getElementById("context-menu");
const versionPanelEl = document.getElementById("version-panel");
const syncCreatePanelEl = document.getElementById("sync-create-panel");
const movePanelEl = document.getElementById("move-panel");
const backupPanelEl = document.getElementById("backup-panel");
const propertiesPanelEl = document.getElementById("properties-panel");
const imageViewerEl = document.getElementById("image-viewer");
const imageViewerImgEl = document.getElementById("image-viewer-img");
const imageViewerFilenameEl = document.getElementById("image-viewer-filename");
const imageViewerZoomEl = document.getElementById("image-viewer-zoom");
const imageViewerStageEl = document.getElementById("image-viewer-stage");
const imageViewerLoadingEl = document.getElementById("image-viewer-loading");
const imageViewerErrorEl = document.getElementById("image-viewer-error");
const imageViewerPrevBtnEl = document.getElementById("image-viewer-prev-btn");
const imageViewerNextBtnEl = document.getElementById("image-viewer-next-btn");
const imageViewerCloseBtnEl = document.getElementById("image-viewer-close-btn");
const videoViewerEl = document.getElementById("video-viewer");
const videoViewerVideoEl = document.getElementById("video-viewer-video");
const videoViewerFilenameEl = document.getElementById("video-viewer-filename");
const videoViewerStageEl = document.getElementById("video-viewer-stage");
const videoViewerErrorEl = document.getElementById("video-viewer-error");
const videoViewerPrevBtnEl = document.getElementById("video-viewer-prev-btn");
const videoViewerNextBtnEl = document.getElementById("video-viewer-next-btn");
const videoViewerCloseBtnEl = document.getElementById("video-viewer-close-btn");
const videoViewerExternalBtnEl = document.getElementById("video-viewer-external-btn");
const videoViewerSkipBackBtnEl = document.getElementById("video-viewer-skip-back-btn");
const videoViewerSkipFwdBtnEl = document.getElementById("video-viewer-skip-fwd-btn");
const videoViewerSetThumbBtnEl = document.getElementById("video-viewer-set-thumb-btn");
const videoViewerSpeedSelectEl = document.getElementById("video-viewer-speed-select");
const audioViewerEl = document.getElementById("audio-viewer");
const audioViewerAudioEl = document.getElementById("audio-viewer-audio");
const audioViewerFilenameEl = document.getElementById("audio-viewer-filename");
const audioViewerStageEl = document.getElementById("audio-viewer-stage");
const audioViewerErrorEl = document.getElementById("audio-viewer-error");
const audioViewerPrevBtnEl = document.getElementById("audio-viewer-prev-btn");
const audioViewerNextBtnEl = document.getElementById("audio-viewer-next-btn");
const audioViewerCloseBtnEl = document.getElementById("audio-viewer-close-btn");
const audioViewerExternalBtnEl = document.getElementById("audio-viewer-external-btn");
const audioViewerSkipBackBtnEl = document.getElementById("audio-viewer-skip-back-btn");
const audioViewerSkipFwdBtnEl = document.getElementById("audio-viewer-skip-fwd-btn");
const audioViewerSpeedSelectEl = document.getElementById("audio-viewer-speed-select");
const fileInputEl = document.getElementById("file-input");
const versionFileInputEl = document.getElementById("version-file-input");
const uploadListEl = document.getElementById("upload-list");
const transfersBadgeEl = document.getElementById("transfers-badge");
const transfersEmptyHintEl = document.getElementById("transfers-empty-hint");
const pauseAllBtnEl = document.getElementById("pause-all-btn");
const continueAllBtnEl = document.getElementById("continue-all-btn");
const clearFinishedBtnEl = document.getElementById("clear-finished-btn");
const clearDuplicatesBtnEl = document.getElementById("clear-duplicates-btn");
const dismissAllBtnEl = document.getElementById("dismiss-all-btn");
const transfersSearchInputEl = document.getElementById("transfers-search-input");
const transfersSearchAllToggleEl = document.getElementById("transfers-search-all-toggle");
const searchInputEl = document.getElementById("search-input");
const smartSearchInputEl = document.getElementById("smart-search-input");
const trashSearchInputEl = document.getElementById("trash-search-input");
const railFootEl = document.querySelector(".rail-foot");
const railStorageEl = document.getElementById("rail-storage");
const railEl = document.querySelector(".rail");
const smartTitleEl = document.getElementById("smart-title");
const smartLedeEl = document.getElementById("smart-lede");
const smartCountEl = document.getElementById("smart-count");
const smartGridEl = document.getElementById("smart-grid");
const settingsConnectedEl = document.getElementById("settings-connected");
const SETTINGS_STEPS = ["connect", "code", "password", "archive"];
const SETTINGS_TABS = ["account", "backup", "storage", "preferences", "shortcuts"];
const MIME_ICONS = [
  [/^image\//, "image"],
  [/^video\//, "video"],
  [/^audio\//, "music"],
  [/^text\//, "file-text"],
  [/pdf/, "file-text"],
  [/zip|rar|7z|compressed/, "file-archive"],
  [/spreadsheet|excel/, "table"],
];

const RESULT_RENDER_CAP = 500;

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : String(str);
  return div.innerHTML;
}

async function apiFetch(url, options = {}) {
  const resp = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.error || `Server returned ${resp.status}`);
  return data;
}

function foldersByParent(parentId) {
  return folders
    .filter((f) => f.parent_id === parentId)
    .sort((a, b) => a.name.localeCompare(b.name));
}

function findFolder(id) {
  return folders.find((f) => f.id === id) || null;
}

function collectDescendantIds(id, folderList = folders) {
  const ids = [];
  const frontier = [id];
  while (frontier.length) {
    const current = frontier.pop();
    folderList.filter((f) => f.parent_id === current).forEach((f) => {
      ids.push(f.id);
      frontier.push(f.id);
    });
  }
  return ids;
}

function folderPath(folderId) {
  const path = [];
  let current = folderId ? findFolder(folderId) : null;
  while (current) {
    path.unshift(current);
    current = current.parent_id ? findFolder(current.parent_id) : null;
  }
  return path;
}

function filesByFolder(folderId) {
  return files.filter((f) => f.folder_id === folderId).sort((a, b) => a.name.localeCompare(b.name));
}

function findFile(id) {
  return files.find((f) => f.id === id) || null;
}

function iconForMime(mime) {
  if (!mime) return "file";
  const hit = MIME_ICONS.find(([pattern]) => pattern.test(mime));
  return hit ? hit[1] : "file";
}

const knownThumbnailIds = new Set();

function fileThumbHtml(f, iconClass = "") {
  const classAttr = iconClass ? ` class="${iconClass}"` : "";

  return `<img src="/api/files/${f.id}/thumbnail" alt="" class="card-thumb" loading="lazy" draggable="false" onload="this.closest('.card').classList.add('has-thumb'); knownThumbnailIds.add('${f.id}');" onerror="this.style.display='none'; this.nextElementSibling.style.display=''; knownThumbnailIds.delete('${f.id}'); this.closest('.card').classList.remove('has-thumb');"><i data-lucide="${iconForMime(f.mime_type)}"${classAttr} style="display:none"></i>`;
}

function debounce(fn, delayMs) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delayMs);
  };
}

function capHintSuffix(totalCount, noun) {
  if (totalCount <= RESULT_RENDER_CAP) return "";
  return ` Showing the first ${RESULT_RENDER_CAP.toLocaleString()} of ${totalCount.toLocaleString()} ${noun} - narrow your search to see more.`;
}

function formatBytes(bytes) {
  if (bytes == null) return "";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i++;
  }
  return `${value.toFixed(i > 0 && value < 10 ? 1 : 0)} ${units[i]}`;
}

function totalSizeSuffix(fileList) {
  if (fileList.length === 0) return "";
  const totalBytes = fileList.reduce((sum, f) => sum + (f.size_bytes || 0), 0);
  return ` · ${formatBytes(totalBytes)}`;
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "";
  const total = Math.round(seconds);
  if (total < 60) return `${total}s`;
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  if (minutes < 60) return `${minutes}m ${secs}s`;
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return `${hours}h ${mins}m`;
}

function formatSpeedAndEta(bytesDoneThisAttempt, bytesTotal, bytesDoneAtAttemptStart, startTime, prevBytesDone, prevTime) {
  const now = Date.now();
  const elapsedSeconds = (now - startTime) / 1000;
  const bytesThisAttempt = bytesDoneThisAttempt - bytesDoneAtAttemptStart;
  if (elapsedSeconds < 1 || bytesThisAttempt <= 0) return "";

  let bytesPerSecond = 0;
  if (prevBytesDone != null && prevTime != null) {
    const deltaSeconds = (now - prevTime) / 1000;
    const deltaBytes = bytesDoneThisAttempt - prevBytesDone;
    if (deltaSeconds > 0 && deltaBytes > 0) {
      bytesPerSecond = deltaBytes / deltaSeconds;
    }
  }

  if (!(bytesPerSecond > 0)) {
    bytesPerSecond = bytesThisAttempt / elapsedSeconds;
  }

  if (!(bytesPerSecond > 0)) return "";
  if (bytesTotal == null) return `${formatBytes(bytesPerSecond)}/s`;
  const etaSeconds = (bytesTotal - bytesDoneThisAttempt) / bytesPerSecond;
  const etaText = formatDuration(etaSeconds);
  return etaText ? `${formatBytes(bytesPerSecond)}/s · ${etaText} left` : `${formatBytes(bytesPerSecond)}/s`;
}

function formatDate(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString);
  if (isNaN(d.getTime())) return "";
  return `${d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}, ${d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`;
}

function folderDisplayPath(folderId) {
  const path = folderPath(folderId);
  return path.length ? path.map((f) => f.name).join(" / ") : "Root";
}

let treeMaxVisibleDepth = 0;

function renderTree() {
  const homeActive = currentFolderId === null ? " active" : "";
  treeMaxVisibleDepth = 0;
  treeEl.innerHTML = `
    <div class="tree-item tree-home${homeActive}" style="--tree-depth:0">
      <span class="tree-chevron-spacer"></span><i data-lucide="home"></i><span>Root</span>
    </div>
    ${renderTreeLevel(null, 1)}
  `;
  lucide.createIcons();

  if (sidebarCollapsed) applySidebarWidth(sidebarCollapsedWidth());
}

const ICON_TREE_STEP = 14;

function _treeGuideHtml(depth, isLast, ancestorHasNext) {
  const trunkX = (d) => 12 + ICON_TREE_STEP * (d - 1);
  const guides = [];

  for (let a = 1; a < depth; a++) {
    if (ancestorHasNext[a - 1]) {
      guides.push(`<span class="tree-guide tree-guide-v" style="left:${trunkX(a)}px"></span>`);
    }
  }

  guides.push(
    `<span class="tree-guide ${isLast ? "tree-guide-half" : "tree-guide-v"}" style="left:${trunkX(depth)}px"></span>`
  );

  guides.push(
    `<span class="tree-guide tree-guide-h" style="left:${trunkX(depth)}px;width:${ICON_TREE_STEP - 8}px"></span>`
  );
  return guides.join("");
}

function renderTreeLevel(parentId, depth, ancestorHasNext = []) {
  const siblings = foldersByParent(parentId);
  return siblings
    .map((f, i) => {
      if (depth > treeMaxVisibleDepth) treeMaxVisibleDepth = depth;
      const active = f.id === currentFolderId ? " active" : "";
      const selected = selectedFolderIds.has(f.id) ? " selected" : "";
      const hasChildren = foldersByParent(f.id).length > 0;
      const expanded = expandedFolderIds.has(f.id);
      const isLast = i === siblings.length - 1;
      const chevron = hasChildren
        ? `<i class="tree-chevron${expanded ? " expanded" : ""}" data-lucide="chevron-right"></i>`
        : `<span class="tree-chevron-spacer"></span>`;
      return `
        <div class="tree-item${active}${selected}" data-id="${f.id}" draggable="true" style="--tree-depth:${depth}">
          ${_treeGuideHtml(depth, isLast, ancestorHasNext)}
          ${chevron}<i data-lucide="folder"></i><span>${escapeHtml(f.name)}</span>
        </div>
        ${hasChildren && expanded ? renderTreeLevel(f.id, depth + 1, [...ancestorHasNext, !isLast]) : ""}
      `;
    })
    .join("");
}

function toggleTreeExpand(id) {
  if (expandedFolderIds.has(id)) expandedFolderIds.delete(id);
  else expandedFolderIds.add(id);
  renderTree();
}

function toggleTreeExpandDeep(id) {
  const expand = !expandedFolderIds.has(id);
  const ids = [id, ...collectDescendantIds(id, folders)];
  for (const descendantId of ids) {
    if (expand) expandedFolderIds.add(descendantId);
    else expandedFolderIds.delete(descendantId);
  }
  renderTree();
}

function toggleTreeExpandAll() {
  if (expandedFolderIds.size) {
    expandedFolderIds.clear();
  } else {
    for (const f of folders) {
      if (f.deleted) continue;
      if (folders.some((child) => !child.deleted && child.parent_id === f.id)) expandedFolderIds.add(f.id);
    }
  }
  renderTree();
}

function renderBreadcrumb() {
  const path = folderPath(currentFolderId);
  const parts = [{ id: null, name: "Root" }, ...path];
  breadcrumbEl.innerHTML = parts
    .map((p, i) => {
      const last = i === parts.length - 1;
      const crumb = `<span class="crumb${last ? " current" : ""}" data-id="${p.id ?? ""}">${escapeHtml(p.name)}</span>`;
      return crumb + (last ? "" : `<i data-lucide="chevron-right"></i>`);
    })
    .join("");
  lucide.createIcons();
}

function fileCardHtml(f, { showFolderPath = false, draggable = true } = {}) {
  const selected = selectedFileIds.has(f.id);
  const sub = showFolderPath
    ? `<div class="card-sub" title="${escapeHtml(folderDisplayPath(f.folder_id))}">${formatBytes(f.size_bytes)} &middot; ${escapeHtml(folderDisplayPath(f.folder_id))}</div>`
    : `<div class="card-sub">${formatBytes(f.size_bytes)}</div>`;

  const hasThumbClass = knownThumbnailIds.has(f.id) ? " has-thumb" : "";

  return `
    <div class="card file-card${selected ? " selected" : ""}${hasThumbClass}" data-id="${f.id}"${draggable ? ' draggable="true"' : ""}>
      ${f.starred_at ? `<i data-lucide="star" class="card-star"></i>` : ""}

      ${fileThumbHtml(f)}
      <div class="card-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</div>

      ${sub}
      <div class="card-modified">${escapeHtml(formatDate(f.date_modified))}</div>

    </div>

  `;
}

function renderSearchResults() {
  const query = searchQuery.toLowerCase();
  const scopeIds = new Set([currentFolderId, ...collectDescendantIds(currentFolderId)]);
  let matches = files.filter((f) => scopeIds.has(f.folder_id) && f.name.toLowerCase().includes(query));
  matches = matches.sort(_sortColumn ? _sortComparator() : (a, b) => a.name.localeCompare(b.name));
  const scopeLabel = currentFolderId ? ` in ${findFolder(currentFolderId)?.name ?? "this folder"}` : "";
  _explorerBaseCountText =
    `${matches.length} match${matches.length === 1 ? "" : "es"} for "${searchQuery}"${scopeLabel}` +
    totalSizeSuffix(matches) +
    capHintSuffix(matches.length, "matches");
  setItemCount(appendSelectionSummary(_explorerBaseCountText, selectedFolderIds, selectedFileIds, files));
  knownThumbnailIds.clear();
  if (matches.length === 0) {
    gridEl.innerHTML = `<div class="empty-hint">No files match "${escapeHtml(searchQuery)}".</div>`;

    return;
  }

  const rendered = matches.length > RESULT_RENDER_CAP ? matches.slice(0, RESULT_RENDER_CAP) : matches;
  gridEl.innerHTML = rendered.map((f) => fileCardHtml(f, { showFolderPath: true })).join("");
  lucide.createIcons();
}

let lastGridContextKey = null;

function renderGrid() {
  const contextKey = `${currentFolderId}::${searchQuery}`;
  if (contextKey !== lastGridContextKey) {
    lastClickedIndex = null;
    lastGridContextKey = contextKey;
  }

  knownThumbnailIds.clear();
  if (searchQuery) {
    renderSearchResults();
    return;
  }
  const subfolders = foldersByParent(currentFolderId);
  const subfiles = filesByFolder(currentFolderId);

  refreshFolderSizes();
  const { folders: sortedFolders, files: sortedFiles } = _sortItems(subfolders, subfiles);
  const total = sortedFolders.length + sortedFiles.length;
  _explorerBaseCountText = `${total} item${total === 1 ? "" : "s"}` + totalSizeSuffix(sortedFiles);
  setItemCount(appendSelectionSummary(_explorerBaseCountText, selectedFolderIds, selectedFileIds, files));
  if (total === 0) {
    gridEl.innerHTML = `<div class="empty-hint">This folder is empty. Right-click to create a subfolder or upload a file.</div>`;
    return;
  }
  const folderCards = sortedFolders.map((f) => {
    const selected = selectedFolderIds.has(f.id);

    const size = folderSizeOf(f.id);
    return `
      <div class="card folder-card${selected ? " selected" : ""}" data-id="${f.id}" draggable="true">
        <i data-lucide="folder"></i>
        <div class="card-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</div>
        <div class="card-sub">${size ? escapeHtml(formatBytes(size)) : ""}</div>
        <div class="card-modified">${escapeHtml(formatDate(f.date_modified))}</div>
      </div>
    `;
  });
  const fileCards = sortedFiles.map((f) => fileCardHtml(f));
  gridEl.innerHTML = folderCards.concat(fileCards).join("");
  lucide.createIcons();
  _renderSortArrows();
}

function renderAll() {
  renderTree();
  renderBreadcrumb();
  renderGrid();
}

const _SORT_COLUMNS = ["name", "size", "modified", "opened", "starred", "added"];
const _SORT_DEFAULTS = {

  explorer: { col: "name", dir: 1 },

  recent: { col: "added", dir: -1 },

  history: { col: "opened", dir: -1 },
  starred: { col: "starred", dir: -1 },
};
const _SORT_STORAGE_KEY = "tvSortByView";

function _loadSortStates() {
  let stored = {};
  try {
    stored = JSON.parse(localStorage.getItem(_SORT_STORAGE_KEY) || "{}");
  } catch {
    stored = {};
  }
  const states = {};
  const explicit = new Set();
  for (const [ctx, fallback] of Object.entries(_SORT_DEFAULTS)) {
    const saved = stored[ctx];
    if (saved && _SORT_COLUMNS.includes(saved.col)) {
      states[ctx] = { col: saved.col, dir: saved.dir === -1 ? -1 : 1 };
      explicit.add(ctx);
    } else {
      states[ctx] = { ...fallback };
    }
  }
  return { states, explicit };
}

const { states: _sortStates, explicit: _sortExplicit } = _loadSortStates();

let _activeSortContext = "explorer";
let _sortColumn = _sortStates.explorer.col;
let _sortDir = _sortStates.explorer.dir;

function _applySortContext(ctx) {
  if (!_sortStates[ctx]) return;
  _activeSortContext = ctx;
  _sortColumn = _sortStates[ctx].col;
  _sortDir = _sortStates[ctx].dir;

  _syncSmartSortOptions();
  _renderSortArrows();
}

function _persistSort() {
  _sortStates[_activeSortContext] = { col: _sortColumn, dir: _sortDir };
  _sortExplicit.add(_activeSortContext);
  const toStore = {};
  for (const ctx of _sortExplicit) toStore[ctx] = _sortStates[ctx];
  try {
    localStorage.setItem(_SORT_STORAGE_KEY, JSON.stringify(toStore));
  } catch {

  }
}

const _SMART_EXTRA_SORT_OPTION = {
  history: { value: "opened", label: "Last opened" },
  starred: { value: "starred", label: "Date starred" },
  recent: { value: "added", label: "Date added" },
};

function _syncSmartSortOptions() {
  const select = document.getElementById("smart-sort-select");
  if (!select) return;
  const extra = _SMART_EXTRA_SORT_OPTION[_activeSortContext];
  for (const opt of Array.from(select.options)) {
    if (opt.dataset.extra === "1") select.removeChild(opt);
  }
  if (extra) {
    const opt = document.createElement("option");
    opt.value = extra.value;
    opt.textContent = extra.label;
    opt.dataset.extra = "1";
    select.insertBefore(opt, select.firstChild);
  }
}

let _folderSizes = new Map();

function refreshFolderSizes(filesList = files, folderList = folders) {
  const direct = new Map();
  for (const f of filesList) {
    const key = f.folder_id || null;
    direct.set(key, (direct.get(key) || 0) + (f.size_bytes || 0));
  }
  const childIds = new Map();
  for (const folder of folderList) {
    const parent = folder.parent_id || null;
    if (!childIds.has(parent)) childIds.set(parent, []);
    childIds.get(parent).push(folder.id);
  }
  const totals = new Map();
  const inProgress = new Set();
  function totalFor(id) {
    if (totals.has(id)) return totals.get(id);
    if (inProgress.has(id)) return 0;
    inProgress.add(id);
    let sum = direct.get(id) || 0;
    for (const child of childIds.get(id) || []) sum += totalFor(child);
    inProgress.delete(id);
    totals.set(id, sum);
    return sum;
  }
  for (const folder of folderList) totalFor(folder.id);
  _folderSizes = totals;
  return totals;
}

function folderSizeOf(folderId) {
  return _folderSizes.get(folderId) || 0;
}

function _sizeOf(item) {
  return item.size_bytes != null ? item.size_bytes : folderSizeOf(item.id);
}

function _sortComparator() {
  const dir = _sortDir;
  return (a, b) => {
    let va, vb;
    if (_sortColumn === "name") { va = a.name.toLowerCase(); vb = b.name.toLowerCase(); return va < vb ? -dir : va > vb ? dir : 0; }
    if (_sortColumn === "size") {
      va = _sizeOf(a); vb = _sizeOf(b);

      if (va === vb) return a.name.toLowerCase() < b.name.toLowerCase() ? -1 : a.name.toLowerCase() > b.name.toLowerCase() ? 1 : 0;
      return (va - vb) * dir;
    }
    if (_sortColumn === "modified") { va = a.date_modified || ""; vb = b.date_modified || ""; return va < vb ? -dir : va > vb ? dir : 0; }

    if (_sortColumn === "added") { va = a.date_uploaded || ""; vb = b.date_uploaded || ""; return va < vb ? -dir : va > vb ? dir : 0; }
    if (_sortColumn === "opened") { va = a.last_opened_at || ""; vb = b.last_opened_at || ""; return va < vb ? -dir : va > vb ? dir : 0; }
    if (_sortColumn === "starred") { va = a.starred_at || ""; vb = b.starred_at || ""; return va < vb ? -dir : va > vb ? dir : 0; }
    return 0;
  };
}

function _sortItems(subfolders, subfiles) {
  if (!_sortColumn) return { folders: subfolders, files: subfiles };
  const sortFn = _sortComparator();
  return { folders: [...subfolders].sort(sortFn), files: [...subfiles].sort(sortFn) };
}

function _rerenderSortableView() {
  if (currentSmartView) renderSmartView(currentSmartView);
  else renderGrid();
  _renderSortArrows();
}

function _setSortColumn(col) {
  if (_sortColumn === col) _sortDir *= -1;
  else { _sortColumn = col; _sortDir = 1; }
  _persistSort();
  _rerenderSortableView();
}

function _renderSortArrows() {
  ["grid-list-header", "smart-list-header"].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    const spans = el.querySelectorAll("span");
    [3, 4, 5].forEach((i) => {
      const span = spans[i - 1];
      if (!span) return;
      const col = i === 3 ? "name" : i === 4 ? "size" : "modified";
      const text = { 3: "Name", 4: "Size", 5: "Modified" }[i];
      span.textContent = _sortColumn === col ? text + (_sortDir === 1 ? " \u25B2" : " \u25BC") : text;
    });
  });
  ["grid-sort-select", "smart-sort-select"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.value = _sortColumn || "";
  });
  ["grid-sort-dir-btn", "smart-sort-dir-btn"].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.disabled = !_sortColumn;
    el.classList.toggle("desc", _sortDir === -1);
  });
}

function _initSortHeaders() {
  ["grid-list-header", "smart-list-header"].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.querySelectorAll("span").forEach((span, i) => {
      if (i === 2 || i === 3 || i === 4) {
        span.style.cursor = "pointer";
        span.addEventListener("click", () => _setSortColumn(i === 2 ? "name" : i === 3 ? "size" : "modified"));
      }
    });
  });
}

function _initGridSortControls() {
  [["grid-sort-select", "grid-sort-dir-btn"], ["smart-sort-select", "smart-sort-dir-btn"]].forEach(([selectId, btnId]) => {
    const select = document.getElementById(selectId);
    const btn = document.getElementById(btnId);
    if (select) {
      select.addEventListener("change", () => {
        _sortColumn = select.value;
        _sortDir = 1;
        _persistSort();
        _rerenderSortableView();
      });
    }
    if (btn) {
      btn.addEventListener("click", () => {
        if (!_sortColumn) return;
        _sortDir *= -1;
        _persistSort();
        _rerenderSortableView();
      });
    }
  });
}

const SMART_VIEWS = {
  recent: {
    title: "Recently added",
    lede: "Every file, newest upload first.",
    emptyHint: "Nothing uploaded yet.",
    filter: () => true,
    sort: (a, b) => b.date_uploaded.localeCompare(a.date_uploaded),
  },
  history: {
    title: "Watch history",
    lede: "Files you've opened, most recent first.",
    emptyHint: "Nothing opened yet - files you open show up here.",
    filter: (f) => !!f.last_opened_at,
    sort: (a, b) => b.last_opened_at.localeCompare(a.last_opened_at),
  },
  starred: {
    title: "Starred",
    lede: "Files you've starred, most recently starred first.",
    emptyHint: "Nothing starred yet - right-click a file and choose Star.",
    filter: (f) => !!f.starred_at,
    sort: (a, b) => b.starred_at.localeCompare(a.starred_at),
  },
};

function renderSmartView(kind) {
  const config = SMART_VIEWS[kind];

  const contextKey = `${kind}::${smartSearchQuery}::${_sortColumn || ""}::${_sortDir}`;
  if (contextKey !== lastSmartContextKey) {
    smartLastClickedIndex = null;
    lastSmartContextKey = contextKey;
  }

  let matches = files.filter(config.filter).sort(_sortColumn ? _sortComparator() : config.sort);
  if (smartSearchQuery) {
    const query = smartSearchQuery.toLowerCase();
    matches = matches.filter((f) => f.name.toLowerCase().includes(query));
  }
  smartTitleEl.textContent = config.title;
  smartLedeEl.textContent = config.lede;
  _smartBaseCountText =
    (smartSearchQuery
      ? `${matches.length} match${matches.length === 1 ? "" : "es"} for "${smartSearchQuery}"`
      : `${matches.length} item${matches.length === 1 ? "" : "s"}`) +
    totalSizeSuffix(matches) +
    capHintSuffix(matches.length, smartSearchQuery ? "matches" : "items");
  smartCountEl.textContent = appendSelectionSummary(_smartBaseCountText, new Set(), smartSelectedFileIds, files);
  mirrorRailCount(smartCountEl.textContent);

  knownThumbnailIds.clear();
  if (matches.length === 0) {
    const emptyMessage = smartSearchQuery
      ? `No files match "${escapeHtml(smartSearchQuery)}" in ${escapeHtml(config.title)}.`
      : escapeHtml(config.emptyHint);
    smartGridEl.innerHTML = `<div class="empty-hint">${emptyMessage}</div>`;
    return;
  }

  const rendered = matches.length > RESULT_RENDER_CAP ? matches.slice(0, RESULT_RENDER_CAP) : matches;

  smartGridEl.innerHTML = rendered.map((f) => fileCardHtml(f, { showFolderPath: true, draggable: false })).join("");
  lucide.createIcons();

  applySmartSelectionClasses();
}

smartGridEl.addEventListener("click", (e) => {

  if (smartMarqueeJustEnded) {
    smartMarqueeJustEnded = false;
    return;
  }
  const card = e.target.closest(".file-card");
  if (card) {
    const id = card.dataset.id;
    if (e.ctrlKey || e.metaKey) smartToggleSelect(id);
    else if (e.shiftKey) smartRangeSelect(id);
    else smartSelectOnly(id);
    return;
  }

  if (smartSelectionActive()) {
    smartClearSelection();
    applySmartSelectionClasses();
  }
});

smartGridEl.addEventListener("dblclick", (e) => {
  const card = e.target.closest(".file-card");
  if (!card) return;
  openFile(card.dataset.id);
});

smartGridEl.addEventListener("contextmenu", (e) => {
  const card = e.target.closest(".file-card");
  if (!card) {
    if (smartSelectionActive()) {
      smartClearSelection();
      applySmartSelectionClasses();
    }
    return;
  }
  e.preventDefault();
  const id = card.dataset.id;

  if (!smartSelectedFileIds.has(id)) {
    smartClearSelection();
    applySmartSelectionClasses();
  }
  openContextMenu(
    smartSelectionActive() ? smartBulkContextItems() : fileContextItems(id),
    e.clientX,
    e.clientY
  );
});

smartSearchInputEl.addEventListener(
  "input",
  debounce(() => {
    smartSearchQuery = smartSearchInputEl.value.trim();
    renderSmartView(currentSmartView);
  }, 180)
);

function smartBulkContextItems() {
  const count = smartSelectedFileIds.size;
  const items = [
    {
      label: "Move to",
      action: () =>
        openMovePanel({
          title: "Batch Move",
          ...smartBulkMoveExclusions(),
          onConfirm: (targetId) => smartBulkMove(targetId, { folderIds: [], fileIds: Array.from(smartSelectedFileIds) }),
        }),
    },
  ];
  if (count) items.unshift({ label: `Download (${count})`, action: () => smartBulkDownload() });
  if (count) {
    const anyUnstarred = Array.from(smartSelectedFileIds).some((id) => {
      const f = findFile(id);
      return f && !f.starred_at;
    });
    items.push({
      label: anyUnstarred ? "Star all" : "Unstar all",
      action: () => smartBulkStar(anyUnstarred),
    });
  }
  items.push({ label: "Delete", danger: true, action: () => smartBulkDelete() });
  return items;
}

function smartBulkMoveExclusions() {
  return { excludedIds: new Set(), currentParentId: null };
}

async function smartBulkMove(targetId, payload) {
  const failures = [];
  for (const id of payload.fileIds) {
    try {
      const updated = await apiFetch(`/api/files/${id}`, { method: "PUT", body: JSON.stringify({ folder_id: targetId }) });
      Object.assign(findFile(id), updated);
    } catch (err) {
      failures.push(`${(findFile(id) || {}).name || id}: ${err.message}`);
    }
  }
  smartClearSelection();
  renderGrid();
  if (currentSmartView) renderSmartView(currentSmartView);
  if (failures.length) alert(`Some items couldn't be moved:\n${failures.join("\n")}`);
}

async function smartBulkStar(starred) {
  const ids = Array.from(smartSelectedFileIds);
  if (!ids.length) return;
  try {
    const result = await apiFetch("/api/files/bulk-star", {
      method: "POST",
      body: JSON.stringify({ file_ids: ids, starred }),
    });
    if (result.ok) {
      for (const id of ids) {
        const f = findFile(id);
        if (f) f.starred_at = starred ? new Date().toISOString() : null;
      }
      smartClearSelection();
      applySmartSelectionClasses();
      renderGrid();
      if (currentSmartView) renderSmartView(currentSmartView);
    }
  } catch (err) {
    alert(err.message);
  }
}

async function smartBulkDelete() {
  const ids = Array.from(smartSelectedFileIds);
  if (!ids.length) return;

  const failures = [];
  const removedFileIds = new Set();
  for (const id of ids) {
    try {
      await apiFetch(`/api/files/${id}`, { method: "DELETE" });
      removedFileIds.add(id);
    } catch (err) {
      failures.push(`${(findFile(id) || {}).name || id}: ${err.message}`);
    }
  }
  files = files.filter((f) => !removedFileIds.has(f.id));
  smartClearSelection();
  renderGrid();
  if (currentSmartView) renderSmartView(currentSmartView);
  if (trashLoaded) loadTrash();
  if (failures.length) alert(`Some items couldn't be deleted:\n${failures.join("\n")}`);
}

function smartBulkDownload() {
  const ids = Array.from(smartSelectedFileIds);
  if (!ids.length) return;
  if (!supportsFileSystemAccess) {
    for (const id of ids) legacyDownloadFile(id);
    return;
  }
  bulkDownloadWithProgress(ids);
}

let folderHistory = [currentFolderId];
let folderHistoryIndex = 0;
let suppressFolderHistoryPush = false;

function openFolder(id) {
  if (!suppressFolderHistoryPush && folderHistory[folderHistoryIndex] !== id) {

    folderHistory = folderHistory.slice(0, folderHistoryIndex + 1);
    folderHistory.push(id);
    folderHistoryIndex = folderHistory.length - 1;
  }
  currentFolderId = id;
  window.currentFolderId = id;
  if (searchQuery) {
    searchQuery = "";
    searchInputEl.value = "";
  }

  let ancestor = id ? findFolder(id) : null;
  while (ancestor) {
    expandedFolderIds.add(ancestor.id);
    ancestor = ancestor.parent_id ? findFolder(ancestor.parent_id) : null;
  }
  clearSelection();
  renderAll();
}

function goFolderBack() {
  if (folderHistoryIndex <= 0) return;
  folderHistoryIndex -= 1;
  suppressFolderHistoryPush = true;
  openFolder(folderHistory[folderHistoryIndex]);
  suppressFolderHistoryPush = false;
}

function goFolderForward() {
  if (folderHistoryIndex >= folderHistory.length - 1) return;
  folderHistoryIndex += 1;
  suppressFolderHistoryPush = true;
  openFolder(folderHistory[folderHistoryIndex]);
  suppressFolderHistoryPush = false;
}

document.addEventListener("mouseup", (e) => {
  if (e.button !== 3 && e.button !== 4) return;
  e.preventDefault();
  const back = e.button === 3;
  if (!imageViewerEl.classList.contains("hide")) {
    imageViewerStep(back ? -1 : 1);
    return;
  }
  if (!videoViewerEl.classList.contains("hide")) {
    videoViewerStep(back ? -1 : 1);
    return;
  }
  if (!audioViewerEl.classList.contains("hide")) {
    audioViewerStep(back ? -1 : 1);
    return;
  }
  if (document.getElementById("view-explorer").classList.contains("hide")) return;
  if (back) goFolderBack();
  else goFolderForward();
});

function selectionActive() {
  return selectedFolderIds.size > 0 || selectedFileIds.size > 0;
}

function clearSelection() {
  selectedFolderIds.clear();
  selectedFileIds.clear();
}

let _explorerBaseCountText = "";

function applySelectionClasses() {
  gridEl.querySelectorAll(".folder-card, .file-card").forEach((card) => {
    const type = card.classList.contains("folder-card") ? "folder" : "file";
    const set = type === "folder" ? selectedFolderIds : selectedFileIds;
    card.classList.toggle("selected", set.has(card.dataset.id));
  });

  treeEl.querySelectorAll(".tree-item[data-id]").forEach((item) => {
    item.classList.toggle("selected", selectedFolderIds.has(item.dataset.id));
  });
  setItemCount(appendSelectionSummary(_explorerBaseCountText, selectedFolderIds, selectedFileIds, files));
}

function currentGridItems() {
  if (searchQuery) {
    const query = searchQuery.toLowerCase();

    const scopeIds = new Set([currentFolderId, ...collectDescendantIds(currentFolderId)]);
    return files
      .filter((f) => scopeIds.has(f.folder_id) && f.name.toLowerCase().includes(query))
      .sort((a, b) => a.name.localeCompare(b.name))
      .slice(0, RESULT_RENDER_CAP)
      .map((f) => ({ type: "file", id: f.id }));
  }
  return [
    ...foldersByParent(currentFolderId).map((f) => ({ type: "folder", id: f.id })),
    ...filesByFolder(currentFolderId).map((f) => ({ type: "file", id: f.id })),
  ];
}

function toggleSelect(type, id) {
  const set = type === "folder" ? selectedFolderIds : selectedFileIds;
  if (set.has(id)) set.delete(id);
  else set.add(id);
  const items = currentGridItems();
  const idx = items.findIndex((it) => it.type === type && it.id === id);
  if (idx !== -1) lastClickedIndex = idx;
  applySelectionClasses();
}

function selectOnly(type, id) {
  selectedFolderIds.clear();
  selectedFileIds.clear();
  (type === "folder" ? selectedFolderIds : selectedFileIds).add(id);
  const items = currentGridItems();
  const idx = items.findIndex((it) => it.type === type && it.id === id);
  if (idx !== -1) lastClickedIndex = idx;
  applySelectionClasses();
}

function rangeSelect(type, id) {
  const items = currentGridItems();
  const idx = items.findIndex((it) => it.type === type && it.id === id);
  if (idx === -1) return;
  const anchor = lastClickedIndex === null ? idx : lastClickedIndex;
  const [start, end] = idx < anchor ? [idx, anchor] : [anchor, idx];
  selectedFolderIds.clear();
  selectedFileIds.clear();
  for (let i = start; i <= end; i++) {
    const it = items[i];
    (it.type === "folder" ? selectedFolderIds : selectedFileIds).add(it.id);
  }
  applySelectionClasses();
}

function trashSelectionActive() {
  return trashSelectedFolderIds.size > 0 || trashSelectedFileIds.size > 0;
}

function trashClearSelection() {
  trashSelectedFolderIds.clear();
  trashSelectedFileIds.clear();
}

let _trashBaseCountText = "";

function applyTrashSelectionClasses() {
  trashListEl.querySelectorAll(".trash-item").forEach((item) => {
    const type = item.dataset.type;
    const set = type === "folder" ? trashSelectedFolderIds : trashSelectedFileIds;
    item.classList.toggle("selected", set.has(item.dataset.id));
  });
  trashCountEl.textContent = appendSelectionSummary(_trashBaseCountText, trashSelectedFolderIds, trashSelectedFileIds, trashFilesCache, trashFoldersCache);
  mirrorRailCount(trashCountEl.textContent);
}

function currentTrashItems() {
  let folders, files;
  if (trashSearchQuery) {
    const query = trashSearchQuery.toLowerCase();
    folders = trashFoldersCache.filter((f) => f.name.toLowerCase().includes(query));
    files = trashFilesCache.filter((f) => f.name.toLowerCase().includes(query));
  } else {
    folders = trashFoldersByParent(currentTrashFolderId);
    files = trashFilesByFolder(currentTrashFolderId);
  }
  const total = folders.length + files.length;
  if (total > RESULT_RENDER_CAP) {
    folders = folders.slice(0, RESULT_RENDER_CAP);
    files = files.slice(0, RESULT_RENDER_CAP - folders.length);
  }
  return [
    ...folders.map((f) => ({ type: "folder", id: f.id })),
    ...files.map((f) => ({ type: "file", id: f.id })),
  ];
}

function trashToggleSelect(type, id) {
  const set = type === "folder" ? trashSelectedFolderIds : trashSelectedFileIds;
  if (set.has(id)) set.delete(id);
  else set.add(id);
  const items = currentTrashItems();
  const idx = items.findIndex((it) => it.type === type && it.id === id);
  if (idx !== -1) trashLastClickedIndex = idx;
  applyTrashSelectionClasses();
}

function trashSelectOnly(type, id) {
  trashSelectedFolderIds.clear();
  trashSelectedFileIds.clear();
  (type === "folder" ? trashSelectedFolderIds : trashSelectedFileIds).add(id);
  const items = currentTrashItems();
  const idx = items.findIndex((it) => it.type === type && it.id === id);
  if (idx !== -1) trashLastClickedIndex = idx;
  applyTrashSelectionClasses();
}

function trashRangeSelect(type, id) {
  const items = currentTrashItems();
  const idx = items.findIndex((it) => it.type === type && it.id === id);
  if (idx === -1) return;
  const anchor = trashLastClickedIndex === null ? idx : trashLastClickedIndex;
  const [start, end] = idx < anchor ? [idx, anchor] : [anchor, idx];
  trashSelectedFolderIds.clear();
  trashSelectedFileIds.clear();
  for (let i = start; i <= end; i++) {
    const it = items[i];
    (it.type === "folder" ? trashSelectedFolderIds : trashSelectedFileIds).add(it.id);
  }
  applyTrashSelectionClasses();
}

function smartSelectionActive() {
  return smartSelectedFileIds.size > 0;
}

function smartClearSelection() {
  smartSelectedFileIds.clear();
}

let _smartBaseCountText = "";

function applySmartSelectionClasses() {
  smartGridEl.querySelectorAll(".file-card").forEach((card) => {
    card.classList.toggle("selected", smartSelectedFileIds.has(card.dataset.id));
  });
  smartCountEl.textContent = appendSelectionSummary(_smartBaseCountText, new Set(), smartSelectedFileIds, files);
  mirrorRailCount(smartCountEl.textContent);
}

function currentSmartItems() {
  if (!currentSmartView) return [];
  const config = SMART_VIEWS[currentSmartView];
  let matches = files.filter(config.filter).sort(_sortColumn ? _sortComparator() : config.sort);
  if (smartSearchQuery) {
    const query = smartSearchQuery.toLowerCase();
    matches = matches.filter((f) => f.name.toLowerCase().includes(query));
  }
  if (matches.length > RESULT_RENDER_CAP) matches = matches.slice(0, RESULT_RENDER_CAP);
  return matches.map((f) => ({ type: "file", id: f.id }));
}

function smartToggleSelect(id) {
  if (smartSelectedFileIds.has(id)) smartSelectedFileIds.delete(id);
  else smartSelectedFileIds.add(id);
  const items = currentSmartItems();
  const idx = items.findIndex((it) => it.id === id);
  if (idx !== -1) smartLastClickedIndex = idx;
  applySmartSelectionClasses();
}

function smartSelectOnly(id) {
  smartSelectedFileIds.clear();
  smartSelectedFileIds.add(id);
  const items = currentSmartItems();
  const idx = items.findIndex((it) => it.id === id);
  if (idx !== -1) smartLastClickedIndex = idx;
  applySmartSelectionClasses();
}

function smartRangeSelect(id) {
  const items = currentSmartItems();
  const idx = items.findIndex((it) => it.id === id);
  if (idx === -1) return;
  const anchor = smartLastClickedIndex === null ? idx : smartLastClickedIndex;
  const [start, end] = idx < anchor ? [idx, anchor] : [anchor, idx];
  smartSelectedFileIds.clear();
  for (let i = start; i <= end; i++) smartSelectedFileIds.add(items[i].id);
  applySmartSelectionClasses();
}

function openFile(id) {
  const file = findFile(id);
  markFileOpened(id);

  if (file && file.mime_type && file.mime_type.startsWith("video/")) {
    openVideoViewer(id);
    return;
  }
  if (file && file.mime_type && file.mime_type.startsWith("audio/")) {
    openAudioViewer(id);
    return;
  }
  if (file && file.mime_type && file.mime_type.startsWith("image/")) {
    openImageViewer(id);
    return;
  }
  window.open(`/api/files/${id}/content`, "_blank");
}

async function markFileOpened(id) {
  try {
    const updated = await apiFetch(`/api/files/${id}/opened`, { method: "POST" });
    const file = findFile(id);
    if (file) Object.assign(file, updated);
    if (currentSmartView === "history") renderSmartView("history");
  } catch (err) {
    console.error("Failed to record watch history:", err);
  }
}

async function playExternal(id) {
  try {
    await apiFetch(`/api/files/${id}/play-external`, { method: "POST" });
  } catch (err) {
    alert(err.message);
  }
}

function downloadFile(id) {
  if (!supportsFileSystemAccess) {
    legacyDownloadFile(id);
    return;
  }
  downloadFileWithProgress(id);
}

function currentTreeItems() {
  return Array.from(treeEl.querySelectorAll(".tree-item[data-id]")).map((el) => el.dataset.id);
}

let lastTreeClickedIndex = null;

function treeRangeSelect(id) {
  const items = currentTreeItems();
  const idx = items.indexOf(id);
  if (idx === -1) return;
  const anchor = lastTreeClickedIndex === null ? idx : lastTreeClickedIndex;
  const [start, end] = idx < anchor ? [idx, anchor] : [anchor, idx];
  selectedFolderIds.clear();
  selectedFileIds.clear();
  for (let i = start; i <= end; i++) selectedFolderIds.add(items[i]);
  applySelectionClasses();
}

treeEl.addEventListener("click", (e) => {
  const chevron = e.target.closest(".tree-chevron");
  if (chevron) {
    const item = chevron.closest(".tree-item");
    if (item && item.dataset.id) {
      if (e.altKey) toggleTreeExpandDeep(item.dataset.id);
      else toggleTreeExpand(item.dataset.id);
    }
    return;
  }

  const altItem = e.altKey ? e.target.closest(".tree-item") : null;
  if (altItem && altItem.dataset.id) {
    e.preventDefault();
    toggleTreeExpandDeep(altItem.dataset.id);
    return;
  }
  const item = e.target.closest(".tree-item");
  if (!item) {
    if (selectionActive()) { clearSelection(); applySelectionClasses(); }
    return;
  }
  const id = item.dataset.id || null;

  if (id && (e.ctrlKey || e.metaKey)) {
    toggleSelect("folder", id);
    const idx = currentTreeItems().indexOf(id);
    if (idx !== -1) lastTreeClickedIndex = idx;
    return;
  }
  if (id && e.shiftKey) {
    treeRangeSelect(id);
    return;
  }
  openFolder(id);
});

let marqueeJustEnded = false;

gridEl.addEventListener("click", (e) => {
  if (marqueeJustEnded) {
    marqueeJustEnded = false;
    return;
  }

  const folderCard = e.target.closest(".folder-card");
  const fileCard = e.target.closest(".file-card");
  const card = folderCard || fileCard;

  if (card) {
    const type = folderCard ? "folder" : "file";
    const id = card.dataset.id;
    if (e.ctrlKey || e.metaKey) {
      toggleSelect(type, id);
    } else if (e.shiftKey) {
      rangeSelect(type, id);
    } else {
      selectOnly(type, id);
    }
    return;
  }

  if (selectionActive()) {
    clearSelection();
    applySelectionClasses();
  }
});

gridEl.addEventListener("dblclick", (e) => {
  const folderCard = e.target.closest(".folder-card");
  const fileCard = e.target.closest(".file-card");
  if (folderCard) {
    openFolder(folderCard.dataset.id);
  } else if (fileCard) {
    openFile(fileCard.dataset.id);
  }
});

let marquee = null;

gridEl.addEventListener("mousedown", (e) => {
  if (e.button !== 0) return;

  marqueeJustEnded = false;
  if (e.target.closest(".card")) return;

  e.preventDefault();
  marquee = {
    startX: e.clientX,
    startY: e.clientY,

    mode: e.ctrlKey || e.metaKey ? "subtract" : e.shiftKey ? "add" : "replace",
    baseFolderIds: new Set(selectedFolderIds),
    baseFileIds: new Set(selectedFileIds),
    el: null,
  };
});

document.addEventListener("mousemove", (e) => {
  if (!marquee) return;
  const dx = e.clientX - marquee.startX;
  const dy = e.clientY - marquee.startY;
  if (!marquee.el) {

    if (Math.hypot(dx, dy) < 4) return;
    marquee.el = document.createElement("div");
    marquee.el.className = "marquee-select";
    document.body.appendChild(marquee.el);
    document.body.classList.add("marquee-dragging");
  }

  const nativeSelection = window.getSelection && window.getSelection();
  if (nativeSelection && nativeSelection.rangeCount) nativeSelection.removeAllRanges();

  const x1 = Math.min(e.clientX, marquee.startX);
  const y1 = Math.min(e.clientY, marquee.startY);
  const x2 = Math.max(e.clientX, marquee.startX);
  const y2 = Math.max(e.clientY, marquee.startY);
  Object.assign(marquee.el.style, {
    left: `${x1}px`,
    top: `${y1}px`,
    width: `${x2 - x1}px`,
    height: `${y2 - y1}px`,
  });

  selectedFolderIds = marquee.mode === "replace" ? new Set() : new Set(marquee.baseFolderIds);
  selectedFileIds = marquee.mode === "replace" ? new Set() : new Set(marquee.baseFileIds);
  const cards = gridEl.querySelectorAll(".folder-card, .file-card");
  cards.forEach((card) => {
    const rect = card.getBoundingClientRect();
    if (!(rect.left < x2 && rect.right > x1 && rect.top < y2 && rect.bottom > y1)) return;
    const type = card.classList.contains("folder-card") ? "folder" : "file";
    const set = type === "folder" ? selectedFolderIds : selectedFileIds;
    if (marquee.mode === "subtract") set.delete(card.dataset.id);
    else set.add(card.dataset.id);
  });

  cards.forEach((card) => {
    const type = card.classList.contains("folder-card") ? "folder" : "file";
    const set = type === "folder" ? selectedFolderIds : selectedFileIds;
    card.classList.toggle("selected", set.has(card.dataset.id));
  });

  setItemCount(appendSelectionSummary(_explorerBaseCountText, selectedFolderIds, selectedFileIds, files));
});

document.addEventListener("mouseup", () => {
  if (!marquee) return;
  if (marquee.el) {
    marquee.el.remove();

    marqueeJustEnded = true;
  }
  document.body.classList.remove("marquee-dragging");
  marquee = null;
});

let smartMarquee = null;
let smartMarqueeJustEnded = false;

smartGridEl.addEventListener("mousedown", (e) => {
  if (e.button !== 0) return;

  smartMarqueeJustEnded = false;

  e.preventDefault();
  smartMarquee = {
    startX: e.clientX,
    startY: e.clientY,
    mode: e.ctrlKey || e.metaKey ? "subtract" : e.shiftKey ? "add" : "replace",
    baseFileIds: new Set(smartSelectedFileIds),
  };
});

document.addEventListener("mousemove", (e) => {
  if (!smartMarquee) return;
  const dx = e.clientX - smartMarquee.startX;
  const dy = e.clientY - smartMarquee.startY;
  if (!smartMarquee.el) {
    if (Math.hypot(dx, dy) < 4) return;
    smartMarquee.el = document.createElement("div");
    smartMarquee.el.className = "marquee-select";
    document.body.appendChild(smartMarquee.el);
    document.body.classList.add("marquee-dragging");
  }
  const nativeSelection = window.getSelection && window.getSelection();
  if (nativeSelection && nativeSelection.rangeCount) nativeSelection.removeAllRanges();

  const x1 = Math.min(e.clientX, smartMarquee.startX);
  const y1 = Math.min(e.clientY, smartMarquee.startY);
  const x2 = Math.max(e.clientX, smartMarquee.startX);
  const y2 = Math.max(e.clientY, smartMarquee.startY);
  Object.assign(smartMarquee.el.style, {
    left: `${x1}px`,
    top: `${y1}px`,
    width: `${x2 - x1}px`,
    height: `${y2 - y1}px`,
  });

  smartSelectedFileIds = smartMarquee.mode === "replace" ? new Set() : new Set(smartMarquee.baseFileIds);
  const cards = smartGridEl.querySelectorAll(".file-card");
  cards.forEach((card) => {
    const rect = card.getBoundingClientRect();
    if (!(rect.left < x2 && rect.right > x1 && rect.top < y2 && rect.bottom > y1)) return;
    if (smartMarquee.mode === "subtract") smartSelectedFileIds.delete(card.dataset.id);
    else smartSelectedFileIds.add(card.dataset.id);
  });
  cards.forEach((card) => {
    card.classList.toggle("selected", smartSelectedFileIds.has(card.dataset.id));
  });

  smartCountEl.textContent = appendSelectionSummary(_smartBaseCountText, new Set(), smartSelectedFileIds, files);
});

document.addEventListener("mouseup", () => {
  if (!smartMarquee) return;
  if (smartMarquee.el) {
    smartMarquee.el.remove();
    smartMarqueeJustEnded = true;
  }
  document.body.classList.remove("marquee-dragging");
  smartMarquee = null;
});

const SIDEBAR_WIDTH_MIN = 160;
const SIDEBAR_WIDTH_MAX = 480;
const sidebarEl = document.querySelector(".sidebar");
const sidebarResizeHandle = document.getElementById("sidebar-resize-handle");

function clampSidebarWidth(px) {
  return Math.min(SIDEBAR_WIDTH_MAX, Math.max(SIDEBAR_WIDTH_MIN, px));
}

function applySidebarWidth(px) {
  document.documentElement.style.setProperty("--sidebar-width", `${px}px`);
}

const SIDEBAR_COLLAPSED_BASE_WIDTH = 28;

const SIDEBAR_COLLAPSED_DEPTH_STEP = 14;

function sidebarCollapsedWidth() {
  return SIDEBAR_COLLAPSED_BASE_WIDTH + treeMaxVisibleDepth * SIDEBAR_COLLAPSED_DEPTH_STEP;
}

const SIDEBAR_COLLAPSE_ENTER = SIDEBAR_WIDTH_MIN;
const SIDEBAR_COLLAPSE_EXIT_DRAG_PX = 40;

let sidebarCollapsed = localStorage.getItem("sidebarCollapsed") === "1";

function setSidebarCollapsed(collapsed) {
  if (collapsed === sidebarCollapsed) return;
  sidebarCollapsed = collapsed;
  sidebarEl.classList.toggle("icon-only", sidebarCollapsed);
  document.body.classList.add("sidebar-snap");
  setTimeout(() => document.body.classList.remove("sidebar-snap"), 220);
  applySidebarWidth(sidebarCollapsed ? sidebarCollapsedWidth() : SIDEBAR_WIDTH_MIN);
  localStorage.setItem("sidebarCollapsed", sidebarCollapsed ? "1" : "0");
}

let sidebarResize = null;

sidebarResizeHandle.addEventListener("mousedown", (e) => {
  if (e.button !== 0) return;
  e.preventDefault();

  const currentWidth = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--sidebar-width"));
  sidebarResize = {
    startX: e.clientX,
    startWidth: Number.isFinite(currentWidth) ? currentWidth : 220,
    collapseStartX: sidebarCollapsed ? e.clientX : null,
  };
  document.body.classList.add("sidebar-resizing");
});

document.addEventListener("mousemove", (e) => {
  if (!sidebarResize) return;
  const rawWidth = sidebarResize.startWidth + (e.clientX - sidebarResize.startX);
  let justExpanded = false;
  if (!sidebarCollapsed && rawWidth < SIDEBAR_COLLAPSE_ENTER) {
    setSidebarCollapsed(true);
    sidebarResize.collapseStartX = e.clientX;
  } else if (sidebarCollapsed && sidebarResize.collapseStartX !== null && e.clientX - sidebarResize.collapseStartX > SIDEBAR_COLLAPSE_EXIT_DRAG_PX) {
    setSidebarCollapsed(false);
    sidebarResize.startX = e.clientX;
    sidebarResize.startWidth = SIDEBAR_WIDTH_MIN;
    sidebarResize.collapseStartX = null;
    justExpanded = true;
  }
  if (!sidebarCollapsed && !justExpanded) {
    applySidebarWidth(clampSidebarWidth(rawWidth));
  }

  const nativeSelection = window.getSelection && window.getSelection();
  if (nativeSelection && nativeSelection.rangeCount) nativeSelection.removeAllRanges();
});

document.addEventListener("mouseup", () => {
  if (!sidebarResize) return;
  sidebarResize = null;
  document.body.classList.remove("sidebar-resizing");
  if (!sidebarCollapsed) {
    const currentWidth = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--sidebar-width"));
    if (Number.isFinite(currentWidth)) localStorage.setItem("sidebarWidth", String(currentWidth));
  }
});

function applyStoredSidebarWidth() {
  const stored = parseFloat(localStorage.getItem("sidebarWidth"));
  if (!Number.isFinite(stored)) return;
  applySidebarWidth(clampSidebarWidth(stored));
}

function applyStoredSidebarCollapsed() {
  if (!sidebarCollapsed) return;
  sidebarEl.classList.add("icon-only");
  applySidebarWidth(sidebarCollapsedWidth());
}

const RAIL_WIDTH_MIN = 160;
const RAIL_WIDTH_MAX = 320;
const railResizeHandle = document.getElementById("rail-resize-handle");

function clampRailWidth(px) {
  return Math.min(RAIL_WIDTH_MAX, Math.max(RAIL_WIDTH_MIN, px));
}

function applyRailWidth(px) {
  document.documentElement.style.setProperty("--rail-width", `${px}px`);
}

const RAIL_COLLAPSED_WIDTH = 68;
const RAIL_COLLAPSE_ENTER = RAIL_WIDTH_MIN;
const RAIL_COLLAPSE_EXIT_DRAG_PX = 40;

let railCollapsed = localStorage.getItem("railCollapsed") === "1";

function setRailCollapsed(collapsed) {
  if (collapsed === railCollapsed) return;
  railCollapsed = collapsed;
  railEl.classList.toggle("icon-only", railCollapsed);

  renderRailCount();

  document.body.classList.add("rail-snap");
  setTimeout(() => document.body.classList.remove("rail-snap"), 220);
  if (railCollapsed) {
    applyRailWidth(RAIL_COLLAPSED_WIDTH);
  } else {

    applyRailWidth(RAIL_WIDTH_MIN);
  }
  localStorage.setItem("railCollapsed", railCollapsed ? "1" : "0");
}

let railResize = null;

railResizeHandle.addEventListener("mousedown", (e) => {
  if (e.button !== 0) return;
  e.preventDefault();

  const currentWidth = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--rail-width"));
  railResize = {
    startX: e.clientX,
    startWidth: Number.isFinite(currentWidth) ? currentWidth : 200,

    collapseStartX: railCollapsed ? e.clientX : null,
  };
  document.body.classList.add("rail-resizing");
});

document.addEventListener("mousemove", (e) => {
  if (!railResize) return;
  const rawWidth = railResize.startWidth + (e.clientX - railResize.startX);
  let justExpanded = false;
  if (!railCollapsed && rawWidth < RAIL_COLLAPSE_ENTER) {
    setRailCollapsed(true);
    railResize.collapseStartX = e.clientX;
  } else if (railCollapsed && railResize.collapseStartX !== null && e.clientX - railResize.collapseStartX > RAIL_COLLAPSE_EXIT_DRAG_PX) {

    setRailCollapsed(false);
    railResize.startX = e.clientX;
    railResize.startWidth = RAIL_WIDTH_MIN;
    railResize.collapseStartX = null;
    justExpanded = true;
  }
  if (!railCollapsed && !justExpanded) {
    applyRailWidth(clampRailWidth(rawWidth));
  }

  const nativeSelection = window.getSelection && window.getSelection();
  if (nativeSelection && nativeSelection.rangeCount) nativeSelection.removeAllRanges();
});

document.addEventListener("mouseup", () => {
  if (!railResize) return;
  railResize = null;
  document.body.classList.remove("rail-resizing");
  if (!railCollapsed) {
    const currentWidth = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--rail-width"));
    if (Number.isFinite(currentWidth)) localStorage.setItem("railWidth", String(currentWidth));
  }
});

function applyStoredRailWidth() {
  const stored = parseFloat(localStorage.getItem("railWidth"));
  if (!Number.isFinite(stored)) return;
  applyRailWidth(clampRailWidth(stored));
}

function applyStoredRailCollapsed() {
  if (!railCollapsed) return;
  railEl.classList.add("icon-only");
  applyRailWidth(RAIL_COLLAPSED_WIDTH);

  renderRailCount();
}

const RAIL_RESPONSIVE_SHRINK_START = 1100;
const RAIL_RESPONSIVE_SHRINK_END = 820;
const RAIL_RESPONSIVE_COLLAPSE_WIDTH = 700;
let railAutoCollapsedByWindow = false;

function applyResponsiveRailSize() {
  if (railResize) return;
  const w = window.innerWidth;

  if (w < RAIL_RESPONSIVE_COLLAPSE_WIDTH) {
    if (!railCollapsed) {
      setRailCollapsed(true);
      railAutoCollapsedByWindow = true;
    }
    return;
  }

  if (railCollapsed) {
    if (!railAutoCollapsedByWindow) return;
    setRailCollapsed(false);
    railAutoCollapsedByWindow = false;
  }

  const stored = parseFloat(localStorage.getItem("railWidth"));
  const preferredWidth = clampRailWidth(Number.isFinite(stored) ? stored : RAIL_WIDTH_MIN);
  let targetWidth;
  if (w >= RAIL_RESPONSIVE_SHRINK_START) {
    targetWidth = preferredWidth;
  } else if (w <= RAIL_RESPONSIVE_SHRINK_END) {
    targetWidth = RAIL_WIDTH_MIN;
  } else {
    const t = (w - RAIL_RESPONSIVE_SHRINK_END) / (RAIL_RESPONSIVE_SHRINK_START - RAIL_RESPONSIVE_SHRINK_END);
    targetWidth = RAIL_WIDTH_MIN + t * (preferredWidth - RAIL_WIDTH_MIN);
  }
  applyRailWidth(targetWidth);
}

const SIDEBAR_RESPONSIVE_SHRINK_START = RAIL_RESPONSIVE_COLLAPSE_WIDTH;
const SIDEBAR_RESPONSIVE_SHRINK_END = 640;
const SIDEBAR_RESPONSIVE_COLLAPSE_WIDTH = 600;
let sidebarAutoCollapsedByWindow = false;

function applyResponsiveSidebarSize() {
  if (sidebarResize) return;
  const w = window.innerWidth;

  if (w < SIDEBAR_RESPONSIVE_COLLAPSE_WIDTH) {
    if (!sidebarCollapsed) {
      setSidebarCollapsed(true);
      sidebarAutoCollapsedByWindow = true;
    }
    return;
  }

  if (sidebarCollapsed) {
    if (!sidebarAutoCollapsedByWindow) return;
    setSidebarCollapsed(false);
    sidebarAutoCollapsedByWindow = false;
  }

  const stored = parseFloat(localStorage.getItem("sidebarWidth"));
  const preferredWidth = clampSidebarWidth(Number.isFinite(stored) ? stored : SIDEBAR_WIDTH_MIN);
  let targetWidth;
  if (w >= SIDEBAR_RESPONSIVE_SHRINK_START) {
    targetWidth = preferredWidth;
  } else if (w <= SIDEBAR_RESPONSIVE_SHRINK_END) {
    targetWidth = SIDEBAR_WIDTH_MIN;
  } else {
    const t = (w - SIDEBAR_RESPONSIVE_SHRINK_END) / (SIDEBAR_RESPONSIVE_SHRINK_START - SIDEBAR_RESPONSIVE_SHRINK_END);
    targetWidth = SIDEBAR_WIDTH_MIN + t * (preferredWidth - SIDEBAR_WIDTH_MIN);
  }
  applySidebarWidth(targetWidth);
}

let responsiveResizeTimer = null;
window.addEventListener("resize", () => {
  if (responsiveResizeTimer) return;
  responsiveResizeTimer = setTimeout(() => {
    responsiveResizeTimer = null;
    applyResponsiveRailSize();
    applyResponsiveSidebarSize();
  }, 16);
});

breadcrumbEl.addEventListener("click", (e) => {
  const crumb = e.target.closest(".crumb");
  if (!crumb) return;
  openFolder(crumb.dataset.id || null);
});

async function createFolder(parentId) {
  const name = window.prompt("Folder name:");
  if (name === null) return;
  const trimmed = name.trim();
  if (!trimmed) return;
  try {
    const folder = await apiFetch("/api/folders", {
      method: "POST",
      body: JSON.stringify({ name: trimmed, parent_id: parentId }),
    });
    folders.push(folder);
    renderAll();
  } catch (err) {
    alert(err.message);
  }
}

async function renameFolder(id) {
  const folder = findFolder(id);
  if (!folder) return;
  const name = window.prompt("Rename folder:", folder.name);
  if (name === null) return;
  const trimmed = name.trim();
  if (!trimmed || trimmed === folder.name) return;
  try {
    const updated = await apiFetch(`/api/folders/${id}`, {
      method: "PUT",
      body: JSON.stringify({ name: trimmed }),
    });
    Object.assign(folder, updated);
    renderAll();
  } catch (err) {
    alert(err.message);
  }
}

async function moveFolder(id, newParentId) {
  try {
    const updated = await apiFetch(`/api/folders/${id}`, {
      method: "PUT",
      body: JSON.stringify({ parent_id: newParentId }),
    });
    Object.assign(findFolder(id), updated);
    renderAll();
  } catch (err) {
    alert(err.message);
  }
}

async function deleteFolder(id) {
  try {
    await apiFetch(`/api/folders/${id}`, { method: "DELETE" });
    const removedIds = new Set([id, ...collectDescendantIds(id)]);
    if (removedIds.has(currentFolderId)) currentFolderId = null;
    folders = folders.filter((f) => !removedIds.has(f.id));
    files = files.filter((f) => !removedIds.has(f.folder_id));
    renderAll();
    if (trashLoaded) loadTrash();
  } catch (err) {
    alert(err.message);
  }
}

async function refreshCurrent() {
  try {
    const [newFolders, newFiles] = await Promise.all([apiFetch("/api/folders"), apiFetch("/api/files")]);
    folders = newFolders;
    files = newFiles;
    if (currentFolderId && !findFolder(currentFolderId)) currentFolderId = null;
    renderAll();
  } catch (err) {
    alert(err.message);
  }
}

async function refreshActiveView() {

  const view = currentView();
  try {
    if (view === "transfers") {

      await Promise.all([loadInterruptedUploads(), loadQueuedUploads(), loadCompletedUploads()]);
      updateTransfersUI();
      return;
    }
    if (view === "sync") {
      await loadSyncView();
      return;
    }
    if (view === "sync-transfers") {
      await loadSyncTransfersView();
      return;
    }
    if (view === "settings") {
      await loadTelegramStatus();
      refreshArchiveCheck();
      return;
    }
  } catch (err) {
    alert(err.message);
    return;
  }
  if (!document.getElementById("view-trash").classList.contains("hide")) {
    await loadTrash();
    return;
  }
  try {
    const [newFolders, newFiles] = await Promise.all([apiFetch("/api/folders"), apiFetch("/api/files")]);
    folders = newFolders;
    files = newFiles;
    if (currentFolderId && !findFolder(currentFolderId)) currentFolderId = null;

    if (currentSmartView && !document.getElementById("view-smart").classList.contains("hide")) {
      renderSmartView(currentSmartView);
    } else {
      renderAll();
    }
  } catch (err) {
    alert(err.message);
  }
}

searchInputEl.addEventListener(
  "input",
  debounce(() => {
    searchQuery = searchInputEl.value.trim();
    renderGrid();
  }, 180)
);

async function renameFile(id) {
  const file = findFile(id);
  if (!file) return;
  const name = window.prompt("Rename file:", file.name);
  if (name === null) return;
  const trimmed = name.trim();
  if (!trimmed || trimmed === file.name) return;
  try {
    const updated = await apiFetch(`/api/files/${id}`, {
      method: "PUT",
      body: JSON.stringify({ name: trimmed }),
    });
    Object.assign(file, updated);
    renderGrid();
    if (currentSmartView) renderSmartView(currentSmartView);
  } catch (err) {
    alert(err.message);
  }
}

async function moveFile(id, newFolderId) {
  try {
    const updated = await apiFetch(`/api/files/${id}`, {
      method: "PUT",
      body: JSON.stringify({ folder_id: newFolderId }),
    });
    Object.assign(findFile(id), updated);
    renderGrid();
    if (currentSmartView) renderSmartView(currentSmartView);
  } catch (err) {
    alert(err.message);
  }
}

async function deleteFile(id) {
  try {
    await apiFetch(`/api/files/${id}`, { method: "DELETE" });
    files = files.filter((f) => f.id !== id);
    renderGrid();
    if (trashLoaded) loadTrash();
    if (currentSmartView) renderSmartView(currentSmartView);
  } catch (err) {
    alert(err.message);
  }
}

let _queuePaused = false;

function pauseQueue() {
  _queuePaused = true;
}

function resumeQueue() {
  if (!_queuePaused) return;
  _queuePaused = false;

}

let _queueCancelled = false;

function cancelQueue() {
  _queueCancelled = true;
  _queuePaused = false;
}

function isQueueCancelled() {
  return _queueCancelled;
}

async function runConcurrentQueue(items, maxConcurrent) {
  let index = 0;

  function getNextIndex() {
    if (_queueCancelled) return -1;
    if (_queuePaused) return -2;
    if (index >= items.length) return -1;
    return index++;
  }
  async function worker() {
    while (true) {
      const i = getNextIndex();
      if (i === -1) break;
      if (i === -2) {
        await new Promise(r => setTimeout(r, 200));
        continue;
      }

  if (_queuePaused) {
    await new Promise(r => setTimeout(r, 50));
    if (_queuePaused) {
      index = i;
      continue;
    }
  }
  await items[i].start();
    }
  }

  _queueCancelled = false;
  const count = Math.min(maxConcurrent, items.length);
  if (count < 1) return;
  const workers = Array.from({ length: count }, () => worker());
  await Promise.all(workers);

  _queueCancelled = false;
}

async function pickAndUploadFiles(targetFolderId = currentFolderId) {
  let paths = null;
  try {
    const result = await apiFetch("/api/pick-files", { method: "POST" });
    paths = result.paths;
  } catch (err) {
    paths = null;
  }
  if (paths === null) {
    fileInputEl.click();
    return;
  }
  if (!paths.length) return;
  await uploadFilesFromPaths(paths, targetFolderId);
}

async function uploadFilesFromPaths(paths, targetFolderId = currentFolderId) {
  const items = paths.map((p) => ({
    file_path: p,
    filename: p.split(/[\\/]/).pop(),
    folder_id: targetFolderId,

    skip_duplicate_check: false,
  }));
  const rows = items.map((pending) => {
    const row = renderUploadRow(pending.filename, undefined, pending.folder_id, "upload", pending.size_bytes);
    row.dataset.queuedId = pending.id;
    row.querySelector(".upload-status").textContent = "Queued - waiting for another transfer to finish…";
    setRowActions(row, [
      {
        label: "Cancel",
        onClick: () => {
          row._uploadCancelled = true;
          dismissRow(row);
        },
      },
    ]);
    return { pending, row };
  });
  updateTransfersUI();
  await runConcurrentQueue(
    rows.map(({ pending, row }) => ({
      start: () => (row._uploadCancelled ? Promise.resolve() : runFolderUploadAttempt(pending, row)),
    })),
    maxParallelTransfers,
  );
}

fileInputEl.addEventListener("change", () => {
  uploadFiles(Array.from(fileInputEl.files));
  fileInputEl.value = "";
});

async function uploadFolder() {
  let path;
  try {
    const result = await apiFetch("/api/pick-folder", { method: "POST" });
    path = result.path;
  } catch (err) {
    alert(err.message);
    return;
  }
  if (!path) return;
  let pendingUploads;
  try {
    const result = await apiFetch("/api/folders/upload-tree", {
      method: "POST",
      body: JSON.stringify({ path, folder_id: currentFolderId }),
    });
    await refreshCurrent();
    pendingUploads = result.pending_uploads;
  } catch (err) {
    alert(err.message);
    return;
  }

  const { rootFiles, folders } = buildFolderTree(pendingUploads);
  const pendingToRow = new Map();

  for (const pending of rootFiles) {
    const row = renderUploadRow(pending.filename, undefined, pending.folder_id, "upload", pending.size_bytes);
    row.dataset.queuedId = pending.id;
    row.querySelector(".upload-status").textContent = "Queued - waiting for another transfer to finish…";
    setRowActions(row, [
      {
        label: "Cancel",
        onClick: async () => {
          row._uploadCancelled = true;
          dismissRow(row);

          apiFetch(`/api/uploads/queued/${pending.id}/dismiss`, { method: "POST" }).catch(() => {});
        },
      },
    ]);
    pendingToRow.set(pending, row);
  }
  for (const [, folder] of folders) {
    renderFolderSubtree(folder, folders, pendingToRow);
  }
  updateTransfersUI();
  const items = pendingUploads.map((pending) => ({
    start: () => {
      const row = pendingToRow.get(pending);
      if (!row) return Promise.resolve();
      return runFolderUploadAttempt(pending, row);
    },
  }));
  await runConcurrentQueue(items, maxParallelTransfers);
}

function _readAllDirEntries(dirEntry) {
  const reader = dirEntry.createReader();
  const all = [];
  function readBatch() {
    return new Promise((resolve, reject) => reader.readEntries(resolve, reject)).then((batch) => {
      if (!batch.length) return all;
      all.push(...batch);
      return readBatch();
    });
  }
  return readBatch();
}

function _readEntryFile(fileEntry) {
  return new Promise((resolve, reject) => fileEntry.file(resolve, reject));
}

async function _walkDroppedEntry(entry, basePath, results) {
  if (entry.isFile) {
    const file = await _readEntryFile(entry);
    results.push({ file, relativePath: basePath + entry.name });
  } else if (entry.isDirectory) {
    const children = await _readAllDirEntries(entry);
    for (const child of children) {
      await _walkDroppedEntry(child, basePath + entry.name + "/", results);
    }
  }
}

function _makeFolderEnsurer(rootFolderId) {
  const cache = new Map([["", rootFolderId]]);
  const inFlight = new Map();
  async function ensure(dirPath) {
    if (cache.has(dirPath)) return cache.get(dirPath);
    if (inFlight.has(dirPath)) return inFlight.get(dirPath);
    const parts = dirPath.split("/");
    const name = parts.pop();
    const parentPath = parts.join("/");
    const promise = (async () => {
      const parentId = await ensure(parentPath);

      const folder = await apiFetch("/api/folders", {
        method: "POST",
        body: JSON.stringify({ name, parent_id: parentId, reuse_if_exists: true }),
      });
      cache.set(dirPath, folder.id);
      return folder.id;
    })();
    inFlight.set(dirPath, promise);
    return promise;
  }
  return ensure;
}

async function stageDroppedFile(file, folderId, relativePath) {
  const formData = new FormData();
  formData.append("file", file, file.name);
  if (folderId) formData.append("folder_id", folderId);
  if (relativePath) formData.append("relative_path", relativePath);
  const resp = await fetch("/api/uploads/queued/stage", { method: "POST", body: formData });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.error || `Server returned ${resp.status}`);
  return data;
}

async function handleDroppedFolders(dataTransferItems, targetFolderId) {
  const topEntries = Array.from(dataTransferItems)
    .map((item) => (item.webkitGetAsEntry ? item.webkitGetAsEntry() : null))
    .filter(Boolean);
  const walked = [];
  for (const entry of topEntries) {
    await _walkDroppedEntry(entry, "", walked);
  }
  if (!walked.length) return;

  const ensureFolder = _makeFolderEnsurer(targetFolderId);

  const pendingUploads = walked.map(({ file, relativePath }) => ({
    id: null,
    filename: file.name,
    relative_path: relativePath,
    folder_id: undefined,
    size_bytes: file.size,
    _file: file,
    _staged: false,
  }));

  const { rootFiles, folders } = buildFolderTree(pendingUploads);
  const pendingToRow = new Map();
  for (const pending of rootFiles) {
    pendingToRow.set(pending, _renderDroppedFileRow(pending));
  }
  for (const [, folder] of folders) {
    renderFolderSubtree(folder, folders, pendingToRow);
  }
  updateTransfersUI();

  for (const pending of pendingUploads) {
    const row = pendingToRow.get(pending);
    if (row && row._uploadCancelled) continue;
    const parts = pending.relative_path.split("/");
    parts.pop();
    try {
      const folderId = await ensureFolder(parts.join("/"));
      const staged = await stageDroppedFile(pending._file, folderId, pending.relative_path);
      Object.assign(pending, staged, { _staged: true });
      if (row) {
        row.dataset.queuedId = pending.id;
        if (pending.folder_id !== undefined) setUploadRowFolder(row, pending.folder_id);
        row.querySelector(".upload-status").textContent = "Queued - waiting for another transfer to finish…";
        setRowActions(row, [_dismissQueuedAction(row, pending)]);
      }
    } catch (err) {

      console.error(`Failed to stage dropped file "${pending.relative_path}":`, err);
      if (row) {
        row.querySelector(".upload-status").textContent = `Couldn't prepare this file - ${err.message}`;
        row.classList.add("upload-error");
        setRowActions(row, [{ label: "Dismiss", onClick: () => dismissRow(row) }]);
      }
    }
    updateTransfersUI();
  }

  const items = pendingUploads
    .filter((pending) => pending._staged)
    .map((pending) => ({
      start: () => {
        const row = pendingToRow.get(pending);
        if (!row || row._uploadCancelled) return Promise.resolve();
        return runFolderUploadAttempt(pending, row);
      },
    }));
  if (!items.length) return;
  await runConcurrentQueue(items, maxParallelTransfers);
}

function _dismissQueuedAction(row, pending) {
  return {
    label: "Cancel",
    onClick: () => {
      row._uploadCancelled = true;
      dismissRow(row);
      if (pending.id) {
        apiFetch(`/api/uploads/queued/${pending.id}/dismiss`, { method: "POST" }).catch(() => {});
      }
    },
  };
}

function _renderDroppedFileRow(pending) {
  const row = renderUploadRow(pending.filename, undefined, undefined, "upload", pending.size_bytes);
  row.querySelector(".upload-status").textContent = "Preparing…";
  setRowActions(row, [_dismissQueuedAction(row, pending)]);
  return row;
}

function buildFolderTree(pendingUploads) {
  const folders = new Map();
  const rootFiles = [];
  for (const pending of pendingUploads) {
    const parts = (pending.relative_path || pending.filename).split("/");
    const filename = parts.pop();
    const folderPath = parts.join("/");
    if (folderPath === "") {
      rootFiles.push(pending);
      continue;
    }

    let currentParent = folders;
    let currentPath = "";
    let leafFolder = null;
    for (const name of parts) {
      currentPath = currentPath ? `${currentPath}/${name}` : name;
      let folder = currentParent.get(currentPath);
      if (!folder) {
        folder = {
          path: currentPath,
          name,
          sourcePath: currentPath + "/",
          vaultPath: currentPath + "/",
          files: [],
          subfolders: new Map(),
        };
        currentParent.set(currentPath, folder);
      }
      leafFolder = folder;
      currentParent = folder.subfolders;
    }
    leafFolder.files.push({ pending, filename });
  }
  return { rootFiles, folders };
}

function folderIdResolverFor(folder) {
  if (!folder.files.length) return undefined;
  return () => {
    for (const entry of folder.files) {

      const pending = entry.pending || entry;
      if (pending.folder_id !== undefined && pending.folder_id !== null) return pending.folder_id;
    }
    return null;
  };
}

function renderFolderSubtree(folder, allFolders, pendingToRow) {

  const { row, childrenContainer } = renderFolderRow(
    folder.sourcePath, folder.vaultPath, folder.files.length, folderIdResolverFor(folder),
  );
  for (const { pending, filename } of folder.files) {
    const childRow = renderUploadRow(filename, undefined, pending.folder_id, "upload", pending.size_bytes);

    if (pending.id) {
      childRow.dataset.queuedId = pending.id;
      childRow.querySelector(".upload-status").textContent = "Queued - waiting for another transfer to finish…";
    } else {
      childRow.querySelector(".upload-status").textContent = "Preparing…";
    }
    setRowActions(childRow, [
      {
        label: "Cancel",
        onClick: async () => {
          childRow._uploadCancelled = true;
          dismissRow(childRow);

          if (pending.id) {
            apiFetch(`/api/uploads/queued/${pending.id}/dismiss`, { method: "POST" }).catch(() => {});
          }
        },
      },
    ]);
    childrenContainer.appendChild(childRow);
    pendingToRow.set(pending, childRow);
  }
  for (const [, sub] of folder.subfolders) {
    renderFolderSubtree(sub, allFolders, pendingToRow);
  }
}

async function runFolderUploadAttempt(pending, row) {

  if (row._uploadCancelled) {
    dismissRow(row);
    if (pending.id) {
      apiFetch(`/api/uploads/queued/${pending.id}/dismiss`, { method: "POST" }).catch(() => {});
    }
    return;
  }
  row.classList.remove("upload-error", "upload-paused");
  row.querySelector(".upload-status").textContent = "Uploading…";
  row.querySelector(".upload-bar-fill").style.width = "0%";
  try {

    const data = await apiFetch("/api/uploads/start-from-path", {
      method: "POST",
      body: JSON.stringify({ ...pending, queued_id: pending.id }),
    });
    row.dataset.uploadId = data.upload_id;
    await runNativeUploadAttempt(data.upload_id, row);
  } catch (err) {
    row.querySelector(".upload-status").textContent = err.message;
    row.classList.add("upload-error");
    const actions = [{ label: "Dismiss", onClick: () => dismissRow(row) }];

    const isConnectionError = err.message && (
      err.message.toLowerCase().includes("not connected") ||
      err.message.toLowerCase().includes("connection") ||
      err.message.toLowerCase().includes("timed out")
    );
    if (isConnectionError) {
      actions.unshift({ label: "Retry", onClick: () => runFolderUploadAttempt(pending, row) });
    }
    setRowActions(row, actions);
    updateTransfersUI();
  }
}

async function uploadFiles(fileList, targetFolderId = currentFolderId) {

  const fileToRow = new Map();
  for (const file of fileList) {
    const row = renderUploadRow(file.name, undefined, targetFolderId, "upload", file.size);
    row.querySelector(".upload-status").textContent = "Queued - waiting for another upload to finish…";
    setRowActions(row, [
      {
        label: "Cancel",
        onClick: async () => {

          row._uploadCancelled = true;
          dismissRow(row);
        },
      },
    ]);
    fileToRow.set(file, row);
  }
  updateTransfersUI();

  const items = fileList.map((file) => ({
    start: async () => {
      const row = fileToRow.get(file);
      if (!row) return;

      if (row._uploadCancelled) {
        dismissRow(row);
        return;
      }
      await runUploadAttempt(file, targetFolderId, row);
    },
  }));
  await runConcurrentQueue(items, maxParallelTransfers);
}

async function triggerVersionUpload(id) {
  versionUploadTargetId = id;

  try {
    const result = await apiFetch("/api/pick-files", {
      method: "POST",
      body: JSON.stringify({ multiple: false }),
    });
    if (result.paths !== null) {
      if (!result.paths.length) return;
      await uploadNewVersionFromPath(id, result.paths[0]);
      return;
    }
  } catch (err) {

  }
  versionFileInputEl.click();
}

async function uploadNewVersionFromPath(fileId, path) {
  const existing = findFile(fileId);
  const row = renderUploadRow(existing?.name ?? path.split(/[\\/]/).pop(), undefined, existing?.folder_id);
  await runFolderUploadAttempt(
    {
      file_path: path,
      filename: path.split(/[\\/]/).pop(),
      folder_id: existing?.folder_id ?? null,
      target_file_id: fileId,

      skip_duplicate_check: true,
    },
    row,
  );
}

versionFileInputEl.addEventListener("change", () => {
  const file = Array.from(versionFileInputEl.files)[0];
  versionFileInputEl.value = "";
  if (file) uploadNewVersion(versionUploadTargetId, file);
});

function isValidMoveTarget(targetFolderId) {
  if (!dragPayload) return false;
  if (dragPayload.folderIds.includes(targetFolderId)) return false;
  for (const fid of dragPayload.folderIds) {
    if (collectDescendantIds(fid).includes(targetFolderId)) return false;
  }
  return true;
}

function clearAllDragOver() {
  document.querySelectorAll(".drag-over").forEach((el) => el.classList.remove("drag-over"));
}

gridEl.addEventListener("dragstart", (e) => {
  const folderCard = e.target.closest(".folder-card");
  const fileCard = e.target.closest(".file-card");
  const card = folderCard || fileCard;
  if (!card) return;
  const type = folderCard ? "folder" : "file";
  const id = card.dataset.id;
  const inSelection = (type === "folder" ? selectedFolderIds : selectedFileIds).has(id);
  dragPayload = inSelection
    ? { folderIds: Array.from(selectedFolderIds), fileIds: Array.from(selectedFileIds) }
    : { folderIds: type === "folder" ? [id] : [], fileIds: type === "file" ? [id] : [] };

  if (dragPayload.fileIds.length === 1 && dragPayload.folderIds.length === 0) {
    const file = findFile(dragPayload.fileIds[0]);
    if (file) {

      const url = new URL(`/api/files/${file.id}/content`, window.location.origin).href;
      const mime = file.mime_type || "application/octet-stream";
      e.dataTransfer.setData("DownloadURL", `${mime}:${file.name}:${url}`);
    }
  }
  e.dataTransfer.effectAllowed = "move";
});
gridEl.addEventListener("dragend", () => {
  dragPayload = null;
  clearAllDragOver();
});

gridEl.addEventListener("dragover", (e) => {
  const folderCard = e.target.closest(".folder-card");
  if (dragPayload) {

    e.stopPropagation();
    if (folderCard && isValidMoveTarget(folderCard.dataset.id)) {
      e.preventDefault();
      folderCard.classList.add("drag-over");
    }
    return;
  }
  if (!e.dataTransfer.types.includes("Files")) return;
  e.preventDefault();
  e.stopPropagation();
  if (folderCard) folderCard.classList.add("drag-over");
  else gridEl.classList.add("drag-over");
});
gridEl.addEventListener("dragleave", (e) => {
  const folderCard = e.target.closest(".folder-card");
  if (folderCard) folderCard.classList.remove("drag-over");
  else gridEl.classList.remove("drag-over");
});
gridEl.addEventListener("drop", (e) => {
  const folderCard = e.target.closest(".folder-card");
  if (dragPayload) {
    e.stopPropagation();
    if (folderCard && isValidMoveTarget(folderCard.dataset.id)) {
      e.preventDefault();
      folderCard.classList.remove("drag-over");
      bulkMove(folderCard.dataset.id, dragPayload);
    }
    return;
  }

  const items = e.dataTransfer.items;
  const hasFolder = items && Array.from(items).some((item) => {
    const entry = item.webkitGetAsEntry && item.webkitGetAsEntry();
    return entry && entry.isDirectory;
  });
  if (hasFolder) {
    e.preventDefault();
    e.stopPropagation();
    if (folderCard) folderCard.classList.remove("drag-over");
    else gridEl.classList.remove("drag-over");
    const targetFolderId = folderCard ? folderCard.dataset.id : currentFolderId;
    handleDroppedFolders(items, targetFolderId);
    return;
  }
  if (!e.dataTransfer.files || !e.dataTransfer.files.length) return;

  if (folderCard) folderCard.classList.remove("drag-over");
  else gridEl.classList.remove("drag-over");
  if (window.pywebview) return;
  e.preventDefault();
  e.stopPropagation();
  const targetFolderId = folderCard ? folderCard.dataset.id : currentFolderId;
  uploadFiles(Array.from(e.dataTransfer.files), targetFolderId);
});

treeEl.addEventListener("dragstart", (e) => {
  const item = e.target.closest(".tree-item");
  if (!item || !item.dataset.id) return;
  dragPayload = { folderIds: [item.dataset.id], fileIds: [] };
  e.dataTransfer.effectAllowed = "move";
});
treeEl.addEventListener("dragend", () => {
  dragPayload = null;
  clearAllDragOver();
});
treeEl.addEventListener("dragover", (e) => {
  const item = e.target.closest(".tree-item");
  if (!item) return;
  const targetId = item.dataset.id || null;
  if (dragPayload) {
    e.stopPropagation();
    if (isValidMoveTarget(targetId)) {
      e.preventDefault();
      item.classList.add("drag-over");
    }
    return;
  }
  if (!e.dataTransfer.types.includes("Files")) return;
  e.preventDefault();
  e.stopPropagation();
  item.classList.add("drag-over");
});
treeEl.addEventListener("dragleave", (e) => {
  const item = e.target.closest(".tree-item");
  if (item) item.classList.remove("drag-over");
});
treeEl.addEventListener("drop", (e) => {
  const item = e.target.closest(".tree-item");
  if (!item) return;
  const targetId = item.dataset.id || null;
  item.classList.remove("drag-over");
  if (dragPayload) {
    e.stopPropagation();
    if (isValidMoveTarget(targetId)) {
      e.preventDefault();
      bulkMove(targetId, dragPayload);
    }
    return;
  }
  if (!e.dataTransfer.files || !e.dataTransfer.files.length) return;

  if (window.pywebview) return;
  e.preventDefault();
  e.stopPropagation();
  uploadFiles(Array.from(e.dataTransfer.files), targetId);
});

document.addEventListener("dragover", (e) => {
  if (dragPayload || e.dataTransfer.types.includes("Files")) e.preventDefault();
});
document.addEventListener("drop", (e) => {
  if (dragPayload || (e.dataTransfer.files && e.dataTransfer.files.length)) e.preventDefault();
});

function applyTransfersSearchFilter() {
  const query = transfersSearchQuery.trim().toLowerCase();
  uploadListEl.querySelectorAll(":scope > .upload-row").forEach((row) => {
    if (row.classList.contains("upload-folder")) {
      const childrenContainer = row.nextElementSibling?.classList.contains("upload-folder-children")
        ? row.nextElementSibling
        : null;
      const children = childrenContainer ? Array.from(childrenContainer.querySelectorAll(".upload-row")) : [];
      let anyChildMatch = false;
      children.forEach((child) => {
        const name = child.querySelector(".upload-name")?.textContent || "";
        const match = !query || name.toLowerCase().includes(query);
        child.classList.toggle("search-hidden", !match);
        if (match) anyChildMatch = true;
      });
      const folderName = row.querySelector(".upload-name")?.textContent || "";
      const folderMatch = !query || folderName.toLowerCase().includes(query);
      row.classList.toggle("search-hidden", !(folderMatch || anyChildMatch));
      if (folderMatch && !anyChildMatch) {
        children.forEach((child) => child.classList.remove("search-hidden"));
      }
    } else {
      const name = row.querySelector(".upload-name")?.textContent || "";
      const match = !query || name.toLowerCase().includes(query);
      row.classList.toggle("search-hidden", !match);
    }
  });
}

function applyTransfersSubTabFilter() {

  if (transfersSearchAllTabs && transfersSearchQuery.trim()) {
    uploadListEl.querySelectorAll(".upload-row, .upload-folder-children").forEach((el) => {
      el.classList.remove("subtab-hidden");
    });
    return;
  }
  uploadListEl.querySelectorAll(":scope > .upload-row").forEach((row) => {
    if (row.classList.contains("upload-folder")) {
      const childrenContainer = row.nextElementSibling?.classList.contains("upload-folder-children")
        ? row.nextElementSibling
        : null;
      const children = childrenContainer ? Array.from(childrenContainer.querySelectorAll(".upload-row")) : [];
      let anyChildVisible = false;
      children.forEach((child) => {
        const isCompleted = child.classList.contains("upload-success");
        const show = transfersSubTab === "completed" ? isCompleted : (!isCompleted && transfersSubTab === "uploading");
        child.classList.toggle("subtab-hidden", !show);
        if (show) anyChildVisible = true;
      });
      row.classList.toggle("subtab-hidden", !anyChildVisible);
      if (childrenContainer) childrenContainer.classList.toggle("subtab-hidden", !anyChildVisible);
      return;
    }
    const kind = row.dataset.kind === "download" ? "downloading" : "uploading";
    const isCompleted = row.classList.contains("upload-success");
    const show = transfersSubTab === "completed" ? isCompleted : (!isCompleted && transfersSubTab === kind);
    row.classList.toggle("subtab-hidden", !show);
  });
}

function updateTransfersSubTabButtons() {
  const counts = { uploading: 0, downloading: 0, completed: 0 };
  uploadListEl.querySelectorAll(".upload-row:not(.upload-folder)").forEach((row) => {
    if (row.classList.contains("upload-success")) {
      counts.completed++;
      return;
    }
    const kind = row.dataset.kind === "download" ? "downloading" : "uploading";
    counts[kind]++;
  });
  document.querySelectorAll(".transfers-subtab-btn").forEach((btn) => {
    const key = btn.dataset.subtab;
    const countEl = btn.querySelector(".transfers-subtab-count");
    countEl.textContent = counts[key] || "";
    countEl.classList.toggle("hide", !counts[key]);
    const active = transfersSubTab === key;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", String(active));
  });
}

function updateTransfersUI() {
  applyTransfersSearchFilter();
  applyTransfersSubTabFilter();
  updateTransfersSubTabButtons();

  const pending = uploadListEl.querySelectorAll(".upload-row:not(.upload-success):not(.upload-folder)").length;
  transfersBadgeEl.textContent = pending || "";
  transfersBadgeEl.classList.toggle("hide", pending === 0);
  const hasAnyRows = uploadListEl.children.length > 0;
  const hasVisibleRows = !!uploadListEl.querySelector(":scope > .upload-row:not(.search-hidden):not(.subtab-hidden)");
  const trimmedQuery = transfersSearchQuery.trim();
  if (!hasAnyRows) {
    transfersEmptyHintEl.textContent = "No transfers yet this session.";
    transfersEmptyHintEl.classList.remove("hide");
  } else if (trimmedQuery && !hasVisibleRows) {

    transfersEmptyHintEl.textContent = `No transfers match "${trimmedQuery}".`;
    transfersEmptyHintEl.classList.remove("hide");
  } else if (!hasVisibleRows) {

    transfersEmptyHintEl.textContent = `No ${transfersSubTab} transfers.`;
    transfersEmptyHintEl.classList.remove("hide");
  } else {
    transfersEmptyHintEl.classList.add("hide");
  }

  pauseAllBtnEl.classList.toggle(
    "hide",
    rowActionButtons("Pause").length === 0
      && rowActionButtons("Cancel").length === 0
      && rowActionButtons("Stop").length === 0,
  );
  continueAllBtnEl.classList.toggle("hide", rowActionButtons("Continue").length === 0);

  clearFinishedBtnEl.classList.toggle("hide", uploadListEl.querySelectorAll(".upload-row.upload-success").length === 0);

  clearDuplicatesBtnEl.classList.toggle("hide", uploadListEl.querySelectorAll(".upload-row.upload-duplicate").length === 0);

  const hasContinueable = rowActionButtons("Continue").length > 0 || queuedUploadsList.length > 0;
  continueAllBtnEl.classList.toggle("hide", !hasContinueable);

  dismissAllBtnEl.classList.toggle("hide", uploadListEl.querySelectorAll(".upload-row").length === 0);
  updateTransfersSummary();
}

function updateTransfersSummary() {

  const overallProgressEl = document.getElementById("transfers-overall-progress");
  const overallText = document.getElementById("transfers-overall-text");
  let batchBytesDone = 0;
  let batchBytesTotal = 0;
  let movingBytesRemaining = 0;
  let activeTransfers = 0;
  let queuedTransfers = 0;
  let pausedTransfers = 0;
  uploadListEl.querySelectorAll(".upload-row:not(.upload-folder)").forEach((row) => {
    const finished = row.classList.contains("upload-success");
    const stalled = row.classList.contains("upload-error") || row.classList.contains("upload-duplicate") || row.classList.contains("upload-paused");
    const total = Number(row.dataset.bytesTotal) || 0;
    const done = Number(row.dataset.bytesDone) || 0;
    if (total > 0) {

      batchBytesTotal += total;
      batchBytesDone += finished ? total : Math.min(done, total);
    }
    if (finished) return;
    if (stalled) {

      if (row.classList.contains("upload-paused") && !row.classList.contains("upload-duplicate")) pausedTransfers++;
      return;
    }
    if (total > 0) {
      activeTransfers++;
      movingBytesRemaining += Math.max(0, total - Math.min(done, total));
    } else {

      queuedTransfers++;
    }
  });

  if (activeTransfers === 0 && queuedTransfers === 0 && pausedTransfers === 0) {
    overallProgressEl.classList.add("hide");
    _overallRateSample = null;
    return;
  }
  overallProgressEl.classList.remove("hide");
  const parts = [];
  if (batchBytesTotal > 0) {
    parts.push(`${formatBytes(batchBytesDone)} / ${formatBytes(batchBytesTotal)}`);
    parts.push(`${Math.round((batchBytesDone / batchBytesTotal) * 100)}%`);

    const eta = _overallEtaText(batchBytesDone, movingBytesRemaining);
    if (eta) parts.push(eta);
  }
  if (activeTransfers) parts.push(`${activeTransfers} active`);
  if (queuedTransfers) parts.push(`${queuedTransfers} queued`);

  if (pausedTransfers) parts.push(`${pausedTransfers} paused`);
  overallText.textContent = parts.join(" · ");
}

function _setRowBytes(row, bytesDone, bytesTotal) {
  if (!row) return;
  if (Number.isFinite(bytesTotal) && bytesTotal > 0) row.dataset.bytesTotal = String(bytesTotal);
  if (Number.isFinite(bytesDone) && bytesDone >= 0) row.dataset.bytesDone = String(bytesDone);
  _scheduleSummaryRefresh();
}

let _summaryRefreshTimer = null;

function _scheduleSummaryRefresh() {
  if (_summaryRefreshTimer) return;
  _summaryRefreshTimer = setTimeout(() => {
    _summaryRefreshTimer = null;
    updateTransfersSummary();
  }, 250);
}

let _overallRateSample = null;

function _overallEtaText(bytesDone, remaining) {
  const now = Date.now();
  if (remaining <= 0) return "";
  if (!_overallRateSample || bytesDone < _overallRateSample.bytes) {

    _overallRateSample = { bytes: bytesDone, time: now, rate: 0 };
    return "";
  }
  const elapsed = (now - _overallRateSample.time) / 1000;
  if (elapsed < 0.5) {

    return _overallRateSample.rate > 0 ? `${formatDuration(remaining / _overallRateSample.rate)} left` : "";
  }
  const instantRate = (bytesDone - _overallRateSample.bytes) / elapsed;

  const rate = _overallRateSample.rate > 0 ? _overallRateSample.rate * 0.7 + instantRate * 0.3 : instantRate;
  _overallRateSample = { bytes: bytesDone, time: now, rate };
  return rate > 0 ? `${formatDuration(remaining / rate)} left` : "";
}

function rowActionButtons(label) {
  return Array.from(uploadListEl.querySelectorAll(".upload-action-btn")).filter((btn) => btn.textContent === label);
}
document.getElementById("pause-all-btn").addEventListener("click", async () => {

  pauseQueue();

  const allRows = Array.from(document.querySelectorAll(".upload-row"));
  for (const row of allRows) {
    const buttons = Array.from(row.querySelectorAll(".upload-action-btn"));
    const pauseBtn = buttons.find((btn) => btn.textContent === "Pause");
    const stopBtn = buttons.find((btn) => btn.textContent === "Stop");
    if (pauseBtn) {
      pauseBtn.click();

      await new Promise(r => setTimeout(r, 50));
    } else if (stopBtn) {
      stopBtn.click();
      await new Promise(r => setTimeout(r, 50));
    }
  }
});
document.getElementById("continue-all-btn").addEventListener("click", async () => {

  for (const btn of rowActionButtons("Continue")) {
    btn.click();
    await new Promise((r) => setTimeout(r, 50));
  }

  resumeQueue();

  if (queuedUploadsList.length > 0) {
    const btn = document.getElementById("continue-all-btn");
    if (btn) btn.disabled = true;
    await uploadAllQueuedSequentially();
    if (btn) btn.disabled = false;
  }
});

document.getElementById("dismiss-all-btn").addEventListener("click", () => {

  cancelQueue();

  uploadListEl.querySelectorAll(".upload-row").forEach((row) => {

    if (row.dataset.queuedId) {
      apiFetch(`/api/uploads/queued/${row.dataset.queuedId}/dismiss`, { method: "POST" }).catch(() => {});
    }

    if (row.dataset.uploadId && !row.classList.contains("upload-success") && !row.classList.contains("upload-paused")) {
      apiFetch(`/api/uploads/${row.dataset.uploadId}/cancel`, {
        method: "POST", body: JSON.stringify({ forget: true }),
      }).catch(() => {});
    }

    if (row.dataset.uploadId && row.classList.contains("upload-paused") && !row.classList.contains("upload-duplicate")) {
      apiFetch(`/api/uploads/interrupted/${row.dataset.uploadId}/cancel`, { method: "POST" }).catch(() => {});
    }

    if (row.dataset.fileId) {
      row._downloadCancelled = true;
      row._downloadAbort?.abort();
    }

    if (row.classList.contains("upload-folder")) {
      const childrenContainer = row.nextElementSibling;
      if (childrenContainer && childrenContainer.classList.contains("upload-folder-children")) {
        childrenContainer.remove();
      }
    }
    row.remove();
  });
  updateTransfersUI();
});

document.getElementById("clear-finished-btn").addEventListener("click", () => {

  apiFetch("/api/transfers/completed/clear", { method: "POST" }).catch(() => {});
  uploadListEl.querySelectorAll(".upload-row.upload-success").forEach((row) => {
    if (row.classList.contains("upload-folder")) {
      const childrenContainer = row.nextElementSibling;
      if (childrenContainer && childrenContainer.classList.contains("upload-folder-children")) {
        childrenContainer.remove();
      }
    }
    row.remove();
  });
  uploadListEl.querySelectorAll(".upload-folder").forEach((folderRow) => updateFolderProgress(folderRow));
  updateTransfersUI();
});

document.getElementById("clear-duplicates-btn").addEventListener("click", () => {
  uploadListEl.querySelectorAll(".upload-row.upload-duplicate").forEach((row) => dismissRow(row));
  updateTransfersUI();
});

function renderUploadRow(name, status = "Uploading…", folderId, kind = "upload", sizeBytes) {
  const row = document.createElement("div");
  row.className = "upload-row";
  if (Number.isFinite(sizeBytes) && sizeBytes > 0) _setRowBytes(row, 0, sizeBytes);

  row.dataset.kind = kind;
  row.innerHTML = `
    <span class="upload-name" title="${escapeHtml(name)}">${escapeHtml(name)}</span>
    <span class="upload-vault-path hide"></span>
    <div class="upload-bar"><div class="upload-bar-fill"></div></div>
    <span class="upload-status">${escapeHtml(status)}</span>
    <span class="upload-actions"></span>
  `;
  if (folderId !== undefined) setUploadRowFolder(row, folderId);
  row.querySelector(".upload-vault-path").addEventListener("click", (e) => {
    e.stopPropagation();
    switchView("explorer");
    openFolder(row.dataset.folderId || null);
  });
  uploadListEl.appendChild(row);
  updateTransfersUI();
  return row;
}

function setUploadRowFolder(row, folderId) {
  row.dataset.folderId = folderId || "";
  const pathEl = row.querySelector(".upload-vault-path");
  if (!pathEl) return;
  pathEl.classList.remove("hide");
  const display = folderDisplayPath(folderId || null);

  const isRoot = !folderId;
  pathEl.textContent = `→ ${display}`;
  pathEl.title = isRoot ? "Go to Folder root" : `Go to ${display}`;
}

function renderFolderRow(sourcePath, vaultPath, totalChildren, resolveFolderId) {
  const row = document.createElement("div");
  row.className = "upload-row upload-folder";
  row.dataset.folderRow = "true";
  row.innerHTML = `
    <button type="button" class="upload-folder-toggle" aria-label="Toggle folder" data-collapsed="false">▼</button>
    <span class="upload-name" title="${escapeHtml(sourcePath)}">${escapeHtml(sourcePath)}</span>
    <span class="upload-vault-path" title="Vault path: ${escapeHtml(vaultPath)}">→ ${escapeHtml(vaultPath)}</span>
    <div class="upload-folder-bar"><div class="upload-folder-bar-fill" style="width: 0%"></div></div>
    <span class="upload-folder-progress">0 of ${totalChildren}</span>
    <span class="upload-actions"></span>
  `;
  const pathEl = row.querySelector(".upload-vault-path");
  if (resolveFolderId) {
    pathEl.addEventListener("click", (e) => {
      e.stopPropagation();
      const folderId = resolveFolderId();
      if (folderId === undefined || folderId === null) return;
      switchView("explorer");
      openFolder(folderId);
    });
  } else {
    pathEl.classList.add("upload-vault-path-static");
  }
  const childrenContainer = document.createElement("div");
  childrenContainer.className = "upload-folder-children";
  const toggle = row.querySelector(".upload-folder-toggle");
  toggle.addEventListener("click", () => {
    const collapsed = toggle.dataset.collapsed === "true";
    if (collapsed) {
      childrenContainer.classList.remove("collapsed");
      toggle.dataset.collapsed = "false";
      toggle.textContent = "▼";
    } else {
      childrenContainer.classList.add("collapsed");
      toggle.dataset.collapsed = "true";
      toggle.textContent = "▶";
    }
  });
  uploadListEl.appendChild(row);
  uploadListEl.appendChild(childrenContainer);
  updateTransfersUI();
  return { row, childrenContainer };
}

function updateFolderProgress(folderRow) {
  const childrenContainer = folderRow.nextElementSibling;
  if (!childrenContainer || !childrenContainer.classList.contains("upload-folder-children")) {
    return;
  }
  const childRows = Array.from(childrenContainer.querySelectorAll(".upload-row"));
  const total = childRows.length;
  const done = childRows.filter((r) => r.classList.contains("upload-success")).length;
  const errored = childRows.filter((r) => r.classList.contains("upload-error")).length;
  const active = total - done - errored;
  const progressEl = folderRow.querySelector(".upload-folder-progress");
  if (total === 0) {

    folderRow.remove();
    childrenContainer.remove();
    updateTransfersUI();
    return;
  }
  if (active > 0) {
    if (progressEl) progressEl.textContent = `${done} of ${total} done`;
    folderRow.classList.remove("upload-success");
    const pct = total ? Math.round((done / total) * 100) : 0;
    const barFill = folderRow.querySelector(".upload-folder-bar-fill");
    if (barFill) barFill.style.width = `${pct}%`;
  } else if (errored > 0) {
    if (progressEl) progressEl.textContent = `${done} done, ${errored} failed`;
    folderRow.classList.remove("upload-success");
    const pct = total ? Math.round((done / total) * 100) : 0;
    const barFill = folderRow.querySelector(".upload-folder-bar-fill");
    if (barFill) barFill.style.width = `${pct}%`;
  } else {
    if (progressEl) progressEl.textContent = `Done (${done})`;
    folderRow.classList.add("upload-success");
    const barFill = folderRow.querySelector(".upload-folder-bar-fill");
    if (barFill) barFill.style.width = "100%";
  }
}

function updateParentFolderProgress(row) {
  const parentChildren = row.parentElement;
  if (!parentChildren || !parentChildren.classList.contains("upload-folder-children")) {
    return;
  }
  const parentFolderRow = parentChildren.previousElementSibling;
  if (parentFolderRow && parentFolderRow.classList.contains("upload-folder")) {
    updateFolderProgress(parentFolderRow);
  }
}

function setRowActions(row, actions) {
  const container = row.querySelector(".upload-actions");
  container.innerHTML = "";
  actions.forEach(({ label, onClick }) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "upload-action-btn";
    btn.textContent = label;
    btn.addEventListener("click", onClick);
    container.appendChild(btn);
  });
}

function dismissRow(row) {

  if (row.dataset.uploadId && row.classList.contains("upload-paused") && !row.classList.contains("upload-duplicate")) {
    apiFetch(`/api/uploads/interrupted/${row.dataset.uploadId}/cancel`, { method: "POST" }).catch(() => {});
  }

  const parentChildrenContainer = row.parentElement;
  const parentFolderRow = parentChildrenContainer?.classList.contains("upload-folder-children")
    ? parentChildrenContainer.previousElementSibling
    : null;
  row.remove();
  if (parentFolderRow && parentFolderRow.classList.contains("upload-folder")) {
    updateFolderProgress(parentFolderRow);
  }
  updateTransfersUI();
}

function startQueuedNativeDrop(items) {
  const rows = items.map((pending) => {
    const row = renderUploadRow(pending.filename, undefined, pending.folder_id, "upload", pending.size_bytes);
    row.dataset.queuedId = pending.id;
    row.querySelector(".upload-status").textContent = "Queued - waiting for another transfer to finish…";
    setRowActions(row, [
      {
        label: "Cancel",
        onClick: () => {
          row._uploadCancelled = true;
          dismissRow(row);
          apiFetch(`/api/uploads/queued/${pending.id}/dismiss`, { method: "POST" }).catch(() => {});
        },
      },
    ]);
    return { pending, row };
  });
  updateTransfersUI();
  const queueItems = rows.map(({ pending, row }) => ({
    start: () => {
      if (row._uploadCancelled) return Promise.resolve();
      return runFolderUploadAttempt(pending, row);
    },
  }));
  runConcurrentQueue(queueItems, maxParallelTransfers);
}
window.startQueuedNativeDrop = startQueuedNativeDrop;

async function runNativeUploadAttempt(uploadId, row) {
  row.dataset.uploadId = uploadId;
  row.classList.remove("upload-error", "upload-paused");
  await pollUpload(uploadId, row, {
    onContinue: () => continueUploadOnRow(uploadId, row, (newUploadId) => runNativeUploadAttempt(newUploadId, row)),
  });
}

async function continueUploadOnRow(uploadId, row, onSuccess) {

  try {
    const data = await apiFetch(`/api/uploads/${uploadId}/continue`, { method: "POST" });
    await onSuccess(data.upload_id);
  } catch (err) {
    row.querySelector(".upload-status").textContent = err.message;
    row.classList.add("upload-error");
    setRowActions(row, [{ label: "Dismiss", onClick: () => dismissRow(row) }]);
    updateTransfersUI();
  }
}

async function uploadOneFile(file, targetFolderId = currentFolderId) {
  const row = renderUploadRow(file.name, undefined, targetFolderId, "upload", file.size);
  await runUploadAttempt(file, targetFolderId, row);
}

async function runUploadAttempt(file, targetFolderId, row, force = false) {
  row.classList.remove("upload-error", "upload-paused");
  row.querySelector(".upload-status").textContent = "Uploading…";
  row.querySelector(".upload-bar-fill").style.width = "0%";
  try {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("folder_id", targetFolderId ?? "");
    if (force) formData.append("force", "true");
    const resp = await fetch("/api/files", { method: "POST", body: formData });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.error || `Server returned ${resp.status}`);
    await pollUploadedFileUpload(data.upload_id, file, targetFolderId, row);
  } catch (err) {
    row.querySelector(".upload-status").textContent = err.message;
    row.classList.add("upload-error");
    const actions = [{ label: "Dismiss", onClick: () => dismissRow(row) }];

    const isConnectionError = err.message && (
      err.message.toLowerCase().includes("not connected") ||
      err.message.toLowerCase().includes("connection") ||
      err.message.toLowerCase().includes("timed out")
    );
    if (isConnectionError) {
      actions.unshift({ label: "Retry", onClick: () => runUploadAttempt(file, targetFolderId, row, force) });
    }
    setRowActions(row, actions);
    updateTransfersUI();
  }
}

async function pollUploadedFileUpload(uploadId, file, targetFolderId, row) {

  row.dataset.uploadId = uploadId;

  await pollUpload(uploadId, row, {
    onContinue: () => continueUploadOnRow(uploadId, row, (newUploadId) =>
      pollUploadedFileUpload(newUploadId, file, targetFolderId, row)),

    onAddAsVersion: (duplicateFileId) => runVersionUploadAttempt(duplicateFileId, file, row),
    onForceUpload: () => runUploadAttempt(file, targetFolderId, row, true),
  });
}

async function uploadNewVersion(fileId, file) {
  const row = renderUploadRow(findFile(fileId)?.name ?? file.name, undefined, findFile(fileId)?.folder_id);
  await runVersionUploadAttempt(fileId, file, row);
}

async function runVersionUploadAttempt(fileId, file, row) {
  row.classList.remove("upload-error", "upload-paused");
  row.querySelector(".upload-status").textContent = "Uploading…";
  row.querySelector(".upload-bar-fill").style.width = "0%";
  try {
    const formData = new FormData();
    formData.append("file", file);
    const resp = await fetch(`/api/files/${fileId}/versions`, { method: "POST", body: formData });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.error || `Server returned ${resp.status}`);
    await pollVersionUpload(data.upload_id, fileId, file, row);
  } catch (err) {
    row.querySelector(".upload-status").textContent = err.message;
    row.classList.add("upload-error");
    setRowActions(row, [{ label: "Dismiss", onClick: () => dismissRow(row) }]);
    updateTransfersUI();
  }
}

async function pollVersionUpload(uploadId, fileId, file, row) {
  row.dataset.uploadId = uploadId;
  await pollUpload(uploadId, row, {
    onContinue: () => continueUploadOnRow(uploadId, row, (newUploadId) =>
      pollVersionUpload(newUploadId, fileId, file, row)),

    onDone: (updatedFile) => {
      const existing = findFile(fileId);
      if (existing) Object.assign(existing, updatedFile);
      renderGrid();
      if (currentSmartView) renderSmartView(currentSmartView);
    },
  });
}

function pollUpload(uploadId, row, { onContinue, onDone, onAddAsVersion, onForceUpload } = {}) {
  return new Promise((resolve) => {
    setRowActions(row, [
      {
        label: "Pause",
        onClick: async () => {
          setRowActions(row, []);
          try {
            await apiFetch(`/api/uploads/${uploadId}/cancel`, { method: "POST" });
          } catch (err) {

          }
        },
      },
    ]);
    updateTransfersUI();

    const attemptStartTime = Date.now();
    let pollRetries = 0;

    let bytesDoneAtAttemptStart = null;
    const tick = async () => {
      try {
        const info = await apiFetch(`/api/uploads/${uploadId}`);

        pollRetries = 0;
        if (bytesDoneAtAttemptStart === null) bytesDoneAtAttemptStart = info.bytes_done || 0;

        if (row.dataset.folderId === undefined && info.folder_id !== undefined) {
          setUploadRowFolder(row, info.folder_id);
        }
        const pct = info.bytes_total ? Math.round((info.bytes_done / info.bytes_total) * 100) : 0;
        row.querySelector(".upload-bar-fill").style.width = `${pct}%`;

        _setRowBytes(row, info.bytes_done, info.bytes_total);
        if (info.status === "done") {
          row.querySelector(".upload-status").textContent = "Done";
          row.classList.add("upload-success");
          setRowActions(row, []);
          if (onDone) {
            onDone(info.file);
          } else {
            files.push(info.file);
            if (info.file.folder_id === currentFolderId) renderGrid();
          }
          refreshStats();
          updateTransfersUI();

          updateParentFolderProgress(row);
          resolve();
        } else if (info.status === "cancelled") {

          const doneText = info.bytes_total
            ? `${formatBytes(info.bytes_done)} / ${formatBytes(info.bytes_total)}`
            : formatBytes(info.bytes_done);
          row.querySelector(".upload-status").textContent = `Paused · ${doneText}`;
          row.classList.add("upload-paused");
          const actions = [{ label: "Dismiss", onClick: () => dismissRow(row) }];
          if (onContinue) actions.unshift({ label: "Continue", onClick: onContinue });
          setRowActions(row, actions);
          updateTransfersUI();
          resolve();
        } else if (info.status === "error") {
          row.querySelector(".upload-status").textContent = info.error;
          row.classList.add("upload-error");
          const actions = [{ label: "Dismiss", onClick: () => dismissRow(row) }];

          const isConnectionError = info.error && (
            info.error.toLowerCase().includes("not connected") ||
            info.error.toLowerCase().includes("connection") ||
            info.error.toLowerCase().includes("timed out")
          );
          if (isConnectionError) {
            actions.unshift({ label: "Retry", onClick: () => {
              row.classList.remove("upload-error");
              row.querySelector(".upload-status").textContent = "Retrying…";

              apiFetch(`/api/uploads/${uploadId}`).then(retryInfo => {
                if (retryInfo.folder_id !== undefined) {
                  runFolderUploadAttempt({
                    file_path: retryInfo.file_path,
                    filename: retryInfo.filename,
                    folder_id: retryInfo.folder_id,
                    max_chunk_size: retryInfo.max_chunk_size,
                  }, row);
                }
              }).catch(() => {
                row.querySelector(".upload-status").textContent = "Retry failed - " + info.error;
                row.classList.add("upload-error");
              });
            }});
          }
          setRowActions(row, actions);
          updateTransfersUI();

          updateParentFolderProgress(row);
          resolve();
        } else if (info.status === "queued") {

          row.querySelector(".upload-status").textContent = "Queued - waiting for another transfer to finish…";
          setRowActions(row, [
            {
              label: "Pause",
              onClick: async () => {
                setRowActions(row, []);
                try {
                  await apiFetch(`/api/uploads/${uploadId}/cancel`, { method: "POST" });
                } catch (err) {

                }
              },
            },
          ]);
          setTimeout(tick, 400);
        } else if (info.status === "duplicate") {

          row.querySelector(".upload-status").textContent = info.duplicate_file
            ? `Duplicate of "${info.duplicate_file.name}"`
            : "Duplicate of a file currently being uploaded elsewhere";

          row.classList.add("upload-paused", "upload-duplicate");
          const actions = [{ label: "Dismiss", onClick: () => dismissRow(row) }];
          if (onForceUpload) actions.unshift({ label: "Upload anyway", onClick: onForceUpload });
          if (onAddAsVersion && info.duplicate_file) {
            actions.unshift({ label: "Add as new version", onClick: () => onAddAsVersion(info.duplicate_file.id) });
          }
          setRowActions(row, actions);
          updateTransfersUI();
          resolve();
        } else {
          const speedEta = formatSpeedAndEta(info.bytes_done, info.bytes_total, bytesDoneAtAttemptStart, attemptStartTime, row._prevBytesDone, row._prevPollTime);
          row._prevBytesDone = info.bytes_done;
          row._prevPollTime = Date.now();
          _setRowBytes(row, info.bytes_done, info.bytes_total);
          row.querySelector(".upload-status").textContent = speedEta
            ? `${formatBytes(info.bytes_done)} / ${formatBytes(info.bytes_total)} · ${speedEta}`
            : `${formatBytes(info.bytes_done)} / ${formatBytes(info.bytes_total)}`;
          setTimeout(tick, 400);
        }
      } catch (err) {

        if (pollRetries < 3) {
          pollRetries++;
          setTimeout(tick, 1000 * pollRetries);
        } else {
          row.querySelector(".upload-status").textContent = err.message;
          row.classList.add("upload-error");
          setRowActions(row, [{ label: "Dismiss", onClick: () => dismissRow(row) }]);
          updateTransfersUI();
          resolve();
        }
      }
    };
    tick();
  });
}

const supportsFileSystemAccess = "showSaveFilePicker" in window;

function legacyDownloadFile(id) {
  const file = findFile(id);
  const a = document.createElement("a");

  a.href = `/api/files/${id}/content?cache=0`;
  a.download = file ? file.name : "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

class DownloadPaused extends Error {}

class DownloadCancelled extends Error {}

async function streamFileToHandle(id, fileHandle, row, startByte = 0) {
  const file = findFile(id);
  const controller = new AbortController();
  row._downloadAbort = controller;
  const headers = startByte > 0 ? { Range: `bytes=${startByte}-` } : {};
  let resp;
  try {

    resp = await fetch(`/api/files/${id}/content?cache=0`, { headers, signal: controller.signal });
  } finally {
    row._downloadAbort = null;
  }
  if (!resp.ok && resp.status !== 206) throw new Error(`Server returned ${resp.status}`);

  let total = null;
  if (resp.status === 206) {
    const contentRange = resp.headers.get("Content-Range");
    const match = contentRange && contentRange.match(/\/(\d+)$/);
    total = match ? parseInt(match[1], 10) : file ? file.size_bytes : null;
  } else {
    const headerTotal = parseInt(resp.headers.get("Content-Length"), 10);
    total = headerTotal > 0 ? headerTotal : file ? file.size_bytes : null;
  }
  row._bytesTotal = total;

  const writable = await fileHandle.createWritable({ keepExistingData: startByte > 0 });
  const reader = resp.body.getReader();
  row._downloadAbort = controller;
  let bytesDone = startByte;
  row._bytesDone = bytesDone;

  const attemptStartTime = Date.now();
  let prevBytesDone = bytesDone;
  let prevTime = Date.now();
  try {
    while (true) {

      if (row._downloadCancelled) {
        throw new DownloadCancelled();
      }
      const { done, value } = await reader.read();
      if (done) break;
      await writable.write({ type: "write", position: bytesDone, data: value });
      bytesDone += value.byteLength;
      row._bytesDone = bytesDone;
      _setRowBytes(row, bytesDone, total);
      row.querySelector(".upload-bar-fill").style.width = total ? `${Math.round((bytesDone / total) * 100)}%` : "0%";
      const now = Date.now();
      const speedEta = formatSpeedAndEta(bytesDone, total, startByte, attemptStartTime, prevBytesDone, prevTime);
      prevBytesDone = bytesDone;
      prevTime = now;
      row.querySelector(".upload-status").textContent = total
        ? (speedEta ? `${formatBytes(bytesDone)} / ${formatBytes(total)} · ${speedEta}` : `${formatBytes(bytesDone)} / ${formatBytes(total)}`)
        : (speedEta ? `${formatBytes(bytesDone)} · ${speedEta}` : formatBytes(bytesDone));
    }
    await writable.close();
  } catch (err) {
    if (row._pausing) {

      await writable.close().catch(() => {});
      throw new DownloadPaused();
    }
    if (row._downloadCancelled) {
      await writable.abort().catch(() => {});
      throw new DownloadCancelled();
    }
    await writable.abort().catch(() => {});
    throw err;
  } finally {
    row._downloadAbort = null;
  }
}

async function runDownloadAttempt(id, fileHandle, row, startByte = 0) {
  row.dataset.fileId = id;
  row.classList.remove("upload-paused", "upload-error");
  row._pausing = false;
  row._stopping = false;
  setRowActions(row, [
    { label: "Pause", onClick: () => { row._pausing = true; row._downloadAbort?.abort(); } },
    { label: "Stop", onClick: () => { row._stopping = true; row._downloadAbort?.abort(); } },
  ]);
  updateTransfersUI();
  try {
    await streamFileToHandle(id, fileHandle, row, startByte);
    row.querySelector(".upload-status").textContent = "Done";
    row.classList.add("upload-success");
    setRowActions(row, []);
    updateTransfersUI();

  } catch (err) {
    if (err instanceof DownloadPaused) {
      const doneText = row._bytesTotal
        ? `${formatBytes(row._bytesDone)} / ${formatBytes(row._bytesTotal)}`
        : formatBytes(row._bytesDone);
      row.querySelector(".upload-status").textContent = `Paused · ${doneText}`;
      row.classList.add("upload-paused");
      setRowActions(row, [
        { label: "Continue", onClick: () => runDownloadAttempt(id, fileHandle, row, row._bytesDone) },
        { label: "Dismiss", onClick: () => dismissRow(row) },
      ]);
      updateTransfersUI();
      return;
    }
    if (err instanceof DownloadCancelled || row._downloadCancelled) {
      dismissRow(row);
      return;
    }
    if (row._stopping) {
      dismissRow(row);
      return;
    }
    row.querySelector(".upload-status").textContent = err.message;
    row.classList.add("upload-error");
    setRowActions(row, [{ label: "Dismiss", onClick: () => dismissRow(row) }]);
    updateTransfersUI();
  }
}

async function downloadFileWithProgress(id) {
  const file = findFile(id);
  let handle;
  try {

    handle = await window.showSaveFilePicker({ suggestedName: file ? file.name : id });
  } catch (err) {
    if (err.name === "AbortError") return;
    alert(err.message);
    return;
  }
  const row = renderUploadRow(file ? file.name : id, "Downloading…", undefined, "download");
  await runDownloadAttempt(id, handle, row, 0);
}

async function dedupeName(name, usedLower, dirHandle) {
  const dot = name.lastIndexOf(".");
  const base = dot > 0 ? name.slice(0, dot) : name;
  const ext = dot > 0 ? name.slice(dot) : "";
  let candidate = name;
  let i = 1;
  while (true) {
    if (!usedLower.has(candidate.toLowerCase())) {
      try {
        await dirHandle.getFileHandle(candidate);
      } catch (err) {
        break;
      }
    }
    candidate = `${base} (${i})${ext}`;
    i++;
  }
  return candidate;
}

async function bulkDownloadWithProgress(ids) {
  let dirHandle;
  try {

    dirHandle = await window.showDirectoryPicker({ mode: "readwrite" });
  } catch (err) {
    if (err.name === "AbortError") return;
    alert(err.message);
    return;
  }
  const usedNamesLower = new Set();

  const handles = [];
  for (const id of ids) {
    const file = findFile(id);
    const name = await dedupeName(file ? file.name : id, usedNamesLower, dirHandle);
    usedNamesLower.add(name.toLowerCase());
    try {
      const fileHandle = await dirHandle.getFileHandle(name, { create: true });
      handles.push({ id, fileHandle, name });
    } catch (err) {
      const row = renderUploadRow(name, "Downloading…", undefined, "download");
      row.querySelector(".upload-status").textContent = err.message;
      row.classList.add("upload-error");
      setRowActions(row, [{ label: "Dismiss", onClick: () => dismissRow(row) }]);
      updateTransfersUI();
    }
  }

  const handleToRow = new Map();
  for (const { id, name } of handles) {
    const row = renderUploadRow(name, "Queued - waiting for another download to finish…", undefined, "download", findFile(id)?.size_bytes);
    setRowActions(row, [
      {
        label: "Cancel",
        onClick: async () => {

          row._downloadCancelled = true;
          row._downloadAbort?.abort();
        },
      },
    ]);
    handleToRow.set(name, row);
  }
  updateTransfersUI();
  const items = handles.map(({ id, fileHandle, name }) => ({
    start: async () => {
      const row = handleToRow.get(name);
      if (!row) return;

      if (row._downloadCancelled) {
        dismissRow(row);
        return;
      }
      row.querySelector(".upload-status").textContent = "Downloading…";
      row.querySelector(".upload-bar-fill").style.width = "0%";
      setRowActions(row, [
        { label: "Pause", onClick: () => { row._pausing = true; row._downloadAbort?.abort(); } },
        { label: "Stop", onClick: () => { row._stopping = true; row._downloadAbort?.abort(); } },
      ]);
      try {
        await runDownloadAttempt(id, fileHandle, row, 0);
      } catch (err) {

        if (err.name === "DownloadPaused" || err.name === "DownloadStopped") {
          return;
        }
        throw err;
      }
    },
  }));
  await runConcurrentQueue(items, maxParallelTransfers);
}

function dedupeFolderName(name, usedLower) {
  let candidate = name;
  let i = 1;
  while (usedLower.has(candidate.toLowerCase())) {
    candidate = `${name} (${i})`;
    i++;
  }
  return candidate;
}

async function downloadFilesInto(fileIds, dirHandle, usedLower) {

  const handles = [];
  for (const id of fileIds) {
    const file = findFile(id);
    const name = await dedupeName(file ? file.name : id, usedLower, dirHandle);
    usedLower.add(name.toLowerCase());
    try {
      const fileHandle = await dirHandle.getFileHandle(name, { create: true });
      handles.push({ id, fileHandle, name });
    } catch (err) {
      const row = renderUploadRow(name, "Downloading…", undefined, "download");
      row.querySelector(".upload-status").textContent = err.message;
      row.classList.add("upload-error");
      setRowActions(row, [{ label: "Dismiss", onClick: () => dismissRow(row) }]);
      updateTransfersUI();
    }
  }

  const handleToRow = new Map();
  for (const { id, name } of handles) {
    const row = renderUploadRow(name, "Queued - waiting for another download to finish…", undefined, "download", findFile(id)?.size_bytes);
    setRowActions(row, [
      {
        label: "Cancel",
        onClick: async () => {
          row._downloadCancelled = true;
          row._downloadAbort?.abort();
        },
      },
    ]);
    handleToRow.set(name, row);
  }
  updateTransfersUI();
  const items = handles.map(({ id, fileHandle, name }) => ({
    start: async () => {
      const row = handleToRow.get(name);
      if (!row) return;

      if (row._downloadCancelled) {
        dismissRow(row);
        return;
      }
      row.querySelector(".upload-status").textContent = "Downloading…";
      row.querySelector(".upload-bar-fill").style.width = "0%";
      setRowActions(row, [
        { label: "Pause", onClick: () => { row._pausing = true; row._downloadAbort?.abort(); } },
        { label: "Stop", onClick: () => { row._stopping = true; row._downloadAbort?.abort(); } },
      ]);
      try {
        await runDownloadAttempt(id, fileHandle, row, 0);
      } catch (err) {
        if (err.name === "DownloadPaused" || err.name === "DownloadStopped") {
          return;
        }
        throw err;
      }
    },
  }));
  await runConcurrentQueue(items, maxParallelTransfers);
}

async function downloadFolderInto(folderId, dirHandle) {
  const usedNamesLower = new Set();
  for (const subfolder of foldersByParent(folderId)) {
    const name = dedupeFolderName(subfolder.name, usedNamesLower);
    usedNamesLower.add(name.toLowerCase());
    const subDirHandle = await dirHandle.getDirectoryHandle(name, { create: true });
    await downloadFolderInto(subfolder.id, subDirHandle);
  }
  await downloadFilesInto(filesByFolder(folderId).map((f) => f.id), dirHandle, usedNamesLower);
}

async function downloadFolderWithProgress(folderId) {
  const folder = findFolder(folderId);
  if (!folder) return;
  if (!supportsFileSystemAccess) {
    alert(
      "Downloading a folder needs a browser feature (File System Access) this environment doesn't have - try updating WebView2, or download the files inside it individually instead."
    );
    return;
  }
  let parentDirHandle;
  try {
    parentDirHandle = await window.showDirectoryPicker({ mode: "readwrite" });
  } catch (err) {
    if (err.name === "AbortError") return;
    alert(err.message);
    return;
  }
  try {
    const rootDirHandle = await parentDirHandle.getDirectoryHandle(folder.name, { create: true });
    await downloadFolderInto(folderId, rootDirHandle);
  } catch (err) {
    alert(err.message);
  }
}

async function downloadMixedWithProgress(folderIds, fileIds) {
  let dirHandle;
  try {
    dirHandle = await window.showDirectoryPicker({ mode: "readwrite" });
  } catch (err) {
    if (err.name === "AbortError") return;
    alert(err.message);
    return;
  }
  const usedNamesLower = new Set();
  for (const folderId of folderIds) {
    const folder = findFolder(folderId);
    if (!folder) continue;
    const name = dedupeFolderName(folder.name, usedNamesLower);
    usedNamesLower.add(name.toLowerCase());
    try {
      const subDirHandle = await dirHandle.getDirectoryHandle(name, { create: true });
      await downloadFolderInto(folderId, subDirHandle);
    } catch (err) {
      alert(err.message);
    }
  }
  await downloadFilesInto(fileIds, dirHandle, usedNamesLower);
}

let trashFoldersCache = [];
let trashFilesCache = [];

function trashFolderIdSet() {
  return new Set(trashFoldersCache.map((f) => f.id));
}

function trashFoldersByParent(parentId) {
  const list =
    parentId === null
      ? trashFoldersCache.filter((f) => f.parent_id === null || !trashFolderIdSet().has(f.parent_id))
      : trashFoldersCache.filter((f) => f.parent_id === parentId);
  return list.slice().sort((a, b) => a.name.localeCompare(b.name));
}

function trashFilesByFolder(folderId) {
  const list =
    folderId === null
      ? trashFilesCache.filter((f) => f.folder_id === null || !trashFolderIdSet().has(f.folder_id))
      : trashFilesCache.filter((f) => f.folder_id === folderId);
  return list.slice().sort((a, b) => a.name.localeCompare(b.name));
}

function findTrashFolder(id) {
  return trashFoldersCache.find((f) => f.id === id) || null;
}

function trashFolderPath(folderId) {
  const deletedIds = trashFolderIdSet();
  const path = [];
  let current = folderId ? findTrashFolder(folderId) : null;
  while (current) {
    path.unshift(current);
    current = current.parent_id && deletedIds.has(current.parent_id) ? findTrashFolder(current.parent_id) : null;
  }
  return path;
}

function renderTrashBreadcrumb() {
  const path = trashFolderPath(currentTrashFolderId);
  const parts = [{ id: null, name: "Trash" }, ...path];
  trashBreadcrumbEl.innerHTML = parts
    .map((p, i) => {
      const last = i === parts.length - 1;
      const crumb = `<span class="crumb${last ? " current" : ""}" data-id="${p.id ?? ""}">${escapeHtml(p.name)}</span>`;
      return crumb + (last ? "" : `<i data-lucide="chevron-right"></i>`);
    })
    .join("");
  lucide.createIcons();
}

function openTrashFolder(id) {
  currentTrashFolderId = id;
  if (trashSearchQuery) {
    trashSearchQuery = "";
    trashSearchInputEl.value = "";
  }
  renderTrash(trashFoldersCache, trashFilesCache);
}

trashBreadcrumbEl.addEventListener("click", (e) => {
  const crumb = e.target.closest(".crumb");
  if (!crumb) return;
  openTrashFolder(crumb.dataset.id || null);
});

async function loadTrash() {
  try {
    const data = await apiFetch("/api/trash");
    renderTrash(data.folders, data.files);
    trashLoaded = true;
  } catch (err) {
    alert(err.message);
  }
}

function renderTrash(trashFolders, trashFiles) {
  trashFoldersCache = trashFolders;
  trashFilesCache = trashFiles;
  renderTrashBreadcrumb();

  let displayFolders, displayFiles;
  if (trashSearchQuery) {
    const query = trashSearchQuery.toLowerCase();
    displayFolders = trashFolders.filter((f) => f.name.toLowerCase().includes(query));
    displayFiles = trashFiles.filter((f) => f.name.toLowerCase().includes(query));
  } else {
    displayFolders = trashFoldersByParent(currentTrashFolderId);
    displayFiles = trashFilesByFolder(currentTrashFolderId);
  }
  const total = displayFolders.length + displayFiles.length;
  _trashBaseCountText =
    (trashSearchQuery
      ? `${total} match${total === 1 ? "" : "es"} for "${trashSearchQuery}"`
      : `${total} item${total === 1 ? "" : "s"}`) +
    totalSizeSuffix(displayFiles) +
    capHintSuffix(total, trashSearchQuery ? "matches" : "items");
  trashCountEl.textContent = appendSelectionSummary(_trashBaseCountText, trashSelectedFolderIds, trashSelectedFileIds, trashFilesCache, trashFoldersCache);
  mirrorRailCount(trashCountEl.textContent);

  let renderFolders = displayFolders;
  let renderFiles = displayFiles;
  if (total > RESULT_RENDER_CAP) {
    renderFolders = displayFolders.slice(0, RESULT_RENDER_CAP);
    renderFiles = displayFiles.slice(0, RESULT_RENDER_CAP - renderFolders.length);
  }
  if (viewMode === "list") renderTrashListMode(renderFolders, renderFiles);
  else renderTrashGridMode(renderFolders, renderFiles);
}

function trashEmptyMessage() {
  if (trashSearchQuery) return `No trash items match "${escapeHtml(trashSearchQuery)}".`;
  if (currentTrashFolderId === null) return "Trash is empty.";
  return "This folder is empty.";
}

function renderTrashListMode(trashFolders, trashFiles) {
  trashListEl.className = "trash-list";

  knownThumbnailIds.clear();
  if (trashFolders.length === 0 && trashFiles.length === 0) {
    trashListEl.innerHTML = `<div class="empty-hint">${trashEmptyMessage()}</div>`;
    return;
  }
  const folderRows = trashFolders.map(
    (f) => {
      const selected = trashSelectedFolderIds.has(f.id);
      return `
      <div class="trash-row trash-item${selected ? " selected" : ""}" data-type="folder" data-id="${f.id}">
        <i class="type-icon" data-lucide="folder"></i>
        <span class="trash-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</span>
        <span class="trash-actions">
          <button type="button" data-action="open">Open</button>
          <button type="button" data-action="restore">Restore</button>
          <button type="button" data-action="delete-permanent" class="danger">Delete permanently</button>
        </span>
      </div>
    `;
    }
  );
  const fileRows = trashFiles.map(
    (f) => {
      const selected = trashSelectedFileIds.has(f.id);
      return `
      <div class="trash-row trash-item${selected ? " selected" : ""}" data-type="file" data-id="${f.id}">
        ${fileThumbHtml(f, "type-icon")}
        <span class="trash-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</span>
        <span class="trash-actions">
          <button type="button" data-action="open">Open</button>
          <button type="button" data-action="restore">Restore</button>
          <button type="button" data-action="delete-permanent" class="danger">Delete permanently</button>
        </span>
      </div>
    `;
    }
  );
  trashListEl.innerHTML = folderRows.concat(fileRows).join("");
  lucide.createIcons();
}

function renderTrashGridMode(trashFolders, trashFiles) {
  trashListEl.className = "grid";

  knownThumbnailIds.clear();
  if (trashFolders.length === 0 && trashFiles.length === 0) {
    trashListEl.innerHTML = `<div class="empty-hint">${trashEmptyMessage()}</div>`;
    return;
  }
  const folderCards = trashFolders.map(
    (f) => {
      const selected = trashSelectedFolderIds.has(f.id);
      return `
      <div class="card trash-card trash-item${selected ? " selected" : ""}" data-type="folder" data-id="${f.id}">
        <i data-lucide="folder"></i>
        <div class="card-name trash-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</div>
        <div class="trash-card-actions">
          <button type="button" data-action="open" title="Open"><i data-lucide="folder-open"></i></button>
          <button type="button" data-action="restore" title="Restore"><i data-lucide="rotate-ccw"></i></button>
          <button type="button" data-action="delete-permanent" class="danger" title="Delete permanently"><i data-lucide="trash-2"></i></button>
        </div>
      </div>
    `;
    }
  );
  const fileCards = trashFiles.map(
    (f) => {
      const selected = trashSelectedFileIds.has(f.id);
      return `
      <div class="card trash-card trash-item${selected ? " selected" : ""}" data-type="file" data-id="${f.id}">
        ${fileThumbHtml(f)}
        <div class="card-name trash-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</div>
        <div class="trash-card-actions">
          <button type="button" data-action="open" title="Open"><i data-lucide="external-link"></i></button>
          <button type="button" data-action="restore" title="Restore"><i data-lucide="rotate-ccw"></i></button>
          <button type="button" data-action="delete-permanent" class="danger" title="Delete permanently"><i data-lucide="trash-2"></i></button>
        </div>
      </div>
    `;
    }
  );
  trashListEl.innerHTML = folderCards.concat(fileCards).join("");
  lucide.createIcons();
}

function mergeRestoredIntoLocalState(restoredFolders, restoredFiles) {
  restoredFolders.forEach((rf) => {
    const idx = folders.findIndex((existing) => existing.id === rf.id);
    if (idx !== -1) folders[idx] = rf;
    else folders.push(rf);
  });
  restoredFiles.forEach((rf) => {
    const idx = files.findIndex((existing) => existing.id === rf.id);
    if (idx !== -1) files[idx] = rf;
    else files.push(rf);
  });
}

trashListEl.addEventListener("click", async (e) => {

  if (trashMarqueeJustEnded) {
    trashMarqueeJustEnded = false;
    return;
  }
  const trashItem = e.target.closest(".trash-item");
  if (!trashItem) return;
  const id = trashItem.dataset.id;
  const type = trashItem.dataset.type;
  const btn = e.target.closest("button[data-action]");
  if (btn) {
    const name = trashItem.querySelector(".trash-name").textContent;
    const action = btn.dataset.action;
    try {
      if (action === "open") {
        if (type === "folder") openTrashFolder(id);
        else openFile(id);
      } else if (action === "restore") {
        if (type === "folder") {
          const result = await apiFetch(`/api/folders/${id}/restore`, { method: "POST" });
          mergeRestoredIntoLocalState(result.restored_folders, result.restored_files);
          renderAll();
        } else {
          const restored = await apiFetch(`/api/files/${id}/restore`, { method: "POST" });
          files.push(restored);
          renderGrid();
        }
        await loadTrash();
      } else if (action === "delete-permanent") {
        if (!window.confirm(`Permanently delete "${name}"? This cannot be undone.`)) return;
        if (type === "folder") {
          await apiFetch(`/api/folders/${id}/permanent`, { method: "DELETE" });
        } else {
          await apiFetch(`/api/files/${id}/permanent`, { method: "DELETE" });
          refreshStats();
        }
        await loadTrash();
      }
    } catch (err) {
      alert(err.message);
    }
    return;
  }

  if (e.ctrlKey || e.metaKey) {
    trashToggleSelect(type, id);
  } else if (e.shiftKey) {
    trashRangeSelect(type, id);
  } else {
    trashSelectOnly(type, id);
  }
});

trashListEl.addEventListener("dblclick", (e) => {
  const item = e.target.closest(".trash-item");
  if (!item || item.dataset.type !== "folder") return;
  openTrashFolder(item.dataset.id);
});

trashListEl.addEventListener("contextmenu", (e) => {
  const item = e.target.closest(".trash-item");
  if (!item) {
    if (trashSelectionActive()) {
      trashClearSelection();
      applyTrashSelectionClasses();
    }
    return;
  }
  const id = item.dataset.id;
  const type = item.dataset.type;
  const set = type === "folder" ? trashSelectedFolderIds : trashSelectedFileIds;
  if (!set.has(id)) trashSelectOnly(type, id);
  e.preventDefault();
  const menuItems = [
    {
      label: trashSelectionActive() ? `Restore selected (${trashSelectedFolderIds.size + trashSelectedFileIds.size})` : "Restore",
      action: trashBulkRestore,
    },
    {
      label: trashSelectionActive() ? `Delete selected permanently (${trashSelectedFolderIds.size + trashSelectedFileIds.size})` : "Delete permanently",
      danger: true,
      action: trashBulkDeletePermanent,
    },
  ];
  openContextMenu(menuItems, e.clientX, e.clientY);
});

trashSearchInputEl.addEventListener(
  "input",
  debounce(() => {
    trashSearchQuery = trashSearchInputEl.value.trim();
    renderTrash(trashFoldersCache, trashFilesCache);
  }, 180)
);

let trashMarquee = null;
let trashMarqueeJustEnded = false;

trashListEl.addEventListener("mousedown", (e) => {
  if (e.button !== 0) return;
  trashMarqueeJustEnded = false;

  e.preventDefault();
  trashMarquee = {
    startX: e.clientX,
    startY: e.clientY,
    mode: e.ctrlKey || e.metaKey ? "subtract" : e.shiftKey ? "add" : "replace",
    baseFolderIds: new Set(trashSelectedFolderIds),
    baseFileIds: new Set(trashSelectedFileIds),
  };
});

document.addEventListener("mousemove", (e) => {
  if (!trashMarquee) return;
  const dx = e.clientX - trashMarquee.startX;
  const dy = e.clientY - trashMarquee.startY;
  if (!trashMarquee.el) {
    if (Math.hypot(dx, dy) < 4) return;
    trashMarquee.el = document.createElement("div");
    trashMarquee.el.className = "marquee-select";
    document.body.appendChild(trashMarquee.el);
    document.body.classList.add("marquee-dragging");
  }
  const nativeSelection = window.getSelection && window.getSelection();
  if (nativeSelection && nativeSelection.rangeCount) nativeSelection.removeAllRanges();

  const x1 = Math.min(e.clientX, trashMarquee.startX);
  const y1 = Math.min(e.clientY, trashMarquee.startY);
  const x2 = Math.max(e.clientX, trashMarquee.startX);
  const y2 = Math.max(e.clientY, trashMarquee.startY);
  Object.assign(trashMarquee.el.style, {
    left: `${x1}px`,
    top: `${y1}px`,
    width: `${x2 - x1}px`,
    height: `${y2 - y1}px`,
  });

  trashSelectedFolderIds = trashMarquee.mode === "replace" ? new Set() : new Set(trashMarquee.baseFolderIds);
  trashSelectedFileIds = trashMarquee.mode === "replace" ? new Set() : new Set(trashMarquee.baseFileIds);
  const items = trashListEl.querySelectorAll(".trash-item");
  items.forEach((item) => {
    const rect = item.getBoundingClientRect();
    if (!(rect.left < x2 && rect.right > x1 && rect.top < y2 && rect.bottom > y1)) return;
    const set = item.dataset.type === "folder" ? trashSelectedFolderIds : trashSelectedFileIds;
    if (trashMarquee.mode === "subtract") set.delete(item.dataset.id);
    else set.add(item.dataset.id);
  });
  items.forEach((item) => {
    const set = item.dataset.type === "folder" ? trashSelectedFolderIds : trashSelectedFileIds;
    item.classList.toggle("selected", set.has(item.dataset.id));
  });
});

document.addEventListener("mouseup", () => {
  if (!trashMarquee) return;
  if (trashMarquee.el) {
    trashMarquee.el.remove();
    trashMarqueeJustEnded = true;
  }
  document.body.classList.remove("marquee-dragging");
  trashMarquee = null;
});

async function trashBulkRestore() {
  const folderIds = Array.from(trashSelectedFolderIds);
  const fileIds = Array.from(trashSelectedFileIds);
  if (folderIds.length === 0 && fileIds.length === 0) return;
  if (!window.confirm(`Restore ${folderIds.length + fileIds.length} item(s) from trash?`)) return;
  const errors = [];
  for (const id of folderIds) {
    try {
      const result = await apiFetch(`/api/folders/${id}/restore`, { method: "POST" });
      mergeRestoredIntoLocalState(result.restored_folders, result.restored_files);
    } catch (err) {
      errors.push(`Folder ${id}: ${err.message}`);
    }
  }
  for (const id of fileIds) {
    try {
      const restored = await apiFetch(`/api/files/${id}/restore`, { method: "POST" });
      files.push(restored);
    } catch (err) {
      errors.push(`File ${id}: ${err.message}`);
    }
  }
  renderAll();
  trashClearSelection();
  await loadTrash();
  refreshStats();
  if (errors.length) alert(`${errors.length} error(s):\n${errors.join("\n")}`);
}

async function deleteFilePermanentlyIgnoringMissing(fileId) {
  try {
    await apiFetch(`/api/files/${fileId}/permanent`, { method: "DELETE" });
  } catch (err) {
    if (/not found/i.test(err.message || "")) return null;
    return `File ${fileId}: ${err.message}`;
  }
  return null;
}

async function deleteFolderPermanentlyIgnoringMissing(folderId) {
  try {
    await apiFetch(`/api/folders/${folderId}/permanent`, { method: "DELETE" });
  } catch (err) {
    if (/not found/i.test(err.message || "")) return null;
    return `Folder ${folderId}: ${err.message}`;
  }
  return null;
}

async function trashBulkDeletePermanent() {
  const folderIds = Array.from(trashSelectedFolderIds);
  const fileIds = Array.from(trashSelectedFileIds);
  if (folderIds.length === 0 && fileIds.length === 0) return;
  if (!window.confirm(`Permanently delete ${folderIds.length + fileIds.length} item(s)? This cannot be undone.`)) return;
  const errors = [];
  for (const id of folderIds) {
    const error = await deleteFolderPermanentlyIgnoringMissing(id);
    if (error) errors.push(error);
  }
  for (const id of fileIds) {
    const error = await deleteFilePermanentlyIgnoringMissing(id);
    if (error) errors.push(error);
  }
  trashClearSelection();
  await loadTrash();
  refreshStats();
  if (errors.length) alert(`${errors.length} error(s):\n${errors.join("\n")}`);
}

async function trashDeleteAll() {
  const allFolders = [...trashFoldersCache];
  const allFiles = [...trashFilesCache];
  if (allFolders.length === 0 && allFiles.length === 0) return;
  if (!window.confirm(`Permanently delete all ${allFolders.length + allFiles.length} item(s) in trash? This cannot be undone.`)) return;
  const errors = [];
  for (const f of allFolders) {
    const error = await deleteFolderPermanentlyIgnoringMissing(f.id);
    if (error) errors.push(error);
  }
  for (const f of allFiles) {
    const error = await deleteFilePermanentlyIgnoringMissing(f.id);
    if (error) errors.push(error);
  }
  trashClearSelection();
  await loadTrash();
  refreshStats();
  if (errors.length) alert(`${errors.length} error(s):\n${errors.join("\n")}`);
}

document.getElementById("trash-delete-all-btn").addEventListener("click", trashDeleteAll);

function closeContextMenu() {
  contextMenuEl.classList.add("hide");
  contextMenuEl.innerHTML = "";
  contextMenuEl.onclick = null;
}

function openContextMenu(items, x, y) {
  contextMenuEl.innerHTML = items
    .map(
      (item, i) =>
        `<button type="button" class="context-menu-item${item.danger ? " danger" : ""}" data-index="${i}">${escapeHtml(item.label)}</button>`
    )
    .join("");
  contextMenuEl.classList.remove("hide");
  lucide.createIcons();

  const rect = contextMenuEl.getBoundingClientRect();
  const clampedX = Math.max(8, Math.min(x, window.innerWidth - rect.width - 8));
  const clampedY = Math.max(8, Math.min(y, window.innerHeight - rect.height - 8));
  contextMenuEl.style.left = `${clampedX}px`;
  contextMenuEl.style.top = `${clampedY}px`;

  contextMenuEl.onclick = (e) => {
    const btn = e.target.closest(".context-menu-item");
    if (!btn) return;
    items[Number(btn.dataset.index)].action();
    closeContextMenu();
  };
}

document.addEventListener("click", (e) => {
  if (!contextMenuEl.contains(e.target)) closeContextMenu();
});

function closeVersionHistory() {
  versionPanelEl.classList.add("hide");
  versionPanelEl.innerHTML = "";
}

async function openVersionHistory(fileId) {
  const file = findFile(fileId);
  try {
    const data = await apiFetch(`/api/files/${fileId}/versions`);
    renderVersionHistory(fileId, file, data);
  } catch (err) {
    alert(err.message);
  }
}

function renderVersionHistory(fileId, file, data) {
  versionPanelEl.dataset.fileId = fileId;

  const rows = data.versions
    .slice()
    .reverse()
    .map((v) => {
      const isCurrent = v.index === data.current_version;
      const actions = isCurrent
        ? `<span class="version-current-label">Current</span>`
        : `
          <button type="button" data-action="download" data-index="${v.index}">Download</button>
          <button type="button" data-action="restore" data-index="${v.index}">Restore</button>
        `;
      return `
        <div class="version-row">
          <div class="version-row-info">
            <div class="version-row-title">Version ${v.index + 1}</div>
            <div class="version-row-sub">${formatBytes(v.size_bytes)} &middot; ${escapeHtml(formatDate(v.uploaded_at))}</div>
          </div>
          <div class="version-row-actions">${actions}</div>
        </div>
      `;
    })
    .join("");
  versionPanelEl.innerHTML = `
    <div class="version-panel-content">
      <div class="version-panel-header">
        <span class="version-panel-title" title="${escapeHtml(file ? file.name : "")}">${escapeHtml(file ? file.name : "")}</span>
        <button type="button" class="version-panel-close" aria-label="Close">&times;</button>
      </div>
      <div class="version-list">${rows}</div>
    </div>
  `;
  versionPanelEl.classList.remove("hide");
}

async function restoreVersion(fileId, index) {
  try {
    const updated = await apiFetch(`/api/files/${fileId}/versions/${index}/restore`, { method: "POST" });
    const existing = findFile(fileId);
    if (existing) Object.assign(existing, updated);
    renderGrid();
    if (currentSmartView) renderSmartView(currentSmartView);
    refreshStats();

    const data = await apiFetch(`/api/files/${fileId}/versions`);
    renderVersionHistory(fileId, findFile(fileId), data);
  } catch (err) {
    alert(err.message);
  }
}

versionPanelEl.addEventListener("click", (e) => {
  if (e.target.closest(".version-panel-close")) {
    closeVersionHistory();
    return;
  }
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;
  const fileId = versionPanelEl.dataset.fileId;
  const index = Number(btn.dataset.index);
  if (btn.dataset.action === "download") {

    window.open(`/api/files/${fileId}/versions/${index}/content`, "_blank");
  } else if (btn.dataset.action === "restore") {
    restoreVersion(fileId, index);
  }
});

function closeProperties() {
  propertiesPanelEl.classList.add("hide");
  propertiesPanelEl.innerHTML = "";
}

function propertiesRowHtml(label, value) {
  if (value === null || value === undefined || value === "") return "";
  return `<div class="properties-row"><span class="properties-row-label">${escapeHtml(label)}</span><span class="properties-row-value">${escapeHtml(String(value))}</span></div>`;
}

function renderPropertiesPanel(title, rowsHtml) {
  propertiesPanelEl.innerHTML = `
    <div class="version-panel-content">
      <div class="version-panel-header">
        <span class="version-panel-title" title="${escapeHtml(title)}">${escapeHtml(title)}</span>
        <button type="button" class="version-panel-close" aria-label="Close">&times;</button>
      </div>
      <div class="properties-list">${rowsHtml}</div>
    </div>
  `;
  propertiesPanelEl.classList.remove("hide");
}

async function openFileProperties(fileId) {
  const file = findFile(fileId);
  renderPropertiesPanel(file ? file.name : "Properties", `<div class="properties-loading">Loading…</div>`);
  try {
    const data = await apiFetch(`/api/files/${fileId}/properties`);
    const media = data.media;

    const isVideoLike = media && media.duration_seconds !== undefined;
    const rows = [
      propertiesRowHtml("Size", formatBytes(data.size_bytes)),
      propertiesRowHtml("Type", data.mime_type),
      media && media.width ? propertiesRowHtml("Dimensions", `${media.width} × ${media.height}`) : "",
      isVideoLike ? propertiesRowHtml("Duration", formatDuration(media.duration_seconds)) : "",
      media && media.video_codec ? propertiesRowHtml(isVideoLike ? "Video codec" : "Codec", media.video_codec) : "",
      media && media.audio_codec ? propertiesRowHtml("Audio codec", media.audio_codec) : "",
      propertiesRowHtml("Versions", data.version_count),
      propertiesRowHtml("Uploaded", formatDate(data.date_uploaded)),
      propertiesRowHtml("Modified", formatDate(data.date_modified)),
    ].join("");
    renderPropertiesPanel(data.name, rows);
  } catch (err) {
    renderPropertiesPanel(file ? file.name : "Properties", `<div class="properties-loading">${escapeHtml(err.message)}</div>`);
  }
}

async function openFolderProperties(folderId) {
  const folder = findFolder(folderId);
  renderPropertiesPanel(folder ? folder.name : "Properties", `<div class="properties-loading">Loading…</div>`);
  try {
    const data = await apiFetch(`/api/folders/${folderId}/properties`);
    const rows = [
      propertiesRowHtml("Files", data.file_count),
      propertiesRowHtml("Subfolders", data.folder_count),
      propertiesRowHtml("Total size", formatBytes(data.total_size)),
      propertiesRowHtml("Created", formatDate(data.date_created)),
    ].join("");
    renderPropertiesPanel(data.name, rows);
  } catch (err) {
    renderPropertiesPanel(folder ? folder.name : "Properties", `<div class="properties-loading">${escapeHtml(err.message)}</div>`);
  }
}

propertiesPanelEl.addEventListener("click", (e) => {
  if (e.target.closest(".version-panel-close")) closeProperties();
});

const aboutPanelEl = document.getElementById("about-panel");

function openAbout() {

  const archiveEl = document.getElementById("about-archive");
  const storedEl = document.getElementById("about-stored");
  if (archiveEl) archiveEl.textContent = _aboutArchiveTitle || "Not connected yet";
  const versionEl = document.getElementById("about-version");
  if (versionEl) versionEl.textContent = _aboutVersion || "-";
  if (storedEl) {
    const totalFiles = files.length;
    const totalBytes = files.reduce((sum, f) => sum + (f.size_bytes || 0), 0);
    storedEl.textContent = totalFiles
      ? `${totalFiles.toLocaleString()} file${totalFiles === 1 ? "" : "s"} · ${formatBytes(totalBytes)}`
      : "Nothing yet";
  }
  aboutPanelEl.classList.remove("hide");
}

function closeAbout() {
  aboutPanelEl.classList.add("hide");
}

let _aboutArchiveTitle = "";

let _aboutVersion = "";

aboutPanelEl.addEventListener("click", (e) => {

  if (e.target.closest(".version-panel-close") || !e.target.closest(".version-panel-content")) {
    closeAbout();
  }
});

document.addEventListener("click", (e) => {
  if (!versionPanelEl.classList.contains("hide")) {
    const content = versionPanelEl.querySelector(".version-panel-content");
    if (content && !content.contains(e.target)) closeVersionHistory();
  }

  if (!syncCreatePanelEl.classList.contains("hide")) {
    const content = syncCreatePanelEl.querySelector(".version-panel-content");
    if (content && !content.contains(e.target) && !(movePanelEl.contains(e.target) && !movePanelEl.classList.contains("hide"))) closeSyncCreatePanel();
  }
  if (!backupPanelEl.classList.contains("hide")) {
    const content = backupPanelEl.querySelector(".version-panel-content");
    if (content && !content.contains(e.target)) closeBackupPanel();
  }
  if (!propertiesPanelEl.classList.contains("hide")) {
    const content = propertiesPanelEl.querySelector(".version-panel-content");
    if (content && !content.contains(e.target)) closeProperties();
  }
});

const SHORTCUT_ACTIONS = [
  { id: "focus-search", label: "Focus search box", defaultCombo: "ctrl+f" },
  { id: "select-all", label: "Select all / deselect all", defaultCombo: "ctrl+a" },
  { id: "open-properties", label: "Open Properties", defaultCombo: "alt+enter" },
  { id: "rename", label: "Rename selected item", defaultCombo: "f2" },
  { id: "move-up", label: "Move selection up", defaultCombo: "arrowup" },
  { id: "move-down", label: "Move selection down", defaultCombo: "arrowdown" },
  { id: "move-left", label: "Move selection left", defaultCombo: "arrowleft" },
  { id: "move-right", label: "Move selection right", defaultCombo: "arrowright" },
  { id: "extend-up", label: "Extend selection up", defaultCombo: "shift+arrowup" },
  { id: "extend-down", label: "Extend selection down", defaultCombo: "shift+arrowdown" },
  { id: "extend-left", label: "Extend selection left", defaultCombo: "shift+arrowleft" },
  { id: "extend-right", label: "Extend selection right", defaultCombo: "shift+arrowright" },
  { id: "delete", label: "Delete selected item(s)", defaultCombo: "delete" },
  { id: "open", label: "Open selected item", defaultCombo: "enter" },

  { id: "refresh", label: "Refresh current view", defaultCombo: "f5" },

  { id: "toggle-tree", label: "Expand / collapse whole folder tree", defaultCombo: "alt+a" },
];
const SHORTCUTS_STORAGE_KEY = "tvShortcutBindings";

function loadShortcutBindings() {
  let stored = {};
  try {
    stored = JSON.parse(localStorage.getItem(SHORTCUTS_STORAGE_KEY) || "{}");
  } catch {
    stored = {};
  }
  const bindings = {};
  for (const action of SHORTCUT_ACTIONS) bindings[action.id] = stored[action.id] || action.defaultCombo;
  return bindings;
}

let shortcutBindings = loadShortcutBindings();

let _comboToAction = {};
function _rebuildComboLookup() {
  _comboToAction = {};
  for (const [actionId, combo] of Object.entries(shortcutBindings)) _comboToAction[combo] = actionId;
}
_rebuildComboLookup();

function saveShortcutBindings() {
  localStorage.setItem(SHORTCUTS_STORAGE_KEY, JSON.stringify(shortcutBindings));
  _rebuildComboLookup();
}

function comboFromEvent(e) {
  if (["Control", "Alt", "Shift", "Meta"].includes(e.key)) return null;
  const parts = [];
  if (e.ctrlKey || e.metaKey) parts.push("ctrl");
  if (e.altKey) parts.push("alt");
  if (e.shiftKey) parts.push("shift");
  let key = e.key.toLowerCase();
  if (key === " ") key = "space";
  parts.push(key);
  return parts.join("+");
}

function formatComboForDisplay(combo) {
  const SYMBOLS = { arrowup: "↑", arrowdown: "↓", arrowleft: "←", arrowright: "→", delete: "Del" };
  return combo
    .split("+")
    .map((p) => {
      if (p === "ctrl") return "Ctrl";
      if (p === "alt") return "Alt";
      if (p === "shift") return "Shift";
      if (SYMBOLS[p]) return SYMBOLS[p];
      return p.length === 1 ? p.toUpperCase() : p[0].toUpperCase() + p.slice(1);
    })
    .join(" + ");
}

let _recordingActionId = null;

function renderShortcutsTab() {
  const listEl = document.getElementById("shortcuts-list");
  if (!listEl) return;
  listEl.innerHTML = SHORTCUT_ACTIONS.map((action) => {
    const combo = shortcutBindings[action.id];
    const recording = _recordingActionId === action.id;
    return `
      <div class="shortcut-row" data-action-id="${action.id}">
        <span class="shortcut-row-label">${escapeHtml(action.label)}</span>
        <div class="shortcut-row-controls">
          <span class="shortcut-combo${recording ? " recording" : ""}">${recording ? "Press keys…" : escapeHtml(formatComboForDisplay(combo))}</span>
          <button type="button" data-rebind="${action.id}">${recording ? "Cancel" : "Change"}</button>
          <button type="button" data-reset="${action.id}">Reset</button>
        </div>
      </div>
    `;
  }).join("");
}

document.getElementById("shortcuts-list").addEventListener("click", (e) => {
  const rebindBtn = e.target.closest("button[data-rebind]");
  if (rebindBtn) {
    _recordingActionId = _recordingActionId === rebindBtn.dataset.rebind ? null : rebindBtn.dataset.rebind;
    renderShortcutsTab();
    return;
  }
  const resetBtn = e.target.closest("button[data-reset]");
  if (resetBtn) {
    const action = SHORTCUT_ACTIONS.find((a) => a.id === resetBtn.dataset.reset);
    if (action) {
      shortcutBindings[action.id] = action.defaultCombo;
      saveShortcutBindings();
      renderShortcutsTab();
    }
  }
});

document.getElementById("reset-shortcuts-btn").addEventListener("click", () => {
  for (const action of SHORTCUT_ACTIONS) shortcutBindings[action.id] = action.defaultCombo;
  saveShortcutBindings();
  renderShortcutsTab();
});

document.addEventListener(
  "keydown",
  (e) => {
    if (!_recordingActionId) return;
    e.preventDefault();
    e.stopPropagation();
    if (e.key === "Escape") {
      _recordingActionId = null;
      renderShortcutsTab();
      return;
    }
    const combo = comboFromEvent(e);
    if (!combo) return;
    const conflict = SHORTCUT_ACTIONS.find((a) => a.id !== _recordingActionId && shortcutBindings[a.id] === combo);
    if (conflict) {
      alert(`"${formatComboForDisplay(combo)}" is already used for "${conflict.label}". Choose a different combination.`);
      return;
    }
    shortcutBindings[_recordingActionId] = combo;
    saveShortcutBindings();
    _recordingActionId = null;
    renderShortcutsTab();
  },
  true,
);

function activeViewKind() {
  if (!document.getElementById("view-explorer").classList.contains("hide")) return "explorer";
  if (!document.getElementById("view-smart").classList.contains("hide")) return "smart";
  if (!document.getElementById("view-trash").classList.contains("hide")) return "trash";
  return null;
}

function activeSearchInput() {
  const kind = activeViewKind();
  if (kind === "explorer") return searchInputEl;
  if (kind === "smart") return smartSearchInputEl;
  if (kind === "trash") return trashSearchInputEl;
  return null;
}

function toggleSelectAllActiveView() {
  const kind = activeViewKind();
  if (kind === "explorer") {
    const items = currentGridItems();
    const allSelected = items.length > 0 && items.every((it) => (it.type === "folder" ? selectedFolderIds : selectedFileIds).has(it.id));
    if (allSelected) {
      clearSelection();
    } else {
      selectedFolderIds = new Set(items.filter((it) => it.type === "folder").map((it) => it.id));
      selectedFileIds = new Set(items.filter((it) => it.type === "file").map((it) => it.id));
    }
    applySelectionClasses();
  } else if (kind === "smart") {
    const items = currentSmartItems();
    const allSelected = items.length > 0 && items.every((it) => smartSelectedFileIds.has(it.id));
    smartSelectedFileIds = allSelected ? new Set() : new Set(items.map((it) => it.id));
    applySmartSelectionClasses();
  } else if (kind === "trash") {
    const items = currentTrashItems();
    const allSelected = items.length > 0 && items.every((it) => (it.type === "folder" ? trashSelectedFolderIds : trashSelectedFileIds).has(it.id));
    if (allSelected) {
      trashClearSelection();
    } else {
      trashSelectedFolderIds = new Set(items.filter((it) => it.type === "folder").map((it) => it.id));
      trashSelectedFileIds = new Set(items.filter((it) => it.type === "file").map((it) => it.id));
    }
    applyTrashSelectionClasses();
  }
}

function openPropertiesForActiveSelection() {
  const kind = activeViewKind();
  if (kind === "explorer") {
    if (selectedFolderIds.size === 1 && selectedFileIds.size === 0) openFolderProperties(Array.from(selectedFolderIds)[0]);
    else if (selectedFileIds.size === 1 && selectedFolderIds.size === 0) openFileProperties(Array.from(selectedFileIds)[0]);
  } else if (kind === "smart" && smartSelectedFileIds.size === 1) {
    openFileProperties(Array.from(smartSelectedFileIds)[0]);
  }
}

function renameActiveSelection() {
  const kind = activeViewKind();
  if (kind === "explorer") {
    if (selectedFolderIds.size === 1 && selectedFileIds.size === 0) renameFolder(Array.from(selectedFolderIds)[0]);
    else if (selectedFileIds.size === 1 && selectedFolderIds.size === 0) renameFile(Array.from(selectedFileIds)[0]);
  } else if (kind === "smart" && smartSelectedFileIds.size === 1) {
    renameFile(Array.from(smartSelectedFileIds)[0]);
  }
}

function computeColumns(containerEl, selector) {
  const cards = containerEl.querySelectorAll(selector);
  if (!cards.length) return 1;
  const firstTop = cards[0].offsetTop;
  let count = 0;
  for (const c of cards) {
    if (c.offsetTop !== firstTop) break;
    count++;
  }
  return Math.max(1, count);
}

function _moveFocusCore({ items, container, selector, focusIndex, anchorIndex, selectOnlyFn, rangeFn, direction, extend }) {
  if (!items.length) return focusIndex;
  const columns = computeColumns(container, selector);
  const base = focusIndex !== null && focusIndex < items.length ? focusIndex : anchorIndex !== null ? anchorIndex : 0;
  let delta = 0;
  if (direction === "left") delta = -1;
  else if (direction === "right") delta = 1;
  else if (direction === "up") delta = -columns;
  else if (direction === "down") delta = columns;
  const newIndex = Math.max(0, Math.min(items.length - 1, base + delta));
  const target = items[newIndex];
  if (extend) rangeFn(target);
  else selectOnlyFn(target);
  const card = container.querySelectorAll(selector)[newIndex];
  if (card) card.scrollIntoView({ block: "nearest" });
  return newIndex;
}

let _explorerFocusIndex = null;
let _smartFocusIndex = null;
let _trashFocusIndex = null;

function moveActiveSelection(direction, extend) {
  const kind = activeViewKind();
  if (kind === "explorer") {
    _explorerFocusIndex = _moveFocusCore({
      items: currentGridItems(), container: gridEl, selector: ".folder-card, .file-card",
      focusIndex: _explorerFocusIndex, anchorIndex: lastClickedIndex,
      selectOnlyFn: (it) => selectOnly(it.type, it.id), rangeFn: (it) => rangeSelect(it.type, it.id),
      direction, extend,
    });
  } else if (kind === "smart") {
    _smartFocusIndex = _moveFocusCore({
      items: currentSmartItems(), container: smartGridEl, selector: ".file-card",
      focusIndex: _smartFocusIndex, anchorIndex: smartLastClickedIndex,
      selectOnlyFn: (it) => smartSelectOnly(it.id), rangeFn: (it) => smartRangeSelect(it.id),
      direction, extend,
    });
  } else if (kind === "trash") {
    _trashFocusIndex = _moveFocusCore({
      items: currentTrashItems(), container: trashListEl, selector: ".trash-item",
      focusIndex: _trashFocusIndex, anchorIndex: trashLastClickedIndex,
      selectOnlyFn: (it) => trashSelectOnly(it.type, it.id), rangeFn: (it) => trashRangeSelect(it.type, it.id),
      direction, extend,
    });
  }
}

document.addEventListener("keydown", (e) => {

  if (e.key === "F1") {
    e.preventDefault();
    if (aboutPanelEl.classList.contains("hide")) openAbout();
    else closeAbout();
    return;
  }
  if (e.key === "Escape") {

    if (!aboutPanelEl.classList.contains("hide")) {
      closeAbout();
      return;
    }
    if (!contextMenuEl.classList.contains("hide")) {
      closeContextMenu();
      return;
    }
    if (!versionPanelEl.classList.contains("hide")) {
      closeVersionHistory();
      return;
    }
    if (!syncCreatePanelEl.classList.contains("hide")) {
      closeSyncCreatePanel();
      return;
    }
    if (!movePanelEl.classList.contains("hide")) {
      closeMovePanel();
      return;
    }
    if (!backupPanelEl.classList.contains("hide")) {
      closeBackupPanel();
      return;
    }
    if (!propertiesPanelEl.classList.contains("hide")) {
      closeProperties();
      return;
    }
    if (!imageViewerEl.classList.contains("hide")) {
      closeImageViewer();
      return;
    }
    if (!videoViewerEl.classList.contains("hide")) {
      closeVideoViewer();
      return;
    }
    if (!audioViewerEl.classList.contains("hide")) {
      closeAudioViewer();
      return;
    }
    if (selectionActive()) {
      clearSelection();
      applySelectionClasses();
    }
    if (trashSelectionActive()) {
      trashClearSelection();
      applyTrashSelectionClasses();
    }
    if (smartSelectionActive()) {
      smartClearSelection();
      applySmartSelectionClasses();
    }
    return;
  }

  if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && !imageViewerEl.classList.contains("hide")) {
    imageViewerStep(e.key === "ArrowLeft" ? -1 : 1);
    return;
  }

  const combo = comboFromEvent(e);
  if (!combo) return;
  const actionId = _comboToAction[combo];
  if (!actionId) return;
  const activeTag = document.activeElement && document.activeElement.tagName;
  const typing = activeTag === "INPUT" || activeTag === "TEXTAREA";

  if (actionId === "focus-search") {
    const input = activeSearchInput();
    if (!input) return;
    e.preventDefault();
    input.focus();
    input.select();
    return;
  }

  if (actionId === "refresh") {
    e.preventDefault();
    refreshActiveView();
    return;
  }
  if (actionId === "toggle-tree") {

    e.preventDefault();
    toggleTreeExpandAll();
    return;
  }

  if (typing) return;

  if (actionId === "select-all") {
    e.preventDefault();
    toggleSelectAllActiveView();
    return;
  }
  if (actionId === "open-properties") {
    e.preventDefault();
    openPropertiesForActiveSelection();
    return;
  }
  if (actionId === "rename") {
    e.preventDefault();
    renameActiveSelection();
    return;
  }
  if (actionId.startsWith("move-")) {
    e.preventDefault();
    moveActiveSelection(actionId.slice(5), false);
    return;
  }
  if (actionId.startsWith("extend-")) {
    e.preventDefault();
    moveActiveSelection(actionId.slice(7), true);
    return;
  }
  if (actionId === "delete") {
    if (!document.getElementById("view-explorer").classList.contains("hide") && selectionActive()) {
      bulkDelete();
      return;
    }
    if (!document.getElementById("view-trash").classList.contains("hide") && trashSelectionActive()) {
      trashBulkDeletePermanent();
      return;
    }

    if (!document.getElementById("view-smart").classList.contains("hide") && smartSelectionActive()) {
      smartBulkDelete();
      return;
    }
    return;
  }
  if (actionId === "open") {
    if (!document.getElementById("view-explorer").classList.contains("hide")) {

      if (selectedFolderIds.size === 1 && selectedFileIds.size === 0) {
        openFolder(Array.from(selectedFolderIds)[0]);
      } else if (selectedFileIds.size === 1 && selectedFolderIds.size === 0) {
        openFile(Array.from(selectedFileIds)[0]);
      }
      return;
    }

    if (!document.getElementById("view-smart").classList.contains("hide") && smartSelectedFileIds.size === 1) {
      openFile(Array.from(smartSelectedFileIds)[0]);
    }
  }
});

function folderMoveExclusions(folderId) {
  const folder = findFolder(folderId);
  return {
    excludedIds: new Set([folderId, ...collectDescendantIds(folderId)]),
    currentParentId: folder ? folder.parent_id : undefined,
  };
}

function fileMoveExclusions(fileId) {
  const file = findFile(fileId);
  return { excludedIds: new Set(), currentParentId: file ? file.folder_id : undefined };
}

function bulkMoveExclusions() {
  const excludedIds = new Set();
  selectedFolderIds.forEach((id) => {
    excludedIds.add(id);
    collectDescendantIds(id).forEach((d) => excludedIds.add(d));
  });
  return { excludedIds, currentParentId: currentFolderId };
}

let movePanelContext = null;
let movePanelExpandedIds = new Set();

let movePanelSelectedId;
let movePanelTreeOpen = false;

function openMovePanel({ title, excludedIds, currentParentId, onConfirm }) {
  movePanelContext = { title, excludedIds, currentParentId, onConfirm };
  movePanelExpandedIds = new Set();
  movePanelSelectedId = undefined;
  movePanelTreeOpen = false;
  renderMovePanel();
  movePanelEl.classList.remove("hide");
}

function closeMovePanel() {
  movePanelEl.classList.add("hide");
  movePanelEl.innerHTML = "";
  movePanelContext = null;
}

function movePanelTargetLabel() {
  if (movePanelSelectedId === undefined) return "Select a folder";
  if (movePanelSelectedId === null) return "Root";
  const f = findFolder(movePanelSelectedId);
  return f ? f.name : "Root";
}

function renderMoveTreeLevel(parentId, depth) {
  return foldersByParent(parentId)
    .map((f) => {
      if (movePanelContext.excludedIds.has(f.id)) return "";
      const hasChildren = foldersByParent(f.id).length > 0;
      const expanded = movePanelExpandedIds.has(f.id);
      const selected = movePanelSelectedId === f.id;
      const chevron = hasChildren
        ? `<i class="movetree-chevron${expanded ? " expanded" : ""}" data-lucide="chevron-right"></i>`
        : `<span class="movetree-chevron-spacer"></span>`;
      return `
        <div class="movetree-item${selected ? " active" : ""}" data-id="${f.id}" style="--movetree-depth:${depth}">
          ${chevron}<i data-lucide="folder"></i><span>${escapeHtml(f.name)}</span>
        </div>
        ${hasChildren && expanded ? renderMoveTreeLevel(f.id, depth + 1) : ""}
      `;
    })
    .join("");
}

function renderMovePanel() {
  if (!movePanelContext) return;
  const homeExcluded = movePanelContext.currentParentId === null;
  const homeSelected = movePanelSelectedId === null;
  const homeRow = homeExcluded
    ? ""
    : `
      <div class="movetree-item movetree-home${homeSelected ? " active" : ""}" data-id="">
        <span class="movetree-chevron-spacer"></span><i data-lucide="home"></i><span>Root</span>
      </div>
    `;
  movePanelEl.innerHTML = `
    <div class="move-panel-content">
      <div class="version-panel-header">
        <span class="version-panel-title">${escapeHtml(movePanelContext.title)}</span>
        <button type="button" class="version-panel-close" aria-label="Close">&times;</button>
      </div>
      <div class="move-panel-body">
        <label class="move-panel-label">Move to</label>
        <button type="button" class="move-panel-field${movePanelTreeOpen ? " open" : ""}" id="move-panel-field">
          <span>${escapeHtml(movePanelTargetLabel())}</span><i data-lucide="chevron-down"></i>
        </button>
        <div class="movetree${movePanelTreeOpen ? "" : " hide"}">${homeRow}${renderMoveTreeLevel(null, 1)}</div>
      </div>
      <div class="move-panel-footer">
        <button type="button" class="move-panel-btn" id="move-panel-cancel-btn">Cancel</button>
        <button type="button" class="move-panel-btn move-panel-btn-primary" id="move-panel-ok-btn"${movePanelSelectedId === undefined ? " disabled" : ""}>OK</button>
      </div>
    </div>
  `;
  lucide.createIcons();
}

movePanelEl.addEventListener("click", (e) => {
  if (e.target === movePanelEl || e.target.closest(".version-panel-close") || e.target.closest("#move-panel-cancel-btn")) {
    closeMovePanel();
    return;
  }
  if (e.target.closest("#move-panel-ok-btn")) {
    if (!movePanelContext || movePanelSelectedId === undefined) return;
    const { onConfirm } = movePanelContext;
    const targetId = movePanelSelectedId;
    closeMovePanel();
    onConfirm(targetId);
    return;
  }
  if (e.target.closest("#move-panel-field")) {
    movePanelTreeOpen = !movePanelTreeOpen;
    renderMovePanel();
    return;
  }
  const chevron = e.target.closest(".movetree-chevron");
  if (chevron) {
    e.stopPropagation();
    const item = chevron.closest(".movetree-item");
    if (item && item.dataset.id) {
      if (movePanelExpandedIds.has(item.dataset.id)) movePanelExpandedIds.delete(item.dataset.id);
      else movePanelExpandedIds.add(item.dataset.id);
      renderMovePanel();
    }
    return;
  }
  const item = e.target.closest(".movetree-item");
  if (item) {
    e.stopPropagation();
    movePanelSelectedId = item.dataset.id || null;
    movePanelTreeOpen = false;
    renderMovePanel();
  }
});

let _fpSel = null;
let _fpExpanded = new Set();
let _fpOnConfirm = null;

function _fpTreeHtml(parentId, depth) {
  return foldersByParent(parentId).map((f) => {
    const hasChildren = foldersByParent(f.id).length > 0;
    const expanded = _fpExpanded.has(f.id);
    const selected = _fpSel === f.id;
    const chevron = hasChildren
      ? `<i class="fp-ch${expanded ? " expanded" : ""}" data-lucide="chevron-right"></i>`
      : `<span style="display:inline-block;width:14px;height:14px;flex-shrink:0"></span>`;
    return `<div class="fp-item${selected ? " active" : ""}" data-fp-sel="${f.id}" style="--movetree-depth:${depth}">${chevron}<i data-lucide="folder"></i><span>${escapeHtml(f.name)}</span></div>${hasChildren && expanded ? _fpTreeHtml(f.id, depth + 1) : ""}`;
  }).join("");
}

function _renderFp() {
  const label = _fpSel === null ? "Root" : _fpSel === undefined ? "Select a folder" : (folders.find((f) => f.id === _fpSel)?.name || "Root");
  movePanelEl.innerHTML = `<div class="move-panel-content"><div class="version-panel-header"><span class="version-panel-title">Select destination folder</span><span class="fp-x" style="cursor:pointer;font-size:1.2rem">&times;</span></div><div class="move-panel-body"><label class="move-panel-label">Folder</label><div class="movetree" style="max-height:300px"><div class="fp-item${_fpSel === null ? " active" : ""}" data-fp-sel=""><i data-lucide="home"></i><span>Root</span></div>${_fpTreeHtml(null, 1)}</div></div><div class="move-panel-footer"><button type="button" class="move-panel-btn" id="fp-cancel">Cancel</button><button type="button" class="move-panel-btn move-panel-btn-primary" id="fp-ok"${_fpSel === undefined ? " disabled" : ""}>OK</button></div></div>`;
  lucide.createIcons();
}

function openFolderPicker(onConfirm) {
  _fpSel = undefined; _fpExpanded = new Set(); _fpOnConfirm = onConfirm;
  _renderFp();
  movePanelEl.classList.remove("hide");
}

function closeFolderPicker() {
  movePanelEl.classList.add("hide"); movePanelEl.innerHTML = "";
  _fpOnConfirm = null; _fpSel = null; _fpExpanded = new Set();
}

movePanelEl.addEventListener("click", function _fpHandler(e) {
  if (e.target.classList.contains("fp-x") || e.target.closest("#fp-cancel")) {
    closeFolderPicker(); e.stopPropagation(); return;
  }
  if (e.target.closest("#fp-ok") && _fpSel !== undefined) {
    e.stopPropagation();
    const id = _fpSel; const cb = _fpOnConfirm;
    closeFolderPicker();
    if (cb) cb(id);
    return;
  }
  const xp = e.target.closest(".fp-ch");
  if (xp) { e.stopPropagation(); const item = xp.closest("[data-fp-sel]"); if (item && item.dataset.fpSel) { const fid = item.dataset.fpSel; if (_fpExpanded.has(fid)) _fpExpanded.delete(fid); else _fpExpanded.add(fid); _renderFp(); } return; }
  const sel = e.target.closest("[data-fp-sel]");
  if (sel) { e.stopPropagation(); _fpSel = sel.dataset.fpSel || null; _renderFp(); return; }
});

let imageViewerIds = [];
let imageViewerIndex = -1;
let imageViewerZoom = 1;
let imageViewerPan = { x: 0, y: 0 };
let imageViewerFitRatio = 1;
const IMAGE_VIEWER_MIN_ZOOM = 0.1;
const IMAGE_VIEWER_MAX_ZOOM = 10;

function currentNavigableImageIds() {
  if (currentSmartView) {
    const config = SMART_VIEWS[currentSmartView];

    let matches = files.filter(config.filter).sort(_sortComparator());
    if (smartSearchQuery) {
      const query = smartSearchQuery.toLowerCase();
      matches = matches.filter((f) => f.name.toLowerCase().includes(query));
    }
    return matches.filter((f) => f.mime_type && f.mime_type.startsWith("image/")).map((f) => f.id);
  }
  return currentGridItems()
    .filter((it) => it.type === "file")
    .map((it) => findFile(it.id))
    .filter((f) => f && f.mime_type && f.mime_type.startsWith("image/"))
    .map((f) => f.id);
}

function openImageViewer(id) {

  const inLiveList = findFile(id) && currentNavigableImageIds().includes(id);
  imageViewerIds = inLiveList ? currentNavigableImageIds() : [id];
  imageViewerIndex = imageViewerIds.indexOf(id);
  if (imageViewerIndex === -1) imageViewerIndex = 0;
  imageViewerEl.classList.remove("hide");
  updateImageViewerNavButtons();
  showImageAt(imageViewerIndex);
}

function closeImageViewer() {
  imageViewerEl.classList.add("hide");
  imageViewerImgEl.removeAttribute("src");
  imageViewerIds = [];
  imageViewerIndex = -1;
}

function showImageAt(index) {
  imageViewerIndex = index;
  const id = imageViewerIds[imageViewerIndex];
  const file = findFile(id);
  imageViewerZoom = 1;
  imageViewerPan = { x: 0, y: 0 };
  imageViewerFitRatio = 1;
  imageViewerImgEl.classList.add("hide");
  imageViewerErrorEl.classList.add("hide");
  imageViewerLoadingEl.classList.remove("hide");
  imageViewerFilenameEl.textContent = file
    ? imageViewerIds.length > 1
      ? `${file.name} (${imageViewerIndex + 1} / ${imageViewerIds.length})`
      : file.name
    : "";
  imageViewerZoomEl.textContent = "";
  imageViewerImgEl.src = `/api/files/${id}/content`;
  if (!file) return;
  markFileOpened(id);
}

imageViewerImgEl.addEventListener("load", () => {
  imageViewerLoadingEl.classList.add("hide");
  imageViewerImgEl.classList.remove("hide");
  imageViewerFitRatio = imageViewerImgEl.naturalWidth ? imageViewerImgEl.clientWidth / imageViewerImgEl.naturalWidth : 1;
  applyImageTransform();
});
imageViewerImgEl.addEventListener("error", () => {
  imageViewerLoadingEl.classList.add("hide");
  imageViewerErrorEl.classList.remove("hide");
});

function updateImageViewerNavButtons() {
  const multiple = imageViewerIds.length > 1;
  imageViewerPrevBtnEl.classList.toggle("hide", !multiple);
  imageViewerNextBtnEl.classList.toggle("hide", !multiple);
}

function imageViewerStep(delta) {
  if (imageViewerIds.length < 2) return;
  const next = (imageViewerIndex + delta + imageViewerIds.length) % imageViewerIds.length;
  showImageAt(next);
}

function applyImageTransform(animated) {
  imageViewerImgEl.style.transition = animated ? "transform 200ms var(--ease-quint)" : "none";
  imageViewerImgEl.style.transform = `translate(${imageViewerPan.x}px, ${imageViewerPan.y}px) scale(${imageViewerZoom})`;
  imageViewerZoomEl.textContent = `${Math.round(imageViewerFitRatio * imageViewerZoom * 100)}%`;
}

function zoomImageAt(clientX, clientY, factor) {
  const rect = imageViewerStageEl.getBoundingClientRect();
  const cx = clientX - (rect.left + rect.width / 2);
  const cy = clientY - (rect.top + rect.height / 2);
  const oldZoom = imageViewerZoom;
  const newZoom = Math.min(IMAGE_VIEWER_MAX_ZOOM, Math.max(IMAGE_VIEWER_MIN_ZOOM, oldZoom * factor));
  const ratio = newZoom / oldZoom;
  imageViewerPan.x = cx - (cx - imageViewerPan.x) * ratio;
  imageViewerPan.y = cy - (cy - imageViewerPan.y) * ratio;
  imageViewerZoom = newZoom;
}

imageViewerStageEl.addEventListener(
  "wheel",
  (e) => {
    if (!imageViewerImgEl.naturalWidth) return;
    e.preventDefault();
    zoomImageAt(e.clientX, e.clientY, e.deltaY < 0 ? 1.15 : 1 / 1.15);
    applyImageTransform();
  },
  { passive: false }
);

imageViewerStageEl.addEventListener("dblclick", (e) => {
  if (e.target.closest(".media-viewer-nav") || !imageViewerImgEl.naturalWidth) return;
  const atFit = Math.abs(imageViewerZoom - 1) < 0.01;
  if (atFit) {
    zoomImageAt(e.clientX, e.clientY, 1 / imageViewerFitRatio / imageViewerZoom);
  } else {
    imageViewerZoom = 1;
    imageViewerPan = { x: 0, y: 0 };
  }
  applyImageTransform(true);
});

let imgDragActive = false;
let imgDragStart = null;
let imgDragMoved = false;

imageViewerImgEl.addEventListener("mousedown", (e) => {
  if (e.button !== 0) return;
  imgDragActive = true;
  imgDragMoved = false;
  imgDragStart = { x: e.clientX, y: e.clientY, panX: imageViewerPan.x, panY: imageViewerPan.y };
  e.preventDefault();
});

document.addEventListener("mousemove", (e) => {
  if (!imgDragActive) return;
  if (!(e.buttons & 1)) {

    imgDragActive = false;
    return;
  }
  const dx = e.clientX - imgDragStart.x;
  const dy = e.clientY - imgDragStart.y;
  if (Math.abs(dx) > 3 || Math.abs(dy) > 3) imgDragMoved = true;
  if (imgDragMoved) {
    imageViewerPan = { x: imgDragStart.panX + dx, y: imgDragStart.panY + dy };
    applyImageTransform();
  }
});

document.addEventListener("mouseup", () => {
  imgDragActive = false;
});

imageViewerStageEl.addEventListener("click", (e) => {
  if (imgDragMoved) {
    imgDragMoved = false;
    return;
  }
  if (e.target === imageViewerStageEl) closeImageViewer();
});

imageViewerPrevBtnEl.addEventListener("click", () => imageViewerStep(-1));
imageViewerNextBtnEl.addEventListener("click", () => imageViewerStep(1));
imageViewerCloseBtnEl.addEventListener("click", () => closeImageViewer());

let videoViewerIds = [];
let videoViewerIndex = -1;

function currentNavigableVideoIds() {
  if (currentSmartView) {
    const config = SMART_VIEWS[currentSmartView];

    let matches = files.filter(config.filter).sort(_sortComparator());
    if (smartSearchQuery) {
      const query = smartSearchQuery.toLowerCase();
      matches = matches.filter((f) => f.name.toLowerCase().includes(query));
    }
    return matches.filter((f) => f.mime_type && f.mime_type.startsWith("video/")).map((f) => f.id);
  }
  return currentGridItems()
    .filter((it) => it.type === "file")
    .map((it) => findFile(it.id))
    .filter((f) => f && f.mime_type && f.mime_type.startsWith("video/"))
    .map((f) => f.id);
}

function openVideoViewer(id) {

  const inLiveList = findFile(id) && currentNavigableVideoIds().includes(id);
  videoViewerIds = inLiveList ? currentNavigableVideoIds() : [id];
  videoViewerIndex = videoViewerIds.indexOf(id);
  if (videoViewerIndex === -1) videoViewerIndex = 0;
  videoViewerEl.classList.remove("hide");

  videoViewerExternalBtnEl.classList.toggle("hide", !externalVideoPlayerEnabled);
  updateVideoViewerNavButtons();
  showVideoAt(videoViewerIndex);
}

function closeVideoViewer() {
  videoViewerVideoEl.pause();
  videoViewerEl.classList.add("hide");
  videoViewerVideoEl.removeAttribute("src");
  videoViewerVideoEl.load();
  videoViewerIds = [];
  videoViewerIndex = -1;
}

function showVideoAt(index) {
  videoViewerIndex = index;
  const id = videoViewerIds[videoViewerIndex];
  const file = findFile(id);
  videoViewerErrorEl.classList.add("hide");
  videoViewerVideoEl.classList.remove("hide");
  videoViewerFilenameEl.textContent = file
    ? videoViewerIds.length > 1
      ? `${file.name} (${videoViewerIndex + 1} / ${videoViewerIds.length})`
      : file.name
    : "";
  videoViewerVideoEl.src = `/api/files/${id}/content`;

  videoViewerVideoEl.playbackRate = videoViewerPlaybackRate;
  videoViewerSpeedSelectEl.value = String(videoViewerPlaybackRate);
  videoViewerVideoEl.play().catch(() => {});
  if (!file) return;
  markFileOpened(id);
}

videoViewerVideoEl.addEventListener("error", () => {
  videoViewerVideoEl.classList.add("hide");
  videoViewerErrorEl.classList.remove("hide");
});

function updateVideoViewerNavButtons() {
  const multiple = videoViewerIds.length > 1;
  videoViewerPrevBtnEl.classList.toggle("hide", !multiple);
  videoViewerNextBtnEl.classList.toggle("hide", !multiple);
}

function videoViewerStep(delta) {
  if (videoViewerIds.length < 2) return;
  const next = (videoViewerIndex + delta + videoViewerIds.length) % videoViewerIds.length;
  showVideoAt(next);
}

videoViewerStageEl.addEventListener("click", (e) => {
  if (e.target === videoViewerStageEl) closeVideoViewer();
});

videoViewerPrevBtnEl.addEventListener("click", () => videoViewerStep(-1));
videoViewerNextBtnEl.addEventListener("click", () => videoViewerStep(1));
videoViewerCloseBtnEl.addEventListener("click", () => closeVideoViewer());
videoViewerExternalBtnEl.addEventListener("click", () => {
  const id = videoViewerIds[videoViewerIndex];
  closeVideoViewer();
  if (id) playExternal(id);
});

const VIDEO_VIEWER_SKIP_SECONDS = 10;
let videoViewerPlaybackRate = 1;

function videoViewerSkip(deltaSeconds) {
  const v = videoViewerVideoEl;
  if (!v.duration) return;
  v.currentTime = Math.min(Math.max(0, v.currentTime + deltaSeconds), v.duration);
}

videoViewerSkipBackBtnEl.addEventListener("click", () => videoViewerSkip(-VIDEO_VIEWER_SKIP_SECONDS));
videoViewerSkipFwdBtnEl.addEventListener("click", () => videoViewerSkip(VIDEO_VIEWER_SKIP_SECONDS));
videoViewerSpeedSelectEl.addEventListener("change", () => {
  videoViewerPlaybackRate = Number(videoViewerSpeedSelectEl.value);
  videoViewerVideoEl.playbackRate = videoViewerPlaybackRate;
});

videoViewerSetThumbBtnEl.addEventListener("click", async () => {
  const id = videoViewerIds[videoViewerIndex];
  if (!id) return;
  const seconds = videoViewerVideoEl.currentTime || 0;
  const originalLabel = videoViewerSetThumbBtnEl.textContent;
  videoViewerSetThumbBtnEl.disabled = true;
  videoViewerSetThumbBtnEl.textContent = "Saving...";
  try {
    const res = await fetch(`/api/files/${id}/thumbnail/from-frame`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ seconds }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Couldn't set thumbnail.");

    const thumbImg = document.querySelector(`.card.file-card[data-id="${id}"] .card-thumb`);
    if (thumbImg) thumbImg.src = `/api/files/${id}/thumbnail?t=${Date.now()}`;
    videoViewerSetThumbBtnEl.textContent = "Saved!";
  } catch (err) {
    videoViewerSetThumbBtnEl.textContent = originalLabel;
    videoViewerSetThumbBtnEl.disabled = false;
    alert(err.message);
    return;
  }
  setTimeout(() => {
    videoViewerSetThumbBtnEl.textContent = originalLabel;
    videoViewerSetThumbBtnEl.disabled = false;
  }, 1200);
});

let audioViewerIds = [];
let audioViewerIndex = -1;

function currentNavigableAudioIds() {
  if (currentSmartView) {
    const config = SMART_VIEWS[currentSmartView];

    let matches = files.filter(config.filter).sort(_sortComparator());
    if (smartSearchQuery) {
      const query = smartSearchQuery.toLowerCase();
      matches = matches.filter((f) => f.name.toLowerCase().includes(query));
    }
    return matches.filter((f) => f.mime_type && f.mime_type.startsWith("audio/")).map((f) => f.id);
  }
  return currentGridItems()
    .filter((it) => it.type === "file")
    .map((it) => findFile(it.id))
    .filter((f) => f && f.mime_type && f.mime_type.startsWith("audio/"))
    .map((f) => f.id);
}

function openAudioViewer(id) {
  const inLiveList = findFile(id) && currentNavigableAudioIds().includes(id);
  audioViewerIds = inLiveList ? currentNavigableAudioIds() : [id];
  audioViewerIndex = audioViewerIds.indexOf(id);
  if (audioViewerIndex === -1) audioViewerIndex = 0;
  audioViewerEl.classList.remove("hide");
  audioViewerExternalBtnEl.classList.toggle("hide", !externalVideoPlayerEnabled);
  updateAudioViewerNavButtons();
  showAudioAt(audioViewerIndex);
}

function closeAudioViewer() {
  audioViewerAudioEl.pause();
  audioViewerEl.classList.add("hide");
  audioViewerAudioEl.removeAttribute("src");
  audioViewerAudioEl.load();
  audioViewerIds = [];
  audioViewerIndex = -1;
}

function showAudioAt(index) {
  audioViewerIndex = index;
  const id = audioViewerIds[audioViewerIndex];
  const file = findFile(id);
  audioViewerErrorEl.classList.add("hide");
  audioViewerAudioEl.classList.remove("hide");
  audioViewerFilenameEl.textContent = file
    ? audioViewerIds.length > 1
      ? `${file.name} (${audioViewerIndex + 1} / ${audioViewerIds.length})`
      : file.name
    : "";
  audioViewerAudioEl.src = `/api/files/${id}/content`;
  audioViewerAudioEl.playbackRate = audioViewerPlaybackRate;
  audioViewerSpeedSelectEl.value = String(audioViewerPlaybackRate);
  audioViewerAudioEl.play().catch(() => {});
  if (!file) return;
  markFileOpened(id);
}

audioViewerAudioEl.addEventListener("error", () => {
  audioViewerAudioEl.classList.add("hide");
  audioViewerErrorEl.classList.remove("hide");
});

function updateAudioViewerNavButtons() {
  const multiple = audioViewerIds.length > 1;
  audioViewerPrevBtnEl.classList.toggle("hide", !multiple);
  audioViewerNextBtnEl.classList.toggle("hide", !multiple);
}

function audioViewerStep(delta) {
  if (audioViewerIds.length < 2) return;
  const next = (audioViewerIndex + delta + audioViewerIds.length) % audioViewerIds.length;
  showAudioAt(next);
}

audioViewerStageEl.addEventListener("click", (e) => {
  if (e.target === audioViewerStageEl) closeAudioViewer();
});

audioViewerPrevBtnEl.addEventListener("click", () => audioViewerStep(-1));
audioViewerNextBtnEl.addEventListener("click", () => audioViewerStep(1));
audioViewerCloseBtnEl.addEventListener("click", () => closeAudioViewer());
audioViewerExternalBtnEl.addEventListener("click", () => {
  const id = audioViewerIds[audioViewerIndex];
  closeAudioViewer();
  if (id) playExternal(id);
});

let audioViewerPlaybackRate = 1;

function audioViewerSkip(deltaSeconds) {
  const a = audioViewerAudioEl;
  if (!a.duration) return;
  a.currentTime = Math.min(Math.max(0, a.currentTime + deltaSeconds), a.duration);
}

audioViewerSkipBackBtnEl.addEventListener("click", () => audioViewerSkip(-VIDEO_VIEWER_SKIP_SECONDS));
audioViewerSkipFwdBtnEl.addEventListener("click", () => audioViewerSkip(VIDEO_VIEWER_SKIP_SECONDS));
audioViewerSpeedSelectEl.addEventListener("change", () => {
  audioViewerPlaybackRate = Number(audioViewerSpeedSelectEl.value);
  audioViewerAudioEl.playbackRate = audioViewerPlaybackRate;
});

async function bulkMove(targetId, payload) {
  const failures = [];
  for (const id of payload.folderIds) {
    try {
      const updated = await apiFetch(`/api/folders/${id}`, { method: "PUT", body: JSON.stringify({ parent_id: targetId }) });
      Object.assign(findFolder(id), updated);
    } catch (err) {
      failures.push(`${(findFolder(id) || {}).name || id}: ${err.message}`);
    }
  }
  for (const id of payload.fileIds) {
    try {
      const updated = await apiFetch(`/api/files/${id}`, { method: "PUT", body: JSON.stringify({ folder_id: targetId }) });
      Object.assign(findFile(id), updated);
    } catch (err) {
      failures.push(`${(findFile(id) || {}).name || id}: ${err.message}`);
    }
  }
  clearSelection();
  renderAll();
  if (failures.length) alert(`Some items couldn't be moved:\n${failures.join("\n")}`);
}

async function bulkStar(starred) {
  const ids = Array.from(selectedFileIds);
  if (!ids.length) return;
  try {
    const result = await apiFetch("/api/files/bulk-star", {
      method: "POST",
      body: JSON.stringify({ file_ids: ids, starred }),
    });
    if (result.ok) {
      for (const id of ids) {
        const f = findFile(id);
        if (f) f.starred_at = starred ? new Date().toISOString() : null;
      }
      clearSelection();
      applySelectionClasses();
      renderGrid();
      if (currentSmartView) renderSmartView(currentSmartView);
    }
  } catch (err) {
    alert(err.message);
  }
}

async function bulkDelete() {
  const failures = [];
  const removedFolderIds = new Set();
  const removedFileIds = new Set();
  for (const id of selectedFolderIds) {
    try {
      await apiFetch(`/api/folders/${id}`, { method: "DELETE" });
      removedFolderIds.add(id);
    } catch (err) {
      failures.push(`${(findFolder(id) || {}).name || id}: ${err.message}`);
    }
  }
  for (const id of selectedFileIds) {
    try {
      await apiFetch(`/api/files/${id}`, { method: "DELETE" });
      removedFileIds.add(id);
    } catch (err) {
      failures.push(`${(findFile(id) || {}).name || id}: ${err.message}`);
    }
  }
  const allRemovedFolderIds = new Set();
  removedFolderIds.forEach((id) => {
    allRemovedFolderIds.add(id);
    collectDescendantIds(id).forEach((d) => allRemovedFolderIds.add(d));
  });
  if (allRemovedFolderIds.has(currentFolderId)) currentFolderId = null;
  folders = folders.filter((f) => !allRemovedFolderIds.has(f.id));
  files = files.filter((f) => !removedFileIds.has(f.id) && !allRemovedFolderIds.has(f.folder_id));
  clearSelection();
  renderAll();
  if (trashLoaded) loadTrash();
  if (failures.length) alert(`Some items couldn't be deleted:\n${failures.join("\n")}`);
}

function bulkDownload() {
  const fileIds = Array.from(selectedFileIds);
  const folderIds = Array.from(selectedFolderIds);
  if (!folderIds.length) {

    if (!supportsFileSystemAccess) {
      fileIds.forEach((id) => legacyDownloadFile(id));
      return;
    }
    bulkDownloadWithProgress(fileIds);
    return;
  }

  if (!supportsFileSystemAccess) {
    alert(
      "Downloading folders needs a browser feature (File System Access) this environment doesn't have - try updating WebView2, or download files individually instead."
    );
    return;
  }
  downloadMixedWithProgress(folderIds, fileIds);
}

function bulkContextItems() {
  const payload = { folderIds: Array.from(selectedFolderIds), fileIds: Array.from(selectedFileIds) };
  const items = [
    {
      label: "Move to",
      action: () => openMovePanel({ title: "Batch Move", ...bulkMoveExclusions(), onConfirm: (targetId) => bulkMove(targetId, payload) }),
    },
  ];
  if (selectedFileIds.size || selectedFolderIds.size) {
    const count = selectedFileIds.size + selectedFolderIds.size;
    items.unshift({ label: `Download (${count})`, action: () => bulkDownload() });
  }
  if (selectedFileIds.size) {
    const anyUnstarred = Array.from(selectedFileIds).some((id) => { const f = findFile(id); return f && !f.starred_at; });
    items.push({
      label: anyUnstarred ? "Star all" : "Unstar all",
      action: () => bulkStar(anyUnstarred),
    });
  }
  items.push({ label: "Delete", danger: true, action: () => bulkDelete() });
  return items;
}

function emptySpaceContextItems() {
  return [
    { label: "New folder", action: () => createFolder(currentFolderId) },
    { label: "Upload file(s)", action: () => pickAndUploadFiles() },
    { label: "Upload folder", action: () => uploadFolder() },
    { label: "Refresh", action: () => refreshCurrent() },
  ];
}

document.getElementById("new-btn").addEventListener("click", (e) => {

  e.stopPropagation();
  const rect = e.currentTarget.getBoundingClientRect();
  openContextMenu(emptySpaceContextItems(), rect.left, rect.bottom + 4);
});

function folderContextItems(id) {
  return [
    { label: "Open", action: () => openFolder(id) },
    { label: "Download", action: () => downloadFolderWithProgress(id) },
    { label: "Rename", action: () => renameFolder(id) },
    { label: "New subfolder", action: () => createFolder(id) },
    {
      label: "Move to",
      action: () => openMovePanel({ title: "Move", ...folderMoveExclusions(id), onConfirm: (targetId) => moveFolder(id, targetId) }),
    },
    { label: "Properties", action: () => openFolderProperties(id) },
    { label: "Delete", danger: true, action: () => deleteFolder(id) },
  ];
}

function fileContextItems(id) {
  const file = findFile(id);
  const showPlayExternal =
    file && file.mime_type && (file.mime_type.startsWith("video/") || file.mime_type.startsWith("audio/")) && externalVideoPlayerEnabled;
  return [
    { label: "Open", action: () => openFile(id) },
    ...(showPlayExternal ? [{ label: "Play in external player", action: () => playExternal(id) }] : []),
    { label: "Download", action: () => downloadFile(id) },
    { label: file && file.starred_at ? "Unstar" : "Star", action: () => toggleStar(id) },
    { label: "Rename", action: () => renameFile(id) },
    { label: "Upload new version…", action: () => triggerVersionUpload(id) },
    { label: "Version history…", action: () => openVersionHistory(id) },
    {
      label: "Move to",
      action: () => openMovePanel({ title: "Move", ...fileMoveExclusions(id), onConfirm: (targetId) => moveFile(id, targetId) }),
    },
    { label: "Properties", action: () => openFileProperties(id) },
    { label: "Delete", danger: true, action: () => deleteFile(id) },
  ];
}

async function toggleStar(id) {
  const file = findFile(id);
  if (!file) return;
  try {
    const updated = await apiFetch(`/api/files/${id}`, {
      method: "PUT",
      body: JSON.stringify({ starred: !file.starred_at }),
    });
    Object.assign(file, updated);
    renderGrid();
    if (currentSmartView) renderSmartView(currentSmartView);
  } catch (err) {
    alert(err.message);
  }
}

treeEl.addEventListener("contextmenu", (e) => {
  const item = e.target.closest(".tree-item");
  if (!item || !item.dataset.id) return;
  e.preventDefault();
  const id = item.dataset.id;

  if (selectedFolderIds.has(id) && selectionActive()) {
    openContextMenu(bulkContextItems(), e.clientX, e.clientY);
    return;
  }
  if (selectionActive()) { clearSelection(); applySelectionClasses(); }
  openContextMenu(folderContextItems(id), e.clientX, e.clientY);
});

gridEl.addEventListener("contextmenu", (e) => {
  e.preventDefault();
  const folderCard = e.target.closest(".folder-card");
  const fileCard = e.target.closest(".file-card");
  const card = folderCard || fileCard;

  if (card) {
    const type = folderCard ? "folder" : "file";
    const id = card.dataset.id;
    const set = type === "folder" ? selectedFolderIds : selectedFileIds;
    if (set.has(id)) {
      openContextMenu(bulkContextItems(), e.clientX, e.clientY);
      return;
    }
    if (selectionActive()) {
      clearSelection();
      applySelectionClasses();
    }
    openContextMenu(folderCard ? folderContextItems(id) : fileContextItems(id), e.clientX, e.clientY);
    return;
  }
  openContextMenu(emptySpaceContextItems(), e.clientX, e.clientY);
});

function showSettingsStep(step) {
  settingsConnectedEl.classList.add("hide");
  SETTINGS_STEPS.forEach((s) => document.getElementById(`step-${s}`).classList.toggle("hide", s !== step));
}

function showSettingsConnected(status) {
  SETTINGS_STEPS.forEach((s) => document.getElementById(`step-${s}`).classList.add("hide"));
  settingsConnectedEl.classList.remove("hide");
  document.getElementById("status-phone").textContent = status.phone_number || "-";
  document.getElementById("status-premium").textContent = status.is_premium ? "Telegram Premium" : "Free account";
  document.getElementById("status-archive").textContent = status.archive_chat_title || "-";
  document.getElementById("f-chunk-size-mb").value = status.max_chunk_size_bytes
    ? Math.round(status.max_chunk_size_bytes / 1e6)
    : "";
  document.getElementById("f-video-player-path").value = status.video_player_path || "";
  externalVideoPlayerEnabled = !!status.external_video_player_enabled;
  document.getElementById("external-video-player-toggle").checked = externalVideoPlayerEnabled;
  maxParallelTransfers = status.max_parallel_transfers || 3;
  document.getElementById("f-parallel-transfers").value = maxParallelTransfers;
  document.getElementById("f-upload-workers").value = status.upload_parallel_workers || 3;
  document.getElementById("f-upload-part-size").value = status.upload_part_size_kb || 0;
  document.getElementById("f-download-workers").value = status.download_parallel_workers || 8;
  document.getElementById("f-completed-uploads-persistence").value = status.completed_uploads_persistence || "clear";

  document.getElementById("close-to-tray-toggle").checked = status.close_to_tray !== false;
  if (status.log_path) document.getElementById("log-path-hint").textContent = status.log_path;
  document.getElementById("f-thumbnail-format").value = status.thumbnail_format || "jpeg";
  document.getElementById("f-thumbnail-quality-slider").value = status.thumbnail_quality || 75;
  document.getElementById("f-thumbnail-quality").value = status.thumbnail_quality || 75;
  document.getElementById("f-thumbnail-chroma-subsampling").value = status.thumbnail_chroma_subsampling || "default";
  document.getElementById("f-sync-backoff-workers").value = status.sync_backoff_workers || 1;

  document.getElementById("f-max-upload-request-gb").value =
    status.max_upload_request_bytes ? Math.round(status.max_upload_request_bytes / 1e9) : 0;
  showSettingsTab("account");

  (async () => {
    await refreshAppDataBackupStatus();
    await refreshArchiveCheck();
  })();
}

function showSettingsTab(tab) {
  SETTINGS_TABS.forEach((t) => {
    document.getElementById(`settings-tab-${t}`).classList.toggle("hide", t !== tab);
  });
  document.querySelectorAll(".settings-tab-btn").forEach((btn) => {
    const active = btn.dataset.tab === tab;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", String(active));
  });
  if (tab === "shortcuts") {
    _recordingActionId = null;
    renderShortcutsTab();
  }
}

document.querySelectorAll(".settings-tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => showSettingsTab(btn.dataset.tab));
});

const SETTINGS_GROUPS_STORAGE_KEY = "tvSettingsGroupsOpen";

function rememberSettingsGroups() {
  const groups = document.querySelectorAll(".settings-group");
  if (!groups.length) return;
  let stored = null;
  try {
    stored = JSON.parse(localStorage.getItem(SETTINGS_GROUPS_STORAGE_KEY) || "null");
  } catch {
    stored = null;
  }
  groups.forEach((group) => {
    if (stored && Object.prototype.hasOwnProperty.call(stored, group.id)) {
      group.open = !!stored[group.id];
    }
    group.addEventListener("toggle", () => {
      const state = {};
      document.querySelectorAll(".settings-group").forEach((g) => { state[g.id] = g.open; });
      try {
        localStorage.setItem(SETTINGS_GROUPS_STORAGE_KEY, JSON.stringify(state));
      } catch {

      }
    });
  });
}

rememberSettingsGroups();

async function refreshArchiveCheck() {
  const rowEl = document.getElementById("archive-check-row");
  const textEl = document.getElementById("status-archive-check");
  const hintEl = document.getElementById("archive-check-hint");
  const recEl = document.getElementById("recovery-section");
  try {
    const check = await apiFetch("/api/telegram/archive-check");
    if (check.local_mismatch_chat_id) {
      textEl.textContent = "Mismatch found";
      textEl.classList.add("step-error");
      hintEl.textContent = `Your local file index has files recorded under a different Telegram chat (${check.local_mismatch_chat_id}) than the archive group configured above - some files may not be reachable until this is resolved.`;
      hintEl.classList.add("step-error");
      rowEl.classList.remove("hide");
      hintEl.classList.remove("hide");
      if (recEl) recEl.classList.remove("hide");
    } else if (check.local_file_count > 0 && check.has_backup_history === false) {
      textEl.textContent = "No backup history";
      textEl.classList.remove("step-error");
      hintEl.textContent = "This archive has no app-data backup history, even though your local index already has files in it - if you expected an established vault here, double check this is the archive you meant to connect to.";
      hintEl.classList.remove("step-error");
      rowEl.classList.remove("hide");
      hintEl.classList.remove("hide");

      if (recEl) recEl.classList.add("hide");
    } else {
      rowEl.classList.add("hide");
      hintEl.classList.add("hide");
      if (recEl) recEl.classList.add("hide");
    }
  } catch (err) {

    rowEl.classList.add("hide");
    hintEl.classList.add("hide");
    if (recEl) recEl.classList.add("hide");
  }
}

document.getElementById("save-video-player-btn").addEventListener("click", async () => {
  const input = document.getElementById("f-video-player-path");
  try {
    const settings = await apiFetch("/api/settings/video-player", {
      method: "PUT",
      body: JSON.stringify({ video_player_path: input.value.trim() }),
    });
    input.value = settings.video_player_path || "";
  } catch (err) {
    alert(err.message);
  }
});

document.getElementById("external-video-player-toggle").addEventListener("change", async (e) => {
  const checkbox = e.target;
  const next = checkbox.checked;
  try {
    await apiFetch("/api/settings/video-player", {
      method: "PUT",
      body: JSON.stringify({ external_video_player_enabled: next }),
    });
    externalVideoPlayerEnabled = next;
  } catch (err) {
    checkbox.checked = !next;
    alert(err.message);
  }
});

document.getElementById("save-chunk-size-btn").addEventListener("click", async () => {
  const hintEl = document.getElementById("chunk-size-hint");
  const mb = parseFloat(document.getElementById("f-chunk-size-mb").value);
  if (!mb || mb <= 0) {
    hintEl.textContent = "Enter a positive number of MB.";
    return;
  }
  try {
    const settings = await apiFetch("/api/settings/max-chunk-size", {
      method: "PUT",
      body: JSON.stringify({ max_chunk_size_bytes: Math.round(mb * 1e6) }),
    });
    document.getElementById("f-chunk-size-mb").value = Math.round(settings.max_chunk_size_bytes / 1e6);
    hintEl.textContent = `Saved - files over ${Math.round(settings.max_chunk_size_bytes / 1e6)} MB will now be split into multiple messages.`;
  } catch (err) {
    hintEl.textContent = err.message;
  }
});

document.getElementById("save-parallel-transfers-btn").addEventListener("click", async () => {
  const hintEl = document.getElementById("parallel-transfers-hint");
  const value = parseInt(document.getElementById("f-parallel-transfers").value, 10);
  if (!value || value < 1 || value > 10) {
    hintEl.textContent = "Enter a number between 1 and 10.";
    return;
  }
  try {
    const result = await apiFetch("/api/settings/parallel-transfers", {
      method: "PUT",
      body: JSON.stringify({ max_parallel_transfers: value }),
    });
    maxParallelTransfers = result.max_parallel_transfers;
    document.getElementById("f-parallel-transfers").value = maxParallelTransfers;
    hintEl.textContent = `Saved - up to ${maxParallelTransfers} whole file(s) will now transfer at once.`;
  } catch (err) {
    hintEl.textContent = err.message;
  }
});

document.getElementById("save-upload-workers-btn").addEventListener("click", async () => {
  const hintEl = document.getElementById("upload-workers-hint");
  const value = parseInt(document.getElementById("f-upload-workers").value, 10);
  if (!value || value < 1 || value > 32) {
    hintEl.textContent = "Enter a number between 1 and 32.";
    return;
  }
  const partKbs = parseInt(document.getElementById("f-upload-part-size").value, 10);
  try {
    const result = await apiFetch("/api/settings/upload", {
      method: "PUT",
      body: JSON.stringify({ upload_parallel_workers: value, upload_part_size_kb: partKbs }),
    });
    document.getElementById("f-upload-workers").value = result.upload_parallel_workers;
    document.getElementById("f-upload-part-size").value = result.upload_part_size_kb;
    if (result.upload_parallel_workers === 1) {
      hintEl.textContent = `Saved - uploads now use the sequential path (1 stream). The part-size setting also took effect.`;
    } else {
      const partDesc = result.upload_part_size_kb === 0 ? "auto-tiered" : `${result.upload_part_size_kb}KB`;
      hintEl.textContent = `Saved - each upload will now use up to ${result.upload_parallel_workers} parallel streams, parts ${partDesc}.`;
    }
  } catch (err) {
    hintEl.textContent = err.message;
  }
});

document.getElementById("save-upload-part-size-btn").addEventListener("click", async () => {
  const hintEl = document.getElementById("upload-part-size-hint");
  const partKbs = parseInt(document.getElementById("f-upload-part-size").value, 10);
  if (isNaN(partKbs) || partKbs < 0 || partKbs > 512 || (partKbs > 0 && partKbs < 32)) {
    hintEl.textContent = "Enter 0 (auto), or a value between 32 and 512 KB (must be a multiple of 32).";
    return;
  }
  const workers = parseInt(document.getElementById("f-upload-workers").value, 10);
  try {
    const result = await apiFetch("/api/settings/upload", {
      method: "PUT",
      body: JSON.stringify({ upload_parallel_workers: workers, upload_part_size_kb: partKbs }),
    });
    document.getElementById("f-upload-workers").value = result.upload_parallel_workers;
    document.getElementById("f-upload-part-size").value = result.upload_part_size_kb;
    if (result.upload_part_size_kb === 0) {
      hintEl.textContent = `Saved - parts now auto-tier by file size (64KB / 256KB / 512KB). Worker setting also took effect.`;
    } else {
      hintEl.textContent = `Saved - uploads now use ${result.upload_part_size_kb}KB parts (fixed). Worker setting also took effect.`;
    }
  } catch (err) {
    hintEl.textContent = err.message;
  }
});

document.getElementById("save-download-workers-btn").addEventListener("click", async () => {
  const hintEl = document.getElementById("download-workers-hint");
  const value = parseInt(document.getElementById("f-download-workers").value, 10);
  if (isNaN(value) || value < 1 || value > 16) {
    hintEl.textContent = "Enter a whole number between 1 and 16.";
    return;
  }
  try {
    const result = await apiFetch("/api/settings/download", {
      method: "PUT",
      body: JSON.stringify({ download_parallel_workers: value }),
    });
    document.getElementById("f-download-workers").value = result.download_parallel_workers;
    hintEl.textContent = `Saved - each download/stream will now use up to ${result.download_parallel_workers} parallel stream(s).`;
  } catch (err) {
    hintEl.textContent = err.message;
  }
});

document.getElementById("save-completed-uploads-persistence-btn").addEventListener("click", async () => {
  const hintEl = document.getElementById("completed-uploads-persistence-hint");
  const value = document.getElementById("f-completed-uploads-persistence").value;
  try {
    const result = await apiFetch("/api/settings/completed-uploads-persistence", {
      method: "PUT",
      body: JSON.stringify({ completed_uploads_persistence: value }),
    });
    document.getElementById("f-completed-uploads-persistence").value = result.completed_uploads_persistence;
    hintEl.textContent = value === "keep"
      ? "Saved - completed uploads will now persist across restarts until you dismiss or clear them."
      : "Saved - completed uploads will be cleared on each restart (historical behavior).";
  } catch (err) {
    hintEl.textContent = err.message;
  }
});

document.getElementById("save-thumbnail-format-btn").addEventListener("click", async () => {
  const hintEl = document.getElementById("thumbnail-format-hint");
  const value = document.getElementById("f-thumbnail-format").value;
  try {
    const result = await apiFetch("/api/settings/thumbnail-format", {
      method: "PUT",
      body: JSON.stringify({ thumbnail_format: value }),
    });
    document.getElementById("f-thumbnail-format").value = result.thumbnail_format;
    hintEl.textContent = `Saved - new thumbnails will now be generated as ${result.thumbnail_format.toUpperCase()}. Existing cached thumbnails are unaffected until regenerated.`;
  } catch (err) {
    hintEl.textContent = err.message;
  }
});

const thumbQualitySliderEl = document.getElementById("f-thumbnail-quality-slider");
const thumbQualityNumberEl = document.getElementById("f-thumbnail-quality");
thumbQualitySliderEl.addEventListener("input", () => { thumbQualityNumberEl.value = thumbQualitySliderEl.value; });
thumbQualityNumberEl.addEventListener("input", () => { thumbQualitySliderEl.value = thumbQualityNumberEl.value; });

document.getElementById("save-thumbnail-quality-btn").addEventListener("click", async () => {
  const hintEl = document.getElementById("thumbnail-quality-hint");
  const value = parseInt(thumbQualityNumberEl.value, 10);
  if (isNaN(value) || value < 1 || value > 100) {
    hintEl.textContent = "Enter a whole number between 1 and 100.";
    return;
  }
  try {
    const result = await apiFetch("/api/settings/thumbnail-quality", {
      method: "PUT",
      body: JSON.stringify({ thumbnail_quality: value }),
    });
    thumbQualityNumberEl.value = result.thumbnail_quality;
    thumbQualitySliderEl.value = result.thumbnail_quality;
    hintEl.textContent = `Saved - new local thumbnails will use quality ${result.thumbnail_quality}. Existing cached thumbnails are unaffected until regenerated.`;
  } catch (err) {
    hintEl.textContent = err.message;
  }
});

document.getElementById("save-thumbnail-chroma-subsampling-btn").addEventListener("click", async () => {
  const hintEl = document.getElementById("thumbnail-chroma-subsampling-hint");
  const value = document.getElementById("f-thumbnail-chroma-subsampling").value;
  try {
    const result = await apiFetch("/api/settings/thumbnail-chroma-subsampling", {
      method: "PUT",
      body: JSON.stringify({ thumbnail_chroma_subsampling: value }),
    });
    document.getElementById("f-thumbnail-chroma-subsampling").value = result.thumbnail_chroma_subsampling;
    hintEl.textContent = `Saved - new local thumbnails will use ${result.thumbnail_chroma_subsampling} chroma subsampling. Existing cached thumbnails are unaffected until regenerated.`;
  } catch (err) {
    hintEl.textContent = err.message;
  }
});

document.getElementById("save-sync-backoff-btn").addEventListener("click", async () => {
  const hintEl = document.getElementById("sync-backoff-hint");
  const value = parseInt(document.getElementById("f-sync-backoff-workers").value, 10);
  if (isNaN(value) || value < 1 || value > 10) {
    hintEl.textContent = "Enter a whole number between 1 and 10.";
    return;
  }
  try {
    const result = await apiFetch("/api/settings/sync-backoff", {
      method: "PUT",
      body: JSON.stringify({ sync_backoff_workers: value }),
    });
    document.getElementById("f-sync-backoff-workers").value = result.sync_backoff_workers;
    hintEl.textContent = `Saved - background sync now keeps up to ${result.sync_backoff_workers} concurrent request(s) per round while you're active.`;
  } catch (err) {
    hintEl.textContent = err.message;
  }
});

async function wipeVersionedData() {
  if (!window.confirm("This deletes every stored OLD VERSION of every file in this vault - each file's current version is kept, only its version history is removed. This is what frees the \"Versioned files\" storage shown above. Continue?")) return;
  if (!window.confirm("Are you sure? Once deleted, those old versions cannot be recovered - this action cannot be undone.")) return;
  try {
    const result = await apiFetch("/api/wipe/versioned", { method: "POST" });
    window.alert(`Done - deleted ${result.files_affected} file version${result.files_affected === 1 ? "" : "s"}, freeing ${formatBytes(result.bytes_freed)}.`);
    window.location.reload();
  } catch (err) {
    window.alert(err.message);
  }
}

async function wipeAllData() {
  if (!window.confirm("This deletes EVERY FILE AND FOLDER in this vault, not just version history - your entire archive group's contents. Continue?")) return;
  if (!window.confirm("Are you sure? Every file and folder currently in this vault will be gone, with no version history left to fall back on - this cannot be undone.")) return;
  if (!window.confirm("Final confirmation: this immediately and irreversibly erases the entire vault - every file, every folder, every version of every file, all of it, permanently. There is no way to get any of this back afterward. Proceed?")) return;
  try {
    const result = await apiFetch("/api/wipe/all", { method: "POST" });
    window.alert(`Done - deleted ${result.files_deleted} file${result.files_deleted === 1 ? "" : "s"}, freeing ${formatBytes(result.bytes_freed)}.`);
    window.location.reload();
  } catch (err) {
    window.alert(err.message);
  }
}

async function clearCache() {
  if (!window.confirm("Clear the local cache? This frees disk space immediately - your files stay safely in Telegram and will simply be re-fetched next time you open them.")) return;
  try {
    const result = await apiFetch("/api/cache/clear", { method: "POST" });
    window.alert(`Done - freed ${formatBytes(result.bytes_freed)}.`);
    refreshStats();
  } catch (err) {
    window.alert(err.message);
  }
}

document.getElementById("wipe-versioned-btn").addEventListener("click", wipeVersionedData);
document.getElementById("wipe-all-btn").addEventListener("click", wipeAllData);
document.getElementById("clear-cache-btn").addEventListener("click", clearCache);

document.getElementById("export-settings-btn").addEventListener("click", async () => {
  try {
    const result = await apiFetch("/api/settings/export");
    if (!result.ok) { alert(result.error); return; }
    const blob = new Blob([JSON.stringify(result.settings, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "telegram-vault-settings.json";
    document.body.appendChild(a); a.click();
    document.body.removeChild(a); URL.revokeObjectURL(url);
  } catch (err) { alert(err.message); }
});

document.getElementById("import-settings-btn").addEventListener("click", () => {
  const input = document.createElement("input");
  input.type = "file"; input.accept = ".json";
  input.onchange = async () => {
    const file = input.files[0];
    if (!file) return;
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      const result = await apiFetch("/api/settings/import", {
        method: "POST", body: JSON.stringify({ settings: data }),
      });
      if (!result.ok) { alert(result.error); return; }
      alert("Settings imported. Restart the app for changes to take full effect.");
      const status = await apiFetch("/api/telegram/status");
      updateRailFoot(status);
      showSettingsConnected(status);
    } catch (err) { alert("Failed to import: " + err.message); }
  };
  input.click();
});

async function runBackfillScan(full) {
  const confirmText = full
    ? "Full rescan? This re-walks every message in your archive group from the beginning, ignoring the last-scanned marker. Slower, and only needed to re-import a file you deleted from this index but kept in Telegram."
    : "Run backfill scan? This scans your archive chat for files uploaded outside this app (e.g. via Telegram directly) and adds them to your vault at the root level. Already-indexed messages are skipped.";
  if (!confirm(confirmText)) return;
  const resultEl = document.getElementById("backfill-result");
  resultEl.textContent = full ? "Re-walking your whole archive group..." : "Scanning your archive group...";
  try {
    const result = await apiFetch("/api/telegram/backfill", {
      method: "POST",
      body: JSON.stringify({ full: !!full }),
    });
    resultEl.textContent = `Imported ${result.imported} file${result.imported === 1 ? "" : "s"}, skipped ${result.skipped} already indexed.`;
    await refreshCurrent();
  } catch (err) {
    resultEl.textContent = err.message;
  }
}

document.getElementById("backfill-btn").addEventListener("click", () => runBackfillScan(false));
document.getElementById("backfill-full-btn").addEventListener("click", () => runBackfillScan(true));

document.getElementById("media-topic-migrate-btn").addEventListener("click", async () => {
  const resultEl = document.getElementById("media-topic-migrate-result");
  resultEl.textContent = "Forwarding into the Media topic...";
  try {
    const result = await apiFetch("/api/media-topic/migrate", { method: "POST" });
    const parts = [`Migrated ${result.migrated.length} file${result.migrated.length === 1 ? "" : "s"}`];
    if (result.migrated.length) parts.push("old copies are still in General for you to remove");
    if (result.errors.length) parts.push(`${result.errors.length} failed - see console`);
    resultEl.textContent = parts.join(" - ") + ".";
    if (result.errors.length) console.error("media-topic migrate errors:", result.errors);
  } catch (err) {
    resultEl.textContent = err.message;
  }
});

let _backupStatusPromise = null;
function fetchAppDataBackupStatus() {
  if (!_backupStatusPromise) {
    _backupStatusPromise = apiFetch("/api/app-data-backup/status").finally(() => {
      _backupStatusPromise = null;
    });
  }
  return _backupStatusPromise;
}

async function refreshAppDataBackupStatus() {
  try {
    const status = await fetchAppDataBackupStatus();
    document.getElementById("backup-enabled-toggle").checked = !!status.backup_enabled;
    document.getElementById("backup-check-on-boot-toggle").checked = !!status.check_on_boot;
    document.getElementById("backup-include-thumbnails-toggle").checked = !!status.include_thumbnails;
    const forumEl = document.getElementById("status-forum-mode");
    const forumBtn = document.getElementById("forum-mode-btn");
    if (status.forum_enabled === true) {

      forumEl.textContent = "On";
      forumBtn.textContent = "";
      forumBtn.classList.add("hide");
    } else if (status.forum_enabled === false) {
      forumEl.textContent = "Off";
      forumBtn.textContent = "Enable";
      forumBtn.classList.remove("hide");
    } else {

      forumEl.textContent = "Unknown";
      forumBtn.textContent = "Enable";
      forumBtn.classList.remove("hide");
    }
  } catch (err) {

  }
}

document.getElementById("refresh-premium-status-btn").addEventListener("click", async () => {
  const btn = document.getElementById("refresh-premium-status-btn");
  btn.disabled = true;
  btn.classList.add("spinning");
  try {
    const result = await apiFetch("/api/telegram/refresh-premium-status", { method: "POST" });
    document.getElementById("status-premium").textContent = result.is_premium ? "Telegram Premium" : "Free account";

    if (result.max_chunk_size_bytes) {
      document.getElementById("f-chunk-size-mb").value = Math.round(result.max_chunk_size_bytes / 1e6);
    }
  } catch (err) {
    alert(err.message);
  } finally {
    btn.disabled = false;
    btn.classList.remove("spinning");
  }
});

document.getElementById("logout-btn").addEventListener("click", async () => {
  if (!window.confirm("Log out of this Telegram account? Your local file index, thumbnails, and settings are kept - only the account session is cleared. You'll need to reconnect (phone number + code) to use the app again.")) return;
  const btn = document.getElementById("logout-btn");
  btn.disabled = true;
  try {
    await apiFetch("/api/telegram/logout", { method: "POST" });
    window.location.reload();
  } catch (err) {
    btn.disabled = false;
    alert(err.message);
  }
});

document.getElementById("forum-mode-btn").addEventListener("click", async () => {
  const btn = document.getElementById("forum-mode-btn");

  const message = "This turns on Topics/Forum mode for your archive group - a real, visible change anyone viewing that group in any Telegram client will see (it adds a topic list). App-data backup needs it to store anything, so Poggram keeps it on. Continue?";
  if (!window.confirm(message)) return;
  try {
    await apiFetch("/api/app-data-backup/forum-mode", { method: "POST", body: JSON.stringify({ enabled: true }) });
    refreshAppDataBackupStatus();
  } catch (err) {
    alert(err.message);
  }
});

document.getElementById("backup-enabled-toggle").addEventListener("change", async (e) => {
  const checkbox = e.target;
  const next = checkbox.checked;
  try {
    await apiFetch("/api/app-data-backup/settings", { method: "POST", body: JSON.stringify({ backup_enabled: next }) });
  } catch (err) {
    checkbox.checked = !next;
    alert(err.message);
  }
});

document.getElementById("backup-check-on-boot-toggle").addEventListener("change", async (e) => {
  const checkbox = e.target;
  const next = checkbox.checked;
  try {
    await apiFetch("/api/app-data-backup/settings", { method: "POST", body: JSON.stringify({ check_on_boot: next }) });
  } catch (err) {
    checkbox.checked = !next;
    alert(err.message);
  }
});

document.getElementById("backup-include-thumbnails-toggle").addEventListener("change", async (e) => {
  const checkbox = e.target;
  const next = checkbox.checked;
  try {
    await apiFetch("/api/app-data-backup/settings", { method: "POST", body: JSON.stringify({ include_thumbnails: next }) });
  } catch (err) {
    checkbox.checked = !next;
    alert(err.message);
  }
});

document.getElementById("open-log-btn").addEventListener("click", async () => {
  try {
    await apiFetch("/api/logs/open", { method: "POST" });
  } catch (err) {
    alert(err.message);
  }
});

document.getElementById("close-to-tray-toggle").addEventListener("change", async (e) => {
  const checkbox = e.target;
  const next = checkbox.checked;
  try {
    await apiFetch("/api/settings/close-to-tray", { method: "PUT", body: JSON.stringify({ close_to_tray: next }) });
  } catch (err) {

    checkbox.checked = !next;
    alert(err.message);
  }
});

document.getElementById("backup-now-btn").addEventListener("click", async () => {
  const btn = document.getElementById("backup-now-btn");
  const resultEl = document.getElementById("backup-now-result");

  btn.disabled = true;
  resultEl.textContent = "Backing up...";
  showBlockingOverlay("Preparing backup...");
  try {
    await apiFetch("/api/app-data-backup/snapshot", { method: "POST" });
    const result = await pollBackupStatus();
    if (result.ok) {
      resultEl.textContent = `Backed up just now (${formatDate(new Date().toISOString())}).`;
    } else {
      resultEl.textContent = `Backup failed: ${result.error}`;
    }
  } catch (err) {
    hideBlockingOverlay();
    resultEl.textContent = `Backup failed: ${err.message}`;
  } finally {
    btn.disabled = false;
  }
});

function closeBackupPanel() {
  backupPanelEl.classList.add("hide");
  backupPanelEl.innerHTML = "";
}

async function openBackupPanel() {
  try {
    const snapshots = await apiFetch("/api/app-data-backup/snapshots");
    renderBackupPanel(snapshots);
  } catch (err) {
    alert(err.message);
  }
}

function renderBackupPanel(snapshots) {
  const rows = snapshots.length
    ? snapshots
        .map(
          (s) => `
        <div class="version-row">
          <div class="version-row-info">
            <div class="version-row-title">${escapeHtml(formatDate(s.date))}</div>
            <div class="version-row-sub">${formatBytes(s.size_bytes)}</div>
          </div>
          <div class="version-row-actions">
            <button type="button" data-action="restore" data-message-id="${s.message_id}">Restore</button>
          </div>
        </div>
      `
        )
        .join("")
    : `<p class="step-hint">No backups yet - use "Back up now" in Settings, or wait for the next automatic one.</p>`;
  backupPanelEl.innerHTML = `
    <div class="version-panel-content">
      <div class="version-panel-header">
        <span class="version-panel-title">Backup history</span>
        <button type="button" class="version-panel-close" aria-label="Close">&times;</button>
      </div>
      <div class="version-list">${rows}</div>
    </div>
  `;
  backupPanelEl.classList.remove("hide");
}

const restoreOverlayEl = document.getElementById("restore-overlay");
const restoreOverlayTextEl = document.getElementById("restore-overlay-text");
const restoreOverlayBarFillEl = document.getElementById("restore-overlay-bar-fill");

function showBlockingOverlay(text) {
  restoreOverlayEl.classList.remove("hide");
  restoreOverlayTextEl.textContent = text;
  restoreOverlayBarFillEl.style.width = "0%";

  if (window.lucide) lucide.createIcons();
}

function hideBlockingOverlay() {
  restoreOverlayEl.classList.add("hide");
}

async function pollBackupStatus() {
  let info;
  try {
    info = await apiFetch("/api/app-data-backup/backup-status");
  } catch (err) {
    hideBlockingOverlay();
    return { ok: false, error: err.message };
  }
  if (info.status === "building") {
    const pct = info.files_total ? Math.round((info.files_done / info.files_total) * 100) : 0;
    restoreOverlayTextEl.textContent = info.files_total
      ? `Compressing thumbnails... ${info.files_done} / ${info.files_total}`
      : "Building backup...";
    restoreOverlayBarFillEl.style.width = `${pct}%`;
  } else if (info.status === "uploading") {
    const pct = info.bytes_total ? Math.round((info.bytes_done / info.bytes_total) * 100) : 0;
    restoreOverlayTextEl.textContent = info.bytes_total
      ? `Uploading backup... ${formatBytes(info.bytes_done)} / ${formatBytes(info.bytes_total)}`
      : "Uploading backup...";
    restoreOverlayBarFillEl.style.width = `${pct}%`;
  } else if (info.status === "pruning") {
    restoreOverlayTextEl.textContent = "Removing expired backups...";
    restoreOverlayBarFillEl.style.width = "100%";
  } else if (info.status === "done") {
    hideBlockingOverlay();
    return { ok: true };
  } else if (info.status === "error") {
    hideBlockingOverlay();
    return { ok: false, error: info.error || "Backup failed." };
  }

  await new Promise((resolve) => setTimeout(resolve, 300));
  return pollBackupStatus();
}

async function pollRestoreStatus() {
  const info = await apiFetch("/api/app-data-backup/restore-status");
  if (info.status === "downloading") {
    const pct = info.bytes_total ? Math.round((info.bytes_done / info.bytes_total) * 100) : 0;
    restoreOverlayTextEl.textContent = info.bytes_total
      ? `Downloading backup... ${formatBytes(info.bytes_done)} / ${formatBytes(info.bytes_total)}`
      : "Downloading backup...";
    restoreOverlayBarFillEl.style.width = `${pct}%`;
    setTimeout(pollRestoreStatus, 300);
  } else if (info.status === "restoring") {
    const pct = info.thumbnails_total ? Math.round((info.thumbnails_done / info.thumbnails_total) * 100) : 0;
    restoreOverlayTextEl.textContent = info.thumbnails_total
      ? `Restoring thumbnails... ${info.thumbnails_done} / ${info.thumbnails_total}`
      : "Restoring index...";
    restoreOverlayBarFillEl.style.width = `${pct}%`;
    setTimeout(pollRestoreStatus, 300);
  } else if (info.status === "done") {

    restoreOverlayTextEl.textContent = "Done - reloading...";
    restoreOverlayBarFillEl.style.width = "100%";
    window.location.reload();
  } else if (info.status === "error") {
    hideBlockingOverlay();
    alert(info.error || "Restore failed.");
  } else {

    setTimeout(pollRestoreStatus, 300);
  }
}

backupPanelEl.addEventListener("click", async (e) => {
  if (e.target.closest(".version-panel-close")) {
    closeBackupPanel();
    return;
  }
  const btn = e.target.closest("button[data-action='restore']");
  if (!btn) return;
  if (!window.confirm("This overwrites your local folder structure, file index, and thumbnail cache with this backup's contents. Continue?")) return;

  showBlockingOverlay("Restoring backup...");
  try {
    await apiFetch(`/api/app-data-backup/snapshots/${btn.dataset.messageId}/restore`, { method: "POST" });
    pollRestoreStatus();
  } catch (err) {
    hideBlockingOverlay();
    alert(err.message);
  }
});

document.getElementById("open-backup-history-btn").addEventListener("click", openBackupPanel);

async function loadInterruptedUploads() {
  try {
    const data = await apiFetch("/api/transfers/interrupted");
    if (!data.uploads.length) return;

    const pendingUploads = data.uploads.map((u) => ({ ...u, relative_path: u.relative_path || u.filename }));
    const { rootFiles, folders } = buildFolderTree(pendingUploads);
    rootFiles.forEach(renderInterruptedUploadRow);
    for (const [, folder] of folders) renderInterruptedFolderSubtree(folder);

    updateTransfersUI();
  } catch (err) {

  }
}

function renderInterruptedFolderSubtree(folder) {
  const { childrenContainer } = renderFolderRow(folder.sourcePath, folder.vaultPath, folder.files.length, folderIdResolverFor(folder));
  for (const { pending } of folder.files) {
    renderInterruptedUploadRow(pending, childrenContainer);
  }
  for (const [, sub] of folder.subfolders) {
    renderInterruptedFolderSubtree(sub);
  }
}

function renderMergedFolderSubtree(folder) {
  const { childrenContainer } = renderFolderRow(folder.sourcePath, folder.vaultPath, folder.files.length, folderIdResolverFor(folder));
  for (const { pending } of folder.files) {
    if (pending._kind === "interrupted") {
      renderInterruptedUploadRow(pending, childrenContainer);
    } else {
      renderQueuedUploadRow(pending, childrenContainer);
    }
  }
  for (const [, sub] of folder.subfolders) {
    renderMergedFolderSubtree(sub);
  }
}

function renderInterruptedUploadRow(u, container) {
  const doneText = `${formatBytes(u.bytes_done)} / ${formatBytes(u.bytes_total)}`;
  const row = renderUploadRow(u.filename, `Paused · ${doneText}`);
  if (container) container.appendChild(row);
  row.classList.add("upload-paused");

  row.dataset.uploadId = u.id;
  const actions = [{ label: "Dismiss", onClick: () => dismissInterruptedUpload(u.id, row) }];
  if (u.resumable) {
    actions.unshift({ label: "Continue", onClick: () => continueInterruptedUpload(u.id, u.filename, row) });
  } else {

    row.querySelector(".upload-status").textContent = `Paused · ${doneText} - source file has moved or changed, can't resume`;
  }
  setRowActions(row, actions);
}

async function continueInterruptedUpload(id, filename, row) {
  setRowActions(row, []);
  try {
    const data = await apiFetch(`/api/uploads/interrupted/${id}/continue`, { method: "POST" });
    row.classList.remove("upload-paused");

    await runNativeUploadAttempt(data.upload_id, row);
  } catch (err) {
    row.querySelector(".upload-status").textContent = err.message;
    row.classList.add("upload-error");
    setRowActions(row, [{ label: "Dismiss", onClick: () => dismissRow(row) }]);
  }
}

async function dismissInterruptedUpload(id, row) {
  setRowActions(row, []);
  try {
    await apiFetch(`/api/uploads/interrupted/${id}/cancel`, { method: "POST" });
  } catch (err) {
    alert(err.message);
  }
  dismissRow(row);
}

function syncPairCardHtml(pair, files) {
  const pairFiles = files.filter((f) => f.sync_pair_id === pair.id);
  const changed = pairFiles.filter((f) => f.status === "changed");
  const synced = pairFiles.filter((f) => f.status === "synced");
  const paused = pair.paused !== false;
  const mode = pair.reupload_mode || "flag";
  const modeLabel = mode === "version" ? "Upload new version" : mode === "soft_delete" ? "New file + soft delete old" : mode === "new_file" ? "Upload as new file only" : "Flag only (no re-upload)";
  const statusText = paused
    ? "Paused."
    : (pair.watching ? "Watching - new files upload automatically." : "Active, but not currently watching (folder may be missing).");
  const lastSync = synced.length ? synced.reduce((a, b) => a.last_synced_at > b.last_synced_at ? a : b).last_synced_at : null;
  const lastSyncStr = lastSync ? new Date(lastSync).toLocaleString() : "Never";
  const changedHtml = changed.length
    ? `
      <p class="step-hint sync-changed-hint">${changed.length} file${changed.length === 1 ? "" : "s"} changed locally since last sync - ${mode === "flag" ? "not re-uploaded automatically" : "will re-upload on next cycle"}:</p>
      <p class="step-hint sync-changed-hint">${changed.map((f) => escapeHtml(f.local_path)).join("<br>")}</p>
    `
    : "";
  return `
    <div class="sync-pair-card" data-id="${pair.id}">
      <div class="sync-pair-header">
        <div class="sync-pair-info">
          <div class="sync-pair-path" title="${escapeHtml(pair.local_path)}">${escapeHtml(pair.local_path) || "(no folder set)"}</div>
          <div class="sync-pair-sub">&rarr; ${escapeHtml(folderDisplayPath(pair.folder_id))} &middot; ${escapeHtml(statusText)}</div>
        </div>
        <div class="sync-pair-actions">
          <button type="button" class="sync-pair-delete">Remove</button>
        </div>
      </div>
      <div class="sync-pair-stats" style="display:flex;gap:var(--space-4);margin-top:var(--space-2);font-size:0.78rem;color:var(--ink-faint)">
        <span>${synced.length} file${synced.length === 1 ? "" : "s"} synced</span>
        <span>Last sync: ${escapeHtml(lastSyncStr)}</span>
        ${pair.pending_count ? `<span style="color:var(--accent-deep)">${pair.pending_count} file${pair.pending_count === 1 ? "" : "s"} left to sync</span>` : ""}

        ${changed.length ? `<span style="color:var(--accent-deep)">${changed.length} changed locally</span>` : ""}
      </div>

      <div class="sync-pair-options">
        <label class="toggle-switch"><input type="checkbox" class="sync-pair-toggle"${paused ? " checked" : ""}> <span class="toggle-label">Pause</span><span class="toggle-track"></span></label>

        <label class="toggle-switch"><input type="checkbox" class="sync-pair-exclude-dot-files"${pair.exclude_dot_files !== false ? " checked" : ""}> <span class="toggle-label">Exclude dot files (recommended)</span><span class="toggle-track"></span></label>

        ${mode !== "flag" ? `<p class="step-hint" style="margin:0;font-size:0.78rem">On local change: ${modeLabel}</p>` : ""}
        <select class="sync-pair-reupload-mode">
          <option value="flag"${mode === "flag" ? " selected" : ""}>Flag only (no re-upload)</option>

          <option value="version"${mode === "version" ? " selected" : ""}>Upload new version</option>

          <option value="soft_delete"${mode === "soft_delete" ? " selected" : ""}>New file + soft delete old</option>

          <option value="new_file"${mode === "new_file" ? " selected" : ""}>Upload as new file only</option>

        </select>

      </div>

      ${changedHtml}
    </div>

  `;
}

let syncPairsCount = 0;

async function loadSyncView() {
  const listEl = document.getElementById("sync-pairs-list");
  const badgeEl = document.getElementById("sync-badge");
  try {
    const result = await apiFetch("/api/sync/pairs");
    const pairs = result.pairs || [];
    const files = result.files || [];
    syncPairsCount = pairs.length;
    listEl.innerHTML = pairs.length
      ? pairs.map((p) => syncPairCardHtml(p, files)).join("")
      : `<p class="step-hint">No sync folders yet - <a href="#" class="sync-empty-create-link">create one</a>.</p>`;
    const changedCount = files.filter((f) => f.status === "changed").length;
    badgeEl.textContent = changedCount || "";
    badgeEl.classList.toggle("hide", changedCount === 0);
  } catch (err) {
    listEl.innerHTML = `<p class="step-error">${escapeHtml(err.message)}</p>`;

    badgeEl.classList.add("hide");
  }
}

let lastSyncUploads = [];
let syncTransfersSearchQuery = "";

const syncTransfersCollapsedFolders = new Set();

async function loadSyncTransfersView() {
  const uploadsEl = document.getElementById("sync-transfers-list");
  const badgeEl = document.getElementById("sync-transfers-badge");
  if (!uploadsEl) return;

  if (syncPairsCount === 0) {
    lastSyncUploads = [];
    renderSyncTransfersList();
    updateSyncTransfersUI();
    badgeEl.classList.add("hide");
    return;
  }
  try {
    const syncUploads = await apiFetch("/api/sync/uploads");
    lastSyncUploads = syncUploads || [];
    renderSyncTransfersList();
    updateSyncTransfersUI();
    const activeCount = lastSyncUploads.filter((u) => u.status === "uploading" || u.status === "queued").length;
    badgeEl.textContent = activeCount || "";
    badgeEl.classList.toggle("hide", activeCount === 0);
  } catch (err) {
    uploadsEl.innerHTML = `<p class="step-error">${escapeHtml(err.message)}</p>`;
    badgeEl.classList.add("hide");
  }
}

function renderSyncTransfersList() {
  const uploadsEl = document.getElementById("sync-transfers-list");
  if (!uploadsEl) return;
  uploadsEl.innerHTML = renderSyncTransfers(lastSyncUploads);
  updateSyncTransfersUI();
}

function _syncTransferPriority(u) {
  if (u.status === "uploading") return 0;
  if (u.status === "queued") return 1;
  if (u.status === "error" || u.status === "duplicate") return 2;
  if (u.status === "done") return 3;
  return 4;
}

function renderSyncTransfers(uploads) {
  if (syncPairsCount === 0) {
    return `<p class="step-hint">No sync folders configured. <a href="#" onclick="switchView('sync'); return false;">Create a sync folder</a> to start syncing files.</p>`;
  }
  if (!uploads || uploads.length === 0) {
    return `<p class="step-hint">No active sync uploads. New files in watched folders will appear here when they start uploading.</p>`;
  }
  const query = syncTransfersSearchQuery.trim().toLowerCase();
  const filtered = query
    ? uploads.filter((u) =>
        (u.filename || "").toLowerCase().includes(query) ||
        (u.relative_path || "").toLowerCase().includes(query))
    : uploads;
  if (filtered.length === 0) {
    return `<p class="step-hint">No sync uploads match "${escapeHtml(syncTransfersSearchQuery)}".</p>`;
  }

  const sorted = [...filtered].sort((a, b) => _syncTransferPriority(a) - _syncTransferPriority(b));
  const { rootFiles, folders } = buildFolderTree(sorted);
  let html = rootFiles.map((u) => syncTransferRowHtml(u)).join("");
  html += [...folders.values()].map((folder) => syncTransferFolderHtml(folder)).join("");
  return html;
}

function _countFolderFiles(folder) {
  let count = folder.files.length;
  for (const sub of folder.subfolders.values()) count += _countFolderFiles(sub);
  return count;
}

const _syncRateSamples = new Map();

function _syncTransferEta(u, key) {
  if (u.status !== "uploading" || !u.bytes_total) {
    _syncRateSamples.delete(key);
    return "";
  }
  const done = u.bytes_done || 0;
  const remaining = u.bytes_total - done;
  if (remaining <= 0) return "";
  const now = Date.now();
  const prev = _syncRateSamples.get(key);

  if (!prev || done < prev.bytes) {
    _syncRateSamples.set(key, { bytes: done, time: now, rate: 0 });
    return "";
  }
  const elapsed = (now - prev.time) / 1000;
  if (elapsed < 0.5) {

    return prev.rate > 0 ? `${formatDuration(remaining / prev.rate)} left` : "";
  }
  const instantRate = (done - prev.bytes) / elapsed;
  const rate = prev.rate > 0 ? prev.rate * 0.7 + instantRate * 0.3 : instantRate;
  _syncRateSamples.set(key, { bytes: done, time: now, rate });
  return rate > 0 ? `${formatDuration(remaining / rate)} left` : "";
}

function syncTransferRowHtml(u) {
  const pct = u.bytes_total ? Math.round((u.bytes_done / u.bytes_total) * 100) : 0;
  const statusLabel = u.status === "uploading" ? "Uploading" : u.status === "queued" ? "Queued" : u.status === "done" ? "Done" : u.status === "error" ? "Error" : u.status === "duplicate" ? "Duplicate" : u.status;

  const detail = [statusLabel];
  if (u.bytes_total) detail.push(`${formatBytes(u.bytes_done || 0)} / ${formatBytes(u.bytes_total)}`);
  detail.push(`${pct}%`);
  const eta = _syncTransferEta(u, u.id || u.local_path || u.filename);
  if (eta) detail.push(eta);
  return `
    <div class="sync-transfer-row">
      <div class="sync-transfer-info">
        <div class="sync-transfer-filename" title="${escapeHtml(u.filename || "")}">${escapeHtml(u.filename || "Unknown file")}</div>
        <div class="sync-transfer-status">${escapeHtml(detail.join(" · "))}</div>
      </div>
      <div class="sync-transfer-bar">
        <div class="sync-transfer-bar-fill" style="width: ${pct}%"></div>
      </div>
    </div>
  `;
}

function syncTransferFolderHtml(folder) {
  const total = _countFolderFiles(folder);
  const collapsed = syncTransfersCollapsedFolders.has(folder.path);
  const childrenHtml = folder.files.map(({ pending }) => syncTransferRowHtml(pending)).join("")
    + [...folder.subfolders.values()].map((sub) => syncTransferFolderHtml(sub)).join("");
  return `
    <div class="sync-transfer-folder" data-folder-path="${escapeHtml(folder.path)}">
      <div class="sync-transfer-folder-row">
        <button type="button" class="sync-transfer-folder-toggle" data-collapsed="${collapsed}">${collapsed ? "▶" : "▼"}</button>
        <span class="sync-transfer-folder-icon" aria-hidden="true">📁</span>
        <span class="sync-transfer-folder-name" title="${escapeHtml(folder.sourcePath)}">${escapeHtml(folder.name)}</span>
        <span class="sync-transfer-folder-count">${total} file${total === 1 ? "" : "s"}</span>
      </div>
      <div class="sync-transfer-folder-children${collapsed ? " collapsed" : ""}">
        ${childrenHtml}
      </div>
    </div>
  `;
}

document.getElementById("sync-transfers-search-input").addEventListener("input", (e) => {
  syncTransfersSearchQuery = e.target.value;
  renderSyncTransfersList();
});

transfersSearchInputEl.addEventListener("input", (e) => {
  transfersSearchQuery = e.target.value;
  updateTransfersUI();
});

transfersSearchAllToggleEl.addEventListener("change", (e) => {
  transfersSearchAllTabs = e.target.checked;
  updateTransfersUI();
});

document.querySelectorAll(".transfers-subtab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    transfersSubTab = btn.dataset.subtab;
    updateTransfersUI();
  });
});

document.getElementById("sync-transfers-list").addEventListener("click", (e) => {
  const toggle = e.target.closest(".sync-transfer-folder-toggle");
  if (!toggle) return;
  const folderEl = toggle.closest(".sync-transfer-folder");
  const path = folderEl.dataset.folderPath;
  if (syncTransfersCollapsedFolders.has(path)) syncTransfersCollapsedFolders.delete(path);
  else syncTransfersCollapsedFolders.add(path);
  renderSyncTransfersList();
});

function updateSyncTransfersUI() {
  const clearFinishedBtn = document.getElementById("sync-clear-finished-btn");
  if (!clearFinishedBtn) return;
  const finishedCount = lastSyncUploads.filter((u) => u.status === "done" || u.status === "duplicate" || u.status === "error").length;
  clearFinishedBtn.classList.toggle("hide", finishedCount === 0);
}

document.getElementById("sync-clear-finished-btn").addEventListener("click", async () => {
  try {
    await apiFetch("/api/sync/uploads/clear-finished", { method: "POST" });
    await loadSyncTransfersView();
  } catch (err) {
    alert(err.message);
  }
});

document.getElementById("sync-pairs-list").addEventListener("click", async (e) => {
  const createLink = e.target.closest(".sync-empty-create-link");
  if (createLink) {
    e.preventDefault();

    e.stopPropagation();
    openSyncCreatePanel();
    return;
  }

  const card = e.target.closest(".sync-pair-card");
  if (!card) return;
  const pairId = card.dataset.id;

  const toggleSwitch = e.target.closest(".toggle-switch");
  if (toggleSwitch) {
    const input = toggleSwitch.querySelector("input");
    if (input && input.classList.contains("sync-pair-toggle")) {
      try {
        await apiFetch(`/api/sync/pairs/${pairId}`, {
          method: "PUT", body: JSON.stringify({ paused: input.checked }),
        });
      } catch (err) { alert(err.message); }
      loadSyncView();
      return;
    }
    if (input && input.classList.contains("sync-pair-exclude-dot-files")) {
      try {
        await apiFetch(`/api/sync/pairs/${pairId}`, {
          method: "PUT", body: JSON.stringify({ exclude_dot_files: input.checked }),
        });
      } catch (err) { alert(err.message); }
      loadSyncView();
      return;
    }
  }

  const modeSelect = e.target.closest(".sync-pair-reupload-mode");
  if (modeSelect) {

    return;
  }

  if (e.target.classList.contains("sync-pair-delete")) {
    if (!confirm("Remove this sync folder? It stops watching immediately - files already uploaded stay in the vault.")) return;
    try {
      await apiFetch(`/api/sync/pairs/${pairId}`, { method: "DELETE" });
    } catch (err) {
      alert(err.message);
    }
    loadSyncView();
  }
});

document.getElementById("sync-pairs-list").addEventListener("change", async (e) => {
  const modeSelect = e.target.closest(".sync-pair-reupload-mode");
  if (!modeSelect) return;
  const card = modeSelect.closest(".sync-pair-card");
  if (!card) return;
  const pairId = card.dataset.id;
  try {
    await apiFetch(`/api/sync/pairs/${pairId}`, {
      method: "PUT", body: JSON.stringify({ reupload_mode: modeSelect.value }),
    });
  } catch (err) { alert(err.message); }
  loadSyncView();
});

let _syncCreateFolderId = null;

function closeSyncCreatePanel() {
  syncCreatePanelEl.classList.add("hide");
  syncCreatePanelEl.innerHTML = "";
  _syncCreateFolderId = null;
}

function openSyncCreatePanel() {
  _syncCreateFolderId = null;
  syncCreatePanelEl.innerHTML = `
    <div class="version-panel-content">
      <div class="version-panel-header">
        <span class="version-panel-title">Add sync folder</span>
        <button type="button" class="version-panel-close" aria-label="Close">&times;</button>
      </div>
      <div class="sync-create-form">
        <label>Local folder
          <span class="sync-create-path-row">
            <input type="text" id="sync-create-local-path" placeholder="C:\\Users\\you\\Videos\\ToUpload">
            <button type="button" id="sync-create-pick-btn">Select</button>
          </span>
        </label>
        <label>Destination folder
          <span class="sync-create-path-row">
            <input type="text" id="sync-create-folder-display" readonly placeholder="Root" style="flex:1;cursor:default">
            <button type="button" id="sync-create-browse-folder-btn">Browse</button>
          </span>
        </label>
        <div class="sync-pair-options">
          <label class="toggle-switch"><input type="checkbox" id="sync-create-paused" checked> <span class="toggle-label">Pause</span><span class="toggle-track"></span></label>
          <label class="toggle-switch"><input type="checkbox" id="sync-create-exclude-dot-files" checked> <span class="toggle-label">Exclude dot files (recommended)</span><span class="toggle-track"></span></label>
          <label>On local file change<select id="sync-create-reupload-mode" style="padding:6px 8px;border-radius:6px;border:1px solid var(--line);background:var(--surface);font-family:var(--sys);font-size:0.82rem;color:var(--ink)">
          <option value="flag" selected>Flag only (no re-upload)</option>
          <option value="version">Upload new version</option>
          <option value="soft_delete">New file + soft delete old</option>
          <option value="new_file">Upload as new file only</option>
        </select></label>
        </div>
        <p class="step-error" id="sync-create-error"></p>
        <div class="sync-create-actions">
          <button type="button" id="sync-create-cancel-btn">Cancel</button>
          <button type="button" id="sync-create-submit-btn">Create</button>
        </div>
      </div>
    </div>
  `;
  syncCreatePanelEl.classList.remove("hide");
  var _btn = document.getElementById("sync-create-browse-folder-btn");
  if (_btn && !_btn._fpAttached) {
    _btn._fpAttached = true;
    _btn.addEventListener("click", function _browseClick() {
      openFolderPicker(function(targetId) {
        _syncCreateFolderId = targetId;
        var _el = document.getElementById("sync-create-folder-display");
        if (_el) _el.value = _syncCreateFolderId === null ? "Root" : (folders.find(function(f) { return f.id === _syncCreateFolderId; })?.name || "Root");
      });
    });
  }
}

document.getElementById("open-sync-create-btn").addEventListener("click", (e) => {

  e.stopPropagation();
  openSyncCreatePanel();
});

syncCreatePanelEl.addEventListener("click", async (e) => {
  if (e.target.closest(".version-panel-close") || e.target.closest("#sync-create-cancel-btn")) {
    closeSyncCreatePanel();
    return;
  }

  if (e.target.closest("#sync-create-pick-btn")) {
    const result = await apiFetch("/api/pick-folder", { method: "POST" });
    if (result.path) {
      document.getElementById("sync-create-local-path").value = result.path;
    }

    return;
  }

  if (e.target.closest("#sync-create-submit-btn")) {
    const errorEl = document.getElementById("sync-create-error");
    const localPathInput = document.getElementById("sync-create-local-path");
    const localPath = localPathInput.value.trim();
    const folderId = _syncCreateFolderId;
    const paused = document.getElementById("sync-create-paused").checked;
    const excludeDotFiles = document.getElementById("sync-create-exclude-dot-files").checked;
    const reuploadMode = document.getElementById("sync-create-reupload-mode").value;
    errorEl.textContent = "";
    try {
      await apiFetch("/api/sync/pairs", {
        method: "POST",
        body: JSON.stringify({
          local_path: localPath, folder_id: folderId, paused,
          exclude_dot_files: excludeDotFiles,
          reupload_mode: reuploadMode,
        }),
      });
      closeSyncCreatePanel();
      loadSyncView();
    } catch (err) {
      errorEl.textContent = err.message;
    }
  }
});

function updateRailFoot(status) {

  if (status.app_version && status.app_version.full) _aboutVersion = status.app_version.full;
  if (status.connected && status.archive_chat_title) {
    railFootEl.textContent = `Connected · ${status.archive_chat_title}`;
    _aboutArchiveTitle = status.archive_chat_title;
  } else if (status.connected) {
    railFootEl.textContent = "Connected · no archive group yet";
  } else {
    railFootEl.textContent = "Not connected to Telegram yet";
  }
}

async function refreshStats() {
  try {
    const stats = await apiFetch("/api/stats");
    railStorageEl.textContent = `${formatBytes(stats.total_current_bytes)} total`;
    const versionedEl = document.getElementById("status-versioned-size");
    const hintEl = document.getElementById("versioned-size-hint");
    if (versionedEl) versionedEl.textContent = formatBytes(stats.total_versioned_bytes);
    if (hintEl) {
      hintEl.textContent = stats.versioned_file_count
        ? `${stats.versioned_file_count} of ${stats.file_count} files have version history, adding this much beyond their current size.`
        : `None of your ${stats.file_count} files have more than one version yet.`;
    }

    const totalEl = document.getElementById("status-total-size");
    if (totalEl) totalEl.textContent = formatBytes(stats.total_current_bytes + stats.total_versioned_bytes);
  } catch (err) {

  }
  try {
    const cacheStats = await apiFetch("/api/cache/summary");
    const cacheEl = document.getElementById("status-cache-size");
    if (cacheEl) cacheEl.textContent = formatBytes(cacheStats.bytes);
  } catch (err) {

  }
}

async function loadTelegramStatus() {
  try {
    const status = await apiFetch("/api/telegram/status");
    updateRailFoot(status);
    if (status.connected && status.archive_chat_id) {
      showSettingsConnected(status);
      settingsLoaded = true;
    } else if (status.connected) {
      showSettingsStep("archive");
      settingsLoaded = true;
    } else {

      prefillConnectStep(status);
      showSettingsStep("connect");
    }
  } catch (err) {

  }
}

function prefillConnectStep(status) {
  const idEl = document.getElementById("f-api-id");
  const hashEl = document.getElementById("f-api-hash");
  const phoneEl = document.getElementById("f-phone");
  if (idEl && !idEl.value && status.api_id) idEl.value = status.api_id;
  if (hashEl && !hashEl.value && status.api_hash) hashEl.value = status.api_hash;
  if (phoneEl && !phoneEl.value && status.phone_number) phoneEl.value = status.phone_number;
}

document.getElementById("step-connect").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("connect-error");
  errorEl.textContent = "";
  try {
    const apiId = document.getElementById("f-api-id").value.trim();
    const apiHash = document.getElementById("f-api-hash").value.trim();
    const phone = document.getElementById("f-phone").value.trim();
    await apiFetch("/api/telegram/connect", {
      method: "POST",
      body: JSON.stringify({ api_id: apiId, api_hash: apiHash, phone_number: phone }),
    });
    showSettingsStep("code");
  } catch (err) {
    errorEl.textContent = err.message;
  }
});

document.getElementById("step-code").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("code-error");
  errorEl.textContent = "";
  try {
    const code = document.getElementById("f-code").value.trim();
    const result = await apiFetch("/api/telegram/code", { method: "POST", body: JSON.stringify({ code }) });
    showSettingsStep(result.step === "password" ? "password" : "archive");
  } catch (err) {
    errorEl.textContent = err.message;
  }
});

document.getElementById("step-password").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("password-error");
  errorEl.textContent = "";
  try {
    const password = document.getElementById("f-password").value;
    await apiFetch("/api/telegram/password", { method: "POST", body: JSON.stringify({ password }) });
    showSettingsStep("archive");
  } catch (err) {
    errorEl.textContent = err.message;
  }
});

function _handleScanResult(item) {
  const chatId = parseInt(item.dataset.chatId);
  const title = item.dataset.chatTitle;
  (async () => {
    try {
      await apiFetch("/api/telegram/set-archive", { method: "POST", body: JSON.stringify({ chat_id: chatId, title }) });
      const status = await apiFetch("/api/telegram/status");
      updateRailFoot(status);
      showSettingsConnected(status);
    } catch (err) { document.getElementById("archive-error").textContent = err.message; }
  })();
}

document.getElementById("scan-archives-btn").addEventListener("click", async () => {
  const errorEl = document.getElementById("archive-error");
  const resultsEl = document.getElementById("scan-results");
  errorEl.textContent = "";
  resultsEl.classList.add("hide");
  resultsEl.innerHTML = '<p class="step-hint" style="padding:8px 0">Scanning...</p>';
  try {
    const data = await apiFetch("/api/telegram/scan-archives", { method: "POST" });
    if (!data.ok) { errorEl.textContent = data.error; return; }
    const cands = data.candidates || [];
    if (!cands.length) {
      resultsEl.innerHTML = '<p class="step-hint" style="padding:8px 0">No existing archive groups found. Create one below.</p>';
    } else {
      resultsEl.innerHTML = cands.map((c) =>
        '<div class="scan-archive-item" data-chat-id="'+c.id+'" data-chat-title="'+escapeHtml(c.title)+'" style="padding:8px 10px;border-radius:8px;border:1px solid var(--line);cursor:pointer;display:flex;align-items:center;justify-content:space-between">'+
          '<span>'+escapeHtml(c.title)+'</span>'+
          '<span style="font-size:0.78rem;color:var(--ink-faint)">'+c.participant_count+' members</span>'+
        '</div>'
      ).join("");
      resultsEl.classList.remove("hide");
    }
  } catch (err) { errorEl.textContent = err.message; }
});

document.getElementById("scan-results").addEventListener("click", async (e) => {
  const item = e.target.closest(".scan-archive-item");
  if (item) _handleScanResult(item);
});

document.getElementById("settings-scan-archives-btn").addEventListener("click", async () => {
  const resultsEl = document.getElementById("settings-scan-results");
  resultsEl.classList.add("hide");
  resultsEl.innerHTML = '<p class="step-hint" style="padding:8px 0">Scanning...</p>';
  try {
    const data = await apiFetch("/api/telegram/scan-archives", { method: "POST" });
    if (!data.ok) { resultsEl.innerHTML = '<p class="step-hint" style="padding:8px 0;color:var(--danger-deep)">'+escapeHtml(data.error)+'</p>'; return; }
    const cands = data.candidates || [];
    if (!cands.length) {
      resultsEl.innerHTML = '<p class="step-hint" style="padding:8px 0">No existing archive groups found.</p>';
    } else {
      resultsEl.innerHTML = cands.map((c) =>
        '<div class="scan-archive-item" data-chat-id="'+c.id+'" data-chat-title="'+escapeHtml(c.title)+'" style="padding:8px 10px;border-radius:8px;border:1px solid var(--line);cursor:pointer;display:flex;align-items:center;justify-content:space-between">'+
          '<span>'+escapeHtml(c.title)+'</span>'+
          '<span style="font-size:0.78rem;color:var(--ink-faint)">'+c.participant_count+' members</span>'+
        '</div>'
      ).join("");
      resultsEl.classList.remove("hide");
    }
  } catch (err) { resultsEl.innerHTML = '<p class="step-hint" style="padding:8px 0;color:var(--danger-deep)">'+escapeHtml(err.message)+'</p>'; }
});

document.getElementById("settings-scan-results").addEventListener("click", async (e) => {
  const item = e.target.closest(".scan-archive-item");
  if (item) _handleScanResult(item);
});

document.getElementById("step-archive").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("archive-error");
  errorEl.textContent = "";
  try {
    const title = document.getElementById("f-archive-title").value.trim();
    await apiFetch("/api/telegram/create-archive", { method: "POST", body: JSON.stringify({ title }) });
    const status = await apiFetch("/api/telegram/status");
    updateRailFoot(status);
    showSettingsConnected(status);
  } catch (err) {
    errorEl.textContent = err.message;
  }
});

function switchView(view) {
  if (view !== "explorer" && selectionActive()) {
    clearSelection();
    renderGrid();
  }
  if (view !== "trash" && trashSelectionActive()) {
    trashClearSelection();
  }

  const nextSmartView = SMART_VIEWS[view] ? view : null;
  if (!nextSmartView && smartSelectionActive()) {
    smartClearSelection();
  }
  if (nextSmartView !== currentSmartView) {
    if (smartSelectionActive()) smartClearSelection();
  }
  const targetId = SMART_VIEWS[view] ? "smart" : view;
  views.forEach((v) => v.classList.toggle("hide", v.id !== `view-${targetId}`));
  document.querySelectorAll(".rail-item").forEach((b) => b.classList.toggle("active", b.dataset.view === view));

  const showRailCount = view === "explorer" || view === "trash" || !!SMART_VIEWS[view];
  railCountEl.classList.toggle("hide", !showRailCount);

  if (view === "explorer" || SMART_VIEWS[view]) {
    _applySortContext(SMART_VIEWS[view] ? view : "explorer");
  }
  if (view === "explorer") renderGrid();
  if (nextSmartView !== currentSmartView) {
    smartSearchQuery = "";
    smartSearchInputEl.value = "";
  }
  currentSmartView = nextSmartView;
  if (currentSmartView) renderSmartView(currentSmartView);

  if (view === "trash") {
    if (trashLoaded) renderTrash(trashFoldersCache, trashFilesCache);
    else loadTrash();
  }
  if (view === "settings") {
    if (!settingsLoaded) {
      loadTelegramStatus();
    } else {

      refreshArchiveCheck();
    }
  }
  if (view === "sync") {
    loadSyncView();

    if (!syncViewPolling) {
      syncViewPolling = setInterval(() => {

        if (currentView() === "sync") {
          loadSyncView();
        } else {
          clearInterval(syncViewPolling);
          syncViewPolling = null;
        }
      }, 3000);
    }
  }
  if (view === "sync-transfers") {
    loadSyncTransfersView();

    if (!syncTransfersViewPolling) {
      syncTransfersViewPolling = setInterval(() => {

        if (currentView() === "sync-transfers") {
          loadSyncTransfersView();
        } else {
          clearInterval(syncTransfersViewPolling);
          syncTransfersViewPolling = null;
        }
      }, 3000);
    }
  }
  history.replaceState(null, "", `#${view}`);
}

let syncViewPolling = null;
let syncTransfersViewPolling = null;

function currentView() {
  const hash = location.hash.slice(1);
  return hash || "explorer";
}

railEl.addEventListener("click", (e) => {
  const btn = e.target.closest(".rail-item");
  if (!btn) return;
  switchView(btn.dataset.view);
});

let viewMode = localStorage.getItem("viewMode") === "list" ? "list" : "grid";
const viewToggleBtn = document.getElementById("view-toggle-btn");
const smartViewToggleBtn = document.getElementById("smart-view-toggle-btn");
const trashViewToggleBtn = document.getElementById("trash-view-toggle-btn");

const viewToggleBtns = [viewToggleBtn, smartViewToggleBtn, trashViewToggleBtn];

function applyViewMode() {
  const isList = viewMode === "list";
  gridEl.classList.toggle("list-view", isList);
  smartGridEl.classList.toggle("list-view", isList);
  document.getElementById("grid-list-header").classList.toggle("show", isList);
  document.getElementById("smart-list-header").classList.toggle("show", isList);

  document.getElementById("grid-sort-control").classList.toggle("show", !isList);
  document.getElementById("smart-sort-control").classList.toggle("show", !isList);
  const nextIcon = isList ? "layout-grid" : "list";
  viewToggleBtns.forEach((btn) => {
    btn.innerHTML = `<i data-lucide="${nextIcon}"></i>`;
    btn.title = isList ? "Grid view" : "List view";
  });

  if (trashLoaded) renderTrash(trashFoldersCache, trashFilesCache);
  lucide.createIcons();
}

function toggleViewMode() {
  viewMode = viewMode === "grid" ? "list" : "grid";
  localStorage.setItem("viewMode", viewMode);
  applyViewMode();
}

viewToggleBtns.forEach((btn) => btn.addEventListener("click", toggleViewMode));

const GRID_SIZE_STEPS = [
  { minWidth: 50, thumbSize: 14, listRowPadding: 2, listThumbSize: 14 },
  { minWidth: 65, thumbSize: 18, listRowPadding: 2, listThumbSize: 14 },
  { minWidth: 80, thumbSize: 20, listRowPadding: 2, listThumbSize: 14 },
  { minWidth: 100, thumbSize: 24, listRowPadding: 2, listThumbSize: 14 },
  { minWidth: 120, thumbSize: 32, listRowPadding: 3, listThumbSize: 16 },
  { minWidth: 140, thumbSize: 44, listRowPadding: 5, listThumbSize: 17 },
  { minWidth: 160, thumbSize: 56, listRowPadding: 7, listThumbSize: 18 },
  { minWidth: 190, thumbSize: 76, listRowPadding: 10, listThumbSize: 23 },
  { minWidth: 220, thumbSize: 96, listRowPadding: 13, listThumbSize: 28 },
  { minWidth: 260, thumbSize: 120, listRowPadding: 16, listThumbSize: 32 },
  { minWidth: 300, thumbSize: 144, listRowPadding: 19, listThumbSize: 36 },
];

const GRID_SIZE_PRESET_STEPS = { small: 4, medium: 6, large: 8 };
const DEFAULT_GRID_SIZE_STEP = GRID_SIZE_PRESET_STEPS.medium;

function _stepNearestWidth(width) {
  let best = DEFAULT_GRID_SIZE_STEP;
  let bestDistance = Infinity;
  GRID_SIZE_STEPS.forEach((step, index) => {
    const distance = Math.abs(step.minWidth - width);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = index;
    }
  });
  return best;
}

function _readStoredGridSizeStep() {

  const width = parseInt(localStorage.getItem("gridSizeWidth"), 10);
  if (Number.isInteger(width)) return _stepNearestWidth(width);

  const legacyIndex = parseInt(localStorage.getItem("gridSizeStep"), 10);
  const ORIGINAL_STEP_WIDTHS = [100, 120, 140, 160, 190, 220, 260, 300];
  if (Number.isInteger(legacyIndex) && ORIGINAL_STEP_WIDTHS[legacyIndex] !== undefined) {
    return _stepNearestWidth(ORIGINAL_STEP_WIDTHS[legacyIndex]);
  }
  const legacyName = GRID_SIZE_PRESET_STEPS[localStorage.getItem("gridSize")];
  return legacyName === undefined ? DEFAULT_GRID_SIZE_STEP : legacyName;
}

let gridSizeStep = _readStoredGridSizeStep();
const gridSizeToggles = [
  document.getElementById("grid-size-toggle"),
  document.getElementById("smart-grid-size-toggle"),
  document.getElementById("trash-grid-size-toggle"),
].filter(Boolean);
const uiSizeSlider = document.getElementById("ui-size-slider");
const uiSizeValue = document.getElementById("ui-size-value");

function applyGridSize() {
  const step = GRID_SIZE_STEPS[gridSizeStep] || GRID_SIZE_STEPS[DEFAULT_GRID_SIZE_STEP];
  document.documentElement.style.setProperty("--card-min-width", `${step.minWidth}px`);
  document.documentElement.style.setProperty("--card-thumb-size", `${step.thumbSize}px`);
  document.documentElement.style.setProperty("--list-row-padding", `${step.listRowPadding}px`);
  document.documentElement.style.setProperty("--list-thumb-size", `${step.listThumbSize}px`);

  document.documentElement.classList.toggle("cards-compact", step.minWidth <= 100);
  document.documentElement.classList.toggle("cards-tiny", step.minWidth <= 80);

  gridSizeToggles.forEach((toggle) => {
    toggle.querySelectorAll(".grid-size-btn").forEach((btn) => {
      btn.classList.toggle("active", GRID_SIZE_PRESET_STEPS[btn.dataset.size] === gridSizeStep);
    });
  });
  if (uiSizeSlider) uiSizeSlider.value = String(gridSizeStep);
  if (uiSizeValue) uiSizeValue.textContent = `${step.minWidth}px`;
}

function setGridSizeStep(step) {
  const next = Math.min(GRID_SIZE_STEPS.length - 1, Math.max(0, Number(step)));
  if (!Number.isInteger(next) || next === gridSizeStep) return;
  gridSizeStep = next;
  localStorage.setItem("gridSizeWidth", String(GRID_SIZE_STEPS[gridSizeStep].minWidth));
  applyGridSize();
}

function setGridSize(size) {
  const step = GRID_SIZE_PRESET_STEPS[size];
  if (step === undefined) return;
  setGridSizeStep(step);
}

gridSizeToggles.forEach((toggle) => {
  toggle.addEventListener("click", (e) => {
    const btn = e.target.closest(".grid-size-btn");
    if (!btn) return;
    setGridSize(btn.dataset.size);
  });
});

if (uiSizeSlider) {
  uiSizeSlider.min = "0";
  uiSizeSlider.max = String(GRID_SIZE_STEPS.length - 1);

  uiSizeSlider.addEventListener("input", () => setGridSizeStep(uiSizeSlider.value));
}

function applyTransfersPosition(pos) {
  railEl.classList.toggle("transfers-bottom", pos === "footer");
}

function setTransfersPosition(pos) {
  const next = pos === "footer" ? "footer" : "nav";
  applyTransfersPosition(next);
  document.querySelectorAll(".pos-toggle-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.pos === next);
  });
  localStorage.setItem("transfersPosition", next);
}

function applyStoredTransfersPosition() {
  setTransfersPosition(localStorage.getItem("transfersPosition") === "footer" ? "footer" : "nav");
}

const transfersPositionToggleEl = document.getElementById("transfers-position-toggle");
if (transfersPositionToggleEl) {
  transfersPositionToggleEl.addEventListener("click", (e) => {
    const btn = e.target.closest(".pos-toggle-btn");
    if (!btn) return;
    setTransfersPosition(btn.dataset.pos);
  });
}

applyStoredTransfersPosition();

(async function initApp() {
  const loadStatusEl = document.getElementById("initial-load-status");
  try {
    const [foldersData, filesData] = await Promise.all([
      apiFetch("/api/folders"),
      apiFetch("/api/files"),
    ]);
    folders = foldersData;
    files = filesData;
    if (loadStatusEl) loadStatusEl.classList.add("hide");

    const validViews = ["explorer", "recent", "history", "starred", "trash", "sync", "settings"];
    const initialView = (location.hash || "").slice(1);
    switchView(validViews.includes(initialView) ? initialView : "explorer");
    renderAll();
    applyViewMode();
    _initSortHeaders();
    _initGridSortControls();
    applyGridSize();
    applyStoredSidebarWidth();
    applyStoredSidebarCollapsed();
    applyStoredRailWidth();
    applyStoredRailCollapsed();
    applyStoredTransfersPosition();
    applyResponsiveRailSize();
    applyResponsiveSidebarSize();
  } catch (err) {
    console.error("Failed to load initial folders/files:", err);
    if (loadStatusEl) {
      loadStatusEl.textContent = `Couldn't load your files: ${err.message}. Try restarting the app.`;
      loadStatusEl.classList.add("load-error");
      loadStatusEl.classList.remove("hide");
    }
  }
})();

apiFetch("/api/telegram/status").then(updateRailFoot).catch(() => {});
refreshStats();

setInterval(() => {
  refreshCurrent().catch(() => {});
}, 5 * 60 * 1000);

(async function checkAppDataBackupOnBoot() {
  try {
    const backupStatus = await fetchAppDataBackupStatus();
    if (!backupStatus.check_on_boot) return;
    const check = await apiFetch("/api/app-data-backup/check-latest");
    if (!check.newer_available) return;
    const when = formatDate(check.latest.date);
    const restore = window.confirm(
      `A newer app-data backup exists from ${when}. Restore it now? This overwrites your local folder structure, file index, and thumbnail cache. You can also do this later from Settings.`
    );
    if (!restore) return;

    showBlockingOverlay("Restoring backup...");

    await apiFetch(`/api/app-data-backup/snapshots/${check.latest.message_id}/restore`, { method: "POST" });
    pollRestoreStatus();
  } catch (err) {
    hideBlockingOverlay();

  }
})();

(async () => {
  try {
    const [interruptedData, queuedData] = await Promise.all([
      apiFetch("/api/transfers/interrupted"),
      apiFetch("/api/uploads/queued")
    ]);

    const allUploads = [
      ...interruptedData.uploads.map((u) => ({
        ...u,
        relative_path: u.relative_path || u.filename,
        _kind: "interrupted",
      })),
      ...queuedData.uploads.map((u) => ({
        ...u,
        relative_path: u.relative_path || u.filename,
        _kind: "queued",
      })),
    ];

    if (allUploads.length) {
      const { rootFiles, folders } = buildFolderTree(allUploads);
      rootFiles.forEach((u) => {
        if (u._kind === "interrupted") renderInterruptedUploadRow(u);
        else renderQueuedUploadRow(u);
      });
      for (const [, folder] of folders) renderMergedFolderSubtree(folder);
      updateTransfersUI();
    }

    queuedUploadsList = queuedData.uploads.map((u) => ({
      ...u,
      relative_path: u.relative_path || u.filename,
    }));
  } catch (err) {

  }
})();

loadCompletedUploads();

function renderQueuedFolderSubtree(folder) {
  const { childrenContainer } = renderFolderRow(folder.sourcePath, folder.vaultPath, folder.files.length, folderIdResolverFor(folder));
  for (const { pending } of folder.files) {
    renderQueuedUploadRow(pending, childrenContainer);
  }
  for (const [, sub] of folder.subfolders) {
    renderQueuedFolderSubtree(sub);
  }
}

let queuedUploadsList = [];

function renderQueuedUploadRow(u, container) {
  const row = renderUploadRow(u.filename, "Queued from a previous session - not started yet", u.folder_id);
  row.dataset.queuedId = u.id;
  if (container) container.appendChild(row);
  setRowActions(row, [
    { label: "Upload", onClick: () => runFolderUploadAttempt(u, row) },
    { label: "Dismiss", onClick: () => dismissQueuedUpload(u.id, row) },
  ]);
}

async function dismissQueuedUpload(id, row) {
  setRowActions(row, []);
  try {
    await apiFetch(`/api/uploads/queued/${id}/dismiss`, { method: "POST" });
  } catch (err) {
    alert(err.message);
  }
  dismissRow(row);
}

async function loadQueuedUploads() {
  try {
    const data = await apiFetch("/api/uploads/queued");
    if (!data.uploads.length) return;
    queuedUploadsList = data.uploads.map((u) => ({ ...u, relative_path: u.relative_path || u.filename }));
    const { rootFiles, folders } = buildFolderTree(queuedUploadsList);
    rootFiles.forEach((u) => renderQueuedUploadRow(u));
    for (const [, folder] of folders) renderQueuedFolderSubtree(folder);
    updateTransfersUI();
  } catch (err) {

  }
}

async function loadCompletedUploads() {
  try {
    const data = await apiFetch("/api/transfers/completed");
    if (!data.uploads.length) return;
    const { rootFiles, folders } = buildFolderTree(data.uploads.map((u) => ({ ...u, relative_path: u.relative_path || u.filename })));
    rootFiles.forEach((u) => renderCompletedUploadRow(u));
    for (const [, folder] of folders) renderCompletedFolderSubtree(folder);
    updateTransfersUI();
  } catch (err) {

  }
}

function renderCompletedFolderSubtree(folder) {
  const { childrenContainer } = renderFolderRow(folder.sourcePath, folder.vaultPath, folder.files.length, folderIdResolverFor(folder));
  for (const { pending } of folder.files) {
    renderCompletedUploadRow(pending, childrenContainer);
  }
  for (const [, sub] of folder.subfolders) {
    renderCompletedFolderSubtree(sub);
  }
}

function renderCompletedUploadRow(u, container) {
  const doneText = `${formatBytes(u.bytes_done)} / ${formatBytes(u.bytes_total)}`;
  const row = renderUploadRow(u.filename, `Done · ${doneText}`);
  if (container) container.appendChild(row);
  row.classList.add("upload-success");
  setRowActions(row, [{ label: "Dismiss", onClick: () => dismissCompletedUpload(u.id, row) }]);
}

async function dismissCompletedUpload(id, row) {
  setRowActions(row, []);
  try {
    await apiFetch(`/api/transfers/completed/${id}`, { method: "DELETE" });
  } catch (err) {
    alert(err.message);
  }
  dismissRow(row);
}

async function uploadAllQueuedSequentially() {
  const remaining = [...queuedUploadsList];
  while (remaining.length) {
    if (_queuePaused || isQueueCancelled()) break;
    const u = remaining[0];
    let target = null;
    for (const row of document.querySelectorAll(".upload-row")) {
      const statusEl = row.querySelector(".upload-status");
      if (statusEl && statusEl.textContent.includes("Queued from a previous session")) {
        const nameEl = row.querySelector(".upload-name");
        if (nameEl && nameEl.textContent.trim() === u.filename) {
          target = row;
          break;
        }
      }
    }

    remaining.shift();
    if (target) await runFolderUploadAttempt(u, target);
  }
  queuedUploadsList = remaining;
}

document.getElementById("save-max-upload-request-btn").addEventListener("click", async () => {
  const hintEl = document.getElementById("max-upload-request-hint");
  const gb = parseInt(document.getElementById("f-max-upload-request-gb").value, 10);
  if (isNaN(gb) || gb < 0) {
    hintEl.textContent = "Enter a whole number of GB, or 0 for no limit.";
    return;
  }
  try {
    const result = await apiFetch("/api/settings/max-upload-request-size", {
      method: "PUT",
      body: JSON.stringify({ max_upload_request_bytes: gb * 1e9 }),
    });
    const bytes = result.max_upload_request_bytes;
    document.getElementById("f-max-upload-request-gb").value = bytes ? Math.round(bytes / 1e9) : 0;
    hintEl.textContent = bytes
      ? `Saved - uploads sent through the browser are capped at ${Math.round(bytes / 1e9)} GB. Dragging from Explorer is never capped.`
      : "Saved - no limit on upload request size.";
  } catch (err) {
    hintEl.textContent = err.message;
  }
});
