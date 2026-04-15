/**
 * Component Library UI module for WiringWizard.
 *
 * Provides browse/search/add/edit/delete for the persistent component library,
 * AI-assisted pin parsing from raw text, and add-from-library-to-project flow.
 */

// Eel bridge — loaded as a regular script, accessible via window.eel
const eel = window.eel;

// ── Pin Type Options (matches PIN_TYPES in project_schema.py) ────────────

const PIN_TYPE_OPTIONS = [
  "power_input", "power_output", "ground", "signal_input", "signal_output",
  "can_high", "can_low", "pwm_output", "serial_tx", "serial_rx",
  "switched_power", "general"
];

const PIN_TYPE_LABELS = {
  power_input: "Power In",
  power_output: "Power Out",
  ground: "Ground",
  signal_input: "Signal In",
  signal_output: "Signal Out",
  can_high: "CAN-H",
  can_low: "CAN-L",
  pwm_output: "PWM Out",
  serial_tx: "Serial TX",
  serial_rx: "Serial RX",
  switched_power: "Switched Pwr",
  general: "General",
};

// ── State ────────────────────────────────────────────────────────────────

let libraryCache = [];
let editingComponentId = null;
let onAddToProjectCallback = null;

// ── Helpers ──────────────────────────────────────────────────────────────

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function setStatus(message, isError = false) {
  const statusElement = document.getElementById("status-message");
  if (statusElement) {
    statusElement.textContent = message;
    statusElement.style.color = isError ? "var(--color-danger)" : "";
  }
}

function showModal(modalId) {
  document.getElementById(modalId)?.removeAttribute("hidden");
}

function hideModal(modalId) {
  document.getElementById(modalId)?.setAttribute("hidden", "");
}

// ── Library Grid Rendering ───────────────────────────────────────────────

/** Render library components as a card grid inside the specified container. */
function renderLibraryGrid(containerId, components, options = {}) {
  const grid = document.getElementById(containerId);
  if (!grid) return;

  const isPickMode = options.isPickMode || false;

  if (!components || components.length === 0) {
    grid.innerHTML = '<div class="tree-empty">No components found. Click "+ Add New" to create one.</div>';
    return;
  }

  grid.innerHTML = components
    .map((comp) => {
      const pinCount = (comp.pins || []).length;
      const typeBadge = `<span class="library-card-badge">${escapeHtml(comp.component_type || "general")}</span>`;
      const pinSummary = pinCount > 0
        ? `${pinCount} pin${pinCount !== 1 ? "s" : ""} defined`
        : "No pins defined";
      const manufacturer = comp.manufacturer ? escapeHtml(comp.manufacturer) : "";
      const partNumber = comp.part_number ? `#${escapeHtml(comp.part_number)}` : "";
      const metaLine = [manufacturer, partNumber].filter(Boolean).join(" ");

      let actionsHtml = "";
      if (isPickMode) {
        actionsHtml = `<div class="library-card-actions">
          <button onclick="window._libraryAddToProject('${escapeHtml(comp.library_id)}')">＋ Add to Project</button>
        </div>`;
      } else {
        actionsHtml = `<div class="library-card-actions">
          <button onclick="window._libraryEditComponent('${escapeHtml(comp.library_id)}')">Edit</button>
          <button class="btn-danger-sm" onclick="window._libraryDeleteComponent('${escapeHtml(comp.library_id)}')">Delete</button>
        </div>`;
      }

      return `<div class="library-card" data-library-id="${escapeHtml(comp.library_id)}">
        <div class="library-card-name">${escapeHtml(comp.name)}</div>
        <div class="library-card-meta">${typeBadge} ${metaLine}</div>
        <div class="library-card-pins">${pinSummary}</div>
        ${actionsHtml}
      </div>`;
    })
    .join("");
}

// ── Pin Table Rendering ──────────────────────────────────────────────────

/** Build one pin row for the editable pin table. */
function createPinRowHtml(pin = {}) {
  const pinId = escapeHtml(pin.pin_id || "");
  const pinName = escapeHtml(pin.name || "");
  const pinDesc = escapeHtml(pin.description || "");
  const pinType = pin.pin_type || pin.type || "general";

  const typeOptions = PIN_TYPE_OPTIONS.map(
    (pt) => `<option value="${pt}" ${pt === pinType ? "selected" : ""}>${PIN_TYPE_LABELS[pt] || pt}</option>`
  ).join("");

  return `<tr>
    <td><input type="text" class="pin-id" value="${pinId}" placeholder="A1" /></td>
    <td><input type="text" class="pin-name" value="${pinName}" placeholder="B+" /></td>
    <td><select class="pin-type">${typeOptions}</select></td>
    <td><input type="text" class="pin-desc" value="${pinDesc}" placeholder="Description" /></td>
    <td><button class="btn-remove-pin" title="Remove pin">✕</button></td>
  </tr>`;
}

/** Populate the pin table body from an array of pin objects. */
function populatePinTable(pins) {
  const tableBody = document.getElementById("pin-table-body");
  if (!tableBody) return;
  if (!pins || pins.length === 0) {
    tableBody.innerHTML = "";
    return;
  }
  tableBody.innerHTML = pins.map((pin) => createPinRowHtml(pin)).join("");
}

/** Read all pins from the pin table as an array of objects. */
function readPinsFromTable() {
  const tableBody = document.getElementById("pin-table-body");
  if (!tableBody) return [];
  const rows = tableBody.querySelectorAll("tr");
  const pins = [];
  rows.forEach((row) => {
    const pinId = row.querySelector(".pin-id")?.value.trim();
    const name = row.querySelector(".pin-name")?.value.trim();
    const pinType = row.querySelector(".pin-type")?.value;
    const description = row.querySelector(".pin-desc")?.value.trim();
    if (pinId || name) {
      pins.push({
        pin_id: pinId || `P${pins.length + 1}`,
        name: name || pinId || "unnamed",
        pin_type: pinType || "general",
        description: description || "",
      });
    }
  });
  return pins;
}

// ── Library CRUD Operations ──────────────────────────────────────────────

/** Fetch the full library from the backend and cache it. */
async function loadLibrary() {
  try {
    const result = await eel.get_library()();
    if (result.error) {
      setStatus(`Library error: ${result.error}`, true);
      return [];
    }
    libraryCache = result.components || [];
    return libraryCache;
  } catch (loadError) {
    setStatus(`Failed to load library: ${loadError}`, true);
    return [];
  }
}

/** Refresh the library browse grid with optional search/filter. */
async function refreshLibraryGrid() {
  const searchQuery = document.getElementById("library-search")?.value.trim() || "";
  const typeFilter = document.getElementById("library-type-filter")?.value || "";

  let components;
  if (searchQuery || typeFilter) {
    try {
      const result = await eel.search_library_components(searchQuery, typeFilter)();
      components = result.error ? [] : result.components || [];
    } catch (searchError) {
      components = [];
    }
  } else {
    components = await loadLibrary();
  }

  renderLibraryGrid("library-grid", components, { isPickMode: false });
  updateTypeFilterOptions(components);
}

/** Populate the type filter dropdown with available types. */
function updateTypeFilterOptions(components) {
  const filterSelect = document.getElementById("library-type-filter");
  if (!filterSelect) return;

  const allTypes = new Set((components || libraryCache).map((c) => c.component_type));
  const currentValue = filterSelect.value;

  filterSelect.innerHTML = '<option value="">All Types</option>';
  [...allTypes].sort().forEach((componentType) => {
    const option = document.createElement("option");
    option.value = componentType;
    option.textContent = componentType;
    filterSelect.appendChild(option);
  });
  filterSelect.value = currentValue;
}

// ── Library Edit Modal ───────────────────────────────────────────────────

/** Open the add/edit modal. Pass null to create new, or a library_id to edit. */
function openEditModal(libraryId = null) {
  editingComponentId = libraryId;
  const titleElement = document.getElementById("library-edit-title");

  if (libraryId) {
    const comp = libraryCache.find((c) => c.library_id === libraryId);
    if (!comp) {
      setStatus(`Component ${libraryId} not found in cache`, true);
      return;
    }
    titleElement.textContent = "Edit Library Component";
    document.getElementById("lib-name").value = comp.name || "";
    document.getElementById("lib-type").value = comp.component_type || "general";
    document.getElementById("lib-manufacturer").value = comp.manufacturer || "";
    document.getElementById("lib-part-number").value = comp.part_number || "";
    document.getElementById("lib-voltage").value = comp.voltage_nominal ?? 12;
    document.getElementById("lib-current").value = comp.current_draw_amps ?? 0;
    document.getElementById("lib-notes").value = comp.notes || "";
    document.getElementById("lib-raw-data").value = "";
    populatePinTable(comp.pins || []);
  } else {
    titleElement.textContent = "Add Component to Library";
    document.getElementById("lib-name").value = "";
    document.getElementById("lib-type").value = "general";
    document.getElementById("lib-manufacturer").value = "";
    document.getElementById("lib-part-number").value = "";
    document.getElementById("lib-voltage").value = 12;
    document.getElementById("lib-current").value = 0;
    document.getElementById("lib-notes").value = "";
    document.getElementById("lib-raw-data").value = "";
    populatePinTable([]);
  }

  showModal("modal-library-edit");
}

/** Collect form data and save the component to the library. */
async function saveLibraryComponent() {
  const componentName = document.getElementById("lib-name").value.trim();
  if (!componentName) {
    setStatus("Component name is required.", true);
    return;
  }

  const pins = readPinsFromTable();
  const componentData = {
    library_id: editingComponentId || componentName.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
    name: componentName,
    manufacturer: document.getElementById("lib-manufacturer").value.trim(),
    part_number: document.getElementById("lib-part-number").value.trim(),
    component_type: document.getElementById("lib-type").value,
    voltage_nominal: parseFloat(document.getElementById("lib-voltage").value) || 12,
    current_draw_amps: parseFloat(document.getElementById("lib-current").value) || 0,
    pins: pins,
    notes: document.getElementById("lib-notes").value.trim(),
    source_urls: [],
    user_notes: "",
    is_verified: pins.length > 0,
    created_at: new Date().toISOString().slice(0, 10),
    updated_at: new Date().toISOString().slice(0, 10),
  };

  setStatus("Saving component...");
  try {
    let result;
    if (editingComponentId) {
      result = await eel.update_library_component(componentData)();
    } else {
      result = await eel.add_library_component(componentData)();
    }
    if (result.error) {
      setStatus(`Save failed: ${result.error}`, true);
      return;
    }
    libraryCache = result.components || [];
    setStatus(`Saved "${componentName}" to library.`);
    hideModal("modal-library-edit");
    renderLibraryGrid("library-grid", libraryCache, { isPickMode: false });
    updateTypeFilterOptions(libraryCache);
  } catch (saveError) {
    setStatus(`Save error: ${saveError}`, true);
  }
}

/** Delete a component from the library after confirmation. */
async function deleteLibraryComponent(libraryId) {
  const comp = libraryCache.find((c) => c.library_id === libraryId);
  const componentName = comp ? comp.name : libraryId;
  if (!confirm(`Delete "${componentName}" from the library?`)) return;

  setStatus("Deleting...");
  try {
    const result = await eel.delete_library_component(libraryId)();
    if (result.error) {
      setStatus(`Delete failed: ${result.error}`, true);
      return;
    }
    libraryCache = result.components || [];
    setStatus(`Deleted "${componentName}".`);
    renderLibraryGrid("library-grid", libraryCache, { isPickMode: false });
    updateTypeFilterOptions(libraryCache);
  } catch (deleteError) {
    setStatus(`Delete error: ${deleteError}`, true);
  }
}

// ── AI Parse Pins ────────────────────────────────────────────────────────

/** Send raw text to AI for structured pin extraction. */
async function aiParsePins() {
  const componentName = document.getElementById("lib-name").value.trim();
  const rawText = document.getElementById("lib-raw-data").value.trim();
  const parseButton = document.getElementById("btn-ai-parse-pins");

  if (!componentName) {
    setStatus("Enter a component name first.", true);
    return;
  }
  if (!rawText) {
    setStatus("Paste some raw data to parse.", true);
    return;
  }

  parseButton.disabled = true;
  parseButton.innerHTML = '<span class="spinner-inline"></span> Parsing...';
  setStatus("AI is parsing pin data...");

  try {
    console.log("[library] aiParsePins: calling eel.ai_parse_component", componentName);
    const result = await eel.ai_parse_component(componentName, rawText)();
    console.log("[library] aiParsePins: result", result);
    if (result.error) {
      setStatus(`AI parse failed: ${result.error}`, true);
      parseButton.disabled = false;
      parseButton.textContent = "🤖 Parse Pins with AI";
      return;
    }

    const parsed = result.parsed || {};
    if (parsed.pins && parsed.pins.length > 0) {
      populatePinTable(parsed.pins);
      setStatus(`AI extracted ${parsed.pins.length} pin(s). Review and edit before saving.`);
    } else {
      setStatus("AI returned no pins. Try providing more detail.", true);
    }

    // Auto-fill type and voltage if AI provided them
    if (parsed.component_type) {
      const typeSelect = document.getElementById("lib-type");
      if ([...typeSelect.options].some((o) => o.value === parsed.component_type)) {
        typeSelect.value = parsed.component_type;
      }
    }
    if (parsed.voltage_nominal) {
      document.getElementById("lib-voltage").value = parsed.voltage_nominal;
    }
    if (parsed.current_draw_amps) {
      document.getElementById("lib-current").value = parsed.current_draw_amps;
    }
  } catch (parseError) {
    console.error("[library] aiParsePins error:", parseError);
    setStatus(`AI parse error: ${parseError}`, true);
  }

  parseButton.disabled = false;
  parseButton.textContent = "🤖 Parse Pins with AI";
}

/** Deep-crawl a documentation URL and AI-parse pin data from it. */
async function fetchAndParseFromUrl() {
  const componentName = document.getElementById("lib-name").value.trim();
  const componentUrl = document.getElementById("lib-fetch-url").value.trim();
  const fetchButton = document.getElementById("btn-fetch-url");

  if (!componentName) {
    setStatus("Enter a component name first.", true);
    return;
  }
  if (!componentUrl) {
    setStatus("Enter a documentation URL to fetch.", true);
    return;
  }

  fetchButton.disabled = true;
  fetchButton.innerHTML = '<span class="spinner-inline"></span> Crawling...';
  setStatus("Fetching and crawling documentation pages — this may take a moment...");

  try {
    console.log("[library] fetchAndParseFromUrl: calling eel.ai_fetch_and_parse_component", componentName, componentUrl);
    const result = await eel.ai_fetch_and_parse_component(componentName, componentUrl)();
    console.log("[library] fetchAndParseFromUrl: result", result);
    if (result.error) {
      setStatus(`URL fetch failed: ${result.error}`, true);
      fetchButton.disabled = false;
      fetchButton.textContent = "🌐 Fetch & Parse";
      return;
    }

    const parsed = result.parsed || {};
    const crawlStats = result.crawl_stats || {};
    const pagesCrawled = crawlStats.pages_crawled || 0;
    const pagesWithPins = crawlStats.pages_with_pin_data || 0;

    if (parsed.pins && parsed.pins.length > 0) {
      populatePinTable(parsed.pins);
      setStatus(
        `Crawled ${pagesCrawled} page(s) (${pagesWithPins} with pin data). ` +
        `AI extracted ${parsed.pins.length} pin(s). Review and edit before saving.`
      );
    } else {
      setStatus(
        `Crawled ${pagesCrawled} page(s) but AI found no pins. ` +
        "Try a more specific URL or paste data manually.",
        true
      );
    }

    // Auto-fill type and voltage if AI provided them.
    if (parsed.component_type) {
      const typeSelect = document.getElementById("lib-type");
      if (typeSelect) typeSelect.value = parsed.component_type;
    }
    if (parsed.voltage_nominal) {
      const voltageInput = document.getElementById("lib-voltage");
      if (voltageInput) voltageInput.value = parsed.voltage_nominal;
    }
    if (parsed.current_draw_amps) {
      const currentInput = document.getElementById("lib-current");
      if (currentInput) currentInput.value = parsed.current_draw_amps;
    }
  } catch (fetchError) {
    console.error("[library] fetchAndParseFromUrl error:", fetchError);
    setStatus(`URL fetch error: ${fetchError}`, true);
  }

  fetchButton.disabled = false;
  fetchButton.textContent = "🌐 Fetch & Parse";
}

/**
 * Experimental: search the web for component pin data by name alone.
 * Uses DuckDuckGo to find datasheets/pinouts, crawls results, then AI-parses.
 */
async function autoSearchComponent() {
  const componentName = document.getElementById("lib-name").value.trim();
  const searchButton = document.getElementById("btn-auto-search");

  if (!componentName) {
    setStatus("Enter a component name first (the more specific the better).", true);
    return;
  }

  searchButton.disabled = true;
  searchButton.innerHTML = '<span class="spinner-inline"></span> Searching...';
  setStatus(`Searching the web for "${componentName}" — this may take 15-30 seconds...`);

  try {
    console.log("[library] autoSearchComponent: calling eel.ai_auto_search_component", componentName);
    const result = await eel.ai_auto_search_component(componentName)();
    console.log("[library] autoSearchComponent: result", result);
    if (result.error) {
      setStatus(`Auto-search: ${result.error}`, true);
      searchButton.disabled = false;
      searchButton.textContent = "🔍 Auto-Search";
      return;
    }

    const parsed = result.parsed || {};
    const searchStats = result.search_stats || {};
    const pagesCrawled = searchStats.pages_crawled || 0;
    const pagesWithPins = searchStats.pages_with_pin_data || 0;
    const queriesRun = searchStats.queries_run || 0;

    if (parsed.pins && parsed.pins.length > 0) {
      populatePinTable(parsed.pins);
      setStatus(
        `🔍 Ran ${queriesRun} search(es), crawled ${pagesCrawled} page(s) ` +
        `(${pagesWithPins} with pin data). AI extracted ${parsed.pins.length} pin(s). ` +
        "Review carefully — auto-search results may need corrections."
      );
    } else {
      setStatus(
        `Searched ${queriesRun} quer(ies), crawled ${pagesCrawled} page(s) but AI found no pins. ` +
        "Try a more specific name, add a part number, or use the URL field instead.",
        true
      );
    }

    // Auto-fill type and voltage if AI provided them.
    if (parsed.component_type) {
      const typeSelect = document.getElementById("lib-type");
      if (typeSelect) typeSelect.value = parsed.component_type;
    }
    if (parsed.voltage_nominal) {
      const voltageInput = document.getElementById("lib-voltage");
      if (voltageInput) voltageInput.value = parsed.voltage_nominal;
    }
    if (parsed.current_draw_amps) {
      const currentInput = document.getElementById("lib-current");
      if (currentInput) currentInput.value = parsed.current_draw_amps;
    }
  } catch (searchError) {
    console.error("[library] autoSearchComponent error:", searchError);
    setStatus(`Auto-search error: ${searchError}`, true);
  }

  searchButton.disabled = false;
  searchButton.textContent = "🔍 Auto-Search";
}

// ── Image/Schematic Upload Parsing ──────────────────────────────────────

/** Read an uploaded image file, base64-encode it, and send to AI vision for pin extraction. */
async function parseImageFile() {
  const componentName = document.getElementById("lib-name").value.trim();
  const fileInput = document.getElementById("lib-image-upload");
  const parseButton = document.getElementById("btn-parse-image");

  if (!componentName) {
    setStatus("Enter a component name first.", true);
    return;
  }
  if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
    setStatus("Select an image file first.", true);
    return;
  }

  const imageFile = fileInput.files[0];
  const allowedTypes = ["image/png", "image/jpeg", "image/gif", "image/webp"];
  if (!allowedTypes.includes(imageFile.type)) {
    setStatus("Unsupported image format. Use PNG, JPG, GIF, or WebP.", true);
    return;
  }

  // 10 MB limit to avoid overwhelming the API
  const MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024;
  if (imageFile.size > MAX_IMAGE_SIZE_BYTES) {
    setStatus("Image too large (max 10 MB). Try a smaller or compressed version.", true);
    return;
  }

  parseButton.disabled = true;
  parseButton.innerHTML = '<span class="spinner-inline"></span> Analyzing...';
  setStatus("AI vision is analyzing the image — this may take a moment...");

  try {
    // Read the file as a base64 data URL
    const imageBase64 = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        // Strip the "data:image/png;base64," prefix to get raw base64
        const dataUrl = reader.result;
        const base64Data = dataUrl.split(",")[1];
        resolve(base64Data);
      };
      reader.onerror = () => reject(new Error("Failed to read image file."));
      reader.readAsDataURL(imageFile);
    });

    console.log("[library] parseImageFile: sending image to AI vision", componentName, imageFile.type);
    const result = await eel.ai_parse_image(componentName, imageBase64, imageFile.type)();
    console.log("[library] parseImageFile: result", result);

    if (result.error) {
      setStatus(`Image parse failed: ${result.error}`, true);
      parseButton.disabled = false;
      parseButton.textContent = "📷 Parse Image";
      return;
    }

    const parsed = result.parsed || {};
    if (parsed.pins && parsed.pins.length > 0) {
      populatePinTable(parsed.pins);
      setStatus(`AI vision extracted ${parsed.pins.length} pin(s) from the image. Review and edit before saving.`);
    } else {
      setStatus("AI vision found no pins in this image. Try a clearer schematic or paste text instead.", true);
    }

    // Auto-fill fields if AI provided them
    if (parsed.component_type) {
      const typeSelect = document.getElementById("lib-type");
      if (typeSelect) typeSelect.value = parsed.component_type;
    }
    if (parsed.voltage_nominal) {
      const voltageInput = document.getElementById("lib-voltage");
      if (voltageInput) voltageInput.value = parsed.voltage_nominal;
    }
    if (parsed.current_draw_amps) {
      const currentInput = document.getElementById("lib-current");
      if (currentInput) currentInput.value = parsed.current_draw_amps;
    }
  } catch (imageError) {
    console.error("[library] parseImageFile error:", imageError);
    setStatus(`Image parse error: ${imageError}`, true);
  }

  parseButton.disabled = false;
  parseButton.textContent = "📷 Parse Image";
}

// ── Bulk Library Builder ────────────────────────────────────────────────

/** State for the bulk builder — holds discovered components until user saves. */
let bulkDiscoveredComponents = [];

/** Crawl a documentation URL and show discovered components for bulk import. */
async function bulkCrawlAndIdentify() {
  const urlInput = document.getElementById("bulk-build-url");
  const crawlButton = document.getElementById("btn-bulk-crawl");
  const saveAllButton = document.getElementById("btn-bulk-save-all");
  const statusDiv = document.getElementById("bulk-build-status");
  const resultsDiv = document.getElementById("bulk-build-results");
  const resultsGrid = document.getElementById("bulk-results-grid");
  const documentationUrl = urlInput ? urlInput.value.trim() : "";

  if (!documentationUrl) {
    setStatus("Enter a documentation URL to crawl.", true);
    return;
  }

  crawlButton.disabled = true;
  crawlButton.innerHTML = '<span class="spinner-inline"></span> Crawling...';
  statusDiv.removeAttribute("hidden");
  statusDiv.className = "bulk-status";
  statusDiv.textContent = "Crawling documentation pages and identifying components — this may take 30-60 seconds...";
  resultsDiv.setAttribute("hidden", "");
  saveAllButton.setAttribute("hidden", "");
  bulkDiscoveredComponents = [];

  try {
    console.log("[library] bulkCrawlAndIdentify: calling eel.ai_bulk_build_library", documentationUrl);
    const result = await eel.ai_bulk_build_library(documentationUrl)();
    console.log("[library] bulkCrawlAndIdentify: result", result);

    if (result.error) {
      statusDiv.className = "bulk-status bulk-error";
      statusDiv.textContent = `Bulk build failed: ${result.error}`;
      crawlButton.disabled = false;
      crawlButton.textContent = "🔍 Crawl & Identify";
      return;
    }

    const components = result.components || [];
    const crawlStats = result.crawl_stats || {};
    const pagesCrawled = crawlStats.pages_crawled || 0;
    const pagesWithPins = crawlStats.pages_with_pin_data || 0;

    if (components.length === 0) {
      statusDiv.className = "bulk-status bulk-error";
      statusDiv.textContent = `Crawled ${pagesCrawled} pages but found no distinct components. Try a more specific documentation URL.`;
      crawlButton.disabled = false;
      crawlButton.textContent = "🔍 Crawl & Identify";
      return;
    }

    bulkDiscoveredComponents = components;
    statusDiv.textContent = `Crawled ${pagesCrawled} pages (${pagesWithPins} with pin data). Found ${components.length} component(s). Review below and save.`;

    // Render component cards with checkboxes
    resultsGrid.innerHTML = components.map((comp, index) => {
      const pinCount = (comp.pins || []).length;
      const typeBadge = `<span class="library-card-badge">${escapeHtml(comp.component_type || "general")}</span>`;
      return `<div class="bulk-component-card">
        <input type="checkbox" class="component-check" data-bulk-index="${index}" checked />
        <div class="library-card-name">${escapeHtml(comp.name)}</div>
        <div class="library-card-meta">${typeBadge} ${escapeHtml(comp.manufacturer || "")}</div>
        <div class="component-pin-count">${pinCount} pin(s)</div>
      </div>`;
    }).join("");

    resultsDiv.removeAttribute("hidden");
    saveAllButton.removeAttribute("hidden");
  } catch (bulkError) {
    console.error("[library] bulkCrawlAndIdentify error:", bulkError);
    statusDiv.className = "bulk-status bulk-error";
    statusDiv.textContent = `Bulk build error: ${bulkError}`;
  }

  crawlButton.disabled = false;
  crawlButton.textContent = "🔍 Crawl & Identify";
}

/** Save all checked components from the bulk builder to the library. */
async function bulkSaveAll() {
  const saveAllButton = document.getElementById("btn-bulk-save-all");
  const statusDiv = document.getElementById("bulk-build-status");
  const checkboxes = document.querySelectorAll(".component-check:checked");
  const selectedIndices = Array.from(checkboxes).map(cb => parseInt(cb.dataset.bulkIndex));

  if (selectedIndices.length === 0) {
    setStatus("No components selected. Check the ones you want to save.", true);
    return;
  }

  saveAllButton.disabled = true;
  saveAllButton.innerHTML = '<span class="spinner-inline"></span> Saving...';
  let savedCount = 0;
  let failedCount = 0;

  for (const idx of selectedIndices) {
    const comp = bulkDiscoveredComponents[idx];
    if (!comp) continue;

    try {
      const saveResult = await eel.add_library_component(comp)();
      if (saveResult.error) {
        failedCount++;
      } else {
        savedCount++;
      }
    } catch (saveError) {
      failedCount++;
    }
  }

  const message = `Saved ${savedCount} component(s) to library.` +
    (failedCount > 0 ? ` ${failedCount} failed.` : "");
  statusDiv.textContent = message;
  setStatus(message);

  saveAllButton.disabled = false;
  saveAllButton.textContent = "💾 Save All to Library";

  // Refresh library cache
  await loadLibrary();
}

// ── Update Checker ──────────────────────────────────────────────────────

/** Check GitHub for a newer release and show the update banner if available. */
async function checkForAppUpdates() {
  try {
    const result = await eel.check_for_updates()();
    if (result.error || !result.is_update_available) return;

    const banner = document.getElementById("update-banner");
    const message = document.getElementById("update-message");
    const link = document.getElementById("update-link");

    if (banner && message && link) {
      message.textContent = `WiringWizard ${result.latest_version} is available! (You have v${result.current_version})`;
      link.href = result.exe_download_url || result.download_url || "#";
      link.textContent = result.exe_download_url ? "Download .exe" : "View Release";
      banner.removeAttribute("hidden");
    }
  } catch (updateError) {
    console.log("[library] Update check failed (non-critical):", updateError);
  }
}

/** Open the pick-from-library modal and set the callback. */
function openAddFromLibrary(callback) {
  onAddToProjectCallback = callback;
  refreshAddFromLibraryGrid();
  showModal("modal-add-from-library");
}

async function refreshAddFromLibraryGrid() {
  const searchQuery = document.getElementById("add-from-lib-search")?.value.trim() || "";
  let components;
  if (searchQuery) {
    try {
      const result = await eel.search_library_components(searchQuery, "")();
      components = result.error ? [] : result.components || [];
    } catch (error) {
      components = [];
    }
  } else {
    if (libraryCache.length === 0) await loadLibrary();
    components = libraryCache;
  }
  renderLibraryGrid("add-from-lib-grid", components, { isPickMode: true });
}

/** Called when user clicks "Add to Project" on a library card. */
function addComponentToProject(libraryId) {
  const comp = libraryCache.find((c) => c.library_id === libraryId);
  if (!comp) {
    setStatus(`Component ${libraryId} not found.`, true);
    return;
  }
  hideModal("modal-add-from-library");
  if (typeof onAddToProjectCallback === "function") {
    onAddToProjectCallback(comp);
    setStatus(`Added "${comp.name}" to project.`);
  }
}

// ── AI Generate Connections ──────────────────────────────────────────────

/** Open the AI wire-generation modal showing component count. */
function openAiWireModal(projectComponents) {
  const componentCount = (projectComponents || []).filter((c) => c.pins && c.pins.length > 0).length;
  const countElement = document.getElementById("ai-wire-comp-count");
  if (countElement) countElement.textContent = componentCount;
  document.getElementById("ai-wire-goal").value = "";
  showModal("modal-ai-wire");
}

// ── Event Binding ────────────────────────────────────────────────────────

/** Wire up all library UI event listeners. Call once on app init. */
function initLibraryUI() {
  console.log("[library] initLibraryUI: binding event listeners");
  console.log("[library] eel available:", typeof eel !== "undefined", eel ? "has functions" : "missing");
  // Close modals via data-close-modal buttons
  document.querySelectorAll("[data-close-modal]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const modalId = btn.getAttribute("data-close-modal");
      hideModal(modalId);
    });
  });

  // Library browse button
  document.getElementById("btn-library")?.addEventListener("click", () => {
    refreshLibraryGrid();
    showModal("modal-library");
  });

  // Search and filter in browse modal
  document.getElementById("library-search")?.addEventListener("input", debounce(refreshLibraryGrid, 300));
  document.getElementById("library-type-filter")?.addEventListener("change", refreshLibraryGrid);

  // Add new component button
  document.getElementById("btn-library-add-new")?.addEventListener("click", () => {
    openEditModal(null);
  });

  // Save component
  document.getElementById("btn-save-library-component")?.addEventListener("click", saveLibraryComponent);

  // AI parse pins
  const parseBtn = document.getElementById("btn-ai-parse-pins");
  console.log("[library] btn-ai-parse-pins found:", !!parseBtn);
  parseBtn?.addEventListener("click", aiParsePins);

  // URL fetch and parse
  const fetchBtn = document.getElementById("btn-fetch-url");
  console.log("[library] btn-fetch-url found:", !!fetchBtn);
  fetchBtn?.addEventListener("click", fetchAndParseFromUrl);

  // Auto-search (experimental)
  const searchBtn = document.getElementById("btn-auto-search");
  console.log("[library] btn-auto-search found:", !!searchBtn);
  searchBtn?.addEventListener("click", autoSearchComponent);

  // Add pin row
  document.getElementById("btn-add-pin-row")?.addEventListener("click", () => {
    const tableBody = document.getElementById("pin-table-body");
    if (tableBody) {
      tableBody.insertAdjacentHTML("beforeend", createPinRowHtml());
    }
  });

  // Remove pin row (delegated)
  document.getElementById("pin-table-body")?.addEventListener("click", (event) => {
    if (event.target.classList.contains("btn-remove-pin")) {
      event.target.closest("tr")?.remove();
    }
  });

  // Add from library search
  document.getElementById("add-from-lib-search")?.addEventListener("input", debounce(refreshAddFromLibraryGrid, 300));

  // Image upload and parse
  const imageBtn = document.getElementById("btn-parse-image");
  console.log("[library] btn-parse-image found:", !!imageBtn);
  imageBtn?.addEventListener("click", parseImageFile);

  // Bulk builder
  document.getElementById("btn-bulk-build")?.addEventListener("click", () => {
    showModal("modal-bulk-build");
  });
  document.getElementById("btn-bulk-crawl")?.addEventListener("click", bulkCrawlAndIdentify);
  document.getElementById("btn-bulk-save-all")?.addEventListener("click", bulkSaveAll);

  // Update banner dismiss
  document.getElementById("update-dismiss")?.addEventListener("click", () => {
    document.getElementById("update-banner")?.setAttribute("hidden", "");
  });

  // Close modals on overlay click
  document.querySelectorAll(".modal-overlay").forEach((overlay) => {
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) {
        overlay.setAttribute("hidden", "");
      }
    });
  });
}

/** Simple debounce utility for search inputs. */
function debounce(fn, delayMs) {
  let timerId;
  return (...args) => {
    clearTimeout(timerId);
    timerId = setTimeout(() => fn(...args), delayMs);
  };
}

// ── Global Hooks (called from inline onclick in cards) ───────────────────

window._libraryEditComponent = (libraryId) => openEditModal(libraryId);
window._libraryDeleteComponent = (libraryId) => deleteLibraryComponent(libraryId);
window._libraryAddToProject = (libraryId) => addComponentToProject(libraryId);

// ── Exports ──────────────────────────────────────────────────────────────

export {
  initLibraryUI,
  loadLibrary,
  openAddFromLibrary,
  openAiWireModal,
  openEditModal,
  checkForAppUpdates,
  libraryCache,
};
