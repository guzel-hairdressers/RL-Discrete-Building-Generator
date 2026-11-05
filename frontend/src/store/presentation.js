// Display semantics shared by the workspace and protocol tests.
export const number = (value) => value == null || value === '' || !Number.isFinite(Number(value)) ? null : Number(value);
export const format = (value, digits = 0) => number(value) == null ? '—' : number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
export const percent = (value) => number(value) == null ? '—' : `${format(Number(value) * 100, 1)}%`;
export function moduleColor(id) {
  let hash = 2166136261;
  for (const c of String(id || 'unknown')) hash = Math.imul(hash ^ c.charCodeAt(0), 16777619);
  return `hsl(${((hash % 360) + 360) % 360}, 46%, 62%)`;
}
export function moduleInventory(nodes = [], dictionary = []) {
  const groups = new Map();
  for (const node of nodes) {
    if (node.type === 'void' || !node.moduleId) continue;
    if (!groups.has(node.moduleId)) groups.set(node.moduleId, { id: node.moduleId, occurrences: new Set(), references: 0, functions: new Set(), identified: true });
    const group = groups.get(node.moduleId);
    group.references++;
    if (node.occurrenceId != null) group.occurrences.add(node.occurrenceId);
    else group.identified = false;
    group.functions.add(node.type);
  }
  return [...groups.values()].map((g) => ({ ...g,
    independent: g.identified ? g.occurrences.size : null,
    copies: g.identified ? g.references - g.occurrences.size : null,
    shape: dictionary.find((d) => (d.id ?? d.moduleId) === g.id),
  })).sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true }));
}
export function validationLabel(validation) {
  if (validation?.valid === true) return 'Geometry & access checked';
  if (validation?.valid === false) return 'Validation failed';
  return 'Geometry not checked';
}
export function areaMetrics(metrics, validation, placements = []) {
  const perSite = metrics.perSite || [];
  const sum = (key) => perSite.length && perSite.every((s) => number(s[key]) != null) ? perSite.reduce((a, s) => a + Number(s[key]), 0) : null;
  const audited = Object.values(validation?.perFloor || {});
  const auditedFill = audited.length && audited.every((s) => number(s.filledArea) != null) ? audited.reduce((a,s) => a + Number(s.filledArea),0) : null;
  const rooms = placements.filter((p) => ['room','special'].includes(p.category));
  const residential = placements.length && rooms.every((p) => number(p.area) != null) ? rooms.reduce((a,p) => a + Number(p.area),0) : null;
  return { filled: number(metrics.filledArea) ?? sum('filledArea') ?? auditedFill, residential: number(metrics.rentableArea) ?? sum('rentableArea') ?? residential, circulation: number(metrics.circulationArea) ?? sum('circulationArea') };
}
// Native graph occurrences carry a local origin/pose; legacy display records
// already contain world-space polygons. Keep the exact geometry, only translate.
export function displayPolygon(placement, boundaries = []) {
  const poly = placement.poly || placement.polygon || [];
  if (placement.position == null || placement.floor == null) return poly;
  const offset = boundaries[placement.floor]?.offset || {};
  return poly.map((p) => ({ x: Number(p.x ?? p[0]) + Number(offset.x || 0), y: Number(p.y ?? p[1]) + Number(offset.y || 0) }));
}
