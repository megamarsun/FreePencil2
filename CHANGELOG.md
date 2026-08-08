# FreePencil2 - Changelog

## [2.6.1] - 2026-08-08
### Removed
- **"This to Quads" is gone.** It rewrote the mesh permanently and paid the
  cost of an Edit-mode round trip for it, but barely touched the drawing.
  Measured over 8 models: **6 of them came out with the ink ratio unchanged
  to the last digit**, while the time went up anyway — 0.6s to 7.1s on an
  A320, 6.5s to 22.9s on an Audi. Face count only moves when the mesh
  happens to have triangles to merge; the Edit-mode entry is paid either
  way. On a 10.6M-face production set it cost 31 seconds and 13.8 GB, and
  quietly cut the mesh from 10,594,485 to 9,040,042 faces — every time
  STEP1 was pressed. (`dev/batch/HANDOFF.md` had already recorded the same
  finding on 5 models in an earlier round.)

  Old files that still have the setting saved are unaffected: the property
  no longer exists, so the value is simply never read. Default output is
  unchanged — 360/360 colour attributes identical before and after removal.

### Added
- **STEP0 / STEP2 / STEP3 now say what they did.** They only ever popped up
  on failure, so a successful run looked like nothing had happened. Each
  now reports whether the node group was created, updated, or already up to
  date, along with its name and node count, the AOVs that were enabled, and
  the file-output passes and destination.

### Fixed
- `dev/batch/hash_paint.py` unpacked `append_objects()` backwards —
  it returns `(meshes, others)` — and normalised the scene against the
  armatures instead of the meshes. The 348/348 comparison it produced is
  still valid (both sides ran through the identical harness), but the tool
  was wrong and is fixed.
- `mesh_islands.py` built `loop_poly` assuming loops are packed in face
  order while the face-centre code explicitly honoured `loop_start`. Only
  one of the two would have been right on a mesh that broke the assumption.
  The check now lives in one place and both paths use it.
- `mesh_islands.connected_components` returned a silently wrong labelling
  if it hit its 200-round runaway guard. It raises now.
- `scripts/install_all.py` read the add-on version from a module that was
  still the pre-install one, so a freshly installed 2.6.0 reported 2.5.0.
  It reloads first, cross-checks against `bl_info` in the installed file,
  and fails the run if the two disagree.

## [2.6.0] - 2026-08-08
### Added
- **Far crush relief (STEP3).** In deep sets — a shop floor, a street, a
  classroom — distant props pack so tightly on screen that their lines
  merge into solid black. Measured on a corridor of 26 receding shelf rows
  at 1200px, the share of pixels whose entire 3x3 neighbourhood is ink:

  | distance | off | **amount 0.6** | amount 1.0 |
  |---|---|---|---|
  | near | 0.0001 | 0.0000 | 0.0000 |
  | mid | 0.1178 | **0.0000** | 0.0000 |
  | far | **0.2387** | **0.0000** | 0.0000 |
  | ink left in the far band | 0.4378 | **0.1419** | 0.0033 |

  Fading by distance would erase the far geometry along with the mess, so
  the trigger is **local line density** instead: crushing *is* saturated
  density, and a distant silhouette that is not crowded survives. Five
  nodes are inserted just before the group's `line` output —
  `alpha *= 1 - amount * clamp((blur(mask) - threshold) / (1 - threshold))`.
  Amount defaults to 0, which inserts nothing and leaves existing images
  bit-identical. Moving the slider re-applies in place; back to 0 removes
  the nodes and restores the original wiring.

  Note 1.0 is too strong (0.3% of the far lines survive); start at 0.5-0.7.

  The nodes are located by following the wiring back from the `line`
  output, not by node name — the same exported file yields different
  auto-assigned names on 4.2 and 4.5, which broke a name-based first cut.

### Performance
- **STEP1 no longer redoes the same mesh once per linked duplicate.** A
  production set (a department store) had 1,186 mesh objects sharing only
  159 mesh datablocks: summed over objects that is 711M faces against
  89.2M of actual data — the same mesh was painted up to 14 times, and
  every pass but the last was thrown away. Worse, the colour seed comes
  from the *object* name, so which pass won depended on iteration order.
  STEP1 now paints one representative per mesh datablock, chosen by lowest
  object name so the result no longer depends on selection order.

- **Island detection moved from bmesh to numpy arrays** (new
  `mesh_islands.py`). Everything it needs — loop→edge, loop→face, face
  normals, areas, centres, sharp/seam/material flags — comes out of
  `foreach_get` in one call each, so no BMesh is built at all.

  | mesh | before | after |
  |---|---|---|
  | 3,189,380 faces | 55.8s | **32.1s** |
  | 10,594,485 faces | 201.3s | **112.6s** |

  Connected components use Shiloach-Vishkin. Hooking *roots* rather than
  nodes is what makes it viable: the node-hooking version needed 96 rounds
  and 5.66s where root-hooking with edge contraction converges in 3 rounds
  and 0.24s.

  The paint output is unchanged, verified by sha1 over every colour
  attribute of 8 models: **348/348 identical**. Reaching that required
  reproducing three accidents of the old code, each found by measurement:
  BMesh reports a zero normal for degenerate faces where the mesh API
  returns (0,0,1), and `calc_face_angle` then returns exactly 60° for them;
  triangle centres differ by 1 ULP because the mesh API divides by 3 while
  BMesh multiplies by 1/3, and that coordinate feeds the colour-jitter
  hash; and Blender sums n-gon (n>=5) vertices in reverse order.

- **Cheaper preparation.** `apply_face_colors` writes all corners with one
  numpy `foreach_set` instead of walking `polygon.loop_indices` (8.7s on a
  3.2M-face mesh). The dihedral angle of each edge is computed once and
  shared between the auto-threshold and the boundary test (it used to run
  7.94M times over 4.79M edges). `many_loose_parts` only asks whether the
  selection has 8 or more parts, which is already true when 8 or more
  objects are selected, so nothing is counted at all in a large scene.
  `_channel_painted` reads each mesh datablock once, smallest first.

### Fixed
- `fp_batch.lineart_metrics` loaded the render with a relative path, which
  Blender resolves against something other than the working directory, so
  a batch run with a relative `--out` failed after rendering. Third place
  this same trap has appeared; resolved at the source now.

- **mask_color did nothing useful on Blender 5.x.** Reported by a user: on
  5.2, painting the mask channel only erased lines around brightness 0.2,
  had almost no effect from 0.4 to 0.8, and white did nothing at all. On
  4.2 / 4.3 / 4.5 the same file erased every painted area regardless of
  brightness, which is the intended behaviour for a mask.

  The 5.x compositor node group is a separate exported file. That export
  ran with a `try/except` around each node's property block, and 5.x moved
  `color_hue` / `color_saturation` / `color_value` from node properties to
  input sockets. The exporter hit an `AttributeError`, wrote
  `# skipped node properties (...)`, and dropped the **entire** block —
  name, label, position and socket values — for four nodes:

  | node | lost | consequence |
  |---|---|---|
  | Color Key (mask chain) | key colour black -> white default, tolerances | mask inverted |
  | Color Key.001 (inpaint) | key tolerances | slightly different matte |
  | Inpaint.001 | name / label only | none (default matched) |
  | Dilate/Erode | name / label only | none (defaults matched) |

  The mask chain keys out **black**; leaving it at the white default made
  painted (bright) areas transparent instead of opaque, flipping the
  channel. Restored the 4.x values. All four Blender versions now produce
  identical results, pinned by `t36`.

  Also checked and cleared as false alarms: `Filter` (Sobel),
  `Dilate/Erode` and `Set Alpha` merely moved their settings from node
  properties to input sockets in 5.x, with matching values; and the
  `Normal` -> `Vector Math (dot product)` port is exact — the compositor
  Normal node computes `-dot(in, normalize(dir))`, so direction
  `(-1,-1,-1)` equals a dot with `(0.5774, 0.5774, 0.5774)` (measured).

### Changed
- **STEP4 channel labels now say what the channels do.** `mask_color` was
  labelled "White erases lines" since the 2023 original, which reads as
  white-specific; brightness is in fact irrelevant, so it is now "paint to
  erase lines". `line_color` was labelled just "Line Color" with no hint
  that it sets line *darkness* and never adds lines; it is now
  "Line Color(line darkness)". Manual section 5 rewritten to match.
- **File Output passes are now selectable, and default to line / color /
  light.** The third slot used to be the shadow pass, which on EEVEE rarely
  comes out clean enough to use; diffuse direct light composites far more
  easily. Shadow is still available as an opt-in checkbox.

  | pass | source | default |
  |---|---|---|
  | line | PRO group output | on |
  | color | PRO group output | on |
  | light | Diffuse Direct render pass | on |
  | shadow | Shadow render pass | off |

  The checkbox name is the written filename. Unchecking everything skips
  the File Output node entirely. Only the passes you select get enabled on
  the view layer. The Render Layers socket for diffuse direct is `DiffDir`
  on 4.x and `Diffuse Direct` on 5.x; `compat.render_layer_socket` resolves
  either. Existing files: rerun STEP3 to rewire.
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
