# FreePencil2 - Changelog

## [Unreleased]
### Changed
- **Generated node trees are now laid out automatically.** Coordinates came
  straight from the exported .blend, where nothing had been arranged: the
  PRO group had 97 overlapping node pairs out of 80 nodes, and 47 of its 97
  links ran right-to-left. STEP3 now runs a layered pass (longest-path
  layering + iterated barycentre ordering) over every tree it builds.

  | tree | overlaps | backward links |
  |---|---|---|
  | scene root | 1 -> 0 | 3 -> 1 |
  | AOV group | 11 -> 0 | 0 -> 0 |
  | PRO group | 97 -> 0 | 47 -> 0 |

  Positions only; links, socket values and render output are untouched
  (mecha still renders ink 0.03765 / silhouette 0.32275 / 1487 components).

### Performance
- **STEP1 is much faster on multi-part models.** Profiling a 138-part /
  889k-face asset showed 93% of the time inside `bpy.ops` calls, almost
  all of it `object.mode_set`: the per-object loop entered and left Edit
  mode for every object, and each switch re-evaluates the whole scene
  depsgraph, so the cost grew with part count.

  The bmesh was only ever read (islands are derived from faces/edges; the
  colours are written afterwards through the data API), so Edit mode was
  never needed. It now uses `bmesh.new()` + `from_mesh()`. Edit mode is
  only entered when "This to Quads" is on, which genuinely rewrites the
  mesh.

  `ensure_vertex_color` likewise stopped using
  `geometry.color_attribute_add` — the data API takes the object directly,
  where the operator worked on whatever was active and forced a mode
  switch per attribute (four per object).

  | model | parts / faces | before | after |
  |---|---|---|---|
  | mecha | 155 / 50k | 8.7 s | **1.32 s** |
  | tank | 43 / 421k | 19.4 s | **7.84 s** |
  | carriage | 138 / 889k | 191 s | **~15 s** |
  | C62 | 1 / 1279k | 28 s | 27.1 s |

  Output is bit-identical on the mecha (ink 0.03765, silhouette 0.32275,
  1487 components — same as the shipped v2.5.0).

### Added
- Blender 4.2 LTS and 4.3 are now covered by the test matrix. The full
  smoke suite (33 tests) runs on 4.2 / 4.3 / 4.5 / 5.2, and rendered line
  output stays within 1.1% ink across all four.
- `compat.HAS_AOV_IN_VIEWPORT_COMPOSITOR` marks whether the viewport
  compositor evaluates AOV outputs (4.3+).
- Support tier table in README and the manual.

### Fixed
- **Blank white viewport on Blender 4.2.** STEP2 and STEP3 both switched
  the viewport to Rendered mode unconditionally. Blender 4.2's viewport
  compositor does not evaluate AOV outputs, so the preview showed nothing
  but white. Measured by isolating the graph: a plain `Invert` and a node
  group both render fine in 4.2, only the AOV input comes through empty —
  so there is no way around it from the add-on side. On 4.2 the viewport
  is now left alone, the preview toggle is disabled with an explanation,
  and the panel says to render with F12.
- Minimum Blender version disagreed between `bl_info` (4.3.0) and
  `blender_manifest.toml` (4.2.0). Both are 4.2.0 now, and a test pins
  version and minimum-version agreement between the two files.

## [2.5.0] - 2026-07-26
### Added
- Blender 5.2 support. The same package now works on both 4.5 and 5.2.
  Version differences are absorbed in `compat.py`, and a 5.x-native
  compositor node script is shipped alongside the 4.x one.
- Progress bar for STEP1 / STEP0. Long vertex color passes no longer
  freeze Blender; the operator runs modally and can be cancelled with ESC.
- STEP0 now turns on the white material preview, so line art is visible
  right after the one-button setup.

### Changed
- Island boundaries are driven by sharp edges instead of Freestyle marks.
  The previous approach temporarily overwrote the user's sharp edges with
  the Freestyle marks and restored them afterwards, which was destructive
  and prone to leaving the mesh in a modified state. STEP1 no longer
  modifies the mesh at all.
  Note: Blender 5.0 removed the `use_freestyle_mark` Python property on
  mesh elements in favour of the attribute API; Freestyle itself and its
  edge marks are still available.
- STEP3 no longer opens a separate compositor window.
- The sidebar starts with only STEP0 expanded.

### Fixed
- Node groups are now regenerated when the shipped graph changes. Files
  containing an older group were previously stuck with it forever.
- Vertex color export honours `render_color_index`, so glTF exports carry
  the painted colors.
- Node export (`node_io`) produced scripts that failed to run when the
  tree contained an Anti-Aliasing node.
- Distribution zip no longer bundles development files.

## [2.4.0] - 2026-07-23
### Added
- Per-channel line strength sliders (STEP3): depth / mecha / bone /
  material / generate, live-updating the generated node group from the
  sidebar. 0 fully disables a channel (ramp colors whitened, restorable).
- White material preview toggle (STEP3): a compositor Mix switches the
  PRO group's Image input between the beauty pass and white, giving an
  instant pure-line-art preview without touching any material.
- 2x supersampling option (STEP3, and STEP0 default ON): render at 200%
  and scale the Composite / File Output results back to 50% for crisp
  1px lines.
- STEP0 per-item toggles, including automatic AOV configuration from the
  scene (painted-channel detection by value, material-ID linkage).
### Changed
- Depth channel reworked to a relative depth gradient
  (Sobel(Z) / (Z + 0.5)) instead of frame min-max normalization, which
  the far clip dominated; interior depth steps now produce lines and the
  depth slider is effective. Regenerate STEP3 nodes in existing files.
### Fixed
- Channel strength 0 previously still drew strong edges (gradients
  exceed the ramp's 1.0 position cap).

## [2.3.0] - 2026-07-18
### Added
- STEP0 "Full Auto": one button that analyzes the scene (rig detection,
  material blend modes), applies recommended settings and runs STEP1-3.
- Part tint (mecha color): touching objects get different brightness bands
  so part boundaries (hairline, collar, assembly seams) become lines.
- Hard boundary bones (`fp_bone_hard_names`): comma-separated bone names
  whose weight region is painted with the dominant color only, producing a
  line at the boundary (e.g. "head,neck" for a jaw line).
- Auto edge angle (STEP1): per-object sharp-edge threshold from the
  dihedral-angle distribution, with guards for rigged/multi-part models.
- Seam/material boundaries and minimum island area merge options for STEP1.
- Line sensitivity (STEP3): scales the node group's line-detection ramps.
- File Output in STEP3: optional node writing line / color / Shadow passes
  as PNGs (default `//render/`).
- STEP5 "Camera Batch Render": per-camera checkboxes and one button that
  renders every checked camera into `//camera_renders/NN_<camera>/`.
### Changed
- Sidebar UI reorganized into collapsible sub-panels (STEP0-STEP5) with
  fixed ordering; full Japanese/English translations for all new strings.
- Depth channel defaults strengthened (threshold 0.22 -> 0.15, darker line
  color) for clearer silhouette and step lines.
- STEP2/STEP3 core logic extracted to `fp_core.py`; operators are
  headless-safe (no UI popups in background mode).
### Fixed
- Crash when running STEP1 headless (popup menu in background mode).
- STEP1 failure on selected meshes with zero faces.

## [2.2.0] - 2026-07-10
### Added
- Reproducible color seed for Auto Vertex Color (STEP1): a "Random seed each run"
  toggle, a Seed field, and a randomize button. Turning the toggle off reproduces
  exactly the same island colors for a given seed and mesh.
### Changed
- Island color generation now uses a process-independent hash of the object name,
  so colors are reproducible across Blender sessions (previously the built-in
  `hash()` was salted per process).

## [2.1.2] - 2025-08-15
### Fixed
- Automatically enable Z-depth pass for compositing when generating Pro node

## [2.1.1] - 2025-08-01
### Changed
- Translation dictionary moved to `locale/*.po` files and loaded at runtime

## [2.1.0] - 2025-06-27
### Added
- Color-noise scale, min neighbor color distance, max color retries の 3 プロパティを追加
- メインパネルに UI スライダーを配置

## [2.0.0] - 2025-04-04

### Added
- Dynamic translation support for EnumProperty items using `items=callback() + pgettext()`
- Full Japanese translation coverage for Blender 4.3.2+
- `description()` method for operator tooltips

### Changed
- Panel structure restored to match main branch (UI clarity improved)
- Translation registration moved to be first in register() function
- Debug translation utilities removed to prevent interference

### Fixed
- Enum dropdown labels not being translated
- Tooltips and buttons displaying incorrect language under Japanese UI
