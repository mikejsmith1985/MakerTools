/**
 * app.js — Main orchestration for WiringWizard web UI.
 * Binds UI events, manages app state, coordinates sidebar/diagram/inspector,
 * and calls Python backend via the Eel bridge.
 */

import {
  renderDiagram, selectComponent, selectConnection, clearSelection,
  zoomIn, zoomOut, fitToView, getZoomLevel, getTypeConfig,
  initCanvasInteraction, WIRE_COLOR_MAP
} from './diagram.js';

// ── Application State ──────────────────────────────────────────────────────
const appState = {
  projectProfile: null,    // {project_name, domain, voltage_class, description}
  components: [],          // array of component objects
  connections: [],         // array of connection objects
  sidebarView: 'components', // 'components' | 'connections'
  editingComponentId: null,
  editingConnectionId: null,
  isLoading: false,
};

// ── Initialization ─────────────────────────────────────────────────────────

/**
 * Entry point — called when the DOM is ready and Eel bridge is connected.
 */
async function initializeApp() {
  bindToolbarButtons();
  bindModalButtons();
  bindSidebarNavigation();
  bindInspectorEvents();
  bindZoomControls();
  initCanvasInteraction();

  // Populate domain dropdown in the New Project modal
  await populateDomainDropdowns();

  // Try loading a saved draft on startup
  await loadDraftIfAvailable();

  setStatus('Ready');
}

// Eel is loaded as a regular script — access via window.eel from ES modules
const eel = window.eel;

/**
 * Wait for the Eel websocket to be ready, then bootstrap the application.
 * Eel.js auto-connects on load; by the time this ES module runs the socket
 * may already be open, so we check readyState first before adding a listener.
 */
function startWhenEelReady() {
  if (!eel || !eel._websocket) {
    // Eel not yet loaded — poll until it appears
    const pollForEel = setInterval(() => {
      if (window.eel && window.eel._websocket) {
        clearInterval(pollForEel);
        startWhenEelReady();
      }
    }, 50);
    setTimeout(() => clearInterval(pollForEel), 5000);
    return;
  }

  if (eel._websocket.readyState === WebSocket.OPEN) {
    initializeApp().catch(error => console.error('Init failed:', error));
  } else {
    eel._websocket.addEventListener('open', () => {
      initializeApp().catch(error => console.error('Init failed:', error));
    });
  }
}

// Kick off once the DOM is interactive
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', startWhenEelReady);
} else {
  startWhenEelReady();
}

// ── Toolbar Button Bindings ────────────────────────────────────────────────

function bindToolbarButtons() {
  getElement('btn-new-project').addEventListener('click', () => openModal('modal-new-project'));
  getElement('btn-ai-assist').addEventListener('click', openAiAssistModal);
  getElement('btn-save').addEventListener('click', saveDraft);
  getElement('btn-load').addEventListener('click', loadDraft);
  getElement('btn-generate').addEventListener('click', generateReport);
  getElement('btn-remap').addEventListener('click', () => openModal('modal-remap'));
  getElement('btn-settings').addEventListener('click', () => openModal('modal-settings'));
  getElement('btn-empty-ai').addEventListener('click', openAiAssistModal);
}

function bindZoomControls() {
  getElement('btn-zoom-in').addEventListener('click', () => { zoomIn(); updateZoomDisplay(); });
  getElement('btn-zoom-out').addEventListener('click', () => { zoomOut(); updateZoomDisplay(); });
  getElement('btn-zoom-fit').addEventListener('click', () => { fitToView(); updateZoomDisplay(); });
}

function updateZoomDisplay() {
  getElement('zoom-level').textContent = `${getZoomLevel()}%`;
}

// ── Sidebar Navigation ─────────────────────────────────────────────────────

function bindSidebarNavigation() {
  getElement('nav-components').addEventListener('click', () => switchSidebarView('components'));
  getElement('nav-connections').addEventListener('click', () => switchSidebarView('connections'));
  getElement('btn-add-item').addEventListener('click', () => {
    if (appState.sidebarView === 'components') openAddComponentModal();
    else openAddConnectionModal();
  });
}

function switchSidebarView(viewName) {
  appState.sidebarView = viewName;

  getElement('nav-components').classList.toggle('active', viewName === 'components');
  getElement('nav-connections').classList.toggle('active', viewName === 'connections');
  getElement('sidebar-title').textContent = viewName === 'components' ? 'Components' : 'Connections';
  getElement('btn-add-item').title = viewName === 'components' ? 'Add Component' : 'Add Connection';

  refreshSidebarTree();
}

function refreshSidebarTree() {
  const treeContainer = getElement('sidebar-tree');
  treeContainer.innerHTML = '';

  if (appState.sidebarView === 'components') {
    if (appState.components.length === 0) {
      treeContainer.innerHTML = '<div class="tree-empty">No components yet.<br/>Use <strong>AI Assist</strong> to get started.</div>';
      return;
    }
    for (const comp of appState.components) {
      treeContainer.appendChild(createComponentTreeItem(comp));
    }
  } else {
    if (appState.connections.length === 0) {
      treeContainer.innerHTML = '<div class="tree-empty">No connections yet.<br/>Add components first, then wire them together.</div>';
      return;
    }
    for (const conn of appState.connections) {
      treeContainer.appendChild(createConnectionTreeItem(conn));
    }
  }
}

function createComponentTreeItem(component) {
  const typeConfig = getTypeConfig(component.component_type);
  const itemElement = document.createElement('div');
  itemElement.className = 'tree-item';
  itemElement.dataset.id = component.component_id;
  itemElement.innerHTML = `
    <span class="tree-item-icon" style="background:${typeConfig.color}22; color:${typeConfig.color}">${typeConfig.icon}</span>
    <span class="tree-item-label">${escapeHtml(component.component_name || component.component_id)}</span>
    <span class="tree-item-badge">${typeConfig.label}</span>
    <span class="tree-item-actions">
      <button title="Edit" data-action="edit" data-id="${component.component_id}">✏</button>
      <button title="Delete" data-action="delete" data-id="${component.component_id}">🗑</button>
    </span>
  `;
  itemElement.addEventListener('click', (event) => {
    const actionButton = event.target.closest('[data-action]');
    if (actionButton) {
      event.stopPropagation();
      if (actionButton.dataset.action === 'edit') openEditComponentModal(component.component_id);
      else if (actionButton.dataset.action === 'delete') deleteComponent(component.component_id);
      return;
    }
    selectComponentInUI(component.component_id);
  });
  return itemElement;
}

function createConnectionTreeItem(connection) {
  const wireColor = WIRE_COLOR_MAP[connection.wire_color] || '#7d8590';
  const itemElement = document.createElement('div');
  itemElement.className = 'tree-item tree-item-wire';
  itemElement.dataset.id = connection.connection_id;
  itemElement.innerHTML = `
    <span class="tree-wire-line" style="background:${wireColor}"></span>
    <span class="tree-item-label">${escapeHtml(connection.connection_id)}</span>
    <span class="tree-wire-detail">${escapeHtml(connection.from_component_id)} → ${escapeHtml(connection.to_component_id)}</span>
    <span class="tree-item-actions">
      <button title="Edit" data-action="edit" data-id="${connection.connection_id}">✏</button>
      <button title="Delete" data-action="delete" data-id="${connection.connection_id}">🗑</button>
    </span>
  `;
  itemElement.addEventListener('click', (event) => {
    const actionButton = event.target.closest('[data-action]');
    if (actionButton) {
      event.stopPropagation();
      if (actionButton.dataset.action === 'edit') openEditConnectionModal(connection.connection_id);
      else if (actionButton.dataset.action === 'delete') deleteConnection(connection.connection_id);
      return;
    }
    selectConnectionInUI(connection.connection_id);
  });
  return itemElement;
}

// ── Selection (UI + Diagram sync) ──────────────────────────────────────────

function selectComponentInUI(componentId) {
  selectComponent(componentId);
  highlightSidebarItem(componentId);
  showComponentInspector(componentId);
}

function selectConnectionInUI(connectionId) {
  selectConnection(connectionId);
  highlightSidebarItem(connectionId);
  showConnectionInspector(connectionId);
}

function highlightSidebarItem(itemId) {
  document.querySelectorAll('.tree-item').forEach(treeItem => {
    treeItem.classList.toggle('selected', treeItem.dataset.id === itemId);
  });
}

// Listen for diagram selection events to sync sidebar/inspector
document.addEventListener('diagram:select', (event) => {
  const { type, id } = event.detail;
  highlightSidebarItem(id);
  if (type === 'component') showComponentInspector(id);
  else showConnectionInspector(id);
});

document.addEventListener('diagram:deselect', () => {
  document.querySelectorAll('.tree-item.selected').forEach(treeItem => treeItem.classList.remove('selected'));
  showEmptyInspector();
});

// ── Inspector ──────────────────────────────────────────────────────────────

function bindInspectorEvents() {
  getElement('btn-close-inspector').addEventListener('click', () => {
    getElement('inspector').classList.add('collapsed');
  });
}

function showEmptyInspector() {
  const inspectorBody = getElement('inspector-body');
  inspectorBody.innerHTML = '<div class="inspector-empty">Click a component or wire in the diagram to inspect it.</div>';
}

function showComponentInspector(componentId) {
  const component = appState.components.find(c => c.component_id === componentId);
  if (!component) return;

  const typeConfig = getTypeConfig(component.component_type);
  const connectedWires = appState.connections.filter(
    c => c.from_component_id === componentId || c.to_component_id === componentId
  );
  const totalCurrent = connectedWires.reduce((sum, c) => sum + (c.current_amps || 0), 0);

  const inspectorBody = getElement('inspector-body');
  getElement('inspector').classList.remove('collapsed');
  inspectorBody.innerHTML = `
    <div class="insp-section">
      <div class="insp-section-title">Component</div>
      <div class="insp-row"><span class="insp-label">Name</span><span class="insp-value">${escapeHtml(component.component_name)}</span></div>
      <div class="insp-row"><span class="insp-label">ID</span><span class="insp-value" style="font-family:var(--font-mono)">${escapeHtml(component.component_id)}</span></div>
      <div class="insp-row"><span class="insp-label">Type</span><span class="insp-badge" style="background:${typeConfig.color}22;color:${typeConfig.color}">${typeConfig.icon} ${typeConfig.label}</span></div>
      <div class="insp-row"><span class="insp-label">Max Draw</span><span class="insp-value accent">${component.current_draw_amps}A</span></div>
      <div class="insp-row"><span class="insp-label">Location</span><span class="insp-value">${escapeHtml(component.position_label || '—')}</span></div>
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Connections (${connectedWires.length})</div>
      ${connectedWires.map(wire => `<div class="insp-row">
        <span class="insp-label" style="font-family:var(--font-mono)">${escapeHtml(wire.connection_id)}</span>
        <span class="insp-value">${wire.current_amps}A</span>
      </div>`).join('')}
      <div class="insp-row"><span class="insp-label">Total Current</span><span class="insp-value ${totalCurrent > component.current_draw_amps ? 'danger' : 'success'}">${totalCurrent.toFixed(1)}A</span></div>
    </div>
    <div class="insp-actions">
      <button class="btn-secondary btn-sm" onclick="document.dispatchEvent(new CustomEvent('inspector:edit-component', {detail:'${componentId}'}))">✏ Edit</button>
      <button class="btn-danger btn-sm" onclick="document.dispatchEvent(new CustomEvent('inspector:delete-component', {detail:'${componentId}'}))">🗑 Delete</button>
    </div>
  `;
}

function showConnectionInspector(connectionId) {
  const connection = appState.connections.find(c => c.connection_id === connectionId);
  if (!connection) return;

  const wireColor = WIRE_COLOR_MAP[connection.wire_color] || '#7d8590';
  const inspectorBody = getElement('inspector-body');
  getElement('inspector').classList.remove('collapsed');
  inspectorBody.innerHTML = `
    <div class="insp-section">
      <div class="insp-section-title">Connection</div>
      <div class="insp-row"><span class="insp-label">ID</span><span class="insp-value" style="font-family:var(--font-mono)">${escapeHtml(connection.connection_id)}</span></div>
      <div class="insp-row"><span class="insp-label">Color</span><span class="insp-value"><span style="display:inline-block;width:12px;height:3px;border-radius:2px;background:${wireColor};vertical-align:middle;margin-right:6px"></span>${escapeHtml(connection.wire_color)}</span></div>
      <div class="insp-row"><span class="insp-label">Current</span><span class="insp-value accent">${connection.current_amps}A</span></div>
      <div class="insp-row"><span class="insp-label">Length</span><span class="insp-value">${connection.run_length_ft} ft</span></div>
      ${connection.awg_override ? `<div class="insp-row"><span class="insp-label">AWG Override</span><span class="insp-value">${escapeHtml(connection.awg_override)}</span></div>` : ''}
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Route</div>
      <div class="insp-row"><span class="insp-label">From</span><span class="insp-value">${escapeHtml(connection.from_component_id)} : ${escapeHtml(connection.from_pin)}</span></div>
      <div class="insp-row"><span class="insp-label">To</span><span class="insp-value">${escapeHtml(connection.to_component_id)} : ${escapeHtml(connection.to_pin)}</span></div>
    </div>
    <div class="insp-actions">
      <button class="btn-secondary btn-sm" onclick="document.dispatchEvent(new CustomEvent('inspector:edit-connection', {detail:'${connectionId}'}))">✏ Edit</button>
      <button class="btn-danger btn-sm" onclick="document.dispatchEvent(new CustomEvent('inspector:delete-connection', {detail:'${connectionId}'}))">🗑 Delete</button>
    </div>
  `;
}

// Inspector action events
document.addEventListener('inspector:edit-component', (e) => openEditComponentModal(e.detail));
document.addEventListener('inspector:delete-component', (e) => deleteComponent(e.detail));
document.addEventListener('inspector:edit-connection', (e) => openEditConnectionModal(e.detail));
document.addEventListener('inspector:delete-connection', (e) => deleteConnection(e.detail));

// ── Modal Management ───────────────────────────────────────────────────────

function bindModalButtons() {
  // Close buttons (generic data-close-modal pattern)
  document.querySelectorAll('[data-close-modal]').forEach(button => {
    button.addEventListener('click', () => closeModal(button.dataset.closeModal));
  });

  // Close modals on overlay click
  document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', (event) => {
      if (event.target === overlay) overlay.hidden = true;
    });
  });

  // New project
  getElement('btn-create-project').addEventListener('click', createProject);

  // Component CRUD
  getElement('btn-save-component').addEventListener('click', saveComponent);

  // Connection CRUD
  getElement('btn-save-connection').addEventListener('click', saveConnection);

  // AI Draft
  getElement('btn-run-ai-draft').addEventListener('click', runAiDraft);

  // Token management
  getElement('btn-save-token').addEventListener('click', saveToken);
  getElement('btn-clear-token').addEventListener('click', clearToken);
  getElement('btn-settings-save-token').addEventListener('click', saveSettingsToken);
  getElement('btn-settings-clear-token').addEventListener('click', clearSettingsToken);

  // Report
  getElement('btn-copy-report').addEventListener('click', copyReport);

  // Remap
  getElement('btn-apply-remap').addEventListener('click', applyRemap);
}

function openModal(modalId) { getElement(modalId).hidden = false; }
function closeModal(modalId) { getElement(modalId).hidden = true; }

// ── New Project ────────────────────────────────────────────────────────────

async function populateDomainDropdowns() {
  try {
    const domainList = await eel.list_available_domains()();
    const domainSelect = getElement('np-domain');
    domainSelect.innerHTML = '';
    for (const domainKey of domainList) {
      const option = document.createElement('option');
      option.value = domainKey;
      option.textContent = domainKey.replace(/_/g, ' ').replace(/\b\w/g, ch => ch.toUpperCase());
      domainSelect.appendChild(option);
    }

    const voltageClasses = ['lv_5v', 'lv_12v', 'lv_24v', 'lv_48v', 'mains_120v', 'mains_240v'];
    const voltageSelect = getElement('np-voltage');
    voltageSelect.innerHTML = '';
    for (const voltageClass of voltageClasses) {
      const option = document.createElement('option');
      option.value = voltageClass;
      option.textContent = voltageClass.replace(/_/g, ' ').toUpperCase();
      voltageSelect.appendChild(option);
    }
    voltageSelect.value = 'lv_12v';
  } catch (error) {
    console.warn('Could not populate domain dropdowns:', error);
  }
}

function createProject() {
  const projectName = getElement('np-name').value.trim();
  const domain = getElement('np-domain').value;
  const voltageClass = getElement('np-voltage').value;
  const description = getElement('np-description').value.trim();

  if (!projectName) { alert('Project name is required.'); return; }

  appState.projectProfile = { project_name: projectName, domain, voltage_class: voltageClass, description };
  appState.components = [];
  appState.connections = [];

  closeModal('modal-new-project');
  refreshFullUI();
  setStatus(`Project "${projectName}" created`);
}

// ── Component CRUD ─────────────────────────────────────────────────────────

function openAddComponentModal() {
  appState.editingComponentId = null;
  getElement('modal-component-title').textContent = 'Add Component';
  getElement('comp-id').value = '';
  getElement('comp-name').value = '';
  getElement('comp-type').value = 'sensor';
  getElement('comp-current').value = '0';
  getElement('comp-position').value = '';
  getElement('comp-id').disabled = false;
  openModal('modal-component');
}

function openEditComponentModal(componentId) {
  const component = appState.components.find(c => c.component_id === componentId);
  if (!component) return;

  appState.editingComponentId = componentId;
  getElement('modal-component-title').textContent = 'Edit Component';
  getElement('comp-id').value = component.component_id;
  getElement('comp-id').disabled = true;
  getElement('comp-name').value = component.component_name;
  getElement('comp-type').value = component.component_type;
  getElement('comp-current').value = component.current_draw_amps;
  getElement('comp-position').value = component.position_label || '';
  openModal('modal-component');
}

function saveComponent() {
  const componentId = getElement('comp-id').value.trim();
  const componentName = getElement('comp-name').value.trim();
  const componentType = getElement('comp-type').value;
  const currentDraw = parseFloat(getElement('comp-current').value) || 0;
  const positionLabel = getElement('comp-position').value.trim();

  if (!componentId || !componentName) { alert('ID and Name are required.'); return; }

  const componentData = {
    component_id: componentId,
    component_name: componentName,
    component_type: componentType,
    current_draw_amps: currentDraw,
    position_label: positionLabel,
  };

  if (appState.editingComponentId) {
    const existingIndex = appState.components.findIndex(c => c.component_id === appState.editingComponentId);
    if (existingIndex >= 0) appState.components[existingIndex] = componentData;
  } else {
    if (appState.components.some(c => c.component_id === componentId)) {
      alert(`Component ID "${componentId}" already exists.`);
      return;
    }
    appState.components.push(componentData);
  }

  closeModal('modal-component');
  refreshFullUI();
  setStatus(`Component "${componentName}" saved`);
}

function deleteComponent(componentId) {
  if (!confirm(`Delete component "${componentId}" and its connections?`)) return;
  appState.components = appState.components.filter(c => c.component_id !== componentId);
  appState.connections = appState.connections.filter(
    c => c.from_component_id !== componentId && c.to_component_id !== componentId
  );
  clearSelection();
  refreshFullUI();
  setStatus(`Component "${componentId}" deleted`);
}

// ── Connection CRUD ────────────────────────────────────────────────────────

function openAddConnectionModal() {
  appState.editingConnectionId = null;
  getElement('modal-connection-title').textContent = 'Add Connection';
  getElement('conn-id').value = `conn_${String(appState.connections.length + 1).padStart(3, '0')}`;
  getElement('conn-id').disabled = false;
  getElement('conn-color').value = 'red';
  getElement('conn-from-pin').value = '';
  getElement('conn-to-pin').value = '';
  getElement('conn-current').value = '0';
  getElement('conn-length').value = '3';
  populateConnectionComponentDropdowns();
  openModal('modal-connection');
}

function openEditConnectionModal(connectionId) {
  const connection = appState.connections.find(c => c.connection_id === connectionId);
  if (!connection) return;

  appState.editingConnectionId = connectionId;
  getElement('modal-connection-title').textContent = 'Edit Connection';
  populateConnectionComponentDropdowns();
  getElement('conn-id').value = connection.connection_id;
  getElement('conn-id').disabled = true;
  getElement('conn-color').value = connection.wire_color;
  getElement('conn-from').value = connection.from_component_id;
  getElement('conn-from-pin').value = connection.from_pin;
  getElement('conn-to').value = connection.to_component_id;
  getElement('conn-to-pin').value = connection.to_pin;
  getElement('conn-current').value = connection.current_amps;
  getElement('conn-length').value = connection.run_length_ft;
  openModal('modal-connection');
}

function populateConnectionComponentDropdowns() {
  for (const selectId of ['conn-from', 'conn-to']) {
    const selectElement = getElement(selectId);
    selectElement.innerHTML = '';
    for (const comp of appState.components) {
      const option = document.createElement('option');
      option.value = comp.component_id;
      option.textContent = `${comp.component_name} (${comp.component_id})`;
      selectElement.appendChild(option);
    }
  }
}

function saveConnection() {
  const connectionId = getElement('conn-id').value.trim();
  const wireColor = getElement('conn-color').value;
  const fromComponent = getElement('conn-from').value;
  const fromPin = getElement('conn-from-pin').value.trim();
  const toComponent = getElement('conn-to').value;
  const toPin = getElement('conn-to-pin').value.trim();
  const currentAmps = parseFloat(getElement('conn-current').value) || 0;
  const runLengthFt = parseFloat(getElement('conn-length').value) || 0;

  if (!connectionId || !fromComponent || !toComponent || !fromPin || !toPin) {
    alert('All connection fields are required.');
    return;
  }

  const connectionData = {
    connection_id: connectionId,
    from_component_id: fromComponent,
    from_pin: fromPin,
    to_component_id: toComponent,
    to_pin: toPin,
    current_amps: currentAmps,
    run_length_ft: runLengthFt,
    wire_color: wireColor,
    awg_override: null,
  };

  if (appState.editingConnectionId) {
    const existingIndex = appState.connections.findIndex(c => c.connection_id === appState.editingConnectionId);
    if (existingIndex >= 0) appState.connections[existingIndex] = connectionData;
  } else {
    if (appState.connections.some(c => c.connection_id === connectionId)) {
      alert(`Connection ID "${connectionId}" already exists.`);
      return;
    }
    appState.connections.push(connectionData);
  }

  closeModal('modal-connection');
  refreshFullUI();
  setStatus(`Connection "${connectionId}" saved`);
}

function deleteConnection(connectionId) {
  if (!confirm(`Delete connection "${connectionId}"?`)) return;
  appState.connections = appState.connections.filter(c => c.connection_id !== connectionId);
  clearSelection();
  refreshFullUI();
  setStatus(`Connection "${connectionId}" deleted`);
}

// ── AI Assist ──────────────────────────────────────────────────────────────

async function openAiAssistModal() {
  openModal('modal-ai');
  // Show token status
  try {
    const hasToken = await eel.has_saved_token()();
    getElement('token-status').textContent = hasToken
      ? '✅ Token is saved.'
      : '⚠ No token saved. Enter one above or set WIRINGWIZARD_GITHUB_TOKEN env var.';
  } catch (error) {
    getElement('token-status').textContent = 'Could not check token status.';
  }
}

async function runAiDraft() {
  const briefText = getElement('ai-brief-text').value.trim();
  const projectName = getElement('ai-project-name').value.trim() || 'AI Draft Project';
  const tokenOverride = getElement('ai-token-input').value.trim() || null;

  if (!briefText) { alert('Please describe your wiring project.'); return; }

  showLoading(true);
  setStatus('🤖 AI is drafting your project…');

  try {
    const draftResult = await eel.draft_from_brief(briefText, projectName, tokenOverride)();

    if (draftResult.error) {
      alert(`AI Draft Error: ${draftResult.error}`);
      setStatus('AI draft failed');
      return;
    }

    // Load the draft into app state
    appState.projectProfile = {
      project_name: projectName,
      domain: draftResult.domain || 'automotive',
      voltage_class: draftResult.voltage_class || 'lv_12v',
      description: briefText.substring(0, 200),
    };
    appState.components = draftResult.components || [];
    appState.connections = draftResult.connections || [];

    closeModal('modal-ai');
    refreshFullUI();
    setStatus(`AI draft loaded: ${appState.components.length} components, ${appState.connections.length} connections`);
  } catch (error) {
    alert(`AI Draft Error: ${error}`);
    setStatus('AI draft failed');
  } finally {
    showLoading(false);
  }
}

async function saveToken() {
  const tokenValue = getElement('ai-token-input').value.trim();
  if (!tokenValue) { alert('Enter a token first.'); return; }
  try {
    await eel.save_api_token(tokenValue)();
    getElement('token-status').textContent = '✅ Token saved.';
    getElement('ai-token-input').value = '';
  } catch (error) {
    getElement('token-status').textContent = '❌ Failed to save token.';
  }
}

async function clearToken() {
  try {
    await eel.clear_api_token()();
    getElement('token-status').textContent = '✅ Token cleared.';
  } catch (error) {
    getElement('token-status').textContent = '❌ Failed to clear token.';
  }
}

async function saveSettingsToken() {
  const tokenValue = getElement('settings-token').value.trim();
  if (!tokenValue) { alert('Enter a token first.'); return; }
  try {
    await eel.save_api_token(tokenValue)();
    getElement('settings-token-status').textContent = '✅ Token saved.';
    getElement('settings-token').value = '';
  } catch (error) {
    getElement('settings-token-status').textContent = '❌ Failed to save token.';
  }
}

async function clearSettingsToken() {
  try {
    await eel.clear_api_token()();
    getElement('settings-token-status').textContent = '✅ Token cleared.';
  } catch (error) {
    getElement('settings-token-status').textContent = '❌ Failed to clear token.';
  }
}

// ── Report Generation ──────────────────────────────────────────────────────

async function generateReport() {
  if (!appState.projectProfile || appState.components.length === 0) {
    alert('Create a project and add components first.');
    return;
  }

  showLoading(true);
  setStatus('Generating wiring plan…');

  try {
    const reportText = await eel.generate_report(
      appState.projectProfile,
      appState.components,
      appState.connections
    )();

    if (reportText.error) {
      alert(`Report Error: ${reportText.error}`);
      setStatus('Report generation failed');
      return;
    }

    getElement('report-output').textContent = reportText;
    openModal('modal-report');
    setStatus('Report generated');
  } catch (error) {
    alert(`Report Error: ${error}`);
    setStatus('Report generation failed');
  } finally {
    showLoading(false);
  }
}

function copyReport() {
  const reportText = getElement('report-output').textContent;
  navigator.clipboard.writeText(reportText).then(() => {
    setStatus('Report copied to clipboard');
  }).catch(() => {
    // Fallback for older browsers
    const textArea = document.createElement('textarea');
    textArea.value = reportText;
    document.body.appendChild(textArea);
    textArea.select();
    document.execCommand('copy');
    document.body.removeChild(textArea);
    setStatus('Report copied to clipboard');
  });
}

// ── Remap (Apply Changes) ─────────────────────────────────────────────────

async function applyRemap() {
  const remapJson = getElement('remap-json').value.trim();
  if (!remapJson) { alert('Enter change requests as JSON.'); return; }

  showLoading(true);
  setStatus('Applying changes…');

  try {
    const result = await eel.apply_changes_to_project(
      appState.projectProfile,
      appState.components,
      appState.connections,
      remapJson
    )();

    if (result.error) {
      alert(`Remap Error: ${result.error}`);
      setStatus('Remap failed');
      return;
    }

    appState.components = result.components || appState.components;
    appState.connections = result.connections || appState.connections;

    closeModal('modal-remap');
    refreshFullUI();
    setStatus('Changes applied');
  } catch (error) {
    alert(`Remap Error: ${error}`);
    setStatus('Remap failed');
  } finally {
    showLoading(false);
  }
}

// ── Save / Load Draft ──────────────────────────────────────────────────────

async function saveDraft() {
  if (!appState.projectProfile) { alert('No project to save.'); return; }

  try {
    await eel.save_draft({
      profile: appState.projectProfile,
      components: appState.components,
      connections: appState.connections,
    })();
    setStatus('Draft saved');
  } catch (error) {
    alert(`Save failed: ${error}`);
  }
}

async function loadDraft() {
  try {
    const draftData = await eel.load_draft()();
    if (!draftData || draftData.error) {
      setStatus('No saved draft found');
      return;
    }
    appState.projectProfile = draftData.profile || null;
    appState.components = draftData.components || [];
    appState.connections = draftData.connections || [];
    refreshFullUI();
    setStatus('Draft loaded');
  } catch (error) {
    alert(`Load failed: ${error}`);
  }
}

async function loadDraftIfAvailable() {
  try {
    const draftData = await eel.load_draft()();
    if (draftData && !draftData.error && draftData.profile) {
      appState.projectProfile = draftData.profile;
      appState.components = draftData.components || [];
      appState.connections = draftData.connections || [];
      refreshFullUI();
      setStatus(`Loaded draft: ${appState.projectProfile.project_name}`);
    }
  } catch (_unusedError) {
    // No draft available — this is fine on first launch
  }
}

// ── Full UI Refresh ────────────────────────────────────────────────────────

function refreshFullUI() {
  updateProjectDisplay();
  refreshSidebarTree();
  renderDiagram(appState.components, appState.connections);
  updateStatusCounts();
  showEmptyInspector();
  updateZoomDisplay();
}

function updateProjectDisplay() {
  const displayElement = getElement('project-name-display');
  if (appState.projectProfile) {
    displayElement.textContent = appState.projectProfile.project_name;
  } else {
    displayElement.textContent = 'No Project';
  }

  // Status bar domain/voltage badges
  const domainBadge = getElement('status-domain');
  const voltageBadge = getElement('status-voltage');
  if (appState.projectProfile) {
    domainBadge.textContent = appState.projectProfile.domain.replace(/_/g, ' ');
    voltageBadge.textContent = appState.projectProfile.voltage_class.replace(/_/g, ' ').toUpperCase();
  } else {
    domainBadge.textContent = '';
    voltageBadge.textContent = '';
  }
}

function updateStatusCounts() {
  const countsElement = getElement('status-counts');
  countsElement.textContent = `${appState.components.length} components · ${appState.connections.length} wires`;
}

// ── Loading Overlay ────────────────────────────────────────────────────────

function showLoading(isVisible) {
  let overlay = document.getElementById('loading-overlay');
  if (!overlay && isVisible) {
    overlay = document.createElement('div');
    overlay.id = 'loading-overlay';
    overlay.className = 'loading-overlay';
    overlay.innerHTML = '<div class="spinner"></div>';
    document.body.appendChild(overlay);
  }
  if (overlay) overlay.hidden = !isVisible;
}

// ── Status Bar ─────────────────────────────────────────────────────────────

function setStatus(message) {
  getElement('status-text').textContent = message;
}

// ── Utility ────────────────────────────────────────────────────────────────

function getElement(elementId) {
  return document.getElementById(elementId);
}

function escapeHtml(unsafeText) {
  const tempDiv = document.createElement('div');
  tempDiv.textContent = unsafeText || '';
  return tempDiv.innerHTML;
}
