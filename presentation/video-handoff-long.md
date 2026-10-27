# Bàn giao dựng video — cho Long

Kế hoạch đầy đủ ở [`video-plan.md`](video-plan.md). File này chỉ trả lời **ba câu**:
Long dán gì vào Flow · ai quay phần nào · lắp lại thế nào.

## Chia việc

| Phần | Ai | Ghi chú |
|---|---|---|
**3 shot B-roll** *(28 giây)* | **Long** — gen bằng Flow | prompt ở §1 |
**9 cảnh màn hình** *(152 giây)* | **Đức** — quay màn hình | Đức có stack chạy được |
**Overlay + lồng tiếng + dựng** | **Long** | danh sách ở §3 |

> ⚠️ **Flow không gen được phần sản phẩm.** 152 giây kia là màn hình thật: terminal,
> war room, Jira. Đó là điểm mạnh nhất của dự án — mọi con số đều thật, kiểm lại được.
> Gen phần đó bằng AI là **tự phá** thứ duy nhất khó bắt chước.
>
> Và chữ do AI gen luôn ra ký tự méo. Cắt cạnh màn hình thật là lộ ngay.

---

# §1. Ba prompt dán vào Flow

## Ba shot, tổng 28 giây

    SHOT A  14s   0:00        sự bình yên
    SHOT B   8s   0:40        nghịch lý — điện thoại reo, đường xanh không đổi
    SHOT C   6s   2:40        đóng vòng — cùng khung, trời đã sáng

## ⚠️ Đọc trước: giới hạn độ dài clip

Flow gen mỗi lần khoảng **8 giây**. Nên **shot A không gen một lần được** nếu muốn 14
giây. Hai cách:

- **Nếu Flow gen được 14 giây một lần** → làm luôn, cắt liền mạch hơn.
- **Nếu chỉ được 8 giây** → gen 2 clip cùng khung rồi nối, hoặc gen 8 giây và 6 giây còn
  lại dùng màn hình trạng thái thật *(Đức quay)*. Lời thoại cảnh 1 chạy xuyên 14 giây nên
  không lệch.

Shot B (8s) và shot C (6s) thì gen một lần được.

## Cài đặt Flow

```
Tỷ lệ khung   16:9
Độ dài        14s (A) · 8s (B) · 6s (C)
Âm thanh      bật, theo khối [AUDIO]
Gen           3–4 lần mỗi shot, chọn bộ KHỚP KHUNG nhất
```

Hai màu lấy từ `ui/theme.py` — `#52B788` là `--ok`, `#E5484D` là `--p1`. Dùng đúng
token của sản phẩm để cắt sang màn hình thật không lệch màu.

---

## SHOT A · 14 giây · đặt ở 0:00 · *sự bình yên*

```
[STYLE]
Extreme close-up, macro, shallow depth of field. A pitch-black bedroom at
night. On a dark wooden bedside table: a smartphone lying face-down, screen
off, completely still. Behind it and far out of focus, a laptop screen glows
faint green, showing only a single perfectly flat horizontal line — no text,
no numbers, unreadable at this distance. Nothing moves. A half-empty glass
of water catches a thin cold rim of moonlight. The room is asleep.

Camera: locked-off macro, almost imperceptible push-in over 14 seconds.
Focus stays on the dark phone in the foreground; the green line stays soft
and out of focus in the background.
Lighting: single soft green wash #52B788 from the out-of-focus laptop, very
low intensity. One thin cold blue moonlight rim from a window behind. Near
black everywhere else.

[AUDIO]
Quiet room tone. A faint air-conditioner hum. A distant single car passing
outside. No phone sound. No music. No alert tone.

[NEGATIVE]
red light, red colour anywhere, alert icons, warning symbols, flashing,
blinking, spiking or falling line graphs, readable text, numbers, letters,
dashboards with labels, sirens, dramatic music, tension score, people, hands,
movement, camera shake
```

---

## SHOT B · 8 giây · đặt ở **đầu cảnh 4 (0:40)** · *nghịch lý*

```
[STYLE]
Same bedside table, same darkness, identical framing to the previous shot.
The phone screen lights up and the phone buzzes hard against the wood,
rattling once, twice, then a third time. Behind it, still out of focus, the
laptop's green line stays perfectly flat and perfectly green — completely
unchanged. The
contradiction is the point: the phone is screaming, the screen says fine.
Hold on the unchanged green line for the final three seconds, not on the phone.

Camera: locked-off, identical to previous shot. In the last three seconds,
focus racks slowly from the buzzing phone to the flat green line behind it.
Lighting: unchanged soft green #52B788 wash. The phone's own screen light
is cold white and blown out, illegible.

[AUDIO]
One second of silence. Then an aggressive phone vibration rattling against
wood, three times. Then silence again. No music, no alert sting, no sub-bass.

[NEGATIVE]
red light, red colour anywhere, red alerts, alert icons, warning symbols,
spiking graphs, falling line charts, readable text, numbers, sirens,
dramatic music, sub-bass swell, people, faces, hands
```

---

## SHOT C · 6 giây · đặt ở **2:40**, sau cảnh 10 · *đóng vòng*

Cùng khung hình với shot A, nhưng **trời đã sáng**. Người xem hiểu ngay mà không cần nói:
*sự cố xong rồi, người trực về ngủ tiếp.* Đây là **giá trị sản phẩm nói bằng hình** — đúng
thứ BTC muốn ở 30 giây cuối.

```
[STYLE]
Same bedside table, same framing as the opening shot — but now early dawn.
The smartphone lies face-down again, screen off, completely still. Behind it,
still out of focus, the laptop's green line is flat and unchanged. The glass
of water is now lit by pale warm dawn light from the window instead of cold
moonlight. Everything is calm. Time has passed and nothing is on fire.

Camera: locked-off, identical framing to the opening shot, no push-in.
Completely static.
Lighting: soft warm dawn light from the window, low and diffuse. The green
#52B788 glow from the out-of-focus laptop is still there but weaker now that
the room has ambient light.

[AUDIO]
Quiet room tone. Faint early morning birds, very distant. Nothing else.
No music, no phone, no alert.

[NEGATIVE]
red light, red colour anywhere, alert icons, warning symbols, flashing,
readable text, numbers, letters, spiking or falling graphs, sirens, music,
uplifting score, people, faces, hands, movement, camera shake, sunrise
timelapse, lens flare
```

> `sunrise timelapse` và `lens flare` trong `[NEGATIVE]` để chặn thứ mô hình rất hay tự
> thêm — nó biến cảnh tĩnh thành clip du lịch.
>
> **Đừng để chữ nào trong shot C**, kể cả logo hay tên nhóm. Muốn card cuối có tên nhóm
> thì Long dựng riêng — chữ Flow gen ra ký tự méo.
>
> **Đừng thêm nhạc "vươn lên".** Tiếng chim xa xa với im lặng nói được nhiều hơn.

---

## Ba lưu ý khi gen

**① `readable text, numbers, letters` là dòng quan trọng nhất trong `[NEGATIVE]`.**
Mọi mô hình gen video dựng chữ thành ký tự méo. Video này cắt sang màn hình **thật**
ngay sau đó.

**② Không để mặt người.** Bỏ người thì mất luôn hai rủi ro: nhân vật khác nhau giữa các
shot, và tay/mắt bị dựng méo. *(Prompt gốc có `[CHARACTER]` chưa định nghĩa — đã bỏ.)*

**③ Giữ nguyên khung cho cả ba shot** — `identical framing` trong prompt B và C. Đây là
chỗ làm nên hiệu quả: người xem thấy **cái gì đã đổi, cái gì không đổi** giữa 2 giờ sáng
và lúc trời sáng. Gen tới khi được một bộ khớp.

**④ Không có màu đỏ nào.** Cảnh 1 là lúc **chưa có sự cố**, và luận điểm của dự án là
*"hệ thống cháy mà số đo vẫn nói ổn"*. Màn đỏ minh hoạ đúng câu chuyện *"monitor bắt
được sự cố"* — mà cảnh 5 nói thẳng là **không đủ**. Có đỏ là video tự mâu thuẫn.

---

# §2. Chín cảnh Đức quay — Long nhận file gì

Đức quay theo `video-plan.md` mục B, xuất **9 file rời**, đặt tên đúng thứ tự:

```
02-trang-trang-thai.mov      8s    trang xanh, không rê chuột
03-so-do-agent.mov          18s    sơ đồ 4 khối (hoặc Long tự dựng, xem dưới)
04-gay-su-co.mov            10s    terminal, đã tua nhanh ×6
05-so-do-mu.mov             22s    terminal, PromQL ra p95 = 0,048
06-agent-vao-cuoc.mov       25s    terminal, 2 dòng log cần khoanh
07-war-room.mov             19s    war room + bấm kiểm chứng PromQL
08-bi-chan.mov              10s    terminal, duyet.py bị từ chối
09-nguoi-duyet.mov          14s    Jira: kéo phiếu + mở History
10-tu-xac-nhan.mov           8s    terminal, verify → đã hồi phục
```

**Cảnh 3 (sơ đồ 4 khối)** — Long tự dựng bằng công cụ dựng cũng được, không cần quay.
Bốn khối `PHÁT HIỆN → CHẨN ĐOÁN → ĐỀ XUẤT → CHỜ DUYỆT`, khối cuối tô khác màu. Có thể
lấy ý từ `docs/architecture_diagram.md`.

**Yêu cầu quay:**

| | |
|---|---|
Độ phân giải | 1920×1080 trở lên |
Chữ terminal | ≥ 16pt — người xem trên điện thoại phải đọc được |
Con trỏ | đứng yên khi không cần thao tác |
Thông báo | tắt hết *(Do Not Disturb)* |
Thanh Dock, bookmark | ẩn / dọn gọn |

---

# §3. Overlay Long cần làm

| Cảnh | Overlay | Giữ bao lâu |
|---|---|---|
④ | khoanh đỏ dòng `{"500": …, "502": …}` + chữ **`0 request thành công`** | 2s |
⑤ | **ba ô cạnh nhau:** `Lỗi 99%` *(đỏ)* · `p95 0,048s` *(xanh)* · `Pool 0%` *(xanh)* | tới hết cảnh |
⑤ | **giữ thêm 3 giây SAU khi hết lời thoại — IM LẶNG, không nhạc** | 3s |
⑥ | khoanh đỏ dòng `tin cậy 30% — Chưa đủ bằng chứng…` **cả câu** | 4s |
⑥ | khoanh đỏ dòng `log đổi kết luận (30% → 70%) — thiếu cột idempotency_key` | 4s |
⑨ | khoanh **hai cái tên khác nhau** trong History của phiếu Jira | 3s |
⑩ | **`100% → 0%`** chữ thật to | tới hết cảnh |
⑪ | **bảng số** — xem dưới | 16s |

## Bảng số cảnh ⑪ — dựng sạch, đừng quay code

```
Phát hiện → đề xuất kèm runbook        39 giây
Tỷ lệ lỗi sau khắc phục               100% → 0%
Request thành công sau rollback        120 / 120
Cổng người duyệt bị vượt qua           0 lần
Chi phí hạ tầng                        0 đồng
```

Năm dòng này là **giá trị giao được**, không phải điểm thi. 30 giây cuối BTC yêu cầu
*"giá trị cốt lõi và **kết quả**"* — recall/precision là điểm thi, và kết video bằng
*"bỏ lọt 4, báo nhầm 5"* là kết bằng thiếu sót.

> ⚠️ **`39 giây` phải lấy từ chính lần quay, không chép số này.**
>
> Nó là hiệu số hai mốc trong log ở cảnh ⑥: dòng `Phát hiện sự cố` → dòng `đề xuất
> rollback`. Lần chạy 22/08 ra 39 giây (`20:27:42` → `20:28:21`). Lần quay của mình ra
> bao nhiêu thì ghi đúng bấy nhiêu.
>
> Bịa một con số nhỏ hơn là phá đúng thứ cả video đang xây. Hỏi Đức mốc thời gian sau
> khi quay xong cảnh ⑥.
>
> Bốn dòng còn lại: `100% → 0%` và `120/120` từ `docs/demo-runbook.md`; `0 lần vượt cổng`
> có `tests/test_hitl.py` và cảnh ⑧ chứng minh trực tiếp; `0 đồng` là Render free tier +
> Jira free + quota DashScope miễn phí.

## Ba giây im lặng ở cảnh ⑤ — đừng cắt

Cảnh 5 là lý do sản phẩm tồn tại. Nếu người xem không *thấm* nghịch lý *"lỗi 99% mà
p95 nhanh hơn bình thường"*, thì cảnh 6 chỉ còn là *"AI đọc log"* — nghe giống trăm dự
án khác, và mọi thứ sau đó mất trọng lượng.

**Ba giây im lặng làm con số nặng hơn ba câu giải thích.** Đừng lấp bằng nhạc.

---

# §4. Lắp lại — dòng thời gian

```
0:00 ─ 0:14   SHOT A (Flow 14s)            cảnh 1
0:14 ─ 0:22   02-trang-trang-thai.mov      cảnh 2
0:22 ─ 0:40   03-so-do-agent               cảnh 3 — chân dung Agent
0:40 ─ 0:48   SHOT B (Flow 8s)           ┐
0:48 ─ 0:58   04-gay-su-co.mov           ┘ cảnh 4
0:58 ─ 1:20   05-so-do-mu.mov              cảnh 5  ⚠️ KHÔNG CẮT
1:20 ─ 1:45   06-agent-vao-cuoc.mov        cảnh 6 — dài nhất
1:45 ─ 2:04   07-war-room.mov              cảnh 7 — có câu "kể tên 4 cái bỏ lọt"
2:04 ─ 2:14   08-bi-chan.mov               cảnh 8  ⚠️ KHÔNG CẮT
2:14 ─ 2:30   09-nguoi-duyet.mov           cảnh 9
2:30 ─ 2:38   10-tu-xac-nhan.mov         ┐
2:38 ─ 2:44   SHOT C (Flow 6s)           ┘ cảnh 10
2:44 ─ 3:00   bảng số (Long dựng)          cảnh 11 ⚠️ KHÔNG CẮT
```

**Lời thoại đầy đủ 11 cảnh ở `video-plan.md` mục B** — đã đếm chữ theo nhịp 150
chữ/phút. **Đừng thêm chữ**, thêm là tràn giờ.

Tổng: **435 chữ · 180 giây hình · 174 giây đọc** — dư 6 giây cho khoảng lặng.

## Nếu tràn giờ, cắt theo thứ tự

1. cảnh ⑦ *(war room)* — 16 → 12 giây, bỏ thao tác thứ nhất
2. cảnh ④ *(gây sự cố)* — tua nhanh mạnh hơn
3. cảnh ⑨ — bỏ phần mở History, chỉ nói

**Không bao giờ cắt:** ⑤ *(số đo mù)* · ⑧ *(bị chặn)* · ⑪ *(con số)*. Ba cảnh đó là ba
luận điểm — mất cái nào là mất một chân.

---

# §5. Nhạc và tiếng

**Không nhạc nền xuyên video.** Ba chỗ duy nhất nên có tiếng:

| Chỗ | Tiếng |
|---|---|
Shot A | room tone + điều hoà, rất nhỏ |
Shot B | **một** tiếng rung điện thoại, rồi im |
Cảnh ⑤, 3 giây cuối | **im lặng hoàn toàn** |

Lý do: video này bán **tính đáng tin**, không bán cảm xúc. Nhạc kịch tính chồng lên số
đo thật làm người xem nghi ngờ số đo. Giọng đọc rõ + im lặng đúng chỗ mạnh hơn.

---

# §6. Trước khi render — kiểm 6 điều

- [ ] Tổng **≤ 3:00**
- [ ] Không có chữ AI-gen nào lọt vào khung *(ký tự méo)*
- [ ] Không có **màu đỏ** nào trong hai shot Flow
- [ ] Màn hình **không hiện chữ `simulated`** ở cảnh ⑨ — thấy là phải quay lại cảnh đó
- [ ] Bảng số cảnh ⑪ khớp `eval/RESULTS-2026-08-21.md`
- [ ] Ba giây im lặng ở cảnh ⑤ còn nguyên
