# ================================================================
# GENERATOR V3.1 - GHÉP CÂU THEO THÀNH PHẦN (COMPOSITIONAL) + EXTREME TYPO
# ================================================================
import random
import re
import unicodedata
import collections

# ---------------------------------------------------------------
# 0. CẤU HÌNH (chỉnh tỉ lệ ở đây)
# ---------------------------------------------------------------
CFG = {
    "p_kind": 0.5,            # địa điểm có kind/anchor
    "p_via": 0.65,             # câu có điểm lấy hàng (via)
    "p_via_composite": 0.10,   # via nằm chung 1 câu với goal
    "p_trap_rel": 0.40,        # câu lừa mô tả địa điểm kèm kind/anchor
    "p_extra_aff": 0.40,       # thêm câu "đi ngang qua" (không dừng)
    "p_extra_neg": 0.50,       # thêm câu phủ định phụ
    "p_neg_goal": 0.80,        # bucket Neg: goal-unit tự mang phủ định
    "p_filler_pre": 0.18,
    "p_filler_post": 0.22,
    "p_filler_info": 0.20,
    "p_attr_combined": 0.40,   # urgent+fragile gộp 1 câu
    "p_omit_no": 0.12,         # label 'no' nhưng không nhắc tới (thực tế hay vậy)
    "p_attr_hard": 0.30,       # câu attr khó (nhắc tới nhưng của đơn khác...)
    "p_attr_para": 0.35,       # fragile nói bằng từ KHÔNG nằm trong BANK['fragile']
    "use_para_attr": True,     # tắt nếu guideline gán nhãn fragile của bạn khác
    "p_chat": 0.3,            # văn phong chat: viết thường, ko/đc/vs...
    "p_terse": 0.20,           # văn phong ghi chú rời rạc "a | b | c"
    "p_lower": 0.15,
    "p_sentence_typo": 0.50,   # (bucket Typo) typo ở phần ngữ cảnh
    "p_alias_typo": 0.5,      # (bucket Typo) typo ở tên địa điểm
    "p_via_trick": 0.40,       # via là câu đánh lừa (hôm qua/đơn khác/sửa lại...)
    "p_attr_dneg": 0.07, "p_attr_sarc": 0.05,
    "use_sarcasm": True, "use_double_neg": True, "use_hypo": True,
}

PH = {"G": "@0@", "V": "@1@", "TV": "@2@",
      "T1": "@3@", "T2": "@4@", "T3": "@5@", "T4": "@6@",
      "GW": "@7@", "GB": "@8@", "AW": "@9@", "KT": "@10@", 
      "KO": "@11@", "AT": "@12@", "TG": "@13@"}
PH_IDX = {"G": 0, "V": 1, "TV": 2, "T1": 3, "T2": 4, "T3": 5, "T4": 6}

PERSONAS = [
    ("mình", "bạn", False, False), ("mình", "bạn", True, False),
    ("tớ", "cậu", False, False), ("tui", "anh", True, False),
    ("tui", "chị", True, False), ("em", "anh", False, True),
    ("em", "chị", False, True), ("em", "bác", True, True),
    ("tôi", "anh", False, True), ("tôi", "chị", False, True),
    ("anh", "em", False, False), ("chị", "em", False, False),
    ("bên mình", "bạn", False, False), ("shop", "anh shipper", False, True),
    ("shop", "bạn shipper", True, False), ("bên em", "anh tài xế", False, True),
]

NAMES = ["chị Lan", "anh Nam", "bạn Minh", "cô Hoa", "chú Tùng", "em Linh",
         "anh Hùng", "chị Mai", "bạn Khánh", "bác Dũng", "anh Phúc", "chị Thảo"]

TAIL_COMMON = ["với", "giúp {me}", "giúp {me} với", "nhớ nhé"]
TAIL_NORTH = ["nhé", "nhá"]
TAIL_SOUTH = ["nha", "nghen", "hen", "dùm {me}", "giùm {me}", "nhen"]
TAIL_POLITE = ["ạ", "nhé ạ", "với ạ"]
TAIL_END_ONLY = ["được không", "được chứ"]

OBJ_PRON = ["đơn này", "món này", "hàng này", "kiện hàng này", "gói này",
            "đơn hàng này", "đồ này", "nó"]

GIVE_VERBS = {
    "giao": ["tới", "đến", "ở", "tại", "về", "sang"],
    "chuyển": ["tới", "đến", "về", "sang"],
    "đưa": ["tới", "đến", "về", "sang"],
    "mang": ["tới", "đến", "về", "sang"],
    "gửi": ["tới", "đến", "về", "sang"],
    "vận chuyển": ["tới", "đến", "về"],
    "ship": ["tới", "đến", "về"],
    "chở": ["tới", "đến", "về"],
    "đem": ["tới", "đến", "về", "sang"],
    "để lại": ["ở", "tại"],
    "bàn giao": ["tại", "ở", "tới"],
}

GS_FAMS = ["imp", "nho", "you", "want", "pass", "topic", "formal",
           "nominal", "recv", "frag", "go"]

NOMINAL = ["điểm giao: {G}", "điểm giao là {G}", "địa chỉ giao: {G}",
           "địa chỉ giao hàng là {G}", "điểm đến: {G}",
           "điểm đến cuối cùng là {G}", "nơi giao hàng: {G}",
           "chỗ giao là {G}", "đích đến của đơn này là {G}",
           "địa chỉ người nhận: {G}", "giao hàng tại: {G}"]
RECV = ["người nhận đang đợi sẵn ở {G}", "khách đang chờ ở {G}",
        "người nhận ở {G}", "khách ở {G} nhé",
        "người nhận đang đứng chờ tại {G}", "bên nhận trực tại {G}",
        "có người chờ nhận hàng ở {G}"]
FRAG = ["{G} {t}", "tới {G} {t}", "→ {G}", "ship {G} {t}", "giao {G}",
        "đi {G} {t}", "{G} nhé", "đến {G} {t}"]
GO = ["đơn này đi {G}", "chuyến này chạy tới {G}",
      "chuyến này đích đến là {G}", "đơn đi {G} {t}",
      "chạy {G} giúp {me}", "đích của đơn này là {G}"]

PICK_PATTERNS = [
    "lấy {o} ở {V}", "lấy {o} tại {V}", "lấy {o} từ {V}", "ghé {V} lấy {o}",
    "qua {V} lấy {o}", "tạt qua {V} lấy {o}", "đến {V} lấy {o}",
    "chạy qua {V} lấy {o}", "nhận {o} tại {V}", "nhận {o} từ {V}",
    "ghé {V} nhận {o}", "gom {o} ở {V}", "bốc {o} ở {V}",
    "dừng ở {V} lấy {o}", "pick {o} ở {V}", "qua {V} bốc {o}",
    "ghé {V} gom {o}",
]
STOP_PATTERNS = ["ghé {V} một lát", "dừng ở {V} một chút", "tạt qua {V} trước",
                 "có một điểm dừng ở {V}", "dừng chân ở {V} trước đã"]
PICK_OBJ = ["hàng", "đồ", "đơn", "đơn hàng", "kiện hàng", "{item}",
            "món {item}", "đơn {item}", "món này", "đơn này", ""]
PS_FRAMES = [
    "{PV} {tail}", "nhờ {you} {PV} {tail}", "{You} {PV} {tail}",
    "trước tiên {PV}", "đầu tiên {PV} {tail}", "{me} cần {you} {PV}",
    "điểm lấy hàng: {V}", "nơi lấy hàng là {V}",
    "điểm dừng đầu tiên: {V}", "{o} đang để ở {V}", "hàng đang nằm ở {V}",
    "{o} gửi sẵn ở {V}", "phiền {you} {PV} {tail}", "vui lòng {PV}",
    "{o} hiện ở {V}, qua đó lấy giúp {me}",
]

CORR_SOFT = ["à nhầm", "nhầm rồi", "ủa lộn", "lộn rồi", "xin lỗi, {me} nói nhầm",
             "khoan, sửa lại", "đính chính một chút", "{me} sửa lại",
             "ý lộn", "viết nhầm", "gõ nhầm", "oops", "sorry nhầm",
             "để {me} nói lại", "nói lại cho đúng", "khoan đã"]
CORR_NEG = ["à không", "bỏ câu trước nhé", "quên chỗ vừa nói đi",
            "đừng nghe câu trước", "khỏi làm theo câu trên"]

REDIR_FORMS = ["{G} mới đúng", "là {G} cơ", "tới {G} nhé", "giao {G} mới phải",
               "ý {me} là {G}", "{G} mới là chỗ nhận", "phải là {G}",
               "chuyển sang {G}", "đổi thành {G}", "đổi qua {G}",
               "sửa thành {G}", "{GV}", "{GV}", "thật ra là {G}",
               "đúng ra là {G}"]

WHY = ["đang đóng cửa", "đã hết giờ làm việc", "đang sửa chữa",
       "đang bị rào chắn", "đang ngập nước", "đang bảo trì", "vừa khóa cổng",
       "đang phong tỏa", "vừa bị cắt điện", "đang vắng người",
       "đã đóng cổng từ chiều"]
CONV = ["tiện đường hơn", "dễ đi hơn", "đỡ kẹt xe hơn", "rẻ phí ship hơn",
        "có chỗ đậu xe hơn", "vào dễ hơn"]

NOT_T = ["chứ không phải {T}", "không phải {T} nhé", "đừng nhầm sang {T}",
         "{T} thì thôi", "khỏi qua {T}", "{T} là sai chỗ", "đừng đưa tới {T}",
         "{T} không liên quan", "tránh {T} nhé", "{T} thì bỏ qua"]
NOT_LEAD = ["không phải {T}", "đừng giao ở {T}", "bỏ {T} đi", "{T} thì không",
            "khỏi qua {T}", "đừng để hàng ở {T}", "tuyệt đối không giao ở {T}",
            "đừng mang tới {T}", "{T} sai rồi", "tránh {T} giúp {me}",
            "{T} không phải chỗ nhận", "không giao ở {T} nhé",
            "đừng nhầm với {T}"]

QA_Q = ["giao ở {T} đúng không?", "tới {T} phải không?", "chỗ nhận là {T} hả?",
        "{T} là điểm giao đúng không?", "giao {T} nhỉ?", "là {T} đúng không ạ?",
        "{T} nhé?", "đơn này đi {T} hả?"]
QA_A = ["không, {GS}", "không phải, {GS}", "sai rồi, {GS}", "không nha, {GS}",
        "không đâu, {GS}", "nhầm rồi, {GS}", "không, {G} cơ",
        "không phải {T}, là {G}", "chưa đúng, {GS}", "ủa không, {GS}",
        "{T} là sai, {GS}"]
QA_REV = ["{GS}. {T} hả? Không phải nhé", "{GS} — còn {T} á? không phải nha",
          "{GS}, {T} thì không nha", "{GS}. {T} á? Không đúng đâu"]

COMPOSITE = [
    "{PV}, rồi {GV}", "{PV}, sau đó {GV}", "sau khi {PV} xong thì {GV}",
    "{PV}; xong {GV}", "{GS}, nhưng trước đó {PV}", "trước khi {GV} nhớ {PV}",
    "việc đầu tiên: {PV}. Việc cuối: {GV}", "{PV} trước rồi mới {GV}",
    "từ {V}, {GV}", "{G} là nơi nhận cuối, còn {V} là chỗ lấy hàng",
    "chặng 1: {PV}. Chặng 2: {GV}", "{GS} (nhớ {PV} trước)",
    "{PV}, rồi {GV} {tail}",
]

GOAL_TPL = {
    "self_correct": [
        "{GV_T}, {corr}, {REDIR}", "{GV_T}... {corr}, {REDIR}",
        "{GS_T}. {Corr}, {REDIR}", "{T}... {corr}, {REDIR}",
        "{T} — {corr}, {REDIR}", "lúc nãy {me} nói {T} là nói nhầm, {REDIR}",
        "lúc đầu {me} bảo {T}, {corr}, {REDIR}",
        "{Corr} nhé, {T} là {me} gõ nhầm, {REDIR}",
        "{GS}. {T} ở tin trước là {me} nhập nhầm",
        "{GS}. Còn {T} lúc nãy là nhầm, quên nó đi",
        "{T} nhầm, {REDIR}", "{T}, ý lộn, {REDIR}",
        "gõ nhầm địa chỉ rồi: {T} sai, {REDIR}",
        "{G} mới đúng nha, lúc nãy ghi {T} là gõ nhầm",
        "{GS}. Vừa rồi {me} ghi {T} là nhầm",
        "{GV}, còn {T} là nhập nhầm ở tin trước",
    ],
    "old_info": [
        "lần trước {GV_T0}, lần này {REDIR}",
        "địa chỉ cũ là {T}, địa chỉ mới là {G}",
        "khách vừa chuyển từ {T} sang {G}, nên {GV}",
        "hôm qua {GV_T0}; hôm nay {GV}",
        "đơn hôm trước ở {T}, còn hôm nay {GV}",
        "{T} là chỗ cũ rồi, giờ thì {REDIR}",
        "ghi chú cũ ghi {T}, thông tin mới nhất là {G}",
        "trước đây khách nhận ở {T}, hiện tại {REDIR}",
        "lúc đặt hàng khách chọn {T}, nhưng sau đó đổi sang {G}",
        "sáng nay {me} định gửi tới {T}, giờ thì {REDIR}",
        "{GS}. {T} chỉ là địa chỉ cũ",
        "từ giờ {GV}; {T} là chuyện của tuần trước",
        "đổi địa chỉ rồi nhé: từ {T} sang {G}",
        "{G} là địa chỉ mới, {T} là địa chỉ cũ",
        "{GS} (khách đã dọn khỏi {T})",
        "{GV} nhé, {T} là chỗ cũ rồi",
        "giờ {GV}; địa chỉ cũ ({T}) bỏ đi",
    ],
    "unavailable": [
        "{T} {why}, nên {GV}", "vì {T} {why} nên {GV}",
        "{T} {why} rồi, {REDIR}", "{GS}, vì {T} {why}",
        "chỗ {T} {why}, {me} đổi sang {G}", "{T} {why} — {GV}",
        "nghe nói {T} {why}, nên cứ {GV}",
        "{T} {why}; phương án thay thế là {G}",
        "{GS} vì {T} {why}",
        "{GV} nhé — {T} {why} rồi",
        "đổi sang {G} thay cho {T}, vì chỗ đó {why}",
    ],
    "preference_override": [
        "{T} {conv}, nhưng cứ {GV}", "dù {T} {conv} thì vẫn {GV}",
        "{T} {conv} đấy, nhưng người nhận chỉ ở {G}",
        "{T} {conv} thật, song điểm nhận là {G}", "{GS}, dù {T} {conv}",
        "tuy {T} {conv} nhưng đích đến vẫn là {G}",
        "mặc dù {T} {conv}, cứ {GV} giúp {me}",
    ],
    "other_order": [
        "đơn của {name} thì {GV_T0}, còn đơn này {GV}",
        "{GS} (đơn của {name} thì ở {T})",
        "hai đơn đi hai nơi: đơn của {name} tới {T}, đơn này tới {G}",
        "đơn kia {GV_T0}, đơn này {GV}",
        "trong cùng chuyến có đơn đi {T}, riêng đơn này {GV}",
        "{name} nhận ở {T}; riêng đơn này thì {GV}",
        "đơn này đi {G}; đơn của {name} đi {T}, hai đơn khác nhau",
        "{GV}; còn đơn của {name} thì đi {T}",
    ],
    "reject_goal": [
        "{GS}, {not_T}", "{GS}; {not_T}", "{notT_lead}. {GS}",
        "{notT_lead}, {GS}", "{GV_C}", "{GV_C} {tail}",
        "giữa {T} với {G}, {GV}",
        "có hai chỗ {T} và {G}; {G} mới là chỗ nhận, {T} bỏ qua",
        "đừng lẫn {T} với {G}: {GV}", "chỉ {G} thôi, {T} thì không",
        "{G} chứ không phải {T}, nhớ giúp {me}",
        "đừng đưa nhầm qua {T}, {GS}", "{T} là chỗ khác, {GS}",
    ],
    "note_wrong": [
        "ghi chú ghi {T} là ghi sai, {GS}",
        "app đang hiện {T} nhưng đó là địa chỉ lỗi, {GS}",
        "đừng làm theo địa chỉ trên hệ thống ({T}); {GS}",
        "địa chỉ trên đơn ({T}) không còn đúng, {GS}",
        "tin nhắn trước nhắc {T}, bỏ qua tin đó, {GS}",
        "người ta hay nhầm sang {T}, nhưng {GV}",
        "thông tin {T} lúc nãy là sai, {GS}",
        "khách ghi {T} nhưng thực tế không nhận ở đó; {GS}",
        "bản đồ đang chỉ {T}, đừng đi theo; {GS}",
        "đừng tin hệ thống, nó ghi {T} là sai. {GS}",
        "{GS}; địa chỉ {T} trên hệ thống là sai",
        "{GS}. Dòng ghi {T} trong ghi chú là lỗi, bỏ qua giúp {me}",
        "{GV}, đừng theo địa chỉ {T} trong ghi chú",
        "{GS}. Chỗ ghi {T} trên hệ thống là sai",
    ],
    "reject_multi": [
        "không giao ở {T1}, cũng không phải {T2}; {GS}",
        "{T1} với {T2} đều không phải điểm nhận, {GS}",
        "loại {T1} và {T2} khỏi danh sách; {GS}",
        "chỉ {G} thôi, {T1} hay {T2} đều bỏ qua",
        "cả {T1} lẫn {T2} đều sai, {GS}",
        "{T1}, {T2}, {T3} đều không phải; {GS}",
        "{GS} — không phải {T1}, không phải {T2}",
        "{GS}, còn {T1} hay {T2} thì khỏi",
        "trong mấy chỗ {T1}, {T2}, {G}, chỉ {G} là đúng",
    ],
    
    # ---------------- 10 KIỂU ĐÁNH LỪA ĐỊA ĐIỂM MỚI ----------------
    "future_cond": [
        "khi nào {T} mở cửa thì mới qua, giờ cứ {GV}",
        "đợi {T} gọi thì lâu lắm, {GV} đi",
        "chừng nào {T} yêu cầu thì giao, nay tạm thời {GV}",
        "bao giờ {T} hết tắc đường hẵng tính, giờ chạy qua {G} trước",
        "giả dụ {T} báo thì đi sau, chuyến này {GV}",
    ],
    "transfer_person": [
        "khách ở {T} vừa gọi báo chạy qua {G} nhận luôn, {GV}",
        "người nhận từ {T} đã di chuyển sang {G}, {GV} nhé",
        "khách không đợi ở {T} nữa đâu, {GV}",
        "bên {T} chuyển ca rồi, người nhận đang ở {G}, {GV}",
    ],
    "wait_vs_deliver": [
        "{me} đang đứng chờ ở {T}, nhưng {you} {GV} nhé",
        "tuy {me} làm ở {T}, nhưng kiện này {GV}",
        "đừng mang qua chỗ {me} ở {T}, {GV} cho khách",
        "xe của {me} đang hỏng ở {T}, {you} cứ {GV} đi",
    ],
    "past_completed": [
        "cái đơn ở {T} nãy giao xong rồi, giờ tập trung {GV}",
        "giao {T} là chuyện ban sáng, chiều nay {GV}",
        "chuyến trước {me} đã tạt qua {T} rồi, chuyến này {GV}",
        "{T} hoàn thành rồi, giờ chỉ còn {GV} nữa thôi",
    ],
    "swap_package": [
        "gói đi {T} bị nhầm rồi, để lại đi, gói này {GV}",
        "không mang gói của {T} theo, chỉ {GV} thôi nhé",
        "nhân viên đưa nhầm kiện của {T}, trả lại và {GV}",
        "kiện {T} đang bị rách, giao gói lành tới {G}",
    ],
    "via_not_goal": [
        "{T} là chỗ lấy hàng của người khác, còn đơn này {GV}",
        "chỗ {T} chỉ tiện đường thôi, đích phải là {G}",
        "đừng tưởng cứ đi ngang {T} là giao, đích đến là {G}",
        "ghé {T} chỉ để đổ xăng thôi, {GV}",
    ],
    "out_of_bounds": [
        "{T} không cho shipper vào đâu, {GV}",
        "xe không vào được {T}, nên {GV}",
        "bảo vệ ở {T} đuổi rồi, vòng qua {G} giùm",
        "{T} nay cấm xe máy, chốt lại là {GV}",
    ],
    "canceled_order": [
        "đơn đi {T} khách hủy rồi, chạy thẳng {GV}",
        "hủy chuyến {T} nha, {GV} thôi",
        "bom hàng ở {T} rồi, mang qua {G} đi",
        "đơn {T} khách không nghe máy, tập trung đơn {G}",
    ],
    "ignore_note": [
        "kệ cái dòng ghi chú {T} đi, {GS}",
        "đừng quan tâm tin nhắn nhắc {T}, {GS}",
        "bỏ qua tờ giấy note dán trên hộp ghi {T}, {GS}",
        "hệ thống lỗi hiển thị {T}, cứ lơ đi, {GS}",
    ],
    "misdirected": [
        "bảo vệ hay chỉ nhầm ra {T}, thực ra {GS}",
        "người ta bảo {T} là sai đấy, {GV}",
        "đứa nào xúi đi {T} là lừa đó, {GS}",
        "đừng nghe mấy người đi đường chỉ ra {T}, {GS}",
    ]
}

AFF_W = {"plain": 3.0, "self_correct": 2.0, "old_info": 1.5, "unavailable": 1.5,
         "preference_override": 1.5, "other_order": 1.5,
         "future_cond": 1.5, "transfer_person": 1.5, "wait_vs_deliver": 1.5, 
         "past_completed": 1.5, "swap_package": 1.5, "via_not_goal": 1.5, 
         "out_of_bounds": 1.5, "canceled_order": 1.5}
NEG_W = {"reject_goal": 3.0, "qa_reject": 1.5, "note_wrong": 1.5,
         "reject_multi": 1.5, "ignore_note": 1.5, "misdirected": 1.5}

EXTRA_TPL = {
    "route_pass": [
        "đường đi sẽ ngang {T}, cứ chạy thẳng", "chạy ngang {T} là thấy",
        "{T} chỉ là mốc để định hướng", "lấy {T} làm mốc rồi đi tiếp",
        "đi ngang qua {T} sẽ thấy", "{T} nằm trên đường đi thôi",
    ],
    "route_no_stop": [
        "đi ngang {T} thôi, đừng dừng", "chạy qua {T} nhưng không cần ghé",
        "{T} chỉ để định hướng, không dừng ở đó",
        "không cần ghé {T}, chỉ đi ngang", "{T} chỉ là điểm đi ngang, không dừng",
        "lướt qua {T} thôi nhé, không vào",
    ],
    "no_stop": [
        "không cần ghé đâu hết, đi thẳng", "đi thẳng, đừng ghé {T}",
        "khỏi qua {T} lấy gì, hàng có sẵn trên xe rồi",
        "hàng có sẵn rồi, không cần qua {T} lấy",
        "không cần lấy hàng ở {T}, đi thẳng",
        "không có điểm dừng trung gian nào, kể cả {T}",
        "đi một mạch, không ghé {T}",
        "không phải qua {T} đâu, hàng {you} đã cầm rồi",
    ],
    "reject_via": [
        "lấy hàng ở {V}, đừng lấy ở {TV}", "{PS}, không phải {TV}",
        "nhận hàng tại {V} chứ không phải {TV}", "{TV} khỏi ghé, {PS}",
        "không lấy hàng ở {TV} nữa, {PS}",
        "điểm lấy hàng là {V}; {TV} là chỗ cũ, bỏ qua",
        "đừng ghé {TV}; {PV}", "{TV} thì thôi, qua {V} lấy hàng",
        "hàng không nằm ở {TV} mà ở {V}",
    ],
}

KIND_TYPES = {"pos_correct", "pos_neg_kind"}
ANCHOR_TYPES = {"pos_neg_anchor", "anchor_reject"}

REF_FIRST = ["cái đầu", "cái thứ nhất", "chỗ đầu tiên", "chỗ nhắc trước", "cái nói trước"]
REF_SECOND = ["cái thứ hai", "cái sau", "chỗ thứ hai", "chỗ nhắc sau", "cái nói sau",
              "chỗ vừa nhắc sau cùng"]
COREF_LEAD = ["{a} và {b} đều ở gần đây", "{a} với {b} đều tiện đường",
              "có hai chỗ: {a} và {b}", "{a}, {b}: cả hai đều giao được",
              "nhắc hai chỗ {a} và {b}", "hai chỗ {a} và {b} đều nhận hàng"]
PERSONS = ["cô lao công", "bác bảo vệ", "chị lễ tân", "anh trực ban", "bạn cùng phòng",
           "thầy giám thị", "cô quản lý", "chú bảo vệ", "em trực quầy"]
TIME_MOD = ["giờ nghỉ trưa", "sau giờ học", "vào buổi tối", "lúc tan ca"]

POS_NEG_KIND_ANCHOR = ["{GS}, chứ không {KO} {AT}", "{GS}, đâu có {KO} {AT}",
                       "{GS}; chỗ đó không {KO} {AT} đâu", "{GS} — nhớ là không {KO} {AT}"]
POS_NEG_KIND_PLAIN = ["{GS}, chứ không phải {GB} {KO}", "{GS} (không phải {KO})",
                      "{GS}; {KO} thì là chỗ khác", "đừng nhầm sang {GB} {KO}: {GS}"]

GOAL_TPL.update({
    "temporal": [
        "hôm qua đã {GV_T0} rồi, hôm nay {REDIR}",
        "hôm qua {GV_T0} xong rồi; hôm nay {GV}",
        "đơn hôm qua đã tới {T} rồi nhé, đơn hôm nay thì {GV}",
        "hôm nay thì {GV}, ngày mai mới tính tới {T}",
        "tuần trước {GV_T0}, tuần này {REDIR}",
        "lần sau {GV_T0}, còn lần này {REDIR}",
        "sau này có thể {GV_T0}, còn bây giờ {GV}",
        "đã {GV_T0} từ chiều qua, giờ {REDIR}",
        "chiều nay {GV_T0} xong rồi, đơn mới này {GV}",
        "{T} là chuyện của hôm kia, hôm nay {REDIR}",
        "{GS}. Chuyện giao ở {T} là của hôm qua",
        "hôm kia {GV_T0}, hôm qua cũng vậy, nhưng hôm nay {GV}",
    ],
    "hypo": [
        "nếu {G} đóng cửa thì mới qua {T}, nhưng {GB} đang mở nên cứ {GV}",
        "{G} mở thì giao ở đó; còn nếu {GB} đóng mới tính tới {T}. Hiện {GB} đang mở",
        "phương án dự phòng là {T}, nhưng chưa cần dùng vì {GB} vẫn nhận hàng bình thường, {GV}",
        "chỉ khi {GB} đóng cửa mới chuyển sang {T}, còn bây giờ {GV}",
        "nếu {T} còn chỗ thì giao ở {T}, nhưng {T} hết chỗ rồi nên {REDIR}",
        "giả sử {T} nhận được thì đã giao ở đó, tiếc là {T} đang đóng nên {REDIR}",
        "kế hoạch A là {T}, nhưng kế hoạch A bị hủy; chốt kế hoạch B: {G}",
        "nếu {T} có người nhận thì {me} đã chọn {T}, nhưng vắng người nên {REDIR}",
    ],
    "pickup_goal": [
        "khách sẽ tự qua lấy ở {G}", "để khách ghé lấy tại {G}",
        "gửi lại ở {G} cho khách tự lấy",
        "người nhận tự đến lấy ở {G}, {you} chỉ cần đưa tới đó",
        "{o} để ở {G}, người nhận sẽ qua lấy",
        "bên nhận tự lấy tại {G}", "{name} tự qua {G} lấy",
    ],
    "pos_correct": [
        "{GV_W}, {corr}, {REDIR}", "{GV_W}... {corr}, {REDIR}",
        "{GS}. {GW} là {me} nói nhầm", "{GW}? {Corr}, {G} mới đúng",
        "{GS}; lúc nãy {me} ghi {GW} là gõ nhầm",
        "vừa rồi {me} bảo {GW}, {corr}: {REDIR}", "{GW} — {corr}, {REDIR}",
    ],
    "pos_neg_anchor": [
        "{GS}, chứ không phải chỗ {KT} {AW}", "{GS} (không {KT} {AW} nhé)",
        "{GS}; {KT} {AW} là chỗ khác", "đừng nhầm với chỗ {KT} {AW}: {GS}",
        "{GS}, {me} không nói chỗ {KT} {AW}",
    ],
    "anchor_reject": [
        "{GS}, chứ không phải {AT}", "{GS}; {AT} chỉ là mốc, không phải chỗ nhận",
        "đừng nhầm {AT} với chỗ nhận: {GS}", "{AT} chỉ để định vị thôi, {GV}",
        "{AT} là mốc thôi nhé, {GS}", "đích không phải {AT} đâu, {GS}",
    ],
    "anchor_trap": [
        "{GS}, không phải {TG}", "{GS}; còn {TG} là chỗ khác",
        "đừng nhầm với {TG}: {GS}", "{TG} thì thôi, {GS}",
    ],
    "double_neg": [
        "không phải là không được ghé {T}, nhưng đích thật sự là {G}",
        "{T} thì không phải không đi được, mà đích đến là {G}",
        "chẳng phải {me} không muốn giao ở {T}, chỉ là đích cuối vẫn là {G}",
        "đâu phải {T} không nhận hàng, nhưng đơn này giao {G}",
        "không thể nói là không cần tới {G}, còn {T} thì khỏi",
        "đâu phải không cần giao tới {G}, đừng nhầm sang {T}",
        "không phải {T} không tiện, song điểm nhận là {G}",
        "chẳng phải {T} không đúng đường, mà là phải {GV}",
    ],
    "sarcasm": [
        "giỏi thì cứ mang ra {T} mà vứt, {me} đang đợi ở {G} cơ mà",
        "ừ cứ giao ở {T} đi, rồi {me} đứng ở {G} chờ hoài",
        "{T} á? thôi đi, {GS}", "chắc là {T} nhỉ? đùa thôi, {GS}",
        "ừ thì cứ ra {T} đi, còn {me} chờ ở {G} nè",
        "tuyệt, lại đưa nhầm ra {T}, {REDIR} mới đúng chứ",
    ],
})

AFF_W.update({"temporal": 1.8, "hypo": 1.2, "coref": 1.3, "pickup_goal": 1.0,
              "recipient": 1.0, "pos_correct": 1.4})
NEG_W.update({"double_neg": 1.0, "sarcasm": 0.8, "coref_neg": 1.0, "pos_neg_anchor": 1.2,
              "pos_neg_kind": 1.2, "anchor_reject": 1.0, "anchor_trap": 1.0})

EXTRA_TPL["landmarks"] = [
    "dọc đường có {T3}, {T4}, chỉ để tham khảo", "đường đi thường qua {T3} rồi {T4}, đó là mốc thôi",
    "nhìn thấy {T3} rồi {T4} là gần tới", "mấy chỗ như {T3}, {T4} chỉ là cột mốc dọc đường",
]
EXTRA_TPL["no_stop_aff"] = [
    "hôm qua phải ghé {T} lấy hàng, hôm nay hàng có sẵn trên xe rồi",
    "đơn của {name} lấy ở {T}, còn đơn này hàng đã ở trên xe",
    "{T} là chỗ lấy hàng của đơn kia, đơn này đi thẳng",
]
EXTRA_TPL["reject_via"] += [
    "không phải là không ghé {TV}, nhưng chỗ lấy hàng là {V}",
    "đâu phải {TV} không có hàng, nhưng đơn này {PV}",
]
VIA_TRICK_AFF = [
    "hôm qua {PV_T}; hôm nay {PV}", "đơn của {name} lấy ở {TV}, còn đơn này {PV}",
    "{TV} {why}, nên {PV}", "{PV_T}... {corr}, {PV}",
    "lần trước lấy ở {TV}, lần này {PV}", "ghi chú cũ ghi lấy ở {TV}, thông tin mới là {V}",
    "hôm qua đã lấy ở {TV} rồi, hôm nay qua {V} lấy",
    "{V} mới là chỗ có hàng hôm nay, {TV} là của hôm qua",
    "nếu {TV} hết hàng thì mới qua {V}, mà {TV} đã hết rồi nên {PV}",
]

ATTR = {
    ("urgent", "yes", "std"): [
        "đơn này gấp", "gấp lắm", "gấp nhé", "đơn gấp", "cần giao gấp",
        "{me} đang cần gấp", "làm nhanh giúp {me}", "ưu tiên đơn này trước",
        "đơn này ưu tiên số một", "khách đang đứng chờ rồi",
        "khách chờ lâu rồi", "cần có trong {n} phút nữa",
        "trong vòng {n} phút phải tới", "càng sớm càng tốt",
        "giao ASAP nha", "đơn hỏa tốc", "đơn khẩn", "sát giờ lắm rồi",
        "đi liền giúp {me}", "chạy nhanh giúp {me}",
        "trễ là khách hủy đơn đó",
    ],
    ("urgent", "no", "std"): [
        "đơn này không gấp", "không gấp đâu", "chưa cần gấp", "không cần vội",
        "từ từ cũng được", "cứ thong thả", "khi nào tiện thì giao",
        "trong ngày mai cũng được", "giao chiều mai cũng ổn",
        "cuối tuần giao cũng không sao", "không có yêu cầu ưu tiên",
        "đi theo lịch bình thường là được", "đơn thường, không phải đơn gấp",
        "khỏi chạy nhanh", "không cần giao ngay", "{me} không vội",
        "thời gian thoải mái", "không áp lực thời gian",
        "ngày mốt tới cũng được", "tuần này giao xong là được",
    ],
    ("urgent", "yes", "hard"): [
        "không thể để trễ được", "không được chậm nhé",
        "tuyệt đối không được trễ", "đừng để khách chờ thêm",
        "không còn nhiều thời gian đâu", "chớ để trễ nhé",
        "nhỏ thôi nhưng cần gấp", "đồ nhỏ mà gấp lắm",
        "tuy đơn nhỏ nhưng khách chờ rồi",
    ],
    ("urgent", "no", "hard"): [
        "đơn của {name} mới gấp, đơn này thì không",
        "hôm qua thì gấp, hôm nay đã ổn rồi", "đừng tưởng đây là đơn gấp",
        "{name} bảo gấp nhưng đơn này thì không cần",
        "gấp là chuyện của đơn kia, đơn này cứ từ từ",
        "lần trước gấp, lần này thì thong thả",
        "không phải đơn gấp, cứ theo lịch",
        "đơn gấp xong rồi, còn đơn này thì không vội",
        "đừng chạy nhanh quá, đơn này chưa gấp",
    ],
    ("fragile", "yes", "std"): [
        "hàng {w}, nhớ nhẹ tay",
        "món này thuộc loại {w}, vận chuyển cẩn thận giúp {me}",
        "nhẹ tay nhé, đây là đồ {w}", "lưu ý: hàng {w}",
        "đừng xóc mạnh vì món này {w}", "kiện này {w}, bảo quản cẩn thận nha",
        "xử lý nhẹ tay một chút, hàng khá {w}",
        "đồ {w} đó, xếp riêng giúp {me}", "hàng dạng {w} nên xếp trên cùng",
        "bên trong là đồ {w}", "cẩn thận vì hàng khá {w}",
        "dán nhãn hàng {w} giúp {me}", "{o} thuộc loại {w}",
    ],
    ("fragile", "no", "std"): [
        "món này không {w}", "đây không phải hàng {w}",
        "không có lưu ý gì về đồ {w}", "kiện này không thuộc loại {w}",
        "hàng thường, không {w}", "không cần xem món này là đồ {w}",
        "hàng chắc chắn, không {w}",
        "đóng gói thường thôi, không phải đồ {w}", "không có gì {w} hết",
        "hàng không {w}, cứ xếp bình thường",
    ],
    ("fragile", "yes", "hard"): [
        "đừng làm rơi", "không được va đập",
        "tuyệt đối không xóc mạnh vì đồ {w}", "đừng quăng, đồ {w} đó",
        "đừng để bị đè lên vì {w}", "không được chồng đồ lên trên, hàng {w}",
    ],
    ("fragile", "no", "hard"): [
        "đơn của {name} mới {w}, đơn này thì không",
        "hôm trước gửi đồ {w}, lần này hàng thường",
        "đừng nhầm với đơn {w} kia",
        "không phải đồ {w} đâu, cứ xếp bình thường",
        "{w} là đơn kia, đơn này thì khác",
        "đơn {w} đã đi trước rồi, đơn này là hàng thường",
    ],
    ("fragile", "yes", "para"): [
        "đừng chồng đồ nặng lên trên", "tránh va đập mạnh", "đừng ném hay quăng",
        "cầm nhẹ tay thôi", "đặt cẩn thận, tránh rung lắc", "nhẹ tay, kẻo bể",
        "xếp riêng ra, đừng để đè",
    ],
    ("fragile", "no", "para"): [
        "đồ cứng cáp, không sợ va chạm", "hàng bình thường, xử lý như mọi khi",
        "hàng chắc chắn, xếp thoải mái",
        "đóng gói thường thôi, chồng đồ cũng được",
        "không cần giữ gìn đặc biệt", "cứ xếp như hàng bình thường",
    ],
}

ATTR[("urgent", "yes", "hard")] += [
    "hôm qua thì thong thả, hôm nay thì gấp", "sáng khách bảo không gấp, giờ đổi ý, cần gấp",
    "trước đó không vội nhưng giờ cần gấp rồi", "khách vừa gọi giục lần nữa",
    "đã nhắc hai lần rồi, khách đang sốt ruột", "đừng nghe câu 'không gấp' ở tin trước, đơn này gấp",
    "không gấp... à nhầm, gấp lắm", "tài liệu gấp làm ba cho vừa túi, nhưng đơn thì gấp thật",
]
ATTR[("urgent", "no", "hard")] += [
    "mai mới cần, hôm nay chưa", "khách dặn tuần sau mới cần",
    "nếu có gấp thì {me} đã báo trước rồi, đơn này thì chưa",
    "hồi sáng thì gấp, giờ khách báo thư thả rồi", "đã gấp từ hôm qua, giờ khách nói không cần nữa",
    "đơn gấp hôm qua đã xong rồi", "gấp... à nhầm, không gấp",
    "tài liệu đã gấp làm ba cho vừa túi, đơn thường thôi",
    "áo đã gấp sẵn trong túi, giao lúc nào cũng được",
    "đoạn qua cổng đi nhanh thôi vì có chó dữ, chứ đơn không gấp",
    "phụ phí cuối tuần gấp đôi, đơn thì không gấp",
]
ATTR[("fragile", "yes", "hard")] += [
    "hôm qua hàng thường, hôm nay là đồ {w}", "tin trước ghi nhầm hàng thường, thật ra là đồ {w}",
    "hàng thường... à nhầm, đồ {w}", "nếu là đồ thường thì cứ xếp, nhưng đây là hàng {w}",
    "{w} nên {me} mới dặn kỹ, đừng cho là hàng thường",
]
ATTR[("fragile", "no", "hard")] += [
    "tin trước ghi {w} là nhầm, hàng thường", "đồ {w}... nhầm, hàng thường",
    "nếu là đồ {w} thì {me} đã báo, đơn này thì không", "nếu {w} thì nhẹ tay, nhưng đây là hàng thường",
    "cẩn thận chó ở cổng nhé, còn hàng thì không {w}", "đi cẩn thận kẻo trơn, hàng thường thôi",
    "mục đồ {w} trên app {me} không chọn", "kiện {w} ở kho kia, kiện này thì không",
]
ATTR[("urgent", "yes", "dneg")] = ["không phải là không gấp", "chẳng phải không gấp đâu",
                                   "đâu phải đơn không gấp", "không thể nói là không gấp"]
ATTR[("fragile", "yes", "dneg")] = ["đâu phải hàng không {w}", "không phải đồ không {w}",
                                    "không thể bảo là không {w}", "chẳng phải món này không {w}"]
ATTR[("urgent", "yes", "sarc")] = ["ừ cứ từ từ đi, khách chờ có vài phút thôi mà",
                                   "thong thả nhé, khách chỉ đứng chờ ngoài mưa thôi"]

ATTR_COMB = {
    ("yes", "yes"): [
        "vừa gấp vừa {w}, ráng giúp {me}",
        "gấp mà lại {w}, đi nhanh nhưng nhẹ tay", "đơn gấp và là hàng {w}",
        "nhanh thì nhanh nhưng nhớ nhẹ tay, đồ {w}",
        "hàng {w} nên nhẹ tay, mà {me} cũng cần gấp",
    ],
    ("yes", "no"): [
        "gấp nhưng không {w}", "đơn gấp, còn hàng thì không {w}",
        "cần nhanh, hàng không {w} nên khỏi lo", "gấp chứ không phải hàng {w}",
        "ưu tiên đơn này, hàng thường thôi",
        "chạy nhanh giúp {me}, đồ không {w}",
    ],
    ("no", "yes"): [
        "không gấp, chỉ cần nhẹ tay vì hàng {w}", "hàng {w} nhưng không vội",
        "từ từ cũng được, miễn là hàng {w} được giữ cẩn thận",
        "đồ {w}, đi chậm mà chắc", "chưa cần gấp, nhớ là hàng {w}",
        "đừng vội, hàng {w} mà",
    ],
    ("no", "no"): [
        "không gấp, cũng không {w}", "đơn thường, không vội, không phải hàng {w}",
        "hàng bình thường và không cần ưu tiên", "không gấp mà cũng chẳng {w}",
        "thong thả thôi, hàng thường",
    ],
}

FILL_PRE = ["chào {you}", "hi {you}", "alo", "{you} ơi", "cho {me} hỏi chút",
            "ok {you}", "dạ", "ừ", "à", "này", "đơn mới nè",
            "chào {you}, {me} gửi thông tin đơn nhé"]
FILL_POST = ["cảm ơn {you} nhiều", "thanks nha", "cảm ơn nhé", "ok chốt vậy nhé",
             "có gì nhắn {me} nha", "xong báo {me} một tiếng", "{me} đợi tin nhé",
             "cảm ơn {you} ạ", "cám ơn nhiều", "chốt vậy nha"]
FILL_INFO = ["mã đơn #{k}", "đơn đặt lúc {h}h", "khách tên {name_short}",
             "sđt cuối {d4}", "đơn đã thanh toán rồi", "đơn thu hộ COD",
             "khách đã xác nhận rồi", "trời đang mưa nhỉ",
             "hôm nay đông khách quá", "đơn số {k}"]


# ---------------------------------------------------------------
# 2. BALANCER (giữ nguyên từ V2)
# ---------------------------------------------------------------
class Balancer:
    def __init__(self, rng):
        self.rng = rng
        self.c = collections.Counter()

    def pick(self, key, options):
        opts = list(dict.fromkeys(options))
        if not opts:
            raise ValueError(f"Không có option để pick: {key!r}")
        m = min(self.c[(key, o)] for o in opts)
        choices = [o for o in opts if self.c[(key, o)] == m]
        o = self.rng.choice(choices)
        self.c[(key, o)] += 1
        return o


# ---------------------------------------------------------------
# 3. TEXT / NOISE HELPERS
# ---------------------------------------------------------------
def cap(s):
    return s[:1].upper() + s[1:] if s else s

def first_upper(text):
    return cap(text)

_TONES = {"\u0301": "s", "\u0300": "f", "\u0309": "r", "\u0303": "x", "\u0323": "j"}

def to_telex(word):
    out, tone = [], ""
    for ch in unicodedata.normalize("NFD", word):
        if ch in _TONES:
            tone = _TONES[ch]
        elif ch == "\u0302" and out:
            out.append(out[-1])
        elif ch in ("\u031b", "\u0306"):
            out.append("w")
        elif ch == "đ":
            out.append("dd")
        elif ch == "Đ":
            out.append("DD")
        else:
            out.append(ch)
    return "".join(out) + tone

def _build_kb():
    rows = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
    nb = {}
    for ri, row in enumerate(rows):
        for ci, ch in enumerate(row):
            s = []
            if ci > 0:
                s.append(row[ci - 1])
            if ci < len(row) - 1:
                s.append(row[ci + 1])
            for rj in (ri - 1, ri + 1):
                if 0 <= rj < len(rows) and ci < len(rows[rj]):
                    s.append(rows[rj][ci])
            nb[ch] = s
    return nb

_KB = _build_kb()

def _mutate_word(core, rng):
    op = rng.choices(["swap", "drop", "dup", "kb", "telex", "elong"],
                     weights=[0.28, 0.22, 0.12, 0.16, 0.14, 0.08], k=1)[0]
    n = len(core)
    if op == "telex":
        t = to_telex(core)
        return t if t != core else core + core[-1]
    if op == "elong":
        return core + core[-1] * rng.randint(1, 2)
    pos = rng.randint(1, n - 2)
    if op == "swap":
        return core[:pos] + core[pos + 1] + core[pos] + core[pos + 2:]
    if op == "drop":
        return core[:pos] + core[pos + 1:]
    if op == "dup":
        return core[:pos] + core[pos] + core[pos:]
    idxs = [i for i, ch in enumerate(core) if ch.lower() in _KB]
    if not idxs:
        return core
    i = rng.choice(idxs)
    return core[:i] + rng.choice(_KB[core[i].lower()]) + core[i + 1:]

# Hàm phá hủy thực thể (lỗi chí mạng khiến NER bối rối)
def extreme_typo(core, rng):
    if len(core) < 3: return core
    op = rng.choice(["insert_space", "drop_char", "dup_char", "kb_miss", "split_end"])
    pos = rng.randint(1, len(core)-1)
    if op == "insert_space":
        return core[:pos] + " " + core[pos:]
    if op == "drop_char":
        return core[:pos] + core[pos+1:]
    if op == "dup_char":
        return core[:pos] + core[pos] + core[pos:]
    if op == "kb_miss":
        c = core[pos].lower()
        if c in _KB:
            return core[:pos] + rng.choice(_KB[c]) + core[pos+1:]
    if op == "split_end": 
        if pos < len(core) - 1:
            return core[:pos] + core[pos] + " " + core[pos+1:]
    return core

def add_typo(text, rng):
    if not text:
        return text
    words = text.split()
    cand = [i for i, w in enumerate(words)
            if "@" not in w and not re.search(r"\d", w)
            and len(re.sub(r"[^\w]", "", w)) >= 4]
    if not cand:
        return text
    n = rng.choices([1, 2, 3], weights=[0.62, 0.28, 0.10], k=1)[0]
    rng.shuffle(cand)
    for idx in cand[:n]:
        m = re.match(r"^(\W*)(.*?)(\W*)$", words[idx], flags=re.UNICODE)
        pre, core, post = m.group(1), m.group(2), m.group(3)
        if len(core) < 4:
            continue
        words[idx] = pre + _mutate_word(core, rng) + post
    if rng.random() < 0.10 and len(words) > 3:      # dính chữ (thiếu space)
        i = rng.randrange(len(words) - 1)
        if "@" not in words[i] and "@" not in words[i + 1]:
            words[i] = words[i] + words[i + 1]
            del words[i + 1]
    return " ".join(words)

_ABBR = {
    "không": ["ko", "k", "hok", "hông", "khong"], "được": ["đc", "dc"],
    "với": ["vs"], "bạn": ["bn"], "mình": ["mk", "mik"], "rồi": ["r", "rùi"],
    "luôn": ["lun"], "thôi": ["thui"], "vậy": ["zậy"], "nhưng": ["nhg"],
    "xong": ["xg"], "gửi": ["gởi"], "ok": ["oke", "okie"], "cảm": ["cám"],
    "người": ["ng"], "nhé": ["nhe"],
}
_ELONG = {"nhé", "nha", "với", "ạ", "nhen", "nghen", "nè", "nhe"}

def chat_noise(text, rng):
    toks = re.findall(r"\S+|\s+", text)
    out = []
    for t in toks:
        if t.isspace() or "@" in t:
            out.append(t)
            continue
        m = re.match(r"^([^\w]*)(.*?)([^\w]*)$", t, flags=re.UNICODE)
        pre, core, post = m.group(1), m.group(2), m.group(3)
        lc = core.lower()
        if lc in _ABBR and rng.random() < 0.55:
            core = rng.choice(_ABBR[lc])
        elif lc in _ELONG and rng.random() < 0.25:
            core = core + core[-1] * rng.randint(1, 3)
        out.append(pre + core + post)
    s = "".join(out)
    if rng.random() < 0.30:
        s = s.replace(",", "")
    return s

def norm_ws(txt):
    txt = re.sub(r"\s+", " ", txt)
    txt = re.sub(r"\s+([,.;!?:])", r"\1", txt)
    txt = re.sub(r"([,;:])\1+", r"\1", txt)
    txt = re.sub(r",\s*([.!?])", r"\1", txt)
    return txt.strip(" ,;")

def sentence(u, rng, p_excl=0.07):
    u = re.sub(r"\s+", " ", u).strip()
    if not u:
        return u
    u = cap(u)
    if u[-1] not in ".!?…)\"":
        u += "!" if rng.random() < p_excl else "."
    return u

_RECAP = re.compile(r"(?<![.])([.!?]\s+)([a-zà-ỹ])")

def recap(s):
    return _RECAP.sub(lambda m: m.group(1) + m.group(2).upper(), s)

def render_units(units, rng, style):
    units = [u for u in units if u and u.strip()]
    if style == "formal":
        return recap(" ".join(sentence(u, rng) for u in units))
    if style == "terse":
        sep = rng.choice([" | ", " / ", "; ", " - "])
        return sep.join(re.sub(r"[\s.;,]+$", "", u.strip()) for u in units)
    sep = rng.choice([", ", ", ", ". ", " - ", " . ", " "])
    parts = [re.sub(r"[\s.;,]+$", "", u.strip()).lower() for u in units]
    return sep.join(parts)


# ---------------------------------------------------------------
# 4. ĐỊA ĐIỂM: ALIAS / CLASH / PHRASE
# ---------------------------------------------------------------
_ALIAS_CACHE = {}
_CLASH = {}

def _alias_set(p):
    s = _ALIAS_CACHE.get(p)
    if s is None:
        s = {fold(a).lower().strip() for a in BANK.get(p, [p])}
        _ALIAS_CACHE[p] = s
    return s

def clash(p, q):
    if p == q:
        return True
    k = (p, q) if p < q else (q, p)
    v = _CLASH.get(k)
    if v is None:
        v = bool(_alias_set(p) & _alias_set(q))
        _CLASH[k] = v
    return v

def _distract(B, key, forb):
    opts = [p for p in PLACES if not any(clash(p, f) for f in forb)]
    if not opts:
        opts = [p for p in PLACES if p not in forb] or list(PLACES)
    return B.pick(key, opts)

def _relation(rng, B, raw, role):
    if rng.random() >= CFG["p_kind"] or not KINDS:
        return "none", "none"
    kind = B.pick((role, "kind"), KINDS)
    if kind not in ("near", "far"):
        return kind, "none"
    opts = [p for p in PLACES if not clash(p, raw)] or [p for p in PLACES if p != raw]
    return kind, B.pick((role, "anchor"), opts)

def alias_for(raw_place, role, B, has_typo, rng):
    aliases = BANK.get(raw_place, [raw_place])
    value = B.pick(("place_alias", role, raw_place), aliases)
    # Bổ sung logic Extreme Typo cho Alias khi có cờ has_typo
    if has_typo and rng.random() < CFG["p_alias_typo"]:
        words = value.split()
        if words:
            idx = rng.randrange(len(words))
            words[idx] = extreme_typo(words[idx], rng)
            value = " ".join(words)
    return value

KIND_ONLY_FORMS = ["{base} {k}", "{k} {base}", "{base}, {k}", "{base} ({k})",
                   "chỗ {base} {k}", "{base} — {k}"]
ANCHOR_FORMS = ["{base} {k} {a}", "{base}, {k} {a}", "{base} ({k} {a})",
                "{base}, chỗ {k} {a}", "{k} {a}, chỗ {base}",
                "{base} nằm {k} {a}", "{base} — {k} {a}",
                "chỗ {base} ấy, {k} {a}", "{base} {k} {a} đó"]

def place_parts(raw_place, kind="none", anchor="none", role="place", B=None,
                has_typo=False, rng=None, base=None, kw=None, aa=None):
    rng = rng or random.Random()
    B = B or Balancer(rng)
    if base is None:
        base = alias_for(raw_place, role, B, has_typo, rng)
    if kind == "none":
        return {"text": base, "base": base, "k": None, "a": None}
    if kw is None:
        kw = B.pick(("kind_alias", kind), BANK.get(kind, [kind]))
    if anchor == "none":
        t = B.pick(("kind_form", role, kind), KIND_ONLY_FORMS).format(base=base, k=kw)
        return {"text": t, "base": base, "k": kw, "a": None}
    if aa is None:
        aa = alias_for(anchor, f"anchor_{role}", B, has_typo, rng)
    t = B.pick(("kind_anchor_form", role, kind), ANCHOR_FORMS).format(base=base, k=kw, a=aa)
    return {"text": t, "base": base, "k": kw, "a": aa}

def place_phrase(raw_place, kind="none", anchor="none", role="place", B=None,
                 has_typo=False, rng=None):
    return place_parts(raw_place, kind, anchor, role, B, has_typo, rng)["text"]

def _forced_relation(B, raw, role, kinds):
    kind = B.pick((role, "fkind"), kinds)
    if kind in ("near", "far"):
        opts = [p for p in PLACES if not clash(p, raw)] or [p for p in PLACES if p != raw]
        return kind, B.pick((role, "fanchor"), opts)
    return kind, "none"


# ---------------------------------------------------------------
# 5. CTX: bộ sinh mệnh đề (ghép từ thành phần)
# ---------------------------------------------------------------
class _Fmt(dict):
    def __init__(self, base, lazy):
        super().__init__(base)
        self._lazy = lazy

    def __missing__(self, k):
        if k in self._lazy:
            v = self._lazy[k]()
            self[k] = v
            return v
        raise KeyError(k)

def render_vp(P, place, with_obj=True):
    o = (" " + P["o"]) if (with_obj and P["o"]) else ""
    return f"{P['v']}{P['adv']}{o} {P['p']} {place}"

class Ctx:
    def __init__(self, rng, B, bk, persona, item):
        self.rng, self.B, self.bk = rng, B, bk
        self.me, self.you, self.south, self.polite = persona
        self.item = item

    def tail(self, mid=False, p_none=0.5):
        r = self.rng
        if r.random() < p_none:
            return ""
        pool = list(TAIL_COMMON) + (TAIL_SOUTH if self.south else TAIL_NORTH)
        if self.polite:
            pool += TAIL_POLITE
        if not mid:
            pool += TAIL_END_ONLY
        return r.choice(pool).format(me=self.me)

    def obj(self, allow_empty=False):
        r = self.rng
        if allow_empty and r.random() < 0.22:
            return ""
        x = r.random()
        if x < 0.38:
            return self.item
        if x < 0.50:
            return "đơn " + self.item
        if x < 0.58:
            return "món " + self.item
        return r.choice(OBJ_PRON)

    def vp_parts(self):
        B, r, bk = self.B, self.rng, self.bk
        verb = B.pick((bk, "verb"), list(GIVE_VERBS))
        prep = B.pick((bk, "prep", verb), GIVE_VERBS[verb])
        adv = ""
        if verb != "để lại" and r.random() < 0.16:
            adv = " " + r.choice(["thẳng", "luôn", "trực tiếp"])
        return {"v": verb, "p": prep, "adv": adv, "o": self.obj(allow_empty=True)}

    def vp(self, place):
        return render_vp(self.vp_parts(), place)

    def vp_contrast(self, G, T):
        P = self.vp_parts()
        fG, sG = render_vp(P, G), render_vp(P, G, False)
        fT, sT = render_vp(P, T), render_vp(P, T, False)
        p = P["p"]
        forms = [
            f"{fG}, chứ không {sT}", f"không {sT} mà {fG}",
            f"{fG} thôi, đừng {sT}", f"đừng {fT}; {sG} mới đúng",
            f"{sG}, không phải {p} {T}", f"đừng {fT}, hãy {sG}",
            f"{fG} nhé, đừng nhầm sang {T}",
            f"{P['v']}{P['adv']} {P['o']} không phải {p} {T} mà là {p} {G}",
        ]
        return self.B.pick((self.bk, "contrast"), forms)

    def gs(self, G, composable=True, family=None):
        r, me, you = self.rng, self.me, self.you
        fams = GS_FAMS if composable else GS_FAMS + ["ask"]
        fam = family or self.B.pick((self.bk, "gs_fam", composable), fams)
        t = self.tail()
        if fam == "imp":
            s = f"{self.vp(G)} {t}"
        elif fam == "nho":
            s = f"{r.choice(['nhờ', 'phiền', 'xin nhờ', 'làm phiền'])} {you} {self.vp(G)} {t}"
        elif fam == "you":
            s = f"{you} {self.vp(G)} {t}"
        elif fam == "want":
            s = r.choice([f"{me} muốn nhờ {you} {self.vp(G)}",
                          f"{me} cần {you} {self.vp(G)}",
                          f"{me} muốn {self.vp(G)}"]) + " " + t
        elif fam == "pass":
            P = self.vp_parts()
            aux = r.choice(["cần được", "phải được", "muốn được", "sẽ được"])
            s = f"{self.obj(False)} {aux} {P['v']}{P['adv']} {P['p']} {G} {t}"
        elif fam == "topic":
            P = self.vp_parts()
            s = f"{self.obj(False)}{r.choice([' thì', ''])} {render_vp(P, G, False)} {t}"
        elif fam == "formal":
            lead = r.choice(["vui lòng", "đề nghị", "yêu cầu", "kính nhờ " + you, "xin vui lòng"])
            s = f"{lead} {self.vp(G)}"
        elif fam == "nominal":
            s = r.choice(NOMINAL).format(G=G)
        elif fam == "recv":
            s = r.choice(RECV).format(G=G)
        elif fam == "frag":
            s = r.choice(FRAG).format(G=G, t=t)
        elif fam == "go":
            s = r.choice(GO).format(G=G, me=me, t=t)
        else:
            s = r.choice([f"có thể {self.vp(G)} không {you}?",
                          f"{you} {self.vp(G)} giúp {me} được không?",
                          f"{self.vp(G)} được không?"])
        return re.sub(r"\s+", " ", s).strip()

    def pv(self, V):
        r, B = self.rng, self.B
        if r.random() < 0.12:
            return B.pick((self.bk, "stop"), STOP_PATTERNS).format(V=V)
        pat = B.pick((self.bk, "pick"), PICK_PATTERNS)
        o = r.choice(PICK_OBJ).format(item=self.item)
        if "nhận" in pat and not o:
            o = "hàng"
        return re.sub(r"\s+", " ", pat.format(o=o, V=V)).strip()

    def ps(self, V):
        tpl = self.B.pick((self.bk, "ps"), PS_FRAMES)
        return re.sub(r"\s+", " ", self.fmt(tpl, V=V)).strip()

    def redir(self, G):
        return self.fmt(self.B.pick((self.bk, "redir"), REDIR_FORMS), G=G)

    def qa(self):
        q = self.fmt(self.B.pick((self.bk, "qa_q"), QA_Q))
        a = self.fmt(self.B.pick((self.bk, "qa_a"), QA_A))
        r = self.rng
        x = r.random()
        if x < 0.25:
            return f"A: {q} B: {a}"
        if x < 0.35:
            return f"- {q} - {a}"
        return q + r.choice([" ", " ", " — ", " - "]) + a

    def obj_plain(self):
        x = self.rng.random()
        if x < 0.30:
            return ""
        if x < 0.65:
            return self.item
        return ("đơn " if x < 0.85 else "món ") + self.item

    def vp0(self, place):
        P = self.vp_parts()
        P["o"] = self.obj_plain()
        return render_vp(P, place)

    def coref(self, G, T, neg=False):
        r = self.rng
        g_first = r.random() < 0.5
        a, b = (G, T) if g_first else (T, G)
        ref_g = r.choice(REF_FIRST if g_first else REF_SECOND)
        ref_t = r.choice(REF_SECOND if g_first else REF_FIRST)
        lead = self.B.pick((self.bk, "coref_lead"), COREF_LEAD).format(a=a, b=b)
        body = self.vp_contrast(ref_g, ref_t) if neg else self.vp(ref_g)
        return f"{lead}, {body}"

    def gs_person(self, G):
        r = self.rng
        verb = r.choice(["giao", "đưa", "gửi", "chuyển", "trao", "để lại"])
        person = self.B.pick((self.bk, "person"), PERSONS)
        tm = (" " + r.choice(TIME_MOD)) if r.random() < 0.4 else ""
        core = f"{verb} {self.obj(allow_empty=True)} cho {person} {r.choice(['ở', 'tại'])} {G}{tm}"
        x, t = r.random(), self.tail()
        if x < 0.4:
            s = f"{core} {t}"
        elif x < 0.7:
            s = f"nhờ {self.you} {core} {t}"
        else:
            s = f"{self.me} muốn nhờ {self.you} {core}"
        return re.sub(r"\s+", " ", s).strip()

    def fmt(self, tpl, **kw):
        G = kw.get("G", PH["G"])
        V = kw.get("V", PH["V"])
        T = kw.get("T", PH["T1"])
        B, r, bk = self.B, self.rng, self.bk
        base = dict(G=G, V=V, T=T, TV=PH["TV"], T1=PH["T1"], T2=PH["T2"],
                    T3=PH["T3"], T4=PH["T4"], me=self.me, you=self.you,
                    Me=cap(self.me), You=cap(self.you),
                    GW=PH["GW"], GB=PH["GB"], AW=PH["AW"], KT=PH["KT"], KO=PH["KO"],
                    AT=PH["AT"], TG=PH["TG"])
        base.update({k: v for k, v in kw.items() if k not in ("G", "V", "T")})
        nm = r.choice(NAMES)
        lazy = {
            "o": lambda: self.obj(False),
            "tail": lambda: self.tail(),
            "tailm": lambda: self.tail(mid=True),
            "name": lambda: nm,
            "name_short": lambda: nm.split()[-1],
            "n": lambda: r.choice([10, 15, 20, 30, 45]),
            "k": lambda: r.randint(100, 9999),
            "h": lambda: r.randint(6, 21),
            "d4": lambda: f"{r.randint(0, 9999):04d}",
            "GV": lambda: self.vp(G),
            "GS": lambda: self.gs(G),
            "GV_T": lambda: self.vp(T),
            "GV_T0": lambda: self.vp0(T),
            "GV_W": lambda: self.vp(PH["GW"]),
            "PV_T": lambda: self.pv(PH["TV"]),
            "GS_T": lambda: self.gs(T),
            "GV_C": lambda: self.vp_contrast(G, T),
            "PV": lambda: self.pv(V),
            "PS": lambda: self.ps(V),
            "REDIR": lambda: self.redir(G),
            "corr": lambda: self.fmt(B.pick((bk, "corr"), CORR_SOFT)),
            "Corr": lambda: cap(self.fmt(B.pick((bk, "corr"), CORR_SOFT))),
            "not_T": lambda: self.fmt(B.pick((bk, "not_T"), NOT_T), T=T),
            "notT_lead": lambda: self.fmt(B.pick((bk, "notT_lead"), NOT_LEAD), T=T),
            "why": lambda: B.pick((bk, "why"), WHY),
            "conv": lambda: B.pick((bk, "conv"), CONV),
        }
        return tpl.format_map(_Fmt(base, lazy))


# ---------------------------------------------------------------
# 6. THUỘC TÍNH (urgent / fragile)
# ---------------------------------------------------------------
def one_attr(ctx, which, val, w):
    r = ctx.rng
    x = r.random()
    cuts = [("hard", CFG["p_attr_hard"])]
    if CFG["use_para_attr"] and which == "fragile":
        cuts.append(("para", CFG["p_attr_para"]))
    if CFG["use_double_neg"] and val == "yes":
        cuts.append(("dneg", CFG["p_attr_dneg"]))
    if CFG["use_sarcasm"] and which == "urgent" and val == "yes":
        cuts.append(("sarc", CFG["p_attr_sarc"]))
    kind, acc = "std", 0.0
    for k, pr in cuts:
        acc += pr
        if x < acc:
            kind = k
            break
    tpl = ctx.B.pick((ctx.bk, "attr", which, val, kind), ATTR[(which, val, kind)])
    return ctx.fmt(tpl, w=w)

def attr_units(ctx, urgent, fragile, w):
    r = ctx.rng
    omit_u = urgent == "no" and r.random() < CFG["p_omit_no"]
    omit_f = fragile == "no" and r.random() < CFG["p_omit_no"]
    if not omit_u and not omit_f and r.random() < CFG["p_attr_combined"]:
        tpl = ctx.B.pick((ctx.bk, "attr_comb", urgent, fragile), ATTR_COMB[(urgent, fragile)])
        return [ctx.fmt(tpl, w=w)], "combined"
    units = []
    if not omit_u:
        units.append(one_attr(ctx, "urgent", urgent, w))
    if not omit_f:
        units.append(one_attr(ctx, "fragile", fragile, w))
    return units, ("omit" if (omit_u or omit_f) else "separate")


# ---------------------------------------------------------------
# 7. TẠO 1 MẪU
# ---------------------------------------------------------------
def _eligible(t):
    kinds = [k for k in KINDS if k != "none"]
    if t in KIND_TYPES and len(kinds) < 2:
        return False
    if t in ANCHOR_TYPES and not ("near" in KINDS and "far" in KINDS):
        return False
    if t == "anchor_trap" and not ("near" in KINDS or "far" in KINDS):
        return False
    if t == "sarcasm" and not CFG["use_sarcasm"]:
        return False
    if t == "double_neg" and not CFG["use_double_neg"]:
        return False
    if t == "hypo" and not CFG["use_hypo"]:
        return False
    return True

def _weighted(table, allowed, exclude):
    return [(k, w) for k, w in table.items()
            if (allowed is None or k in allowed) and k not in exclude and _eligible(k)]

def _make_sample(rng, B, bk, is_neg, has_acc, has_typo, allowed, exclude):
    persona = B.pick((bk, "persona"), PERSONAS)
    item = B.pick((bk, "item"), ITEMS)
    ctx = Ctx(rng, B, bk, persona, item)

    pool = _weighted(NEG_W if is_neg else AFF_W, allowed, exclude)
    if pool and (not is_neg or rng.random() < CFG["p_neg_goal"]):
        gtype = rng.choices([k for k, _ in pool], weights=[w for _, w in pool], k=1)[0]
    else:
        gtype = "plain"
    is_neg_type = gtype in NEG_W

    goal = B.pick((bk, "goal"), PLACES)
    if gtype in KIND_TYPES:
        gk, ga = _forced_relation(B, goal, (bk, "grel"), [k for k in KINDS if k != "none"])
    elif gtype in ANCHOR_TYPES:
        gk, ga = _forced_relation(B, goal, (bk, "grel"), ["near", "far"])
    elif gtype in ("coref", "coref_neg"):
        gk, ga = "none", "none"
    else:
        gk, ga = _relation(rng, B, goal, (bk, "grel"))
    via = "none"
    if rng.random() < CFG["p_via"]:
        opts = [p for p in PLACES if not clash(p, goal)]
        if opts:
            via = B.pick((bk, "via"), opts)
    if via == "none":
        vk, va = "none", "none"
    else:
        vk, va = _relation(rng, B, via, (bk, "vrel"))

    forb = {goal} | ({via} if via != "none" else set())
    t1 = _distract(B, (bk, "t1"), forb)
    t2 = _distract(B, (bk, "t2"), forb | {t1})
    t3 = _distract(B, (bk, "t3"), forb | {t1, t2})
    t4 = _distract(B, (bk, "t4"), forb | {t1, t2, t3})
    tv = _distract(B, (bk, "tv"), forb | {t1, t2, t3, t4})

    ptr = (0.6 if gtype in ("other_order", "temporal", "old_info")
           else 0.0 if gtype in ("coref", "coref_neg") else CFG["p_trap_rel"])

    def trap(raw, role):
        if rng.random() < ptr:
            k, a = _relation(rng, B, raw, (bk, role + "_rel"))
            return place_phrase(raw, k, a, role, B, has_typo, rng)
        return alias_for(raw, role, B, has_typo, rng)

    gp = place_parts(goal, gk, ga, "goal", B, has_typo, rng)
    surf = {0: gp["text"], 8: gp["base"],
            2: alias_for(tv, "tv", B, has_typo, rng),
            3: trap(t1, "t1"), 4: trap(t2, "t2"),
            5: alias_for(t3, "t3", B, has_typo, rng),
            6: alias_for(t4, "t4", B, has_typo, rng)}
    if gp["k"] is not None:
        surf[10] = gp["k"]
    if gp["a"] is not None:
        surf[12] = gp["a"]
    if via != "none":
        surf[1] = place_phrase(via, vk, va, "via", B, has_typo, rng)

    if gtype in KIND_TYPES or gtype in ANCHOR_TYPES:
        wa_raw = _distract(B, (bk, "aw"), forb | ({ga} if ga != "none" else set()))
        surf[9] = alias_for(wa_raw, "aw", B, has_typo, rng)
        if gtype in KIND_TYPES:
            if gk in ("near", "far") and gtype == "pos_neg_kind":
                wk = "far" if gk == "near" else "near"
            else:
                alts = [k for k in KINDS if k not in (gk, "none")]
                if gtype == "pos_neg_kind":
                    alts = [k for k in alts if k not in ("near", "far")] or alts
                wk = B.pick((bk, "wk", gk), alts)
            wkw = B.pick(("kind_alias", wk), BANK.get(wk, [wk]))
            surf[11] = wkw
            if wk in ("near", "far"):
                wp = place_parts(goal, wk, wa_raw, "goalw", B, has_typo, rng,
                                 base=gp["base"], kw=wkw, aa=surf[9])
            else:
                wp = place_parts(goal, wk, "none", "goalw", B, has_typo, rng,
                                 base=gp["base"], kw=wkw)
            surf[7] = wp["text"]
    if gtype == "anchor_trap":
        kt = B.pick((bk, "tgk"), [k for k in ("near", "far") if k in KINDS])
        tgk = B.pick(("kind_alias", kt), BANK.get(kt, [kt]))
        surf[13] = place_parts(t1, kt, goal, "tg", B, has_typo, rng,
                               kw=tgk, aa=gp["base"])["text"]

    if gtype == "plain":
        goal_unit = ctx.gs(PH["G"], composable=False)
    elif gtype == "qa_reject":
        goal_unit = (ctx.fmt(B.pick((bk, "tpl", "qa_rev"), QA_REV))
                     if rng.random() < 0.50 else ctx.qa())
    elif gtype == "coref":
        goal_unit = ctx.coref(PH["G"], PH["T1"])
    elif gtype == "coref_neg":
        goal_unit = ctx.coref(PH["G"], PH["T1"], neg=True)
    elif gtype == "recipient":
        goal_unit = ctx.gs_person(PH["G"])
    elif gtype == "pos_neg_kind":
        if gk in ("near", "far"):
            lst, tag = POS_NEG_KIND_ANCHOR, "a"
        elif wk in ("near", "far"):
            lst, tag = [t.replace("{AT}", "{AW}") for t in POS_NEG_KIND_ANCHOR], "w"
        else:
            lst, tag = POS_NEG_KIND_PLAIN, "p"
        goal_unit = ctx.fmt(B.pick((bk, "tpl", gtype, tag), lst))
    else:
        goal_unit = ctx.fmt(B.pick((bk, "tpl", gtype), GOAL_TPL[gtype]))

    neg_units = 1 if is_neg_type else 0

    via_unit, via_mode = "", "none"
    if via != "none":
        if gtype == "plain" and rng.random() < CFG["p_via_composite"]:
            goal_unit = ctx.fmt(B.pick((bk, "tpl", "composite"), COMPOSITE))
            via_mode = "composite"
        elif is_neg and ((not is_neg_type) or rng.random() < 0.35):
            via_unit = ctx.fmt(B.pick((bk, "tpl", "reject_via"), EXTRA_TPL["reject_via"]))
            via_mode, neg_units = "reject", neg_units + 1
        elif (not is_neg) and rng.random() < CFG["p_via_trick"]:
            via_unit = ctx.fmt(B.pick((bk, "tpl", "via_trick"), VIA_TRICK_AFF))
            via_mode = "trick"
        else:
            via_unit, via_mode = ctx.ps(PH["V"]), "plain"

    extras, extra_kinds = [], []
    if is_neg:
        if neg_units == 0 or rng.random() < CFG["p_extra_neg"]:
            opts = ["route_no_stop"]
            if via == "none":
                opts.append("no_stop")
            elif via_mode != "reject":
                opts.append("reject_via")
            k = B.pick((bk, "extra_neg"), opts)
            extras.append(ctx.fmt(B.pick((bk, "tpl", k), EXTRA_TPL[k]), T=PH["T4"]))
            extra_kinds.append(k)
            neg_units += 1
    elif rng.random() < CFG["p_extra_aff"]:
        opts = ["route_pass", "landmarks"] + (["no_stop_aff"] if via == "none" else [])
        k = B.pick((bk, "extra_aff"), opts)
        extras.append(ctx.fmt(B.pick((bk, "tpl", k), EXTRA_TPL[k]), T=PH["T4"]))
        extra_kinds.append(k)

    urgent = B.pick((bk, "urgent"), ["yes", "no"])
    fragile = B.pick((bk, "fragile"), ["yes", "no"])
    fra_w = B.pick((bk, "fra_w"), BANK.get("fragile", ["dễ vỡ"]))
    attrs, attr_mode = attr_units(ctx, urgent, fragile, fra_w)

    pre = post = ""
    infos = []
    if rng.random() < CFG["p_filler_pre"]:
        pre = ctx.fmt(B.pick((bk, "fpre"), FILL_PRE))
    if rng.random() < CFG["p_filler_post"]:
        post = ctx.fmt(B.pick((bk, "fpost"), FILL_POST))
    if rng.random() < CFG["p_filler_info"]:
        infos.append(ctx.fmt(B.pick((bk, "finfo"), FILL_INFO)))

    core = [goal_unit] + ([via_unit] if via_unit else [])
    if via_unit and rng.random() < 0.5:
        core.reverse()
    body = list(core)
    for u in extras + attrs + infos:
        body.insert(rng.randint(0, len(body)), u)
    if pre:
        body.insert(0, pre)
    if post:
        body.append(post)

    r_style = rng.random()
    style = ("chat" if r_style < CFG["p_chat"]
             else "terse" if r_style < CFG["p_chat"] + CFG["p_terse"] else "formal")
    masked = render_units(body, rng, style)

    ok = (PH["G"] in masked
          and ((via != "none") == (PH["V"] in masked))
          and not (via == "none" and PH["TV"] in masked)
          and "{" not in masked and "}" not in masked)
    if not ok:
        return None

    pos_g, pos_t = masked.find(PH["G"]), masked.find(PH["T1"])
    
    # Ở BƯỚC NÀY, thực thể mới được gỡ placeholder ra (sau khi văn cảnh đã chèn typo)
    if has_typo and rng.random() < CFG["p_sentence_typo"]:
        masked = add_typo(masked, rng)
    if style == "chat":
        masked = chat_noise(masked, rng)

    txt = re.sub(r"@(\d+)@", lambda m: surf.get(int(m.group(1)), m.group(0)), masked)
    if "@" in txt:
        return None
    if rng.random() < CFG["p_lower"]:
        txt = txt.lower()
    if not has_acc:
        txt = fold(txt)
    txt = norm_ws(txt)

    y = {
        "goal": H2I["goal"][goal], "via": H2I["via"][via],
        "gkind": H2I["gkind"][gk], "ganchor": H2I["ganchor"][ga],
        "vkind": H2I["vkind"][vk], "vanchor": H2I["vanchor"][va],
        "urgent": H2I["urgent"][urgent], "fragile": H2I["fragile"][fragile],
    }
    meta = {"gtype": gtype, "via_mode": via_mode, "extras": extra_kinds,
            "attr_mode": attr_mode, "style": style, "persona": persona,
            "goal_first": (pos_t < 0 or pos_g < pos_t) if pos_g >= 0 else None,
            "has_distractor": gtype not in ("plain",) or bool(extras)}
    return txt, y, meta


# ---------------------------------------------------------------
# 8. GENERATOR CHÍNH (cùng chữ ký với V2 + tham số holdout)
# ---------------------------------------------------------------
GEN_META = {}

def generate_15k_dataset(seed=42, num_per_bucket=1875, dedupe=True,
                         goal_types=None, exclude_goal_types=()):
    rng = random.Random(seed)
    B = Balancer(rng)
    allowed = set(goal_types) if goal_types else None
    exclude = set(exclude_goal_types or ())
    GEN_META.clear()

    buckets = {n: [] for n in [
        "Aff_Acc_NoTypo", "Aff_Acc_Typo", "Aff_NoAcc_NoTypo", "Aff_NoAcc_Typo",
        "Neg_Acc_NoTypo", "Neg_Acc_Typo", "Neg_NoAcc_NoTypo", "Neg_NoAcc_Typo"]}
    global_seen = set()
    bad = 0

    for bk in buckets:
        is_neg = bk.startswith("Neg")
        has_acc = "NoAcc" not in bk
        has_typo = "NoTypo" not in bk
        attempts, max_attempts = 0, max(num_per_bucket * 60, 20000)
        while len(buckets[bk]) < num_per_bucket:
            attempts += 1
            if attempts > max_attempts:
                raise RuntimeError(f"Không tạo đủ dữ liệu unique cho {bk}: "
                                   f"{len(buckets[bk])}/{num_per_bucket}.")
            res = _make_sample(rng, B, bk, is_neg, has_acc, has_typo, allowed, exclude)
            if res is None:
                bad += 1
                continue
            txt, y, meta = res
            if dedupe and txt in global_seen:
                continue
            global_seen.add(txt)
            GEN_META[txt] = meta
            buckets[bk].append({"text": txt, "y": y, "syn": True})
    if bad:
        print(f"  (bỏ {bad} mẫu vi phạm bất biến label/text)")
    return buckets, B


# ---------------------------------------------------------------
# 9. AUDIT: đo độ đa dạng + cân bằng vị trí goal/distractor
# ---------------------------------------------------------------
def audit_dataset(buckets, top=5):
    texts = [it["text"] for l in buckets.values() for it in l]
    alias = sorted({a for p in PLACES for a in BANK.get(p, [p])} |
                   {a for k in (KINDS or []) for a in BANK.get(k, [k])},
                   key=len, reverse=True)
    rx = re.compile("|".join(re.escape(a) for a in alias), re.IGNORECASE) if alias else None
    sk = collections.Counter()
    for t in texts:
        s = rx.sub("<P>", t) if rx else t
        sk[re.sub(r"\d+", "<N>", s)] += 1
    n = len(texts)
    print(f"Tổng mẫu: {n} | skeleton khác nhau: {len(sk)} ({len(sk)/n:.1%})")
    print(f"Skeleton phổ biến nhất chiếm: {sk.most_common(1)[0][1]/n:.3%}")
    gt = collections.Counter(GEN_META[t]["gtype"] for t in texts if t in GEN_META)
    print("Phân bố kiểu goal-unit:", dict(gt))
    gf = [GEN_META[t]["goal_first"] for t in texts
          if t in GEN_META and GEN_META[t]["has_distractor"]
          and GEN_META[t]["goal_first"] is not None]
    if gf:
        print(f"Goal đứng TRƯỚC distractor: {sum(gf)/len(gf):.1%} (lý tưởng ~50%)")
    lens = [len(t.split()) for t in texts]
    print(f"Độ dài (từ): min {min(lens)}, TB {sum(lens)/n:.1f}, max {max(lens)}")


# ================================================================
# 10. BUILD TRAIN SET (giữ nguyên luồng cũ)
# ================================================================
print("Đang sinh 15.000 dữ liệu cân bằng + đa dạng cấu trúc (V3.1 - Enhanced Typos & Logic)...")
bal_buckets, BalancerObj = generate_15k_dataset(seed=42, num_per_bucket=5000, dedupe=True)

final_15k_items = []
for bucket_name, bucket_items in bal_buckets.items():
    final_15k_items.extend(bucket_items)
    print(f"  {bucket_name}: {len(bucket_items)}")

print("Đang gộp thêm dữ liệu Train gốc + no-accent...")
train_extended = []
for it in base_items:
    train_extended.append({"text": it["text"], "y": it["y"]})
    train_extended.append({"text": fold(it["text"]), "y": it["y"]})

final_train_items = train_extended + final_15k_items
print(f"✅ Synthetic: {len(final_15k_items)}")
print(f"✅ Train gốc mở rộng: {len(train_extended)}")
print(f"✅ Tổng train sau gộp: {len(final_train_items)}")
audit_dataset(bal_buckets)