# Kịch bản quay video demo — P-035

> Khác [demo-runbook.md](demo-runbook.md): file kia dành cho demo **trực tiếp**, chạy một mạch, sai là sai luôn. File này dành cho **quay video**, và tận dụng đúng lợi thế của video — quay rời từng đoạn rồi cắt ghép.

---

## Ý tưởng gốc: đừng chuyển trang khi đang quay

Vấn đề "phải di chuyển giữa các web liên tục" là vấn đề của demo trực tiếp. Quay video thì không cần: **mỗi cảnh là một lần quay riêng**, người xem chỉ thấy phần đã cắt.

Ba nguyên tắc:

1. **Một cảnh = một lần quay = một bố cục.** Không chuyển tab GIỮA cảnh. Cần đổi màn hình thì cắt.
2. **Chỉ dùng 3 bố cục.** Người xem nhận ra ngay mình đang nhìn cái gì, không bị lạc.
3. **Hỏng cảnh nào quay lại cảnh đó.** Không phải quay lại từ đầu — đây là lý do chính để quay theo take.

### Ba bố cục

| Mã | Bố cục | Dùng cho |
|---|---|---|
| **A** | Toàn màn hình một trang | Status page, war room, Jira, Prometheus |
| **B** | Chia đôi dọc: trình duyệt trái · terminal phải | Lúc cần thấy "lệnh chạy → màn hình đổi" |
| **C** | Chia đôi dọc: war room trái · Jira phải | Chỉ cảnh phê duyệt HITL |

> Chuyển tab trong lúc quay là lỗi hay gặp nhất — nó làm video trông lúng túng, và người xem mất mạch. Thà cắt.

---

## Chuẩn bị trước khi bấm ghi

### 1. Dựng hệ thống

```bash
docker compose -f docker-compose.demo.yml up -d
```
```bash
make api-local
```
```bash
make ui-local
```
```bash
python scripts/run_agent.py
```

### 2. Tải nền — làm SỚM, ít nhất 30 phút trước

```bash
python demo/loadtest.py
```

Không có tải nền thì biểu đồ trống trơn và `quantile_over_time` không có baseline để so. Chạy một lượt rồi để yên.

### 3. Nới thời gian tự thi hành — BẮT BUỘC nếu muốn quay cảnh HITL

`.env` đang đặt `AUTO_REMEDIATION_TIMEOUT_MINUTES=2`. Hai phút là **không đủ** để quay: Agent sẽ tự thi hành trước khi bạn kịp bấm duyệt, và mất luôn cảnh mạnh nhất của cả video.

```bash
AUTO_REMEDIATION_TIMEOUT_MINUTES=20 python scripts/run_agent.py
```

Quay xong cảnh HITL thì khởi động lại Agent bình thường để quay cảnh tự thi hành (Take 10).

### 4. Đăng nhập Jira đúng tài khoản người

Phải là tài khoản **người trực**, không phải tài khoản Agent. Đăng nhập nhầm tài khoản Agent thì `assert_human_approved()` chặn — đúng thiết kế, nhưng hỏng cảnh quay.

### 5. Dọn màn hình

- Tắt thông báo hệ thống, Zalo, Discord
- Đóng hết tab thừa, ẩn bookmark bar
- Zoom trình duyệt **125%** — chữ trong video nhỏ hơn nhìn trực tiếp rất nhiều
- Theme tối cho cả trang lẫn terminal

### ⚠️ Bẫy về thời gian: log container trôi rất nhanh

Đo được: cửa sổ log của một phiếu **biến mất sau ~20 phút** nếu có đợt tải mới. Nên **Take 6 (war room · log) phải quay ngay sau khi sự cố xảy ra**, đừng để sang hôm sau.

---

## Trình tự quay — 13 cảnh, ~10 phút

Thứ tự dưới đây là thứ tự **kể chuyện**, không phải thứ tự bắt buộc phải quay. Quay theo thứ tự nào tiện thì quay, cắt ghép sau.

---

### Take 0 · Mở đầu — 40 giây · Bố cục A

**Màn hình:** Status page `035.emmetech.id.vn`, cả 4 dịch vụ xanh.

**Lời thoại:**
> "Khi một hệ thống gặp sự cố lúc 2 giờ sáng, việc tốn thời gian nhất không phải là sửa — mà là **hiểu chuyện gì đang xảy ra**. Người trực phải mở Grafana, đọc log, đoán nguyên nhân, rồi mới quyết định làm gì.
>
> P-035 là một AI Agent làm phần đó. Nó quan sát hệ thống thật, tự phát hiện sự cố, tự chẩn đoán có bằng chứng, và đề xuất cách sửa — nhưng **không tự ý hành động**. Quyền quyết định vẫn là của con người."

---

### Take 1 · Kiến trúc — 50 giây · Bố cục A

**Màn hình:** `docs/architecture_diagram.md` mở trong VS Code (hoặc sơ đồ đã render).

**Lời thoại:**
> "Bốn khối. **Hệ thống giả lập** gồm 4 microservice chạy trong Docker — chúng bị sự cố THẬT, không phải giả lập bằng cách chèn lỗi. **Prometheus** thu số đo. **Agent** viết bằng LangGraph, quét mỗi 10 giây. **Jira** là nơi lưu vòng đời sự cố — chúng tôi cố ý không tự viết hệ thống ticket riêng.
>
> Toàn bộ tự host trên máy cá nhân, đưa ra internet qua Cloudflare Tunnel — ba tên miền, một cho trang trạng thái, một cho API, một cho Prometheus."

**Chú ý:** nói rõ "sự cố THẬT" — đây là điểm khác biệt so với fault injection, có ADR riêng ([ADR-0003](adr/0003-load-test-that-thay-fault-injection.md)).

---

### Take 2 · Hệ thống lúc bình thường — 45 giây · Bố cục A

**Màn hình:** Status page. Cuộn chậm qua 4 thẻ.

**Thao tác:**
1. Cuộn qua 4 thẻ dịch vụ
2. Dừng ở một thẻ, chỉ vào ô `up = 1` và biểu đồ 3 đường
3. **Bôi đen dòng `up = 1`** rồi giữ nguyên 5 giây — chứng minh trang tự cập nhật mà không phá thao tác người dùng

**Lời thoại:**
> "Đây là trang trạng thái công khai — thứ khách hàng nhìn thấy. Mỗi dịch vụ kèm ba chỉ số đo được thật: thời gian phản hồi p95, tỷ lệ lỗi, lưu lượng. Mỗi chỉ số một trục riêng vì đơn vị lệch nhau hàng trăm lần.
>
> Trang tự cập nhật mỗi 2 giây, nhưng **không tải lại**. Tôi đang bôi đen một dòng — nó không mất. Trang chỉ thay đúng con số nào đổi."

---

### Take 3 · Tạo sự cố thật — 60 giây · Bố cục B

**Màn hình:** Trái = status page (biểu đồ). Phải = terminal.

**Thao tác:**
```bash
python demo/loadtest.py
```

Để chạy ~90 giây. Quay **tua nhanh 4×** đoạn giữa lúc dựng, giữ tốc độ thật ở đoạn đường p95 bắt đầu vọt.

**Lời thoại:**
> "Bây giờ tôi tạo sự cố. Không chèn lỗi giả — tôi bắn tải tăng dần vào hệ thống, y như lưu lượng thật lúc cao điểm. Service thanh toán có connection pool 5 chỗ; tải lên đủ cao thì pool cạn, request phải xếp hàng, và độ trễ tăng.
>
> Nhìn biểu đồ bên trái — đường p95 đang leo."

---

### Take 4 · Agent phát hiện — 70 giây · Bố cục B

**Màn hình:** Trái = Prometheus (`prom-035.emmetech.id.vn`) chạy câu p95. Phải = log Agent.

**Thao tác:** Chỉ vào dòng log:
```
Mở war room KAN-xx cho service-thanh-toan (P1)
```

**Lời thoại:**
> "Agent quét Prometheus mỗi 10 giây. Nó không dùng Alertmanager — có ADR riêng giải thích: chúng tôi cần Agent **đọc được số**, không chỉ nhận một cái chuông báo.
>
> Nhưng vượt ngưỡng một nhịp thì chưa đủ. Phải vượt **liên tục ít nhất 30 giây** mới tính là sự cố — nếu không thì một cú tăng tải 5 giây cũng thành báo động, và người trực sẽ tắt hệ thống cảnh báo trong một tuần.
>
> Đây, nó vừa mở war room, tự xếp mức P1."

---

### Take 5 · Cảnh báo ra ngoài — 45 giây · Bố cục A

**Màn hình:** Lần lượt (cắt giữa các cảnh, đừng chuyển tab khi đang quay):
1. Jira board — phiếu mới xuất hiện
2. Hộp thư — email `🔴 [P1] service-thanh-toan — KAN-xx`
3. Link phòng họp Daily trong email

**Lời thoại:**
> "Cùng lúc, ba việc xảy ra: một phiếu Jira được mở, một email gửi tới toàn bộ người trực, và một phòng họp trực tuyến được tạo sẵn — để lúc cần gọi nhau thì đã có chỗ, không phải đi tìm."

---

### Take 6 · War room — bằng chứng · 90 giây · Bố cục A

**Màn hình:** War room, phiếu vừa mở. Cuộn từ trên xuống.

**Thao tác:**
1. Dải chỉ số (vitals) — dừng ở con số p95
2. Chỉ dòng `↳` bên dưới — tên metric gốc, giá trị thô
3. Mở khối **"Câu truy vấn dán vào Prometheus"** → bấm link → Prometheus mở ra với câu đã điền sẵn *(cắt sang cảnh Prometheus, rồi cắt về)*
4. Mở khối **"Log gốc đọc trực tiếp"** — dòng `pool_in_use=5 pool_size=5`

**Lời thoại:**
> "War room là màn hình của người trực. Nguyên tắc xuyên suốt: **dịch thêm, không dịch thay**. Dòng trên là câu tiếng Việt cho người mới; dòng `↳` bên dưới giữ nguyên tên metric gốc và số thô, để người rành kỹ thuật đào tiếp.
>
> Mọi con số đều kiểm chứng được. Bấm vào đây, nó mở thẳng Prometheus với đúng câu truy vấn và **đúng mốc thời gian sự cố** — vì chạy lại câu đó lúc này sẽ ra rỗng, sự cố đã qua rồi.
>
> Còn đây là log gốc, đọc trực tiếp từ container. `pool_in_use=5 pool_size=5` — pool đầy. Đây là bằng chứng chống lưng cho chẩn đoán, không phải suy đoán."

---

### Take 7 · Chẩn đoán — 80 giây · Bố cục A

**Màn hình:** War room, mục **Lập luận** và **Kết luận**.

**Thao tác:** Chỉ lần lượt: độ tin cậy → các chip bằng chứng → ghi chú deploy → khối "sự cố liên quan".

**Lời thoại:**
> "Chẩn đoán đi qua hai lớp. **Bộ luật** tính điểm tin cậy từ bằng chứng đo được — con số này do luật quyết, không phải LLM tự nhận, để nó không tự khen mình.
>
> **LLM** viết phần diễn giải và nối các mảnh lại: số đo, ghi chú deploy, và log. Ghi chú deploy là dữ liệu **phi cấu trúc** duy nhất Agent có — luật không đọc được đoạn văn, chỉ LLM đọc được rồi nối với số.
>
> Và đây: Agent tự nhận ra sự cố đã **lan sang** service đặt hàng, nối hai phiếu lại. Người trực không phải tự đoán hai sự cố này có liên quan hay không."

---

### Take 8 · Cổng phê duyệt — 100 giây · Bố cục C ⭐

> **Cảnh quan trọng nhất của cả video.** Nếu chỉ có thời gian làm kỹ một cảnh, làm cảnh này.

**Màn hình:** Trái = war room (mục Đề xuất). Phải = Jira phiếu đó.

**Thao tác:**
1. Bên trái: đọc đề xuất `increase_pool`, chỉ vào ô **"Đánh đổi cần cân nhắc"**
2. Chỉ vào dòng `Cần người duyệt: Bắt buộc · HITL`
3. Chỉ dòng chữ nhỏ cuối trang: *"Trang này chỉ hiển thị, không thi hành hành động nào"*
4. Bên phải: bấm chuyển phiếu sang **`Remediating`**
5. Quay lại bên trái, làm mới — hành động đã thi hành

**Lời thoại:**
> "Agent đề xuất nâng connection pool lên 20. Và nó tự nói ra **rủi ro của chính đề xuất đó**: mỗi kết nối thêm là thêm tải lên database; nếu database đã gần giới hạn thì việc này chỉ đổi một chỗ nghẽn lấy một chỗ nghẽn khác.
>
> Nhưng Agent **dừng ở đây**. Nó không có đường nào để tự đi tiếp. Nút duyệt không nằm trên war room — nó nằm trên Jira, và Agent phải đọc lịch sử thay đổi của Jira để xác minh **ai** đã duyệt.
>
> Tôi bấm duyệt... và giờ Agent mới thi hành.
>
> Điều đáng nói: nếu chính tài khoản Agent bấm nút này, hệ thống sẽ **từ chối**. Có test tự động khoá riêng luật đó — AI không được tự cho phép mình hành động."

---

### Take 9 · Sau khi sửa — 60 giây · Bố cục A

**Màn hình:** Jira phiếu đã Resolved.

**Thao tác:** Chỉ postmortem → 2 sub-task action item → email postmortem trong hộp thư.

**Lời thoại:**
> "Thi hành xong, Agent tự viết postmortem: chuyện gì đã xảy ra, vì sao, đã làm gì. Nó tạo luôn các đầu việc cần làm tiếp thành sub-task trên Jira, và gửi báo cáo cho cả đội.
>
> Sau đó nó **đo lại** — kiểm xem cách sửa có thật sự hiệu quả không, chứ không mặc định là xong."

---

### Take 10 · Hai nhánh còn lại — 55 giây · Bố cục A

Hai tình huống thực tế mà hệ thống phải xử lý được:

**10a — Không ai phản hồi.** Khởi động lại Agent với `AUTO_REMEDIATION_TIMEOUT_MINUTES=2`, tạo sự cố P3, để yên.

> "Nếu sự cố mức thấp mà không ai phản hồi sau một khoảng thời gian đã đặt trước, Agent tự thi hành — và ghi rõ lý do vào phiếu. Ngưỡng này cấu hình được, và **không áp dụng** cho sự cố nặng nếu không xác định được phiên bản để quay lui."

**10b — Người tự sửa tay.** Kéo một phiếu thẳng sang `Resolved`.

> "Còn nếu người trực không đồng ý với đề xuất và tự sửa bằng tay, Agent vẫn sinh postmortem — nhưng đi nhánh khác, ghi rõ là 'người tự sửa', và không thi hành gì cả."

---

### Take 11 · Đo lường — 55 giây · Bố cục A

**Màn hình:** `eval/RESULTS-2026-08-21.md`.

**Lời thoại:**
> "Cuối cùng: chúng tôi **đo** chứ không tự nhận. Bộ 50 ca kiểm, trong đó 25 ca là nhiễu cố ý — tải cao nhưng không phải sự cố — để xem Agent có báo bừa không.
>
> Recall 84%, Precision gần 81%, MCC +0,64. Và chúng tôi ghi cả chỉ số **xấu đi**: tỷ lệ xếp đúng mức độ giảm 8 điểm so với mốc trước. Một bảng đo mà mọi con số đều đẹp là bảng đo đáng nghi."

---

### Take 12 · Kết — 30 giây · Bố cục A

**Màn hình:** Quay về status page, 4 dịch vụ xanh trở lại.

**Lời thoại:**
> "Từ lúc sự cố xảy ra đến lúc có chẩn đoán kèm bằng chứng và đề xuất cụ thể: khoảng một phút, không cần ai thức dậy.
>
> Nhưng quyết định cuối cùng vẫn là của con người. Đó không phải giới hạn kỹ thuật — đó là lựa chọn thiết kế."

---

## Bảng phủ chức năng — soát trước khi dựng phim

| # | Chức năng | Cảnh |
|---|---|---|
| 1 | Status page công khai, 4 dịch vụ | 0, 2, 12 |
| 2 | Biểu đồ Prometheus 3 chỉ số / 3 trục | 2, 3 |
| 3 | Tự cập nhật kiểu SPA, giữ thao tác người dùng | 2 |
| 4 | Sự cố THẬT bằng tải tăng dần | 3 |
| 5 | Phát hiện qua PromQL + ngưỡng + 30s liên tục | 4 |
| 6 | Tự xếp mức độ P1–P4 | 4 |
| 7 | Mở phiếu Jira tự động | 5 |
| 8 | Email cảnh báo người trực | 5 |
| 9 | Tạo phòng họp tự động | 5 |
| 10 | War room hai tầng (dịch thêm, không dịch thay) | 6 |
| 11 | PromQL kiểm chứng được kèm mốc thời gian | 6 |
| 12 | Đọc log container trực tiếp | 6 |
| 13 | Bộ luật tính độ tin cậy | 7 |
| 14 | LLM diễn giải + nối bằng chứng | 7 |
| 15 | Đối chiếu lịch sử deploy | 7 |
| 16 | Nối sự cố lan truyền | 7 |
| 17 | Đề xuất khắc phục + runbook + rủi ro | 8 |
| 18 | **Cổng phê duyệt HITL** | 8 |
| 19 | Chặn Agent tự duyệt | 8 |
| 20 | Thi hành thật sau khi duyệt | 8 |
| 21 | Postmortem tự sinh + sub-task | 9 |
| 22 | Đo lại sau khi sửa | 9 |
| 23 | Tự thi hành khi không ai phản hồi | 10a |
| 24 | Nhánh người tự sửa tay | 10b |
| 25 | Kiến trúc tự host qua Cloudflare Tunnel | 1 |
| 26 | Bảng đo lường 11 chỉ số | 11 |

---

## Mẹo dựng phim

**Tua nhanh chỗ chờ.** Loadtest 90 giây, Agent quét 10 giây — tua 4× và để đồng hồ góc màn hình cho người xem biết đang tua.

**Zoom vào con số.** Lúc đọc "p95 = 1.86 giây", phóng to đúng chỗ đó. Người xem trên điện thoại không đọc nổi chữ 12px.

**Cắt ngay khi chuyển màn hình.** Đừng quay cảnh rê chuột lên thanh tab.

**Giữ chuột yên khi đang nói.** Chuột chạy lung tung làm người xem không biết nhìn đâu.

**Quay lời thoại riêng.** Thu tiếng sau, ghép vào hình. Đọc trong lúc thao tác thì hay vấp, mà vấp là phải quay lại cả cảnh.

**Đừng che tên miền thật.** `035.emmetech.id.vn` chạy được thật là một điểm cộng — nó chứng minh đây không phải bản chạy localhost.

---

## Nếu chỉ có 3 phút

Cắt còn 4 cảnh: **0 → 3 → 8 → 11**.

Mở đầu, tạo sự cố thật, cổng phê duyệt, số đo. Bỏ hết phần còn lại. Cảnh 8 là thứ phân biệt dự án này với một con bot gọi API.
