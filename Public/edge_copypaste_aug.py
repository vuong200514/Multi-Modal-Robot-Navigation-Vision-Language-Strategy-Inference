"""
COPY-PASTE CẠNH cho YOLO (Phenikaa Campus Courier)
- Input : /content/YOLO_Full_Dataset (images/train + labels/train, ảnh 1024x1024, nhãn YOLO)
- Output: /content/YOLO_CP  (train = gốc + ảnh copy-paste, val = val THẬT)
Ý tưởng: cắt 1 cạnh (kèm icon stairs/oneway) từ ảnh A, dán sang ảnh B (hoặc chỗ khác ảnh A),
xoay nhẹ +-ROT_DEG độ, và ghi nhãn cho cạnh mới. Chỉ dán vào CHỖ TRỐNG nền.
Class id phải khớp CLASSES trong notebook: 14-19 nét, 20 closed, 21 stairs, 22-25 oneway.
"""
import os, glob, random, shutil, yaml
import numpy as np, cv2
from collections import Counter, defaultdict

BASE = "/content/YOLO_Full_Dataset"
OUT  = "/content/YOLO_CP"
N_PASTE_IMGS   = 1500      # số ảnh mới sinh ra
EDGES_PER_IMG  = (3, 8)    # mỗi ảnh dán thêm bao nhiêu cạnh
INSET          = 15        # = BOX_PAD của build_split: bỏ phần đệm 2 đầu (hay dính landmark / nét cạnh kề)
ROT_DEG        = 6.0       # xoay tối đa (độ). Giữ nhỏ: oneway/stairs đổi nghĩa nếu xoay lớn
SCALE_RANGE    = (0.9, 1.1)
RARE_BOOST     = 2.0       # ưu tiên lấy cạnh thuộc tổ hợp hiếm (nét x icon)
SEED           = 0
LOOK, CLOSED, STAIRS, ONEWAY = set(range(14, 20)), 20, 21, set(range(22, 26))
EDGE_ALL = LOOK | {CLOSED, STAIRS} | ONEWAY
random.seed(SEED); np.random.seed(SEED)


def read_labels(p):
    out = []
    for l in open(p, encoding="utf-8"):
        q = l.split()
        if len(q) >= 5:
            out.append((int(float(q[0])), *map(float, q[1:5])))
    return out


def group_edges(labels, W, H):
    """Gộp các box cùng toạ độ (nét + icon) thành 1 'cạnh'. Trả list dict."""
    g = defaultdict(list)
    for c, xc, yc, w, h in labels:
        if c in EDGE_ALL:
            g[(round(xc, 4), round(yc, 4), round(w, 4), round(h, 4))].append(c)
    res = []
    for (xc, yc, w, h), cs in g.items():
        x1, y1 = (xc - w / 2) * W, (yc - h / 2) * H
        x2, y2 = (xc + w / 2) * W, (yc + h / 2) * H
        res.append(dict(box=[x1, y1, x2, y2], cls=cs))
    return res


def ink_mask(crop, bg, thr=40):
    d = np.linalg.norm(crop.astype(np.float32) - bg.astype(np.float32), axis=2)
    m = (d > thr).astype(np.uint8) * 255
    return cv2.dilate(m, np.ones((3, 3), np.uint8))          # ăn thêm viền anti-alias


def bg_color(img):
    return np.median(img.reshape(-1, 3), axis=0)


def free_space(labels, W, H):
    """Mặt nạ vùng đã bị chiếm (mọi box nhãn, nới 6px) -> không dán đè."""
    occ = np.zeros((H, W), np.uint8)
    for c, xc, yc, w, h in labels:
        x1, y1 = int((xc - w / 2) * W) - 6, int((yc - h / 2) * H) - 6
        x2, y2 = int((xc + w / 2) * W) + 6, int((yc + h / 2) * H) + 6
        occ[max(0, y1):y2, max(0, x1):x2] = 1
    return occ


def make_patch(src_img, e, bg):
    x1, y1, x2, y2 = [int(round(v)) for v in e["box"]]
    if (x2 - x1) >= (y2 - y1): x1, x2 = x1 + INSET, x2 - INSET       # cạnh ngang: cắt 2 đầu trái/phải
    else:                      y1, y2 = y1 + INSET, y2 - INSET       # cạnh dọc : cắt 2 đầu trên/dưới
    if x2 - x1 < 6 or y2 - y1 < 6: return None
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(src_img.shape[1], x2), min(src_img.shape[0], y2)
    crop = src_img[y1:y2, x1:x2].copy()
    if crop.size == 0 or min(crop.shape[:2]) < 6:
        return None
    mask = ink_mask(crop, bg)
    return crop, mask


def rotate_patch(crop, mask, deg, scale):
    h, w = crop.shape[:2]
    pad = int(max(h, w) * 0.4) + 4
    cp = cv2.copyMakeBorder(crop, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
    mk = cv2.copyMakeBorder(mask, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    H, W = cp.shape[:2]
    M = cv2.getRotationMatrix2D((W / 2, H / 2), deg, scale)
    cp = cv2.warpAffine(cp, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    mk = cv2.warpAffine(mk, M, (W, H), flags=cv2.INTER_LINEAR)
    ys, xs = np.where(mk > 40)
    if len(xs) < 10:
        return None
    x1, x2, y1, y2 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1     # box ôm sát phần mực sau xoay
    return cp[y1:y2, x1:x2], mk[y1:y2, x1:x2]


def try_paste(dst, patch, mask, occ, tries=40):
    """Trả box NHÃN = vùng patch nới INSET ở 2 đầu (giống box gốc = đoạn + BOX_PAD)."""
    ph, pw = patch.shape[:2]
    H, W = dst.shape[:2]
    ex, ey = (INSET, 0) if pw >= ph else (0, INSET)
    if ph + 2 * ey >= H - 4 or pw + 2 * ex >= W - 4:
        return None
    for _ in range(tries):
        x = random.randint(2 + ex, W - pw - 2 - ex)
        y = random.randint(2 + ey, H - ph - 2 - ey)
        if occ[y - ey:y + ph + ey, x - ex:x + pw + ex].any():
            continue
        a = (mask.astype(np.float32) / 255.0)[..., None]
        roi = dst[y:y + ph, x:x + pw].astype(np.float32)
        dst[y:y + ph, x:x + pw] = (a * patch + (1 - a) * roi).astype(np.uint8)
        occ[max(0, y - ey - 6):y + ph + ey + 6, max(0, x - ex - 6):x + pw + ex + 6] = 1
        return x - ex, y - ey, x + pw + ex, y + ph + ey
    return None


def to_yolo(cls, box, W, H):
    x1, y1, x2, y2 = box
    return f"{cls} {((x1+x2)/2)/W:.6f} {((y1+y2)/2)/H:.6f} {(x2-x1)/W:.6f} {(y2-y1)/H:.6f}"


def link(s, d):
    if os.path.exists(d): return
    try: os.link(s, d)
    except Exception: shutil.copy(s, d)


def main():
    SRC_I, SRC_L = f"{BASE}/images/train", f"{BASE}/labels/train"
    for sub in ("images/train", "labels/train", "images/val", "labels/val"):
        os.makedirs(f"{OUT}/{sub}", exist_ok=True)
    ids = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(f"{SRC_I}/*.jpg"))

    # 1) Thư viện cạnh
    bank, combo_cnt = [], Counter()
    for i in ids:
        im = cv2.imread(f"{SRC_I}/{i}.jpg"); H, W = im.shape[:2]
        bg = bg_color(im)
        for e in group_edges(read_labels(f"{SRC_L}/{i}.txt"), W, H):
            look = [c for c in e["cls"] if c in LOOK]
            icon = [c for c in e["cls"] if c in ONEWAY or c in (STAIRS, CLOSED)]
            key = (look[0] if look else -1, 'oneway' if set(icon) & ONEWAY else ('stairs' if STAIRS in icon else ('closed' if CLOSED in icon else 'plain')))
            e.update(src=i, key=key, bg=bg)
            bank.append(e); combo_cnt[key] += 1
    top = max(combo_cnt.values())
    weights = np.array([(top / combo_cnt[e["key"]]) ** (RARE_BOOST / 2) for e in bank]); weights /= weights.sum()
    print(f"Thư viện: {len(bank)} cạnh | tổ hợp:", dict(combo_cnt))

    # 2) Ảnh gốc
    for i in ids:
        link(f"{SRC_I}/{i}.jpg", f"{OUT}/images/train/{i}.jpg")
        link(f"{SRC_L}/{i}.txt", f"{OUT}/labels/train/{i}.txt")

    # 3) Sinh ảnh copy-paste
    new_combo = Counter()
    for n in range(N_PASTE_IMGS):
        i = random.choice(ids)
        dst = cv2.imread(f"{SRC_I}/{i}.jpg"); H, W = dst.shape[:2]
        labels = read_labels(f"{SRC_L}/{i}.txt")
        occ = free_space(labels, W, H)
        new_lines = [f"{c} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}" for c, xc, yc, w, h in labels]
        added = 0
        for _ in range(random.randint(*EDGES_PER_IMG)):
            e = bank[np.random.choice(len(bank), p=weights)]
            src = cv2.imread(f"{SRC_I}/{e['src']}.jpg")
            got = make_patch(src, e, e["bg"])
            if got is None: continue
            crop, mask = got
            # nền ảnh đích khác nền ảnh nguồn -> thay nền nguồn bằng nền đích (mask đã tách mực)
            bg_dst = bg_color(dst)
            crop = np.where(mask[..., None] > 0, crop, bg_dst.astype(np.uint8)).astype(np.uint8)
            r = rotate_patch(crop, mask, random.uniform(-ROT_DEG, ROT_DEG), random.uniform(*SCALE_RANGE))
            if r is None: continue
            box = try_paste(dst, r[0], r[1], occ)
            if box is None: continue
            for c in e["cls"]:                               # nét + icon cùng 1 box, giống build_split
                new_lines.append(to_yolo(c, box, W, H))
            new_combo[e["key"]] += 1; added += 1
        if added == 0: continue
        name = f"{i}_cp{n}"
        cv2.imwrite(f"{OUT}/images/train/{name}.jpg", dst)
        open(f"{OUT}/labels/train/{name}.txt", "w").write("\n".join(new_lines))

    # 4) val thật
    for p in glob.glob(f"{BASE}/images/val/*.jpg"):
        n = os.path.basename(p)[:-4]
        link(p, f"{OUT}/images/val/{n}.jpg"); link(f"{BASE}/labels/val/{n}.txt", f"{OUT}/labels/val/{n}.txt")

    from_names = yaml.safe_load(open(f"{BASE}/data.yaml", encoding="utf-8"))["names"]
    yaml.dump({"train": f"{OUT}/images/train", "val": f"{OUT}/images/val",
               "nc": len(from_names), "names": from_names}, open(f"{OUT}/data.yaml", "w", encoding="utf-8"), sort_keys=False)
    for c in glob.glob(f"{OUT}/labels/*.cache"): os.remove(c)
    print("Cạnh dán thêm theo tổ hợp:", dict(new_combo))
    print("Ảnh train:", len(glob.glob(f"{OUT}/images/train/*.jpg")))


def preview(k=4):
    """Vẽ box nhãn lên vài ảnh _cp để mắt thường kiểm tra TRƯỚC khi train."""
    import matplotlib.pyplot as plt
    ps = sorted(glob.glob(f"{OUT}/images/train/*_cp*.jpg"))[:k]
    fig, ax = plt.subplots(1, len(ps), figsize=(6 * len(ps), 6))
    for a, p in zip(np.atleast_1d(ax), ps):
        im = cv2.imread(p)[:, :, ::-1].copy(); H, W = im.shape[:2]
        for c, xc, yc, w, h in read_labels(p.replace("images", "labels")[:-4] + ".txt"):
            if c in EDGE_ALL:
                cv2.rectangle(im, (int((xc-w/2)*W), int((yc-h/2)*H)), (int((xc+w/2)*W), int((yc+h/2)*H)), (255, 0, 0), 1)
        a.imshow(im); a.axis("off"); a.set_title(os.path.basename(p))
    plt.show()


if __name__ == "__main__":
    main()
