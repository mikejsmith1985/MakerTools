/**
 * diagram.js — SVG-based interactive wiring diagram renderer for WiringWizard.
 * Handles component layout, wire routing, zoom/pan, selection, and circuit tracing.
 */

// ── Component Type Visual Config ───────────────────────────────────────────
const COMPONENT_TYPE_CONFIG = {
  battery:        { icon: '🔋', color: '#e85454', label: 'BAT' },
  power_supply:   { icon: '⚡', color: '#e85454', label: 'PSU' },
  ecu:            { icon: '🧠', color: '#58a6ff', label: 'ECU' },
  microcontroller:{ icon: '💻', color: '#58a6ff', label: 'MCU' },
  relay:          { icon: '🔀', color: '#d29922', label: 'RLY' },
  fuse:           { icon: '🛡️', color: '#d29922', label: 'FSE' },
  led_load:       { icon: '💡', color: '#3fb950', label: 'LED' },
  light:          { icon: '🔦', color: '#3fb950', label: 'LGT' },
  motor:          { icon: '⚙️', color: '#a371f7', label: 'MTR' },
  servo:          { icon: '🎯', color: '#a371f7', label: 'SRV' },
  fan:            { icon: '🌀', color: '#a371f7', label: 'FAN' },
  pump:           { icon: '💧', color: '#a371f7', label: 'PMP' },
  sensor:         { icon: '📡', color: '#3fb950', label: 'SNS' },
  switch:         { icon: '🔘', color: '#d29922', label: 'SWT' },
  display:        { icon: '🖥️', color: '#58a6ff', label: 'DSP' },
  buzzer:         { icon: '🔔', color: '#db6d28', label: 'BZR' },
  solenoid:       { icon: '🧲', color: '#a371f7', label: 'SOL' },
  stepper:        { icon: '⚙️', color: '#a371f7', label: 'STP' },
  motor_driver:   { icon: '🔧', color: '#d29922', label: 'DRV' },
};
const DEFAULT_TYPE_CONFIG = { icon: '❓', color: '#7d8590', label: '???' };

// Wire color CSS values matching the reference palette
const WIRE_COLOR_MAP = {
  red:    '#e85454', black:  '#8b8b8b', blue:   '#58a6ff',
  green:  '#3fb950', yellow: '#d29922', orange: '#db6d28',
  white:  '#d0d7de', purple: '#a371f7', brown:  '#a0704e',
  pink:   '#db61a2', 'yellow/green': '#b8cc2a',
};
const DEFAULT_WIRE_COLOR = '#7d8590';

// Layout constants
const CARD_WIDTH = 170;
const CARD_HEIGHT_BASE = 80;
const CARD_HEIGHT_PER_PIN = 14;
const CARD_HEIGHT_MIN = 80;
const CARD_PADDING = 14;
const CARD_HEADER_HEIGHT = 24;
const PIN_RADIUS = 5;
const COLUMN_GAP = 240;
const ROW_GAP = 120;
const GRID_MARGIN_X = 80;
const GRID_MARGIN_Y = 60;
const GRID_DOT_SPACING = 30;

// Pin type color mapping for visual differentiation on the diagram
const PIN_TYPE_COLORS = {
  power_input:   '#e85454',
  power_output:  '#e85454',
  switched_power:'#db6d28',
  ground:        '#8b8b8b',
  signal_input:  '#3fb950',
  signal_output: '#3fb950',
  can_high:      '#58a6ff',
  can_low:       '#58a6ff',
  pwm_output:    '#a371f7',
  serial_tx:     '#d29922',
  serial_rx:     '#d29922',
  general:       '#7d8590',
};

// Power types placed on the left column
const POWER_SOURCE_TYPES = new Set(['battery', 'power_supply']);
// Control/processing types in center
const CONTROLLER_TYPES = new Set([
  'ecu', 'microcontroller', 'motor_driver', 'display', 'ignition_switch',
]);
// Protection placed between source and loads
const PROTECTION_TYPES = new Set(['fuse', 'fuse_box', 'relay']);
// Infrastructure types placed in their own column
const INFRASTRUCTURE_TYPES = new Set([
  'ground_bus', 'termination_resistor',
]);

// ── SVG Namespace ──────────────────────────────────────────────────────────
const SVG_NS = 'http://www.w3.org/2000/svg';

/**
 * Create an SVG element with the given tag and attributes.
 */
function createSvgElement(tagName, attributes = {}) {
  const element = document.createElementNS(SVG_NS, tagName);
  for (const [key, value] of Object.entries(attributes)) {
    element.setAttribute(key, String(value));
  }
  return element;
}

// ── Diagram State ──────────────────────────────────────────────────────────
let diagramState = {
  components: [],
  connections: [],
  componentPositions: new Map(),  // componentId → {x, y, width, height}
  pinPositions: new Map(),        // "componentId:pinLabel" → {x, y}
  scaleFactor: 1.0,
  panX: 0,
  panY: 0,
  isPanning: false,
  panStartX: 0,
  panStartY: 0,
  selectedComponentId: null,
  selectedConnectionId: null,
  tracedCircuit: new Set(),       // Set of connection IDs in the traced circuit
};

// ── Public API ─────────────────────────────────────────────────────────────

/**
 * Render the full diagram from component and connection data arrays.
 * Clears existing content and rebuilds everything.
 */
export function renderDiagram(components, connections) {
  diagramState.components = components || [];
  diagramState.connections = connections || [];
  diagramState.selectedComponentId = null;
  diagramState.selectedConnectionId = null;
  diagramState.tracedCircuit.clear();

  const svg = document.getElementById('diagram-svg');
  const canvasEmpty = document.getElementById('canvas-empty');

  if (diagramState.components.length === 0) {
    canvasEmpty.classList.remove('hidden');
    clearLayers();
    return;
  }
  canvasEmpty.classList.add('hidden');

  computeLayout();
  clearLayers();
  drawGrid();
  drawWires();
  drawComponents();
  updateLegend();
  fitToView();
}

/**
 * Select a component by ID (highlights it in the diagram and sidebar).
 */
export function selectComponent(componentId) {
  clearSelection();
  diagramState.selectedComponentId = componentId;
  diagramState.tracedCircuit.clear();

  // Dim everything except the selected component and its wires
  const connectedWireIds = new Set();
  for (const conn of diagramState.connections) {
    if (conn.from_component_id === componentId || conn.to_component_id === componentId) {
      connectedWireIds.add(conn.connection_id);
    }
  }

  // Dim components not selected
  document.querySelectorAll('.comp-group').forEach(group => {
    const isSelected = group.dataset.id === componentId;
    group.classList.toggle('selected', isSelected);
    group.classList.toggle('dimmed', !isSelected &&
      !connectedWireIds.size || (!isSelected && !isConnectedTo(group.dataset.id, componentId)));
  });

  // Dim wires not connected
  document.querySelectorAll('.wire-group').forEach(group => {
    const isConnected = connectedWireIds.has(group.dataset.id);
    group.classList.toggle('dimmed', !isConnected);
    group.querySelector('.wire-path')?.classList.toggle('selected', isConnected);
  });

  // Dispatch custom event for the inspector
  document.dispatchEvent(new CustomEvent('diagram:select', {
    detail: { type: 'component', id: componentId }
  }));
}

/**
 * Select a connection (wire) by ID and trace its full circuit.
 */
export function selectConnection(connectionId) {
  clearSelection();
  diagramState.selectedConnectionId = connectionId;

  // BFS flood-fill to trace the complete circuit through shared components
  const tracedConnectionIds = traceCircuit(connectionId);
  diagramState.tracedCircuit = tracedConnectionIds;

  const involvedComponentIds = new Set();
  for (const conn of diagramState.connections) {
    if (tracedConnectionIds.has(conn.connection_id)) {
      involvedComponentIds.add(conn.from_component_id);
      involvedComponentIds.add(conn.to_component_id);
    }
  }

  // Highlight traced wires, dim the rest
  document.querySelectorAll('.wire-group').forEach(group => {
    const isTraced = tracedConnectionIds.has(group.dataset.id);
    group.querySelector('.wire-path')?.classList.toggle('selected', isTraced);
    group.classList.toggle('dimmed', !isTraced);
  });

  // Dim components not in the traced circuit
  document.querySelectorAll('.comp-group').forEach(group => {
    group.classList.toggle('dimmed', !involvedComponentIds.has(group.dataset.id));
  });

  document.dispatchEvent(new CustomEvent('diagram:select', {
    detail: { type: 'connection', id: connectionId }
  }));
}

/**
 * Clear all selections and restore full opacity.
 */
export function clearSelection() {
  diagramState.selectedComponentId = null;
  diagramState.selectedConnectionId = null;
  diagramState.tracedCircuit.clear();

  document.querySelectorAll('.comp-group').forEach(g => {
    g.classList.remove('selected', 'dimmed');
  });
  document.querySelectorAll('.wire-group').forEach(g => {
    g.classList.remove('dimmed');
    g.querySelector('.wire-path')?.classList.remove('selected');
  });

  document.dispatchEvent(new CustomEvent('diagram:deselect'));
}

// Zoom API
export function zoomIn() { setZoom(diagramState.scaleFactor * 1.15); }
export function zoomOut() { setZoom(diagramState.scaleFactor / 1.15); }
export function fitToView() {
  const svg = document.getElementById('diagram-svg');
  if (!svg) return;
  const containerRect = svg.getBoundingClientRect();
  const bounds = getContentBounds();
  if (!bounds) { setZoom(1.0); return; }

  const horizontalScale = (containerRect.width - 40) / bounds.width;
  const verticalScale = (containerRect.height - 40) / bounds.height;
  const fitScale = Math.min(horizontalScale, verticalScale, 1.5);

  diagramState.scaleFactor = fitScale;
  diagramState.panX = (containerRect.width - bounds.width * fitScale) / 2 - bounds.x * fitScale;
  diagramState.panY = (containerRect.height - bounds.height * fitScale) / 2 - bounds.y * fitScale;
  applyTransform();
}

export function getZoomLevel() {
  return Math.round(diagramState.scaleFactor * 100);
}

// ── Layout Algorithm ───────────────────────────────────────────────────────

/**
 * Compute x/y positions for all components using a column-based layout.
 * Power sources left, controllers center, loads right, protection between.
 */
function computeLayout() {
  diagramState.componentPositions.clear();
  diagramState.pinPositions.clear();

  const columns = { power: [], protection: [], controller: [], load: [], infra: [] };

  for (const comp of diagramState.components) {
    const componentType = comp.component_type || '';
    if (POWER_SOURCE_TYPES.has(componentType)) columns.power.push(comp);
    else if (PROTECTION_TYPES.has(componentType)) columns.protection.push(comp);
    else if (CONTROLLER_TYPES.has(componentType)) columns.controller.push(comp);
    else if (INFRASTRUCTURE_TYPES.has(componentType)) columns.infra.push(comp);
    else columns.load.push(comp);
  }

  const columnOrder = ['power', 'protection', 'controller', 'load', 'infra'];
  let currentColumnX = GRID_MARGIN_X;

  for (const columnName of columnOrder) {
    const columnComponents = columns[columnName];
    if (columnComponents.length === 0) continue;

    let currentRowY = GRID_MARGIN_Y;
    for (const comp of columnComponents) {
      const cardHeight = computeCardHeight(comp);
      diagramState.componentPositions.set(comp.component_id, {
        x: currentColumnX,
        y: currentRowY,
        width: CARD_WIDTH,
        height: cardHeight,
      });
      currentRowY += cardHeight + ROW_GAP;
    }
    currentColumnX += CARD_WIDTH + COLUMN_GAP;
  }

  // Compute pin positions for all components (library pins + connection pins)
  computePinPositions();
}

/**
 * Compute card height to fit all defined pins. Cards with no pins use the
 * base height; cards with pins grow to accommodate the full pin list.
 */
function computeCardHeight(component) {
  const pinCount = (component.pins || []).length;
  if (pinCount === 0) return CARD_HEIGHT_MIN;
  // Base area (header + name + current) is ~60px, then add per-pin rows
  const pinAreaHeight = pinCount * CARD_HEIGHT_PER_PIN + 8;
  return Math.max(CARD_HEIGHT_MIN, 60 + pinAreaHeight);
}

/**
 * Compute pin positions on component edges.
 *
 * Phase 1: If a component has library-defined pins (component.pins[]),
 * ALL pins are placed in a vertical list on both edges — left for input-type
 * pins, right for output-type pins.
 *
 * Phase 2: For connection-only pins (components without library pin data),
 * pins are placed dynamically based on connections, as before.
 */
function computePinPositions() {
  const LEFT_PIN_TYPES = new Set([
    'power_input', 'ground', 'signal_input', 'can_low', 'serial_rx', 'general',
  ]);

  // Phase 1: Library-defined pins
  for (const comp of diagramState.components) {
    const pins = comp.pins || [];
    if (pins.length === 0) continue;

    const pos = diagramState.componentPositions.get(comp.component_id);
    if (!pos) continue;

    const leftPins = pins.filter(p => LEFT_PIN_TYPES.has(p.pin_type || 'general'));
    const rightPins = pins.filter(p => !LEFT_PIN_TYPES.has(p.pin_type || 'general'));

    const pinStartY = pos.y + CARD_HEADER_HEIGHT + 18;

    leftPins.forEach((pin, idx) => {
      const pinKey = `${comp.component_id}:${pin.pin_id || pin.name}`;
      diagramState.pinPositions.set(pinKey, {
        x: pos.x,
        y: pinStartY + idx * CARD_HEIGHT_PER_PIN,
        pinType: pin.pin_type || 'general',
        label: pin.name || pin.pin_id,
        isDefined: true,
      });
    });

    rightPins.forEach((pin, idx) => {
      const pinKey = `${comp.component_id}:${pin.pin_id || pin.name}`;
      diagramState.pinPositions.set(pinKey, {
        x: pos.x + pos.width,
        y: pinStartY + idx * CARD_HEIGHT_PER_PIN,
        pinType: pin.pin_type || 'general',
        label: pin.name || pin.pin_id,
        isDefined: true,
      });
    });
  }

  // Phase 2: Connection-based pins for components WITHOUT library pin data
  const componentPinCounts = new Map();

  for (const conn of diagramState.connections) {
    const fromPos = diagramState.componentPositions.get(conn.from_component_id);
    const toPos = diagramState.componentPositions.get(conn.to_component_id);
    if (!fromPos || !toPos) continue;

    const fromKey = `${conn.from_component_id}:${conn.from_pin}`;
    if (!diagramState.pinPositions.has(fromKey)) {
      if (!componentPinCounts.has(conn.from_component_id)) {
        componentPinCounts.set(conn.from_component_id, { left: [], right: [] });
      }
      componentPinCounts.get(conn.from_component_id).right.push(fromKey);
    }

    const toKey = `${conn.to_component_id}:${conn.to_pin}`;
    if (!diagramState.pinPositions.has(toKey)) {
      if (!componentPinCounts.has(conn.to_component_id)) {
        componentPinCounts.set(conn.to_component_id, { left: [], right: [] });
      }
      componentPinCounts.get(conn.to_component_id).left.push(toKey);
    }
  }

  for (const [componentId, sides] of componentPinCounts) {
    const pos = diagramState.componentPositions.get(componentId);
    if (!pos) continue;

    const usableHeight = pos.height - CARD_HEADER_HEIGHT - 10;
    const topOffset = pos.y + CARD_HEADER_HEIGHT + 8;

    sides.left.forEach((pinKey, pinIndex) => {
      if (diagramState.pinPositions.has(pinKey)) return;
      const pinSpacing = usableHeight / (sides.left.length + 1);
      diagramState.pinPositions.set(pinKey, {
        x: pos.x,
        y: topOffset + pinSpacing * (pinIndex + 1),
        isDefined: false,
      });
    });

    sides.right.forEach((pinKey, pinIndex) => {
      if (diagramState.pinPositions.has(pinKey)) return;
      const pinSpacing = usableHeight / (sides.right.length + 1);
      diagramState.pinPositions.set(pinKey, {
        x: pos.x + pos.width,
        y: topOffset + pinSpacing * (pinIndex + 1),
        isDefined: false,
      });
    });
  }
}

// ── Drawing Functions ──────────────────────────────────────────────────────

function clearLayers() {
  for (const layerId of ['grid-layer', 'wires-layer', 'components-layer', 'labels-layer']) {
    const layer = document.getElementById(layerId);
    if (layer) layer.innerHTML = '';
  }
}

function drawGrid() {
  const gridLayer = document.getElementById('grid-layer');
  if (!gridLayer) return;

  const bounds = getContentBounds() || { x: 0, y: 0, width: 2000, height: 1200 };
  const gridStartX = 0;
  const gridStartY = 0;
  const gridEndX = bounds.x + bounds.width + 200;
  const gridEndY = bounds.y + bounds.height + 200;

  for (let gridX = gridStartX; gridX < gridEndX; gridX += GRID_DOT_SPACING) {
    for (let gridY = gridStartY; gridY < gridEndY; gridY += GRID_DOT_SPACING) {
      gridLayer.appendChild(createSvgElement('circle', {
        cx: gridX, cy: gridY, r: 1, fill: '#1a1f27', class: 'grid-dot',
      }));
    }
  }
}

function drawComponents() {
  const componentsLayer = document.getElementById('components-layer');
  if (!componentsLayer) return;

  for (const comp of diagramState.components) {
    const pos = diagramState.componentPositions.get(comp.component_id);
    if (!pos) continue;

    const typeConfig = COMPONENT_TYPE_CONFIG[comp.component_type] || DEFAULT_TYPE_CONFIG;
    const group = createSvgElement('g', {
      class: 'comp-group',
      'data-id': comp.component_id,
      transform: `translate(${pos.x}, ${pos.y})`,
    });

    // Card background with type-colored border
    group.appendChild(createSvgElement('rect', {
      class: 'comp-card-bg',
      width: pos.width, height: pos.height,
      fill: '#161b22', stroke: typeConfig.color, 'stroke-width': 1.5,
      rx: 8, ry: 8, filter: 'url(#card-shadow)',
    }));

    // Type accent stripe along the top
    group.appendChild(createSvgElement('rect', {
      x: 0, y: 0, width: pos.width, height: CARD_HEADER_HEIGHT,
      fill: typeConfig.color, opacity: 0.15,
      rx: 8, ry: 8,
    }));
    // Cover bottom corners of the header stripe
    group.appendChild(createSvgElement('rect', {
      x: 0, y: 12, width: pos.width, height: 12,
      fill: typeConfig.color, opacity: 0.15,
    }));

    // Type badge
    group.appendChild(createSvgElement('text', {
      x: 10, y: 16, fill: typeConfig.color,
      'font-size': '10', 'font-weight': '700', 'font-family': 'var(--font-mono)',
    })).textContent = typeConfig.label;

    // Component icon
    group.appendChild(createSvgElement('text', {
      x: pos.width - 10, y: 17, fill: typeConfig.color,
      'font-size': '13', 'text-anchor': 'end',
    })).textContent = typeConfig.icon;

    // Component name (truncated)
    const displayName = truncateText(comp.component_name || comp.component_id, 22);
    group.appendChild(createSvgElement('text', {
      x: pos.width / 2, y: 42, fill: '#e6edf3',
      'font-size': '12', 'font-weight': '600', 'text-anchor': 'middle',
      'font-family': 'var(--font-family)',
    })).textContent = displayName;

    // Current draw info
    const currentAmps = comp.current_draw_amps || 0;
    const pinCount = (comp.pins || []).length;
    const metaText = pinCount > 0 ? `${currentAmps}A  |  ${pinCount} pins` : `${currentAmps}A`;
    group.appendChild(createSvgElement('text', {
      x: pos.width / 2, y: 58, fill: '#7d8590',
      'font-size': '10', 'text-anchor': 'middle',
      'font-family': 'var(--font-mono)',
    })).textContent = metaText;

    // Position label
    if (comp.position_label && comp.position_label !== 'TBD') {
      group.appendChild(createSvgElement('text', {
        x: pos.width / 2, y: 72, fill: '#484f58',
        'font-size': '9', 'text-anchor': 'middle',
        'font-family': 'var(--font-family)',
      })).textContent = truncateText(comp.position_label, 24);
    }

    // Draw pin dots
    drawComponentPins(group, comp, pos);

    // Click handler
    group.addEventListener('click', (event) => {
      event.stopPropagation();
      selectComponent(comp.component_id);
    });

    componentsLayer.appendChild(group);
  }
}

/**
 * Draw all pin dots and labels on a component card's edges.
 * Library-defined pins get colored dots by type; connection-only pins are blue.
 * Connected pins get a brighter fill to indicate an active wire.
 */
function drawComponentPins(parentGroup, component, position) {
  // Build a set of connected pin keys for highlighting
  const connectedPinKeys = new Set();
  for (const conn of diagramState.connections) {
    connectedPinKeys.add(`${conn.from_component_id}:${conn.from_pin}`);
    connectedPinKeys.add(`${conn.to_component_id}:${conn.to_pin}`);
  }

  for (const [pinKey, pinPos] of diagramState.pinPositions) {
    if (!pinKey.startsWith(component.component_id + ':')) continue;

    const localX = pinPos.x - position.x;
    const localY = pinPos.y - position.y;
    const pinLabel = pinPos.label || pinKey.split(':')[1];
    const pinTypeColor = PIN_TYPE_COLORS[pinPos.pinType] || '#7d8590';
    const isConnected = connectedPinKeys.has(pinKey);
    const isDefined = pinPos.isDefined;

    // Pin dot — filled if connected, hollow if not
    parentGroup.appendChild(createSvgElement('circle', {
      class: 'pin-dot',
      cx: localX, cy: localY, r: PIN_RADIUS,
      fill: isConnected ? pinTypeColor : '#21262d',
      stroke: isDefined ? pinTypeColor : '#58a6ff',
      'stroke-width': isConnected ? 2 : 1.5,
    }));

    // Pin label — positioned outside the card edge
    const isLeftSide = localX < position.width / 2;
    parentGroup.appendChild(createSvgElement('text', {
      x: isLeftSide ? localX + 8 : localX - 8,
      y: localY + 3,
      fill: isDefined ? '#7d8590' : '#484f58',
      'font-size': '8',
      'text-anchor': isLeftSide ? 'start' : 'end',
      'font-family': 'var(--font-mono)',
    })).textContent = truncateText(pinLabel, 14);
  }
}

/**
 * Draw all connection wires using Manhattan routing (right-angle paths).
 */
function drawWires() {
  const wiresLayer = document.getElementById('wires-layer');
  if (!wiresLayer) return;

  for (const conn of diagramState.connections) {
    const fromPinKey = `${conn.from_component_id}:${conn.from_pin}`;
    const toPinKey = `${conn.to_component_id}:${conn.to_pin}`;
    const fromPin = diagramState.pinPositions.get(fromPinKey);
    const toPin = diagramState.pinPositions.get(toPinKey);

    if (!fromPin || !toPin) continue;

    const wireColor = WIRE_COLOR_MAP[conn.wire_color] || DEFAULT_WIRE_COLOR;
    const wireGroup = createSvgElement('g', {
      class: 'wire-group', 'data-id': conn.connection_id,
    });

    // Manhattan path: horizontal out → vertical → horizontal in
    const midX = (fromPin.x + toPin.x) / 2;
    const pathData = `M${fromPin.x},${fromPin.y} ` +
      `L${midX},${fromPin.y} ` +
      `L${midX},${toPin.y} ` +
      `L${toPin.x},${toPin.y}`;

    wireGroup.appendChild(createSvgElement('path', {
      class: 'wire-path', d: pathData, stroke: wireColor,
      'stroke-width': 2, fill: 'none',
      'marker-end': 'url(#arrowhead)',
    }));

    // Wire label at the midpoint
    const labelX = midX;
    const labelY = (fromPin.y + toPin.y) / 2;
    const labelText = conn.connection_id;

    const labelBackground = createSvgElement('rect', {
      class: 'wire-label-bg',
      x: labelX - 24, y: labelY - 8,
      width: 48, height: 14,
      fill: '#0d1117', stroke: wireColor, 'stroke-width': 0.5,
      opacity: 0.9,
    });
    wireGroup.appendChild(labelBackground);

    wireGroup.appendChild(createSvgElement('text', {
      x: labelX, y: labelY + 3,
      fill: wireColor, 'font-size': '8', 'text-anchor': 'middle',
      'font-family': 'var(--font-mono)', 'font-weight': '600',
    })).textContent = labelText;

    // Click handler for circuit tracing
    wireGroup.addEventListener('click', (event) => {
      event.stopPropagation();
      selectConnection(conn.connection_id);
    });

    wiresLayer.appendChild(wireGroup);
  }
}

// ── Circuit Tracing (BFS) ──────────────────────────────────────────────────

/**
 * Trace a complete circuit starting from a given connection via BFS flood fill.
 * Follows shared components to find all electrically connected wires.
 */
function traceCircuit(startConnectionId) {
  const tracedIds = new Set();
  const connectionQueue = [startConnectionId];

  while (connectionQueue.length > 0) {
    const currentConnectionId = connectionQueue.shift();
    if (tracedIds.has(currentConnectionId)) continue;
    tracedIds.add(currentConnectionId);

    const currentConnection = diagramState.connections.find(
      c => c.connection_id === currentConnectionId
    );
    if (!currentConnection) continue;

    // Find all other connections that share a component with this one
    for (const otherConnection of diagramState.connections) {
      if (tracedIds.has(otherConnection.connection_id)) continue;
      const isSharesComponent =
        otherConnection.from_component_id === currentConnection.from_component_id ||
        otherConnection.from_component_id === currentConnection.to_component_id ||
        otherConnection.to_component_id === currentConnection.from_component_id ||
        otherConnection.to_component_id === currentConnection.to_component_id;
      if (isSharesComponent) {
        connectionQueue.push(otherConnection.connection_id);
      }
    }
  }
  return tracedIds;
}

function isConnectedTo(componentIdA, componentIdB) {
  return diagramState.connections.some(
    c => (c.from_component_id === componentIdA && c.to_component_id === componentIdB) ||
         (c.to_component_id === componentIdA && c.from_component_id === componentIdB)
  );
}

// ── Zoom / Pan ─────────────────────────────────────────────────────────────

function setZoom(newScale) {
  diagramState.scaleFactor = Math.max(0.2, Math.min(3.0, newScale));
  applyTransform();
  updateZoomDisplay();
}

function applyTransform() {
  const zoomGroup = document.getElementById('zoom-group');
  if (zoomGroup) {
    zoomGroup.setAttribute('transform',
      `translate(${diagramState.panX}, ${diagramState.panY}) scale(${diagramState.scaleFactor})`
    );
  }
}

function updateZoomDisplay() {
  const zoomDisplay = document.getElementById('zoom-level');
  if (zoomDisplay) {
    zoomDisplay.textContent = `${Math.round(diagramState.scaleFactor * 100)}%`;
  }
}

function getContentBounds() {
  const positions = Array.from(diagramState.componentPositions.values());
  if (positions.length === 0) return null;

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const pos of positions) {
    minX = Math.min(minX, pos.x);
    minY = Math.min(minY, pos.y);
    maxX = Math.max(maxX, pos.x + pos.width);
    maxY = Math.max(maxY, pos.y + pos.height);
  }
  return { x: minX - 40, y: minY - 40, width: maxX - minX + 80, height: maxY - minY + 80 };
}

/** Update the wire color legend in the sidebar. */
function updateLegend() {
  const legendContainer = document.getElementById('legend-items');
  if (!legendContainer) return;
  legendContainer.innerHTML = '';

  const usedColors = new Set();
  for (const conn of diagramState.connections) {
    if (conn.wire_color) usedColors.add(conn.wire_color);
  }

  for (const colorName of usedColors) {
    const cssColor = WIRE_COLOR_MAP[colorName] || DEFAULT_WIRE_COLOR;
    const legendItem = document.createElement('div');
    legendItem.className = 'legend-item';
    legendItem.innerHTML =
      `<span class="legend-swatch" style="background:${cssColor}"></span>` +
      `<span>${colorName.charAt(0).toUpperCase() + colorName.slice(1)}</span>`;
    legendContainer.appendChild(legendItem);
  }
}

// ── Pan / Zoom Event Setup ─────────────────────────────────────────────────

export function initCanvasInteraction() {
  const svg = document.getElementById('diagram-svg');
  if (!svg) return;

  // Pan with mouse drag
  svg.addEventListener('mousedown', (event) => {
    if (event.button !== 0) return;
    diagramState.isPanning = true;
    diagramState.panStartX = event.clientX - diagramState.panX;
    diagramState.panStartY = event.clientY - diagramState.panY;
    svg.classList.add('panning');
  });

  window.addEventListener('mousemove', (event) => {
    if (!diagramState.isPanning) return;
    diagramState.panX = event.clientX - diagramState.panStartX;
    diagramState.panY = event.clientY - diagramState.panStartY;
    applyTransform();
  });

  window.addEventListener('mouseup', () => {
    diagramState.isPanning = false;
    svg.classList.remove('panning');
  });

  // Zoom with scroll wheel
  svg.addEventListener('wheel', (event) => {
    event.preventDefault();
    const zoomDelta = event.deltaY < 0 ? 1.08 : 1 / 1.08;
    setZoom(diagramState.scaleFactor * zoomDelta);
  }, { passive: false });

  // Click on empty canvas area clears selection
  svg.addEventListener('click', (event) => {
    if (event.target === svg || event.target.id === 'grid-layer' ||
        event.target.classList.contains('grid-dot')) {
      clearSelection();
    }
  });
}

// ── Utility ────────────────────────────────────────────────────────────────

function truncateText(text, maxLength) {
  if (!text) return '';
  return text.length > maxLength ? text.substring(0, maxLength - 1) + '…' : text;
}

/**
 * Get component type config for a given type string.
 */
export function getTypeConfig(componentType) {
  return COMPONENT_TYPE_CONFIG[componentType] || DEFAULT_TYPE_CONFIG;
}

export { WIRE_COLOR_MAP };
