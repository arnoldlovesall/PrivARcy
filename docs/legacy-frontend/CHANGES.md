# PrivARcy Frontend — Changes

## 8. UI/UX requirements pass (Process, Live, Review, Results, Settings)

- **Process.py**: the Blur / Pixelate / Solid Mask radio group now exposes
  `get_redaction_method()` and updates immediately on selection; the active
  processing placeholder reflects whichever method is selected. Added
  `reset()` for session clearing.
- **Live.py**: the monitoring preview panel now uses a true black
  (`#000000`) background instead of the previous dark navy, in both the
  initial layout and `retheme()`, with light-colored status/overlay text
  kept for contrast. No functional changes to the (still backend-free)
  live pipeline.
- **Review.py**: rewritten to add a `DetectionInfoCard` (Class, Confidence,
  Frame, OCR Text, Classification, Confidence Score) that opens when a
  detection is selected from the now-clickable timeline or from a queue
  card. Added Previous / Confirm Redaction / Next controls with icons.
  Replaced the old "remove on decision" behavior with a proper three-state
  model — Pending Review / Confirmed / Rejected — so items stay visible
  with a status pill instead of disappearing, and the selected detection is
  highlighted in both the timeline and the queue.
- **Results.py**: added a "Processing Summary" section with Precision,
  Recall, F1-score, Average FPS, Total Detections, Auto-Redacted, and
  Temporal IoU metric cards; an "🎬 Export MP4" flow (file picker, busy/
  disabled state while "exporting", honest error since no backend is wired
  up yet, and a public `export_video_result()` API for the real backend to
  call); and a prominent "Process Another Video" button that clears the
  Process/Review/Results session state and returns to Home via a new
  `MainWindow.reset_session()` in `main.py`. Also fixed a pre-existing bug
  where `ResultMetricCard.value_lbl` wasn't stored as an instance
  attribute, so `set_results()` could never actually update the Overview
  cards.
- **Settings.py**: already matched the spec (Performance Profile cards,
  Redaction Style previews for Gaussian Blur / Solid Mask) — no changes
  needed here.
- **styles.py / components.py**: added `QRadioButton` styling (previously
  unstyled, so the Process page's redaction-method radios had no visible
  selected state) and new `chevron_left` / `chevron_right` icons for the
  Review page's Previous/Next controls.


## 1. The theme/settings reset bug (root cause + fix)

**Root cause:** `main.py`'s `toggle_theme()` called `create_dashboard()` again
on every Light/Dark switch, which re-instantiated the sidebar *and every
page from scratch* (`HomePage()`, `FaceRegisterPage()`, `SettingsPage()`,
etc). Since each page keeps its own state in memory (uploaded faces,
slider positions, the review queue, the process timer...), recreating the
page objects meant that state was gone — it looked like "everything resets"
because it genuinely did.

**Fix:** the dashboard and every page are now built exactly **once**, in
`MainWindow.__init__`. Switching theme now:
1. Swaps the live palette in `styles.py` and re-applies the app-wide
   stylesheet (`QApplication.setStyleSheet`) — this alone re-colors every
   object-name-styled widget (buttons, cards, inputs, checkboxes...) for
   free, since Qt widgets read `objectName`-scoped QSS live.
2. Walks the existing widget tree (`components.retheme_widget_tree`) and
   re-applies any inline stylesheet that was registered with the new
   `styles.themed(widget, style_fn)` helper — this covers the labels that
   bake a color directly into `setStyleSheet(f"...")` instead of going
   through an object name.
3. Lets the two pages with dynamic list content (Face Register, Review)
   rebuild just their visual cards from their *existing* data list, which
   is the simplest way to recolor nested placeholders/icons in those.

No widget holding user state is ever destroyed by a theme switch anymore.

**Bonus:** the chosen theme is now also saved via `QSettings` and restored
on the next launch (UI/UX suggestion "Theme Persistence").

## 2. Face Register
- Upload dialog now accepts PNG, JPG, JPEG, BMP, WEBP, GIF, TIFF.
- Uploaded photos are stored (`{"name", "path"}`) and actually **rendered**
  as the card thumbnail in the Registered Faces grid (previously always a
  plain colored rectangle).
- Re-uploading a photo for an existing name replaces its picture.
- A notification banner confirms how many faces were added.

## 3. Review
- Each queue card's thumbnail is now clickable and opens a larger preview
  dialog. If a real detection crop isn't available yet (`image_path` is
  `None` in the mock data), it says so honestly instead of pretending —
  the moment the backend supplies real crops, they'll render automatically.

## 4. Export / Save (Results page)
- Buttons are wired up and give clear feedback ("ready — connect the
  backend to enable it") instead of doing nothing silently, so the GUI is
  structurally ready for backend integration as requested.

## 5. Settings — restructured
- **Pipeline Configuration**: dropped the free-text "Detection Confidence
  Threshold" field; "Redaction Behavior" is now a proper dropdown
  describing what happens to a detection, not a raw number.
- **Redaction Style**: separated into its own card with two large,
  clearly-selectable preview cards (Gaussian Blur / Solid Mask) with a
  small visual swatch and description each.
- **Performance Profile**: separated into its own card with three
  selectable cards. Choosing one **automatically re-tunes** the Face
  Detection Interval + JPEG Quality sliders for that profile; the user can
  still fine-tune manually afterward.
- **Detection Classes**: new checkbox group — Faces, ID Cards,
  Credit/Debit Cards, Documents, Screens.
- Saving now shows a proper success banner and assembles a complete
  settings payload (`self._last_saved_settings`) ready to hand to a
  backend call.

## 7. Phase 1 spec audit (backend-simulation & mock-data violations)

An audit against the Phase 1 rules ("no backend/OpenCV/video processing",
"never fake a real processing process") found two real violations and one
minor one. All three are fixed; no other gaps were found — theming, the
status bar, empty/loading/error states, toasts, the Process page's backend
API, and most keyboard shortcuts were already implemented correctly.

- **`Live.py` was doing real backend work.** It imported `cv2`/`numpy`,
  opened an actual webcam via `cv2.VideoCapture`, decoded real frames, and
  ran a `random.randint`-driven timer that fabricated "Bystander face —
  auto-redacted" style audit-log entries and detection counts — i.e. fake
  AI output presented as if real. Rewritten to be strictly frontend-only:
  no camera access, no invented detections. The only timer left is an
  honest wall-clock for session duration. A clean public API
  (`set_preview_pixmap`, `set_live_stats`, `add_audit_entry`,
  `set_stream_active`, `set_source_label`) is now the only way this page's
  data changes, ready for the real backend to drive later.
- **`Process.py` was auto-simulating an entire processing run.** Clicking
  "Start Processing" kicked off a `QTimer` that incremented frame counts,
  FPS, and ETA once a second and auto-completed after ~20 seconds — this is
  exactly the "do not fake a real processing process" case the spec calls
  out twice. Removed the timer entirely. Start now shows one static,
  clearly-labeled placeholder frame (matching the mockup in the spec) with
  no auto-advancing numbers, and tells the user honestly that no backend is
  connected via the existing `NotificationBanner` pattern. The public API
  (`set_progress`, `set_frame_progress`, `set_processing_fps`, `set_eta`,
  `set_processing_state`) is untouched and is now the only path that can
  move the progress bar.
- **`Home.py` hard-coded fake dashboard numbers** ("18 videos processed",
  "92% avg confidence", etc.) with no way for a backend to overwrite them
  cleanly. Changed to start at 0/"—" placeholders and added
  `HomePage.set_overview_stats(...)` plus `StatCard.set_value()` /
  `set_trend()` so a backend can populate real numbers without fighting
  hard-coded ones.
- Also filled in the two keyboard shortcuts from the spec's table that
  mapped onto functionality that already existed but wasn't wired up yet:
  `Ctrl+O` (opens Process's existing file picker) and `Ctrl+S` (triggers
  Results' existing export action). `Space` (Play/Pause) is now registered
  as a shortcut scoped to the Live page itself rather than window-wide, so
  it toggles the stream there without swallowing spacebar keystrokes in
  text fields on other pages. `Esc` now cancels an in-progress action on
  the current page if one exists (e.g. Process), falling back to
  navigating Home otherwise.

## 6. UI/UX polish
- Sidebar: wordmark + tagline next to the logo, a divider, and a
  "MAIN MENU" section label for a more deliberate, branded look.
- Process page: added an overall progress bar alongside the existing
  per-stage pipeline indicators and metric cards.
- New reusable `NotificationBanner` component (success/error/info) used
  across Face Register, Settings, and Results instead of a single
  hidden/shown label.
