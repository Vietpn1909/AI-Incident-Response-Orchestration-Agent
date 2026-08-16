# Prompt: Xây dựng giao diện War Room cho Agent xử lí sự cố

Copy toàn bộ nội dung dưới đây và gửi cho agent (Claude, GPT, Cursor, v0, hoặc bất kỳ code-gen agent nào có khả năng viết HTML/CSS/JS).

---

## 🎯 Bối cảnh & mục tiêu

Xây dựng một giao diện web **War Room** — công cụ giúp on-call engineer (SRE/DevOps) xử lí sự cố khi server hoặc service gặp vấn đề. Đây là nơi engineer làm việc **cùng với một AI Agent** đang tự động phân tích incident và đề xuất hành động.

Deliverable: **một file HTML duy nhất**, tự chứa, không cần build step, không dùng framework (không Tailwind, không React, không Vue). Chỉ vanilla HTML + CSS + JS. Font qua Google Fonts. Ngôn ngữ giao diện: **tiếng Việt**.

Người dùng cuối là engineer đang stress lúc 3h sáng. Giao diện phải giúp họ **bình tĩnh và quyết định nhanh**, chứ không được góp phần vào sự hoảng loạn.

---

## 🎨 Triết lý thiết kế (BẮT BUỘC giữ đúng — không được "tự sáng tạo")

**Ẩn dụ chủ đạo:** phòng điều khiển yên tĩnh (như control room NASA hoặc phòng cấp cứu bệnh viện được vận hành tốt) — KHÔNG PHẢI trung tâm báo động màu đỏ chói.

**5 nguyên tắc:**

1. **Muted severity colors.** P1 không phải đỏ máu `#FF0000` mà là `#E5484D` (dark) / `#C8353B` (light) — vẫn đủ khẩn cấp nhưng không tạo panic. Áp dụng chung cho mọi màu cảnh báo.

2. **Serif editorial cho tiêu đề.** Dùng font **Newsreader** cho tất cả headings và severity numbers. Tạo cảm giác "đang đọc hồ sơ ca bệnh" thay vì "đọc dashboard alert". Font này in italic ở weight 300–400 cho cảm giác biên tập, thoáng.

3. **Amber accent là chữ ký của AI/Agent content.** Màu `#D4A056` (dark) / `#A16A25` (light) CHỈ dùng cho nội dung do Agent tạo ra: reasoning trail, proposal cards, section eyebrows, code function names. Người dùng sẽ học được: *thấy amber = Agent đang nói*.

4. **Sparklines everywhere.** Mọi incident trong sidebar đều có sparkline nhỏ 52×16px hiển thị "hình dạng" của vấn đề. Metric đang tăng vọt trông rất khác metric đã bình ổn.

5. **Human-in-the-loop có chủ ý.** Nút "Duyệt" là nút primary trắng nổi bật, "Từ chối" là ghost button. KHÔNG phải hai nút xanh-đỏ đối trọng ngang nhau — phản ánh thực tế 90% lần Agent đúng.

**KHÔNG làm những thứ sau (đây là tell của AI-generated design generic):**
- ❌ Không dùng nền cream `#F4F1EA` + terracotta `#D97757`
- ❌ Không dùng gradient hero với big number + small label
- ❌ Không dùng numbered markers `01 / 02 / 03` **trừ khi content thực sự là sequence** (trong project này, các section 01-05 CÓ là sequence, nên được dùng)
- ❌ Không dùng emoji trong UI production
- ❌ Không thêm animation ambient (glowing, floating particles)
- ❌ Không dùng shadow to. Border 1px là đủ.

---

## 🛠️ Yêu cầu kỹ thuật

- **1 file HTML** self-contained: `war-room.html`
- `<html lang="vi" data-theme="dark">` — mặc định dark
- Fonts qua Google Fonts CDN: `Newsreader`, `Inter`, `JetBrains Mono`
- Tất cả icons dùng **inline SVG** — không dùng icon library
- Không dùng images/photos, kể cả avatar (dùng initials trong div)
- Không dùng `localStorage` / `sessionStorage` — theme state chỉ giữ trong JS runtime
- Charts vẽ bằng **inline SVG với path element**, không dùng library
- Sparklines cũng vẽ bằng SVG path
- Transitions max 0.25s ease
- Không có external requests ngoài Google Fonts

---

## 🎨 Design Tokens

### Dark theme (default) — dán vào `:root {}`

```css
--bg-0: #0A0D12;         /* page background */
--bg-1: #10151C;         /* card/surface */
--bg-2: #171E27;         /* elevated surface */
--bg-3: #1F2A37;         /* highest surface, hover states */
--bg-hover: #1A222D;
--border: #1F2A37;
--border-strong: #2D3A4A;
--ink-0: #E6EBF2;        /* primary text */
--ink-1: #8593A6;        /* secondary text */
--ink-2: #556377;        /* tertiary/metadata */
--ink-3: #3B4757;        /* quaternary/disabled */
--accent: #D4A056;       /* AMBER - AI/agent signature */
--accent-soft: rgba(212, 160, 86, 0.12);
--accent-line: rgba(212, 160, 86, 0.35);
--p1: #E5484D;           /* Severity P1 */
--p1-soft: rgba(229, 72, 77, 0.14);
--p2: #F5A524;           /* Severity P2 */
--p2-soft: rgba(245, 165, 36, 0.14);
--p3: #4493F8;           /* Severity P3 */
--p3-soft: rgba(68, 147, 248, 0.14);
--ok: #52B788;           /* Resolved/success */
--ok-soft: rgba(82, 183, 136, 0.14);
--ok-line: rgba(82, 183, 136, 0.35);
--signal: #6BB6C7;       /* Chart lines, data */
--pending: #9C6ADE;      /* Pending approval */

--btn-primary-bg: #E6EBF2;
--btn-primary-fg: #0A0D12;

/* Code block - luôn theme-aware */
--code-bg: #06090D;
--code-head-bg: #0D1218;
--code-border: #1A2028;
--code-k: #C792EA;       /* keywords - purple */
--code-fn: #D4A056;      /* function names - amber */
--code-s: #A3D5AA;       /* strings - green */
--code-n: #6BB6C7;       /* numbers - cyan */
--code-cm: #556377;      /* comments */
--code-p: #8593A6;       /* punctuation */
```

### Light theme — dán vào `[data-theme="light"]`

```css
--bg-0: #F0F2F5;         /* cool off-white, KHÔNG dùng cream ấm */
--bg-1: #FFFFFF;
--bg-2: #F6F8FB;
--bg-3: #EAEEF3;
--bg-hover: #F1F4F8;
--border: #E1E5EC;
--border-strong: #C7CDD6;
--ink-0: #0F1620;
--ink-1: #4C5766;
--ink-2: #6C7684;
--ink-3: #A2AAB6;
--accent: #A16A25;       /* Darker amber for contrast */
--accent-soft: rgba(161, 106, 37, 0.08);
--accent-line: rgba(161, 106, 37, 0.35);
--p1: #C8353B;
--p1-soft: rgba(200, 53, 59, 0.08);
--p2: #B77813;
--p2-soft: rgba(183, 120, 19, 0.08);
--p3: #2465C6;
--p3-soft: rgba(36, 101, 198, 0.08);
--ok: #1E7F4E;
--ok-soft: rgba(30, 127, 78, 0.10);
--ok-line: rgba(30, 127, 78, 0.35);
--signal: #2B7185;
--pending: #6541A2;

--btn-primary-bg: #0F1620;
--btn-primary-fg: #FFFFFF;

--code-bg: #F8FAFC;
--code-head-bg: #EEF2F7;
--code-border: #E1E5EC;
--code-k: #7A3EBE;
--code-fn: #A16A25;
--code-s: #2E7D32;
--code-n: #1F6580;
--code-cm: #8993A2;
--code-p: #6C7684;
```

### Typography

```css
--font-display: 'Newsreader', Georgia, serif;
--font-body: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
--font-mono: 'JetBrains Mono', ui-monospace, 'SF Mono', monospace;
```

**Type scale:**
- Body default: **13.5px / 1.55** — hơi nhỏ để dense info
- Sidebar title: `font-display` 22px weight 400
- Case title (H1): `font-display` **34px** weight 400, letter-spacing -0.02em, có thể có `<span class="sev">P1</span>` italic weight 300 phía trước
- Section title (H2): `font-display` 22px weight 400, có `<em>` in italic weight 300 màu ink-1 để tạo nhấn nhá kiểu editorial
- Section eyebrow: `font-mono` 10.5px UPPERCASE letter-spacing 0.16em màu accent
- Vital value: `font-display` 30px weight 400 letter-spacing -0.02em
- Meta/small text: 11.5–12.5px
- Code inline & mono labels: `font-mono` 10.5–12px

### Layout dimensions

- Header: **52px** height, `grid-template-columns: 340px 1fr auto`
- Sidebar: **340px** width
- Main content: `max-width: 920px`, padding `32px 44px 80px`
- Card border-radius: **10px** (main cards) hoặc 8px (nested) hoặc 6-7px (small controls)
- Button height: 34px (default), 28-30px (small)

---

## 🏗️ Cấu trúc layout tổng thể

```
<html data-theme="dark">
<body>
  <div class="app">                          /* grid-template-rows: 52px 1fr */
    <header class="header">…</header>
    <div class="main-grid">                  /* grid-template-columns: 340px 1fr */
      <aside class="sidebar">…</aside>
      <main class="content">
        <div class="content-inner view active" data-view="active">…</div>
        <div class="content-inner view" data-view="resolved">…</div>
      </main>
    </div>
  </div>
</body>
</html>
```

CSS cho views:
```css
.view { display: none; }
.view.active { display: block; }
```

---

## 🧩 Components — spec chi tiết

### 1. Header

3 vùng grid: `[brand] [center-status-strip] [right-actions]`

**Brand (trái):**
- 22×22px vuông với gradient `linear-gradient(135deg, var(--accent) 0%, #7A5122 100%)`, border-radius 5px, chứa chữ "W" (Newsreader italic 14px, màu trắng)
- Text "War Room" (Newsreader 17px weight 400) + "/ v2" (Newsreader italic 300, màu ink-1)

**Center status strip:**
- Hàng ngang các status item, gap 22px
- `pulse-dot` animation cho P1 đang mở (7×7px, đỏ, có ring pulse expand ra `2s ease-out infinite`)
- Các item khác: `◆` màu tương ứng + text "11 P2", "15 P3", "MTTR hôm nay 14ph", "Agent chạy 98.2%"

**Right (phải):**
- 2 ghost buttons: "Runbooks", "Postmortems" (icon + text)
- 1 primary button: "Deploy" (nền `btn-primary-bg`, chữ `btn-primary-fg`)
- **Theme toggle button** — icon-only 30×30px, chứa 2 SVG (sun + moon) chồng lên nhau, dùng CSS `opacity` + `transform: rotate()` để crossfade khi đổi theme. Sun hiển thị khi `data-theme="light"`, moon khi `dark`. Animation 0.35s cubic-bezier.
- Avatar: 28×28px tròn, gradient xám xanh `linear-gradient(135deg, #4A5F7A 0%, #2C3E52 100%)`, chứa initials "TH"

### 2. Sidebar

4 vùng grid dọc: `[header] [tabs] [search] [scrollable list]`

**Sidebar header:**
- Eyebrow: "Bảng theo dõi" (mono 10.5px uppercase)
- Title: "Sự cố *của hệ thống*" — Newsreader 22px, từ "của hệ thống" bọc trong `<em>` italic weight 300

**Tabs (2 tabs):**
- "Đang xảy ra" (count 28) và "Đã xử lí" (count 14)
- Active tab: chữ ink-0 + border-bottom 2px màu accent, count badge có nền accent-soft và chữ accent
- Data attribute: `data-tab="active"` / `data-tab="resolved"`

**Search:**
- Input 32px cao, background bg-2, có kính lúp SVG bên trái và badge `⌘K` bên phải
- Placeholder: "Tìm theo service, KAN, người trực..."

**Incident list (scrollable):**
- 2 panels `<div class="sb-panel active" data-panel="active">` và `<div class="sb-panel" data-panel="resolved">`
- Chỉ panel `.active` được `display: block`

**Incident card structure:**
```html
<div class="incident" data-view="active|resolved" data-id="KAN-XX">
  <div class="inc-row1">
    <span class="inc-sev p1|p2|p3|done">P1</span>   <!-- Newsreader italic 15px, màu severity -->
    <span class="inc-id">KAN-43</span>               <!-- mono 10.5px, ink-2 -->
    <span class="inc-status-dot active|pending|resolving|resolved"></span>
  </div>
  <div class="inc-title">…</div>                     <!-- 13px weight 500, max 2 lines truncate -->
  <div class="inc-meta">
    <span>13 phút</span><span>·</span><span>Thanh Toàn</span>
    <span class="inc-spark"><svg…/></span>            <!-- 52×16 sparkline SVG path -->
  </div>
</div>
```

- Card padding: `12px 12px 12px 14px`, border-radius 7px, transparent border
- Hover: background bg-hover
- Active state: background bg-2 + border border-strong + có thanh 2px accent bên trái (dùng `::before`)
- Status dot 6×6px:
  - `.active` — đỏ P1 với ring `box-shadow: 0 0 0 3px var(--p1-soft)`
  - `.pending` — tím pending
  - `.resolving` — vàng P2
  - `.resolved` — xanh ok

**Sparkline SVG:**
```html
<svg width="52" height="16" viewBox="0 0 52 16">
  <path d="M0 12 L6 11 L12 12 …" fill="none" stroke="var(--p1)" stroke-width="1.5"/>
</svg>
```
Sparkline dùng màu tương ứng với severity (p1/p2/p3/ok). Path shape phản ánh trend: tăng dốc = incident đang xấu đi, giảm về = đang khắc phục.

### 3. Case header (main content)

- **Crumb** (breadcrumb): mono 11px uppercase, format `KAN-43 / service-thanh-toan / latency-p95 · [status pill]`
- Status pill:
  - `.live` — nền p1-soft, chữ p1, có chấm nhỏ 5×5px blink animation `1.5s ease-in-out infinite` (opacity 1 ↔ 0.3)
  - `.done` — nền ok-soft, chữ ok, prefix bằng `✓` (không animate)
- **Title (H1):** Newsreader 34px weight 400. Format: `<span class="sev p1|done">P1</span> Tiêu đề với <span class="service">tên-service</span>`
  - `.sev` italic weight 300, màu severity, margin-right 6px
  - `.service` italic weight 300, màu ink-1
- **Meta strip:** Border top+bottom 1px, padding 14px, các item cách 22px, mỗi item có icon SVG 14px + label + `<span class="val">value bold</span>`. Cuối cùng có `.meta-actions` với `margin-left: auto`

### 4. Section header pattern (dùng cho mọi section)

```html
<div class="sec-head">
  <span class="sec-eyebrow">01 · Bằng chứng</span>
  <h2 class="sec-title">Agent <em>thấy gì</em></h2>
  <span class="sec-aside">Cập nhật cách đây 8 giây</span>
</div>
```

- Eyebrow: mono 10.5px uppercase letter-spacing 0.16em màu accent, có prefix số section
- Title: Newsreader 22px, từ khóa italic bọc `<em>` màu ink-1 weight 300
- Aside: right-aligned qua `margin-left: auto`, ink-2 12px

**Sections dùng chung pattern này với title và eyebrow khác nhau.**

### 5. Vitals strip

Grid 4 cột, gap 1px trên nền border (tạo hiệu ứng divider), border-radius 10px, overflow hidden.

```html
<div class="vitals">
  <div class="vital alert">                    <!-- .alert: gradient p1-soft từ trên xuống -->
    <div class="vital-label"><svg…/>Hiện tại</div>
    <div class="vital-value">1.9<span class="unit">giây</span></div>
    <div class="vital-sub">p95 · 1 phút gần nhất</div>
  </div>
  <!-- 3 vitals khác không có .alert -->
</div>
```

- Vital padding: `16px 18px`
- Label: mono 10px uppercase letter-spacing 0.12em ink-2
- Value: Newsreader 30px weight 400 letter-spacing -0.02em
- Unit: body font 13px ink-1
- Delta badge (optional): mono 12px, `.bad` màu p1 nền p1-soft, `.good` màu ok nền ok-soft
- Variant `.alert`: gradient nền `linear-gradient(180deg, var(--p1-soft) 0%, var(--bg-1) 60%)` + value màu p1
- Variant `.ok`: tương tự nhưng dùng ok-soft và ok

### 6. Chart panel

- Panel: bg-1, border 1px, radius 10px, padding `18px 20px 12px`
- Chart head: title bên trái (function name màu accent, mono), legend bên phải (mỗi item có swatch 10×2px)
- SVG chart `viewBox="0 0 800 200"` preserveAspectRatio="none"
  - Grid lines: `<line stroke="var(--border)" stroke-dasharray="2 4"/>` ở y=40, 80, 120, 160
  - Threshold line: y=100, stroke p1, dasharray "4 4", opacity 0.55
  - Baseline (dashed, subtle): stroke ink-2, dasharray "3 3", opacity 0.65
  - Main metric path: 2 layers — 1 layer area fill với `<linearGradient>` (signal stop-opacity 0.28 → 0), 1 layer line stroke signal width 1.75
  - Current point: circle r=4 + circle r=8 opacity 0.2 (glow effect)
  - Annotation marker (vertical line + text label) tại các điểm quan trọng: `t=0 · vượt ngưỡng`, `peak`, `fix áp dụng`, `về baseline`
- Chart foot: mono 10.5px ink-2, các timestamp `space-between`

### 7. Evidence + Code block

**Evidence card:** bg-1, border, radius 10px, padding 18px 20px, chứa `<p>` và optionally code block + link row.

**Inline code (`.inline-code`):**
```css
font-family: mono; font-size: 12px;
padding: 1px 6px; background: bg-3; border: 1px solid border;
border-radius: 4px; color: accent;
```

**Code block (theme-aware):**
```html
<div class="code-block">
  <div class="code-head">
    <span class="code-lang">PromQL</span>
    <button class="code-copy"><svg…/> Sao chép</button>
  </div>
  <pre class="code-body">
    <span class="k">histogram_quantile</span><span class="p">(</span>…
  </pre>
</div>
```

- Background dùng `--code-bg` (đen ở dark, gần trắng ở light)
- Head background `--code-head-bg`
- Syntax highlighting qua CSS classes: `.k` keyword, `.fn` function, `.s` string, `.n` number, `.cm` comment italic, `.p` punctuation

**Link row (Prometheus link):**
- Card bg-2, border, radius 8px, padding 10px 14px
- Icon external-link + text label + `.url` (mono nhỏ, màu accent, truncate)

### 8. Reasoning timeline (Agent's chain of thought)

```html
<div class="reasoning">                       <!-- hoặc .reasoning.done cho resolved view -->
  <div class="reasoning-item">
    <div class="r-label">Quan sát</div>
    <div class="r-body">…text với <strong>emphasized bits</strong>…</div>
    <span class="r-evidence warn">p95 <span class="val">1.90s</span></span>
    <span class="r-evidence ok">GC pause <span class="val">&lt; 40ms</span></span>
  </div>
  <div class="reasoning-item conclusion">…</div>
</div>
```

- `.reasoning`: padding-left 24px, border-left 1px màu `--accent-line` (hoặc `--ok-line` cho `.done`), margin-left 4px
- Mỗi item: `::before` là chấm tròn 9×9px `background: var(--bg-0)` border 1.5px accent, positioned `left: -29px; top: 5px`
- `.conclusion` item có chấm filled (background accent) + `box-shadow: 0 0 0 4px var(--accent-soft)` tạo hiệu ứng emphasis
- `.r-label`: mono 10.5px uppercase màu accent (hoặc ok cho `.done`)
- `.r-evidence`: chip inline, bg-2, border, radius 5px, mono 11px. Variants `.warn` (val màu p1), `.ok` (val màu ok)

### 9. Proposal card (2 variants: pending & executed)

**Pending variant (active view):**
```html
<div class="proposal">
  <div class="proposal-head">
    <div class="proposal-tag">
      <svg lightning-bolt/> Hành động khẩn · cần bạn phê duyệt
    </div>
    <div class="proposal-title">Nâng <code>max_connections</code> của Postgres từ <code>32</code> lên <code>64</code></div>
    <div class="proposal-target">→ service-thanh-toan · db-primary.payment.internal</div>
  </div>
  <div class="proposal-body">
    <p>Đây là biện pháp <strong>giảm áp lực tức thời</strong>…</p>
    <div class="impact-grid">                 <!-- 3 cột -->
      <div class="impact"><div class="lb">Rủi ro</div><div class="vl">Thấp</div></div>
      <div class="impact"><div class="lb">Downtime</div><div class="vl">0 <small>giây (hot reload)</small></div></div>
      <div class="impact"><div class="lb">Có thể rollback</div><div class="vl">Được <small>· 1 lệnh</small></div></div>
    </div>
    <p>Chi tiết: chạy <span class="inline-code">…</span></p>
  </div>
  <div class="confirm-strip">
    <div class="who">
      <span class="a">TT</span>                <!-- Mini avatar 20×20 -->
      <span>Chờ <strong>Thanh Toàn</strong> phê duyệt · Agent sẽ không tự chạy nếu chưa được duyệt</span>
    </div>
    <button class="btn ghost">Hỏi thêm</button>
    <button class="btn ghost">Từ chối</button>
    <button class="btn approve">Duyệt & thực thi <svg arrow-right/></button>
  </div>
</div>
```

- `.proposal`: `background: linear-gradient(180deg, var(--accent-soft) 0%, transparent 40%), var(--bg-1)` + border color accent-line, radius 12px
- `.proposal-tag`: mono 10.5px uppercase màu accent
- `.proposal-title`: Newsreader 20px, `<code>` inside có nền bg-2 + border + color accent
- `.proposal-target`: mono 12.5px ink-1
- `.impact-grid`: 3 cột, mỗi impact là card bg-2 border radius 8px
- `.confirm-strip`: nền bg-2, border-top, các nút align right
- Nút `.approve`: nền `--btn-primary-bg` chữ `--btn-primary-fg` (trắng nền đen ở dark, đen nền trắng ở light)

**Executed variant (resolved view):**
```html
<div class="proposal executed">…</div>
```
- Background gradient dùng `ok-soft` thay vì `accent-soft`
- Border color `ok-line`
- `.proposal-tag` và `.proposal-title code` màu `ok` thay vì `accent`
- `.confirm-strip .who` chứa `<span class="check-icon">✓</span>` (20×20 tròn nền ok trắng chữ) thay vì avatar
- Chỉ có 1 nút "Xem log thực thi" (ghost), không có approve/reject

### 10. Activity timeline

```html
<div class="activity">
  <div class="act agent">
    <div class="time">16:29:53</div>
    <div class="text"><span class="who agent">Agent</span> đề xuất tăng max_connections…</div>
  </div>
  <div class="act human">…</div>
  <div class="act system">…</div>
  <div class="act ok">…</div>                  <!-- Chỉ trong resolved view -->
</div>
```

- Container: `padding-left: 24px; border-left: 1px solid var(--border); margin-left: 4px`
- Mỗi `.act`: grid `60px 1fr` (time cột trái, text cột phải), padding-bottom 18px
- `::before` là chấm 7×7px:
  - `.agent` → accent
  - `.human` → signal
  - `.system` → ink-3
  - `.ok` → ok + `box-shadow: 0 0 0 3px var(--ok-soft)`
- Time: mono 11px ink-2
- Text: 13px ink-0, `.who` có màu tương ứng

### 11. Related incidents grid

```html
<div class="related-grid">                     <!-- 2 cột, gap 10px -->
  <div class="rel-card">
    <div class="rel-head">
      <span class="rel-sev" style="color: var(--p1)">P1</span>
      <span>KAN-42 · Kafka lag</span>
    </div>
    <div class="rel-title">…</div>
    <div class="rel-meta">…</div>
  </div>
</div>
```

- Card: bg-1, border, radius 8px, padding 14px 16px, hover đổi border-strong
- Head: mono 10.5px uppercase, sev là Newsreader italic

### 12. Checklist (chỉ trong resolved view — section Bài học)

```html
<div class="checklist">
  <div class="check-item done">                 <!-- .done: checkbox đã tick -->
    <div class="check-box"></div>               <!-- 18×18px, khi .done: nền ok + chứa ✓ -->
    <div class="text">Thêm index idx_orders_customer_id vào Postgres production</div>
    <div class="assignee">Minh</div>            <!-- 11.5px ink-2 -->
    <div class="tag">immediate</div>            <!-- mono 10.5px, nền bg-3 -->
  </div>
</div>
```

- Item: bg-1, border, radius 8px, padding 12px 14px, gap 12px, cursor pointer
- Check-box: 18×18 border 1.5px, khi `.done`: nền ok + border ok + chứa `✓`
- Text khi done: strikethrough với `text-decoration-color: var(--ink-3)`, màu ink-1

### 13. Buttons

- `.btn`: height 34px, padding `0 16px`, radius 7px, font 12.5px weight 500
- `.btn.ghost`: chữ ink-1, border border-strong, hover: chữ ink-0 + nền bg-3
- `.btn.approve`: nền `--btn-primary-bg`, chữ `--btn-primary-fg`, hover filter brightness(1.05)
- `.btn.small`: height 28px, padding `0 10px`, font 12px

---

## 📄 Nội dung 2 views

### VIEW 1: Active incident (KAN-43)

**Case title:** "P1 Thời gian xử lí request vượt ngưỡng ở *service-thanh-toan*"

**Meta strip items:**
- Phát hiện: `16:16:38 hôm nay`
- Kéo dài: `13 phút 15 giây`
- Người trực: `Thanh Toàn`
- Ảnh hưởng: `~12% traffic thanh toán`
- Actions: "Nhận việc", "Bàn giao" (cả 2 đều ghost small)

**Section 01 · Bằng chứng → Agent *thấy gì***
- Aside: "Cập nhật cách đây 8 giây"
- Vitals: **Hiện tại 1.9 giây** (alert) / Ngưỡng 1.0 giây / Mức lệch 1.9× (+90% badge bad) / Baseline 7 ngày 1.06 giây
- Chart: metric tăng vọt từ ~1.08 lên 1.9 trong khoảng 40% cuối, có marker `t=0 · vượt ngưỡng`, current point đỏ với glow
- Evidence card: text + code PromQL (histogram_quantile) + link row Prometheus

**Section 02 · Lập luận → Agent *nghĩ vì sao***
- Aside: "Độ tin cậy · cao (0.87)" (số 0.87 màu ok)
- Reasoning timeline 4 items:
  1. **Quan sát** — p95 tăng từ 1.06s → 1.90s trong 3 phút, request rate không tăng. Evidence: `p95 1.90s` (warn), `rate ≈ ổn định`, `CPU 42%`
  2. **Kiểm tra database** — `db_pool_connections_in_use / db_pool_size = 100%`. Evidence: `pool used 32/32` (warn), `giao dịch idle 0%`
  3. **Loại trừ nguyên nhân khác** — VNPay ok, GC ok, disk I/O ok, deploy cách đây 2h. Evidence: 3 chip `ok`
  4. **Kết luận** (`.conclusion`) — Connection pool cạn kiệt, root cause likely là query chậm mới

**Section 03 · Đề xuất hành động → Agent *muốn làm gì***
- Proposal (pending variant):
  - Tag: "Hành động khẩn · cần bạn phê duyệt"
  - Title: "Nâng `max_connections` của Postgres từ `32` lên `64`"
  - Target: "→ service-thanh-toan · db-primary.payment.internal"
  - Body: giải thích + impact grid (Rủi ro: Thấp / Downtime: 0 giây / Rollback: Được)
  - Confirm strip với avatar TT + 3 nút

**Section 04 · Diễn biến** — Activity timeline 6 events từ 16:15:22 (alert first fires) đến 16:29:53 (Agent đề xuất)

**Section 05 · Ngữ cảnh** — 2 related cards: KAN-42 (đang mở, cùng service) + KAN-28 (đã đóng, cùng triệu chứng)

### VIEW 2: Resolved incident (KAN-28)

**Case title:** "P1 Truy vấn chậm trên bảng *orders* làm nghẽn connection pool"

**Meta strip items:**
- Bắt đầu: `14:02 hôm nay`
- Giải quyết lúc: `14:20 · kéo dài 18 phút`
- Xử lí bởi: `Thanh Toàn + Agent`
- Ảnh hưởng: `~14% traffic peak`
- Actions: "Mở lại" (ghost), "Xem postmortem" (approve variant, có icon file)

**Section 01 · Tóm tắt → *Chuyện gì đã xảy ra***
- Evidence card với đoạn văn tóm tắt vụ việc
- Vitals: **Peak 2.4 giây** / **Hiện tại 0.9 giây** (`.ok` variant) / Thời gian phát hiện 47 giây / Thời gian khắc phục 18 phút (sub "tốt hơn MTTR trung bình (24ph)")
- Chart: **full arc** — baseline flat → tăng nhanh → peak → giảm → về baseline. Có 3 markers: `peak · 2.4s` (amber), `fix áp dụng` (ok), `về baseline` (ok). Current point màu ok thay vì p1.

**Section 02 · Nguyên nhân gốc → Vì sao *chuyện này xảy ra***
- Aside: "Xác nhận bởi Thanh Toàn + DBA" (chữ "Thanh Toàn + DBA" màu ok)
- Reasoning timeline `.done` (viền và chấm màu ok) 3 items:
  1. **Trigger** — feature "lịch sử giao dịch" deploy lúc 13:45, dùng query `SELECT * FROM orders WHERE customer_id = ?` không có index
  2. **Cơ chế** — full-table scan 800ms, 4.2M rows, giữ connection lâu → pool 32 cạn
  3. **Kết luận** — root cause là thiếu index, không phải hạ tầng

**Section 03 · Cách khắc phục → *Đã làm gì***
- Proposal `.executed` variant:
  - Tag: "Đã thực thi thành công · 14:14 (giảm áp lực) + 14:19 (fix gốc)"
  - Title: "Fix 2 bước: nâng pool tạm thời rồi `CREATE INDEX`"
  - Body: mô tả bước 1 (nâng max_connections) và bước 2 (CREATE INDEX)
  - Impact grid: p95 trước→sau (2.4s → 0.9s) / Query time (800ms → 12ms) / Rollback đã sẵn (Có)
  - Confirm strip có check-icon xanh + "Duyệt bởi Thanh Toàn lúc 14:13 · Thực thi bởi Agent · Xác minh xong lúc 14:20", chỉ có 1 nút "Xem log thực thi"

**Section 04 · Diễn biến → Timeline *đầy đủ***
- 10 events từ 14:02:31 (alert fires) đến 14:20:11 (`.ok` variant — "Đã giải quyết")

**Section 05 · Bài học → Hành động *để không lặp lại***
- Aside: "3 / 5 hoàn tất"
- Checklist 5 items:
  - ✅ Thêm index `idx_orders_customer_id` — Minh — tag `immediate`
  - ✅ Cấu hình `max_connections = 64` làm mặc định trong Terraform — Thanh Toàn — `immediate`
  - ✅ Viết postmortem và chia sẻ trong #eng-weekly — Thanh Toàn — `this-week`
  - ⬜ Bổ sung rule vào CI: cảnh báo khi query mới không có EXPLAIN ANALYZE — Minh — `next-sprint`
  - ⬜ Thêm alert `db_query_time_p95 > 500ms` theo từng bảng — SRE team — `next-sprint`

**Section 06 · Ngữ cảnh** — 2 related: KAN-43 (đang mở, có thể cùng root cause) + KAN-15 (đã đóng, cùng service)

---

## 📋 Data cho sidebar

### Active tab (9 incidents)
| ID | Sev | Status dot | Title | Duration | Extra |
|---|---|---|---|---|---|
| KAN-43 | P1 | active | service-thanh-toan: p95 request duration = 1.90s (ngưỡng 1.00s) | 13 phút | Thanh Toàn |
| KAN-42 | P1 | pending | service-thanh-toan: Kafka consumer lag > 50k | 14 phút | Chờ duyệt |
| KAN-38 | P1 | resolving | gateway-api: 5xx rate spike lên 4.2% | 19 phút | Đang khắc phục |
| KAN-37 | P2 | active | redis-cache: hit rate rơi xuống 71% (baseline 94%) | 21 phút | — |
| KAN-36 | P2 | resolving | worker-mail: queue backlog 12k messages | 34 phút | — |
| KAN-32 | P2 | pending | service-don-hang: connection timeout khi gọi payment | 41 phút | — |
| KAN-31 | P2 | active | service-user: DB read replica lag 4.2s | 52 phút | — |
| KAN-29 | P3 | active | metrics-collector: memory usage 87% | 1h 22ph | — |
| KAN-27 | P3 | pending | image-cdn: cache miss ratio tăng nhẹ | 2h 14ph | — |

### Resolved tab (5 incidents) — sev class `.done` (màu ok)
| ID | Sev | Title | Duration | When |
|---|---|---|---|---|
| KAN-28 | P1 | service-thanh-toan: p95 = 2.4s do query orders thiếu index | 18 phút | 2h trước |
| KAN-24 | P2 | worker-mail: queue backlog do rate limit từ SendGrid | 42 phút | 5h trước |
| KAN-19 | P1 | gateway-api: 5xx spike do cert expired ở upstream | 1h 12ph | Hôm qua |
| KAN-15 | P2 | redis-cache: eviction rate cao do memory limit thấp | 27 phút | Hôm qua |
| KAN-11 | P3 | cron-report: chạy chậm do lock trên bảng transactions | 15 phút | 2 ngày trước |

---

## ⚡ Interactive behaviors (JavaScript)

Chỉ dùng vanilla JS, không dùng framework. Đặt trong `<script>` cuối `<body>`.

```javascript
// 1. Theme toggle
const themeToggle = document.getElementById('theme-toggle');
const html = document.documentElement;
themeToggle.addEventListener('click', () => {
  const current = html.getAttribute('data-theme');
  html.setAttribute('data-theme', current === 'dark' ? 'light' : 'dark');
});

// 2. Sidebar tab switching
document.querySelectorAll('.sb-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    const target = tab.dataset.tab;
    document.querySelectorAll('.sb-tab').forEach(t => t.classList.toggle('active', t === tab));
    document.querySelectorAll('.sb-panel').forEach(p => p.classList.toggle('active', p.dataset.panel === target));
  });
});

// 3. Incident selection → switch main view
document.querySelectorAll('.incident').forEach(inc => {
  inc.addEventListener('click', () => {
    const view = inc.dataset.view;
    document.querySelectorAll('.incident').forEach(i => i.classList.remove('active'));
    inc.classList.add('active');
    document.querySelectorAll('.view').forEach(v => v.classList.toggle('active', v.dataset.view === view));
    document.querySelector('.content').scrollTop = 0;
  });
});
```

**Behavior spec:**
- Click theme toggle → `<html data-theme>` swap giữa `dark` ↔ `light`. Body có `transition: background 0.25s ease, color 0.25s ease` để đổi mượt. Icon sun/moon crossfade qua opacity + transform rotate.
- Click sidebar tab → panel tương ứng show (dùng class `.active` toggle `display: block/none`).
- Click bất kỳ incident nào → highlight nó trong sidebar + đổi view chính. Content scroll về đầu.

---

## ✅ Acceptance criteria

Giao diện xong khi:

1. **Chạy được** khi mở file HTML trực tiếp trong browser (không cần server).
2. **Dark mode và light mode đều đẹp** — không có chỗ nào contrast thấp, không có text vô hình. Test cả 2 themes ở view active và view resolved.
3. **Theme toggle mượt** — icon crossfade, background transition 0.25s, không có "flash of unstyled content".
4. **Tab switching hoạt động** — click "Đã xử lí" hiện đúng list resolved, click "Đang xảy ra" hiện đúng list active.
5. **Click bất kỳ incident nào** → main view đổi (active incident → view "active", resolved incident → view "resolved").
6. **Sparklines render đúng** — mỗi incident trong sidebar có sparkline SVG hiển thị.
7. **Chart render đúng** — SVG chart trong cả 2 views có gradient area fill và markers.
8. **Không có console error.**
9. **Typography phân biệt rõ** — serif (Newsreader) chỉ dùng cho headings/severity/vital values; sans (Inter) cho body/UI; mono (JetBrains Mono) cho code/timestamps/labels.
10. **Amber accent chỉ xuất hiện ở nội dung AI/Agent** — không dùng cho các nút primary hoặc các elements khác.
11. **Không thêm animation thừa** — không glow ambient, không floating, không parallax. Chỉ có: pulse dot ở header, blink dot ở live status pill, transition khi hover/theme change.
12. **Layout không vỡ** khi resize window đến ~1200px width (không cần responsive mobile).

---

## 💡 Gợi ý khi implement

- Viết CSS variables trước, HTML sau. Test theme toggle sớm.
- Viết layout chính (grid + sidebar + content) trước, rồi mới đến chi tiết components.
- SVG charts hardcode data trong `d` attribute — đây là mockup UI, không cần dynamic.
- Sparklines chỉ cần ~7-10 điểm là đủ để nhìn ra trend.
- Test rằng click các nút không làm reload page (thêm `type="button"` nếu cần).
- Ghi CSS theo thứ tự: reset → tokens → layout → components. Comment block phân section rõ ràng.
- File final khoảng 1200-1400 lines HTML+CSS+JS là hợp lý.

**Chúc bạn build vui vẻ. Nhớ giữ triết lý "phòng điều khiển yên tĩnh" — đừng biến nó thành cây thông Noel.**

