# Assignment 4 — Part B: Multimedia in the prototype

Project: **My AITU / LMS bridge**, the working prototype in `bridge-test/`. The older top-level `index.html` is a separate design and is not used for this inventory. File sizes below are binary KiB (1 KiB = 1024 bytes), measured on 23 October 2026.

## B1. Media asset inventory

The inline SVG symbols share one HTML response: their individual byte counts describe source markup, not separate downloads. All 18 used icons below come from [Flaticon Uicons Regular Rounded](https://www.flaticon.com/uicons/get-started). Their free licence requires visible attribution; the application footer supplies it. The source revision and saved licence are documented in `bridge-test/FLATICON.md` and `bridge-test/FLATICON-LICENSE.txt`. Two additional symbols (`ui-right`, `ui-stats`) are defined in the file but are currently unused.

| # | Asset | Where used | Format | Resolution / duration | File size | Source | Licence |
|---:|---|---|---|---|---:|---|---|
| 1 | Attendance screen preview | Sign-in screen | WebP, quality 80 | 390 × 844 px | 15.75 KiB | Own test-screen capture; includes credited Flaticon icons | Own screenshot + Flaticon free with attribution |
| 2 | LMS wordmark | Sign-in screen | CSS and text | 68 × 68 px display box | Embedded; no separate request | Own work | Own |
| 3 | Book icon (`ui-book`) | Courses and navigation | Inline SVG | Vector, viewBox 300 × 300 | 740 B | Flaticon Uicons | Free with attribution |
| 4 | Calendar icon (`ui-calendar`) | Tasks and attendance | Inline SVG | Vector, viewBox 300 × 300 | 1,162 B | Flaticon Uicons | Free with attribution |
| 5 | Graduation icon (`ui-grad`) | Grades | Inline SVG | Vector, viewBox 300 × 300 | 857 B | Flaticon Uicons | Free with attribution |
| 6 | User icon (`ui-user`) | Account button | Inline SVG | Vector, viewBox 300 × 300 | 869 B | Flaticon Uicons | Free with attribution |
| 7 | Menu icon (`ui-menu`) | Navigation button | Inline SVG | Vector, viewBox 300 × 300 | 561 B | Flaticon Uicons | Free with attribution |
| 8 | Close icon (`ui-close`) | Navigation controls | Inline SVG | Vector, viewBox 300 × 300 | 441 B | Flaticon Uicons | Free with attribution |
| 9 | Down icon (`ui-down`) | Account menu | Inline SVG | Vector, viewBox 300 × 300 | 391 B | Flaticon Uicons | Free with attribution |
| 10 | Sign-out icon (`ui-out`) | Account menu | Inline SVG | Vector, viewBox 300 × 300 | 906 B | Flaticon Uicons | Free with attribution |
| 11 | Refresh icon (`ui-refresh`) | Reload button | Inline SVG | Vector, viewBox 300 × 300 | 945 B | Flaticon Uicons | Free with attribution |
| 12 | Search icon (`ui-search`) | Course search | Inline SVG | Vector, viewBox 300 × 300 | 669 B | Flaticon Uicons | Free with attribution |
| 13 | Eye icon (`ui-eye`) | Password visibility | Inline SVG | Vector, viewBox 300 × 300 | 935 B | Flaticon Uicons | Free with attribution |
| 14 | Check icon (`ui-check`) | Attendance status | Inline SVG | Vector, viewBox 300 × 300 | 366 B | Flaticon Uicons | Free with attribution |
| 15 | Absent icon (`ui-absent`) | Attendance status | Inline SVG | Vector, viewBox 300 × 300 | 442 B | Flaticon Uicons | Free with attribution |
| 16 | Clock icon (`ui-clock`) | Attendance time/status | Inline SVG | Vector, viewBox 300 × 300 | 777 B | Flaticon Uicons | Free with attribution |
| 17 | Minus icon (`ui-minus`) | Unmarked attendance | Inline SVG | Vector, viewBox 300 × 300 | 284 B | Flaticon Uicons | Free with attribution |
| 18 | Left arrow (`ui-left`) | Previous calendar month | Inline SVG | Vector, viewBox 300 × 300 | 416 B | Flaticon Uicons | Free with attribution |
| 19 | Next arrow (`ui-next`) | Next calendar month | Inline SVG | Vector, viewBox 300 × 300 | 404 B | Flaticon Uicons | Free with attribution |
| 20 | List icon (`ui-list`) | Attendance status | Inline SVG | Vector, viewBox 300 × 300 | 1,010 B | Flaticon Uicons | Free with attribution |
| 21 | Login progress pulse | Microsoft login progress | CSS animation | 2 s, looping | Embedded; no separate request | Own work | Own |
| 22 | Content entrance motion | Sign-in/content transition | CSS animation | 0.4 s per element | Embedded; no separate request | Own work | Own |
| 23 | Campus map | Map section, external iframe | Interactive web content | Responsive iframe | Variable, served by third party | [Yuujiso / aitumap](https://github.com/Yuujiso/aitumap) | [MIT](https://github.com/Yuujiso/aitumap/blob/main/LICENSE.md); author credited beside map |
| 24 | Inter font | Interface typography | Web font | Variable font, several weights | Variable, served by Google Fonts | [Inter project](https://github.com/rsms/inter) | [SIL OFL 1.1](https://github.com/rsms/inter/blob/master/LICENSE.txt) |
| 25 | Temporary remote browser view | Optional Microsoft/Moodle support screen | JPEG, quality 70 | 1100 × 800 px | Variable; generated per request | Live screenshot of the user's own browser session | Not a bundled/distributed asset |

The original `attendance-preview.png` (58.39 KiB) and the other `*-preview.png` files are evidence files, not images loaded by the running interface. The remote view can contain private information and must not appear in the submitted video or screenshots. The map is an iframe: its internal assets and transfer size depend on the third-party site and are outside the local inventory.

## B2. Integration and optimisation

The sign-in screen now displays the **390 × 844 px** test attendance preview as a 250 px wide WebP image; its CSS width is bounded by the available viewport. This sizing is designed for a 360 px viewport and still needs a browser screenshot to verify the whole page. The prototype also contains inline SVG icons and the visible CSS login pulse/entrance animation. The existing `prefers-reduced-motion` rule disables the animation when requested by the user.

| Image version | Resolution | File size | Difference |
|---|---:|---:|---:|
| Original PNG | 390 × 844 px | 59,787 B = 58.39 KiB | Baseline |
| WebP, quality 80 | 390 × 844 px | 16,126 B = 15.75 KiB | 43,661 B / 42.64 KiB smaller (73.0%) |

The four local front-end files (`index.html`, `features.css`, `features.js`, `attendance.js`) total **81,815 B** in the WebP version. With the one-byte-shorter PNG URL, their raw file bytes plus the preview would be **141,601 B** with PNG and **97,941 B** with WebP, a **30.8%** reduction for this controlled set. This is a file-payload calculation, **not** a browser Network measurement: HTTP headers, compression, API calls, Google Fonts and the external map can change the actual transferred total. Replacing one image URL does not add or remove a request.

| Required Network measurement (cache disabled, Fast 4G) | Before: PNG | After: WebP | Change |
|---|---|---|---|
| Total transferred size | **Measure in DevTools** | **Measure in DevTools** | — |
| Number of requests | **Measure in DevTools** | **Measure in DevTools** | Expected image-request delta: 0; verify total |
| Finish or Load time | **Measure in DevTools** | **Measure in DevTools** | — |

Run `venv/bin/python assignment4/measure_part_b.py` on a machine that permits Chromium and a local HTTP server. It writes `assignment4/part-b-network.json` and a 360 px screenshot, using the same page and synthetic API responses for both image versions. It reports only local resources. For the required **DevTools screenshots**, run the FastAPI prototype locally, open Chrome DevTools → Network, check **Disable cache**, choose **Fast 4G**, and reload the sign-in screen. Capture the PNG baseline by temporarily changing the image `src` in `bridge-test/index.html` to `/attendance-preview.png`; then restore `/attendance-preview.webp` and capture the second reload. Keep the viewport, server, network profile, cache setting, and login state identical. The PNG and WebP routes are both available. Record the Network footer's transferred size, request count and Finish/Load time in the table above. Do not submit the current table as measured data until both captures exist.

Project Stage 1, Part B specified **under 3 seconds per request for up to 1,000 concurrent users**, including LMS/Learn parsing. A static image reduction cannot prove this server-side requirement. The existing project tests cover a smaller concurrency level; the 1,000-user requirement remains unverified.

## B3. Accessibility evidence

| Check | Evidence in prototype | Result |
|---|---|---|
| Meaningful image alternative | The preview `<img>` in `bridge-test/index.html` has a specific Russian `alt` describing the calendar and attendance counts. The temporary remote browser image also has an `alt`. | Implemented; the remote image's changing contents cannot be fully conveyed by its fixed label. |
| Decorative vectors | The inline sprite has `aria-hidden="true"`; static control SVGs and `uiIcon()` output are hidden from screen readers. Buttons have text or labels such as “Открыть навигацию”. | Implemented. |
| Captions/transcript | The prototype contains no speech audio or video. | Not applicable at present; add captions/transcript if such media is introduced. |
| Sound plus visual equivalent | The prototype contains no sound; authentication progress is presented by visible text and a visual pulse. | No sound-only information. |
| Sound autoplay | There are no `<audio>`/`<video>` elements or audio playback calls in the prototype. | No automatic sound. |
| Text over image contrast | The screenshot has a separate `<figcaption>` below it; no live text is overlaid on a raster image. | The 4.5:1 over-image check is not applicable to the current layout. |
| Reduced motion | `@media(prefers-reduced-motion:reduce)` disables CSS animations and transitions. | Implemented. |

Code excerpts for the report:

```html
<img src="/attendance-preview.webp" width="390" height="844"
     alt="Тестовый экран посещаемости: календарь за октябрь 2026 года и счётчики — 0 присутствий, 1 пропуск, 0 опозданий, 1 запись без отметки.">
```

```css
@media(prefers-reduced-motion:reduce){
  *,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}
}
```

### References

- Flaticon. [Uicons: licence summary and attribution instructions](https://www.flaticon.com/uicons/get-started). Local licence copy: `bridge-test/FLATICON-LICENSE.txt`.
- Yuujiso. [aitumap repository, README and MIT licence](https://github.com/Yuujiso/aitumap).
- The Inter Project. [Inter font and OFL licence](https://github.com/rsms/inter).
