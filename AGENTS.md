# AGENTS.md — Firefly Wrap Designer

Single-file browser-based 3D decal placement tool for car wrap/livery design. Load a GLB model, import PNG/SVG decals, place them on the 3D car surface with real-time preview. Export orthographic view PNGs.

## Architecture

```
index.html (single file, ~1200 lines)
├── CSS        — dark theme UI, grid layout (viewport + sidebar)
├── HTML       — toolbar, 3D viewport, decal library, layer list, controls, export modal
└── JS (ES module via importmap)
    ├── Three.js 0.160 (CDN: unpkg)
    ├── OrbitControls, GLTFLoader, DRACOLoader, DecalGeometry
    ├── State object — all mutable app state in one place
    ├── Decal placement — DecalGeometry on mesh surface via raycaster
    ├── Layer system — renderOrder-based z-ordering
    ├── View/Edit mode — toggle between orbit-only and decal manipulation
    └── Export — orthographic camera → canvas → PNG download
```

## File Structure

```
firefly-wrap-tool/
├── index.html              # The entire application
├── firefly.glb             # Car 3D model (user provides, ~6MB)
├── export_from_blender.py  # Blender script to export GLB from .blend
├── AGENTS.md               # This file
└── README.md
```

## State Object

All mutable state lives in `const state = { ... }` at the top of the JS module. Key fields:

| Field | Type | Purpose |
|---|---|---|
| `model` | THREE.Group | Loaded GLB scene |
| `carMeshes` | THREE.Mesh[] | All meshes from GLB (raycast targets) |
| `decalLibrary` | {id, name, texture, element}[] | Imported decal PNGs/SVGs |
| `decalObjects` | {id, libId, mesh, scale, aspect, rotation, extraMeshes}[] | Placed decals on car |
| `selectedDecal` | string\|null | Currently selected decal ID |
| `activeLibId` | string\|null | Library decal selected for placement |
| `carBounds` | {center, size} | Bounding box after auto-lift |
| `viewMode` | 'view' \| 'edit' | Orbit-only vs decal manipulation |
| `isDragging` | boolean | Mid-drag flag |

## Key Technologies

- **DecalGeometry** (`three/addons/geometries/DecalGeometry.js`) — Projects a planar texture onto a mesh surface, conforming to geometry. Constructor: `new DecalGeometry(mesh, position, orientation, size)`.
- **Raycaster** — Two separate raycaster instances: `carRaycaster` for surface placement, `decalRaycaster` for selecting placed decals.
- **Import maps** — Three.js loaded via `<script type="importmap">` pointing to unpkg CDN. No build step, no node_modules.

## Lighting Architecture

6 directional lights (front/back/left/right/top/bottom) + 1 ambient. All intensities are moderate (1.5 directionals, 0.6 ambient). No shadows. Car materials are modified on load: `roughness=0.95, metalness=0` to minimize shading gradients while preserving geometric detail and textures.

**Critical gotcha**: `scene.add(new THREE.DirectionalLight(...).position.set(...))` does NOT add the light — `.position.set()` returns a Vector3, not the light. Always create the light separately: `const l = new THREE.DirectionalLight(...); l.position.set(...); scene.add(l);`

## Decal Lifecycle

1. **Import** — User loads PNG/SVG via file input. SVG is rasterized to canvas → CanvasTexture. PNG loaded as Texture. Both stored in `decalLibrary`.
2. **Activate** — Click library thumbnail → `activeLibId` set. Cursor changes to crosshair.
3. **Place** — Click car surface → raycaster finds intersection → `addDecalToScene()` creates DecalGeometry on hit mesh + all nearby meshes (for panel gap spanning).
4. **Manipulate** — Selected decal can be dragged (raycast to surface), scaled (uniform %), rotated. All changes rebuild the DecalGeometry.
5. **Delete** — Removes main mesh + all extra meshes on nearby panels.

## Panel Gap Handling

When a decal spans across a panel gap (separate mesh pieces like doors vs body), DecalGeometry only renders on the hit mesh. To fix this, `addDecalToScene` and `rebuildDecalGeometry` iterate ALL `carMeshes`, check bounding box overlap with the decal footprint, and create additional decal meshes on overlapping meshes. These "extra meshes" are stored in `decal.extraMeshes` and cleaned up on delete/rebuild.

## View/Edit Mode

- **View mode** (default): All mouse events pass through to OrbitControls. Decals are visible but not interactive.
- **Edit mode**: Click decal → select. Click car → place new decal. Drag decal → move.
- Toggle via sidebar buttons. Auto-switches to edit when clicking a layer list item.

## Common Changes

### Adding a new decal property
1. Add to the state type comment
2. Set in `addDecalToScene()`
3. Sync in `selectDecal()`
4. Handle in `rebuildDecalGeometry()`
5. Add UI control in sidebar HTML + event listener

### Changing lighting
Modify the `addLight()` calls at the top of the JS. Keep intensities balanced (all directionals same value). Don't chain `.position.set()` on the constructor.

### Adding a new view preset
Add entry to the `views` object in the view preset handler. Format: `{ pos: [x,y,z], target: [x,y,z], up: [ux,uy,uz] }`. Add a matching button with `data-ortho="name"`.

### Modifying the car appearance
The material tweak is in `loadModel()` inside the `traverse` callback. Currently sets `roughness=0.95, metalness=0`. Do NOT convert to MeshBasicMaterial — it loses textures and normal maps, making surface detail (door lines, panel gaps) invisible.

## Export Script (export_from_blender.py)

Run in Blender GUI (Scripting workspace). Headless Blender crashes on macOS ARM. Exports:
- `firefly.glb` — All visible mesh objects, no filtering
- `templates/*.png` — Orthographic view renders (optional, tool generates its own)

## Dependencies

All loaded from CDN at runtime:
- three.js 0.160 (unpkg)
- OrbitControls, GLTFLoader, DRACOLoader, DecalGeometry
- Draco decoder (gstatic.com)

No npm, no build, no server required. Open index.html directly or serve via GitHub Pages.
