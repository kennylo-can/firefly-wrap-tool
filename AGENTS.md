# AGENTS.md — Firefly Wrap Designer

> **To all agents working on this project**: Please append your changes to the Changelog section at the bottom of this file. Keep existing documentation intact. Write in the same conversational style — note what you added, why, and any gotchas for the next agent.

Single-file browser-based 3D wrap/livery design tool for car models. Load a GLB model, import or generate decals, paint panels, and export high-resolution orthographic or perspective PNGs.

## Architecture

```
index.html (single file, ~2000 lines)
├── CSS        — dark theme UI, 3-tab sidebar layout (贴花 / 涂装 / 视图)
├── HTML       — toolbar, 3D viewport, tab panels, 5 modal dialogs
└── JS (ES module via importmap)
    ├── Three.js 0.160 (CDN: unpkg)
    ├── OrbitControls, GLTFLoader, DRACOLoader, DecalGeometry
    ├── State object — all mutable app state in one place
    ├── Decal placement — positionLocal/normalLocal in mesh object space
    ├── Paint system — per-group color + material presets
    ├── Explode view — mesh offset along centroid direction
    ├── History — linear undo/redo stack (max 40 entries)
    ├── URL share — base64-encoded scene state in location.hash
    └── Export — offscreen WebGLRenderTarget → pixel readback → PNG
```

## File Structure

```
firefly-wrap-tool/
├── index.html              # The entire application (~2000 lines)
├── firefly.glb             # Car 3D model (auto-loaded if present, ~6MB)
├── export_from_blender.py  # Blender script to export GLB from .blend
├── AGENTS.md               # This file
└── README.md
```

## State Object

All mutable state lives in `const state = { ... }` at the top of the JS module.

| Field | Type | Purpose |
|---|---|---|
| `model` | THREE.Group | Loaded GLB scene |
| `carMeshes` | THREE.Mesh[] | All meshes from GLB (raycast targets) |
| `meshInfo` | Map<Mesh, MeshInfo> | Per-mesh metadata (see below) |
| `decalLibrary` | LibDecal[] | Imported/generated decals |
| `decalObjects` | DecalObj[] | Placed decals on car |
| `selectedDecal` | string\|null | ID of selected placed decal |
| `activeLibId` | string\|null | Library decal queued for placement |
| `carBounds` | {center, size} | Bounding box after auto-lift |
| `viewMode` | 'view'\|'edit' | Orbit-only vs decal manipulation |
| `paintMode` | boolean | True when Paint tab is active |
| `paintGroup` | string | 'body'\|'wheels'\|'glass'\|'calipers'\|'trim'\|'interior'\|'picker' |
| `paintColor` | string | Hex color for next paint operation |
| `pickedMeshes` | Set<Mesh> | Meshes selected via picker mode |
| `explodeAmount` | number | Current explode offset in world units |
| `lockRatio` | boolean | Whether X/Y decal scale are locked together |
| `currentMaterialPreset` | string\|null | Active material preset key |
| `history` | HistoryEntry[] | Undo/redo stack |
| `historyIndex` | number | Current position in history stack |

### MeshInfo (per mesh, stored in `state.meshInfo`)

| Field | Purpose |
|---|---|
| `originalPos` | THREE.Vector3 — mesh position before any explode |
| `explodeDir` | THREE.Vector3 (normalized) — direction to push mesh when exploding |
| `group` | 'body'\|'wheels'\|'glass'\|'calipers'\|'trim'\|'interior' — heuristic from mesh name |
| `originalColors` | string[] — hex color per material slot at load time |
| `originalProps` | object[] — roughness/metalness/clearcoat per material at load time |

### DecalObj (per placed decal)

| Field | Purpose |
|---|---|
| `id` | Unique string ID |
| `libId` | ID of the source LibDecal |
| `mesh` | THREE.Mesh — main decal mesh (geometry in world space, position = 0,0,0) |
| `extraMeshes` | THREE.Mesh[] — decal copies on adjacent meshes (panel gap spanning) |
| `targetMesh` | THREE.Mesh — the car mesh this decal is anchored to |
| `positionLocal` | THREE.Vector3 — hit point in targetMesh's LOCAL space (key for explode correctness) |
| `normalLocal` | THREE.Vector3 — face normal in targetMesh's object space |
| `position` | THREE.Vector3 — world-space position (derived, updated by rebuildDecalGeometry) |
| `normal` | THREE.Vector3 — world-space normal (derived, updated by rebuildDecalGeometry) |
| `scaleX`, `scaleY` | number — independent width/height multipliers |
| `aspect` | number — texture native aspect ratio (w/h) |
| `rotation` | number — degrees rotation around surface normal |
| `opacity` | number — 0..1 |

## Key Technologies

- **DecalGeometry** (`three/addons/geometries/DecalGeometry.js`) — Projects a planar texture onto a mesh surface. Constructor: `new DecalGeometry(mesh, worldPosition, orientation, size)`. Output vertices are in **world space**. The decal THREE.Mesh must therefore stay at `position = (0,0,0)` in the scene — do NOT offset it.
- **positionLocal / normalLocal** — Decal anchor stored in mesh-LOCAL space. `rebuildDecalGeometry` calls `mesh.localToWorld(positionLocal)` to get the correct world position at any explode state. This is the key design decision that makes explode + decals work correctly.
- **Raycaster** — `carRaycaster` for car surface, `decalRaycaster` for selecting placed decals.
- **Import maps** — Three.js 0.160 loaded from unpkg CDN. No build step, no node_modules.

## Lighting Architecture

6 directional lights (front/back/left/right/top/bottom) + 1 ambient. Intensities: 1.5 directionals, 0.6 ambient. No shadows. Car materials on load: `roughness=0.85, metalness=0.05`.

**Critical gotcha**: `scene.add(new THREE.DirectionalLight(...).position.set(...))` does NOT add the light — `.position.set()` returns a Vector3. Always: `const l = new THREE.DirectionalLight(...); l.position.set(...); scene.add(l);`

## Decal Lifecycle

1. **Import / Generate** — User loads PNG/SVG/JPG, or creates via text/solid/gradient generators. SVG is rasterized to canvas → CanvasTexture. Thumbnail cached to `lib.thumbDataUrl` once at import time (not on every render).
2. **Activate** — Click library thumbnail → `activeLibId` set, auto-switches to Edit mode. Cursor → crosshair.
3. **Place** — Click car surface → raycaster hit → `addDecalToScene()`. Stores `positionLocal = mesh.worldToLocal(hitPoint)` and `normalLocal = face.normal` (object space). Creates DecalGeometry + spans panel gaps.
4. **Manipulate** — Drag: `moveDecal()` stores new `positionLocal`. Scale/rotate/opacity: `rebuildDecalGeometry()`. All rebuilds use `localToWorld(positionLocal)` so they remain correct after explode.
5. **Delete** — Disposes main mesh + all extraMeshes, removes from scene and state.

## Panel Gap Handling

`rebuildDecalGeometry` iterates all `carMeshes`, checks bounding box overlap with a footprint sphere around the world-space hit point, and creates additional DecalGeometry meshes on overlapping panels. These "extraMeshes" are disposed and rebuilt every time the decal changes.

Extra mesh material is the **same object** as the primary decal's material (`mat` reference, not `mat.clone()`). This avoids per-panel material allocation.

## Explode View

`updateExplode(amount)`:
1. Each mesh is moved: `mesh.position = originalPos + explodeDir * amount`
2. `explodeDir` is computed at load time as `normalize(meshCenter - carCenter)`, with Y component damped by 0.4 to avoid flying off vertically.
3. After moving meshes, **all decal geometries are rebuilt** via `rebuildDecalGeometry`. Because positions are stored in local space, `localToWorld` now returns the exploded world position automatically.
4. Highlight overlays (panel picker) are also repositioned to follow their mesh.

Do NOT move `decal.mesh.position` — the geometry is in world space and the mesh must stay at origin.

## Paint System

`applyPaint(what)` operates on `targetMeshesForPaint()`:
- Group modes (`body`, `wheels`, etc.) filter `carMeshes` by `meshInfo.group`
- Picker mode (`paintGroup === 'picker'`) uses `state.pickedMeshes` (built by clicking in viewport)

`applyMaterialPreset(key)` sets `state.currentMaterialPreset` then calls `applyPaint('material')`.

All paint operations push a history entry with before/after material snapshots.

Mesh group is assigned heuristically in `classifyMesh()` from mesh name and material name. Patterns: `wheel|rim|tire` → wheels; `glass|window` → glass; `caliper|brake` → calipers; `trim|chrome|grill|light` → trim; else → body.

## History (Undo/Redo)

`pushHistory(entry)` — appends to stack, truncates future on new action. Max 40 entries.

Entry types:
- `add-decal` — stores `positionLocal`, `normalLocal`, scaleX/Y, rotation, opacity, libId, targetMeshUuid
- `delete-decal` — same fields
- `paint` — stores `meshUuids[]`, `before[]` (material snapshots), `after[]`
- `move-decal` — records position after drag (undo of move is currently a no-op; extend if needed)

Keyboard: `Ctrl+Z` undo, `Ctrl+Shift+Z` / `Ctrl+Y` redo.

## URL Share

`serializeState()` builds a JSON object with: background color, exposure, ground/grid visibility, explode amount, and per-mesh material snapshots (color + roughness/metalness/clearcoat). Encodes to base64 and writes to `location.hash` as `#s=<encoded>`.

`tryApplyStateFromUrl()` is called after each model load. It decodes and applies the hash state. Mesh matching is by `mesh.name` first, then fallback to index.

Note: decal images are NOT included in the share URL (too large). Recipients need to re-import their decal assets.

## Export

Uses an offscreen `THREE.WebGLRenderTarget` (not renderer resize) to avoid viewport flash.

`exportView(viewName)`:
- For named views (front/rear/left/right/top): uses `THREE.OrthographicCamera`
- For `'current'`: clones the main `PerspectiveCamera` with aspect forced to 1:1
- Background options: scene color, transparent (`scene.background = null`), or white
- Reads pixels via `renderer.readRenderTargetPixels`, flips Y, writes to a canvas, downloads as PNG

`exportAll()` — async sequential export of 5 orthographic views with 100ms gap.

Resolution options: 1024, 2048 (default), 4096.

## View/Edit Mode

- **View mode** (default): OrbitControls active, decals not interactive.
- **Edit mode**: click car → place decal from active library item; click/drag decal mesh → select/move.
- **Paint mode**: activates when Paint tab is selected. If `paintGroup === 'picker'`, clicks on car surface toggle mesh highlight (purple overlay) instead of placing decals. Highlighted meshes become the target for color/material operations.

Selecting a library item auto-switches to Edit mode.

## Common Changes

### Adding a new decal property
1. Add field to `decalObj` in `addDecalToScene()`
2. Sync in `selectDecal()` (populate UI controls)
3. Read in `updateSelectedDecalSize()` or a new event handler
4. Persist in `pushHistory()` and restore in `recreateDecalFromEntry()`
5. Use in `rebuildDecalGeometry()` if it affects geometry/material

### Adding a new material preset
Add an entry to `MATERIAL_PRESETS` object. Fields: `name` (display), `roughness`, `metalness`, `clearcoat`, `clearcoatRoughness`. Optionally update `previewSwatchFor()` for a matching visual.

### Adding a new paint group
1. Add a button in `#paint-groups` HTML with `data-group="newgroup"`
2. Add the group name to `classifyMesh()` pattern matching
3. No other changes needed — `targetMeshesForPaint()` reads `meshInfo.group` automatically

### Adding a new view preset
Add entry to the `views` object in the ortho button handler. Format: `{ pos: [x,y,z], target: [x,y,z], up: [ux,uy,uz] }`. Add a matching button with `data-ortho="name"`.

### Changing lighting
Modify `addLight(intensity, x, y, z)` calls. Keep directional intensities balanced. Never chain `.position.set()` on the DirectionalLight constructor (see gotcha above).

### Modifying default car appearance
In `loadModel()` → `traverse` callback. Currently sets `roughness=0.85, metalness=0.05`. Do NOT use MeshBasicMaterial — it loses textures and normal maps.

## Critical Bugs Fixed (v2 rewrite)

### DecalGeometry position coordinate system
**Problem**: `DecalGeometry` outputs vertices in world space. The original code called `decal.mesh.position.copy(targetMesh.position)` which offset already-world-space vertices by the mesh's local position, causing decals to appear displaced or "bunched up".

**Fix**: `decal.mesh.position` stays at `(0,0,0)` always. Decal anchor is stored as `positionLocal = mesh.worldToLocal(hitPoint)` and `normalLocal = face.normal` (object space). `rebuildDecalGeometry` converts back with `mesh.localToWorld(positionLocal)` and `normalLocal.transformDirection(mesh.matrixWorld)`.

### Explode + DecalGeometry interaction
**Problem**: When meshes move (explode), the old code tried to move `decal.mesh.position` by the mesh's new absolute position — double-offsetting world-space geometry.

**Fix**: Store positions in local space. `updateExplode()` moves car meshes, then calls `rebuildDecalGeometry` on all decals. Because `positionLocal` is in mesh-local space, `localToWorld` automatically returns the correct exploded world position. No separate sync needed.

### `moveDecal` incorrect offset subtraction
**Problem**: `moveDecal` subtracted `hitMesh.position` from the world-space hit point before storing it — wrong when mesh has non-zero local position.

**Fix**: `moveDecal` now does `positionLocal = hitMesh.worldToLocal(newIntersect.point)` and `normalLocal = newIntersect.face.normal` directly.

### Material clone per extra panel
**Problem**: `rebuildDecalGeometry` called `mat.clone()` for every extra panel mesh, allocating N materials per decal.

**Fix**: All extra panel meshes share the same material object reference as the primary decal mesh.

### Thumbnail recompute on every render
**Problem**: `renderLayerList()` called `toDataURL()` on every repaint, re-drawing every decal thumbnail each time.

**Fix**: `addToLibrary()` computes `lib.thumbDataUrl` once at import time (capped at 128px). Layer list reads the cached value.

### Model dispose on reload
**Problem**: Loading a second model did not clean up the first model's geometry, materials, or decals — leading to memory leaks and visual overlap.

**Fix**: `disposeCurrentModel()` traverses and disposes all meshes, materials, and geometries before loading a new GLB.

### Rotation around surface normal
**Problem**: Original code used `euler.z += rotationDeg` after a quaternion decomposition, causing rotation axis to drift on curved surfaces.

**Fix**: Rotation is applied as `Quaternion.setFromAxisAngle(normal, deg)` multiplied onto the alignment quaternion: `spin.multiply(align)`.

## Dependencies

All loaded from CDN at runtime:
- three.js 0.160 (unpkg)
- OrbitControls, GLTFLoader, DRACOLoader, DecalGeometry
- Draco decoder (gstatic.com)

No npm, no build, no server required. Open `index.html` directly or serve via any static server / GitHub Pages.

If `firefly.glb` exists in the same directory as `index.html`, it is loaded automatically on startup via `fetch('firefly.glb')`.

---

## Changelog

### 2026-05-21 — Hanako: Body-Only Decompose View

Added a "仅车身分解" (body-only decompose) mode inspired by teslawrap.art's panel-separated wrap templates.

**What it does**:
- Toggle button in View tab: `btn-decompose` + `btn-reset-explode`
- When active: hides non-body meshes (wheels, glass, calipers, trim), pushes body panels to 70% explode for clear panel separation
- When deactivated: restores all mesh visibility, resets explode to 0
- State tracked in `state.decomposeMode` (boolean)
- Visibility saved in `savedVisibility` Map for restore
- Included in URL share via `data.decompose`

**New functions**:
- `toggleDecomposeMode()` — toggle on/off, manage visibility + explode
- `resetExplode()` — reset both decompose and explode to defaults

**CSS added**: `.btn.active` style for toggle button highlight

**Future agents**: The decompose mode only affects mesh visibility and explode level. It does NOT alter mesh geometry or decal placement. The explode slider still works independently in decompose mode. When adding new mesh groups to `classifyMesh()`, body decompose will automatically hide them (only 'body' group stays visible).

### 2026-05-21 — Hanako: Interior mesh classification

Added 'interior' group to `classifyMesh()`. Patterns: `interior|seat|steering|dashboard|carpet|headliner|doorpanel|console|内饰|座|方向盘|仪表|地毯|顶棚|门板`. Interior meshes are now automatically hidden in body decompose mode (since the filter is `group !== 'body'`). Added paint group button for interior.

### 2026-05-21 — Hanako: Paint material filter

**Problem**: `applyPaint('color')` was tinting ALL material slots on target meshes, including non-paint materials like plastic trim, chrome, glass, etc. The GLB has 7 materials: `mat_1`-`mat_3` (generic white, probably body), `AMH7852-CARPAINT` (explicit paint), `mat_5.001` (generic), `plastic01_object` (black plastic), `mat_15` (generic).

**Fix**: Added `isPaintMaterial(mat)` function that checks material name for keywords (`paint`, `carpaint`) or generic mat_ names (which are heuristically treated as paint unless they contain `plastic|glass|chrome|trim|rubber|leather`). `applyPaint('color')` now calls `isPaintMaterial()` and only tints qualifying materials. Material presets (`applyPaint('material')`) still apply to all materials on the target mesh (roughness/metalness can be safely set on any PBR material).
