# =====================================================================
# robot_fit3.py - FIT chi phí cho TẤT CẢ robot 0..8 (robot 9 là tham lam, giữ nguyên).
#
# KHÁC fit2:
#  1) AN TOÀN NAMESPACE: mọi tên đều có tiền tố f3_/_F3_. File KHÔNG ghi đè bất kỳ biến nào của
#     notebook (fit2 ghi đè TIE_BREAKER dict -> tuple nên simulate_robot_dijkstra ném TypeError
#     ở mọi scene, pipeline bắt lỗi và gán 0 => "0 hết luôn").
#  2) Học bằng QUY HOẠCH TUYẾN TÍNH (LP) thay perceptron: mỗi ca sai cho 1 ràng buộc
#        w . (đặc trưng đường đúng - đặc trưng đường đoán) <= 0
#     LP tìm w thỏa mọi ràng buộc, rồi tính KHOẢNG [min,max] của từng tham số mà vẫn thỏa
#     (tương đương "vùng phẳng" của đường cong điểm, nhưng cho mọi tham số cùng lúc),
#     sau đó chọn giá trị tròn trong khoảng, ưu tiên giữ giá trị cũ / 0.
#  3) Nếu LP không thỏa được (còn slack) => bộ đặc trưng chưa đủ: in các ca không giải thích được,
#     phân loại "hòa điểm" (luật phá hòa) / "lệch chi phí" (thiếu đặc trưng) / "không dựng được đường".
#
# Mô hình: cost 1 đoạn = 1 + tổng phạt áp dụng. Đặc trưng:
#   crowded_dry crowded_rain covered_dry covered_rain   right left uturn
#   oneway (đoạn một chiều)  oneway_crowded (đoạn một chiều VÀ đông, phạt thêm)
#   stairs_dry stairs_rain (chỉ robot 4)
# Robot 6 tách ngữ cảnh urgent/calm, robot 7 tách fragile/normal (mỗi nhóm 1 bộ phạt riêng).
#
#   exec(open('/content/robot_fit3.py').read())
#   f3_load()            # nạp train + validation
#   f3_overview()        # điểm hiện tại mọi robot (so với điểm notebook để kiểm tra bản sao đúng)
#   f3_fit(7)            # fit 1 robot      |  f3_fit_all()  # mọi robot chưa 100%
#   f3_diagnose(7)       # in các ca còn sai + nguyên nhân
#   f3_export()          # ghi /content/calculate_cost_final.py (dán thay calculate_cost)
# =====================================================================
import copy, heapq, json, math, random, time
from collections import Counter
from multiprocessing import cpu_count, get_context
from pathlib import Path

import numpy as np

_F3_ROOT = Path('/content/dataset/Phenikaa_Campus_Courier_2026_v3/delivery_public')  # sửa nếu đường dẫn khác

_F3_DIRS = {(-1, 0): 0, (0, 1): 1, (1, 0): 2, (0, -1): 3}      # UP RIGHT DOWN LEFT
_F3_HEAD = {"UP": 0, "RIGHT": 1, "DOWN": 2, "LEFT": 3}
_F3_SUB = {0: 0, 2: 1, 3: 2, 1: 3}                              # hướng tuyệt đối -> nhãn nộp bài
_F3_DELTA = {0: (-1, 0), 1: (1, 0), 2: (0, -1), 3: (0, 1)}      # nhãn nộp bài -> (dr,dc)
_F3_TIE = (0, 1, 3, 2)                                          # (nh-h)%4: thẳng,phải,quay đầu,trái

_F3_FEATS = ['crowded_dry', 'crowded_rain', 'covered_dry', 'covered_rain', 'right', 'left',
             'uturn', 'oneway', 'oneway_crowded', 'stairs_dry', 'stairs_rain']
_F3_K = len(_F3_FEATS)
_F3_I = {f: i for i, f in enumerate(_F3_FEATS)}
# cận dưới (cost 1 đoạn luôn >= 0.2 để Dijkstra hợp lệ) / cận trên
_F3_LB = {'covered_dry': -0.8, 'covered_rain': -0.8}
_F3_UB = 3000.0
_F3_EPS = 1e-3


def _f3_w(**kw):
    d = {f: 0.0 for f in _F3_FEATS}
    d.update(kw)
    return d


# Trọng số khởi đầu = luật hiện tại của bạn (robot 4 = nghiệm đã fit 100%)
F3W = {
    0: {'all': _f3_w()},
    1: {'all': _f3_w(crowded_dry=5.0, crowded_rain=5.0)},
    2: {'all': _f3_w(covered_dry=-0.5, covered_rain=-0.5)},
    3: {'all': _f3_w(crowded_dry=2.0, covered_rain=-0.75)},
    4: {'all': _f3_w(crowded_dry=1.0, crowded_rain=1.0, stairs_rain=4.0)},
    5: {'all': _f3_w(right=50.0, left=50.0, uturn=1000.0)},
    6: {'urgent': _f3_w(), 'calm': _f3_w(crowded_dry=5.0, crowded_rain=5.0, covered_dry=-0.25, covered_rain=-0.25)},
    7: {'fragile': _f3_w(crowded_dry=5.0, crowded_rain=5.0, right=0.5, left=0.5, uturn=10.0), 'normal': _f3_w()},
    8: {'all': _f3_w(right=0.5, left=5.0, uturn=10.0)},
    9: {'all': _f3_w(crowded_dry=2.0, crowded_rain=2.0)},
}
F3W_INIT = copy.deepcopy(F3W)
# điểm notebook của bạn (để so khi chạy f3_overview với trọng số khởi đầu CŨ, robot 4 chưa fix)
F3_NOTEBOOK_ACC = {3: 99.87, 5: 99.30, 6: 99.74, 7: 98.70, 8: 99.78}

_F3D = {}
_F3_ADJ = {}


def _f3_ctx(robot, scene):
    m = scene['mission']
    if robot == 6:
        return 'urgent' if m.get('urgent', False) else 'calm'
    if robot == 7:
        return 'fragile' if m.get('fragile', False) else 'normal'
    return 'all'


def _f3_vec(wdict):
    return [wdict[f] for f in _F3_FEATS]


def _f3_vecs(robot, W=None):
    W = F3W if W is None else W
    return {c: _f3_vec(d) for c, d in W[robot].items()}


def f3_load(splits=('train', 'validation'), root=_F3_ROOT):
    sc_all, lb_all, sp_all = [], [], []
    for sp in splits:
        sc = json.load(open(Path(root) / sp / 'scenes.json', encoding='utf-8'))
        lb = json.load(open(Path(root) / sp / 'labels.json', encoding='utf-8'))
        assert len(lb) == len(sc) * 10
        for i, s in enumerate(sc):
            sc_all.append(s)
            lb_all.append(lb[i * 10:(i + 1) * 10])
            sp_all.append(sp)
    _F3D.update(scenes=sc_all, labels=lb_all, split=sp_all)
    _F3_ADJ.clear()
    print("Đã nạp %d scene: %s" % (len(sc_all), ", ".join("%s=%d" % kv for kv in Counter(sp_all).items())))


def _f3_adj(i, robot):
    key = (i, robot == 4)
    if key in _F3_ADJ:
        return _F3_ADJ[key]
    sc = _F3D['scenes'][i]
    rain = sc.get('weather') == 'rain'
    E = {}
    for e in sc['edges']:
        if e['status'] == 'closed':
            continue
        if e.get('stairs', False) and robot != 4:
            continue
        u, v = tuple(e['a']), tuple(e['b'])
        ow = e.get('oneway_to')
        if ow is None:
            E[(u, v)] = e
            E[(v, u)] = e
        else:
            dest = tuple(ow)
            if dest == v:
                E[(u, v)] = e
            elif dest == u:
                E[(v, u)] = e
    adj = {}
    for (u, v), e in E.items():
        nh = _F3_DIRS.get((v[0] - u[0], v[1] - u[1]))
        if nh is None:
            continue
        st = e['status']
        f = []
        if st == 'crowded':
            f.append(1 if rain else 0)
        elif st == 'covered':
            f.append(3 if rain else 2)
        if e.get('oneway_to') is not None:
            f.append(7)
            if st == 'crowded':
                f.append(8)
        if e.get('stairs', False):
            f.append(10 if rain else 9)
        adj.setdefault(u, []).append((v, nh, tuple(f)))
        adj.setdefault(v, adj.get(v, []))
    _F3_ADJ[key] = adj
    return adj


def _f3_nodes(scene, node_type, ref):
    if not node_type:
        return []
    if ref and ref.get('rc'):
        return [tuple(ref['rc'])]
    return [tuple(lm['rc']) for lm in scene['landmarks'] if lm['type'] == node_type]


def _f3_dij(adj, src, h0, wv, force=None):
    best = {(src, h0): (0.0, (), None, None)}
    pq = [(0.0, (), src, h0)]
    while pq:
        cost, tie, node, h = heapq.heappop(pq)
        b = best[(node, h)]
        if cost > b[0] or (cost == b[0] and tie > b[1]):
            continue
        for nb, nh, stat in adj.get(node, ()):
            if force is not None and cost == 0.0 and node == src and h == h0 and nb != force:
                continue
            turn = (nh - h) % 4
            c = 1.0
            for k in stat:
                c += wv[k]
            if turn == 1:
                c += wv[4]
            elif turn == 3:
                c += wv[5]
            elif turn == 2:
                c += wv[6]
            nc = round(cost + c, 9)
            nt = tie + (_F3_TIE[turn],)
            cur = best.get((nb, nh))
            if cur is None or nc < cur[0] or (nc == cur[0] and nt < cur[1]):
                best[(nb, nh)] = (nc, nt, (node, h), (turn, stat))
                heapq.heappush(pq, (nc, nt, nb, nh))
    return best


def _f3_chain(best, state):
    phi = [0] * (_F3_K + 1)
    first = None
    while True:
        _, _, prev, info = best[state]
        if prev is None:
            break
        turn, stat = info
        phi[_F3_K] += 1
        for k in stat:
            phi[k] += 1
        if turn == 1:
            phi[4] += 1
        elif turn == 3:
            phi[5] += 1
        elif turn == 2:
            phi[6] += 1
        first = state[0]
        state = prev
    return phi, first


def _f3_plan(i, robot, vecs, force=None, cache=None):
    """(action, cost, tie, phi) của lựa chọn tối ưu; force = nhãn nộp bài ép bước đầu. None nếu không có đường."""
    sc = _F3D['scenes'][i]
    adj = _f3_adj(i, robot)
    start = tuple(sc['robot']['rc'])
    if start not in adj:
        return None
    h0 = _F3_HEAD[sc['robot']['heading']]
    wv = vecs[_f3_ctx(robot, sc)]
    m = sc['mission']
    vias = _f3_nodes(sc, m.get('via'), m.get('via_ref'))
    goals = _f3_nodes(sc, m.get('goal'), m.get('goal_ref'))
    ff = None
    if force is not None:
        dr, dc = _F3_DELTA[force]
        ff = (start[0] + dr, start[1] + dc)
    s1 = _f3_dij(adj, start, h0, wv, ff)
    res = None
    if vias:
        cache = {} if cache is None else cache
        for via in vias:
            for vh in range(4):
                if (via, vh) not in s1:
                    continue
                c1, t1, _, _ = s1[(via, vh)]
                ck = (via, vh)
                if ck not in cache:
                    vc = _f3_dij(adj, via, vh, wv)
                    bg = None
                    for g in goals:
                        for gh in range(4):
                            if (g, gh) not in vc:
                                continue
                            c2, t2, _, _ = vc[(g, gh)]
                            if bg is None or c2 < bg[0] or (c2 == bg[0] and t2 < bg[1]):
                                bg = (c2, t2, _f3_chain(vc, (g, gh))[0])
                    cache[ck] = bg
                bg = cache[ck]
                if bg is None:
                    continue
                tc, tt = round(c1 + bg[0], 9), t1 + bg[1]
                if res is None or tc < res[0] or (tc == res[0] and tt < res[1]):
                    res = (tc, tt, s1, (via, vh), bg[2])
        if res is None:
            return None
        phi1, first = _f3_chain(res[2], res[3])
        phi = [a + b for a, b in zip(phi1, res[4])]
        cost, tie = res[0], res[1]
    else:
        for g in goals:
            for gh in range(4):
                if (g, gh) not in s1:
                    continue
                c, t, _, _ = s1[(g, gh)]
                if res is None or c < res[0] or (c == res[0] and t < res[1]):
                    res = (c, t, g, gh)
        if res is None:
            return None
        phi, first = _f3_chain(s1, (res[2], res[3]))
        cost, tie = res[0], res[1]
    if first is None:
        return None
    a = _F3_SUB[_F3_DIRS[(first[0] - start[0], first[1] - start[1])]]
    return a, cost, tie, phi


def _f3_pred(i, robot, vecs):
    try:
        r = _f3_plan(i, robot, vecs)
    except Exception:
        return -1
    return -1 if r is None else r[0]


def _f3_alts(i, robot, vecs):
    """{nhãn: (cost, tie, phi)} cho từng bước đầu khả dụng (đường tốt nhất ép bước đó)."""
    sc = _F3D['scenes'][i]
    adj = _f3_adj(i, robot)
    start = tuple(sc['robot']['rc'])
    out = {}
    cache = {}
    for a, (dr, dc) in _F3_DELTA.items():
        nb = (start[0] + dr, start[1] + dc)
        if not any(x[0] == nb for x in adj.get(start, ())):
            continue
        try:
            r = _f3_plan(i, robot, vecs, force=a, cache=cache)
        except Exception:
            r = None
        if r is not None:
            out[a] = (r[1], r[2], r[3])
    return out


# ---------------------------------------------------------------------
# Chấm điểm (song song, trọng số truyền tường minh - không dùng biến toàn cục thay đổi)
# ---------------------------------------------------------------------
def _f3_wrong_task(args):
    robot, vecs, idx = args
    L = _F3D['labels']
    return [i for i in idx if _f3_pred(i, robot, vecs) != L[i][robot]]


def f3_wrong(robot, idx=None, workers=None, W=None, pool=None):
    idx = list(range(len(_F3D['scenes']))) if idx is None else list(idx)
    vecs = _f3_vecs(robot, W)
    workers = workers if workers is not None else max(1, cpu_count())
    if workers <= 1 or len(idx) < 200:
        return _f3_wrong_task((robot, vecs, idx))
    chunks = [idx[k::workers * 3] for k in range(workers * 3)]
    own = pool is None
    pool = pool or get_context('fork').Pool(workers)
    try:
        out = pool.map(_f3_wrong_task, [(robot, vecs, c) for c in chunks if c])
    finally:
        if own:
            pool.close()
            pool.join()
    return sorted(i for part in out for i in part)


def _f3_acc(idx_all, wrong, sel):
    s = set(sel)
    n = len(s)
    return n - len(s & set(wrong)), n


def f3_overview(robots=range(0, 9), workers=None, W=None):
    sp = _F3D['split']
    allidx = list(range(len(sp)))
    tr = [i for i in allidx if sp[i] == 'train']
    va = [i for i in allidx if sp[i] != 'train']
    for r in robots:
        t0 = time.time()
        wr = f3_wrong(r, allidx, workers, W)
        a, n = _f3_acc(allidx, wr, allidx)
        note = ''
        if r in F3_NOTEBOOK_ACC and abs(100 * a / n - F3_NOTEBOOK_ACC[r]) > 0.02 and W is None:
            note = '   <-- notebook báo %.2f%%' % F3_NOTEBOOK_ACC[r]
        print("Robot %d: %d/%d = %.2f%%  train %d/%d  val %d/%d  (%d sai, %.0fs)%s" % (
            r, a, n, 100 * a / n, _f3_acc(allidx, wr, tr)[0], len(tr), _f3_acc(allidx, wr, va)[0], len(va),
            len(wr), time.time() - t0, note))


# ---------------------------------------------------------------------
# Ràng buộc từ nhãn
# ---------------------------------------------------------------------
def _f3_cons_from(i, robot, vecs, label, alts=None):
    """Danh sách ràng buộc (ctx, d, rhs) bảo đảm bước 'label' thắng mọi bước đầu khác."""
    alts = _f3_alts(i, robot, vecs) if alts is None else alts
    if label not in alts:
        return None, []
    cT, tT, pT = alts[label]
    ctx = _f3_ctx(robot, _F3D['scenes'][i])
    out = []
    for b, (cQ, tQ, pQ) in alts.items():
        if b == label:
            continue
        d = tuple(x - y for x, y in zip(pT[:_F3_K], pQ[:_F3_K]))
        if not any(d):
            continue
        dlen = pT[_F3_K] - pQ[_F3_K]                      # chi phí nền 1/đoạn: cost = độ dài + w.phi
        out.append((ctx, d, -dlen, not (tT < tQ)))      # (ctx, d, rhs, strict): w.d <= rhs (strict: <= rhs-EPS)
    return alts, out


def _f3_bounds(robot):
    lb, ub = {}, {}
    for ctx in F3W[robot]:
        for f in _F3_FEATS:
            lo = _F3_LB.get(f, 0.0)
            hi = _F3_UB
            if f.startswith('stairs') and robot != 4:
                lo = hi = 0.0
            lb[(ctx, f)] = lo
            ub[(ctx, f)] = hi
    return lb, ub


def _f3_lp(robot, cons, w_prev, fixed=None, obj=None, slack_cap=None, trust=False, relax=False):
    """Giải LP. obj=None: min tổng slack (+ gần w_prev). obj=(ctx,f,+1/-1): min/max 1 biến dưới slack_cap."""
    from scipy.optimize import linprog
    from scipy.sparse import lil_matrix
    ctxs = list(F3W[robot].keys())
    nv = len(ctxs) * _F3_K
    m = len(cons)
    lb, ub = _f3_bounds(robot)
    ci = {c: j for j, c in enumerate(ctxs)}
    nvar = nv + m + nv
    A = lil_matrix((m + 2 * nv + (1 if slack_cap is not None else 0), nvar))
    b = []
    for j, (ctx, d, rhs, strict) in enumerate(cons):
        if strict and not relax:
            rhs = rhs - _F3_EPS
        base = ci[ctx] * _F3_K
        for k, dk in enumerate(d):
            if dk:
                A[j, base + k] = dk
        A[j, nv + j] = -1.0
        b.append(rhs)
    r = m
    wp = []
    for c in ctxs:
        for f in _F3_FEATS:
            wp.append(w_prev[c][f])
    for v in range(nv):
        A[r, v] = 1.0
        A[r, nv + m + v] = -1.0
        b.append(wp[v])
        r += 1
        A[r, v] = -1.0
        A[r, nv + m + v] = -1.0
        b.append(-wp[v])
        r += 1
    if slack_cap is not None:
        for j in range(m):
            A[r, nv + j] = 1.0
        b.append(slack_cap)
        r += 1
    bounds = []
    for c in ctxs:
        for f in _F3_FEATS:
            lo, hi = lb[(c, f)], ub[(c, f)]
            if trust:
                dl = 0.5 + 0.2 * abs(w_prev[c][f])
                lo, hi = max(lo, w_prev[c][f] - dl), min(hi, w_prev[c][f] + dl)
            if fixed and (c, f) in fixed:
                lo = hi = fixed[(c, f)]
            bounds.append((lo, hi))
    bounds += [(0, None)] * m + [(0, None)] * nv
    cvec = np.zeros(nvar)
    if obj is None:
        cvec[nv:nv + m] = 1000.0
        cvec[nv + m:] = 1e-3
    else:
        ctx, f, sgn = obj
        cvec[ci[ctx] * _F3_K + _F3_I[f]] = sgn
    res = linprog(cvec, A_ub=A.tocsr(), b_ub=np.array(b), bounds=bounds, method='highs')
    if res.status != 0:
        return None
    x = res.x
    w = {c: {f: float(x[ci[c] * _F3_K + k]) for k, f in enumerate(_F3_FEATS)} for c in ctxs}
    return w, float(x[nv:nv + m].sum())


def _f3_interval(robot, cons, w_prev, fixed, slack_cap, relax=False):
    out = {}
    for ctx in F3W[robot]:
        for f in _F3_FEATS:
            if (ctx, f) in fixed:
                out[(ctx, f)] = (fixed[(ctx, f)], fixed[(ctx, f)])
                continue
            lo = _f3_lp(robot, cons, w_prev, fixed, (ctx, f, +1), slack_cap, relax=relax)
            hi = _f3_lp(robot, cons, w_prev, fixed, (ctx, f, -1), slack_cap, relax=relax)
            if lo is None or hi is None:
                continue
            out[(ctx, f)] = (lo[0][ctx][f], hi[0][ctx][f])
    return out


def _f3_nice(lo, hi, init):
    """Giá trị 'đẹp' nhất trong [lo,hi]: giữ giá trị cũ nếu nằm trong khoảng, rồi 0, số nguyên, .5, .25, .1."""
    tol = 1e-5
    if lo - tol <= init <= hi + tol:
        return init
    if lo - tol <= 0 <= hi + tol:
        return 0.0
    for step in (1.0, 0.5, 0.25, 0.1, 0.05, 0.01):
        a = math.ceil((lo - tol) / step)
        b = math.floor((hi + tol) / step)
        if a <= b:
            if hi > 5 * max(lo, 1e-9) and hi > 40:       # khoảng rất rộng: lấy số tròn 1/2/5 x 10^k gần tâm hình học
                best, bd = None, None
                c0 = math.sqrt(max(lo, 1.0) * hi)
                for e in range(0, 5):
                    for mant in (1, 2, 5):
                        v = mant * 10 ** e
                        if lo - tol <= v <= hi + tol:
                            d = abs(math.log(v / c0))
                            if bd is None or d < bd:
                                best, bd = float(v), d
                if best is not None:
                    return best
            mid = (lo + hi) / 2
            vals = [k * step for k in range(a, b + 1)]
            return min(vals, key=lambda v: (abs(v - mid), v))
    return (lo + hi) / 2


def _f3_snapshot(robot):
    return copy.deepcopy(F3W[robot])


def f3_show(robot):
    for ctx, d in F3W[robot].items():
        nz = {f: round(v, 4) for f, v in d.items() if abs(v) > 1e-12}
        print("   [%s] %s   (cost đoạn = 1 + tổng phạt áp dụng)" % (ctx, nz))


# ---------------------------------------------------------------------
# Chẩn đoán các ca sai
# ---------------------------------------------------------------------
def f3_diagnose(robot, idx=None, max_show=15, workers=None):
    idx = list(range(len(_F3D['scenes']))) if idx is None else list(idx)
    wr = f3_wrong(robot, idx, workers)
    vecs = _f3_vecs(robot)
    print("Robot %d: %d ca sai" % (robot, len(wr)))
    cat = Counter()
    agg = Counter()
    shown = 0
    for i in wr:
        sc = _F3D['scenes'][i]
        lab = _F3D['labels'][i][robot]
        alts = _f3_alts(i, robot, vecs)
        p = _f3_plan(i, robot, vecs)
        head = "[%s] %s ctx=%s via=%s heading=%s nhãn=%s đoán=%s" % (
            sc.get('scene_id'), sc.get('weather'), _f3_ctx(robot, sc), bool(sc['mission'].get('via')),
            sc['robot']['heading'], lab, None if p is None else p[0])
        if lab not in alts or p is None:
            cat['không dựng được đường'] += 1
            if shown < max_show:
                print(head, "-> không dựng được đường (nhãn bị chặn / không có đường)")
                shown += 1
            continue
        cT, tT, pT = alts[lab]
        cP = p[1]
        d = {_F3_FEATS[k]: pT[k] - p[3][k] for k in range(_F3_K) if pT[k] != p[3][k]}
        if abs(cT - cP) < 1e-9:
            cat['HÒA ĐIỂM (cost bằng nhau -> luật phá hòa)'] += 1
            kind = 'hòa'
        else:
            cat['LỆCH CHI PHÍ (cần đổi tham số / thiếu đặc trưng)'] += 1
            kind = 'lệch'
            for k, v in d.items():
                agg[(k, '+' if v > 0 else '-')] += 1
        if shown < max_show:
            print("%s\n     %s cost(đúng)=%.3f cost(đoán)=%.3f  Δ(đúng-đoán)=%s" % (head, kind, cT, cP, d))
            shown += 1
    print("\nPhân loại:")
    for k, v in cat.most_common():
        print("   %-55s %d" % (k, v))
    if agg:
        print("Đặc trưng mà đường ĐÚNG nhiều hơn(+)/ít hơn(-) đường đoán (chỉ ca lệch chi phí):")
        for (k, s), c in agg.most_common(8):
            print("   %-16s %s  %d ca" % (k, s, c))
    return wr


# ---------------------------------------------------------------------
# FIT 1 ROBOT
# ---------------------------------------------------------------------
def f3_fit(robot, max_iter=25, workers=None, verbose=True, pins=None):
    """pins={'crowded_dry': 4, 'fragile.uturn': 8}: ép giá trị tròn bạn đã chọn (khóa 'ctx.feature' hoặc 'feature').
       Pha A: tìm w đúng nhãn bằng LP vùng tin cậy (ràng buộc dựng lại mỗi vòng từ tập 'ca từng sai').
       Pha B: dựng ràng buộc sát từ MỌI scene, tính khoảng hợp lệ của từng tham số, chọn số đẹp, kiểm tra lại."""
    t0 = time.time()
    sp = _F3D['split']
    allidx = list(range(len(sp)))
    tr = [i for i in allidx if sp[i] == 'train']
    va = [i for i in allidx if sp[i] != 'train']
    L = _F3D['labels']
    backup = _f3_snapshot(robot)
    workers = workers if workers is not None else max(1, cpu_count())
    pool = get_context('fork').Pool(workers) if workers > 1 else None
    unexplained = set()

    def build(idxs, vecs):
        cons = {}
        for i in idxs:
            alts, lst = _f3_cons_from(i, robot, vecs, L[i][robot])
            if alts is None or not lst:
                unexplained.add(i)
                continue
            for c in lst:
                cons[c] = 1
        return list(cons.keys())

    try:
        wr = f3_wrong(robot, allidx, workers, pool=pool)
        a0 = len(allidx) - len(wr)
        print("\n=== ROBOT %d: %d/%d (%.2f%%) trước khi fit" % (robot, a0, len(allidx), 100 * a0 / len(allidx)))
        if not wr:
            print("   đã 100% -> bỏ qua")
            return a0, a0
        # ---------------- Pha A ----------------
        active = set(wr)
        best_err, best_w = len(wr), _f3_snapshot(robot)
        for it in range(max_iter):
            cons = build(sorted(active - unexplained), _f3_vecs(robot))
            sol = _f3_lp(robot, cons, F3W[robot], trust=True)
            if sol is None:
                print("   LP vô nghiệm"); break
            F3W[robot], slack = sol
            wr = f3_wrong(robot, allidx, workers, pool=pool)
            fresh = set(wr) - active
            if verbose:
                print("   [A%d] ràng buộc %d | slack %.4f | sai %d/%d | ca mới sai %d | không giải thích được %d" % (
                    it + 1, len(cons), slack, len(wr), len(allidx), len(fresh), len(unexplained)))
            if len(wr) < best_err:
                best_err, best_w = len(wr), _f3_snapshot(robot)
            active |= set(wr)
            if not wr or set(wr) <= unexplained:
                break
        if len(wr) > best_err:
            F3W[robot] = best_w
            wr = f3_wrong(robot, allidx, workers, pool=pool)
        # ---------------- Pha B ----------------
        for rnd in range(3):
            if not wr:
                pass
            vecs = _f3_vecs(robot)
            cons = build(allidx, vecs)
            rx = (rnd == 0)           # vòng đầu: đa diện đóng (hòa điểm ở biên được phép), vòng sau: chặt
            sol = _f3_lp(robot, cons, F3W[robot], relax=rx)
            if sol is None:
                break
            wbest, s_star = sol
            cap = s_star + 1e-6
            iv0 = _f3_interval(robot, cons, wbest, {}, cap, rx)
            if verbose and rnd == 0:
                print("\n   KHOẢNG hợp lệ của từng tham số (từ %d ràng buộc 'sát' của mọi scene, slack*=%.4f):" % (len(cons), s_star))
                for (c, f), (lo, hi) in iv0.items():
                    if f.startswith('stairs') and robot != 4:
                        continue
                    if hi - lo > 1e-6 or abs(wbest[c][f]) > 1e-9 or abs(F3W_INIT[robot][c][f]) > 1e-9:
                        print("      [%s] %-15s [%9.3f , %9.3f]%s   (cũ %.3f)" % (
                            c, f, lo, hi, '  <-- còn tự do' if hi - lo > 1e-3 else '', F3W_INIT[robot][c][f]))
            fixed = {}
            order = [(c, f) for c in F3W[robot] for f in _F3_FEATS if not (f.startswith('stairs') and robot != 4)]
            for key, val in (pins or {}).items():              # giá trị bạn chốt tay
                for (c, f) in order:
                    if key == f or key == "%s.%s" % (c, f):
                        trial = dict(fixed)
                        trial[(c, f)] = float(val)
                        s2 = _f3_lp(robot, cons, wbest, trial, None, cap, relax=rx)
                        if s2 is None:
                            print("   !! pin %s=%s không khớp ràng buộc -> bỏ qua pin này" % (key, val))
                        else:
                            fixed[(c, f)] = float(val)
            # đặc trưng có giá trị cũ = 0 (thưa) chốt trước; còn lại chốt từ khoảng hẹp đến rộng
            order = [cf for cf in order if cf not in fixed]
            order.sort(key=lambda cf: (abs(F3W_INIT[robot][cf[0]][cf[1]]) > 0,
                                       (iv0[cf][1] - iv0[cf][0]) if cf in iv0 else 0.0))
            for (c, f) in order:
                iv = _f3_interval(robot, cons, wbest, fixed, cap, rx).get((c, f))
                if iv is None:
                    fixed[(c, f)] = wbest[c][f]
                    continue
                fixed[(c, f)] = _f3_nice(iv[0], iv[1], F3W_INIT[robot][c][f])
                s2 = _f3_lp(robot, cons, wbest, fixed, None, cap, relax=rx)
                if s2 is not None:
                    wbest = s2[0]
            F3W[robot] = {c: {f: fixed.get((c, f), wbest[c][f]) for f in _F3_FEATS} for c in F3W[robot]}
            wr = f3_wrong(robot, allidx, workers, pool=pool)
            if verbose:
                print("   [B%d: chọn số đẹp] sai %d/%d" % (rnd + 1, len(wr), len(allidx)))
            if not wr or set(wr) <= unexplained:
                break
    finally:
        if pool:
            pool.close()
            pool.join()
    a1 = len(allidx) - len(wr)
    try:
        cons_f = build(allidx, _f3_vecs(robot))
        solf = _f3_lp(robot, cons_f, F3W[robot], relax=True)
        if solf is not None:
            capf = solf[1] + 1e-6
            print("\n   ĐỘ CHẮC của từng giá trị đã chọn (khoảng khi mọi tham số KHÁC giữ nguyên):")
            for c in F3W[robot]:
                for f in _F3_FEATS:
                    if f.startswith('stairs') and robot != 4:
                        continue
                    v = F3W[robot][c][f]
                    fx = {(c2, f2): F3W[robot][c2][f2] for c2 in F3W[robot] for f2 in _F3_FEATS if (c2, f2) != (c, f)}
                    lo = _f3_lp(robot, cons_f, F3W[robot], fx, (c, f, +1), capf, relax=True)
                    hi = _f3_lp(robot, cons_f, F3W[robot], fx, (c, f, -1), capf, relax=True)
                    if lo is None or hi is None:
                        continue
                    lo, hi = lo[0][c][f], hi[0][c][f]
                    if abs(v) > 1e-9 or hi - lo > 1e-6 and (lo < -1e-6 or hi > 1e-6):
                        tag = 'chắc' if hi - lo < 0.3 * max(1.0, abs(v)) else 'MƠ HỒ - nên chốt tay bằng pins='
                        print("      [%s] %-15s chọn %-8g khoảng [%.3f , %.3f]  %s" % (c, f, v, lo, hi, tag))
    except Exception as ex:
        print("   (bỏ qua bảng độ chắc: %s)" % ex)
    print("\n   KẾT QUẢ: %d/%d (%.2f%%)  train %d/%d  val %d/%d   (%.0fs)" % (
        a1, len(allidx), 100 * a1 / len(allidx), _f3_acc(allidx, wr, tr)[0], len(tr),
        _f3_acc(allidx, wr, va)[0], len(va), time.time() - t0))
    f3_show(robot)
    if a1 < a0:
        F3W[robot] = backup
        print("   (điểm giảm so với trước -> giữ trọng số cũ)")
        a1 = a0
    elif wr:
        print("   Còn %d ca sai -> chạy f3_diagnose(%d) để xem nguyên nhân." % (len(wr), robot))
    return a0, a1


def f3_fit_all(robots=(7, 4, 5, 8, 6, 3, 0, 1, 2), **kw):
    summ = []
    for r in robots:
        summ.append((r,) + tuple(f3_fit(r, **kw)))
    n = len(_F3D['scenes'])
    print("\n=== TỔNG KẾT ===")
    for r, a0, a1 in summ:
        print("  Robot %d: %.2f%% -> %.2f%%" % (r, 100 * a0 / n, 100 * a1 / n))


# ---------------------------------------------------------------------
# Xuất calculate_cost (6 tham số) tự chứa, không phụ thuộc biến nào của notebook
# ---------------------------------------------------------------------
_F3_COST_SRC = '''
def calculate_cost(robot_id, edge_data, curr_heading, next_heading, mission, weather):
    rain = (weather == 'rain')
    status = edge_data.get('status', 'normal')
    turn = (next_heading - curr_heading) % 4          # 0 thẳng, 1 phải, 2 quay đầu, 3 trái
    if robot_id == 6:
        ctx = 'urgent' if mission.get('urgent', False) else 'calm'
    elif robot_id == 7:
        ctx = 'fragile' if mission.get('fragile', False) else 'normal'
    else:
        ctx = 'all'
    w = F3_WEIGHTS.get(robot_id, {}).get(ctx)
    cost = 1.0
    if w is None:
        return cost
    if status == 'crowded':
        cost += w['crowded_rain'] if rain else w['crowded_dry']
    elif status == 'covered':
        cost += w['covered_rain'] if rain else w['covered_dry']
    if turn == 1: cost += w['right']
    elif turn == 3: cost += w['left']
    elif turn == 2: cost += w['uturn']
    if edge_data.get('oneway_to') is not None:
        cost += w['oneway']
        if status == 'crowded': cost += w['oneway_crowded']
    if edge_data.get('stairs', False):
        cost += w['stairs_rain'] if rain else w['stairs_dry']
    return cost
'''


def f3_export(path='/content/calculate_cost_final.py'):
    with open(path, 'w', encoding='utf-8') as f:
        f.write("# Sinh bởi robot_fit3.f3_export(). Cost đoạn = 1 + tổng phạt áp dụng. Tự chứa, chỉ dùng biến F3_WEIGHTS.\n")
        f.write("F3_WEIGHTS = {\n")
        for r in sorted(F3W):
            f.write("    %d: %s,\n" % (r, json.dumps(F3W[r])))
        f.write("}\n")
        f.write(_F3_COST_SRC)
    print("Đã ghi %s  -> exec file này SAU cell định nghĩa pipeline để thay calculate_cost" % path)